"""Unit tests for `app.services.m3u`: parsing and re-import merge logic."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.lineup import Channel, ChannelMapping, Lineup, LineupSource, LineupsFile
from app.services import m3u as m3u_service
from app.services.lineups import NotFoundError, ValidationError
from app.storage.lineups import load_lineups, save_lineups

# --- Fixture M3U content -------------------------------------------------

WELL_FORMED_M3U = """#EXTM3U
#EXTINF:-1 tvg-id="KGO.us" tvg-name="KGO-TV" tvg-logo="https://example.test/kgo.png" tvg-chno="7.1" group-title="Local",KGO-TV (display)
http://hdhomerun.local/auto/v7.1
#EXTINF:-1 tvg-id="KPIX.us" tvg-name="KPIX" tvg-chno="5.1" group-title="Local",KPIX
http://hdhomerun.local/auto/v5.1
"""

_BOM = "﻿"

MESSY_M3U = (
    _BOM + "#EXTM3U\r\n"
    "\r\n"
    + '#EXTINF:-1 tvg-id="A.us" tvg-name="Channel A" tvg-chno="1.1",A display\r\n'
    + "http://example.test/a\r\n"
    + "# a plain comment, not EXTINF\n"
    + "#EXTGRP:Sports\n"
    + '#EXTINF:-1 tvg-logo=unquoted.png tvg-id="" tvg-chno="2.1",\n'
    + "http://example.test/no-name\n"
    + '#EXTINF:-1 tvg-id="DUP.us",First Dup\n'
    + "http://example.test/dup1\n"
    + '#EXTINF:-1 tvg-id="DUP.us",Second Dup\n'
    + "http://example.test/dup2\n"
    + '#EXTINF:-1 tvg-id="ORPHAN.us",Orphan (no url follows)\n'
    + '#EXTINF:-1 tvg-id="NEXT.us",Next entry\n'
    + "http://example.test/next\n"
)

NOT_M3U = "this is just some text\nnot a playlist at all\n"

#: Andrew's actual real-world HDHomeRun firmware export (checkpoint 19 bug
#: report) — this firmware emits `channel-id`/`channel-number` instead of
#: `tvg-id`/`tvg-chno`. Used verbatim (not a synthetic equivalent) because
#: the bug this guards against (every one of his 88 real channels being
#: treated as brand-new on every re-import) was only caught against the
#: real file, not a hand-rolled approximation of it.
HDHOMERUN_CHANNEL_ID_M3U = """#EXTM3U
#EXTINF:-1 channel-id="2.2" channel-number="2.2" tvg-name="World",2.2 World
http://172.16.8.101:5004/auto/v2.2
#EXTINF:-1 channel-id="4.1" channel-number="4.1" tvg-name="WBZ-DT",4.1 WBZ-DT
http://172.16.8.101:5004/auto/v4.1
"""


# --- parse_m3u ------------------------------------------------------------


def test_parse_well_formed_m3u():
    entries = m3u_service.parse_m3u(WELL_FORMED_M3U)
    assert len(entries) == 2

    first, second = entries
    assert first.tvgId == "KGO.us"
    assert first.name == "KGO-TV"  # tvg-name preferred over display text
    assert first.logoUrl == "https://example.test/kgo.png"
    assert first.number == "7.1"
    assert first.groupTitle == "Local"
    assert first.streamUrl == "http://hdhomerun.local/auto/v7.1"

    assert second.tvgId == "KPIX.us"
    assert second.name == "KPIX"
    assert second.number == "5.1"


def test_parse_rejects_non_m3u_content():
    with pytest.raises(m3u_service.M3UParseError):
        m3u_service.parse_m3u(NOT_M3U)


def test_parse_rejects_empty_content():
    with pytest.raises(m3u_service.M3UParseError):
        m3u_service.parse_m3u("")
    with pytest.raises(m3u_service.M3UParseError):
        m3u_service.parse_m3u("   \n   \n")


def test_parse_tolerates_messiness_without_crashing():
    entries = m3u_service.parse_m3u(MESSY_M3U)

    by_tvg_id = {}
    for entry in entries:
        by_tvg_id.setdefault(entry.tvgId, []).append(entry)

    # CRLF + BOM + a comment line + an #EXTGRP directive line all handled.
    a = by_tvg_id["A.us"][0]
    assert a.name == "Channel A"  # tvg-name present, used over display text
    assert a.number == "1.1"
    assert a.streamUrl == "http://example.test/a"

    # Missing/unquoted tvg-logo attribute skipped; missing tvg-id skipped
    # (empty-string value treated as absent); blank display name falls
    # back to a positional placeholder rather than raising or being blank.
    no_name_entries = [e for e in entries if e.streamUrl == "http://example.test/no-name"]
    assert len(no_name_entries) == 1
    no_name = no_name_entries[0]
    assert no_name.tvgId is None
    assert no_name.logoUrl is None
    assert no_name.name.strip() != ""

    # Duplicate tvg-id across two entries: parser does not de-duplicate,
    # both come through as separate entries (merge logic handles this).
    assert len(by_tvg_id["DUP.us"]) == 2
    assert by_tvg_id["DUP.us"][0].name == "First Dup"
    assert by_tvg_id["DUP.us"][1].name == "Second Dup"

    # An #EXTINF with no following URL line (ORPHAN) is dropped entirely —
    # it never shows up as an entry at all, and doesn't corrupt the entry
    # that follows it (NEXT).
    assert "ORPHAN.us" not in by_tvg_id
    assert by_tvg_id["NEXT.us"][0].streamUrl == "http://example.test/next"


def test_parse_fallback_to_display_name_when_no_tvg_name():
    text = (
        "#EXTM3U\n"
        '#EXTINF:-1 tvg-id="X.us",Display Only\n'
        "http://example.test/x\n"
    )
    entries = m3u_service.parse_m3u(text)
    assert entries[0].name == "Display Only"


def test_parse_fallback_to_tvg_id_when_no_name_at_all():
    text = '#EXTM3U\n#EXTINF:-1 tvg-id="Y.us",\nhttp://example.test/y\n'
    entries = m3u_service.parse_m3u(text)
    assert entries[0].name == "Y.us"


def test_parse_fallback_placeholder_when_nothing_identifies_the_entry():
    text = "#EXTM3U\n#EXTINF:-1,\nhttp://example.test/z\n"
    entries = m3u_service.parse_m3u(text)
    assert entries[0].name.startswith("Channel")
    assert entries[0].tvgId is None


def test_parse_quoted_comma_in_attribute_value_does_not_truncate_display_name():
    text = (
        "#EXTM3U\n"
        '#EXTINF:-1 tvg-name="Channel, Two" tvg-id="CT.us",ignored display\n'
        "http://example.test/ct\n"
    )
    entries = m3u_service.parse_m3u(text)
    assert entries[0].name == "Channel, Two"


def test_parse_recognizes_channel_id_and_channel_number_alternates():
    """Regression for checkpoint 19 (Andrew's real HDHomeRun firmware
    export): `channel-id`/`channel-number` are alternates for
    `tvg-id`/`tvg-chno` respectively, recognized when the standard
    attribute is absent. Using Andrew's exact real sample file, verbatim.
    """
    entries = m3u_service.parse_m3u(HDHOMERUN_CHANNEL_ID_M3U)
    assert len(entries) == 2

    first, second = entries
    assert first.tvgId == "2.2"
    assert first.number == "2.2"
    assert first.name == "World"

    assert second.tvgId == "4.1"
    assert second.number == "4.1"
    assert second.name == "WBZ-DT"

    # Both entries carry a real identifier -> no unidentified-entry warning.
    assert sum(1 for e in entries if not e.tvgId and not e.number) == 0


def test_parse_prefers_tvg_id_and_tvg_chno_over_channel_alternates_when_both_present():
    """Documents the precedence rule: when an entry has *both* the standard
    (`tvg-id`/`tvg-chno`) and alternate (`channel-id`/`channel-number`)
    attributes, the standard one wins.
    """
    text = (
        "#EXTM3U\n"
        '#EXTINF:-1 tvg-id="STD.us" channel-id="ALT.us" tvg-chno="1.0" '
        'channel-number="9.9" tvg-name="Both",Both\n'
        "http://example.test/both\n"
    )
    entries = m3u_service.parse_m3u(text)
    assert entries[0].tvgId == "STD.us"
    assert entries[0].number == "1.0"


# --- import_m3u_entries / create_lineup_from_m3u merge logic ---------------


def _make_entry(**kwargs):
    defaults = dict(tvgId=None, name="Channel", logoUrl=None, number=None, groupTitle=None, streamUrl="http://x")
    defaults.update(kwargs)
    from app.models.m3u import M3UEntry

    return M3UEntry(**defaults)


def _seed_lineup(tmp_path, lineup: Lineup) -> None:
    data = LineupsFile(lineups=[lineup])
    save_lineups(data, base_dir=tmp_path)


def test_create_lineup_from_m3u_adds_every_entry(tmp_path):
    entries = [
        _make_entry(tvgId="A.us", name="A", streamUrl="http://a"),
        _make_entry(tvgId="B.us", name="B", streamUrl="http://b"),
    ]
    lineup, result = m3u_service.create_lineup_from_m3u(
        "My Lineup", entries, base_dir=tmp_path
    )

    assert lineup.source == LineupSource.M3U
    assert len(result.added) == 2
    assert result.updated == []
    assert result.flaggedMissing == []
    assert {c.tvgId for c in lineup.channels} == {"A.us", "B.us"}

    # Persisted.
    on_disk = load_lineups(base_dir=tmp_path)
    assert len(on_disk.lineups[0].channels) == 2


def test_import_matches_by_tvg_id(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    existing = Channel(id="c1", tvgId="A.us", name="Old Name", number="1.1")
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[existing],
    )
    _seed_lineup(tmp_path, lineup)

    entries = [_make_entry(tvgId="A.us", name="New Name", number="2.2", streamUrl="http://new")]
    _, result = m3u_service.import_m3u_entries("lu1", entries, base_dir=tmp_path)

    assert len(result.updated) == 1
    updated = result.updated[0]
    assert updated.id == "c1"
    assert updated.name == "New Name"
    assert updated.number == "2.2"
    assert updated.sourceStreamUrl == "http://new"
    assert result.added == []
    assert result.flaggedMissing == []


def test_import_matches_by_number_fallback_when_no_tvg_id(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    existing = Channel(id="c1", tvgId=None, name="Old Name", number="7.1")
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[existing],
    )
    _seed_lineup(tmp_path, lineup)

    entries = [_make_entry(tvgId=None, name="New Name", number="7.1", streamUrl="http://new")]
    _, result = m3u_service.import_m3u_entries("lu1", entries, base_dir=tmp_path)

    assert len(result.updated) == 1
    assert result.updated[0].id == "c1"
    assert result.updated[0].name == "New Name"


def test_import_tvg_id_present_but_not_matching_falls_back_to_number(tmp_path):
    """tvgId is present on the incoming entry but doesn't match any
    existing channel's tvgId *anywhere in the file*; number still matches
    an existing channel -> falls back to number, per CLAUDE.md ("match by
    tvgId ... if no tvgId match, fall back to number").

    This scenario is unaffected by the order-independence fix in
    `_merge_entries` (see `test_import_tvg_id_match_is_order_independent_
    across_whole_file`): there is only one entry in this file and its
    tvgId genuinely doesn't match any channel in pass 1, so it's still
    eligible for the pass-2 number fallback exactly as before.
    """
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    existing = Channel(id="c1", tvgId="OLD.us", name="Old Name", number="7.1")
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[existing],
    )
    _seed_lineup(tmp_path, lineup)

    entries = [
        _make_entry(tvgId="NEW.us", name="New Name", number="7.1", streamUrl="http://new")
    ]
    _, result = m3u_service.import_m3u_entries("lu1", entries, base_dir=tmp_path)

    assert len(result.updated) == 1
    assert result.updated[0].id == "c1"
    assert result.updated[0].tvgId == "NEW.us"  # tvgId itself still gets updated


def test_import_tvg_id_match_is_order_independent_across_whole_file():
    """Regression for the HIGH-severity order-dependence bug: channel A
    (tvgId="A.us", number="1.1") has a mapping. The file
    contains two entries: one for a brand-new channel B that happens to
    reuse channel A's *old* number ("1.1"), and one that is genuinely
    channel A re-numbered (tvgId="A.us", number="2.2"). Regardless of
    which entry comes first in the file, channel A must be matched by its
    own tvgId (updated to number "2.2", mapping preserved) and channel B
    must be created fresh and unmapped at number "1.1" — an earlier entry
    falling back to a number match must never be able to steal a channel
    that a later entry in the same file would have claimed by tvgId.
    """
    from app.services.m3u import _merge_entries

    mapping = ChannelMapping(sdStationId="STATION_A", sdLineupId="USA-OTA")

    def make_lineup(now):
        channel_a = Channel(
            id="a", tvgId="A.us", name="Channel A", number="1.1", mapping=mapping
        )
        return Lineup(
            id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
            channels=[channel_a],
        )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entry_b_reusing_old_number = _make_entry(
        tvgId="B.us", name="ChanB", number="1.1", streamUrl="http://b"
    )
    entry_a_renumbered = _make_entry(
        tvgId="A.us", name="Channel A", number="2.2", streamUrl="http://a"
    )

    for order_name, entries in (
        ("B-then-A", [entry_b_reusing_old_number, entry_a_renumbered]),
        ("A-then-B", [entry_a_renumbered, entry_b_reusing_old_number]),
    ):
        lineup = make_lineup(now)
        result = _merge_entries(lineup, entries, now)

        assert len(result.updated) == 1, order_name
        updated = result.updated[0]
        assert updated.id == "a", order_name
        assert updated.number == "2.2", order_name
        assert updated.tvgId == "A.us", order_name
        assert updated.mapping is not None, order_name
        assert updated.mapping.sdStationId == "STATION_A", order_name

        assert len(result.added) == 1, order_name
        added = result.added[0]
        assert added.id != "a", order_name
        assert added.tvgId == "B.us", order_name
        assert added.number == "1.1", order_name
        assert added.mapping is None or added.mapping.sdStationId is None, order_name

        assert result.flaggedMissing == [], order_name


def test_import_pre_existing_tvg_id_match_not_reachable_via_live_number_index():
    """Regression for the HIGH-severity variant of the ordering bug above,
    found by peer review in the final pass's live de-dup indices
    (`by_tvg_id_live`/`by_number_live`).

    Channel A pre-exists with tvgId="A.us", number="1.1" and a mapping. The file contains two entries, in either order: one that is
    genuinely channel A (tvgId="A.us", number="1.1" — resolved by pass 1),
    and one for a brand-new, unrelated channel B that merely happens to
    reuse the *same* number ("1.1") but a *different* tvgId ("B.us").

    The bug: the final pass's live indices used to be seeded from every
    entry's resolved channel, including ones already resolved against a
    pre-existing channel by pass 1/2 — not just channels newly created
    within the final pass. That let the second entry's number ("1.1")
    hit `by_number_live` and silently reassign channel A's identity
    (tvgId, number) and steal its mapping onto what should have
    been an unrelated new channel B — even though pass 1/2's
    `tvg_claimed_channel_ids` correctly refused this exact pairing.

    Regardless of file order, channel A must keep its own id/tvgId/number
    and its mapping untouched, and channel B must be created as
    a brand-new, unmapped channel.
    """
    from app.services.m3u import _merge_entries

    mapping = ChannelMapping(sdStationId="STATION_A", sdLineupId="USA-OTA")

    def make_lineup(now):
        channel_a = Channel(
            id="a", tvgId="A.us", name="Channel A", number="1.1", mapping=mapping
        )
        return Lineup(
            id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
            channels=[channel_a],
        )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entry_a = _make_entry(tvgId="A.us", name="Channel A", number="1.1", streamUrl="http://a")
    entry_b = _make_entry(tvgId="B.us", name="Channel B", number="1.1", streamUrl="http://b")

    for order_name, entries in (
        ("A-then-B", [entry_a, entry_b]),
        ("B-then-A", [entry_b, entry_a]),
    ):
        lineup = make_lineup(now)
        result = _merge_entries(lineup, entries, now)

        assert len(result.updated) == 1, order_name
        updated = result.updated[0]
        assert updated.id == "a", order_name
        assert updated.tvgId == "A.us", order_name
        assert updated.number == "1.1", order_name
        assert updated.mapping is not None, order_name
        assert updated.mapping.sdStationId == "STATION_A", order_name

        assert len(result.added) == 1, order_name
        added = result.added[0]
        assert added.id != "a", order_name
        assert added.tvgId == "B.us", order_name
        assert added.number == "1.1", order_name
        assert added.mapping is None or added.mapping.sdStationId is None, order_name

        # Exactly two channels in the lineup afterward: A (updated) and the
        # new B — channel A's identity must never have been overwritten by
        # B's entry, and no third/phantom channel should exist either.
        assert len(lineup.channels) == 2, order_name
        by_id = {c.id: c for c in lineup.channels}
        assert by_id["a"].tvgId == "A.us", order_name
        assert by_id["a"].mapping.sdStationId == "STATION_A", order_name

        assert result.flaggedMissing == [], order_name


def test_import_pre_existing_number_fallback_match_not_reachable_via_live_number_index():
    """Same bug class as above, but for pass 2's *number*-fallback match
    rather than pass 1's tvgId match — answering the question of whether
    a pre-existing channel resolved via pass 2 (not pass 1) is equally
    reachable through the final pass's live index.

    Channel A pre-exists with *no* tvgId, number="1.1", and a mapping — so it can only ever be matched by number. The file's first
    entry has no tvgId either, so it resolves to channel A purely via
    pass 2's number fallback. The file's second entry has a different,
    non-matching tvgId ("B.us") but the same number ("1.1"); it must
    never be able to reach channel A through the live index and steal its
    mapping — it should instead become a brand-new, unmapped channel B.
    """
    from app.services.m3u import _merge_entries

    mapping = ChannelMapping(sdStationId="STATION_A", sdLineupId="USA-OTA")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    channel_a = Channel(id="a", tvgId=None, name="Channel A", number="1.1", mapping=mapping)
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[channel_a],
    )

    entry_bare = _make_entry(tvgId=None, name="Channel A", number="1.1", streamUrl="http://a")
    entry_b = _make_entry(tvgId="B.us", name="Channel B", number="1.1", streamUrl="http://b")

    result = _merge_entries(lineup, [entry_bare, entry_b], now)

    assert len(result.updated) == 1
    updated = result.updated[0]
    assert updated.id == "a"
    assert updated.number == "1.1"
    assert updated.mapping is not None
    assert updated.mapping.sdStationId == "STATION_A"

    assert len(result.added) == 1
    added = result.added[0]
    assert added.id != "a"
    assert added.tvgId == "B.us"
    assert added.number == "1.1"
    assert added.mapping is None or added.mapping.sdStationId is None

    assert len(lineup.channels) == 2
    by_id = {c.id: c for c in lineup.channels}
    assert by_id["a"].mapping.sdStationId == "STATION_A"


def test_import_duplicate_new_entries_still_collapse_despite_pre_existing_claim():
    """Confirms the fix doesn't regress the legitimate live-index dedup
    behavior: a pre-existing channel resolved by tvgId in pass 1 must
    stay protected, while *two* genuinely new, unmatched entries that
    share a tvgId/number *with each other* still collapse onto a single
    newly created channel (not two separate ones) — exercising both the
    protection and the intentional dedup path in the same run.
    """
    from app.services.m3u import _merge_entries

    mapping = ChannelMapping(sdStationId="STATION_A", sdLineupId="USA-OTA")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    channel_a = Channel(
        id="a", tvgId="A.us", name="Channel A", number="1.1", mapping=mapping
    )
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[channel_a],
    )

    entry_a = _make_entry(tvgId="A.us", name="Channel A", number="1.1", streamUrl="http://a")
    entry_b1 = _make_entry(
        tvgId="B.us", name="Channel B (first)", number="1.1", streamUrl="http://b1"
    )
    entry_b2 = _make_entry(
        tvgId="B.us", name="Channel B (second)", number="1.1", streamUrl="http://b2"
    )

    result = _merge_entries(lineup, [entry_a, entry_b1, entry_b2], now)

    # entry_a resolves against the pre-existing channel A (pass 1) -> one
    # `updated` write. entry_b1 is unmatched -> creates a new channel
    # (`added`). entry_b2 shares B's tvgId/number *with entry_b1* (not
    # with any pre-existing channel), so the live index correctly
    # collapses it onto that same new channel -> a second write, recorded
    # in `updated` (per `_merge_entries`'s docstring: a channel touched by
    # more than one entry in a run can appear in both lists, since each
    # occurrence is a real write).
    assert len(result.updated) == 2
    assert result.updated[0].id == "a"
    assert result.updated[0].mapping.sdStationId == "STATION_A"

    assert len(result.added) == 1
    new_channel_id = result.added[0].id
    assert new_channel_id != "a"

    # The second B write (in `updated`) landed on the *same* channel the
    # first B write created (in `added`), not a separate third channel.
    assert result.updated[1].id == new_channel_id
    assert result.updated[1].name == "Channel B (second)"
    assert result.updated[1].tvgId == "B.us"

    # Exactly two channels total: A (untouched identity) and the one new B.
    assert len(lineup.channels) == 2
    by_id = {c.id: c for c in lineup.channels}
    assert by_id["a"].tvgId == "A.us"
    assert by_id["a"].mapping.sdStationId == "STATION_A"


def test_import_tvg_id_match_wins_over_conflicting_number_match():
    """Entry's tvgId matches channel A; entry's number matches a different
    channel B. tvgId wins (channel A is updated, channel B is untouched
    and flagged missing)."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    channel_a = Channel(id="a", tvgId="A.us", name="Channel A", number="1.1")
    channel_b = Channel(id="b", tvgId="B.us", name="Channel B", number="2.2")
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[channel_a, channel_b],
    )

    from app.services.m3u import _merge_entries

    entry = _make_entry(tvgId="A.us", name="Updated", number="2.2", streamUrl="http://x")
    result = _merge_entries(lineup, [entry], now)

    assert len(result.updated) == 1
    assert result.updated[0].id == "a"
    assert result.updated[0].name == "Updated"
    assert len(result.flaggedMissing) == 1
    assert result.flaggedMissing[0].id == "b"


