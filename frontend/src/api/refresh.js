// Vanilla JS HTTP client for the backend's global refresh pipeline trigger:
// `POST /api/refresh-now`.
//
// Kept in its own module, separate from `lineups.js`, because this is not
// scoped to a single epg-editor lineup the way everything in `lineups.js`
// is - it runs the same pipeline as the APScheduler job in
// `backend/app/scheduler/jobs.py` across *every* lineup in one call. Mirrors
// `sdAccount.js`'s precedent of splitting out a conceptually distinct
// domain into its own api module rather than overloading `lineups.js`.
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
 * Calls POST /api/refresh-now: runs the global SD refresh + XMLTV
 * regeneration pipeline immediately, across every epg-editor lineup (not
 * just one). This is the manual "do it now" counterpart to the
 * APScheduler job that runs the same pipeline on a timer
 * (`EPG_EDITOR_REFRESH_INTERVAL` hours) - calling this does not reset or
 * otherwise affect that schedule.
 *
 * This is a slow, real-network call against the SD API (can take tens of
 * seconds to minutes depending on how many lineups/stations/schedule-days
 * need refreshing) and the backend has no guard against two overlapping
 * calls - callers are responsible for not firing a second request while
 * one is still pending (see `RefreshNowPanel`).
 *
 * A successful (200) response can still contain a non-empty `errors`
 * array - partial failures at the SD-lineup/lineup/station/programs level
 * don't abort the whole run, so callers should surface `errors`
 * separately from the success counts rather than treating a 200 as
 * unconditional success.
 *
 * Rejects with the extracted `detail` message (via `extractErrorDetail`)
 * for the backend's documented error cases: 503 (SD credentials not
 * configured server-side), 502 (SD account/auth-level failure).
 *
 * @returns {Promise<unknown>} the `RefreshResult`.
 */
export function refreshNow() {
  return request('/api/refresh-now', { method: 'POST' });
}
