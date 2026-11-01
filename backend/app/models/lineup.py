"""Domain Pydantic models for epg-editor's own data.

These mirror `/data/config/lineups.json` exactly as specified in
`docs/data-model.md`. `storage/lineups.py` loads/saves `LineupsFile`
instances; nothing outside `storage/` should read or write the JSON file
directly.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


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

    Populated by the (not-yet-built, Phase 3) suggestion-scoring service.
    Recomputed wholesale each time suggestions are (re)run for a channel —
    never accumulated across runs.
    """

    sdStationId: str
    sdLineupId: str
    score: float


class ChannelMapping(BaseModel):
    """A channel's association with a SchedulesDirect station.

    `confirmed=False` with `suggestions` populated is the "needs review"
    state the (future) bulk-accept flow operates on. `sdStationId`/
    `sdLineupId` are `None` until a suggestion is accepted or the user sets
    a mapping directly via the manual-confirm endpoint (Phase 1 item 8).
    """

    sdStationId: str | None = None
    sdLineupId: str | None = None
    confirmed: bool = False
    confirmedAt: datetime | None = None
    suggestions: list[MappingSuggestion] = Field(default_factory=list)


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