def test_import_does_not_match_stale_freed_up_number_within_same_import():
    """Regression: channel A's number changes from "1.1" to "9.9" in this
    import; a later entry in the *same* file carries the now-freed-up
    "1.1" with no tvgId. It must be treated as unmatched/new, not
    incorrectly matched to channel A via a number A no longer has.
    """
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    channel_a = Channel(id="a", tvgId="A.us", name="Channel A", number="1.1")
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[channel_a],
    )

    from app.services.m3u import _merge_entries

    entry_a_renumbered = _make_entry(
        tvgId="A.us", name="Channel A", number="9.9", streamUrl="http://a"
    )
    entry_reusing_old_number = _make_entry(
        tvgId=None, name="Different Channel", number="1.1", streamUrl="http://diff"
    )
    result = _merge_entries(lineup, [entry_a_renumbered, entry_reusing_old_number], now)

    assert len(result.updated) == 1
    assert result.updated[0].id == "a"
    assert result.updated[0].number == "9.9"

    assert len(result.added) == 1
    assert result.added[0].name == "Different Channel"
    assert result.added[0].number == "1.1"
    assert result.added[0].id != "a"


def test_import_preserves_mapping_on_metadata_update(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    mapping = ChannelMapping(sdStationId="10123", sdLineupId="USA-OTA")
    existing = Channel(id="c1", tvgId="A.us", name="Old Name", mapping=mapping)
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[existing],
    )
    _seed_lineup(tmp_path, lineup)

    entries = [_make_entry(tvgId="A.us", name="New Name", streamUrl="http://new")]
    _, result = m3u_service.import_m3u_entries("lu1", entries, base_dir=tmp_path)

    updated = result.updated[0]
    assert updated.name == "New Name"
    assert updated.mapping is not None
    assert updated.mapping.sdStationId == "10123"


