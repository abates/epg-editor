"""Filesystem path resolution and bootstrapping for the data directory.

This is the only place that decides where the `/data` tree (`config/`,
`cache/`, `output/`) lives on disk and ensures those directories exist.
Other `app.storage` submodules build on top of these paths; nothing outside
`app.storage` should compute or create paths under the data directory
(see CLAUDE.md's backend module layout).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Environment variable used to override the base data directory, so
#: development/tests don't require write access to the real `/data`.
DATA_DIR_ENV_VAR = "EPG_EDITOR_DATA_DIR"
DEFAULT_DATA_DIR = "/data"

CONFIG_DIRNAME = "config"
CACHE_DIRNAME = "cache"
OUTPUT_DIRNAME = "output"


@dataclass(frozen=True)
class DataDirs:
    """Resolved paths under the configured data directory."""

    base: Path
    config: Path
    cache: Path
    output: Path


def get_data_dir() -> Path:
    """Return the configured base data directory.

    Controlled by the ``EPG_EDITOR_DATA_DIR`` environment variable
    (defaulting to ``/data``) rather than being hardcoded, so this is
    testable without real `/data` write permissions.
    """
    return Path(os.environ.get(DATA_DIR_ENV_VAR, DEFAULT_DATA_DIR))


def ensure_data_dirs(base_dir: Path | None = None) -> DataDirs:
    """Create ``config/``, ``cache/``, and ``output/`` if they don't exist.

    Idempotent — safe to call on every startup. Returns the resolved
    ``DataDirs`` so callers can locate the subdirectories without
    recomputing them.
    """
    base = base_dir if base_dir is not None else get_data_dir()
    dirs = DataDirs(
        base=base,
        config=base / CONFIG_DIRNAME,
        cache=base / CACHE_DIRNAME,
        output=base / OUTPUT_DIRNAME,
    )
    for path in (dirs.config, dirs.cache, dirs.output):
        path.mkdir(parents=True, exist_ok=True)
    return dirs
