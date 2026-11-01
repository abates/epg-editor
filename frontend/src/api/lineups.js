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

/**
 * Extracts a human-readable message from a FastAPI JSON error body.
 *
 * FastAPI's default error shape is `{ "detail": "..." }` for
 * `HTTPException`s (e.g. the 404s and the 400 "invalid sdLineupId" case
 * from the mapping endpoint) and `{ "detail": [{ loc, msg, type }, ...] }`
 * for 422 request-validation errors.
 *
 * @param {Response} response
 * @returns {Promise<string | null>} the extracted message, or null if the
 *   body wasn't JSON or didn't have a recognizable `detail`.
 */
async function extractErrorDetail(response) {
  let body;
  try {
    body = await response.json();
  } catch {
    return null;
  }

  const detail = body?.detail;

  if (typeof detail === 'string') {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item?.msg !== 'string') {
          return JSON.stringify(item);
        }
        const field = Array.isArray(item?.loc) ? item.loc.slice(1).join('.') : '';
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join('; ');
  }

  return null;
}

/**
 * Builds the Error thrown for a non-OK response, shared by `request()` and
 * `requestMultipart()` so both surface the same human-readable-message
 * shape.
 *
 * @param {Response} response
 * @param {string} method
 * @param {string} path
 * @returns {Promise<Error>}
 */
async function buildResponseError(response, method, path) {
  const detail = await extractErrorDetail(response);
  const summary = `${method} ${path} failed with status ${response.status}`;
  // Presentational code (components/pages) displays `error.message`
  // directly to the user, so it must be a clean, human-readable string -
  // not the method/path/status/UUID-laden `summary`. When the backend
  // supplied a `detail` (the common case for our FastAPI HTTPExceptions,
  // e.g. the 400 "sdLineupId isn't associated with this lineup" error),
  // that's already human-readable on its own, so use it as the message.
  // `summary` is kept only as a fallback for the rare case where the
  // error body wasn't JSON / had no recognizable `detail`, and is also
  // attached to the thrown error for anyone who wants it for logging.
  const error = new Error(detail ?? summary);
  error.status = response.status;
  error.summary = summary;
  if (detail) {
    error.detail = detail;
  }
  return error;
}

/**
 * Issues a JSON request to the backend and returns the parsed response
 * body, throwing a descriptive Error on any non-OK status.
 *
 * @param {string} path
 * @param {RequestInit} [options]
 * @returns {Promise<unknown>}
 */
async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw await buildResponseError(response, options.method ?? 'GET', path);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

/**
 * Issues a multipart/form-data request (file upload) to the backend and
 * returns the parsed JSON response body, throwing the same kind of
 * descriptive Error as `request()` on any non-OK status.
 *
 * Deliberately does NOT set a `Content-Type` header - the browser has to
 * generate the multipart boundary itself for a `FormData` body, and setting
 * the header manually (even to the right-looking value) breaks that.
 *
 * @param {string} path
 * @param {FormData} formData
 * @param {string} [method]
 * @returns {Promise<unknown>}
 */
async function requestMultipart(path, formData, method = 'POST') {
  const response = await fetch(path, { method, body: formData });

  if (!response.ok) {
    throw await buildResponseError(response, method, path);
  }

  return response.json();
}

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
 * Calls POST /api/lineups/{lineupId}/sync-and-generate: fetches fresh
 * schedule/program data from SchedulesDirect for every confirmed-mapped
 * channel in the lineup, caches it, and regenerates the lineup's XMLTV
 * output file (served at `/xmltv/{lineupId}.xml`).
 *
 * This is a slow, real-network call against the SD API (seconds to tens
 * of seconds) and the backend has no guard against two overlapping calls
 * for the same lineup - callers are responsible for not firing a second
 * request while one is still pending (see `SyncAndGeneratePanel`).
 *
 * Rejects with the extracted `detail` message (via `extractErrorDetail`)
 * for the backend's documented error cases: 404 (lineup doesn't exist),
 * 503 (SD credentials not configured), 502 (SD rejected the request).
 *
 * @param {string} lineupId
 * @returns {Promise<unknown>} the `SyncResult`.
 */
export function syncAndGenerate(lineupId) {
  return request(`/api/lineups/${encodeURIComponent(lineupId)}/sync-and-generate`, {
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