def test_import_clears_missing_since_when_channel_reappears(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    previously_missing_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    existing = Channel(id="c1", tvgId="A.us", name="Old", missingSince=previously_missing_at)
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[existing],
    )
    _seed_lineup(tmp_path, lineup)

    entries = [_make_entry(tvgId="A.us", name="Old", streamUrl="http://x")]
    _, result = m3u_service.import_m3u_entries("lu1", entries, base_dir=tmp_path, now=now)

    assert result.updated[0].missingSince is None


def test_import_flags_new_disappearance(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    existing = Channel(id="c1", tvgId="A.us", name="A")
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[existing],
    )
    _seed_lineup(tmp_path, lineup)

    _, result = m3u_service.import_m3u_entries("lu1", [], base_dir=tmp_path, now=now)

    assert len(result.flaggedMissing) == 1
    assert result.flaggedMissing[0].id == "c1"
    assert result.flaggedMissing[0].missingSince == now
    assert result.added == []
    assert result.updated == []

    # Channel is not deleted.
    on_disk = load_lineups(base_dir=tmp_path)
    assert len(on_disk.lineups[0].channels) == 1


def test_import_does_not_bump_missing_since_on_repeated_absence(tmp_path):
    first_missing_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    existing = Channel(id="c1", tvgId="A.us", name="A", missingSince=first_missing_at)
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U,
        createdAt=first_missing_at, updatedAt=first_missing_at,
        channels=[existing],
    )
    _seed_lineup(tmp_path, lineup)

    later = datetime(2026, 2, 1, tzinfo=timezone.utc)
    _, result = m3u_service.import_m3u_entries("lu1", [], base_dir=tmp_path, now=later)

    assert len(result.flaggedMissing) == 1
    # Timestamp unchanged, not bumped to `later`.
    assert result.flaggedMissing[0].missingSince == first_missing_at


