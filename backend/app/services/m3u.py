"""M3U playlist parsing and lineup-merge logic.

See CLAUDE.md's Core workflow 1 (M3U import/re-import) and
`docs/backlog.md` Phase 2 (items 15-16). Two independent pieces:

- `parse_m3u`: pure text -> `M3UEntry` parsing, no I/O, no knowledge of
  epg-editor's own lineups.
- `import_m3u_entries` / `create_lineup_from_m3u`: merge parsed entries into
  epg-editor's own `Lineup`/`Channel` state, persisted via
  `app.storage.lineups.update_lineups` — never a raw load/save pair, so a
  whole re-import (matching + updates + additions + missing-flagging) is
  one atomic load-mutate-save cycle, per CLAUDE.md's lost-update-race rule
  (see `storage/lineups.py`'s module docstring).

Depends only on `app.models` + `app.storage` (+ the exception types already
defined in `app.services.lineups`, reused rather than redefined) — no
filesystem or SD-client access of its own, per CLAUDE.md's module layering.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from app.models.lineup import Channel, Lineup, LineupSource, LineupsFile
from app.models.m3u import M3UEntry, M3UImportResult
from app.services.lineups import NotFoundError, ValidationError
from app.storage.lineups import update_lineups

#: Matches a double-quoted `key="value"` attribute anywhere in an
#: `#EXTINF` line's attribute section. Real-world M3U playlists (HDHomeRun,
#: most IPTV playlist generators) always quote `tvg-*`/`group-title`
#: attribute values, so this intentionally only recognizes the quoted
#: form — an attribute with no value, or with missing/mismatched quotes,
#: simply fails to match this regex and is dropped (treated as absent)
#: rather than raising, per the messiness this parser must tolerate.
_ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"')

_EXTM3U_HEADER = "#EXTM3U"
_EXTINF_PREFIX = "#EXTINF:"


class M3UParseError(Exception):
    """Raised when input text isn't parseable as an M3U playlist at all.

    Not raised for messiness *within* an otherwise-valid playlist (bad
    attributes, missing display names, etc. are tolerated/worked around —
    see `parse_m3u`'s docstring) — only for input that doesn't look like an
    M3U file in the first place (missing/garbled `#EXTM3U` header).
    """


def _split_attrs_and_display_name(content: str) -> tuple[str, str]:
    """Split an `#EXTINF:` line's content (with the `#EXTINF:` prefix
    already stripped) into its attribute section and display-name text.

    The two are separated by the first comma that isn't inside a quoted
    attribute value — found by scanning char by char (rather than a naive
    `content.split(",", 1)`) so a comma inside a quoted attribute value
    (e.g. `tvg-name="Channel, Two"`) doesn't prematurely end the attribute
    section and truncate the display name.
    """
    in_quotes = False
    for index, char in enumerate(content):
        if char == '"':
            in_quotes = not in_quotes
        elif char == "," and not in_quotes:
            return content[:index], content[index + 1 :].strip()
    # No top-level comma at all: no display name, the whole line is attrs.
    return content, ""


def _parse_extinf_attrs(attrs_section: str) -> dict[str, str]:
    """Extract `tvg-*`/`group-title` attributes from an `#EXTINF` line's
    attribute section (lower-cased keys). The leading duration token (e.g.
    `-1`) has no `=` in it, so it simply never matches `_ATTR_RE` — no need
    to explicitly strip it before scanning for attributes.
    """
    return {key.lower(): value for key, value in _ATTR_RE.findall(attrs_section)}


def parse_m3u(text: str) -> list[M3UEntry]:
    """Parse raw M3U playlist text into a list of `M3UEntry`.

    Tolerates the real-world messiness an M3U file in the wild can have:
    CRLF/LF/CR line endings (`str.splitlines()` handles all three
    uniformly), a leading UTF-8 BOM, blank lines, non-`#EXTINF`
    comment/directive lines interleaved between entries (e.g. `#EXTGRP`,
    `#EXTVLCOPT`), attributes in any order, attributes with no value or
    missing/mismatched quotes (that single attribute is dropped, not the
    whole line/file), an entry missing a display name, and duplicate
    `tvg-id`s across entries (returned as-is — de-duplication across
    entries pointing at the same logical channel is `import_m3u_entries`'s
    concern, not this function's; see its docstring).

    `tvgId`/`number` alternate attribute names: some real-world M3U
    exports (confirmed on at least one HDHomeRun firmware revision) omit
    `tvg-id`/`tvg-chno` entirely and instead emit `channel-id` and
    `channel-number` for the same information. Both are recognized as
    alternate sources for `M3UEntry.tvgId`/`M3UEntry.number` respectively.
    Precedence when an entry has *both* the standard and alternate
    attribute: `tvg-id` wins over `channel-id`, and `tvg-chno` wins over
    `channel-number` — the `tvg-*` names are the more established,
    first-class ones per the rest of this docstring (e.g. `tvg-name`'s
    precedence over the comma display-name below), so they're preferred
    whenever both happen to be present; the alternate is consulted only
    when the standard attribute is absent (missing, or present but empty —
    same "empty string treated as absent" rule as every other attribute
    here).

    Display-name precedence when both are present: the `tvg-name`
    attribute wins over the free-text display name following the comma.
    In practice (HDHomeRun and most IPTV playlist generators), `tvg-name`
    is the clean, EPG-oriented name meant for exactly this kind of
    matching, while the comma-text is meant for on-screen display in a
    player and sometimes carries extra formatting (a channel-number
    prefix, an emoji, etc.) that would hurt rather than help Phase 3's
    fuzzy station-matching against this same `name` field later. Falls
    back to the comma display-name, then `tvg-id`, then a positional
    placeholder (`"Channel {n}"`) if both are blank or whitespace-only —
    `Channel.name` requires a non-empty, non-whitespace-only value, so an
    entry returned from here can never surface a blank `name` downstream.

    An `#EXTINF` entry with no following stream-URL line (e.g. a truncated
    file, or two consecutive `#EXTINF` lines) is dropped silently — it has
    no `streamUrl` to populate `Channel.sourceStreamUrl` with. Likewise a
    stray URL-looking line with no preceding `#EXTINF` is skipped (nothing
    to attach it to).

    Raises `M3UParseError` if the text is empty/all-blank, or its first
    non-blank line doesn't start with `#EXTM3U` — i.e. it isn't M3U at all,
    as distinct from being merely messy M3U.
    """
    if not text:
        raise M3UParseError("M3U content is empty")

    # Strip a leading UTF-8 BOM (common from Windows-authored playlists/
    # editors), which would otherwise make the header check below fail.
    stripped_text = text.lstrip("﻿")
    lines = stripped_text.splitlines()

    first_content_index = next(
        (index for index, line in enumerate(lines) if line.strip()), None
    )
    if first_content_index is None or not lines[
        first_content_index
    ].strip().startswith(_EXTM3U_HEADER):
        raise M3UParseError(
            "not a valid M3U playlist: expected the first non-blank line to "
            "start with '#EXTM3U'"
        )

    entries: list[M3UEntry] = []
    pending_attrs: dict[str, str] | None = None
    pending_display_name: str | None = None
    entry_count = 0

    for line in lines[first_content_index + 1 :]:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        if stripped_line.startswith(_EXTINF_PREFIX):
            # A new #EXTINF line while one is already pending means the
            # previous one was never followed by a URL — it's simply
            # dropped by being overwritten here (see docstring).
            content = stripped_line[len(_EXTINF_PREFIX) :]
            attrs_section, display_name = _split_attrs_and_display_name(content)
            pending_attrs = _parse_extinf_attrs(attrs_section)
            pending_display_name = display_name
            continue

        if stripped_line.startswith("#"):
            # Any other directive/comment line — not a URL, doesn't change
            # pending state either way.
            continue

        # A non-comment, non-blank line: the stream URL for the pending
        # entry, if there is one.
        if pending_attrs is None:
            continue

        entry_count += 1
        # `channel-id`/`channel-number` are alternate attribute names seen
        # in the wild (confirmed on real HDHomeRun firmware output that
        # omits `tvg-id`/`tvg-chno` entirely) — see this function's
        # docstring for the precedence rule between the two spellings.
        tvg_id = pending_attrs.get("tvg-id") or pending_attrs.get("channel-id") or None
        raw_name = pending_attrs.get("tvg-name") or pending_display_name or tvg_id or ""
        name = raw_name.strip() or f"Channel {entry_count}"
        number = (
            pending_attrs.get("tvg-chno") or pending_attrs.get("channel-number") or None
        )
        entries.append(
            M3UEntry(
                tvgId=tvg_id,
                name=name,
                logoUrl=pending_attrs.get("tvg-logo") or None,
                number=number,
                groupTitle=pending_attrs.get("group-title") or None,
                streamUrl=stripped_line,
            )
        )
        pending_attrs = None
        pending_display_name = None

    return entries


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _find_lineup(data: LineupsFile, lineup_id: str) -> Lineup:
    for lineup in data.lineups:
        if lineup.id == lineup_id:
            return lineup
    raise NotFoundError(f"lineup {lineup_id!r} not found")


#: ---------------------------------------------------------------------
#: `_merge_entries` invariants
#: ---------------------------------------------------------------------
#: These are the contract `_merge_entries` is implemented against. Any
#: change to the matching algorithm must keep all of these true — they are
#: the thing property/regression tests below assert, not implementation
#: detail.
#:
#: - INV-IDENTITY: every pre-existing channel is referenced by its stable
#:   `id` throughout the merge, never by Pydantic value-equality on a
#:   mutable `Channel` object (e.g. never `list.index(some_channel)`).
#:   `Channel` instances are replaced wholesale on update (a fresh
#:   `model_validate` call), so two entries that both resolve to the same
#:   pre-existing channel must still both find it correctly — the first
#:   entry's write must not make the second entry's lookup fail. This is
#:   what closes the crash in finding 1 structurally: a lookup table keyed
#:   by `id` is built once, before any mutation, and never invalidated by
#:   later writes.
#:
#: - INV-TVGID-FIRST: an entry whose `tvgId` is non-null and equals a
#:   pre-existing channel's `tvgId` always resolves to that channel.
#:   Resolved globally across the whole file (pass 1, below) before any
#:   number-based matching is considered, regardless of file order.
#:
#: - INV-NO-HIJACK: once a pre-existing channel is resolved — by tvgId
#:   (pass 1) or by number fallback (pass 2) — no other entry, regardless
#:   of its own tvgId/number or its position in the file, can ever change
#:   that channel's identity, metadata, or mapping again within the same
#:   import. Structurally: pass 1 and pass 2 together produce a single
#:   `entry_target` mapping from entry -> pre-existing channel that is
#:   complete and final before the pass that actually writes anything
#:   runs; the final pass's own live de-dup indices (for brand-new
#:   channels, see INV-SYMMETRIC-NEW-CHANNEL-PROTECTION) are *only* ever
#:   seeded from channels created within that same final pass, never from
#:   `entry_target` results, so a later unrelated entry can never reach a
#:   pre-existing channel through that back door either.
#:
#: - INV-DETERMINISTIC-COMPETITION: when multiple entries could plausibly
#:   number-match the same unclaimed pre-existing channel(s), the
#:   competition is resolved by an explicit, content-based priority rule,
#:   not first-come-first-served: an entry with no `tvgId` at all is
#:   preferred over an entry whose `tvgId` is present but simply didn't
#:   match anything in pass 1 (reasoning: a tvgId-bearing-but-unmatched
#:   entry more likely describes a genuinely different channel that
#:   happens to reuse the number, while a tvgId-less entry carries no
#:   information contradicting "this is the same untracked channel, just
#:   refreshed"). This ranking is a function of entry content, so it is
#:   independent of file order whenever ranks differ. When >1 pre-existing
#:   channel shares the same number (itself only reachable via repeated
#:   re-imports that created a second channel at that number — see
#:   INV-IDEMPOTENT-REIMPORT), candidates are paired against those
#:   channels in rank order, channels taken in their existing, stable
#:   `lineup.channels` list order (itself unaffected by this import's
#:   entry order) — so *which* pre-existing channels get matched at all
#:   never depends on file order. The only residual, explicitly accepted
#:   ambiguity is *whose data wins* when two or more candidates tie on
#:   rank (e.g. two tvgId-less entries both competing for one number): the
#:   tie is broken by original position in the `entries` list purely to
#:   pick whose field values get written — never to decide which channels
#:   participate — the same spirit as the pre-existing "duplicate tvgIds
#:   progressively update the same channel, last entry wins" behavior.
#:
#: - INV-SYMMETRIC-NEW-CHANNEL-PROTECTION: the same "a different, present
#:   tvgId blocks a number-based merge" rule that protects pre-existing
#:   channels (INV-NO-HIJACK) also applies to two *newly created* channels
#:   within the final pass's own live de-dup index: two unmatched entries
#:   only collapse onto one freshly created channel via a shared number if
#:   their tvgIds are compatible (equal, or at least one side is null).
#:   Two entries with different, both-present, non-equal tvgIds that
#:   happen to share a number become two separate new channels.
#:
#: - INV-IDEMPOTENT-REIMPORT: re-importing the exact same, unchanged file
#:   into the same lineup repeatedly converges to a stable state after the
#:   first re-import — no unbounded channel growth, no legitimately
#:   matched channel flipping to flagged-missing on a later identical
#:   re-import. This falls out of the other invariants rather than being
#:   separately implemented: `lineup.channels`' order is stable across
#:   runs (updates replace in place by id; new channels are only ever
#:   appended), so INV-DETERMINISTIC-COMPETITION's "channels taken in
#:   their existing list order" pairing reproduces the *same* entry/
#:   channel pairing on every re-import of the same file, which is what
#:   keeps the result stable rather than oscillating or growing.
def _merge_entries(
    lineup: Lineup, entries: list[M3UEntry], now: datetime
) -> M3UImportResult:
    """Merge `entries` into `lineup.channels` in place and return the
    resulting `M3UImportResult`.

    Matching rule (CLAUDE.md Core workflow 1): an incoming entry matches an
    existing channel by `tvgId` first; only when that doesn't resolve to
    any existing channel (the entry has no `tvgId`, or its `tvgId` doesn't
    match any channel) does `number` get consulted as a fallback. See the
    `INV-*` invariants block directly above this docstring for the full,
    precise contract; this docstring just narrates the structure that
    implements it.

    Resolved in three passes over the whole `entries` list, rather than
    greedily one entry at a time, so the outcome is independent of entry
    order within the file wherever the invariants above require it:

      1. Pass 1 (INV-TVGID-FIRST): for every entry, check its `tvgId`
         against the *original* existing channels (a snapshot taken
         before any mutation this run). Every match is claimed
         immediately, for the whole file, before any number-based
         matching happens at all.

      2. Pass 2 (INV-DETERMINISTIC-COMPETITION): entries left unresolved
         by pass 1 are grouped by `number` and matched against existing
         channels *not already claimed* in pass 1, grouped the same way.
         Within each number's group, candidate entries are ranked
         tvgId-less-first (see INV-DETERMINISTIC-COMPETITION) and paired
         off against that number's channels in their existing
         `lineup.channels` order. This both makes pass 1 authoritative
         (a channel reserved by some entry's tvgId match can never be
         re-claimed by a different entry's number fallback) and resolves
         same-number competition between multiple entries/channels
         deterministically rather than first-come-first-served.

      3. Final pass: applies the resolved pairings from passes 1/2 (by
         channel `id`, per INV-IDENTITY — never by list/object equality),
         or creates a new channel for anything still unresolved, in file
         order. Within *this* pass, entries that share a `tvgId`/`number`
         with each other (not with any pre-existing channel — that's
         already fully resolved by passes 1/2) are de-duplicated onto the
         same channel via a live index, so duplicate entries for a *new*
         channel land on one channel rather than several — see
         INV-SYMMETRIC-NEW-CHANNEL-PROTECTION for the tvgId-compatibility
         guard on that index, and "Duplicate tvgIds/numbers" below for the
         resulting `updated`-list behavior. Critically (INV-NO-HIJACK),
         the live index is only ever seeded with channels *newly created
         by this same final pass* — an entry resolved via passes 1/2
         never has its `tvgId`/`number` written into the live index, so a
         later, non-matching entry can never reach back into an
         already-resolved pre-existing channel through the live index.

    Matched channels have `name`/`logoUrl`/`number`/`tvgId`/
    `sourceStreamUrl`/`group` overwritten from the incoming entry and
    `missingSince` unconditionally cleared to `None` (a match means the
    channel is present in this import, whether or not it was previously
    flagged missing) — but `mapping` is always carried over untouched.

    Unmatched incoming entries become new channels (via the same
    `Channel` validation path as `services.lineups.add_channel`, so a
    pathological entry can't bypass e.g. the non-empty-name constraint).

    Existing channels matched by no entry this run get `missingSince` set
    to `now` *only if it's currently `None`* — preserving the original
    "first went missing" timestamp across repeated re-imports where the
    channel is still absent — and are never removed from `lineup.channels`
    (deletion is a separate, explicit user action via the existing
    `DELETE /api/lineups/{lineup_id}/channels/{channel_id}` endpoint).

    Also computes `M3UImportResult.unidentifiedEntryCount` — the count of
    entries with neither `tvgId` nor `number` — purely by inspecting the
    incoming `entries` list; this is reported on every call, not something
    the matching passes above need to produce or are affected by.

    Duplicate `tvgId`s/`number`s *within the same `entries` list* (the
    parser doesn't de-duplicate — see `parse_m3u`) that don't match any
    pre-existing channel are handled by a live index kept up to date as
    the final pass processes each entry, so the second (and further)
    duplicate entries land on the *same*, newly created channel rather
    than each creating a separate one (subject to the tvgId-compatibility
    guard in INV-SYMMETRIC-NEW-CHANNEL-PROTECTION). Because of this, a
    channel touched by more than one duplicate entry in one import can
    appear more than once in the returned `updated`/`added` lists (each
    occurrence is a real write — the last one's data is what's actually
    persisted) rather than being de-duplicated in the result.
    """
    added: list[Channel] = []
    updated: list[Channel] = []
    matched_ids: set[str] = set()

    # Descriptive count of entries with no stable identity signal at all —
    # computed from the raw `entries` list up front, independent of (and
    # unaffected by) the matching passes below: it's a property of what's
    # *in the file*, not of how this particular import happened to resolve.
    # See `M3UImportResult.unidentifiedEntryCount`'s docstring.
    unidentified_entry_count = sum(
        1 for entry in entries if not entry.tvgId and not entry.number
    )

    # Snapshot of *pre-existing* channels only — never mutated or added to
    # as entries are processed below, which is exactly what makes passes 1
    # and 2 order-independent: every entry sees the same starting state.
    # Stable id -> list-position map, built once before any mutation
    # (INV-IDENTITY): the final pass below writes `lineup.channels` only
    # via in-place same-position replacement or append, so this mapping
    # stays valid for the whole merge — unlike `list.index(channel)`,
    # which breaks the moment a channel's value changes underneath it.
    channel_index_by_id: dict[str, int] = {
        channel.id: position for position, channel in enumerate(lineup.channels)
    }
    original_by_tvg_id: dict[str, Channel] = {
        channel.tvgId: channel for channel in lineup.channels if channel.tvgId
    }

    # --- Pass 1: tvgId matches against existing channels, globally. -----
    entry_target: dict[int, Channel] = {}
    tvg_claimed_channel_ids: set[str] = set()
    for index, entry in enumerate(entries):
        if entry.tvgId and entry.tvgId in original_by_tvg_id:
            target = original_by_tvg_id[entry.tvgId]
            entry_target[index] = target
            tvg_claimed_channel_ids.add(target.id)

    # --- Pass 2: number fallback, only for still-unresolved entries, and
    # only against existing channels not already claimed in pass 1.
    # Channels sharing the same `number` are grouped (not collapsed to a
    # single winner by dict-overwrite) so that, when a previous re-import
    # already created a second channel at the same number, both are
    # available as pairing targets this time too — see INV-IDEMPOTENT-
    # REIMPORT. ------------------------------------------------------
    unclaimed_by_number: dict[str, list[Channel]] = {}
    for channel in lineup.channels:
        if channel.number and channel.id not in tvg_claimed_channel_ids:
            unclaimed_by_number.setdefault(channel.number, []).append(channel)

    candidates_by_number: dict[str, list[int]] = {}
    for index, entry in enumerate(entries):
        if index in entry_target:
            continue
        if entry.number and entry.number in unclaimed_by_number:
            candidates_by_number.setdefault(entry.number, []).append(index)

    for number, channel_bucket in unclaimed_by_number.items():
        candidate_indices = candidates_by_number.get(number)
        if not candidate_indices:
            continue
        # INV-DETERMINISTIC-COMPETITION: tvgId-less entries outrank
        # tvgId-bearing-but-unmatched ones (content-based, order-
        # independent); ties within a rank are broken by original file
        # position purely to decide whose data wins, never which channels
        # participate (see the invariant's docstring for the reasoning).
        ranked_indices = sorted(
            candidate_indices, key=lambda i: (0 if not entries[i].tvgId else 1, i)
        )
        for channel, index in zip(channel_bucket, ranked_indices):
            entry_target[index] = channel

    # --- Final pass: apply the resolved pairings (or create new channels
    # for anything still unresolved), de-duplicating entries that share a
    # tvgId/number with each other but with no pre-existing channel. -----
    by_tvg_id_live: dict[str, Channel] = {}
    by_number_live: dict[str, Channel] = {}

    for index, entry in enumerate(entries):
        existing = entry_target.get(index)
        if existing is None and entry.tvgId and entry.tvgId in by_tvg_id_live:
            existing = by_tvg_id_live[entry.tvgId]
        if existing is None and entry.number and entry.number in by_number_live:
            candidate = by_number_live[entry.number]
            # INV-SYMMETRIC-NEW-CHANNEL-PROTECTION: only merge via a
            # shared number if the tvgIds are compatible (equal, or at
            # least one side is null) — a different, present tvgId on
            # each side means these are two distinct channels that merely
            # happen to reuse the same number, not duplicate entries for
            # the same new channel.
            if (
                candidate.tvgId is None
                or entry.tvgId is None
                or candidate.tvgId == entry.tvgId
            ):
                existing = candidate

        if existing is not None:
            merged = {
                **existing.model_dump(),
                "name": entry.name,
                "logoUrl": entry.logoUrl,
                "number": entry.number,
                "tvgId": entry.tvgId,
                "sourceStreamUrl": entry.streamUrl,
                "group": entry.groupTitle,
                "missingSince": None,
                # `mapping`/`id` intentionally not overwritten above — both
                # come through as-is from `existing.model_dump()`.
            }
            try:
                new_channel = Channel.model_validate(merged)
            except PydanticValidationError as exc:
                raise ValidationError(
                    f"invalid M3U-derived update for channel {existing.id!r} "
                    f"in lineup {lineup.id!r}: {exc}"
                ) from exc
            # INV-IDENTITY: looked up by stable id, never by
            # `list.index(existing)` (Pydantic value-equality on a
            # mutable object) — a prior duplicate-entry write targeting
            # this same channel earlier in this same final pass must not
            # make this lookup fail.
            lineup.channels[channel_index_by_id[existing.id]] = new_channel
            updated.append(new_channel)
            channel = new_channel
        else:
            try:
                channel = Channel(
                    id=_new_id(),
                    number=entry.number,
                    name=entry.name,
                    logoUrl=entry.logoUrl,
                    tvgId=entry.tvgId,
                    group=entry.groupTitle,
                    sourceStreamUrl=entry.streamUrl,
                )
            except PydanticValidationError as exc:
                raise ValidationError(
                    f"invalid M3U entry {entry.name!r} for lineup "
                    f"{lineup.id!r}: {exc}"
                ) from exc
            lineup.channels.append(channel)
            channel_index_by_id[channel.id] = len(lineup.channels) - 1
            added.append(channel)

        matched_ids.add(channel.id)
        # Only seed the live indices when this entry was *not* resolved
        # against a pre-existing channel by pass 1/2 (`entry_target`).
        # Pre-existing channels are fully and finally resolved by passes
        # 1 and 2 alone — a channel reached via `entry_target` (whether by
        # tvgId in pass 1 or by number fallback in pass 2) must never be
        # reachable through `by_tvg_id_live`/`by_number_live` by some
        # *other*, non-matching entry later in the same file. The live
        # indices exist only so that multiple unmatched incoming entries
        # that share a tvgId/number *with each other* collapse onto the
        # same freshly created channel; letting a pre-existing channel's
        # identifiers leak into them would let an unrelated later entry
        # steal/overwrite it by number (or tvgId) collision alone — the
        # exact bug class `entry_target`/`tvg_claimed_channel_ids` above
        # was built to prevent.
        if index not in entry_target:
            if entry.tvgId:
                by_tvg_id_live[entry.tvgId] = channel
            if entry.number:
                # Don't clobber an existing, *incompatible* number-live
                # entry (INV-SYMMETRIC-NEW-CHANNEL-PROTECTION): only
                # (re)point `by_number_live[entry.number]` at `channel`
                # when doing so doesn't paper over a real tvgId conflict
                # with whatever is currently registered for this number.
                current = by_number_live.get(entry.number)
                if (
                    current is None
                    or current.id == channel.id
                    or current.tvgId is None
                    or channel.tvgId is None
                    or current.tvgId == channel.tvgId
                ):
                    by_number_live[entry.number] = channel

    flagged_missing: list[Channel] = []
    for channel in lineup.channels:
        if channel.id in matched_ids:
            continue
        if channel.missingSince is None:
            channel.missingSince = now
        flagged_missing.append(channel)

    lineup.updatedAt = now
    return M3UImportResult(
        added=added,
        updated=updated,
        flaggedMissing=flagged_missing,
        unidentifiedEntryCount=unidentified_entry_count,
    )


def import_m3u_entries(
    lineup_id: str,
    entries: list[M3UEntry],
    *,
    base_dir: Path | None = None,
    now: datetime | None = None,
) -> tuple[Lineup, M3UImportResult]:
    """Re-import parsed M3U entries into an existing `m3u`-sourced lineup.

    One atomic `update_lineups` load-mutate-save cycle for the whole merge
    (matching + updates + additions + missing-flagging) — never several
    separate storage calls, per CLAUDE.md/`storage/lineups.py`'s
    lost-update-race rule.

    Returns the up-to-date `Lineup` *from that same transaction* alongside
    the `M3UImportResult`, rather than making the caller re-read the lineup
    in a second, separate call after this one returns — a second read
    could race with a concurrent delete (spurious 500) or simply return a
    snapshot that no longer corresponds to this `result` (see
    `app.api.m3u`, which used to do exactly that).

    Raises `NotFoundError` if `lineup_id` doesn't exist, or `ValidationError`
    if the target lineup's `source` isn't `m3u` (re-importing an M3U file
    into a manually-curated lineup isn't part of the documented workflow
    and would silently overwrite hand-entered channel metadata).
    """
    effective_now = now if now is not None else _now()

    def mutate(data: LineupsFile) -> tuple[Lineup, M3UImportResult]:
        lineup = _find_lineup(data, lineup_id)
        if lineup.source != LineupSource.M3U:
            raise ValidationError(
                f"lineup {lineup_id!r} has source {lineup.source.value!r}, "
                "not 'm3u' — re-importing an M3U file into a non-M3U-sourced "
                "lineup is not supported"
            )
        result = _merge_entries(lineup, entries, effective_now)
        return lineup, result

    return update_lineups(mutate, base_dir)


def create_lineup_from_m3u(
    name: str,
    entries: list[M3UEntry],
    *,
    base_dir: Path | None = None,
    now: datetime | None = None,
) -> tuple[Lineup, M3UImportResult]:
    """Create a new, empty `m3u`-sourced lineup, then import `entries` into
    it.

    Reuses `_merge_entries` (the same function `import_m3u_entries` uses
    for re-import) rather than a separate "just append everything" path, so
    first-import and re-import behavior (name fallback, `group`, etc.) stay
    identical. Every parsed entry ends up in the result's `added` list
    since the new lineup starts with no channels. Lineup creation and the
    initial import happen in one atomic `update_lineups` cycle.
    """
    effective_now = now if now is not None else _now()
    lineup = Lineup(
        id=_new_id(),
        name=name,
        source=LineupSource.M3U,
        createdAt=effective_now,
        updatedAt=effective_now,
        sdLineupIds=[],
        channels=[],
    )

    def mutate(data: LineupsFile) -> M3UImportResult:
        data.lineups.append(lineup)
        return _merge_entries(lineup, entries, effective_now)

    result = update_lineups(mutate, base_dir)
    return lineup, result
