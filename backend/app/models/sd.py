"""Pydantic models for SchedulesDirect's JSON API shapes.

Field names/shapes follow SD's documented JSON Service
(https://json.schedulesdirect.org/) as of implementation time. SD's docs are
not versioned as strictly as a typical REST API, so treat the field set here
as "what we observed/documented," not an immutable contract — see
`docs/schedulesdirect-integration.md`. Only the fields epg-editor actually
uses are modeled; unknown extra fields from SD are ignored (not an error).

These models are used exclusively by `sd_client/` (request/response bodies)
and the cache wrapper models below (used by `storage/sd_cache.py`). Nothing
in here knows about epg-editor's own domain concepts (`Lineup`, `Channel`,
etc. live in `models/lineup.py`).
"""

from __future__ import annotations

import datetime as dt

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError, model_validator

# SD's JSON responses use a field literally named `datetime`. Several models
# below have a `datetime` field, which (with `from __future__ import
# annotations`) shadows a same-named type import inside the class body when
# Pydantic evaluates the forward-ref annotations — hence the `dt` alias for
# the actual `datetime.datetime` type throughout this module.


class SdModel(BaseModel):
    """Base class: tolerate unknown fields from SD's JSON responses."""

    model_config = ConfigDict(extra="ignore")


# --- Auth / token -----------------------------------------------------------


class SdTokenRequest(SdModel):
    """Body for `POST /token`.

    `password` must already be the SHA1 hex digest of the real password —
    callers (sd_client) are responsible for hashing; the raw password never
    gets this far into a model that could be logged or serialized elsewhere.
    """

    username: str
    password: str


class SdTokenResponse(SdModel):
    """Response from `POST /token`."""

    code: int
    message: str | None = None
    serverID: str | None = None
    datetime: dt.datetime | None = None
    token: str | None = None


# --- Account lineups ---------------------------------------------------------


class SdLineupSummary(SdModel):
    """One of the user's subscribed SD account lineups."""

    lineup: str
    name: str
    transport: str | None = None
    location: str | None = None
    uri: str | None = None


class SdAccountLineupsResponse(SdModel):
    """Response from `GET /lineups` (the account's subscribed lineups).

    `response`/`message` are only populated when SD returns an account-level
    error instead of a real lineups list (e.g.
    `{"code": 4003, "response": "ACCOUNT_LOCKOUT"}`) — see
    `SdClient.list_account_lineups`, which checks `code` explicitly rather
    than letting an error body validate as "zero lineups."
    """

    code: int | None = None
    response: str | None = None
    message: str | None = None
    serverID: str | None = None
    datetime: dt.datetime | None = None
    lineups: list[SdLineupSummary] = Field(default_factory=list)


class SdAddRemoveLineupResponse(SdModel):
    """Response from `PUT /lineups/{lineupID}` or `DELETE /lineups/{lineupID}`."""

    response: str | None = None
    code: int
    serverID: str | None = None
    message: str | None = None
    changesRemaining: int | None = None
    datetime: dt.datetime | None = None


# --- Account status -----------------------------------------------------------


class SdAccountStatusInfo(SdModel):
    """The `account` object nested within `GET /status`.

    `maxLineups` is the account-wide total number of lineup slots allowed
    (verified against SchedulesDirect/JSON-Service's wiki, "Getting
    status" section — https://github.com/SchedulesDirect/JSON-Service/wiki/API-20141201,
    fetched during implementation) — this is the account's total slot
    *limit*, not `SdAddRemoveLineupResponse.changesRemaining` (a separate,
    decrementing "lineup changes remaining" counter that rate-limits
    add/remove *operations*, not the number of lineups the account may
    hold at once).
    """

    expires: dt.datetime | None = None
    messages: list[dict[str, object]] = Field(default_factory=list)
    maxLineups: int | None = None


class SdStatusLineupSummary(SdModel):
    """One entry in `GET /status`'s `lineups` array.

    Deliberately a separate model from `SdLineupSummary` (`GET /lineups`'s
    shape): per SD's docs this array's entries carry `modified`/
    `isDeleted` rather than `name`/`transport`/`location`.
    """

    lineup: str | None = None
    modified: dt.datetime | None = None
    uri: str | None = None
    isDeleted: bool | None = None