def test_import_persists_group_from_group_title(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[],
    )
    _seed_lineup(tmp_path, lineup)

    entries = [
        _make_entry(tvgId="A.us", name="A", groupTitle="Local", streamUrl="http://a")
    ]
    _, result = m3u_service.import_m3u_entries("lu1", entries, base_dir=tmp_path)

    assert result.added[0].group == "Local"


def test_import_adds_unmatched_new_entry(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[],
    )
    _seed_lineup(tmp_path, lineup)

    entries = [_make_entry(tvgId="NEW.us", name="Brand New", streamUrl="http://new")]
    _, result = m3u_service.import_m3u_entries("lu1", entries, base_dir=tmp_path)

    assert len(result.added) == 1
    assert result.added[0].tvgId == "NEW.us"
    assert result.added[0].name == "Brand New"


def test_import_rejects_blank_display_name_entry_gracefully():
    """Entries always have a non-blank `name` by construction in
    `parse_m3u`, but `M3UEntry.name` itself isn't constrained — guard
    against a hypothetical blank name being rejected cleanly rather than
    corrupting storage.
    """
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[],
    )
    from app.services.m3u import _merge_entries

    entry = _make_entry(name="   ", streamUrl="http://x")
    with pytest.raises(ValidationError):
        _merge_entries(lineup, [entry], now)


