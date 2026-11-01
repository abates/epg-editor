"""Pydantic models for the global scheduled/manual refresh pipeline.

See `services/refresh.py` (the business logic that produces a
`RefreshResult`), `scheduler/jobs.py` (the APScheduler job that runs it on a
timer), and `api/refresh.py` (the `POST /api/refresh-now` route that runs it
on demand and returns one as its response body).

`RefreshResult` has no predecessor to unify with: the earlier per-lineup
`sync-and-generate` trigger (`models/sync.py`'s `SyncResult`, a Phase 1
stopgap) was removed once this global pipeline superseded it — see
docs/backlog.md item 29.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: What a `RefreshError` is scoped to — lets a caller/UI group errors
#: sensibly without needing to parse free-text messages.
RefreshErrorScope = Literal["account", "sd_lineup", "lineup", "station", "programs"]


class RefreshError(BaseModel):
    """One failure recorded during a `refresh_all_lineups` run.

    Collected here rather than raised so one bad SD lineup, epg-editor
    lineup, or station doesn't abort the whole run — see
    `services.refresh.refresh_all_lineups`'s docstring. `id` is the
    relevant SD lineup id / epg-editor lineup id / SD station id for
    `scope`s that have one; `None` for `scope="account"` (nothing more
    specific than "the whole run") and `scope="programs"` (the batched
    program-metadata fetch isn't tied to one station).
    """

    scope: RefreshErrorScope
    id: str | None = None
    message: str


class RefreshResult(BaseModel):
    """Outcome of one `refresh_all_lineups` run across every epg-editor lineup.

    Produced identically by the scheduled job and the manual `POST
    /api/refresh-now` trigger — both call the same `services.refresh
    .refresh_all_lineups` function, per docs/backlog.md items 29-30.
    """

    lineupsProcessed: int = 0
    lineupsRegenerated: int = 0
    stationRostersRefreshed: int = 0
    stationRostersSkipped: int = 0
    scheduleDaysChecked: int = 0
    scheduleDaysRefetched: int = 0
    scheduleDaysSkippedUnchanged: int = 0
    programsFetched: int = 0
    errors: list[RefreshError] = Field(default_factory=list)
