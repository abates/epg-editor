"""Tests for `app.storage.lineups`: atomic round-trip + fresh-install default."""

from datetime import datetime, timezone

from app.models.lineup import Channel, ChannelMapping, Lineup, LineupSource, LineupsFile
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
                            confirmed=True,
                            confirmedAt=now,
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
