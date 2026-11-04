"""Business logic for epg-editor's own lineups/channels/mappings.

Called by thin FastAPI routers in `app.api.lineups`; persists via
`app.storage.lineups`. No direct filesystem or SD-client access here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.models.lineup import (
    Channel,
    ChannelMapping,
    Lineup,
    LineupSource,
    LineupsFile,
)
from app.storage.lineups import load_lineups, update_lineups


class NotFoundError(Exception):
    """Raised when a requested lineup or channel doesn't exist."""


class ValidationError(Exception):
    """Raised when a requested mutation would violate a data-integrity rule."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _find_lineup(data: LineupsFile, lineup_id: str) -> Lineup:
    for lineup in data.lineups:
        if lineup.id == lineup_id:
            return lineup
    raise NotFoundError(f"lineup {lineup_id!r} not found")


def _find_channel(lineup: Lineup, channel_id: str) -> Channel:
    for channel in lineup.channels:
        if channel.id == channel_id:
            return channel
    raise NotFoundError(f"channel {channel_id!r} not found in lineup {lineup.id!r}")


def list_lineups() -> list[Lineup]:
    """Return every epg-editor lineup."""
    return load_lineups().lineups


def get_lineup(lineup_id: str) -> Lineup:
    """Return one lineup by id, or raise `NotFoundError`."""
    return _find_lineup(load_lineups(), lineup_id)


def create_lineup(name: str) -> Lineup:
    """Create a new, empty, manually-sourced lineup."""
    now = _now()
    lineup = Lineup(
        id=_new_id(),
        name=name,
        source=LineupSource.MANUAL,
        createdAt=now,
        updatedAt=now,
        sdLineupIds=[],
        channels=[],
    )

    def mutate(data: LineupsFile) -> None:
        data.lineups.append(lineup)

    update_lineups(mutate)
    return lineup


def delete_lineup(lineup_id: str) -> None:
    """Remove an entire lineup (and all its channels/mappings) from
    `config/lineups.json`.

    Raises `NotFoundError` if `lineup_id` doesn't exist, consistent with
    every other mutator here. Scope is intentionally minimal: this only
    removes the lineup's entry from `config/lineups.json`. It does *not*
    delete the lineup's generated XMLTV output file (`output/<lineup-id>.xml`)
    or any SchedulesDirect cache entries — both are regenerable/rebuildable
    from `config/` + SD per CLAUDE.md's persistent-data-layout notes, so
    leaving a stale output file behind is harmless (it's simply never
    regenerated again, and can be cleaned up by the next full cache/output
    rebuild) rather than something this call needs to clean up itself.
    """

    def mutate(data: LineupsFile) -> None:
        lineup = _find_lineup(data, lineup_id)
        data.lineups.remove(lineup)

    update_lineups(mutate)


def update_lineup_sd_lineup_ids(lineup_id: str, sd_lineup_ids: list[str]) -> Lineup:
    """Replace a lineup's associated SD lineup IDs wholesale.

    Rejects dropping an SD lineup ID that a channel's mapping still points
    at (`mapping.sdLineupId` set — see docs/backlog.md item 38; there is no
    separate gating boolean). Without this check, removing a `sdLineupId`
    out from under a mapped channel would silently orphan that mapping —
    the station would no longer be in any SD lineup this epg-editor lineup
    actually draws from, yet `services/xmltv.py` would still happily emit
    it (see Phase 1 review finding #4). We chose to *reject* the update
    (400, listing the affected channels) rather than auto-clearing those
    channels' mappings: a set mapping represents explicit user intent, and
    silently clearing it as a side effect of an unrelated edit (editing the
    lineup's SD associations) seemed more surprising than asking the user
    to deal with the affected channels first (remap them or accept the
    removal explicitly).

    Note (item 38): gating on `sdLineupId` presence instead of the old
    `confirmed` boolean is itself a latent-bug fix, not just a rename — the
    old guard didn't protect a channel stuck in the "has a station,
    unconfirmed" bug state (the exact state item 37's UAT surfaced) from
    having its `sdLineupId` silently orphaned, which is exactly what this
    guard exists to prevent.
    """
    new_ids = set(sd_lineup_ids)

    def mutate(data: LineupsFile) -> Lineup:
        lineup = _find_lineup(data, lineup_id)
        removed_ids = set(lineup.sdLineupIds) - new_ids
        if removed_ids:
            affected = [
                channel
                for channel in lineup.channels
                if channel.mapping is not None
                and channel.mapping.sdLineupId is not None
                and channel.mapping.sdLineupId in removed_ids
            ]
            if affected:
                affected_desc = ", ".join(
                    f"{channel.name!r} ({channel.id})" for channel in affected
                )
                raise ValidationError(
                    f"cannot remove sdLineupId(s) {sorted(removed_ids)!r} from "
                    f"lineup {lineup_id!r}: channels have mappings pointing at "
                    f"them: {affected_desc}"
                )
        lineup.sdLineupIds = list(sd_lineup_ids)
        lineup.updatedAt = _now()
        return lineup

    return update_lineups(mutate)


def add_channel(
    lineup_id: str,
    *,
    name: str,
    number: str | None = None,
    logo_url: str | None = None,
    tvg_id: str | None = None,
    source_stream_url: str | None = None,
) -> Channel:
    """Manually add a channel to a lineup.

    Validated through `Channel` itself (e.g. `name` must be non-empty after
    trimming whitespace — see `models.lineup.NonEmptyName`), same as
    `update_channel`'s re-validation path, so a bad `name` is rejected with
    `ValidationError` (-> 400 at the API layer) instead of letting a raw
    `pydantic.ValidationError` escape uncaught (-> 500).
    """
    try:
        channel = Channel(
            id=_new_id(),
            number=number,
            name=name,
            logoUrl=logo_url,
            tvgId=tvg_id,
            sourceStreamUrl=source_stream_url,
        )
    except PydanticValidationError as exc:
        raise ValidationError(
            f"invalid channel for lineup {lineup_id!r}: {exc}"
        ) from exc

    def mutate(data: LineupsFile) -> None:
        lineup = _find_lineup(data, lineup_id)
        lineup.channels.append(channel)
        lineup.updatedAt = _now()

    update_lineups(mutate)
    return channel


#: `UpdateChannelRequest` field names that map 1:1 onto `Channel` attributes.
_CHANNEL_UPDATABLE_FIELDS = frozenset(
    {"name", "number", "logoUrl", "tvgId", "sourceStreamUrl"}
)


def update_channel(lineup_id: str, channel_id: str, fields: dict[str, Any]) -> Channel:
    """Edit a channel's metadata in place.

    `fields` must only contain keys the caller explicitly set in the
    request (e.g. via Pydantic's `model_dump(exclude_unset=True)`), *not*
    just every non-`None` field — otherwise an explicit `null` meant to
    clear a field (e.g. `logoUrl: null`) is indistinguishable from the
    field being omitted entirely, and clearing silently does nothing (see
    Phase 1 review finding #3). A key present in `fields` is applied
    verbatim, including when its value is `None`.

    The merged result is re-validated through `Channel` *before* anything
    is written back to `lineup.channels`/disk. Applying `fields` via raw
    `setattr` with no re-validation let an explicit `null` for a required
    field (e.g. `name`) land directly on the in-memory `Channel` and then
    get persisted as-is, corrupting `config/lineups.json` (every later
    `load_lineups()` call then raised `ValidationError` trying to parse it
    back — see the HIGH-severity regression review finding). Re-validating
    via `Channel.model_validate` here means an invalid combination raises
    *before* `update_lineups`'s `save_lineups` call, so the mutation fails
    cleanly instead of writing anything.
    """
    unknown = set(fields) - _CHANNEL_UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"not updatable channel field(s): {sorted(unknown)!r}")

    def mutate(data: LineupsFile) -> Channel:
        lineup = _find_lineup(data, lineup_id)
        channel = _find_channel(lineup, channel_id)
        merged = {**channel.model_dump(), **fields}
        try:
            updated = Channel.model_validate(merged)
        except PydanticValidationError as exc:
            raise ValidationError(
                f"invalid update for channel {channel_id!r} in lineup "
                f"{lineup_id!r}: {exc}"
            ) from exc
        lineup.channels[lineup.channels.index(channel)] = updated
        lineup.updatedAt = _now()
        return updated

    return update_lineups(mutate)


def remove_channel(lineup_id: str, channel_id: str) -> None:
    """Remove a channel from a lineup."""

    def mutate(data: LineupsFile) -> None:
        lineup = _find_lineup(data, lineup_id)
        channel = _find_channel(lineup, channel_id)
        lineup.channels.remove(channel)
        lineup.updatedAt = _now()

    update_lineups(mutate)


def set_channel_mapping(
    lineup_id: str,
    channel_id: str,
    *,
    sd_station_id: str,
    sd_lineup_id: str,
) -> Channel:
    """Directly set a channel's SD station mapping (no suggestion scoring).

    Rejects a `sd_lineup_id` that isn't one of the lineup's associated
    `sdLineupIds` — a mapping pointing at an unassociated SD lineup would be
    a silent data-integrity bug (the station wouldn't be in any cached
    roster this lineup actually draws from).

    Setting `sdStationId` always means mapped, full stop (see
    docs/backlog.md item 38) — `mappedAt` is set unconditionally to the
    current time whenever this is called.
    """

    def mutate(data: LineupsFile) -> Channel:
        lineup = _find_lineup(data, lineup_id)
        channel = _find_channel(lineup, channel_id)

        if sd_lineup_id not in lineup.sdLineupIds:
            raise ValidationError(
                f"sdLineupId {sd_lineup_id!r} is not associated with lineup "
                f"{lineup_id!r} (associated: {lineup.sdLineupIds!r})"
            )

        now = _now()
        channel.mapping = ChannelMapping(
            sdStationId=sd_station_id,
            sdLineupId=sd_lineup_id,
            mappedAt=now,
            suggestions=channel.mapping.suggestions if channel.mapping else [],
        )
        lineup.updatedAt = now
        return channel

    return update_lineups(mutate)
