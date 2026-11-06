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

Per-programme metadata (docs/backlog.md item 40): beyond `<title>`/`<desc>`,
each `<programme>` also gets, in the order the XMLTV DTD requires
(`title+, sub-title*, desc*, ..., date?, category*, ..., episode-num*, ...,
previously-shown?, ..., new?`):

- `<sub-title>` from SD's `episodeTitle150`, when present.
- `<date>` from SD's `originalAirDate` (digits only, e.g. `"20131108"` —
  the long-established convention most SchedulesDirect-sourced XMLTV
  grabbers, e.g. zap2xml, use for this field, despite the DTD's own
  wording being closer to "production/copyright date").
- `<category>` — a "Movie"/"Series" classification (see `_is_movie`/
  `_is_series_episode`) plus every genre SD reported.
- `<episode-num>` — movies get none. Series episodes always get a
  `system="dd_progid"` entry (the raw SD programID, zap2xml-formatted with
  a dot before the last 4 digits) even with no season/episode numbers from
  SD, since the programID's own root segment is enough for a consumer to
  group recordings under one series — this is the single most impactful
  part of this fix, since not every station's programs carry Gracenote
  season/episode data. When SD *does* supply season/episode numbers
  (`SdProgram.metadata`), `system="xmltv_ns"` (zero-indexed per the DTD)
  and `system="onscreen"` (`"S04E07"`-style) entries are added too.
- `<new>`/`<previously-shown>` from the schedule airing's own `new` flag
  (`SdScheduleProgram.new`) — distinct from anything in the cached program
  record itself, since it's a property of this particular airing, not the
  program. Per SD's own docs (API-20141201.md), an optional boolean field
  that's absent from a schedule entry should be read as `False`, and SD's
  real responses never send `"new": false` explicitly for a rerun — they
  just omit the key. So `False` and `None`/missing are handled identically:
  both emit `<previously-shown>`; only `new is True` emits `<new>`.

See `_is_movie`/`_is_series_episode` for the movie-vs-series decision.
SD's `entityType` is authoritative when present, but classification is
"movie unless proven otherwise": only a short, explicitly-enumerated set
of `entityType` values (`_MOVIE_ENTITY_TYPES`) counts as a movie, and
everything else — `Series`, `Show`, `Special`, `Sports`, `Team Event`,
`Miniseries`, `Sport-Related Episode`, and any other/future `entityType`
value SD introduces — gets series treatment (at minimum a `dd_progid`
episode-num). This fails safe toward the series branch rather than the
movie branch: enumerating "every series type" instead would silently
regress to no episode-num for any `entityType` value not yet accounted
for, which is the exact bug this classification exists to avoid. The
programID's two-letter prefix is only a fallback for programs cached
before `entityType` existed on `SdProgram` — see that model's docstring
for the cache-migration implication of that field being newly added.
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

#: SD programID prefix for a standalone movie — only consulted as a
#: fallback when `SdProgram.entityType` is missing (see `_is_movie`).
_MOVIE_PROGRAM_ID_PREFIX = "MV"

#: SD programID prefixes that represent episodic content — likewise only a
#: fallback for when `entityType` is missing (see `_is_series_episode`).
_SERIES_PROGRAM_ID_PREFIXES = ("EP", "SH")

#: `SdProgram.entityType` values (per SD's docs — see
#: docs/schedulesdirect-integration.md) that represent a standalone movie,
#: as opposed to episodic/series content. Deliberately a short, explicit
#: "movie" allowlist rather than a "series" allowlist: SD's full
#: `entityType` enum has on the order of 20 documented values (`Episode`,
#: `Series`, `Show`, `Special`, `Sports`, `Sport-Related Episode`,
#: `Team Event`, `Miniseries`, ... — see
#: docs/schedulesdirect-integration.md for what's confirmed), most of which
#: are series-ish/non-movie in nature. Enumerating every series-ish value
#: here would silently regress (no episode-num at all) the moment SD
#: documents a value this list doesn't yet know about; enumerating movies
#: instead fails safe toward the series branch, which is the side
#: docs/backlog.md item 40's bug report was actually about. `"TV Movie"`
#: and `"Paid Program"` are included alongside `"Movie"` itself — both are
#: standalone, non-episodic content, not series episodes.
_MOVIE_ENTITY_TYPES = frozenset({"Movie", "TV Movie", "Paid Program"})


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


