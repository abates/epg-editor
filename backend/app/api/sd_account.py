"""`/api/sd-account/lineups` and `/api/sd-account/limit`.

CRUD against the user's *SchedulesDirect account* lineups (SD's own
headend subscriptions) — entirely distinct from
`api/lineups.py`'s `PUT /lineups/{lineup_id}/sd-lineups`, which just
updates which SD lineup ID *strings* one of epg-editor's own lineups
references locally. Nothing here touches `config/lineups.json`.

Thin HTTP layer only: resolves a `SdClient` (reusing `app.api.sync`'s
`get_sd_client` dependency, same real-or-mocked construction pattern used
by every other SD-backed router) and delegates everything else to
`app.services.sd_account`, per CLAUDE.md's module layering.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from app.api.sync import get_sd_client
from app.models.sd import SdAddRemoveLineupResponse, SdLineupSummary
from app.models.sd_account import (
    LINEUP_ID_PATTERN,
    AddSdAccountLineupRequest,
    SdAccountLineupLimit,
)
from app.sd_client.client import SdClient, SdClientError
from app.services import sd_account as sd_account_service

router = APIRouter(prefix="/sd-account", tags=["sd-account"])


@router.get("/lineups", response_model=list[SdLineupSummary])
async def list_sd_account_lineups(
    sd_client: SdClient = Depends(get_sd_client),
) -> list[SdLineupSummary]:
    """List the lineups currently subscribed on the user's real SD account.

    503 if `SD_USERNAME`/`SD_PASSWORD` aren't configured (via
    `get_sd_client`); 502 if SD itself rejects the request (bad/expired
    token, SD-side error) — mirrors every other SD-backed route's error
    handling (see `api/sync.py`).
    """
    try:
        return await sd_account_service.list_account_lineups(sd_client)
    except SdClientError as exc:
        raise HTTPException(
            status_code=502, detail=f"SchedulesDirect request failed: {exc}"
        ) from exc


@router.post("/lineups", response_model=SdAddRemoveLineupResponse)
async def add_sd_account_lineup(
    body: AddSdAccountLineupRequest, sd_client: SdClient = Depends(get_sd_client)
) -> SdAddRemoveLineupResponse:
    """Subscribe the account to `body.lineupId`.

    This consumes one of the account's limited lineup slots and one of its
    "changes remaining" allowance (see the response's `changesRemaining`
    field) — this is a real mutation against the user's SD account, not a
    local-only change. 502 on an SD-side rejection (e.g. the lineup id
    doesn't exist, or the account is already at its lineup limit).
    """
    try:
        return await sd_account_service.add_account_lineup(sd_client, body.lineupId)
    except SdClientError as exc:
        raise HTTPException(
            status_code=502, detail=f"SchedulesDirect request failed: {exc}"
        ) from exc


@router.delete("/lineups/{lineup_id}", response_model=SdAddRemoveLineupResponse)
async def remove_sd_account_lineup(
    lineup_id: Annotated[str, Path(min_length=1, pattern=LINEUP_ID_PATTERN)],
    sd_client: SdClient = Depends(get_sd_client),
) -> SdAddRemoveLineupResponse:
    """Unsubscribe the account from `lineup_id`.

    Also a real mutation against the user's SD account. 502 on an SD-side
    rejection (e.g. the account isn't subscribed to that lineup).
    """
    try:
        return await sd_account_service.remove_account_lineup(sd_client, lineup_id)
    except SdClientError as exc:
        raise HTTPException(
            status_code=502, detail=f"SchedulesDirect request failed: {exc}"
        ) from exc


@router.get("/limit", response_model=SdAccountLineupLimit)
async def get_sd_account_lineup_limit(
    sd_client: SdClient = Depends(get_sd_client),
) -> SdAccountLineupLimit:
    """How many of the account's lineup slots are used vs. the total allowed.

    Lets the frontend show "N of M lineup slots used" proactively (per
    CLAUDE.md's Core workflow 2) before the user attempts to add a lineup,
    rather than only discovering the limit from a failed
    `POST /api/sd-account/lineups` call. See
    `app.services.sd_account.get_account_lineup_limit`'s docstring for
    exactly where `maxLineups` comes from.
    """
    try:
        return await sd_account_service.get_account_lineup_limit(sd_client)
    except SdClientError as exc:
        raise HTTPException(
            status_code=502, detail=f"SchedulesDirect request failed: {exc}"
        ) from exc
