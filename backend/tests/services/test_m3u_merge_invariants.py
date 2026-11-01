"""Regression + property tests for `app.services.m3u._merge_entries`.

These target the four findings from the latest peer review (see the task
that produced this file for the exact repro descriptions) plus a
randomized-order property test that exercises the same scenarios (and a
couple of variants) across every possible entry ordering, asserting the
set of channel identities/mappings never depends on file order — only the
explicitly-documented tie-break ambiguity (whose *data* wins when two
same-rank entries compete) may vary.

See the `INV-*` invariants block directly above `_merge_entries` in
`app.services.m3u` for the precise contract these tests check against.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timezone

from app.models.lineup import Channel, ChannelMapping, Lineup, LineupSource
from app.models.m3u import M3UEntry
from app.services.m3u import _merge_entries

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _entry(**kwargs) -> M3UEntry:
    defaults = dict(
        tvgId=None, name="Channel", logoUrl=None, number=None, groupTitle=None,
        streamUrl="http://x",
    )
    defaults.update(kwargs)
    return M3UEntry(**defaults)


def _mapping(station_id: str) -> ChannelMapping:
    return ChannelMapping(sdStationId=station_id, sdLineupId="USA-OTA", confirmed=True)


def _lineup(*channels: Channel) -> Lineup:
    return Lineup(
        id="lu1", name="L", source=LineupSource.M3U,
        createdAt=NOW, updatedAt=NOW, channels=list(channels),
    )


# ---------------------------------------------------------------------------
# Finding 1 (HIGH, crash): duplicate tvgId entries both resolving to the same
# pre-existing channel must not crash the `list.index(existing)` lookup.
# ---------------------------------------------------------------------------


def test_finding1_duplicate_tvg_id_entries_do_not_crash():
    channel_a = Channel(id="a", tvgId="A.us", name="A", number="1.1", mapping=_mapping("ST_A"))
    lineup = _lineup(channel_a)

    entries = [
        _entry(tvgId="A.us", number="1.1", name="A HD", streamUrl="http://a-hd"),
        _entry(tvgId="A.us", number="1.1", name="A SD", streamUrl="http://a-sd"),
    ]

    # Must not raise ValueError("... is not in list").
    result = _merge_entries(lineup, entries, NOW)

    assert len(lineup.channels) == 1
    channel = lineup.channels[0]
    assert channel.id == "a"
    assert channel.mapping is not None
    assert channel.mapping.sdStationId == "ST_A"
    # Last duplicate entry's data wins (documented, order-dependent-within-
    # a-single-channel behavior — not in scope of INV-DETERMINISTIC-
    # COMPETITION, which only governs competition across *different*
    # pre-existing channels).
    assert channel.name == "A SD"
    assert len(result.updated) == 2
    assert result.flaggedMissing == []


# ---------------------------------------------------------------------------
# Finding 2 (HIGH): pass-2 number-fallback competition between a tvgId-less
# entry and a tvgId-bearing-but-unmatched entry for the same pre-existing
# channel's number must resolve deterministically (tvgId-less wins),
# regardless of file order.
# ---------------------------------------------------------------------------


def test_finding2_two_entry_competition_both_orders():
    for order_name, entries in (
        (
            "B-then-A",
            [
                _entry(tvgId="B.us", number="1.1", name="B", streamUrl="http://b"),
                _entry(tvgId=None, number="1.1", name="A", streamUrl="http://a"),
            ],
        ),
        (
            "A-then-B",
            [
                _entry(tvgId=None, number="1.1", name="A", streamUrl="http://a"),
                _entry(tvgId="B.us", number="1.1", name="B", streamUrl="http://b"),
            ],
        ),
    ):
        channel_a = Channel(
            id="a", tvgId=None, name="A", number="1.1", mapping=_mapping("ST_A")
        )
        lineup = _lineup(channel_a)

        result = _merge_entries(lineup, entries, NOW)

        assert len(lineup.channels) == 2, order_name
        by_id = {c.id: c for c in lineup.channels}
        assert by_id["a"].mapping is not None, order_name
        assert by_id["a"].mapping.sdStationId == "ST_A", order_name
        assert by_id["a"].number == "1.1", order_name

        new_channels = [c for c in lineup.channels if c.id != "a"]
        assert len(new_channels) == 1, order_name
        assert new_channels[0].tvgId == "B.us", order_name
        assert new_channels[0].mapping is None, order_name

        assert len(result.updated) == 1, order_name
        assert result.updated[0].id == "a", order_name
        assert len(result.added) == 1, order_name
        assert result.flaggedMissing == [], order_name


def test_finding2_three_entry_variant_with_second_existing_channel():
    """Same competition as above for channel A's number, plus a second,
    unrelated pre-existing channel C that must be completely unaffected
    regardless of where its own (unambiguous, single-candidate) entry
    falls in file order relative to the A/B competition.
    """
    base_entries = {
        "B": _entry(tvgId="B.us", number="1.1", name="B", streamUrl="http://b"),
        "A": _entry(tvgId=None, number="1.1", name="A", streamUrl="http://a"),
        "C": _entry(tvgId=None, number="2.2", name="C", streamUrl="http://c"),
    }

    for permutation in itertools.permutations(["B", "A", "C"]):
        channel_a = Channel(
            id="a", tvgId=None, name="A", number="1.1", mapping=_mapping("ST_A")
        )
        channel_c = Channel(
            id="c", tvgId=None, name="C", number="2.2", mapping=_mapping("ST_C")
        )
        lineup = _lineup(channel_a, channel_c)
        entries = [base_entries[key] for key in permutation]

        result = _merge_entries(lineup, entries, NOW)
        order_name = "-".join(permutation)

        assert len(lineup.channels) == 3, order_name
        by_id = {c.id: c for c in lineup.channels}
        assert by_id["a"].mapping.sdStationId == "ST_A", order_name
        assert by_id["c"].mapping.sdStationId == "ST_C", order_name

        new_channels = [c for c in lineup.channels if c.id not in ("a", "c")]
        assert len(new_channels) == 1, order_name
        assert new_channels[0].tvgId == "B.us", order_name
        assert new_channels[0].mapping is None, order_name

        assert len(result.added) == 1, order_name
        assert result.flaggedMissing == [], order_name


# ---------------------------------------------------------------------------
# Finding 3 (MEDIUM): repeated identical re-imports must converge, not grow
# unboundedly or flip a legitimately-matched channel to missing.
# ---------------------------------------------------------------------------


def test_finding3_repeated_identical_reimport_is_idempotent():
    channel_a = Channel(id="a", tvgId=None, name="A", number="1.1", mapping=_mapping("ST_A"))
    lineup = _lineup(channel_a)

    def make_entries():
        return [
            _entry(tvgId=None, number="1.1", name="A1", streamUrl="http://a1"),
            _entry(tvgId=None, number="1.1", name="A2", streamUrl="http://a2"),
        ]

    # First re-import: necessarily grows by one (two number-only entries,
    # one pre-existing slot -> one genuinely new channel for the loser).
    result1 = _merge_entries(lineup, make_entries(), NOW)
    assert len(lineup.channels) == 2
    assert len(result1.added) == 1
    assert len(result1.updated) == 1
    assert result1.flaggedMissing == []
    assert lineup.channels[0].id == "a"
    assert lineup.channels[0].mapping.sdStationId == "ST_A"

    stable_channel_count = len(lineup.channels)
    stable_ids = {c.id for c in lineup.channels}

    # Further identical re-imports must be stable: no growth, no newly
    # missing channel, same set of channel ids, mapping intact.
    for _ in range(3):
        result_n = _merge_entries(lineup, make_entries(), NOW)
        assert len(lineup.channels) == stable_channel_count
        assert {c.id for c in lineup.channels} == stable_ids
        assert result_n.added == []
        assert result_n.flaggedMissing == []
        by_id = {c.id: c for c in lineup.channels}
        assert by_id["a"].mapping is not None
        assert by_id["a"].mapping.sdStationId == "ST_A"


# ---------------------------------------------------------------------------
# Finding 4 (MEDIUM): two brand-new entries sharing a number but carrying
# different, non-null tvgIds must become two separate channels, not merge.
# ---------------------------------------------------------------------------


def test_finding4_new_channels_with_different_tvg_ids_stay_separate():
    lineup = _lineup()
    entries = [
        _entry(tvgId="X.us", number="5", name="X", streamUrl="http://x"),
        _entry(tvgId="W.us", number="5", name="W", streamUrl="http://w"),
    ]

    result = _merge_entries(lineup, entries, NOW)

    assert len(result.added) == 2
    tvg_ids = {c.tvgId for c in result.added}
    assert tvg_ids == {"X.us", "W.us"}
    assert len(lineup.channels) == 2


# ---------------------------------------------------------------------------
# Randomized-order property tests.
#
# For each scenario, run `_merge_entries` under every permutation of the
# entries list and assert the *set* of outcomes that matters — which
# pre-existing channels keep which mapping, how many channels end up
# existing in total, and that nothing crashes — is identical across every
# ordering. Per-entry "whose text data wins a tie" is allowed to vary (the
# documented INV-DETERMINISTIC-COMPETITION/duplicate-tvgId ambiguity) and
# is deliberately not asserted here.
# ---------------------------------------------------------------------------


def _channel_signature(
    lineup: Lineup, stable_ids: frozenset[str]
) -> frozenset[tuple[str, str | None]]:
    """A permutation-independent summary of the *pre-existing* channels'
    state: for each channel id in `stable_ids` (ids fixed by the test
    fixture, unlike freshly created channels' random uuids), its
    mapping's station id (or `None`). Restricted to `stable_ids` because
    newly created channels get a fresh random id on every run — only
    their *count*/`tvgId`s (asserted separately) are meaningful to
    compare across permutations, not their generated ids.
    """
    return frozenset(
        (channel.id, channel.mapping.sdStationId if channel.mapping else None)
        for channel in lineup.channels
        if channel.id in stable_ids
    )


def test_property_pass2_two_entry_competition_order_independent():
    entries_by_key = {
        "B": _entry(tvgId="B.us", number="1.1", name="B", streamUrl="http://b"),
        "A": _entry(tvgId=None, number="1.1", name="A", streamUrl="http://a"),
    }

    outcomes = []
    for permutation in itertools.permutations(entries_by_key.keys()):
        channel_a = Channel(
            id="a", tvgId=None, name="A", number="1.1", mapping=_mapping("ST_A")
        )
        lineup = _lineup(channel_a)
        entries = [entries_by_key[key] for key in permutation]

        result = _merge_entries(lineup, entries, NOW)  # must not raise

        new_channel_tvg_ids = sorted(
            c.tvgId for c in lineup.channels if c.id != "a"
        )
        outcomes.append(
            (
                len(lineup.channels),
                _channel_signature(lineup, frozenset({"a"})),
                tuple(new_channel_tvg_ids),
                len(result.flaggedMissing),
            )
        )

    assert len(set(outcomes)) == 1, outcomes


def test_property_pass2_three_entry_two_existing_channels_order_independent():
    entries_by_key = {
        "B": _entry(tvgId="B.us", number="1.1", name="B", streamUrl="http://b"),
        "A": _entry(tvgId=None, number="1.1", name="A", streamUrl="http://a"),
        "C": _entry(tvgId=None, number="2.2", name="C", streamUrl="http://c"),
    }

    outcomes = []
    for permutation in itertools.permutations(entries_by_key.keys()):
        channel_a = Channel(
            id="a", tvgId=None, name="A", number="1.1", mapping=_mapping("ST_A")
        )
        channel_c = Channel(
            id="c", tvgId=None, name="C", number="2.2", mapping=_mapping("ST_C")
        )
        lineup = _lineup(channel_a, channel_c)
        entries = [entries_by_key[key] for key in permutation]

        result = _merge_entries(lineup, entries, NOW)

        new_channel_tvg_ids = sorted(
            c.tvgId for c in lineup.channels if c.id not in ("a", "c")
        )
        outcomes.append(
            (
                len(lineup.channels),
                _channel_signature(lineup, frozenset({"a", "c"})),
                tuple(new_channel_tvg_ids),
                len(result.flaggedMissing),
            )
        )

    assert len(set(outcomes)) == 1, outcomes


def test_property_duplicate_tvg_id_entries_order_independent():
    """Finding 1's crash scenario, run under every ordering of three
    entries (two duplicates for the pre-existing channel, plus one
    unrelated new entry), asserting no crash and a stable outcome shape
    (channel count, which channel keeps the mapping, how many channels
    are newly added) across every order.
    """
    entries_by_key = {
        "A_HD": _entry(tvgId="A.us", number="1.1", name="A HD", streamUrl="http://a-hd"),
        "A_SD": _entry(tvgId="A.us", number="1.1", name="A SD", streamUrl="http://a-sd"),
        "NEW": _entry(tvgId="N.us", number="9.9", name="New", streamUrl="http://n"),
    }

    outcomes = []
    for permutation in itertools.permutations(entries_by_key.keys()):
        channel_a = Channel(
            id="a", tvgId="A.us", name="A", number="1.1", mapping=_mapping("ST_A")
        )
        lineup = _lineup(channel_a)
        entries = [entries_by_key[key] for key in permutation]

        result = _merge_entries(lineup, entries, NOW)  # must not raise

        outcomes.append(
            (
                len(lineup.channels),
                _channel_signature(lineup, frozenset({"a"})),
                len(result.added),
                len(result.flaggedMissing),
            )
        )

    assert len(set(outcomes)) == 1, outcomes


def test_property_new_channel_tvg_id_conflict_order_independent():
    """Finding 4's scenario (two brand-new entries sharing a number but
    carrying different tvgIds) must stay as two separate channels
    regardless of which entry is processed first.
    """
    entries_by_key = {
        "X": _entry(tvgId="X.us", number="5", name="X", streamUrl="http://x"),
        "W": _entry(tvgId="W.us", number="5", name="W", streamUrl="http://w"),
    }

    outcomes = []
    for permutation in itertools.permutations(entries_by_key.keys()):
        lineup = _lineup()
        entries = [entries_by_key[key] for key in permutation]

        result = _merge_entries(lineup, entries, NOW)

        outcomes.append(
            (len(result.added), tuple(sorted(c.tvgId for c in lineup.channels)))
        )

    assert len(set(outcomes)) == 1, outcomes
    # And every outcome must show two separate channels, never a collapse.
    for added_count, tvg_ids in outcomes:
        assert added_count == 2
        assert tvg_ids == ("W.us", "X.us")