def test_import_raises_not_found_for_missing_lineup(tmp_path):
    save_lineups(LineupsFile(), base_dir=tmp_path)
    with pytest.raises(NotFoundError):
        m3u_service.import_m3u_entries("does-not-exist", [], base_dir=tmp_path)


def test_unidentified_entry_count_is_zero_when_every_entry_has_an_identifier(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[],
    )
    _seed_lineup(tmp_path, lineup)

    entries = [
        _make_entry(tvgId="A.us", name="A", streamUrl="http://a"),
        _make_entry(tvgId=None, name="B", number="2.1", streamUrl="http://b"),
    ]
    _, result = m3u_service.import_m3u_entries("lu1", entries, base_dir=tmp_path)

    assert result.unidentifiedEntryCount == 0


def test_unidentified_entry_count_reports_entries_with_neither_tvg_id_nor_number(
    tmp_path,
):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[],
    )
    _seed_lineup(tmp_path, lineup)

    entries = [
        _make_entry(tvgId="A.us", name="A", streamUrl="http://a"),
        _make_entry(tvgId=None, name="No Identifier 1", streamUrl="http://n1"),
        _make_entry(tvgId=None, name="No Identifier 2", streamUrl="http://n2"),
        _make_entry(tvgId=None, name="C", number="3.1", streamUrl="http://c"),
    ]
    _, result = m3u_service.import_m3u_entries("lu1", entries, base_dir=tmp_path)

    # Both fully-unidentified entries counted, regardless of whether they
    # matched an existing channel or were added as new ones.
    assert result.unidentifiedEntryCount == 2
    assert len(result.added) == 4