def _program_sub_title(program: SdProgram) -> str | None:
    """`<sub-title>` text from SD's `episodeTitle150`, if present.

    Emitted regardless of movie/series classification — the DTD doesn't
    reserve `sub-title` to episodic content, and trusting whatever SD
    itself chose to supply here is simpler than second-guessing it against
    `entityType`.
    """
    return program.episodeTitle150 or None


def _program_date(program: SdProgram) -> str | None:
    """`<date>` text from SD's `originalAirDate` ("YYYY-MM-DD" -> digits
    only, e.g. "20131108") — see module docstring for why this field is
    used for both movies (release date) and episodes (original air date).
    """
    if not program.originalAirDate:
        return None
    return program.originalAirDate.replace("-", "")


def _is_movie(program: SdProgram) -> bool:
    """Whether `program` is a standalone movie, not a series episode.

    `entityType` is SD's own authoritative signal for this per its docs,
    checked against the explicit `_MOVIE_ENTITY_TYPES` allowlist (see that
    constant's docstring for why this is a movie allowlist rather than a
    series allowlist). The programID's "MV" prefix is only a fallback for a
    `CachedProgram` written before `entityType` existed on this model (see
    that field's docstring on `SdProgram`) — that fallback's own prefix set
    is unchanged by the allowlist-direction fix above; it's a separate,
    narrower heuristic only used when there's no `entityType` data at all.
    """
    if program.entityType is not None:
        return program.entityType in _MOVIE_ENTITY_TYPES
    return program.programID.startswith(_MOVIE_PROGRAM_ID_PREFIX)


def _is_series_episode(program: SdProgram) -> bool:
    """Whether `program` belongs to a series (vs. a standalone movie).

    Drives whether `<episode-num>`/`<sub-title>`/a "Series" `<category>`
    get emitted for this programme. When `entityType` is present, this is
    simply "not a movie" (see `_is_movie` and `_MOVIE_ENTITY_TYPES`'s
    docstring for the fail-safe-toward-series rationale) — every
    `entityType` value that isn't an explicitly-enumerated movie type
    counts as series-ish here, including ones this module doesn't know
    about yet. When `entityType` is missing entirely, falls back to the
    narrower programID-prefix heuristic (`EP`/`SH` only) used before that
    field existed on `SdProgram` — this fallback path is intentionally
    *not* "not a movie by prefix," since an unrecognized prefix (e.g. an
    `SP` sports programID with no `entityType`) shouldn't be assumed to be
    series content just because it isn't a recognized movie prefix either.
    """
    if program.entityType is not None:
        return not _is_movie(program)
    return program.programID.startswith(_SERIES_PROGRAM_ID_PREFIXES)


def _program_categories(program: SdProgram) -> list[str]:
    """`<category>` text values for this programme.

    A "Movie"/"Series" classification (the signal docs/backlog.md item 40
    calls out) comes first, followed by every genre SD reported. Order
    among these doesn't matter to the DTD (`category*` — any number,
    position only fixed relative to *other* element types), but putting the
    classification first keeps generated output readable.

    Note there's no third "neither" case here when `entityType` is
    present: per `_is_movie`/`_is_series_episode`'s fail-safe-toward-series
    design, every program with `entityType` data is classified as one or
    the other (e.g. a "Sports"- or "Special"-typed program now gets a
    "Series" category, not its raw `entityType` string) — see those
    functions' docstrings. A program with neither `entityType` nor a
    recognized programID prefix (the `entityType`-missing fallback path)
    gets no classification category at all, only genres, same as before.
    """
    categories: list[str] = []
    if _is_movie(program):
        categories.append("Movie")
    elif _is_series_episode(program):
        categories.append("Series")
    if program.genres:
        categories.extend(program.genres)
    return categories


