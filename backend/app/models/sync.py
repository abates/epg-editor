"""Pydantic models for the manual SD sync + XMLTV generation trigger.

See `services/sync.py` (the business logic that produces a `SyncResult`)
and `api/sync.py` (the `POST /api/lineups/{lineup_id}/sync-and-generate`
route that returns one as its response body).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StationSyncError(BaseModel):
    """One station's schedule fetch that failed during a sync run.

    Collected here rather than raised so one bad station (e.g. an
    invalid/removed SD station id) doesn't abort the whole lineup's sync —
    see `services.sync.sync_and_generate`.
    """

    sdStationId: str
    message: str


class SyncResult(BaseModel):
    """Outcome of one `sync_and_generate` run for a single epg-editor lineup."""

    lineupId: str
    stationsSynced: int = 0
    scheduleDaysFetched: int = 0
    programsFetched: int = 0
    channelsGenerated: int = 0
    stationErrors: list[StationSyncError] = Field(default_factory=list)
    #: Failures not tied to one specific station (currently: the batched
    #: `get_programs` call). Also collected rather than aborting the sync —
    #: generation still proceeds with whatever data *did* get cached.
    errors: list[str] = Field(default_factory=list)
