"""Business logic for the user's SchedulesDirect *account* lineups.

These are SD's own headend subscriptions (SD calls them "lineups" too) —
distinct from epg-editor's own lineups in `services/lineups.py`/
`models/lineup.py`. Entirely a pass-through to `sd_client/`: nothing here
touches `storage/` or `config/lineups.json` at all, since these calls read
and write SD's account state directly, not any of epg-editor's own
persisted state.

Kept in `services/` (rather than called directly from `api/sd_account.py`)
to preserve CLAUDE.md's one-directional module layering
(`api/` -> `services/` -> `sd_client/`), the same pattern already
established by `services/refresh.py` and `services/suggestions.py` — even
though each function here is a thin, mostly line-for-line wrapper around a
single `SdClient` call.
"""

from __future__ import annotations

from app.models.sd import SdAddRemoveLineupResponse, SdLineupSummary
from app.models.sd_account import SdAccountLineupLimit
from app.sd_client.client import SdClient


async def list_account_lineups(sd_client: SdClient) -> list[SdLineupSummary]:
    """The account's currently-subscribed SD lineups."""
    result = await sd_client.list_account_lineups()
    return result.lineups


async def add_account_lineup(sd_client: SdClient, lineup_id: str) -> SdAddRemoveLineupResponse:
    """Subscribe the account to `lineup_id`.

    `lineup_id` is an SD lineup identifier (e.g. a postal-code-derived
    headend id like `USA-IL57303-X`) — see
    `models.sd_account.AddSdAccountLineupRequest`'s docstring for how a
    caller is expected to have obtained it.
    """
    return await sd_client.add_account_lineup(lineup_id)


async def remove_account_lineup(
    sd_client: SdClient, lineup_id: str
) -> SdAddRemoveLineupResponse:
    """Unsubscribe the account from `lineup_id`."""
    return await sd_client.remove_account_lineup(lineup_id)


async def get_account_lineup_limit(sd_client: SdClient) -> SdAccountLineupLimit:
    """How many of the account's lineup slots are used vs. the total allowed.

    Sourced entirely from one `GET /status` call
    (`SdClient.get_account_status`): `account.maxLineups` is the account-
    wide slot limit, and that same response's `lineups` array is used to
    count current usage — rather than issuing a second `GET /lineups` call
    just to count them, which would cost an extra SD request for no new
    information (see docs/schedulesdirect-integration.md's caching/rate-
    limit guidance).

    `lineupsUsed` counts *every* entry in `lineups`, including ones SD has
    flagged `isDeleted`. This was checked against SD's own published docs
    during review: they only say a client should "notify the user that
    their lineup may no longer be valid" when `isDeleted` is true — nothing
    about a deleted-on-SD's-side lineup freeing up a slot. Since this
    number exists specifically so the UI can proactively warn "you're at
    your limit" instead of the user discovering it from a failed add,
    undercounting is the worse failure mode than overcounting: the
    conservative assumption (every entry still occupies a slot until proven
    otherwise) is used here instead. `deletedLineupCount` is returned
    alongside it so the frontend can still surface which entries are
    deleted without that information being silently dropped from the
    response.
    """
    status = await sd_client.get_account_status()
    max_lineups = status.account.maxLineups if status.account is not None else None
    lineups_used = len(status.lineups)
    deleted_lineup_count = sum(1 for lineup in status.lineups if lineup.isDeleted)
    return SdAccountLineupLimit(
        maxLineups=max_lineups,
        lineupsUsed=lineups_used,
        deletedLineupCount=deleted_lineup_count,
    )
