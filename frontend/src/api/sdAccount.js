// Vanilla JS HTTP client for the backend's `/api/sd-account/*` endpoints:
// CRUD against the user's real SchedulesDirect *account* lineups (SD's own
// headend subscriptions) and the account's lineup-slot usage.
//
// Kept in its own module, separate from `lineups.js`, because this is a
// conceptually distinct domain from epg-editor's own lineups - mirroring
// the backend's separate `app.api.sd_account`/`app.services.sd_account`
// modules (see CLAUDE.md's Core workflow 2 and `api/sd_account.py`'s
// module docstring). Do not confuse this with `lineups.js`'s
// `updateLineupSdLineups`, which just edits which SD lineup ID *strings*
// one of epg-editor's own lineups references locally - nothing here
// touches `config/lineups.json`.
//
// frontend/src/api/ is the only module that issues HTTP requests to the
// epg-editor backend (see CLAUDE.md's "Frontend module layout"). It is
// plain JavaScript - no React/JSX/TypeScript/styled-components - and is
// imported by `components/`/`pages/` rather than those modules calling
// `fetch` directly. The shared `request()` helper (fetch wrapper +
// FastAPI-error-shape parsing) lives in `httpClient.js`, reused here rather
// than duplicated.

import { request } from './httpClient.js';

/**
 * Calls GET /api/sd-account/lineups: the account's current subscribed SD
 * lineups.
 *
 * Rejects with the extracted `detail` message (see `httpClient.js`'s
 * `extractErrorDetail`) for the backend's documented error cases: 503 (SD
 * credentials not configured server-side), 502 (SD rejected the request).
 *
 * @returns {Promise<Array<{
 *   lineup: string,
 *   name: string,
 *   transport: string | null,
 *   location: string | null,
 *   uri: string | null,
 * }>>}
 */
export function listSdAccountLineups() {
  return request('/api/sd-account/lineups');
}

/**
 * Calls POST /api/sd-account/lineups to subscribe the account to
 * `lineupId`. This consumes one of the account's limited lineup slots and
 * one of its "changes remaining" allowance - a real mutation against the
 * user's SD account, not a local-only change.
 *
 * Rejects with the extracted `detail` message for the backend's documented
 * error cases: 422 (`lineupId` empty or containing characters other than
 * letters/digits/hyphens), 503/502 as above (e.g. the lineup id doesn't
 * exist, or the account is already at its lineup limit).
 *
 * @param {string} lineupId
 * @returns {Promise<{
 *   response: string | null,
 *   code: number,
 *   serverID: string | null,
 *   message: string | null,
 *   changesRemaining: number | null,
 *   datetime: string | null,
 * }>}
 */
export function addSdAccountLineup(lineupId) {
  return request('/api/sd-account/lineups', {
    method: 'POST',
    body: JSON.stringify({ lineupId }),
  });
}

/**
 * Calls DELETE /api/sd-account/lineups/{lineupId} to unsubscribe the
 * account from `lineupId`. Also a real mutation against the user's SD
 * account.
 *
 * Rejects with the extracted `detail` message for the backend's documented
 * error cases: 422 (malformed `lineupId`), 503/502 (e.g. the account isn't
 * subscribed to that lineup).
 *
 * @param {string} lineupId
 * @returns {Promise<{
 *   response: string | null,
 *   code: number,
 *   serverID: string | null,
 *   message: string | null,
 *   changesRemaining: number | null,
 *   datetime: string | null,
 * }>}
 */
export function removeSdAccountLineup(lineupId) {
  return request(`/api/sd-account/lineups/${encodeURIComponent(lineupId)}`, {
    method: 'DELETE',
  });
}

/**
 * Calls GET /api/sd-account/limit: how many of the account's lineup slots
 * are used vs. the total allowed. Intended to be fetched proactively (per
 * CLAUDE.md's Core workflow 2 - "surface that limit in the UI rather than
 * discovering it via a failed API call") rather than only on a failed
 * `addSdAccountLineup` call.
 *
 * `maxLineups` can be `null` if SD's `/status` response didn't include it -
 * treat that as "limit unknown," not as zero/unlimited. `lineupsUsed` is a
 * conservative count that includes lineups SD has marked `isDeleted` on
 * their side; `deletedLineupCount` says how many of that total are in that
 * state, so callers can caveat the display rather than hiding the nuance.
 *
 * Rejects with the extracted `detail` message for the backend's documented
 * error cases: 503/502 as above.
 *
 * @returns {Promise<{
 *   maxLineups: number | null,
 *   lineupsUsed: number,
 *   deletedLineupCount: number,
 * }>}
 */
export function getSdAccountLineupLimit() {
  return request('/api/sd-account/limit');
}
