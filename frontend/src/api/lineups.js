// Vanilla JS HTTP client for the backend's lineup/channel/mapping endpoints
// under /api/lineups.
//
// frontend/src/api/ is the only module that issues HTTP requests to the
// epg-editor backend (see CLAUDE.md's "Frontend module layout"). It is
// plain JavaScript - no React/JSX/TypeScript/styled-components - and is
// imported by `components/`/`pages/` rather than those modules calling
// `fetch` directly.
//
// Requests are made against relative paths so this module works regardless
// of where the frontend is served from: in production the backend serves
// the API and the built frontend from the same origin, and in dev the Vite
// dev server proxies `/api` to the backend (see vite.config.ts).
//
// The actual `fetch` wrapper + FastAPI-error-shape parsing (`request()`/
// `requestMultipart()`) live in `httpClient.js`, shared with the other
// domain-specific client modules (e.g. `sdAccount.js`) rather than
// duplicated here.

import { request, requestMultipart } from './httpClient.js';

/**
 * Calls GET /api/lineups.
 *
 * @returns {Promise<unknown[]>} the list of lineups.
 */
export function listLineups() {
  return request('/api/lineups');
}

/**
 * Calls POST /api/lineups to create a new, empty, manually-sourced lineup.
 *
 * @param {{ name: string }} params
 * @returns {Promise<unknown>} the created lineup.
 */
