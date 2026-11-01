"""Global, all-lineups scheduled/manual SD refresh pipeline (Phase 5, item 29).

This is the pipeline CLAUDE.md's "Guide refresh" section describes: the
APScheduler job (`scheduler/jobs.py`) and the manual "refresh now" endpoint
(`api/refresh.py`) both call `refresh_all_lineups` directly, so they run
identically on demand or on a timer.

This is the *only* SD sync/generate pipeline in the app — it fully
replaced and superseded an earlier Phase 1 stopgap, a per-lineup
`sync_and_generate` manual trigger (`services/sync.py`/`api/sync.py`/
`models/sync.py`) that had no md5-based skip-if-unchanged optimization.
That stopgap was removed once this pipeline existed; see docs/backlog.md
item 29's closing note. What makes this pipeline the "real" one:

- It covers *every* epg-editor lineup in one run, not one.
- It refreshes each distinct associated SD lineup's station roster
  (`storage/sd_cache.py`'s `CachedLineupStations`) when SD's own `modified`
  timestamp (from `GET /status`) is newer than what's cached, or when the
  cached roster has exceeded `STATION_ROSTER_TTL` regardless of
  `modified` — see `_should_refresh_station_roster`. Phase 3's suggestion
  generation caches a lineup's roster on first fetch with no expiry of its
  own by design; this is where that staleness gets resolved.
- It uses `SdClient.get_schedule_md5s` (SD's lighter `/schedules/md5`
  endpoint) to skip a full `get_schedules` re-fetch for any station/day
  whose md5 hasn't changed since what's already cached — the actual
  "respect SD's rate limits" point of this phase.

Still respects "no speculative bulk-fetching": schedule/program data is
only ever fetched for SD stations that are actually `confirmed`-mapped to a
channel in some epg-editor lineup (via `services.xmltv
.confirmed_mapped_channels`) — station *rosters* are the one exception,
refreshed for every SD lineup associated with any epg-editor lineup (not
just mapped stations) because the roster itself is the candidate pool
suggestion-generation draws from, not schedule/program data.

One bad SD lineup, one bad epg-editor lineup, or one bad station doesn't
abort the whole run: failures are collected into `RefreshResult.errors`
and the run continues with everything else. The one exception is an
*auth/account-level* `SdClientError` (`SdClientError.is_auth_error`): that's
let propagate uncaught, because every subsequent SD call would fail
identically — there's nothing useful to do except stop immediately rather
than keep burning SD calls against a broken account. Callers (the API
route, the scheduler job) decide how to surface that.

Depends only on `sd_client/` + `storage/` + other `services/` modules —
never raw HTTP or raw file I/O itself, per CLAUDE.md's module layering.
Callers supply an already-constructed `SdClient` (same dependency-
injection pattern as `services/suggestions.py`), so this stays testable
with `httpx.MockTransport` and zero real credentials.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.lineup import Lineup
from app.models.refresh import RefreshError, RefreshResult
from app.models.sd import (
    CachedLineupStations,
    CachedStationSchedule,
    SdScheduleMd5DateEntry,
    SdScheduleRequest,
    SdStationSchedule,
)
from app.sd_client.client import SdClient, SdClientError
from app.services.lineups import list_lineups
from app.services.xmltv import (
    GUIDE_WINDOW_DAYS,
    confirmed_mapped_channels,
    generate_xmltv_for_lineup_id,
    guide_window_dates,
)
from app.storage import sd_cache

#: Fallback TTL for a cached SD lineup station roster: refetch unconditionally
#: once this old, even if SD's own `modified` timestamp didn't change (or
#: wasn't available). A backend constant, not user-configurable, per the
#: product owner's decision recorded in docs/backlog.md item 29 — station
#: rosters change rarely enough that this is purely a "don't go stale
#: forever if `GET /status` ever fails to report this lineup" safety net,
#: not a tuning knob.
STATION_ROSTER_TTL = timedelta(days=30)


def _should_refresh_station_roster(
    cached: CachedLineupStations | None,
    sd_modified: datetime | None,
    now: datetime,
) -> bool:
    """Whether a SD lineup's cached station roster needs re-fetching.

    - Never cached at all -> always refresh.
    - Cached longer ago than `STATION_ROSTER_TTL` -> always refresh,
      regardless of `modified` (the fallback safety net).
    - Otherwise, refresh only if SD's current `modified` timestamp is newer
      than the one recorded at the cached entry's own fetch time, or if we
      have a current `modified` value but no recorded one to compare
      against (treated as "unknown, refresh to establish a baseline").
    - If SD didn't report a `modified` value for this lineup at all (e.g.
      it's missing from `GET /status`'s `lineups` array) and the TTL hasn't
      expired, don't refresh — nothing suggests it changed.
    """
    if cached is None:
        return True
    if now - cached.fetchedAt > STATION_ROSTER_TTL:
        return True
    if sd_modified is None:
        return False
    if cached.modified is None:
        return True
    return sd_modified > cached.modified


def _needs_schedule_fetch(
    md5_entry: SdScheduleMd5DateEntry | None,
    cached_schedule: CachedStationSchedule | None,
) -> bool:
    """Whether a station/day's full schedule needs re-fetching.

    Missing/error-coded/un-cached inputs all default to "needs fetch" — the
    safe default when there isn't enough information to prove "unchanged".
    """
    if md5_entry is None:
        return True
    if md5_entry.code not in (None, 0):
        return True
    if not md5_entry.md5:
        return True
    if cached_schedule is None:
        return True
    metadata = cached_schedule.data.metadata
    cached_md5 = metadata.md5 if metadata is not None else None
    if not cached_md5:
        return True
    return cached_md5 != md5_entry.md5


def _distinct_mapped_station_ids(lineups: list[Lineup]) -> dict[str, set[str]]:
    """`lineup.id -> {sdStationId, ...}` for every confirmed-mapped channel.

    Reuses `services.xmltv.confirmed_mapped_channels` rather than
    re-deriving it, per CLAUDE.md's instruction to share, not duplicate,
    that logic.
    """
    result: dict[str, set[str]] = {}
    for lineup in lineups:
        mapped = confirmed_mapped_channels(lineup)
        result[lineup.id] = {
            channel.mapping.sdStationId
            for channel in mapped
            if channel.mapping is not None and channel.mapping.sdStationId
        }
    return result


async def refresh_all_lineups(
    sd_client: SdClient,
    *,
    guide_window_days: int = GUIDE_WINDOW_DAYS,
    base_dir: Path | None = None,
    now: datetime | None = None,
) -> RefreshResult:
    """Run one full refresh cycle across every epg-editor lineup.

    Called identically by the scheduled APScheduler job
    (`scheduler/jobs.py`) and the manual `POST /api/refresh-now` endpoint
    (`api/refresh.py`) — see module docstring. Raises `SdClientError`
    uncaught only for an auth/account-level failure
    (`SdClientError.is_auth_error`); every other failure is collected into
    the returned `RefreshResult.errors` and the run continues.
    """
    current_time = now if now is not None else datetime.now(timezone.utc)
    dates = guide_window_dates(current_time, guide_window_days)
    result = RefreshResult()

    lineups = list_lineups()

    # Validate SD auth once, upfront, deliberately uncaught: any failure
    # here (not just an auth/account-level one per
    # `SdClientError.is_auth_error`) means every subsequent call in this
    # run would fail identically, so there's nothing useful to do except
    # stop immediately and let the caller (the API route, the scheduler
    # job) handle it, rather than quietly recording it as one more
    # `RefreshError` and proceeding as if the rest of the run could still
    # succeed.
    await sd_client.get_token()

    # --- 1. Account status: general health + per-SD-lineup `modified` ------
    status_modified_by_lineup: dict[str, datetime | None] = {}
    try:
        status = await sd_client.get_account_status()
    except SdClientError as exc:
        if exc.is_auth_error:
            raise
        result.errors.append(
            RefreshError(scope="account", message=f"could not fetch SD account status: {exc}")
        )
    else:
        for entry in status.lineups:
            if entry.lineup:
                status_modified_by_lineup[entry.lineup] = entry.modified

    # --- 2. Station roster refresh, per distinct associated SD lineup ------
    distinct_sd_lineup_ids = sorted({sd_id for lineup in lineups for sd_id in lineup.sdLineupIds})
    for sd_lineup_id in distinct_sd_lineup_ids:
        cached = sd_cache.load_lineup_stations(sd_lineup_id, base_dir=base_dir)
        sd_modified = status_modified_by_lineup.get(sd_lineup_id)
        if not _should_refresh_station_roster(cached, sd_modified, current_time):
            result.stationRostersSkipped += 1
            continue
        try:
            stations = await sd_client.get_lineup_stations(sd_lineup_id)
        except SdClientError as exc:
            if exc.is_auth_error:
                raise
            result.errors.append(
                RefreshError(scope="sd_lineup", id=sd_lineup_id, message=str(exc))
            )
            continue
        sd_cache.save_lineup_stations(
            sd_lineup_id,
            stations,
            modified=sd_modified,
            fetched_at=current_time,
            base_dir=base_dir,
        )
        result.stationRostersRefreshed += 1

    # --- 3. Schedule refresh: md5-check every confirmed-mapped station ------
    station_ids_by_lineup = _distinct_mapped_station_ids(lineups)
    all_station_ids = sorted({sid for ids in station_ids_by_lineup.values() for sid in ids})

    md5_by_station: dict[str, dict[str, SdScheduleMd5DateEntry]] = {}
    if all_station_ids:
        try:
            md5_response = await sd_client.get_schedule_md5s(
                [SdScheduleRequest(stationID=sid, date=dates) for sid in all_station_ids]
            )
        except SdClientError as exc:
            if exc.is_auth_error:
                raise
            # Can't tell what changed — fall back to treating every
            # mapped station/day as needing a full fetch rather than
            # silently skipping schedule refresh entirely for this run.
            result.errors.append(
                RefreshError(scope="account", message=f"schedule md5 check failed: {exc}")
            )
        else:
            md5_by_station = {sid: md5_response.for_station(sid) for sid in all_station_ids}

    # `schedule_data_by_station_date` ends up holding the *current* schedule
    # data for every mapped station/day in the guide window that we have any
    # data for at all — whether that data came from this run's refetch below,
    # or was already cached and confirmed unchanged by the md5 check above.
    # Step 4 scans this (not just what got refetched this run) to decide
    # which programs need fetching — see that step's comment for why that
    # distinction is the whole point of this fix.
    schedule_data_by_station_date: dict[tuple[str, str], SdStationSchedule] = {}

    stations_needing_dates: dict[str, list[str]] = {}
    for station_id in all_station_ids:
        date_entries = md5_by_station.get(station_id, {})
        for date in dates:
            result.scheduleDaysChecked += 1
            cached_schedule = sd_cache.load_station_schedule(station_id, date, base_dir=base_dir)
            entry = date_entries.get(date) if date_entries else None
            if _needs_schedule_fetch(entry, cached_schedule):
                stations_needing_dates.setdefault(station_id, []).append(date)
            else:
                result.scheduleDaysSkippedUnchanged += 1
                if cached_schedule is not None:
                    schedule_data_by_station_date[(station_id, date)] = cached_schedule.data

    for station_id, fetch_dates in stations_needing_dates.items():
        try:
            schedules = await sd_client.get_schedules(
                [SdScheduleRequest(stationID=station_id, date=fetch_dates)]
            )
        except SdClientError as exc:
            if exc.is_auth_error:
                raise
            result.errors.append(
                RefreshError(scope="station", id=station_id, message=str(exc))
            )
            continue
        for schedule in schedules:
            if schedule.code not in (None, 0):
                result.errors.append(
                    RefreshError(
                        scope="station",
                        id=schedule.stationID or station_id,
                        message=(
                            f"SD reported schedule error {schedule.code}"
                            f" ({schedule.response or 'no further detail'})"
                        ),
                    )
                )
                continue
            schedule_date = schedule.metadata.startDate if schedule.metadata else None
            if schedule_date is None:
                continue
            sd_cache.save_station_schedule(
                station_id, schedule_date, schedule, fetched_at=current_time, base_dir=base_dir
            )
            result.scheduleDaysRefetched += 1
            schedule_data_by_station_date[(station_id, schedule_date)] = schedule

    # --- 4. Program metadata for everything referenced in the guide window --
    #
    # Deliberately scans *every* station/day we have current schedule data
    # for (`schedule_data_by_station_date`, built above from both this run's
    # refetches and days that were skipped as unchanged) rather than only
    # the schedule days refetched this run. Building this set from only
    # this-run refetches was the bug (reviewer finding, HIGH severity): once
    # a schedule day's md5 stops changing, it's skipped on every subsequent
    # run, so a `/programs` failure on *this* run's fetch for that day's
    # programs would otherwise never be retried again — the guide would
    # permanently show "Unknown" for those airings with no further error
    # anywhere after the one that caused it. Scanning the full cached guide
    # window every run means a previously-failed (or never-attempted)
    # program fetch gets another chance as long as its schedule entry is
    # still in the window, independent of that day's own md5.
    #
    # Also newly adds a program-level md5 skip (previously entirely
    # missing): a program already cached with a matching
    # `CachedProgram.scheduleMd5` (the per-airing md5 SD reported alongside
    # it) is left alone rather than re-fetched on every run that happens to
    # refetch its schedule day.
    program_md5_by_id: dict[str, str | None] = {}
    for schedule_data in schedule_data_by_station_date.values():
        for program in schedule_data.programs:
            program_md5_by_id[program.programID] = program.md5

    program_ids_needing_fetch: list[str] = []
    for program_id, expected_md5 in program_md5_by_id.items():
        cached_program = sd_cache.load_program(program_id, base_dir=base_dir)
        if cached_program is None:
            program_ids_needing_fetch.append(program_id)
            continue
        if expected_md5 is not None and cached_program.scheduleMd5 != expected_md5:
            program_ids_needing_fetch.append(program_id)

    if program_ids_needing_fetch:
        try:
            # `SdClient.get_programs` chunks internally at SD's documented
            # per-request cap — this set is the union across every mapped
            # station's guide window and can exceed that on a large real
            # account.
            programs = await sd_client.get_programs(sorted(program_ids_needing_fetch))
        except SdClientError as exc:
            if exc.is_auth_error:
                raise
            result.errors.append(
                RefreshError(scope="programs", message=f"fetching program metadata failed: {exc}")
            )
        else:
            for program in programs:
                if program.code not in (None, 0):
                    result.errors.append(
                        RefreshError(
                            scope="programs",
                            id=program.programID,
                            message=(
                                f"SD reported program error {program.code}"
                                f" ({program.response or 'no further detail'})"
                            ),
                        )
                    )
                    continue
                sd_cache.save_program(
                    program.programID,
                    program,
                    schedule_md5=program_md5_by_id.get(program.programID),
                    fetched_at=current_time,
                    base_dir=base_dir,
                )
                result.programsFetched += 1

    # --- 5. Regenerate XMLTV for every lineup --------------------------------
    # Cheap/local (no SD cost), so always regenerate rather than tracking
    # "did anything actually change for this lineup" — see module docstring.
    for lineup in lineups:
        result.lineupsProcessed += 1
        try:
            generate_xmltv_for_lineup_id(
                lineup.id,
                now=current_time,
                guide_window_days=guide_window_days,
                base_dir=base_dir,
            )
        except Exception as exc:  # noqa: BLE001 — one bad lineup must not abort the run
            result.errors.append(RefreshError(scope="lineup", id=lineup.id, message=str(exc)))
            continue
        result.lineupsRegenerated += 1

    return result
