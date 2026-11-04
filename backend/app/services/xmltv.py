"""XMLTV document generation.

For every channel in a lineup with a mapped SD station (`sdStationId`/
`sdLineupId` set — see docs/backlog.md item 38), pulls that station's
cached schedule entries (never fetches live — this module calls
`storage/`, never `sd_client/` or raw HTTP/file I/O directly, per
CLAUDE.md's dependency direction) for a guide window of upcoming days,
resolves each schedule entry's program ID against cached program metadata,
and emits a standard XMLTV document. The result is written atomically to
`/data/output/<lineup-id>.xml` via `storage.output.save_xmltv`.

Guide window: defaults to the next 3 days (`GUIDE_WINDOW_DAYS`). Chosen as
a conservative default that keeps the scheduled refresh job's (Phase 5)
per-day SD schedule fetches modest while still covering "today plus a
couple of days," which is enough for a guide grid to be useful immediately
after generation; callers needing a deeper window can pass
`guide_window_days` explicitly.

Channels without a mapped SD station are *omitted from the output
entirely* (no `<channel>` element, no `<programme>` elements) rather than
included as an empty/placeholder channel — a `<channel>` with no programme
data isn't useful to a guide consumer like Plex/Jellyfin, and this keeps
"skipped" from item 9's test brief unambiguous (no crash, no output for
that channel).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.lineup import Channel, Lineup
from app.models.sd import SdProgram, SdScheduleProgram
from app.services.lineups import NotFoundError
from app.storage import sd_cache
from app.storage.lineups import load_lineups
from app.storage.output import find_xmltv, save_xmltv

logger = logging.getLogger(__name__)

#: Default guide window, in days, starting from "now" — see module docstring.
GUIDE_WINDOW_DAYS = 3

GENERATOR_INFO_NAME = "epg-editor"


def guide_window_dates(now: datetime, days: int) -> list[str]:
    """Return `days` consecutive "YYYY-MM-DD" date strings starting at `now`.

    Public (not `_`-prefixed) because `services/refresh.py` needs to
    request SD schedules for the *exact same* date window generation will
    later read back out of the cache — keeping both callers on one
    definition avoids them silently drifting apart.
    """
    start_date = now.date()
    return [(start_date + timedelta(days=offset)).isoformat() for offset in range(days)]


def _xmltv_timestamp(moment: datetime) -> str:
    """Format a datetime per XMLTV's `YYYYMMDDHHMMSS +0000` convention."""
    utc_moment = moment.astimezone(timezone.utc)
    return utc_moment.strftime("%Y%m%d%H%M%S +0000")


def _channel_xmltv_id(channel: Channel) -> str:
    """The id used for both `<channel id>` and `<programme channel>`.

    Prefers `tvgId` (what an M3U-derived channel would be matched against
    downstream) and falls back to epg-editor's own channel id for
    manually-created channels that have no `tvgId`.

    Output-only sanitization (backlog item 34): Plex fails to match XMLTV
    channel ids containing a literal `.` (e.g. an ATSC-subchannel-style
    `tvgId` like `7.1`), so dots are replaced with `-` in the emitted id.
    This never touches the stored `Channel.tvgId`/`id` in
    `config/lineups.json` — only the string returned here, used for the
    `<channel id>`/`<programme channel>` attributes. Scoped to dots only
    per the backlog item; a broader Plex-unsafe character set is deferred.
    """
    return (channel.tvgId or channel.id).replace(".", "-")


def _program_title(program: SdProgram) -> str:
    if program.titles:
        return program.titles[0].title120
    return "Unknown"


def _program_description(program: SdProgram) -> str | None:
    if not program.descriptions:
        return None
    for entries in program.descriptions.values():
        if entries:
            return entries[0].description
    return None


def mapped_channels(lineup: Lineup) -> list[Channel]:
    """Channels with a mapped SD station, with duplicate XMLTV ids filtered out.

    "Mapped" is derived purely from `sdStationId` (and `sdLineupId`) being
    set — see docs/backlog.md item 38; there is no separate gating boolean.

    Two channels sharing a `tvgId` (or, in principle, a fallback bare
    channel `id`, though those are always unique UUIDs in practice) would
    otherwise produce two `<channel>` elements with the same `id`
    attribute, which a consumer effectively merges — not invalid per the
    DTD, but semantically wrong. We keep the first occurrence and skip
    (log, don't crash) later duplicates: this is a data-quality issue in
    the user's channel list, not a reason to fail the whole lineup's guide
    generation (fixing it in the UI is out of scope for now).

    Public (not `_`-prefixed): `services/refresh.py` reuses this exact
    filtering/dedup logic to decide which SD stations to refresh, rather
    than duplicating it — see CLAUDE.md's instruction to share, not copy,
    this helper.
    """
    candidates = [
        channel
        for channel in lineup.channels
        if channel.mapping is not None
        and channel.mapping.sdStationId
        and channel.mapping.sdLineupId
    ]

    seen_ids: set[str] = set()
    deduped: list[Channel] = []
    for channel in candidates:
        xmltv_id = _channel_xmltv_id(channel)
        if xmltv_id in seen_ids:
            logger.warning(
                "lineup %r: skipping channel %r (%s) from XMLTV generation — "
                "duplicate XMLTV id %r shared with an earlier channel",
                lineup.id,
                channel.name,
                channel.id,
                xmltv_id,
            )
            continue
        seen_ids.add(xmltv_id)
        deduped.append(channel)
    return deduped


