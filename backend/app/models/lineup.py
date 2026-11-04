"""Domain Pydantic models for epg-editor's own data.

These mirror `/data/config/lineups.json` exactly as specified in
`docs/data-model.md`. `storage/lineups.py` loads/saves `LineupsFile`
instances; nothing outside `storage/` should read or write the JSON file
directly.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, model_validator


class LineupSource(str, Enum):
    """How an epg-editor lineup's channel list was populated."""

    MANUAL = "manual"
    M3U = "m3u"


#: A channel's display name must be non-empty after trimming surrounding
#: whitespace. `strip_whitespace=True` normalizes the stored value (so
#: `"  KGO-TV  "` is persisted as `"KGO-TV"`) *before* `min_length=1` is
#: checked, so whitespace-only input (e.g. `"   "`) is rejected the same as
#: `""` rather than being accepted as a non-empty-looking blank name.
NonEmptyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MappingSuggestion(BaseModel):
    """A single candidate SD station suggested for a channel.

    Populated by the suggestion-scoring service (`services/suggestions.py`).
    Recomputed wholesale each time suggestions are (re)run for a channel —
    never accumulated across runs.

    `stationName`/`callsign`/`logoUrl` are **display-only, response-time
    enrichment fields** — see `services.suggestions.enrich_lineup_suggestions`
    (checkpoint 25's fix for "the suggestion review UI only shows a bare SD
    station ID"). They default to `None` and are populated *only* by that
    enrichment step, applied to a `Lineup` already loaded from storage,
    right before it's returned from `GET /api/lineups` / `GET
    /api/lineups/{lineup_id}`. Nothing that writes back to
    `config/lineups.json` (`storage.lineups.update_lineups` and friends)
    ever sees a non-`None` value here — `docs/data-model.md`'s persisted
    `mapping.suggestions` shape stays the minimal
    `{sdStationId, sdLineupId, score}` it documents. Added as fields on this
    model (rather than a parallel API-only response model wrapping
    `Lineup`/`Channel`/`ChannelMapping`) because `api/lineups.py`'s
    `GET` routes already use `response_model=Lineup`/`list[Lineup]` directly
    against service-returned domain objects — extending the domain model
    with optional, always-defaulted-`None` fields is far less invasive than
    introducing and threading a second parallel model hierarchy just for two
    read endpoints.
    """

    sdStationId: str
    sdLineupId: str
    score: float
    stationName: str | None = None
    callsign: str | None = None
    logoUrl: str | None = None


class ChannelMapping(BaseModel):
    """A channel's association with a SchedulesDirect station.

    "Mapped" is derived purely from `sdStationId`/`sdLineupId` being
    non-`None` — there is no separate gating boolean (see docs/backlog.md
    item 38). `suggestions` populated with `sdStationId` still `None` is the
    "needs review" state the bulk-accept flow operates on. `sdStationId`/
    `sdLineupId` are `None` until a suggestion is accepted or the user sets
    a mapping directly via the manual mapping-set endpoint (Phase 1 item 8).

    `mappedAt` is a plain audit/diagnostic timestamp — "when was this
    mapping set" — not a gate; it's set whenever `sdStationId` is set, and
    left `None` otherwise.
    """

    sdStationId: str | None = None
    sdLineupId: str | None = None
    mappedAt: datetime | None = None
    suggestions: list[MappingSuggestion] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_confirmed_at(cls, data: Any) -> Any:
        """Carry forward pre-item-38 `confirmed`/`confirmedAt` data.

        Real production data (Andrew's own `/data/config/lineups.json`)
        already has `ChannelMapping` records shaped like
        `{"confirmed": true/false, "confirmedAt": "<timestamp>", ...}` from
        before this refactor. Pydantic v2 silently drops unknown extra keys
        on its own, which would otherwise lose the `confirmedAt` audit
        timestamp for every mapping already on disk the first time it's
        loaded and re-saved. This runs before field validation and, only
        when the new `mappedAt` key isn't already present, copies a legacy
        `confirmedAt` value over to `mappedAt`.

        Deliberately does *not* try to recover a timestamp for the "bug
        state" this refactor fixes (`sdStationId` set, `confirmed: false`,
        `confirmedAt: null`) — there's no original timestamp to carry
        forward there, and fabricating one with `now()` would misrepresent
        when the mapping was actually set. That record simply loads with
        `mappedAt = None`, and is correctly treated as mapped under the new
        `sdStationId is not None` derivation — the intended behavioral fix,
        not a gap.
        """
        if not isinstance(data, dict):
            return data
        if data.get("mappedAt") is None and data.get("confirmedAt") is not None:
            data = {**data, "mappedAt": data["confirmedAt"]}
        return data


class Channel(BaseModel):
    """A single channel within an epg-editor lineup."""

    id: str
    number: str | None = None
    name: NonEmptyName
    logoUrl: str | None = None
    tvgId: str | None = None
    #: From an M3U entry's `group-title` attribute (e.g. "Local", "Sports").
    #: `None` for manually-added channels and for M3U entries that didn't
    #: specify one. Persisted (rather than surfaced only in the import
    #: response) so it survives for later UI grouping/filtering, not just
    #: for a single import's review screen — see Phase 2 backend-developer
    #: report for the reasoning (CLAUDE.md's Core workflow 1 explicitly
    #: calls out `group-title` as parsed metadata alongside `tvg-id`/
    #: `tvg-name`/`tvg-logo`, all of which already have a persisted field).
    group: str | None = None
    sourceStreamUrl: str | None = None
    missingSince: datetime | None = None
    mapping: ChannelMapping | None = None


class Lineup(BaseModel):
    """An epg-editor lineup: a named list of channels plus SD associations."""

    id: str
    name: str
    source: LineupSource
    createdAt: datetime
    updatedAt: datetime
    sdLineupIds: list[str] = Field(default_factory=list)
    channels: list[Channel] = Field(default_factory=list)


class LineupsFile(BaseModel):
    """The full contents of `/data/config/lineups.json`."""

    schemaVersion: int = 1
    lineups: list[Lineup] = Field(default_factory=list)