def _dd_progid(program_id: str) -> str:
    """Format an SD programID as a zap2xml-style `dd_progid` episode-num.

    SD program IDs are documented as 14 characters: a 2-letter type prefix
    (EP/SH/MV/SP/...) followed by 12 digits, the first 8 identifying the
    show/series and the last 4 identifying the specific episode (`"0000"`
    conventionally meaning "no specific episode," as in a generic
    "SH"-prefixed listing) — see docs/schedulesdirect-integration.md.
    `dd_progid` is the de facto `episode-num` system name zap2xml (the most
    widely used SchedulesDirect-to-XMLTV grabber) uses for exactly this
    format, specifically because Plex's XMLTV importer recognizes it as a
    strong "this is a TV episode, and here is its series identity" signal —
    independent of whether SD supplied season/episode numbers for this
    particular program. Falls back to the raw, unformatted programID if it
    isn't the expected 14-character shape (defensive: SD's docs describe
    this length as typical, not a hard contractual guarantee).
    """
    if len(program_id) == 14:
        return f"{program_id[:10]}.{program_id[10:]}"
    return program_id


def _program_episode_nums(program: SdProgram) -> list[tuple[str, str]]:
    """`(system, value)` pairs for every `<episode-num>` this programme gets.

    Movies (and anything else that isn't a series episode) get none.
    Series episodes always get at least a `dd_progid` entry (see
    `_dd_progid`) even with no season/episode numbers from SD — this alone
    is enough for a consumer to recognize "this belongs to a series" and is
    the single most impactful part of docs/backlog.md item 40's fix, since
    not every station's programs carry Gracenote season/episode metadata.
    When SD *does* supply season/episode numbers (`SdProgram
    .primary_season_episode()`), `xmltv_ns` (zero-indexed per the DTD) and
    `onscreen` (`"S04E07"`-style) entries are added on top of that.
    """
    if not _is_series_episode(program) or _is_movie(program):
        return []

    entries: list[tuple[str, str]] = [("dd_progid", _dd_progid(program.programID))]

    season_episode = program.primary_season_episode()
    if season_episode is None or season_episode.season is None or season_episode.season < 1:
        return entries

    season_zero = season_episode.season - 1
    if season_episode.episode is not None and season_episode.episode >= 1:
        episode_zero = season_episode.episode - 1
        entries.append(("xmltv_ns", f"{season_zero}.{episode_zero}."))
        entries.append(
            ("onscreen", f"S{season_episode.season:02d}E{season_episode.episode:02d}")
        )
    else:
        entries.append(("xmltv_ns", f"{season_zero}.."))

    return entries


def _apply_new_or_previously_shown(programme_el: ET.Element, airing: SdScheduleProgram) -> None:
    """Emit `<new>` or `<previously-shown>` from the airing's own `new` flag.

    This is a property of *this particular airing* (`SdScheduleProgram
    .new`, from the schedule), not of the cached program record — a rerun
    of a program that was new when first aired has `new=False`-equivalent
    on the rerun's airing, same program metadata either way.

    Per SD's own docs (API-20141201.md), an optional boolean field that's
    absent from a schedule entry should be read as `False` — and in
    practice SD's real responses never send `"new": false` explicitly for
    a rerun, they just omit the key entirely, so `airing.new` is only ever
    `True` or `None` in real data. `True` emits `<new/>`; anything else
    (`False` or `None`/missing) emits `<previously-shown/>` — there is no
    "unknown, emit neither" case.
    """
    if airing.new is True:
        ET.SubElement(programme_el, "new")
    else:
        ET.SubElement(programme_el, "previously-shown")


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
                program = cached_program.data
                title_el.text = _program_title(program)

                # Element order from here follows the XMLTV DTD's required
                # sequence for <programme>'s children: sub-title*, desc*,
                # date?, category*, ..., episode-num*, ..., previously-shown?
                # / new? (see module docstring).
                sub_title = _program_sub_title(program)
                if sub_title:
                    sub_title_el = ET.SubElement(
                        programme_el, "sub-title", attrib={"lang": "en"}
                    )
                    sub_title_el.text = sub_title

                description = _program_description(program)
                if description:
                    desc_el = ET.SubElement(programme_el, "desc", attrib={"lang": "en"})
                    desc_el.text = description

                date_text = _program_date(program)
                if date_text:
                    date_el = ET.SubElement(programme_el, "date")
                    date_el.text = date_text

                for category_text in _program_categories(program):
                    category_el = ET.SubElement(
                        programme_el, "category", attrib={"lang": "en"}
                    )
                    category_el.text = category_text

                for system, value in _program_episode_nums(program):
                    episode_num_el = ET.SubElement(
                        programme_el, "episode-num", attrib={"system": system}
                    )
                    episode_num_el.text = value

                _apply_new_or_previously_shown(programme_el, airing)
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