export function createLineup({ name }) {
  return request('/api/lineups', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

/**
 * Calls GET /api/lineups/{lineupId}.
 *
 * @param {string} lineupId
 * @returns {Promise<unknown>} the lineup.
 */
export function getLineup(lineupId) {
  return request(`/api/lineups/${encodeURIComponent(lineupId)}`);
}

/**
 * Calls DELETE /api/lineups/{lineupId}, permanently removing the lineup
 * and all of its channels/mappings from `config/lineups.json`.
 *
 * @param {string} lineupId
 * @returns {Promise<null>}
 */
export function deleteLineup(lineupId) {
  return request(`/api/lineups/${encodeURIComponent(lineupId)}`, { method: 'DELETE' });
}

/**
 * Calls PUT /api/lineups/{lineupId}/sd-lineups, replacing the lineup's
 * entire list of associated SchedulesDirect lineup ids.
 *
 * @param {string} lineupId
 * @param {string[]} sdLineupIds
 * @returns {Promise<unknown>} the updated lineup.
 */
export function updateLineupSdLineups(lineupId, sdLineupIds) {
  return request(`/api/lineups/${encodeURIComponent(lineupId)}/sd-lineups`, {
    method: 'PUT',
    body: JSON.stringify({ sdLineupIds }),
  });
}

/**
 * Calls POST /api/lineups/{lineupId}/channels to manually add a channel.
 *
 * @param {string} lineupId
 * @param {{
 *   name: string,
 *   number?: string | null,
 *   logoUrl?: string | null,
 *   tvgId?: string | null,
 *   sourceStreamUrl?: string | null,
 * }} fields
 * @returns {Promise<unknown>} the created channel.
 */
export function addChannel(lineupId, fields) {
  return request(`/api/lineups/${encodeURIComponent(lineupId)}/channels`, {
    method: 'POST',
    body: JSON.stringify(fields),
  });
}

/**
 * Calls PUT /api/lineups/{lineupId}/channels/{channelId}. Every field is
 * optional server-side: a field omitted from `fields` is left unchanged, and
 * a field explicitly sent as `null` clears it (if it's nullable, e.g.
 * `logoUrl`). Sending `null` for a required, non-nullable field (currently
 * just `name`) is rejected by the backend with a 400, not applied.
 *
 * @param {string} lineupId
 * @param {string} channelId
 * @param {{
 *   name?: string | null,
 *   number?: string | null,
 *   logoUrl?: string | null,
 *   tvgId?: string | null,
 *   sourceStreamUrl?: string | null,
 * }} fields
 * @returns {Promise<unknown>} the updated channel.
 */
export function updateChannel(lineupId, channelId, fields) {
  return request(
    `/api/lineups/${encodeURIComponent(lineupId)}/channels/${encodeURIComponent(channelId)}`,
    {
      method: 'PUT',
      body: JSON.stringify(fields),
    },
  );
}

/**
 * Calls DELETE /api/lineups/{lineupId}/channels/{channelId}.
 *
 * @param {string} lineupId
 * @param {string} channelId
 * @returns {Promise<null>}
 */
export function removeChannel(lineupId, channelId) {
  return request(
    `/api/lineups/${encodeURIComponent(lineupId)}/channels/${encodeURIComponent(channelId)}`,
    { method: 'DELETE' },
  );
}

/**
 * Calls PUT /api/lineups/{lineupId}/channels/{channelId}/mapping to
 * directly set (or confirm) a channel's SD station mapping.
 *
 * The backend returns 400 if `sdLineupId` isn't one of the lineup's
 * associated `sdLineupIds` - that case surfaces as a rejected promise with
 * the backend's actual error message (see `extractErrorDetail`), not a
 * generic failure.
 *
 * @param {string} lineupId
 * @param {string} channelId
 * @param {{ sdStationId: string, sdLineupId: string, confirmed?: boolean }} params
 * @returns {Promise<unknown>} the updated channel.
 */
export function setChannelMapping(lineupId, channelId, { sdStationId, sdLineupId, confirmed }) {
  const body = { sdStationId, sdLineupId };
  if (confirmed !== undefined) {
    body.confirmed = confirmed;
  }

  return request(
    `/api/lineups/${encodeURIComponent(lineupId)}/channels/${encodeURIComponent(channelId)}/mapping`,
    {
      method: 'PUT',
      body: JSON.stringify(body),
    },
  );
}

/**
 * Calls POST /api/lineups/{lineupId}/suggestions: (re)scores candidate SD
 * stations - from the deduped union of the lineup's associated
 * `sdLineupIds` - against every channel in the lineup, and overwrites each
 * channel's `mapping.suggestions` with the result (capped at the top 5
 * highest-scoring candidates per channel; see `docs/data-model.md`'s
 * `suggestions` notes for the scoring/dedup rules). This is a real-network
 * call against the SD API (fetching/caching station rosters on a cache
 * miss) and can take a few seconds.
 *
 * The returned `SuggestionResult` does NOT include the actual suggestions -
 * those live on each channel's own (unreturned-here) `mapping.suggestions`
 * field, so callers must `getLineup(lineupId)` afterward to see them
 * reflected (see `SuggestionsPanel`).
 *
 * Rejects with the extracted `detail` message for the backend's documented
 * error cases: 404 (lineup doesn't exist), 503 (SD credentials not
 * configured), 502 (SD/auth failure fetching a station roster).
 *
 * @param {string} lineupId
 * @returns {Promise<unknown>} the `SuggestionResult`.
 */
export function generateSuggestions(lineupId) {
  return request(`/api/lineups/${encodeURIComponent(lineupId)}/suggestions`, {
    method: 'POST',
  });
}

/**
 * Calls POST /api/lineups/{lineupId}/bulk-accept-suggestions: confirms the
 * mapping for every channel with an unconfirmed mapping whose top
 * suggestion is unambiguously highest-scoring (ties are skipped, left for
 * manual review - intentional, not a bug) and at/above the backend's fixed
 * confidence threshold (not a UI control - see CLAUDE.md's Core workflow
 * #4). Pure local computation against already-cached suggestions, no SD
 * network call.
 *
 * The returned `BulkAcceptResult` doesn't include full updated `Channel`
 * objects either - callers must `getLineup(lineupId)` afterward to see the
 * newly-confirmed mappings (see `SuggestionsPanel`).
 *
 * Rejects with the extracted `detail` message for the backend's documented
 * error case: 404 (lineup doesn't exist).
 *
 * @param {string} lineupId
 * @returns {Promise<unknown>} the `BulkAcceptResult`.
 */
export function bulkAcceptSuggestions(lineupId) {
  return request(`/api/lineups/${encodeURIComponent(lineupId)}/bulk-accept-suggestions`, {
    method: 'POST',
  });
}

/**
 * Calls POST /api/lineups/import-m3u (multipart/form-data: `name` + `file`)
 * to create a brand-new, `m3u`-sourced lineup from an uploaded M3U
 * playlist. Every parsed entry comes back in `result.added` since the
 * lineup starts out empty.
 *
 * Rejects with the extracted `detail` message for the backend's documented
 * error cases: 400 (upload too large, or not parseable as M3U at all).
 *
 * @param {string} name
 * @param {File} file
 * @returns {Promise<{ lineup: unknown, result: { added: unknown[], updated: unknown[], flaggedMissing: unknown[] } }>}
 */
export function importM3u(name, file) {
  const formData = new FormData();
  formData.append('name', name);
  formData.append('file', file);
  return requestMultipart('/api/lineups/import-m3u', formData);
}

/**
 * Calls POST /api/lineups/{lineupId}/import-m3u (multipart/form-data: just
 * `file`) to re-import an uploaded M3U playlist into an existing
 * `m3u`-sourced lineup, merging by `tvgId` (fallback: channel number) - see
 * `docs/data-model.md`'s `missingSince` notes for the merge contract.
 *
 * The returned `lineup` already reflects the fully-merged, persisted state
 * - callers don't need to separately `getLineup()` after a successful call.
 *
 * Rejects with the extracted `detail` message for the backend's documented
 * error cases: 404 (lineup doesn't exist), 400 (upload too large, not
 * parseable as M3U, or the lineup's `source` isn't `"m3u"`).
 *
 * @param {string} lineupId
 * @param {File} file
 * @returns {Promise<{ lineup: unknown, result: { added: unknown[], updated: unknown[], flaggedMissing: unknown[] } }>}
 */
export function reimportM3u(lineupId, file) {
  const formData = new FormData();
  formData.append('file', file);
  return requestMultipart(
    `/api/lineups/${encodeURIComponent(lineupId)}/import-m3u`,
    formData,
  );
}
