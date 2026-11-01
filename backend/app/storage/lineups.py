"""Load/save `/data/config/lineups.json`.

The only module that reads or writes the epg-editor config file. Writes are
atomic (temp file in the same directory + `os.replace`) so a crash mid-write
never leaves a partially-written file at the real path — per CLAUDE.md and
docs/data-model.md, this file must never be silently corrupted.

Atomicity of the *file* is not the same as atomicity of a *mutation*:
FastAPI runs sync route handlers in a threadpool, so two concurrent
requests that each do their own load -> mutate-in-memory -> save can race
and silently lose one of the updates (classic lost-update problem), even
though each individual `save_lineups` call is itself atomic. `update_lineups`
below closes that gap by holding a single process-wide lock across the
whole load-mutate-save cycle. A single `threading.Lock` is sufficient here
per CLAUDE.md: no database, and no multi-process deployment is assumed
(single `uvicorn` process serving everything).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from app.models.lineup import LineupsFile
from app.storage._atomic import atomic_write_text
from app.storage.paths import CONFIG_DIRNAME, get_data_dir

LINEUPS_FILENAME = "lineups.json"

T = TypeVar("T")

#: Guards the full load-mutate-save cycle for `config/lineups.json` so
#: concurrent mutations (see module docstring) can't race and lose updates.
#: Process-wide and not keyed by `base_dir` on purpose — it only needs to
#: serialize writes, never blocks correctness, and tests freely use
#: different `base_dir`s under it without issue.
_LOCK = threading.Lock()


def _lineups_path(base_dir: Path | None = None) -> Path:
    base = base_dir if base_dir is not None else get_data_dir()
    return base / CONFIG_DIRNAME / LINEUPS_FILENAME


def load_lineups(base_dir: Path | None = None) -> LineupsFile:
    """Load `config/lineups.json`.

    A fresh install has no file yet — that's expected, not an error, so this
    returns an empty default (`schemaVersion=1`, no lineups) rather than
    raising.
    """
    path = _lineups_path(base_dir)
    if not path.exists():
        return LineupsFile()
    return LineupsFile.model_validate_json(path.read_text(encoding="utf-8"))


def save_lineups(data: LineupsFile, base_dir: Path | None = None) -> None:
    """Atomically write `config/lineups.json`.

    Writes to a temp file in the same directory (so the rename is on the
    same filesystem) and `os.replace`s it into place, so readers never see a
    partially-written file.
    """
    path = _lineups_path(base_dir)
    atomic_write_text(path, data.model_dump_json(indent=2))


def update_lineups(
    mutate_fn: Callable[[LineupsFile], T], base_dir: Path | None = None
) -> T:
    """Atomically load, mutate, and save `config/lineups.json`.

    Holds `_LOCK` for the full cycle: loads the current `LineupsFile`,
    passes it to `mutate_fn` (which mutates it in place and/or returns a
    result), then saves it back — all without any other caller able to
    interleave a load/save of its own. This is the only sanctioned way for
    `services/lineups.py` to mutate the config file; calling
    `load_lineups`/`save_lineups` as a separate pair (instead of through
    here) reintroduces the lost-update race this function exists to close.

    If `mutate_fn` raises, nothing is saved (the lock is released and the
    in-memory `data` is simply discarded).
    """
    with _LOCK:
        data = load_lineups(base_dir)
        result = mutate_fn(data)
        save_lineups(data, base_dir)
        return result
