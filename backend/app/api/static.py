"""Static frontend serving: built React SPA asset mount + `index.html`
fallback.

This is the only place that serves the frontend's built static files. It's
intentionally outside the `storage/` module: `storage/` owns reads/writes
under the `/data` tree (`config/`, `cache/`, `output/`, see CLAUDE.md's
"Persistent data layout"), and the built frontend isn't part of that
tree -- it's a build artifact staged by the Dockerfile at a path outside
`/data` entirely. This module stays a thin "serve a file" concern with zero
business logic, consistent with the rest of `app.api`'s module layout.

Implementation note: the SPA fallback is wired as a *404 exception handler*
on the FastAPI app, not an extra catch-all `@router.get("/{full_path:path}")`
route. An earlier version of this module used a catch-all route, but that
has a subtle correctness bug: Starlette matches routes by path first and
method second, so a glob route matching *every* path (to serve `index.html`
for arbitrary SPA deep links) also intercepts non-GET requests to paths no
other router claims -- turning what should be a plain 404 (no route
matches at all) into a 405 (a route's path matched, but not its method),
which broke existing routing tests for e.g. `DELETE` to a malformed
`/api/...` path. Hooking the *absence* of any route match (a genuine
Starlette/FastAPI 404) instead sidesteps that: it never changes what does
or doesn't match, it only decides, after routing has already failed to
find anything, whether to serve a frontend asset/`index.html` or let the
original 404 through unchanged.

Note this exception handler is registered app-wide: it catches *every*
`StarletteHTTPException` with status 404, not just ones produced by "no
route matched at all" routing failures. That includes 404s explicitly
raised by application code (e.g. `lineups`'s "lineup not found", or
`xmltv`'s "no generated file yet"). What keeps those from being swallowed
into an `index.html` response isn't the handler distinguishing "routing
miss" from "app-raised" -- it has no way to do that -- it's the reserved-
prefix check (`_is_reserved_path`, matched against `/api`, `/xmltv`, and
`/assets`) below: any 404 for a path under one of those prefixes is passed
through unchanged regardless of why it was raised. Every 404 application
code raises in this codebase today lives under one of those prefixes, so
this is safe, but it's a convention this module relies on, not a guarantee
it enforces structurally.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

#: Overrides where the built frontend (Vite's `frontend/dist` build output)
#: is found, mirroring `storage.paths.DATA_DIR_ENV_VAR`'s env-var pattern so
#: this is testable/dev-overridable without relying on the default path.
#:
#: Default is computed relative to this file rather than hardcoded, and
#: lands on the right place in both environments:
#:   - In the root Dockerfile's backend stage, `WORKDIR /app/backend` and
#:     `COPY backend/ ./` put this file at `/app/backend/app/api/static.py`,
#:     and `COPY --from=frontend-build /app/frontend/dist /app/frontend/dist`
#:     stages the build output at `/app/frontend/dist` -- a sibling of
#:     `/app/backend`, not nested under it. `parents[3]` from this file is
#:     `/app` there, so `parents[3] / "frontend" / "dist"` is
#:     `/app/frontend/dist`. Confirmed against the actual Dockerfile, not
#:     assumed.
#:   - In a local checkout, this file is at
#:     `<repo>/backend/app/api/static.py`, so `parents[3]` is `<repo>`, and
#:     the same expression resolves to `<repo>/frontend/dist` -- where
#:     `npm run build` (run manually from `frontend/`) also leaves its
#:     output.
FRONTEND_DIR_ENV_VAR = "EPG_EDITOR_FRONTEND_DIR"
_DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"

_logger = logging.getLogger(__name__)

#: Top-level path segments owned by other routers (or by the `/assets`
#: `StaticFiles` mount below). The SPA fallback must never serve
#: `index.html` for an unmatched sub-path under these -- it must let the
#: original 404 through instead, so a typo'd/missing API or XMLTV path, or
#: a stale/renamed hashed asset filename, doesn't silently look like a
#: successful frontend route (or get served with the wrong content type).
_RESERVED_TOP_LEVEL_SEGMENTS = {"api", "xmltv", "assets"}


def get_frontend_dir() -> Path:
    """Return the configured built-frontend directory.

    Controlled by the ``EPG_EDITOR_FRONTEND_DIR`` environment variable
    (defaulting to the path the root Dockerfile's layout resolves to),
    mirroring `storage.paths.get_data_dir`'s pattern.
    """
    return Path(os.environ.get(FRONTEND_DIR_ENV_VAR, str(_DEFAULT_FRONTEND_DIR)))


def _is_reserved_path(full_path: str) -> bool:
    """True if `full_path` is, or starts with, a reserved top-level prefix."""
    first_segment = full_path.split("/", 1)[0]
    return first_segment in _RESERVED_TOP_LEVEL_SEGMENTS


def _safe_file_in_dir(directory: Path, relative_path: str) -> Path | None:
    """Resolve `relative_path` under `directory`, refusing traversal outside it.

    Returns the resolved `Path` if it names an existing file inside
    `directory`, else `None` -- including when `relative_path` would escape
    `directory` (e.g. via `..` segments), or when resolving/stat-ing it
    raises `ValueError`/`OSError` (e.g. a request path containing an
    embedded null byte, which `Path.resolve()` rejects with `ValueError`
    rather than treating as "not found"). Any of those cases is treated the
    same as a plain missing file -- the caller falls back to `index.html`
    (or, for a reserved/`/assets` path, to the original 404) rather than
    letting the exception propagate into an unhandled 500.
    """
    try:
        candidate = (directory / relative_path).resolve()
        resolved_dir = directory.resolve()
        candidate.relative_to(resolved_dir)
        is_file = candidate.is_file()
    except (ValueError, OSError):
        return None
    return candidate if is_file else None


def register_static_frontend(app: FastAPI) -> None:
    """Mount the built frontend's static assets and register the SPA
    `index.html` fallback -- but only if a built frontend is actually
    present at `get_frontend_dir()`.

    If the configured frontend directory doesn't exist or doesn't contain
    an `index.html` (expected in local dev -- `uv run uvicorn
    app.main:app --reload` has no frontend build sitting next to it -- and
    in the backend test suite, which doesn't want a frontend build as a
    prerequisite), this is a deliberate no-op: no mount, no fallback
    handler get registered, so the app still starts cleanly and unmatched
    paths just fall through to FastAPI's normal 404 instead of crashing on
    a `StaticFiles(directory=...)` pointed at a missing directory.

    That no-op is silent at the "app still starts" level by design (local
    dev/tests shouldn't need a frontend build), but it's still logged as a
    warning so the equivalent situation in production -- the configured
    `EPG_EDITOR_FRONTEND_DIR` missing or incomplete, e.g. from a broken
    image build or a misconfigured override -- shows up in the server log
    instead of manifesting only as "the site serves bare 404s for
    everything."
    """
    frontend_dir = get_frontend_dir()
    index_file = frontend_dir / "index.html"
    if not frontend_dir.is_dir() or not index_file.is_file():
        _logger.warning(
            "Static frontend not found at %s (set via %s) -- no index.html "
            "there, so the SPA/static-asset routes will not be registered "
            "and all non-API/XMLTV paths will 404. This is expected in "
            "local dev/tests without a frontend build, but likely a "
            "misconfiguration in production.",
            frontend_dir,
            FRONTEND_DIR_ENV_VAR,
        )
        return

    assets_dir = frontend_dir / "assets"
    if assets_dir.is_dir():
        # Vite's default build output puts hashed JS/CSS bundles under
        # `dist/assets/`. A dedicated `StaticFiles` mount gets proper
        # content-type/ETag/range-request handling for those, and (being an
        # ordinary route) is matched by Starlette the normal way -- it never
        # reaches the 404 handler below at all for a request it actually
        # serves.
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="frontend-assets",
        )

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback_or_404(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        """Registered app-wide, this intercepts *every* `StarletteHTTPException`
        with status 404 -- not just "no route matched" routing failures, but
        also any 404 explicitly raised by application code (e.g. a real
        `/api/lineups/{id}` "not found"). It overrides the response -- serving
        a matching frontend asset or falling back to `index.html` for the
        SPA's client-side router -- only for a GET/HEAD request whose path is
        NOT under a reserved top-level segment (`/api`, `/xmltv`, `/assets`;
        see `_RESERVED_TOP_LEVEL_SEGMENTS`). Everything else -- non-404s,
        non-GET/HEAD requests, or any path under a reserved prefix, whether
        its 404 came from routing or from application code -- is passed
        through to FastAPI's normal handling, original status/body untouched.
        """
        full_path = request.url.path.lstrip("/")
        if (
            exc.status_code == 404
            and request.method in ("GET", "HEAD")
            and not _is_reserved_path(full_path)
        ):
            asset_path = _safe_file_in_dir(frontend_dir, full_path) if full_path else None
            return FileResponse(asset_path if asset_path is not None else index_file)
        return await http_exception_handler(request, exc)
