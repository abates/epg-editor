"""Manual, on-demand "sync SD data + generate XMLTV" trigger for one lineup.

Phase 1 pulled a minimal version of this forward from its original Phase 5
slot so checkpoint 14 (testing against a real SchedulesDirect account) is
actually exercisable through the app before the scheduler exists. This is
deliberately minimal:

- No APScheduler wiring and no automatic/background triggering — this is
  invoked only by the `POST /api/lineups/{lineup_id}/sync-and-generate`
  route, on demand.
- No md5-based "has this changed" skip-fetch optimization. SD exposes
  per-station/day md5 hashes (see docs/schedulesdirect-integration.md) but
  using them to avoid redundant re-fetches is explicitly deferred to
  Phase 5's scheduled-refresh job — every call here always fetches fresh,
  full schedule/program data for the stations it syncs.

What it *does* respect from day one is SD's "no speculative bulk-fetching"
rule: it fetches schedules/programs only for the distinct `sdStationId`s
that this lineup's *confirmed*-mapped channels actually reference (reusing
`services.xmltv.confirmed_mapped_channels` rather than re-deriving that
filter), never an SD lineup's full station roster.

Depends only on `sd_client/` + `storage/` + other `services/` modules —
never raw HTTP or raw file I/O itself, per CLAUDE.md's module layering.
Callers supply an already-constructed `SdClient` (e.g.
`SdClient.from_env()`, built by the API layer) rather than this module
constructing one itself: that keeps this function trivially testable with
a `httpx.MockTransport`-backed client, with zero real credentials/network
touched anywhere in the test suite.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.models.sd import SdScheduleRequest
from app.models.sync import StationSyncError, SyncResult
from app.sd_client.client import SdClient, SdClientError
from app.services.lineups import get_lineup
from app.services.xmltv import (
    GUIDE_WINDOW_DAYS,
    confirmed_mapped_channels,
    generate_xmltv_for_lineup_id,
    guide_window_dates,
)
from app.storage import sd_cache


async def sync_and_generate(
    lineup_id: str,
    sd_client: SdClient,
    *,
    guide_window_days: int = GUIDE_WINDOW_DAYS,
    base_dir: Path | None = None,
    now: datetime | None = None,
) -> SyncResult:
    """Sync fresh SD data for `lineup_id`'s confirmed-mapped stations, then
    regenerate its XMLTV file.

    Raises `services.lineups.NotFoundError` if no such lineup exists.

    Raises `sd_client.client.SdClientError` (uncaught) if SD rejects the
    initial token request (e.g. bad credentials) *and* there's at least
    one station to sync, or if any later per-station/programs call fails
    with an *auth/account-level* `SdClientError` (see
    `SdClientError.is_auth_error` — e.g. a 401/403, a revoked token, an
    account lockout). This is deliberately not swallowed/collected into
    `SyncResult.stationErrors` the way an individual station's own
    data-quality failure is below: an auth/account failure would make every
    subsequent call fail identically, not a one-station data-quality issue,
    so there's nothing useful to do except stop immediately (rather than
    keep burning SD calls against a broken account) and let the caller (the
    API route) turn it into a clean 4xx/502 with SD's real error message,
    rather than quietly reporting a sync that "completed with partial
    failures." A lineup with nothing confirmed-mapped never reaches this
    check at all — it trivially succeeds without touching SD, consistent
    with "no speculative fetching."

    An individual station's `get_schedules` call failing for a
    *non-auth-level* reason (e.g. an invalid/removed station id, a
    transport timeout talking to SD, a malformed response body) is instead
    recorded in `SyncResult.stationErrors` and the sync continues with the
    remaining stations. SD can also report a per-station/day problem (e.g.
    `code=7100` "schedule not ready yet") as a normal-looking 200 response
    item rather than a request failure — that's detected via
    `SdStationSchedule.code` and recorded the same way. The final
    `get_programs` batch call failing outright, or an individual returned
    program carrying an error `code`, is likewise recorded (in
    `SyncResult.errors`) rather than aborting. Either way, generation still
    runs afterward against whatever data *did* get cached.
    """
    lineup = get_lineup(lineup_id)
    current_time = now if now is not None else datetime.now(timezone.utc)
    dates = guide_window_dates(current_time, guide_window_days)

    mapped_channels = confirmed_mapped_channels(lineup)
    station_ids = sorted(
        {
            channel.mapping.sdStationId
            for channel in mapped_channels
            if channel.mapping is not None and channel.mapping.sdStationId
        }
    )

    result = SyncResult(lineupId=lineup_id, channelsGenerated=len(mapped_channels))

    if station_ids:
        # Validate SD auth once, upfront — see docstring for why this is
        # intentionally not caught/collected per-station.
        await sd_client.get_token()

    # NOTE: `get_programs` below is called once per sync with every distinct
    # program ID collected across all synced stations, with no chunking of
    # that id list. SD's `/programs` endpoint documents a per-request ID
    # limit; a lineup large enough to exceed it would need this call split
    # into batches. Deferred per review — not worth building for Andrew's
    # initial test lineup's scale; revisit if/when a real lineup is large
    # enough to hit SD's limit.
    program_ids: set[str] = set()
    for station_id in station_ids:
        try:
            schedules = await sd_client.get_schedules(
                [SdScheduleRequest(stationID=station_id, date=dates)]
            )
        except SdClientError as exc:
            if exc.is_auth_error:
                # Account/token-wide failure, not a one-station data
                # problem — stop burning SD calls against a broken account
                # and let this propagate to the caller's 502 path. See the
                # docstring above.
                raise
            result.stationErrors.append(
                StationSyncError(sdStationId=station_id, message=str(exc))
            )
            continue

        result.stationsSynced += 1
        for schedule in schedules:
            if schedule.code not in (None, 0):
                result.stationErrors.append(
                    StationSyncError(
                        sdStationId=schedule.stationID or station_id,
                        message=(
                            f"SD reported schedule error {schedule.code}"
                            f" ({schedule.response or 'no further detail'})"
                        ),
                    )
                )
                continue
            schedule_date = schedule.metadata.startDate if schedule.metadata else None
            if schedule_date is None:
                # Malformed/unexpected SD response shape — skip caching this
                # one entry rather than crashing the whole sync over it.
                continue
            sd_cache.save_station_schedule(
                station_id, schedule_date, schedule, base_dir=base_dir
            )
            result.scheduleDaysFetched += 1
            program_ids.update(program.programID for program in schedule.programs)

    if program_ids:
        try:
            programs = await sd_client.get_programs(sorted(program_ids))
        except SdClientError as exc:
            if exc.is_auth_error:
                raise
            result.errors.append(f"fetching program metadata failed: {exc}")
        else:
            for program in programs:
                if program.code not in (None, 0):
                    result.errors.append(
                        f"SD reported program error {program.code} for "
                        f"program {program.programID} "
                        f"({program.response or 'no further detail'})"
                    )
                    continue
                sd_cache.save_program(program.programID, program, base_dir=base_dir)
                result.programsFetched += 1

    generate_xmltv_for_lineup_id(
        lineup_id,
        now=current_time,
        guide_window_days=guide_window_days,
        base_dir=base_dir,
    )

    return result
