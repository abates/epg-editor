"""Cache for SchedulesDirect API responses under `/data/cache/sd/`.

Fully regenerable from SD (per docs/data-model.md) — safe to delete at any
time. Organized as one small file per cached entity (one SD lineup's
stations, one station-day's schedule, one program) rather than a single
blob, so a single station/lineup/program can be invalidated/refreshed
independently, per docs/data-model.md's explicit requirement.

Layout under `cache/sd/`::

    stations/<sdLineupId>.json          -> CachedLineupStations
    schedules/<stationId>/<date>.json   -> CachedStationSchedule
    programs/<programId>.json           -> CachedProgram

`sd_client/` never writes here directly (see CLAUDE.md: storage/ is the only
module touching the filesystem) — callers in `services/` fetch via
`sd_client` and persist via this module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.models.sd import (
    CachedLineupStations,
    CachedProgram,
    CachedStationSchedule,
    SdLineupStationsResponse,
    SdProgram,
    SdStationSchedule,
)
from app.storage._atomic import atomic_write_text
from app.storage._safe import safe_segment as _safe_segment
from app.storage.paths import CACHE_DIRNAME, get_data_dir

SD_CACHE_DIRNAME = "sd"
STATIONS_DIRNAME = "stations"
SCHEDULES_DIRNAME = "schedules"
PROGRAMS_DIRNAME = "programs"


def _sd_cache_dir(base_dir: Path | None = None) -> Path:
    base = base_dir if base_dir is not None else get_data_dir()
    return base / CACHE_DIRNAME / SD_CACHE_DIRNAME


# --- Lineup stations ---------------------------------------------------------


def _lineup_stations_path(sd_lineup_id: str, base_dir: Path | None = None) -> Path:
    return (
        _sd_cache_dir(base_dir) / STATIONS_DIRNAME / f"{_safe_segment(sd_lineup_id)}.json"
    )


def save_lineup_stations(
    sd_lineup_id: str,
    data: SdLineupStationsResponse,
    *,
    fetched_at: datetime | None = None,
    base_dir: Path | None = None,
) -> CachedLineupStations:
    """Cache a SD lineup's station roster. Returns the cache entry written."""
    entry = CachedLineupStations(
        fetchedAt=fetched_at or datetime.now(timezone.utc),
        sdLineupId=sd_lineup_id,
        data=data,
    )
    atomic_write_text(
        _lineup_stations_path(sd_lineup_id, base_dir), entry.model_dump_json(indent=2)
    )
    return entry


def load_lineup_stations(
    sd_lineup_id: str, base_dir: Path | None = None
) -> CachedLineupStations | None:
    """Load a cached SD lineup's stations, or `None` if not cached."""
    path = _lineup_stations_path(sd_lineup_id, base_dir)
    if not path.exists():
        return None
    return CachedLineupStations.model_validate_json(path.read_text(encoding="utf-8"))


def invalidate_lineup_stations(sd_lineup_id: str, base_dir: Path | None = None) -> None:
    """Drop the cached stations for one SD lineup, if present."""
    path = _lineup_stations_path(sd_lineup_id, base_dir)
    path.unlink(missing_ok=True)


# --- Station schedules --------------------------------------------------------


def _station_schedule_path(
    station_id: str, date: str, base_dir: Path | None = None
) -> Path:
    return (
        _sd_cache_dir(base_dir)
        / SCHEDULES_DIRNAME
        / _safe_segment(station_id)
        / f"{_safe_segment(date)}.json"
    )


def save_station_schedule(
    station_id: str,
    date: str,
    data: SdStationSchedule,
    *,
    fetched_at: datetime | None = None,
    base_dir: Path | None = None,
) -> CachedStationSchedule:
    """Cache one station's one-day schedule (keyed by station + date)."""
    entry = CachedStationSchedule(
        fetchedAt=fetched_at or datetime.now(timezone.utc),
        stationId=station_id,
        date=date,
        data=data,
    )
    atomic_write_text(
        _station_schedule_path(station_id, date, base_dir),
        entry.model_dump_json(indent=2),
    )
    return entry


def load_station_schedule(
    station_id: str, date: str, base_dir: Path | None = None
) -> CachedStationSchedule | None:
    """Load a cached station-day schedule, or `None` if not cached."""
    path = _station_schedule_path(station_id, date, base_dir)
    if not path.exists():
        return None
    return CachedStationSchedule.model_validate_json(path.read_text(encoding="utf-8"))


def load_station_schedules(
    station_id: str, dates: list[str], base_dir: Path | None = None
) -> list[CachedStationSchedule]:
    """Load whichever of the given station-days are cached (skips misses)."""
    results = []
    for date in dates:
        entry = load_station_schedule(station_id, date, base_dir)
        if entry is not None:
            results.append(entry)
    return results


def invalidate_station_schedule(
    station_id: str, date: str | None = None, base_dir: Path | None = None
) -> None:
    """Drop a cached station-day schedule.

    If `date` is omitted, drops every cached day for that station.
    """
    if date is not None:
        _station_schedule_path(station_id, date, base_dir).unlink(missing_ok=True)
        return
    station_dir = (
        _sd_cache_dir(base_dir) / SCHEDULES_DIRNAME / _safe_segment(station_id)
    )
    if station_dir.is_dir():
        for child in station_dir.glob("*.json"):
            child.unlink(missing_ok=True)


# --- Programs -----------------------------------------------------------------


def _program_path(program_id: str, base_dir: Path | None = None) -> Path:
    return _sd_cache_dir(base_dir) / PROGRAMS_DIRNAME / f"{_safe_segment(program_id)}.json"


def save_program(
    program_id: str,
    data: SdProgram,
    *,
    fetched_at: datetime | None = None,
    base_dir: Path | None = None,
) -> CachedProgram:
    """Cache one program's metadata."""
    entry = CachedProgram(fetchedAt=fetched_at or datetime.now(timezone.utc), data=data)
    atomic_write_text(_program_path(program_id, base_dir), entry.model_dump_json(indent=2))
    return entry


def load_program(program_id: str, base_dir: Path | None = None) -> CachedProgram | None:
    """Load a cached program's metadata, or `None` if not cached."""
    path = _program_path(program_id, base_dir)
    if not path.exists():
        return None
    return CachedProgram.model_validate_json(path.read_text(encoding="utf-8"))


def load_programs(
    program_ids: list[str], base_dir: Path | None = None
) -> dict[str, CachedProgram]:
    """Load whichever of the given program IDs are cached (skips misses)."""
    results: dict[str, CachedProgram] = {}
    for program_id in program_ids:
        entry = load_program(program_id, base_dir)
        if entry is not None:
            results[program_id] = entry
    return results


def invalidate_program(program_id: str, base_dir: Path | None = None) -> None:
    """Drop one cached program's metadata, if present."""
    _program_path(program_id, base_dir).unlink(missing_ok=True)
