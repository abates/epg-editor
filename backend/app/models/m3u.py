"""Pydantic models for M3U playlist parsing and import.

See `app.services.m3u` for the parsing/merge logic that produces these, and
`app.api.m3u` for the HTTP routes that return `M3UImportResult` in their
response body.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.models.lineup import Channel


class M3UEntry(BaseModel):
    """One parsed `#EXTINF` + stream-URL pair from an M3U playlist.

    M3U attribute -> field mapping:

    - `tvg-id` -> `tvgId`, falling back to `channel-id` when `tvg-id` is
      absent (an alternate attribute name seen on real-world HDHomeRun
      firmware output that omits `tvg-id` entirely — see
      `app.services.m3u.parse_m3u`'s docstring for the precedence rule)
    - `tvg-name` attribute if present, else the free-text display name
      after the comma, else `tvgId`, else a positional placeholder -> `name`
      (see `app.services.m3u.parse_m3u`'s docstring for why `tvg-name` is
      preferred over the display-name text when both are present)
    - `tvg-logo` -> `logoUrl`
    - `tvg-chno` -> `number`, falling back to `channel-number` when
      `tvg-chno` is absent (same real-world rationale as `channel-id` above)
    - `group-title` -> `groupTitle`
    - the stream URL line itself -> `streamUrl`

    Not persisted directly — `app.services.m3u`'s merge logic turns these
    into (or merges them onto) `app.models.lineup.Channel` instances.
    """

    tvgId: str | None = None
    name: str
    logoUrl: str | None = None
    number: str | None = None
    groupTitle: str | None = None
    streamUrl: str


class M3UImportResult(BaseModel):
    """Outcome of merging parsed `M3UEntry` objects into an epg-editor lineup.

    - `added`: channels newly created because no existing channel matched
      their incoming entry (by `tvgId`, fallback `number`).
    - `updated`: existing channels whose metadata was refreshed in place
      from a matching incoming entry (their `mapping` is left untouched).
    - `flaggedMissing`: channels present in the lineup before this import
      that no incoming entry matched this run — never deleted automatically,
      only flagged via `Channel.missingSince` (set on first disappearance,
      left unchanged on every subsequent import where they're still
      missing). Includes channels flagged missing by a *previous* import
      that are still missing now, not just newly-flagged ones.
    - `unidentifiedEntryCount`: how many parsed entries in *this* import had
      neither `tvgId` nor `number` set — i.e. entries with no stable
      identity signal to match against existing channels on a future
      re-import (see `app.services.m3u._merge_entries`'s module-level
      `INV-*` docs). This is a known, accepted limitation, not a bug: such
      an entry is always treated as brand-new on every import/re-import,
      which can both grow the lineup by a duplicate channel per re-import
      and flag a previously-matched channel as missing as a side effect.
      Reported as a plain count (not the entries themselves) — this is
      descriptive of "what's in this file" on every import, not a one-time
      alert, and a count is enough for the UI to warn the user without
      growing the response body for large playlists; `0` is the normal,
      expected value whenever every entry carries at least one identifier
      (e.g. HDHomeRun exports, which always assign a channel number).
    """

    added: list[Channel]
    updated: list[Channel]
    flaggedMissing: list[Channel]
    unidentifiedEntryCount: int = 0
