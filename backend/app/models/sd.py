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

from pydantic import BaseModel, ConfigDict, Field

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
    """Response from `GET /lineups/{lineupID}`: a lineup's station roster."""

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
    `extra="ignore"`) so `services/sync.py` can detect a non-success `code`
    and record it instead of treating a blank schedule as a successful
    empty fetch. `code` is `None`/`0` for a normal, successful item.
    """

    stationID: str
    programs: list[SdScheduleProgram] = Field(default_factory=list)
    metadata: SdScheduleMetadata | None = None
    code: int | None = None
    response: str | None = None


# A dedicated `POST /schedules/md5`-only response model isn't defined here:
# `SdClient` doesn't call that endpoint yet (the md5-driven "skip unchanged
# schedules" optimization is Phase 5/scheduler work per docs/backlog.md).
# `SdStationSchedule` above already carries an md5 per program plus a
# `metadata.md5` for the whole station-day, which is what the Phase 1
# models need.


# --- Programs -----------------------------------------------------------------


class SdProgramTitle(SdModel):
    title120: str


class SdProgramDescriptionEntry(SdModel):
    descriptionLanguage: str | None = None
    description: str


class SdProgram(SdModel):
    """Program metadata from `POST /programs`, keyed by program ID.

    Like `SdStationSchedule` above, SD can report a per-program error (e.g.
    an unknown/queued program ID) as an item with only `programID` and a
    `code`/`response`, no real title/description data. Modeled here so
    `services/sync.py` can detect and record that instead of caching a
    blank/untitled program as if the fetch had succeeded. `code` is
    `None`/`0` for a normal, successful item.
    """

    programID: str
    titles: list[SdProgramTitle] = Field(default_factory=list)
    descriptions: dict[str, list[SdProgramDescriptionEntry]] | None = None
    episodeTitle150: str | None = None
    originalAirDate: str | None = None
    genres: list[str] | None = None
    code: int | None = None
    response: str | None = None


# --- Cache wrapper models (used by storage/sd_cache.py) ----------------------
#
# Each wraps a raw SD response with a `fetchedAt` timestamp so the (future)
# refresh job can apply a TTL / use md5s to skip redundant re-fetches, per
# docs/data-model.md's note that cached entities need a fetched-at timestamp.


class CachedLineupStations(SdModel):
    fetchedAt: dt.datetime
    sdLineupId: str
    data: SdLineupStationsResponse


class CachedStationSchedule(SdModel):
    fetchedAt: dt.datetime
    stationId: str
    date: str  # "YYYY-MM-DD"
    data: SdStationSchedule


class CachedProgram(SdModel):
    fetchedAt: dt.datetime
    data: SdProgram
