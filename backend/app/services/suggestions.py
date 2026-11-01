"""Mapping-suggestion generation and bulk-accept (Phase 3, items 21-22).

Two independent operations live here:

- `generate_suggestions`: scores every channel in a lineup against the
  candidate SD station pool drawn from its associated `sdLineupIds`, and
  (re)writes `channel.mapping.suggestions` for every channel.
- `bulk_accept_suggestions`: confirms whichever *unconfirmed* channels'
  top-scoring suggestion clears `BULK_ACCEPT_THRESHOLD`, a fixed backend
  constant (per CLAUDE.md, explicitly not a request parameter/UI control).

Fuzzy-matching library: `rapidfuzz`, confirmed (not just evaluated) by the
product owner per docs/backlog.md item 20 — see module-level constants
below for the exact scoring function/threshold and the reasoning for each.

Depends only on `sd_client/` + `storage/` + `services.lineups` (for
`NotFoundError`/`get_lineup`), never raw HTTP or raw file I/O itself, per
CLAUDE.md's module layering. Callers supply an already-constructed
`SdClient` (same dependency-injection pattern as `services/refresh.py`),
so this stays testable with `httpx.MockTransport` and zero real
credentials.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rapidfuzz import fuzz
from rapidfuzz.utils import default_process

from app.models.lineup import (
    Channel,
    ChannelMapping,
    Lineup,
    LineupsFile,
    MappingSuggestion,
)
from app.models.sd import SdStation
from app.models.suggestions import (
    BulkAcceptResult,
    ChannelSuggestionCount,
    ConfirmedSuggestion,
    SuggestionResult,
)
from app.sd_client.client import SdClient
from app.services.lineups import NotFoundError, get_lineup
from app.storage import sd_cache
from app.storage.lineups import update_lineups

#: Keep only the top-N scoring candidates per channel, discarding the long
#: tail of low-relevance stations. A cable SD lineup's station roster can
#: run into the hundreds, and nobody is going to usefully review 200
#: candidates for one channel — 5 is enough to show a couple of plausible
#: near-ties (e.g. two affiliates of the same network in different cities)
#: without burying the actual best match in noise. Chosen as a starting
#: value for Phase 3; revisit at checkpoint 25 if real lineups show 5 is
#: too few/many.
MAX_SUGGESTIONS_PER_CHANNEL = 5

#: Fixed backend bulk-accept threshold (0-1 scale, matching
#: `MappingSuggestion.score`). Per CLAUDE.md, this is a backend constant,
#: not a UI-adjustable setting.
#:
#: What 0.92 actually does: `rapidfuzz.fuzz.WRatio` applies roughly a 0.9
#: multiplier to the top score of a *partial* (non-exact) string match when
#: the two strings differ substantially in length after normalization
#: (roughly 1.5x or more) — e.g. a bare callsign against a fuller display
#: name. That ~0.90 ceiling is a structural property of the scoring function
#: itself, not a signal that distinguishes a genuine match from a false
#: positive: a channel named "FOX 5" scores exactly 0.90 against both a
#: genuine longer match like "FOX 5 New York" *and* a different-market
#: station that only shares the "FOX" affiliate (a false positive) — the two
#: are indistinguishable at that score level by this metric alone, so
#: raising/lowering the threshold *within* that range can't separate them.
#: When the two strings are closer in length, though, a word-reordered or
#: word-subset match can score higher still — e.g. "NBC Bay Area" vs. "Bay
#: Area NBC" and "FOX 5 NY" vs. "FOX 5 NY HD" both score 0.95 — so the 0.90
#: ceiling is not a hard cap on all partial matches, just on the
#: substantially-different-length case.
#:
#: Setting the threshold at 0.92, just above that ~0.90 ceiling, sidesteps
#: the length-driven ambiguity above rather than solving it: bulk-accept
#: fires on near-exact full-string matches *and* on same-length-ish
#: word-reordered/word-subset matches (which can clear 0.92), while
#: deliberately excluding the substantially-different-length partial
#: matches (capped ~0.90) — good or bad alike. So bulk-accept does confirm
#: some genuine non-exact matches, just not the "bare callsign vs. fuller
#: name" style of partial match. This is a conservative starting point, not
#: a tuned one. In practice it's expected to bulk-accept conservatively
#: against real lineups: many real HDHomeRun-style channel names
#: (e.g. "KGO-HD") won't exact-match or closely length-match a station's
#: name/callsign/affiliate. That's intentional caution, not a bug — real
#: tuning (a lower threshold, and/or a better signal than a bare WRatio
#: score for distinguishing partial matches) happens at checkpoint 25
#: against real lineup data.
#:
#: Note this threshold alone also can't resolve *ties* among same-scoring
#: candidates for different stations (e.g. a channel named "FOX" scoring a
#: perfect 1.0 against every same-affiliate station in the pool) —
#: `bulk_accept_suggestions` below handles that separately by skipping the
#: channel entirely rather than guessing which tied candidate to confirm.
BULK_ACCEPT_THRESHOLD = 0.92

#: Tie-break epsilon (same 0-1 scale) for `bulk_accept_suggestions`: two
#: suggestions whose scores differ by no more than this are treated as
#: tied. Needed because a channel named after a bare network affiliate
#: (e.g. "FOX") scores a perfect 1.0 against *every* station sharing that
#: affiliate in the candidate pool — without a tie check, `max()` would
#: silently confirm whichever one happened to land first in pool-insertion
#: order, which is exactly the wrong-match-gets-auto-accepted failure the
#: threshold exists to prevent.
BULK_ACCEPT_TIE_EPSILON = 0.001


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _find_lineup(data: LineupsFile, lineup_id: str) -> Lineup:
    """Local copy of `services.lineups._find_lineup`.

    Not imported from there because it's a private (`_`-prefixed) helper of
    that module — duplicating these few lines here is simpler than widening
    that module's public surface for one caller.
    """
    for lineup in data.lineups:
        if lineup.id == lineup_id:
            return lineup
    raise NotFoundError(f"lineup {lineup_id!r} not found")


def _score_channel_against_station(channel_name: str, station: SdStation) -> float:
    """Score a channel's `name` against one candidate station.

    Per product owner decision, matches against the station's `name`,
    `callsign`, *and* `affiliate` (e.g. "FOX", "NBC"), taking the max across
    all three — several genuine matches share zero literal text with the
    station's `name` but do match its `affiliate` (e.g. "FOX 5" vs callsign
    "WNYW", affiliate "FOX"). `rapidfuzz.fuzz.WRatio` with
    `rapidfuzz.utils.default_process` (case-folds, strips punctuation) is
    the confirmed scoring function; its 0-100 output is normalized to the
    0-1 scale `MappingSuggestion.score` documents.

    `channel.tvgId` is deliberately *not* used as an additional signal here
    (CLAUDE.md/the product owner only called out name/call sign/affiliate).
    `tvgId` is an M3U/XMLTV-side identifier (e.g. "KGO.us") with its own
    format conventions unrelated to SD's station naming — fuzzy-matching it
    against SD station fields would mostly add noise, not signal, so it's
    skipped rather than folded in speculatively.
    """
    best = 0.0
    for candidate in (station.name, station.callsign, station.affiliate):
        if not candidate:
            continue
        score = fuzz.WRatio(channel_name, candidate, processor=default_process)
        if score > best:
            best = score
    return best / 100.0


def _score_channel_against_station_name_only(
    channel_name: str, station: SdStation
) -> float:
    """Secondary, tie-break-only score: `channel.name` vs. `station.name` alone.

    Used solely to order same-scoring candidates in `generate_suggestions`
    before truncating to `MAX_SUGGESTIONS_PER_CHANNEL` (see that function's
    docstring) — never stored on `MappingSuggestion.score` and never
    consulted by `bulk_accept_suggestions`. Deliberately excludes
    `callsign`/`affiliate`: those are exactly the fields that make several
    *different* stations tie on the primary score (e.g. every station
    sharing the "FOX" affiliate), so folding them into the tie-break would
    just reproduce the tie instead of breaking it. Comparing `name` alone
    prefers the station whose actual name most resembles the channel.
    """
    if not station.name:
        return 0.0
    return fuzz.WRatio(channel_name, station.name, processor=default_process) / 100.0


async def _ensure_lineup_stations_cached(
    sd_lineup_id: str, sd_client: SdClient, *, base_dir: Path | None
) -> list[SdStation]:
    """Return a SD lineup's station roster, fetching+caching it if needed.

    First real caller of `storage.sd_cache.save_lineup_stations` — Phase 1/5
    built the cache file shape (`CachedLineupStations`) but nothing had
    populated it yet (`services/refresh.py` only ever fetches schedules/
    programs for already-known station ids, never a lineup's station
    *list*). Respects "no speculative bulk-fetching": only called for SD
    lineup ids actually associated with the epg-editor lineup being scored
    (see `generate_suggestions`), and only hits the network at all on a
    cache miss.
    """
    # NOTE: this cache is populated on a miss but never expires/refreshes —
    # there's no TTL check here and nothing currently calls
    # `storage.sd_cache.invalidate_lineup_stations`. Phase 5's scheduled
    # refresh job needs to give the station roster cache the same
    # TTL/refresh treatment it gives schedules/programs; tracked there, not
    # fixed here.
    cached = sd_cache.load_lineup_stations(sd_lineup_id, base_dir=base_dir)
    if cached is not None:
        return cached.data.stations
    response = await sd_client.get_lineup_stations(sd_lineup_id)
    sd_cache.save_lineup_stations(sd_lineup_id, response, base_dir=base_dir)
    return response.stations


async def generate_suggestions(
    lineup_id: str,
    sd_client: SdClient,
    *,
    base_dir: Path | None = None,
    now: datetime | None = None,
) -> SuggestionResult:
    """(Re)compute `mapping.suggestions` for every channel in a lineup.

    Candidate pool: the union (deduped by `stationID`) of cached stations
    across every distinct `sdLineupId` in `lineup.sdLineupIds`, fetching
    and caching a SD lineup's roster on a cache miss (see
    `_ensure_lineup_stations_cached`). If a station appears in more than
    one of the lineup's associated SD lineups, the first `sdLineupId`
    (in `lineup.sdLineupIds` order) it's found under wins for that
    station's suggestion entries — `MappingSuggestion.sdLineupId` has to
    name exactly one.

    Tie-break rule for the top-N cutoff: candidates are sorted primarily by
    `score` (the name/callsign/affiliate max, descending), and ties on that
    primary score are broken by a secondary score comparing just
    `channel.name` against the station's `name` alone, also descending (see
    `_score_channel_against_station_name_only`). This matters because
    several *different* stations can tie at the same primary score purely
    by sharing a `callsign`/`affiliate` match (e.g. multiple stations
    affiliated with "FOX") — without a tie-break, which one lands in the
    top 5 (and in what order) would depend on arbitrary pool-insertion
    order, which could push a station whose actual *name* genuinely
    resembles the channel out of the visible suggestions. The secondary
    score is never stored on `MappingSuggestion.score` — it's ordering-only.

    Every channel's `suggestions` list is recomputed wholesale (overwritten,
    never accumulated), per docs/data-model.md. This includes channels that
    already have a *confirmed* mapping: recomputing only replaces the
    `suggestions` list (a read-only "here's what else was considered" record
    for the UI) and never touches `sdStationId`/`confirmed`/`confirmedAt`,
    so it can't silently un-confirm or re-point an existing mapping. Scoring
    is pure in-memory string comparison (no SD calls per channel), so
    recomputing confirmed channels too costs nothing extra in SD API calls
    and keeps the stored suggestions useful if the user later wants to
    review/change a confirmed channel's mapping.

    Raises `services.lineups.NotFoundError` if no such lineup exists.
    Raises `sd_client.client.SdClientError` (uncaught, not collected) if
    fetching any associated SD lineup's station roster fails — unlike
    `services/refresh.py`'s per-station error collection, there's no
    partial result that makes sense here: a lineup missing part of its
    candidate pool would silently produce worse/incomplete suggestions for
    every channel rather than a clearly-failed run, so this surfaces the failure
    immediately for the caller (the API route) to map to a clean 502.
    """
    lineup = get_lineup(lineup_id)
    current_time = now if now is not None else _now()

    station_pool: dict[str, tuple[SdStation, str]] = {}
    for sd_lineup_id in lineup.sdLineupIds:
        stations = await _ensure_lineup_stations_cached(
            sd_lineup_id, sd_client, base_dir=base_dir
        )
        for station in stations:
            if station.stationID not in station_pool:
                station_pool[station.stationID] = (station, sd_lineup_id)

    def mutate(data: LineupsFile) -> tuple[int, list[ChannelSuggestionCount]]:
        current_lineup = _find_lineup(data, lineup_id)
        counts: list[ChannelSuggestionCount] = []
        for channel in current_lineup.channels:
            scored = [
                (
                    _score_channel_against_station(channel.name, station),
                    _score_channel_against_station_name_only(channel.name, station),
                    station,
                    sd_lineup_id,
                )
                for station, sd_lineup_id in station_pool.values()
            ]
            # Primary: the name/callsign/affiliate max score, descending.
            # Secondary (tie-break only, never stored): name-only score,
            # descending — see this function's docstring.
            scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
            top = [
                MappingSuggestion(
                    sdStationId=station.stationID,
                    sdLineupId=sd_lineup_id,
                    score=primary_score,
                )
                for primary_score, _secondary_score, station, sd_lineup_id in scored[
                    :MAX_SUGGESTIONS_PER_CHANNEL
                ]
            ]

            if channel.mapping is None:
                channel.mapping = ChannelMapping(suggestions=top)
            else:
                channel.mapping.suggestions = top

            counts.append(
                ChannelSuggestionCount(channelId=channel.id, suggestionCount=len(top))
            )

        current_lineup.updatedAt = current_time
        return len(current_lineup.channels), counts

    channels_scored, channel_counts = update_lineups(mutate)

    return SuggestionResult(
        lineupId=lineup_id,
        stationPoolSize=len(station_pool),
        channelsScored=channels_scored,
        channelSuggestionCounts=channel_counts,
    )


def _load_station_lookup(
    sd_lineup_id: str, base_dir: Path | None
) -> dict[str, SdStation]:
    """Cache-only lookup of one SD lineup's roster, keyed by `stationID`.

    Reads whatever `storage.sd_cache` already has on disk — never calls
    `sd_client`/SD itself (see `enrich_lineup_suggestions`'s docstring for
    why: this is response-time display enrichment of already-cached data,
    not a suggestion-generation path). Returns an empty dict (not an error)
    on a cache miss, e.g. the SD lineup was since disassociated from every
    epg-editor lineup, or the cache was cleared — callers treat that the
    same as "station not found" and leave the display fields `None`.
    """
    cached = sd_cache.load_lineup_stations(sd_lineup_id, base_dir=base_dir)
    if cached is None:
        return {}
    return {station.stationID: station for station in cached.data.stations}


def _enrich_channel_suggestions_inplace(
    channel: Channel,
    station_lookups: dict[str, dict[str, SdStation]],
    base_dir: Path | None,
) -> None:
    """Mutate `channel.mapping.suggestions` in place, filling in display-only
    fields from `station_lookups` (populated lazily, on a cache miss, via
    `_load_station_lookup`).

    Shared helper behind both `enrich_channel_suggestions` (fresh,
    single-use `station_lookups` dict) and `enrich_lineup_suggestions`/
    `enrich_lineups_suggestions` (one `station_lookups` dict shared across
    every channel in a lineup/every lineup in a list), so a given
    `sdLineupId`'s cache file is read at most once per top-level enrichment
    call no matter how many channels/suggestions reference it — never
    re-read redundantly within the same call. Callers are responsible for
    only ever calling this on a deep copy (see the public functions below);
    it never touches `storage.lineups.update_lineups`/`save_lineups` itself.
    """
    mapping = channel.mapping
    if mapping is None or not mapping.suggestions:
        return
    for suggestion in mapping.suggestions:
        lookup = station_lookups.get(suggestion.sdLineupId)
        if lookup is None:
            lookup = _load_station_lookup(suggestion.sdLineupId, base_dir)
            station_lookups[suggestion.sdLineupId] = lookup
        station = lookup.get(suggestion.sdStationId)
        if station is None:
            continue
        suggestion.stationName = station.name
        suggestion.callsign = station.callsign
        suggestion.logoUrl = station.logo.URL if station.logo else None


def enrich_channel_suggestions(channel: Channel, *, base_dir: Path | None = None) -> Channel:
    """Return a copy of `channel` with every suggestion's display-only fields
    (`stationName`/`callsign`/`logoUrl`) filled in from the cached SD
    station roster for that suggestion's `sdLineupId`.

    Single-`Channel` sibling of `enrich_lineup_suggestions` below — same
    pure, cache-only, read-only, response-shaping-only contract (see that
    function's docstring for the full rationale), just scoped to one
    channel rather than a whole lineup. Exists so every endpoint in
    `api/lineups.py` that can return a bare `Channel` (`add_channel`,
    `update_channel`, `set_channel_mapping`, ...) can enrich its response
    the same way the two `GET` routes already do, without those endpoints
    having to round-trip through a whole-`Lineup` enrichment or duplicate
    `enrich_lineup_suggestions`'s logic. See that function's docstring for
    why a cache miss falls back to `None` display fields instead of
    raising, and why `logoUrl` never triggers a separate SD call.
    """
    enriched = channel.model_copy(deep=True)
    station_lookups: dict[str, dict[str, SdStation]] = {}
    _enrich_channel_suggestions_inplace(enriched, station_lookups, base_dir)
    return enriched


def enrich_lineup_suggestions(lineup: Lineup, *, base_dir: Path | None = None) -> Lineup:
    """Return a copy of `lineup` with every suggestion's display-only fields
    (`stationName`/`callsign`/`logoUrl`) filled in from the cached SD
    station roster for that suggestion's `sdLineupId`.

    Pure, cache-only, read-only enrichment applied *after* a `Lineup` has
    already been loaded from `config/lineups.json` — intended for every
    `api/lineups.py` (and `api/m3u.py`) route that returns a `Lineup`, so
    suggestion display data never disappears depending on which endpoint
    the frontend happens to be using for its local state update (see
    `MappingSuggestion`'s docstring in `models/lineup.py` for the full
    rationale/checkpoint-25 context, and the follow-on review finding that
    broadened this past just the two `GET` routes). Callers must never pass
    the result into `storage.lineups.update_lineups`/`save_lineups` — the
    returned `Lineup` is a deep copy, so mutating or persisting it wouldn't
    corrupt the on-disk file, but it also wouldn't actually be saved; this
    function exists only to shape a response body.

    A suggestion whose `(sdLineupId, sdStationId)` isn't found in the
    cache (evicted, lineup disassociated since the suggestion was
    generated, etc.) is left with `stationName`/`callsign`/`logoUrl` all
    `None` rather than raising — the frontend falls back to the raw
    `sdStationId` in that case. `logoUrl` comes from `SdStation.logo.URL`,
    which `get_lineup_stations` already returns inline with the rest of a
    station's roster entry — no separate "get logos" SD call is made or
    needed for this.

    Only ever reads `storage.sd_cache` (never `sd_client`), consistent with
    this module's existing "depends only on `sd_client/` + `storage/`"
    layering note — this function specifically only exercises the
    `storage/` half.
    """
    enriched = lineup.model_copy(deep=True)
    station_lookups: dict[str, dict[str, SdStation]] = {}

    for channel in enriched.channels:
        _enrich_channel_suggestions_inplace(channel, station_lookups, base_dir)

    return enriched


def enrich_lineups_suggestions(
    lineups: list[Lineup], *, base_dir: Path | None = None
) -> list[Lineup]:
    """`enrich_lineup_suggestions` applied to every lineup in a list.

    For `GET /api/lineups` (list_lineups), which returns every lineup at
    once.
    """
    return [enrich_lineup_suggestions(lineup, base_dir=base_dir) for lineup in lineups]


def bulk_accept_suggestions(
    lineup_id: str,
    *,
    threshold: float = BULK_ACCEPT_THRESHOLD,
) -> BulkAcceptResult:
    """Confirm every unconfirmed channel whose top suggestion clears `threshold`.

    Only considers channels with an existing, *unconfirmed* `mapping` that
    has at least one suggestion — channels with no `mapping` yet (never had
    `generate_suggestions` run) and channels already `confirmed` are left
    untouched (an already-confirmed mapping represents explicit user intent
    or a previous accept and is never silently overwritten by a later bulk
    run). `suggestions` is left in place after accepting, as a visible
    record of what was auto-accepted and why (per the task brief) — only
    `sdStationId`/`sdLineupId`/`confirmed`/`confirmedAt` are updated.

    `threshold` defaults to the fixed backend constant `BULK_ACCEPT_THRESHOLD`
    and is not exposed as a request parameter at the API layer (per
    CLAUDE.md's explicit "fixed backend default, not a UI control") — the
    keyword argument exists only so tests can exercise other thresholds
    without needing to monkeypatch the module constant.

    Tie handling: a channel whose name exactly matches a bare network
    affiliate (e.g. a channel literally named "FOX") scores a perfect 1.0
    against *every* station sharing that affiliate in the candidate pool —
    `top.score` clearing `threshold` doesn't mean `top` is uniquely the best
    candidate. If the top-scoring suggestion is tied (within
    `BULK_ACCEPT_TIE_EPSILON`) with another suggestion pointing at a
    *different* `sdStationId`, the channel is skipped entirely rather than
    auto-confirming an arbitrary one of the tied candidates — it's left for
    manual review via the individual-confirm endpoint, same as a
    below-threshold channel. Raising `threshold` can't fix this case since
    the tied scores are already at (or near) the maximum.

    Raises `services.lineups.NotFoundError` if no such lineup exists.
    """
    now = _now()

    def mutate(data: LineupsFile) -> BulkAcceptResult:
        lineup = _find_lineup(data, lineup_id)
        confirmed: list[ConfirmedSuggestion] = []

        for channel in lineup.channels:
            mapping = channel.mapping
            if mapping is None or mapping.confirmed or not mapping.suggestions:
                continue
            top = max(mapping.suggestions, key=lambda suggestion: suggestion.score)
            if top.score < threshold:
                continue

            tied_on_different_station = any(
                suggestion.sdStationId != top.sdStationId
                and abs(suggestion.score - top.score) <= BULK_ACCEPT_TIE_EPSILON
                for suggestion in mapping.suggestions
            )
            if tied_on_different_station:
                # Ambiguous top match (e.g. several same-affiliate stations
                # tied at the same score) — don't guess, leave for manual
                # review instead of auto-confirming an arbitrary candidate.
                continue

            mapping.sdStationId = top.sdStationId
            mapping.sdLineupId = top.sdLineupId
            mapping.confirmed = True
            mapping.confirmedAt = now
            confirmed.append(
                ConfirmedSuggestion(
                    channelId=channel.id,
                    sdStationId=top.sdStationId,
                    sdLineupId=top.sdLineupId,
                    score=top.score,
                )
            )

        if confirmed:
            lineup.updatedAt = now

        return BulkAcceptResult(
            lineupId=lineup_id,
            threshold=threshold,
            confirmedCount=len(confirmed),
            confirmed=confirmed,
        )

    return update_lineups(mutate)


__all__ = [
    "BULK_ACCEPT_THRESHOLD",
    "BULK_ACCEPT_TIE_EPSILON",
    "MAX_SUGGESTIONS_PER_CHANNEL",
    "bulk_accept_suggestions",
    "enrich_channel_suggestions",
    "enrich_lineup_suggestions",
    "enrich_lineups_suggestions",
    "generate_suggestions",
]