class SdStatusResponse(SdModel):
    """Response from `GET /status`.

    Used by `services/sd_account.py` to compute the account's lineup-slot
    usage (`account.maxLineups` vs. the count of entries in `lineups` — see
    that module for why *every* entry counts, `isDeleted` or not) without
    needing a separate `GET /lineups` call — see
    `SdClient.get_account_status`.

    `response`/`message` are only populated when SD returns an account-level
    error instead of real status data (e.g.
    `{"code": 4003, "response": "ACCOUNT_LOCKOUT"}`) — `SdClient
    .get_account_status` checks `code` explicitly rather than letting an
    error body validate as an under-populated "no data" result.
    """

    code: int | None = None
    response: str | None = None
    message: str | None = None
    serverID: str | None = None
    datetime: dt.datetime | None = None
    account: SdAccountStatusInfo | None = None
    lineups: list[SdStatusLineupSummary] = Field(default_factory=list)
    lastDataUpdate: dt.datetime | None = None


# --- Lineup stations ---------------------------------------------------------


class SdStationLogo(SdModel):
    URL: str
    height: int | None = None
    width: int | None = None
    md5: str | None = None


class SdStation(SdModel):
    """A station entry from `GET /lineups/{lineupID}`."""

    stationID: str
    name: str
    callsign: str | None = None
    affiliate: str | None = None
    logo: SdStationLogo | None = None


class SdLineupMapEntry(SdModel):
    """A channel-number-to-station mapping entry from the same response."""

    stationID: str
    channel: str | None = None
    uhfVhf: int | None = None


class SdLineupStationsResponse(SdModel):
    """Response from `GET /lineups/{lineupID}`: a lineup's station roster.

    `code`/`response`/`message` are only populated when SD returns an
    error instead of a real roster (e.g. `{"code": 2100, "response":
    "LINEUP_NOT_FOUND"}`) — like `SdAccountLineupsResponse`/`SdStatusResponse`,
    every other field here is optional, so that would otherwise validate as
    an empty-but-successful roster instead of surfacing the error. See
    `SdClient.get_lineup_stations`, which checks `code` explicitly the same
    way `list_account_lineups`/`get_account_status` already do (reviewer
    finding: without this check, a cached station roster could be silently
    replaced by an empty one and stamped with SD's `modified` timestamp,
    suppressing a retry for up to `STATION_ROSTER_TTL`).
    """

    code: int | None = None
    response: str | None = None
    message: str | None = None
    map: list[SdLineupMapEntry] = Field(default_factory=list)
    stations: list[SdStation] = Field(default_factory=list)
    metadata: dict[str, object] | None = None


# --- Schedules ----------------------------------------------------------------


class SdScheduleRequest(SdModel):
    """One element of the body array for `POST /schedules`."""

    stationID: str
    date: list[str] = Field(default_factory=list)  # "YYYY-MM-DD"


class SdScheduleProgram(SdModel):
    """One scheduled airing within a station's day of programming."""

    programID: str
    airDateTime: dt.datetime
    duration: int  # seconds
    md5: str | None = None
    new: bool | None = None


class SdScheduleMetadata(SdModel):
    modified: dt.datetime | None = None
    md5: str | None = None
    startDate: str | None = None


class SdStationSchedule(SdModel):
    """Response element from `POST /schedules`: one station's one-day schedule.

    SD reports many per-station/day problems (e.g. `code=7100` /
    `response="SCHEDULE_QUEUED"` when a station's schedule isn't ready yet,
    or an invalid/unavailable station) as an item *within* an otherwise-200
    HTTP response, rather than as an HTTP-level error — this item then has
    no real `programs`/`metadata` to speak of. `code`/`response` are
    modeled here (rather than silently dropped by `SdModel`'s
    `extra="ignore"`) so `services/refresh.py` can detect a non-success
    `code` and record it instead of treating a blank schedule as a
    successful empty fetch. `code` is `None`/`0` for a normal, successful
    item.
    """

    stationID: str
    programs: list[SdScheduleProgram] = Field(default_factory=list)
    metadata: SdScheduleMetadata | None = None
    code: int | None = None
    response: str | None = None


class SdScheduleMd5DateEntry(SdModel):
    """One date's entry within `POST /schedules/md5`'s response.

    Verified against SchedulesDirect/JSON-Service's wiki ("Download the MD5
    and lastModified for stationIDs" section of API-20141201.md) during
    Phase 5 implementation — https://github.com/SchedulesDirect/JSON-Service/wiki/API-20141201.
    A normal entry carries `code=0`/`message="OK"` plus `lastModified`/`md5`;
    SD can presumably report a per-date problem (e.g. the same
    `7020 SCHEDULE_RANGE_EXCEEDED` family `get_schedules`'s per-item entries
    can carry) the same way, with no real `md5` to trust — the docs don't
    show a worked error example for this specific endpoint, but `code`/
    `response` are modeled defensively here (rather than silently dropped by
    `SdModel`'s `extra="ignore"`) so callers can check `code` before
    trusting `md5`, consistent with how `SdStationSchedule`/`SdProgram`
    above already handle their own per-item error shape.
    """

    code: int | None = None
    message: str | None = None
    response: str | None = None
    lastModified: dt.datetime | None = None
    md5: str | None = None


