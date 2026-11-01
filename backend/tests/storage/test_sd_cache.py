"""Tests for `app.storage.sd_cache`: round-trip + independent invalidation."""

from datetime import datetime, timezone

from app.models.sd import SdLineupStationsResponse, SdProgram, SdStation, SdStationSchedule
from app.storage import sd_cache


def test_lineup_stations_round_trip_and_cache_miss(tmp_path):
    assert sd_cache.load_lineup_stations("USA-OTA12345", base_dir=tmp_path) is None

    response = SdLineupStationsResponse(
        stations=[SdStation(stationID="10123", name="KGO-TV", callsign="KGO")]
    )
    sd_cache.save_lineup_stations("USA-OTA12345", response, base_dir=tmp_path)

    loaded = sd_cache.load_lineup_stations("USA-OTA12345", base_dir=tmp_path)
    assert loaded is not None
    assert loaded.sdLineupId == "USA-OTA12345"
    assert loaded.data == response
    assert loaded.fetchedAt is not None


def test_lineup_stations_invalidate_removes_only_that_lineup(tmp_path):
    response = SdLineupStationsResponse(stations=[])
    sd_cache.save_lineup_stations("lineup-a", response, base_dir=tmp_path)
    sd_cache.save_lineup_stations("lineup-b", response, base_dir=tmp_path)

    sd_cache.invalidate_lineup_stations("lineup-a", base_dir=tmp_path)

    assert sd_cache.load_lineup_stations("lineup-a", base_dir=tmp_path) is None
    assert sd_cache.load_lineup_stations("lineup-b", base_dir=tmp_path) is not None


def test_station_schedule_round_trip_per_day(tmp_path):
    schedule = SdStationSchedule(stationID="10123", programs=[])
    sd_cache.save_station_schedule("10123", "2026-10-29", schedule, base_dir=tmp_path)
    sd_cache.save_station_schedule("10123", "2026-10-30", schedule, base_dir=tmp_path)

    assert sd_cache.load_station_schedule("10123", "2026-10-29", base_dir=tmp_path).data == schedule
    assert sd_cache.load_station_schedule("10123", "2026-11-05", base_dir=tmp_path) is None

    loaded = sd_cache.load_station_schedules(
        "10123", ["2026-10-29", "2026-10-30", "2026-11-05"], base_dir=tmp_path
    )
    assert {entry.date for entry in loaded} == {"2026-10-29", "2026-10-30"}


def test_station_schedule_invalidate_single_day_vs_all_days(tmp_path):
    schedule = SdStationSchedule(stationID="10123", programs=[])
    sd_cache.save_station_schedule("10123", "2026-10-29", schedule, base_dir=tmp_path)
    sd_cache.save_station_schedule("10123", "2026-10-30", schedule, base_dir=tmp_path)

    sd_cache.invalidate_station_schedule("10123", "2026-10-29", base_dir=tmp_path)
    assert sd_cache.load_station_schedule("10123", "2026-10-29", base_dir=tmp_path) is None
    assert sd_cache.load_station_schedule("10123", "2026-10-30", base_dir=tmp_path) is not None

    sd_cache.invalidate_station_schedule("10123", base_dir=tmp_path)
    assert sd_cache.load_station_schedule("10123", "2026-10-30", base_dir=tmp_path) is None


def test_program_round_trip_and_batched_load(tmp_path):
    program = SdProgram(programID="EP012345670001", titles=[])
    sd_cache.save_program("EP012345670001", program, base_dir=tmp_path)

    loaded = sd_cache.load_programs(
        ["EP012345670001", "EP0000000000"], base_dir=tmp_path
    )
    assert set(loaded.keys()) == {"EP012345670001"}
    assert loaded["EP012345670001"].data == program

    sd_cache.invalidate_program("EP012345670001", base_dir=tmp_path)
    assert sd_cache.load_program("EP012345670001", base_dir=tmp_path) is None


def test_unsafe_cache_key_segment_cannot_escape_the_cache_directory(tmp_path):
    # Path separators get neutralized into a single safe filename component,
    # so a "../.." style ID can't be used to write/read outside the
    # stations/ cache directory.
    response = SdLineupStationsResponse(stations=[])
    sd_cache.save_lineup_stations("../../etc/passwd", response, base_dir=tmp_path)

    stations_dir = tmp_path / "cache" / "sd" / "stations"
    written = list(stations_dir.iterdir())

    assert len(written) == 1
    assert written[0].parent == stations_dir


def test_unsafe_cache_key_segment_that_is_exactly_dotdot_is_rejected(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        sd_cache.load_lineup_stations("..", base_dir=tmp_path)


def test_fetched_at_timestamps_are_timezone_aware(tmp_path):
    # Regression test: these used to be `datetime.now()` (naive), which
    # raises `TypeError` the moment anything compares them against an
    # aware `datetime` (e.g. Phase 5's TTL logic comparing against
    # `datetime.now(timezone.utc)`).
    response = SdLineupStationsResponse(stations=[])
    stations_entry = sd_cache.save_lineup_stations("USA-OTA12345", response, base_dir=tmp_path)
    assert stations_entry.fetchedAt.tzinfo is not None

    schedule = SdStationSchedule(stationID="10123", programs=[])
    schedule_entry = sd_cache.save_station_schedule(
        "10123", "2026-10-29", schedule, base_dir=tmp_path
    )
    assert schedule_entry.fetchedAt.tzinfo is not None

    program = SdProgram(programID="EP012345670001", titles=[])
    program_entry = sd_cache.save_program("EP012345670001", program, base_dir=tmp_path)
    assert program_entry.fetchedAt.tzinfo is not None

    # And comparing against another aware datetime must not raise.
    now = datetime.now(timezone.utc)
    assert stations_entry.fetchedAt <= now
    assert schedule_entry.fetchedAt <= now
    assert program_entry.fetchedAt <= now
