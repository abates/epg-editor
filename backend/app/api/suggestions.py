"""`/api/lineups/{lineup_id}/suggestions` and
`/api/lineups/{lineup_id}/bulk-accept-suggestions`.

Thin HTTP layer only: resolves a `SdClient` (reusing
`app.api.dependencies`'s `get_sd_client` dependency, same real-or-mocked
construction pattern) and delegates everything else to
`app.services.suggestions`, per CLAUDE.md's module layering.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_sd_client
from app.models.suggestions import BulkAcceptResult, SuggestionResult
from app.sd_client.client import SdClient, SdClientError
from app.services import suggestions as suggestions_service
from app.services.lineups import NotFoundError

router = APIRouter(tags=["suggestions"])


@router.post("/lineups/{lineup_id}/suggestions", response_model=SuggestionResult)
async def generate_suggestions(
    lineup_id: str, sd_client: SdClient = Depends(get_sd_client)
) -> SuggestionResult:
    """(Re)compute mapping suggestions for every channel in a lineup.

    Fetches (and caches) the station roster for each of the lineup's
    associated `sdLineupIds` on a cache miss, unions them into one
    candidate pool, and scores every channel against it — see
    `app.services.suggestions.generate_suggestions`. 404 if the lineup
    doesn't exist; a SD-level failure (auth, transport, malformed
    response) fetching a station roster is surfaced as a clean 502 rather
    than a raw 500.
    """
    try:
        return await suggestions_service.generate_suggestions(lineup_id, sd_client)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SdClientError as exc:
        raise HTTPException(
            status_code=502, detail=f"SchedulesDirect request failed: {exc}"
        ) from exc


@router.post(
    "/lineups/{lineup_id}/bulk-accept-suggestions", response_model=BulkAcceptResult
)
def bulk_accept_suggestions(lineup_id: str) -> BulkAcceptResult:
    """Confirm every unconfirmed channel whose top suggestion clears the
    fixed backend bulk-accept threshold.

    No request body: the threshold
    (`app.services.suggestions.BULK_ACCEPT_THRESHOLD`) is a fixed backend
    constant, not a UI-adjustable setting, per CLAUDE.md. Synchronous (no
    `SdClient` needed) — this only reads/writes already-computed
    suggestions in `config/lineups.json`, no SD call involved. 404 if the
    lineup doesn't exist.
    """
    try:
        return suggestions_service.bulk_accept_suggestions(lineup_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
