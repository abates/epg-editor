"""Pydantic models for mapping-suggestion generation and bulk-accept.

See `services/suggestions.py` (the business logic that produces these) and
`api/suggestions.py` (the `POST /api/lineups/{lineup_id}/suggestions` and
`POST /api/lineups/{lineup_id}/bulk-accept-suggestions` routes that return
them as response bodies).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChannelSuggestionCount(BaseModel):
    """How many candidate suggestions were (re)computed for one channel.

    Capped at `services.suggestions.MAX_SUGGESTIONS_PER_CHANNEL` even when
    the candidate station pool is larger — see that module for why.
    """

    channelId: str
    suggestionCount: int


class SuggestionResult(BaseModel):
    """Outcome of one `generate_suggestions` run for a single epg-editor lineup."""

    lineupId: str
    #: Size of the deduped candidate station pool across the lineup's
    #: associated `sdLineupIds` (see
    #: `services.suggestions.generate_suggestions`'s docstring for how
    #: duplicates across multiple SD lineups are resolved).
    stationPoolSize: int
    #: Number of channels in the lineup that suggestions were (re)computed
    #: for. Currently always every channel in the lineup (see
    #: `generate_suggestions`'s docstring for why channels with
    #: `sdStationId` already set aren't excluded).
    channelsScored: int
    channelSuggestionCounts: list[ChannelSuggestionCount] = Field(default_factory=list)


class ConfirmedSuggestion(BaseModel):
    """One channel that `bulk_accept_suggestions` auto-confirmed."""

    channelId: str
    sdStationId: str
    sdLineupId: str
    score: float


class BulkAcceptResult(BaseModel):
    """Outcome of one `bulk_accept_suggestions` run for a single epg-editor lineup."""

    lineupId: str
    #: The fixed backend threshold actually applied (see
    #: `services.suggestions.BULK_ACCEPT_THRESHOLD`) — surfaced here so the
    #: frontend can display it without hardcoding its own copy of the value.
    threshold: float
    confirmedCount: int
    confirmed: list[ConfirmedSuggestion] = Field(default_factory=list)
