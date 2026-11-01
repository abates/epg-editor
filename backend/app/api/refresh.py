"""`POST /api/refresh-now` — manual trigger for the global refresh pipeline.

Deliberately not nested under `/lineups/{lineup_id}`: this runs
`services.refresh.refresh_all_lineups` across *every* epg-editor lineup,
the exact same function the APScheduler job in `scheduler/jobs.py` runs on
a timer. Triggering this does not touch the scheduled job's timer/schedule
in any way — it's an independent, on-demand run of the same pipeline, not
a "reset the clock" action.

Thin HTTP layer only: resolves a `SdClient` (reusing
`app.api.dependencies`'s `get_sd_client` dependency, same real-or-mocked
construction pattern used by every other SD-calling route in this project)
and delegates everything else to `app.services.refresh`, per CLAUDE.md's
module layering.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_sd_client
from app.models.refresh import RefreshResult
from app.sd_client.client import SdClient, SdClientError
from app.services import refresh as refresh_service

router = APIRouter(tags=["refresh"])


@router.post("/refresh-now", response_model=RefreshResult)
async def refresh_now(sd_client: SdClient = Depends(get_sd_client)) -> RefreshResult:
    """Run the global SD refresh + XMLTV regeneration pipeline immediately.

    Covers every epg-editor lineup (not just one) and uses the md5-based
    "skip unchanged schedules" optimization — see
    `app.services.refresh.refresh_all_lineups`. Missing SD credentials
    surface as a clean 503 (via `get_sd_client`); an auth/account-level SD
    failure (e.g. a rejected token) surfaces as a clean 502. Any other
    per-SD-lineup/per-station/per-lineup failure is instead collected into
    the 200 response body's `errors` list and the run still completes for
    everything else.
    """
    try:
        return await refresh_service.refresh_all_lineups(sd_client)
    except SdClientError as exc:
        raise HTTPException(
            status_code=502, detail=f"SchedulesDirect request failed: {exc}"
        ) from exc
