// Vanilla JS HTTP client for the backend's `/xmltv/*` static-file serving
// prefix (see CLAUDE.md's "Reserved URL path prefixes" -
// `backend/app/api/xmltv.py`).
//
// frontend/src/api/ is the only module that issues HTTP requests to the
// epg-editor backend (see CLAUDE.md's "Frontend module layout"). It is
// plain JavaScript - no React/JSX/TypeScript/styled-components - and is
// imported by `components/`/`pages/` rather than those modules calling
// `fetch` directly.
//
// This module intentionally does NOT use `httpClient.js`'s `request()`
// helper: `request()` always parses the response body as JSON and throws
// on a non-OK status, which is the wrong shape for a plain existence
// check against a binary/XML static-file endpoint. It also deliberately
// does not funnel a 404 into a thrown Error - a 404 here is an entirely
// expected, common state (XMLTV hasn't been generated yet), not a failure.

/**
 * Builds the absolute, browser-origin URL for a lineup's generated XMLTV
 * file - what a user would point Plex/Jellyfin at.
 *
 * @param {string} lineupId
 * @returns {string}
 */
export function getXmltvUrl(lineupId) {
  return `${window.location.origin}/xmltv/${encodeURIComponent(lineupId)}.xml`;
}

/**
 * Checks whether a lineup's XMLTV file has actually been generated yet, by
 * issuing a `HEAD` request against its serving URL
 * (`/xmltv/{lineupId}.xml` in `backend/app/api/xmltv.py`, whose route
 * explicitly adds `HEAD` support via a stacked `@router.head(...,
 * include_in_schema=False)` alongside `@router.get(...)` - FastAPI/Starlette
 * does NOT answer `HEAD` automatically for a plain `@router.get`). This is a
 * cheap existence check - no response body is downloaded/parsed - and
 * reflects the real on-disk state rather than inferring it from anything
 * indirect (e.g. "has a mapped channel"), since the backend has no
 * persisted "generated" field to query directly.
 *
 * Network errors (offline, CORS misconfiguration, etc.) are treated as
 * "not generated" rather than thrown - callers show a "not generated yet"
 * state either way, and a transient network hiccup here shouldn't crash
 * the page.
 *
 * @param {string} lineupId
 * @returns {Promise<boolean>} whether the file exists (HTTP 200 on HEAD).
 */
export async function checkXmltvExists(lineupId) {
  try {
    const response = await fetch(getXmltvUrl(lineupId), { method: 'HEAD' });
    return response.ok;
  } catch {
    return false;
  }
}
