"""FastAPI application entrypoint.

Wires routers under the reserved `/api/*` and `/xmltv/*` prefixes and
bootstraps the `/data` directory tree on startup via `app.storage`.
Business logic lives in `app.services`, not here (see CLAUDE.md's backend
module layout).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, lineups, m3u, suggestions, sync, xmltv
from app.storage.paths import ensure_data_dirs


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ensure `config/`, `cache/`, and `output/` exist before serving."""
    ensure_data_dirs()
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(title="epg-editor", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(lineups.router, prefix="/api")
    app.include_router(m3u.router, prefix="/api")
    app.include_router(sync.router, prefix="/api")
    app.include_router(suggestions.router, prefix="/api")
    # `/xmltv/*` is its own reserved top-level prefix (see CLAUDE.md's
    # "Reserved URL path prefixes") — registered directly on the app, not
    # nested under `/api`.
    app.include_router(xmltv.router)
    return app


app = create_app()
