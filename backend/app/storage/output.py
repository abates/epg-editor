"""Read/write generated XMLTV files under `/data/output/`.

The only module that touches `output/` — `services/xmltv.py` builds the
XML document text and hands it here to write; `api/xmltv.py` asks this
module for the path to serve. Writes are atomic (temp file + rename), the
same discipline used for `config/lineups.json`. Per CLAUDE.md, XMLTV is
never generated on-the-fly per request — the serving side only ever reads
what generation already wrote.
"""

from __future__ import annotations

from pathlib import Path

from app.storage._atomic import atomic_write_text
from app.storage._safe import safe_segment
from app.storage.paths import OUTPUT_DIRNAME, get_data_dir


def xmltv_output_path(lineup_id: str, base_dir: Path | None = None) -> Path:
    """Return the path `<lineup-id>.xml` would be written to/read from."""
    base = base_dir if base_dir is not None else get_data_dir()
    return base / OUTPUT_DIRNAME / f"{safe_segment(lineup_id)}.xml"


def save_xmltv(lineup_id: str, xml_text: str, base_dir: Path | None = None) -> Path:
    """Atomically write a lineup's generated XMLTV document, overwriting any prior version."""
    path = xmltv_output_path(lineup_id, base_dir)
    atomic_write_text(path, xml_text)
    return path


def find_xmltv(lineup_id: str, base_dir: Path | None = None) -> Path | None:
    """Return the path to a lineup's generated XMLTV file if it exists, else `None`."""
    path = xmltv_output_path(lineup_id, base_dir)
    return path if path.is_file() else None
