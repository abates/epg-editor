"""Tests for `app.storage.lineups`: atomic round-trip + fresh-install default."""

import json
from datetime import datetime, timezone

from app.models.lineup import Channel, ChannelMapping, Lineup, LineupSource, LineupsFile
from app.services.xmltv import mapped_channels
from app.storage.lineups import load_lineups, save_lineups


def test_load_lineups_returns_empty_default_when_file_missing(tmp_path):
    result = load_lineups(base_dir=tmp_path)

    assert result == LineupsFile(schemaVersion=1, lineups=[])


def test_save_then_load_round_trips_exactly(tmp_path):
    now = datetime(2026, 10, 29, 0, 0, 0, tzinfo=timezone.utc)
    data = LineupsFile(
        schemaVersion=1,
        lineups=[
            Lineup(
                id="living-room",
                name="Living Room Antenna",
                source=LineupSource.MANUAL,
                createdAt=now,
                updatedAt=now,
                sdLineupIds=["USA-OTA12345"],
                channels=[
                    Channel(
                        id="ch-7-1",
                        number="7.1",
                        name="KGO-TV",
                        mapping=ChannelMapping(
                            sdStationId="10123",
                            sdLineupId="USA-OTA12345",
                            mappedAt=now,
                        ),
                    )
                ],
            )
        ],
    )

    save_lineups(data, base_dir=tmp_path)
    loaded = load_lineups(base_dir=tmp_path)

    assert loaded == data


def test_save_lineups_writes_atomically_leaving_no_temp_file(tmp_path):
    save_lineups(LineupsFile(), base_dir=tmp_path)

    config_dir = tmp_path / "config"
    entries = list(config_dir.iterdir())

    assert entries == [config_dir / "lineups.json"]


def test_load_lineups_migrates_legacy_confirmed_fields(tmp_path):
    """Backlog item 38: loading real pre-refactor data (old `confirmed`/
    `confirmedAt` keys) must carry `confirmedAt` forward into `mappedAt`
    for a normal confirmed-true record, and must treat the "bug state"
    record (`sdStationId` set, `confirmed: false`, `confirmedAt: null` —
    the exact UI bug item 38 fixes) as mapped with `mappedAt = None` rather
    than crashing or losing data.

    Re-saving (via `update_lineups`-equivalent `save_lineups`) must produce
    clean new-schema JSON with no leftover `confirmed`/old-shape
    `confirmedAt` keys.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    raw = {
        "schemaVersion": 1,
        "lineups": [
            {
                "id": "living-room",
                "name": "Living Room Antenna",
                "source": "manual",
                "createdAt": "2026-10-29T00:00:00Z",
                "updatedAt": "2026-10-29T00:00:00Z",
                "sdLineupIds": ["USA-OTA12345"],
                "channels": [
                    {
                        "id": "ch-normal",
                        "number": "7.1",
                        "name": "KGO-TV",
                        "mapping": {
                            "sdStationId": "10123",
                            "sdLineupId": "USA-OTA12345",
                            "confirmed": True,
                            "confirmedAt": "2026-10-29T00:10:00Z",
                            "suggestions": [],
                        },
                    },
                    {
                        "id": "ch-bug-state",
                        "number": "9.1",
                        "name": "KQED-TV",
                        "mapping": {
                            "sdStationId": "10456",
                            "sdLineupId": "USA-OTA12345",
                            "confirmed": False,
                            "confirmedAt": None,
                            "suggestions": [],
                        },
                    },
                ],
            }
        ],
    }
    (config_dir / "lineups.json").write_text(json.dumps(raw), encoding="utf-8")

    loaded = load_lineups(base_dir=tmp_path)
    lineup = loaded.lineups[0]
    normal_channel = next(c for c in lineup.channels if c.id == "ch-normal")
    bug_state_channel = next(c for c in lineup.channels if c.id == "ch-bug-state")

    # Normal confirmed-true record: `confirmedAt` carried forward to `mappedAt`.
    assert normal_channel.mapping.mappedAt == datetime(
        2026, 10, 29, 0, 10, 0, tzinfo=timezone.utc
    )
    assert normal_channel.mapping.sdStationId == "10123"

    # Bug-state record: no original timestamp to recover, so `mappedAt`
    # stays `None` — but it's now treated as mapped since `sdStationId` is
    # set, which is the whole point of this refactor.
    assert bug_state_channel.mapping.mappedAt is None
    assert bug_state_channel.mapping.sdStationId == "10456"
    assert bug_state_channel.mapping.sdLineupId == "USA-OTA12345"

    # End-to-end: the bug-state channel must actually be included in
    # `mapped_channels()`'s output, since an invisibly-excluded mapped
    # channel is the actual user-visible bug this refactor fixes.
    assert bug_state_channel in mapped_channels(lineup)

    # Re-saving produces clean new-schema JSON: no leftover `confirmed` key
    # anywhere, and `mappedAt` (not `confirmedAt`) is what's persisted.
    save_lineups(loaded, base_dir=tmp_path)
    resaved_text = (config_dir / "lineups.json").read_text(encoding="utf-8")
    assert '"confirmed"' not in resaved_text
    assert '"confirmedAt"' not in resaved_text
    assert '"mappedAt"' in resaved_text


def test_save_lineups_overwrites_previous_contents(tmp_path):
    save_lineups(
        LineupsFile(
            lineups=[
                Lineup(
                    id="a",
                    name="A",
                    source=LineupSource.MANUAL,
                    createdAt=datetime.now(timezone.utc),
                    updatedAt=datetime.now(timezone.utc),
                )
            ]
        ),
        base_dir=tmp_path,
    )
    save_lineups(LineupsFile(), base_dir=tmp_path)

    assert load_lineups(base_dir=tmp_path) == LineupsFile()
