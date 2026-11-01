// Shared HTTP plumbing for every module under frontend/src/api/.
//
// frontend/src/api/ is the only module that issues HTTP requests to the
// epg-editor backend (see CLAUDE.md's "Frontend module layout"). This file
// itself is plain JavaScript - no React/JSX/TypeScript/styled-components -
// just the `fetch` wrapper + FastAPI-error-shape parsing shared by the
// domain-specific client modules (`lineups.js`, `sdAccount.js`, ...), so
// that logic isn't duplicated in each one.
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
export async function extractErrorDetail(response) {
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
export async function request(path, options = {}) {
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
export async function requestMultipart(path, formData, method = 'POST') {
  const response = await fetch(path, { method, body: formData });

  if (!response.ok) {
    throw await buildResponseError(response, method, path);
  }

  return response.json();
}
