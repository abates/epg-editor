"""Tests for `app.storage._atomic`."""

from __future__ import annotations

import stat

from app.storage._atomic import atomic_write_text


def test_atomic_write_leaves_no_temp_file(tmp_path):
    path = tmp_path / "subdir" / "thing.json"

    atomic_write_text(path, "hello")

    assert path.read_text(encoding="utf-8") == "hello"
    assert list(path.parent.iterdir()) == [path]


def test_atomic_write_overwrite_updates_contents(tmp_path):
    path = tmp_path / "thing.json"
    atomic_write_text(path, "first")
    atomic_write_text(path, "second")

    assert path.read_text(encoding="utf-8") == "second"


def test_atomic_write_produces_group_and_other_readable_file(tmp_path):
    # `mkstemp` creates files mode 0600 by default, and `os.replace`
    # preserves that mode across the rename — without an explicit chmod,
    # every atomically-written file (lineups.json, SD cache entries,
    # generated XMLTV) would end up unreadable by anything but the app's
    # own user/group, which is surprising for host-side backups or sidecar
    # containers reading the /data volume (see Phase 1 review finding #7).
    path = tmp_path / "thing.json"

    atomic_write_text(path, "hello")

    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode & stat.S_IRGRP, "group should have read permission"
    assert mode & stat.S_IROTH, "other should have read permission"
    assert not mode & stat.S_IWOTH, "other should not have write permission"
