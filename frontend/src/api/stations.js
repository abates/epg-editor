// Vanilla JS HTTP client for the cache-only SD station search endpoint
// (backlog item 37) under /api/lineups/{lineupId}/station-search.
//
// frontend/src/api/ is the only module that issues HTTP requests to the
// epg-editor backend (see CLAUDE.md's "Frontend module layout"). It is
// plain JavaScript - no React/JSX/TypeScript/styled-components - and is
// imported by `components/`/`pages/` rather than those modules calling
// `fetch` directly.
//
// Kept in its own module (rather than folded into `lineups.js`) because it
// backs a different concern - a free-text/browse search over a lineup's
// cached candidate station pool, not lineup/channel/mapping CRUD - mirroring
// how the backend keeps `models/station_search.py` separate from
// `models/suggestions.py` for the same reason.
//
// This module does not debounce - that's left to the calling component
// (see `ChannelMappingForm.tsx`), which is better positioned to decide how
// typing pauses map to requests (e.g. firing immediately for the initial
// empty-query "browse mode" load vs. debouncing keystrokes).

import { request } from './httpClient.js';

/**
 * Calls GET /api/lineups/{lineupId}/station-search.
 *
 * Cache-only: never triggers a live SchedulesDirect call (see
 * `backend/app/services/suggestions.py`'s `search_stations`). An empty/
 * whitespace `q` ("browse mode") returns the full deduped candidate pool
 * sorted by name, each with `score: 0.0`; a non-empty `q` returns only
 * candidates that scored `> 0.0`, ranked by score descending.
 *
 * Rejects with the extracted `detail` message for the backend's documented
 * error case: 404 (lineup doesn't exist).
 *
 * @param {string} lineupId
 * @param {{ q?: string, limit?: number }} [params] `limit` is left to the
 *   backend's own default (25) when omitted; the backend rejects values
 *   outside [1, 100] with a 422, so don't pass one out of that range.
 * @returns {Promise<unknown>} the `StationSearchResult`.
 */
export function searchStations(lineupId, { q = '', limit } = {}) {
  const params = new URLSearchParams();
  if (q) {
    params.set('q', q);
  }
  if (limit !== undefined) {
    params.set('limit', String(limit));
  }
  const queryString = params.toString();

  return request(
    `/api/lineups/${encodeURIComponent(lineupId)}/station-search${queryString ? `?${queryString}` : ''}`,
  );
}
