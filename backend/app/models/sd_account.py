"""Pydantic models for epg-editor's `/api/sd-account/*` routes.

These are the *API-boundary* shapes for managing the user's SchedulesDirect
account lineups (the SD-side headend subscriptions) — distinct from the raw
SD response shapes in `models/sd.py` (which `sd_client/` speaks) and from
epg-editor's own `Lineup`/`Channel` domain models in `models/lineup.py`. See
`services/sd_account.py` (the business logic) and `api/sd_account.py` (the
routes that use these).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

#: SD lineup IDs observed in SD's docs/API examples are tokens like
#: `USA-OTA12345`, `USA-IL57303-X`, `USA-WI61859-DEFAULT` — uppercase
#: country/region prefix, numeric headend/zip-derived segment, optional
#: `-X`/`-DEFAULT`-style suffix, always alphanumeric plus hyphens. This
#: constrains `lineupId` to that shape so a value containing `?`/`/`
#: (which could otherwise alter the request's target path/query when
#: interpolated via f-string in `sd_client/client.py`) is rejected with a
#: clean 422 before it ever reaches the SD client, rather than guessed at
#: more loosely.
LINEUP_ID_PATTERN = r"^[A-Za-z0-9-]+$"


class AddSdAccountLineupRequest(BaseModel):
    """Body for `POST /api/sd-account/lineups`.

    `lineupId` is an SD lineup identifier (e.g. `USA-IL57303-X`), normally
    obtained from SD's `GET /headends?country=...&postalcode=...` headend-
    lookup endpoint (see docs/schedulesdirect-integration.md). That
    postal-code lookup isn't wired up as its own epg-editor endpoint yet —
    out of scope for this change, see the handoff report that introduced
    this module — so for now a caller must already have a lineup id in
    hand (e.g. typed in manually, or looked up via SD's own site) to use
    this endpoint.
    """

    lineupId: Annotated[str, Field(min_length=1, pattern=LINEUP_ID_PATTERN)]


class SdAccountLineupLimit(BaseModel):
    """The account's lineup-slot usage.

    Surfaced so the frontend can proactively show "N of M lineup slots
    used" per CLAUDE.md's Core workflow 2 ("SD accounts have a limited
    number of lineup slots — surface that limit in the UI rather than
    discovering it via a failed API call"), rather than only finding out
    about the limit from a failed `POST /api/sd-account/lineups` call.

    Sourced from SD's `GET /status` (`account.maxLineups`) — see
    `services.sd_account.get_account_lineup_limit`. `maxLineups` is `None`
    if SD's response omits it (defensive; not expected in practice based
    on the documented shape).

    `lineupsUsed` counts *every* entry in `/status`'s `lineups` array,
    including ones SD has flagged `isDeleted` — see
    `get_account_lineup_limit`'s docstring for why (SD's docs only say a
    deleted entry "may no longer be valid," not that it has freed up an
    account slot; the conservative assumption is that it still counts).
    `deletedLineupCount` is surfaced separately so the frontend can still
    show/explain those entries without the count silently hiding them.
    """

    maxLineups: int | None
    lineupsUsed: int
    deletedLineupCount: int
