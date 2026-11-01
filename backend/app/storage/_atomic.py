"""Shared atomic-file-write helper for `storage/` submodules.

Private to `app.storage` (leading underscore) — not part of the public
storage API other modules should import from directly.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


#: `mkstemp` creates temp files mode 0600, and `os.replace` preserves that
#: mode across the rename — so without this, every atomically-written file
#: (`lineups.json`, SD cache entries, generated XMLTV) would end up
#: readable only by the app's own user. That's surprising for host-side
#: backups or sidecar containers reading the `/data` volume, which per
#: CLAUDE.md's Docker design is explicitly meant to be visible outside the
#: app's own process (XMLTV output in particular is meant to be served/read
#: by other tools). 0644 (owner read/write, everyone else read-only) is
#: permissive enough for that without making the file world-writable.
_FINAL_FILE_MODE = 0o644


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically.

    Writes to a temp file in the same directory as `path` (so the final
    rename is same-filesystem and therefore atomic on POSIX) and
    `os.replace`s it into place. Cleans up the temp file on failure. The
    final file is `chmod`ed to `_FINAL_FILE_MODE` after the rename, since
    `mkstemp`'s default 0600 would otherwise survive the rename unchanged.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.chmod(tmp_name, _FINAL_FILE_MODE)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
