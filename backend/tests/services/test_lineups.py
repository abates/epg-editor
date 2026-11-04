"""Tests for `app.services.lineups`.

Covers the Phase 1 peer-review findings:
- #1 (HIGH): concurrent mutations against the same lineup must not lose
  updates (the original bug: 40 concurrent `add_channel` calls against one
  lineup only kept 7 of 41 channels because of an unlocked
  load-mutate-save race).
- #3: explicitly clearing an optional channel field via `null` must
  actually clear it, distinct from omitting the field.
- #4: removing a `sdLineupId` that a channel's mapping still depends on
  must be rejected, not silently orphan the mapping.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.models.lineup import ChannelMapping
from app.services import lineups as lineups_service
from app.storage.lineups import update_lineups


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path))


# --- #1: concurrent-mutation race -------------------------------------------


def test_concurrent_add_channel_does_not_lose_updates():
    lineup = lineups_service.create_lineup("Living Room Antenna")
    concurrency = 40

    def add_one(index: int) -> None:
        lineups_service.add_channel(lineup.id, name=f"Channel {index}")

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(add_one, range(concurrency)))

    reloaded = lineups_service.get_lineup(lineup.id)
    assert len(reloaded.channels) == concurrency
    assert len({channel.name for channel in reloaded.channels}) == concurrency


def test_concurrent_mixed_mutations_do_not_lose_updates():
    """Same race, but with a mix of mutation types against one lineup."""
    lineup = lineups_service.create_lineup("Living Room Antenna")
    # Seed some channels to update/remove concurrently with new adds.
    seeded = [
        lineups_service.add_channel(lineup.id, name=f"Seed {i}") for i in range(10)
    ]

    def add_one(index: int) -> None:
        lineups_service.add_channel(lineup.id, name=f"New {index}")

    def rename_one(channel) -> None:
        lineups_service.update_channel(lineup.id, channel.id, {"name": "Renamed"})

    with ThreadPoolExecutor(max_workers=40) as pool:
        futures = [pool.submit(add_one, i) for i in range(30)]
        futures += [pool.submit(rename_one, channel) for channel in seeded]
        for future in futures:
            future.result()

    reloaded = lineups_service.get_lineup(lineup.id)
    # 10 seeded (renamed in place, not removed) + 30 newly added.
    assert len(reloaded.channels) == 40
    assert sum(1 for c in reloaded.channels if c.name == "Renamed") == 10


# --- #3: explicit null clears a field; omission leaves it unchanged --------


def test_update_channel_omitted_field_is_unchanged():
    lineup = lineups_service.create_lineup("Lineup")
    channel = lineups_service.add_channel(
        lineup.id, name="KGO-TV", logo_url="https://example.test/kgo.png"
    )

    updated = lineups_service.update_channel(lineup.id, channel.id, {"name": "KGO HD"})

    assert updated.name == "KGO HD"
    assert updated.logoUrl == "https://example.test/kgo.png"


def test_update_channel_explicit_null_clears_field():
    lineup = lineups_service.create_lineup("Lineup")
    channel = lineups_service.add_channel(
        lineup.id, name="KGO-TV", logo_url="https://example.test/kgo.png"
    )

    updated = lineups_service.update_channel(lineup.id, channel.id, {"logoUrl": None})

    assert updated.logoUrl is None
    assert updated.name == "KGO-TV"  # untouched, since it was omitted


def test_update_channel_rejects_unknown_field():
    lineup = lineups_service.create_lineup("Lineup")
    channel = lineups_service.add_channel(lineup.id, name="KGO-TV")

    with pytest.raises(ValueError):
        lineups_service.update_channel(lineup.id, channel.id, {"bogus": "value"})


# --- regression: explicit null for a required field must not corrupt disk -


def test_update_channel_rejects_null_for_required_field(tmp_path):
    """`name` is required/non-nullable on `Channel`.

    Sending an explicit `null` for it must be rejected *before* anything
    is written, not applied via raw `setattr` and persisted — a prior
    regression let this corrupt `config/lineups.json` with `name: null`,
    which then made every subsequent `load_lineups()` raise a
    `pydantic.ValidationError`, 500ing the entire API.
    """
    lineup = lineups_service.create_lineup("Lineup")
    channel = lineups_service.add_channel(lineup.id, name="KGO-TV")

    with pytest.raises(lineups_service.ValidationError):
        lineups_service.update_channel(lineup.id, channel.id, {"name": None})

    # Nothing was persisted: the channel's name survives unchanged, and the
    # file is still a valid, loadable `LineupsFile`.
    reloaded = lineups_service.get_lineup(lineup.id)
    assert reloaded.channels[0].name == "KGO-TV"


def test_update_channel_still_allows_clearing_nullable_field():
    """Sanity check: the fix above must not regress clearing e.g. `logoUrl`."""
    lineup = lineups_service.create_lineup("Lineup")
    channel = lineups_service.add_channel(
        lineup.id, name="KGO-TV", logo_url="https://example.test/kgo.png"
    )

    updated = lineups_service.update_channel(lineup.id, channel.id, {"logoUrl": None})

    assert updated.logoUrl is None
    assert updated.name == "KGO-TV"


# --- empty-name regression: `Channel.name` must be non-empty after trim ---


def test_add_channel_rejects_empty_name():
    lineup = lineups_service.create_lineup("Lineup")

    with pytest.raises(lineups_service.ValidationError):
        lineups_service.add_channel(lineup.id, name="")

    reloaded = lineups_service.get_lineup(lineup.id)
    assert reloaded.channels == []


def test_add_channel_rejects_whitespace_only_name():
    lineup = lineups_service.create_lineup("Lineup")

    with pytest.raises(lineups_service.ValidationError):
        lineups_service.add_channel(lineup.id, name="   ")

    reloaded = lineups_service.get_lineup(lineup.id)
    assert reloaded.channels == []


def test_add_channel_trims_surrounding_whitespace_from_name():
    lineup = lineups_service.create_lineup("Lineup")

    channel = lineups_service.add_channel(lineup.id, name="  KGO-TV  ")

    assert channel.name == "KGO-TV"


def test_update_channel_rejects_empty_name_without_corrupting_disk():
    lineup = lineups_service.create_lineup("Lineup")
    channel = lineups_service.add_channel(lineup.id, name="KGO-TV")

    with pytest.raises(lineups_service.ValidationError):
        lineups_service.update_channel(lineup.id, channel.id, {"name": ""})

    reloaded = lineups_service.get_lineup(lineup.id)
    assert reloaded.channels[0].name == "KGO-TV"


def test_update_channel_rejects_whitespace_only_name_without_corrupting_disk():
    lineup = lineups_service.create_lineup("Lineup")
    channel = lineups_service.add_channel(lineup.id, name="KGO-TV")

    with pytest.raises(lineups_service.ValidationError):
        lineups_service.update_channel(lineup.id, channel.id, {"name": "   "})

    reloaded = lineups_service.get_lineup(lineup.id)
    assert reloaded.channels[0].name == "KGO-TV"


# --- delete_lineup (checkpoint 19 CRUD gap) ---------------------------------


def test_delete_lineup_removes_it():
    lineup = lineups_service.create_lineup("Lineup to delete")
    other = lineups_service.create_lineup("Other lineup")

    lineups_service.delete_lineup(lineup.id)

    remaining_ids = {l.id for l in lineups_service.list_lineups()}
    assert remaining_ids == {other.id}


def test_delete_lineup_raises_not_found_for_missing_lineup():
    with pytest.raises(lineups_service.NotFoundError):
        lineups_service.delete_lineup("does-not-exist")


def test_concurrent_delete_and_mutation_on_different_lineups_do_not_lose_updates():
    """`update_lineups`'s process-wide lock already structurally guarantees
    this; a brief smoke test is enough (see CLAUDE.md task notes) rather
    than a dedicated deep-dive, unlike the existing #1 concurrency tests
    above which guard a real historical bug.
    """
    target = lineups_service.create_lineup("Delete me")
    survivor = lineups_service.create_lineup("Survives")

    with ThreadPoolExecutor(max_workers=2) as pool:
        delete_future = pool.submit(lineups_service.delete_lineup, target.id)
        add_future = pool.submit(
            lineups_service.add_channel, survivor.id, name="Channel"
        )
        delete_future.result()
        add_future.result()

    remaining = lineups_service.list_lineups()
    assert {l.id for l in remaining} == {survivor.id}
    reloaded_survivor = lineups_service.get_lineup(survivor.id)
    assert len(reloaded_survivor.channels) == 1


# --- #4: can't remove a sdLineupId a mapped channel depends on -------------


def test_update_sd_lineup_ids_rejects_removal_when_mapped_channel_depends_on_it():
    lineup = lineups_service.create_lineup("Lineup")
    lineups_service.update_lineup_sd_lineup_ids(lineup.id, ["USA-OTA12345"])
    channel = lineups_service.add_channel(lineup.id, name="KGO-TV")
    lineups_service.set_channel_mapping(
        lineup.id,
        channel.id,
        sd_station_id="10123",
        sd_lineup_id="USA-OTA12345",
    )

    with pytest.raises(lineups_service.ValidationError):
        lineups_service.update_lineup_sd_lineup_ids(lineup.id, [])

    # Confirm nothing was persisted: the association and mapping both survive.
    reloaded = lineups_service.get_lineup(lineup.id)
    assert reloaded.sdLineupIds == ["USA-OTA12345"]
    assert reloaded.channels[0].mapping.sdLineupId == "USA-OTA12345"


def test_update_sd_lineup_ids_allows_removal_when_no_mapped_channel_depends_on_it():
    lineup = lineups_service.create_lineup("Lineup")
    lineups_service.update_lineup_sd_lineup_ids(
        lineup.id, ["USA-OTA12345", "USA-CABLE67890"]
    )
    channel = lineups_service.add_channel(lineup.id, name="KGO-TV")
    lineups_service.set_channel_mapping(
        lineup.id,
        channel.id,
        sd_station_id="10123",
        sd_lineup_id="USA-OTA12345",
    )

    # Removing the *unused* sdLineupId is fine.
    updated = lineups_service.update_lineup_sd_lineup_ids(lineup.id, ["USA-OTA12345"])

    assert updated.sdLineupIds == ["USA-OTA12345"]


def test_update_sd_lineup_ids_allows_removal_when_channel_has_no_mapping():
    lineup = lineups_service.create_lineup("Lineup")
    lineups_service.update_lineup_sd_lineup_ids(lineup.id, ["USA-OTA12345"])
    lineups_service.add_channel(lineup.id, name="KGO-TV")

    # A channel with no mapping at all doesn't block removal.
    updated = lineups_service.update_lineup_sd_lineup_ids(lineup.id, [])

    assert updated.sdLineupIds == []


def test_update_sd_lineup_ids_rejects_removal_for_bug_state_mapping():
    """Backlog item 38's incidental bug fix: a mapping that has
    `sdLineupId` set is now protected from being silently orphaned
    regardless of the (now-removed) `confirmed` flag's old value — the old
    guard only checked `confirmed`, so a channel stuck in the "has a
    station, unconfirmed" bug state was previously *unprotected*. Simulate
    that state directly (bypassing `set_channel_mapping`, which always sets
    `sdLineupId`/`mappedAt` together now) to prove the guard itself is
    correct independent of how the mapping was produced.
    """
    lineup = lineups_service.create_lineup("Lineup")
    lineups_service.update_lineup_sd_lineup_ids(lineup.id, ["USA-OTA12345"])
    channel = lineups_service.add_channel(lineup.id, name="KGO-TV")

    def mutate(data):
        target_lineup = next(l for l in data.lineups if l.id == lineup.id)
        target_channel = next(c for c in target_lineup.channels if c.id == channel.id)
        target_channel.mapping = ChannelMapping(
            sdStationId="10123", sdLineupId="USA-OTA12345", mappedAt=None
        )

    update_lineups(mutate)

    with pytest.raises(lineups_service.ValidationError):
        lineups_service.update_lineup_sd_lineup_ids(lineup.id, [])