class SdScheduleMd5Response(RootModel[dict[str, dict[str, SdScheduleMd5DateEntry]]]):
    """Response from `POST /schedules/md5`: `stationID -> date -> md5 info`.

    SD's response here isn't a fixed-field object — it's a dict keyed
    dynamically by whatever `stationID`s were requested, each mapping to a
    dict keyed by whatever `date`s were requested — hence `RootModel` rather
    than a `SdModel` subclass with named fields. `SdClient.get_schedule_md5s`
    still passes the decoded body through `SdClient._raise_for_top_level_sd_error`
    first, the same as `get_schedules`/`get_programs`, to catch SD reporting
    a single account-wide error object instead of this per-station shape.

    Each station's entry is validated independently (see
    `_tolerate_malformed_station_entries` below) rather than validating the
    whole `dict[str, dict[str, SdScheduleMd5DateEntry]]` atomically: SD can
    report a per-station problem in a flatter shape than the expected
    per-date dict (e.g. `{"S1": {"code": 2201, ...}}` instead of
    `{"S1": {"2026-01-01": {"code": 0, "md5": "..."}}}`). Without
    per-station tolerance, that one malformed entry would fail validation
    for the *entire* response, and `services/refresh.py` would fall back to
    treating every mapped station/day as needing a full refetch — not just
    the one bad station. A station whose entry doesn't fit the expected
    shape is instead dropped from `root` entirely, so `for_station` returns
    `{}` for it — the same as a station SD didn't mention at all, which
    `_needs_schedule_fetch` already treats as "needs a full fetch."
    """

    root: dict[str, dict[str, SdScheduleMd5DateEntry]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _tolerate_malformed_station_entries(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        sanitized: dict[str, dict[str, SdScheduleMd5DateEntry]] = {}
        for station_id, value in data.items():
            sanitized[station_id] = cls._validate_station_entry(value)
        return sanitized

    @staticmethod
    def _validate_station_entry(value: Any) -> dict[str, SdScheduleMd5DateEntry]:
        """Validate one station's `date -> md5 info` entry, or `{}` on any
        shape/validation mismatch — see class docstring."""
        if not isinstance(value, dict):
            return {}
        try:
            return {
                date: SdScheduleMd5DateEntry.model_validate(entry)
                for date, entry in value.items()
            }
        except ValidationError:
            return {}

    def for_station(self, station_id: str) -> dict[str, SdScheduleMd5DateEntry]:
        """Convenience accessor: this station's `date -> md5 info` dict, or `{}`."""
        return self.root.get(station_id, {})


# --- Programs -----------------------------------------------------------------


class SdProgramTitle(SdModel):
    title120: str


class SdProgramDescriptionEntry(SdModel):
    descriptionLanguage: str | None = None
    description: str


class SdProgramMetadataEntry(SdModel):
    """One data source's season/episode info for a program (e.g. Gracenote).

    SD's `metadata` field on a `/programs` response item is a list of
    single-key objects keyed by the providing data source's name (observed:
    `"Gracenote"`; SD's docs also mention TVMaze) — see
    docs/schedulesdirect-integration.md. This models one such entry's
    *value*; `SdProgram.metadata` carries the provider name as the dict key
    rather than flattening it away, since a future caller might care which
    source a season/episode number came from.

    Per SD's docs: `totalEpisodes` means "episodes in this season" on an
    "EP" program but "episodes in the series" on an "SH" program; `season`
    is documented as mandatory-when-present but `episode`/`totalEpisodes`/
    `totalSeasons` are all optional — e.g. a program can carry a season
    number with no specific episode number, which is exactly the "SH"
    generic-series-reference case (no numbered episode identified).
    """

    season: int | None = None
    episode: int | None = None
    totalEpisodes: int | None = None
    totalSeasons: int | None = None


class SdProgram(SdModel):
    """Program metadata from `POST /programs`, keyed by program ID.

    Like `SdStationSchedule` above, SD can report a per-program error (e.g.
    an unknown/queued program ID) as an item with only `programID` and a
    `code`/`response`, no real title/description data. Modeled here so
    `services/refresh.py` can detect and record that instead of caching a
    blank/untitled program as if the fetch had succeeded. `code` is
    `None`/`0` for a normal, successful item.

    `entityType`/`showType`/`metadata` were added for docs/backlog.md item
    40 (Plex showing no series/episode info and misfiling episodes as
    movies): `services/xmltv.py` needs these to decide whether a programme
    is a movie or a series episode and to emit `<episode-num>`/`<sub-title>`
    correctly. **Cache-migration note**: a `CachedProgram` written by an
    earlier version of this app (before these fields existed) deserializes
    fine — they default to `None`/empty, same as a program SD itself didn't
    supply season/episode data for — but `services/refresh.py`'s md5-based
    skip logic means such a stale cache entry will *not* automatically
    re-fetch just because this app upgraded; nothing in its own data
    (SD's per-airing/program md5) changed. Since `cache/sd/` is fully
    regenerable and safe to delete per docs/data-model.md, the documented
    fix for an existing deployment upgrading to this version is a one-time
    manual `cache/sd/programs/` clear followed by a refresh (scheduled or
    `POST /api/refresh-now`) — see docs/backlog.md item 40's verification
    notes.
    """

    programID: str
    titles: list[SdProgramTitle] = Field(default_factory=list)
    descriptions: dict[str, list[SdProgramDescriptionEntry]] | None = None
    episodeTitle150: str | None = None
    originalAirDate: str | None = None
    genres: list[str] | None = None
    #: SD's own classification of the program (e.g. "Episode", "Series",
    #: "Movie", "Sports", "Special", ...) — per SD's docs this, not the
    #: programID's two-letter prefix, is the authoritative movie-vs-episode
    #: signal ("not all sports events will have a leading SP programID;
    #: your application should use the entity type").
    entityType: str | None = None
    #: A finer-grained description than `entityType` (e.g. "Feature Film"
    #: for a Movie-entityType program) — currently carried through for
    #: completeness/future use; `services/xmltv.py` keys its movie/series
    #: decision off `entityType`, not this field.
    showType: str | None = None
    #: Season/episode metadata, keyed by provider name — see
    #: `SdProgramMetadataEntry`. Empty when SD supplied none (most movies,
    #: and "SH"-prefixed generic series references with no specific episode
    #: identified).
    metadata: list[dict[str, SdProgramMetadataEntry]] = Field(default_factory=list)
    code: int | None = None
    response: str | None = None

    def primary_season_episode(self) -> SdProgramMetadataEntry | None:
        """The first season/episode metadata entry's value, if any.

        SD's `metadata` is a list of single-key `{provider: info}` objects;
        this returns the first entry's value regardless of which provider
        supplied it (SD's observed provider in practice is "Gracenote").
        Returns `None` when `metadata` is empty.
        """
        for entry in self.metadata:
            for value in entry.values():
                return value
        return None


# --- Cache wrapper models (used by storage/sd_cache.py) ----------------------
#
# Each wraps a raw SD response with a `fetchedAt` timestamp so the (future)
# refresh job can apply a TTL / use md5s to skip redundant re-fetches, per
# docs/data-model.md's note that cached entities need a fetched-at timestamp.


class CachedLineupStations(SdModel):
    """Cached station roster for one SD lineup.

    `modified` is SD's own `GET /status` `lineups[].modified` timestamp for
    this SD lineup *as of the fetch that produced this cache entry* — not a
    live/recomputed value. `services/refresh.py`'s scheduled-refresh job
    compares this against a freshly-fetched `modified` value (plus a 30-day
    TTL fallback keyed off `fetchedAt`) to decide whether this roster needs
    re-fetching, per docs/backlog.md item 29's scope. `None` for entries
    written before this field existed, or when no `GET /status` lineup
    entry was available at fetch time — either case is treated as "unknown,
    refetch to establish a baseline" by the refresh job rather than being
    read as "definitely unchanged."
    """

    fetchedAt: dt.datetime
    sdLineupId: str
    modified: dt.datetime | None = None
    data: SdLineupStationsResponse


class CachedStationSchedule(SdModel):
    fetchedAt: dt.datetime
    stationId: str
    date: str  # "YYYY-MM-DD"
    data: SdStationSchedule


class CachedProgram(SdModel):
    """Cached program metadata for one SD program ID.

    `scheduleMd5` records the per-airing `SdScheduleProgram.md5` value (from
    whichever schedule day this program was fetched on behalf of) *as of the
    fetch that produced this cache entry* — not SD's own program-level data,
    which has no md5 of its own. `services/refresh.py`'s refresh job compares
    this against the md5 a *current* cached schedule reports for the same
    program ID to decide whether this program needs re-fetching, independent
    of whether that schedule day's own md5 happened to change this run — see
    that module's docstring for why this independence matters (a schedule
    day can go unchanged for months while a program fetch that failed on an
    earlier run would otherwise never be retried). `None` for entries
    written before this field existed, or when the schedule entry that
    prompted the fetch had no md5 of its own — either case means "unknown,
    refetch on any future mismatch" rather than "definitely still correct."
    """

    fetchedAt: dt.datetime
    data: SdProgram
    scheduleMd5: str | None = None
