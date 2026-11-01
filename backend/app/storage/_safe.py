"""Shared filename-safety helper for `storage/` submodules.

Private to `app.storage` — not part of the public storage API.
"""

from __future__ import annotations

import re

# IDs used as filename components (SD lineup/station/program IDs,
# epg-editor lineup IDs, dates) are alphanumeric plus `-`/`_`/`.` in
# practice. Sanitize defensively so a weird/hostile ID can never be used
# for path traversal or escape the intended cache/output directory.
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def safe_segment(value: str) -> str:
    """Return `value` made safe for use as a single path component.

    Any character outside `[A-Za-z0-9_.-]` (notably `/`) is replaced with
    `_`, so even a value containing `../` can't escape the directory it's
    joined into — the result is always one filename component, never a
    path. Raises `ValueError` if the sanitized result is empty or exactly
    `.`/`..`.
    """
    sanitized = _UNSAFE_CHARS.sub("_", value)
    if not sanitized or sanitized in {".", ".."}:
        raise ValueError(f"unsafe path segment: {value!r}")
    return sanitized