def test_unidentified_entry_without_any_identifier_duplicates_on_every_reimport(
    tmp_path,
):
    """Documents the explicitly-accepted limitation (product decision,
    option B): an entry with neither `tvgId` nor `number` has no stable
    identity signal, so it is always treated as brand-new on every import —
    growing the lineup by one duplicate channel per re-import of the same
    file, and flagging the previously-created copy as missing as a side
    effect. This test is a regression guard that the behavior itself is
    unchanged by `unidentifiedEntryCount`'s addition (a purely descriptive,
    additive field) — not a request to fix it.
    """
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lineup = Lineup(
        id="lu1", name="L", source=LineupSource.M3U, createdAt=now, updatedAt=now,
        channels=[],
    )
    _seed_lineup(tmp_path, lineup)

    def make_entries():
        return [_make_entry(tvgId=None, name="Mystery Channel", streamUrl="http://x")]

    _, result1 = m3u_service.import_m3u_entries("lu1", make_entries(), base_dir=tmp_path, now=now)
    assert result1.unidentifiedEntryCount == 1
    assert len(result1.added) == 1
    assert result1.flaggedMissing == []

    later = datetime(2026, 1, 2, tzinfo=timezone.utc)
    _, result2 = m3u_service.import_m3u_entries(
        "lu1", make_entries(), base_dir=tmp_path, now=later
    )
    assert result2.unidentifiedEntryCount == 1
    # No stable identity -> a second, duplicate channel is created...
    assert len(result2.added) == 1
    # ...and the first import's channel, unmatched this time, is flagged
    # missing rather than being matched/updated or deleted.
    assert len(result2.flaggedMissing) == 1

    on_disk = load_lineups(base_dir=tmp_path)
    assert len(on_disk.lineups[0].channels) == 2