def _collect_airings(
    station_id: str, dates: list[str], base_dir: Path | None
) -> list[SdScheduleProgram]:
    schedules = sd_cache.load_station_schedules(station_id, dates, base_dir=base_dir)
    airings: list[SdScheduleProgram] = []
    for schedule_entry in schedules:
        airings.extend(schedule_entry.data.programs)
    airings.sort(key=lambda program: program.airDateTime)
    return airings


def build_xmltv_document(
    lineup: Lineup,
    *,
    now: datetime | None = None,
    guide_window_days: int = GUIDE_WINDOW_DAYS,
    base_dir: Path | None = None,
) -> str:
    """Build the XMLTV document text for a lineup (no file I/O).

    Separated from `generate_xmltv` so tests can inspect/validate the XML
    text directly without needing to re-read it back off disk.
    """
    current_time = now if now is not None else datetime.now(timezone.utc)
    dates = guide_window_dates(current_time, guide_window_days)

    tv_el = ET.Element("tv", attrib={"generator-info-name": GENERATOR_INFO_NAME})

    channels_to_emit = mapped_channels(lineup)

    # DTD requires all <channel> elements before any <programme> elements
    # (`<!ELEMENT tv (channel*, programme*)>`), so channels are built in a
    # first pass and programmes in a second.
    for channel in channels_to_emit:
        channel_el = ET.SubElement(
            tv_el, "channel", attrib={"id": _channel_xmltv_id(channel)}
        )
        display_name_el = ET.SubElement(channel_el, "display-name")
        display_name_el.text = channel.name
        if channel.logoUrl:
            ET.SubElement(channel_el, "icon", attrib={"src": channel.logoUrl})

    for channel in channels_to_emit:
        mapping = channel.mapping
        assert mapping is not None and mapping.sdStationId is not None
        xmltv_channel_id = _channel_xmltv_id(channel)

        airings = _collect_airings(mapping.sdStationId, dates, base_dir)
        program_ids = [airing.programID for airing in airings]
        cached_programs = sd_cache.load_programs(program_ids, base_dir=base_dir)

        for airing in airings:
            stop = airing.airDateTime + timedelta(seconds=airing.duration)
            programme_el = ET.SubElement(
                tv_el,
                "programme",
                attrib={
                    "start": _xmltv_timestamp(airing.airDateTime),
                    "stop": _xmltv_timestamp(stop),
                    "channel": xmltv_channel_id,
                },
            )
            cached_program = cached_programs.get(airing.programID)
            title_el = ET.SubElement(programme_el, "title", attrib={"lang": "en"})
            if cached_program is not None:
                title_el.text = _program_title(cached_program.data)
                description = _program_description(cached_program.data)
                if description:
                    desc_el = ET.SubElement(programme_el, "desc", attrib={"lang": "en"})
                    desc_el.text = description
            else:
                # Schedule entry exists but program metadata isn't cached
                # yet (e.g. refresh hasn't pulled it) — emit a minimal valid
                # <programme> rather than dropping the airing or crashing.
                title_el.text = "Unknown"

    body = ET.tostring(tv_el, encoding="unicode")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE tv SYSTEM "xmltv.dtd">\n'
        f"{body}\n"
    )


def generate_xmltv(
    lineup: Lineup,
    *,
    now: datetime | None = None,
    guide_window_days: int = GUIDE_WINDOW_DAYS,
    base_dir: Path | None = None,
) -> Path:
    """Build a lineup's XMLTV document and atomically write it to `output/`."""
    xml_text = build_xmltv_document(
        lineup, now=now, guide_window_days=guide_window_days, base_dir=base_dir
    )
    return save_xmltv(lineup.id, xml_text, base_dir=base_dir)


def get_xmltv_output_path(lineup_id: str, base_dir: Path | None = None) -> Path | None:
    """Return the path to a lineup's already-generated XMLTV file, if any.

    Thin pass-through to `storage.output.find_xmltv` — exists so
    `api/xmltv.py` never calls `storage/` directly, per CLAUDE.md's module
    layering (`api/` -> `services/` -> `storage/`), and so the "serve" side
    doesn't need its own knowledge of where output files live. May raise
    `ValueError` if `lineup_id` sanitizes to an unsafe path segment (see
    `storage._safe.safe_segment`) — callers should treat that the same as
    "not found".
    """
    return find_xmltv(lineup_id, base_dir=base_dir)


def generate_xmltv_for_lineup_id(
    lineup_id: str,
    *,
    now: datetime | None = None,
    guide_window_days: int = GUIDE_WINDOW_DAYS,
    base_dir: Path | None = None,
) -> Path:
    """Look up a lineup by id and generate its XMLTV document.

    Raises `services.lineups.NotFoundError` if no such lineup exists.
    """
    data = load_lineups(base_dir=base_dir)
    lineup = next((item for item in data.lineups if item.id == lineup_id), None)
    if lineup is None:
        raise NotFoundError(f"lineup {lineup_id!r} not found")
    return generate_xmltv(
        lineup, now=now, guide_window_days=guide_window_days, base_dir=base_dir
    )
