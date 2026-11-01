"""Lineup/channel/mapping routers under `/api/lineups`.

Thin HTTP layer: validates request/response bodies via Pydantic and
delegates every mutation/query to `app.services.lineups`. No business logic
or storage access here (see CLAUDE.md's backend module layout).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.lineup import Channel, Lineup
from app.services import lineups as lineups_service

router = APIRouter(tags=["lineups"])


# --- Request bodies -----------------------------------------------------------
# These are HTTP-layer DTOs specific to these routes (not epg-editor domain
# objects, which live in `app.models.lineup`), so they're defined here
# rather than in `app.models`.


class CreateLineupRequest(BaseModel):
    name: str


class UpdateSdLineupIdsRequest(BaseModel):
    sdLineupIds: list[str] = Field(default_factory=list)


class AddChannelRequest(BaseModel):
    name: str
    number: str | None = None
    logoUrl: str | None = None
    tvgId: str | None = None
    sourceStreamUrl: str | None = None


class UpdateChannelRequest(BaseModel):
    name: str | None = None
    number: str | None = None
    logoUrl: str | None = None
    tvgId: str | None = None
    sourceStreamUrl: str | None = None


class SetChannelMappingRequest(BaseModel):
    sdStationId: str
    sdLineupId: str
    confirmed: bool = True


# --- Routes --------------------------------------------------------------------


@router.get("/lineups", response_model=list[Lineup])
def list_lineups() -> list[Lineup]:
    """List every epg-editor lineup."""
    return lineups_service.list_lineups()


@router.post("/lineups", response_model=Lineup, status_code=201)
def create_lineup(body: CreateLineupRequest) -> Lineup:
    """Create a new, empty, manually-sourced lineup."""
    return lineups_service.create_lineup(name=body.name)


@router.get("/lineups/{lineup_id}", response_model=Lineup)
def get_lineup(lineup_id: str) -> Lineup:
    """Fetch a single lineup by id."""
    try:
        return lineups_service.get_lineup(lineup_id)
    except lineups_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/lineups/{lineup_id}", status_code=204)
def delete_lineup(lineup_id: str) -> None:
    """Delete an entire lineup, including all its channels and mappings.

    Only removes the lineup from `config/lineups.json` — any previously
    generated `/xmltv/{lineup_id}.xml` output file or SD cache entries are
    left in place (both are regenerable, see
    `services.lineups.delete_lineup`'s docstring) rather than being cleaned
    up as a side effect of this call.
    """
    try:
        lineups_service.delete_lineup(lineup_id)
    except lineups_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/lineups/{lineup_id}/sd-lineups", response_model=Lineup)
def update_sd_lineup_ids(lineup_id: str, body: UpdateSdLineupIdsRequest) -> Lineup:
    """Replace a lineup's associated SchedulesDirect lineup IDs.

    Rejects (400) removing a SD lineup ID that a channel's confirmed
    mapping still depends on (see `services.lineups.update_lineup_sd_lineup_ids`).
    """
    try:
        return lineups_service.update_lineup_sd_lineup_ids(lineup_id, body.sdLineupIds)
    except lineups_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except lineups_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lineups/{lineup_id}/channels", response_model=Channel, status_code=201)
def add_channel(lineup_id: str, body: AddChannelRequest) -> Channel:
    """Manually add a channel to a lineup."""
    try:
        return lineups_service.add_channel(
            lineup_id,
            name=body.name,
            number=body.number,
            logo_url=body.logoUrl,
            tvg_id=body.tvgId,
            source_stream_url=body.sourceStreamUrl,
        )
    except lineups_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except lineups_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/lineups/{lineup_id}/channels/{channel_id}", response_model=Channel)
def update_channel(
    lineup_id: str, channel_id: str, body: UpdateChannelRequest
) -> Channel:
    """Edit a channel's metadata in place.

    Only fields explicitly present in the request body are changed —
    `model_dump(exclude_unset=True)` distinguishes "field omitted" (leave
    unchanged) from "field explicitly sent as `null`" (clear it), so e.g.
    `{"logoUrl": null}` actually clears `logoUrl` instead of being a no-op
    (see Phase 1 review finding #3). Sending `null` for a field that's
    required/non-nullable on `Channel` (e.g. `name`) is rejected with 400
    rather than being persisted (see regression review finding).
    """
    try:
        return lineups_service.update_channel(
            lineup_id,
            channel_id,
            body.model_dump(exclude_unset=True),
        )
    except lineups_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except lineups_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/lineups/{lineup_id}/channels/{channel_id}", status_code=204)
def remove_channel(lineup_id: str, channel_id: str) -> None:
    """Remove a channel from a lineup."""
    try:
        lineups_service.remove_channel(lineup_id, channel_id)
    except lineups_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/lineups/{lineup_id}/channels/{channel_id}/mapping", response_model=Channel)
def set_channel_mapping(
    lineup_id: str, channel_id: str, body: SetChannelMappingRequest
) -> Channel:
    """Directly confirm (or set) a channel's SD station mapping.

    Rejects a `sdLineupId` that isn't one of the lineup's associated SD
    lineups (see `services.lineups.set_channel_mapping`).
    """
    try:
        return lineups_service.set_channel_mapping(
            lineup_id,
            channel_id,
            sd_station_id=body.sdStationId,
            sd_lineup_id=body.sdLineupId,
            confirmed=body.confirmed,
        )
    except lineups_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except lineups_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