def test_reimport_hdhomerun_channel_id_sample_is_idempotent(tmp_path):
    """Regression for Andrew's actual checkpoint-19 bug: before recognizing
    `channel-id`/`channel-number`, every entry in his real HDHomeRun export
    parsed with `tvgId=None`/`number=None`, so re-importing the identical
    file duplicated all 88 of his channels (2, in this reduced sample) on
    every re-import. Importing the same real-sample-style file twice must
    now converge: the second import updates the same two channels in place
    (no `added`, no `flaggedMissing`), and the lineup still has exactly two
    channels afterward.
    """
    lineup, first_result = m3u_service.create_lineup_from_m3u(
        "HDHomeRun Tuner",
        m3u_service.parse_m3u(HDHOMERUN_CHANNEL_ID_M3U),
        base_dir=tmp_path,
    )
    assert len(first_result.added) == 2
    assert first_result.unidentifiedEntryCount == 0

    _, second_result = m3u_service.import_m3u_entries(
        lineup.id,
        m3u_service.parse_m3u(HDHOMERUN_CHANNEL_ID_M3U),
        base_dir=tmp_path,
    )

    assert second_result.added == []
    assert second_result.flaggedMissing == []
    assert len(second_result.updated) == 2
    assert {c.tvgId for c in second_result.updated} == {"2.2", "4.1"}

    on_disk = load_lineups(base_dir=tmp_path)
    assert len(on_disk.lineups[0].channels) == 2


def test_import_rejects_non_m3u_sourced_lineup(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lineup = Lineup(
        id="lu1", name="Manual Lineup", source=LineupSource.MANUAL,
        createdAt=now, updatedAt=now, channels=[],
    )
    _seed_lineup(tmp_path, lineup)

    with pytest.raises(ValidationError):
        m3u_service.import_m3u_entries("lu1", [], base_dir=tmp_path)
