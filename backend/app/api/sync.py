"""`POST /api/lineups/{lineup_id}/sync-and-generate`.

A manual, on-demand trigger pulled forward into Phase 1 (see
`app.services.sync` for why) so a lineup's confirmed channel mappings can
actually be exercised against a real SchedulesDirect account before the
Phase 5 scheduler exists. Thin HTTP layer only: constructs/resolves a
`SdClient` and delegates everything else to `app.services.sync`, per
CLAUDE.md's module layering.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException

from app.models.sync import SyncResult
from app.sd_client.client import SdClient, SdClientError, SdCredentialsNotConfiguredError
from app.services import sync as sync_service
from app.services.lineups import NotFoundError

router = APIRouter(tags=["sync"])


async def get_sd_client() -> AsyncIterator[SdClient]:
    """FastAPI dependency: a real `SdClient` built from env-var credentials.

    `SdClient.from_env()` is the one and only place in the codebase that
    constructs a real `httpx.AsyncClient` (see its docstring) — this module
    deliberately never imports `httpx` itself, so there's exactly one place
    that owns the real-network timeout/transport configuration.

    A generator dependency (rather than a plain module-level call inside
    the route) so the real client is scoped per-request and explicitly
    closed afterward (`async with sd_client`, delegating to
    `SdClient.aclose()`) rather than leaked, and so tests can swap in a
    mock-transport-backed `SdClient` via
    `app.dependency_overrides[get_sd_client]` — per CLAUDE.md, no real SD
    credentials or network are ever touched in the test suite.

    Missing/empty `SD_USERNAME`/`SD_PASSWORD` raises
    `SdCredentialsNotConfiguredError` from `SdClient.from_env()`, mapped
    here to a clean 503 rather than letting it surface as a raw exception.
    """
    try:
        sd_client = SdClient.from_env()
    except SdCredentialsNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    async with sd_client:
        yield sd_client


@router.post("/lineups/{lineup_id}/sync-and-generate", response_model=SyncResult)
async def sync_and_generate(
    lineup_id: str, sd_client: SdClient = Depends(get_sd_client)
) -> SyncResult:
    """Fetch fresh SD schedule/program data for this lineup's confirmed-
    mapped stations only, cache it, and regenerate `/xmltv/{lineup_id}.xml`.

    Manual/on-demand only (see `app.services.sync`'s module docstring for
    why there's no scheduler wiring yet). A lineup with zero confirmed-
    mapped channels succeeds trivially (nothing to sync, an empty-but-valid
    XMLTV document is still (re)generated).
    """
    try:
        return await sync_service.sync_and_generate(lineup_id, sd_client)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SdClientError as exc:
        # Covers both an SD auth failure (bad credentials/token rejected)
        # and any other SD-level failure that isn't a per-station schedule
        # fetch (those are collected into the response body instead of
        # raised — see `services.sync.sync_and_generate`). Surfaced with
        # SD's own error text, not swallowed.
        raise HTTPException(
            status_code=502, detail=f"SchedulesDirect request failed: {exc}"
        ) from exc
