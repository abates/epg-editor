// Vanilla JS HTTP client for the backend's health-check endpoint.
//
// frontend/src/api/ is the only module that issues HTTP requests to the
// epg-editor backend (see CLAUDE.md's "Frontend module layout"). It is
// plain JavaScript - no React/JSX/TypeScript/styled-components - and is
// imported by `components/`/`pages/` rather than those modules calling
// `fetch` directly.
//
// Requests are made against a relative path so this module works
// regardless of where the frontend is served from: in production the
// backend serves the API and the built frontend from the same origin,
// and in dev the Vite dev server proxies `/api` to the backend (see
// vite.config.ts).

/**
 * Calls GET /api/health and returns the parsed JSON body.
 *
 * @returns {Promise<unknown>} the parsed JSON response body.
 * @throws {Error} if the request fails or the response is not OK.
 */
export async function getHealth() {
  const response = await fetch('/api/health');

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }

  return response.json();
}
