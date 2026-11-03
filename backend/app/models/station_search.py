"""Pydantic models for the cache-only SD station search endpoint.

See `services/suggestions.py`'s `search_stations` (the business logic that
produces these) and `api/lineups.py`'s
`GET /api/lineups/{lineup_id}/station-search` (the route that returns them
as a response body).

Kept in a separate module from `models/suggestions.py` rather than folded in
there: that module's docstring scopes it to "mapping-suggestion generation
and bulk-accept" specifically. This is a related but distinct read path (a
free-text search over the same cached station pool, with no suggestion
generation, no persistence, and no bulk-accept-style threshold concept) —
see `search_stations`'s docstring for the full rationale.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StationSearchCandidate(BaseModel):
    """One SD station matched against a search query.

    Mirrors the per-suggestion display fields `MappingSuggestion` already
    carries (`stationName`/`callsign`/`logoUrl` there, `name`/`callsign`/
    `logoUrl` here) so the frontend's searchable station picker can reuse
    the same rendering as the suggestion-review UI.
    """

    stationID: str
    name: str
    callsign: str | None = None
    affiliate: str | None = None
    logoUrl: str | None = None
    #: Which of the epg-editor lineup's associated `sdLineupIds` this
    #: candidate was resolved against. A station can appear in more than one
    #: associated SD lineup; the same "first `sdLineupId` in `lineup
    #: .sdLineupIds` order wins" rule `generate_suggestions` already applies
    #: is applied here too, for consistency (see `search_stations`'s
    #: docstring).
    sdLineupId: str
    #: `rapidfuzz.fuzz.WRatio` score against the query, normalized to 0-1
    #: (same scale/scoring function as `MappingSuggestion.score` — see
    #: `services.suggestions._score_channel_against_station`). `0.0` for
    #: every result when `query` is empty/whitespace-only (browse mode) —
    #: see `search_stations`'s docstring for why there's no real score to
    #: compute in that case. For a non-empty `query`, this is always
    #: `>= services.suggestions.STATION_SEARCH_MIN_RELEVANCE` — candidates
    #: scoring below that threshold are excluded from `results` entirely
    #: rather than appearing with a low `score` (see
    #: `StationSearchResult.results`'s docstring and
    #: `STATION_SEARCH_MIN_RELEVANCE`'s own docstring for why a literal
    #: `> 0.0` filter wasn't sufficient).
    score: float


class StationSearchResult(BaseModel):
    """Outcome of one `search_stations` call for a single epg-editor lineup."""

    lineupId: str
    #: The query actually searched for, echoed back verbatim (including
    #: whitespace-only/empty) so the frontend can confirm which request a
    #: response belongs to.
    query: str
    #: Number of results actually returned, i.e. `len(results)`. Kept as an
    #: explicit field (rather than leaving callers to compute `len(results)`
    #: themselves) for parity with `SuggestionResult.channelsScored`-style
    #: fields elsewhere in this API, and because its meaning changed once
    #: `candidatePoolSize` was added below: it's no longer "the" count,
    #: just "how many are in *this* response" — which may be less than
    #: `candidatePoolSize` whenever the pool is bigger than `limit`. Kept
    #: rather than dropped since existing/future response consumers may
    #: already read it and it's cheap to keep accurate.
    resultCount: int
    #: Size of the full deduped candidate pool *before* scoring/truncation
    #: to `limit` — mirrors `SuggestionResult.stationPoolSize`'s naming/
    #: intent from the same module. Lets the frontend show e.g. "showing 25
    #: of 340 — type to narrow" in browse mode instead of a silently
    #: truncated list with no hint more results exist.
    candidatePoolSize: int
    #: The subset of `lineup.sdLineupIds` that had no cached station roster
    #: at search time (see `search_stations`'s docstring: a SD lineup with
    #: no cache is silently skipped when building the candidate pool,
    #: rather than erroring or fetching). Surfaced separately so the
    #: frontend can distinguish "genuinely no matches" from "part of the
    #: candidate pool hasn't been fetched yet" — e.g. "N of your associated
    #: SD lineups haven't been fetched yet" — instead of a misleadingly
    #: empty/incomplete result with no explanation.
    uncachedSdLineupIds: list[str] = Field(default_factory=list)
    #: For a non-empty `query`, excludes every candidate scoring below
    #: `services.suggestions.STATION_SEARCH_MIN_RELEVANCE` (dropped before
    #: the `limit` cap, not just hidden) — a below-threshold score isn't
    #: treated as a meaningful match, so a real search never surfaces one
    #: just to pad the list out to `limit`. An earlier version of this
    #: filter only excluded literal `0.0` scores; UAT found that threshold
    #: didn't actually work against a realistic station roster (`WRatio`
    #: essentially never scores exactly `0.0` for two real, non-trivial-
    #: length strings) — see `STATION_SEARCH_MIN_RELEVANCE`'s docstring for
    #: the empirical investigation behind the replacement. This means an
    #: empty `results` list combined with an empty `uncachedSdLineupIds`
    #: means "nothing cleared the minimum-relevance bar" — not "data not
    #: ready yet" (the frontend can rely on that distinction; see
    #: `uncachedSdLineupIds`'s docstring for that half of the signal), but
    #: also not an absolute guarantee that nothing excluded shared any
    #: genuine relationship with the query — see
    #: `STATION_SEARCH_MIN_RELEVANCE`'s docstring for the acknowledged,
    #: unavoidable ambiguity in the score band right around that threshold.
    #: Whitespace-only/empty `query` ("browse mode") is the one exception:
    #: it intentionally still returns every candidate with `score: 0.0`,
    #: since there's no query for them to be irrelevant to — see
    #: `search_stations`'s docstring.
    results: list[StationSearchCandidate] = Field(default_factory=list)
