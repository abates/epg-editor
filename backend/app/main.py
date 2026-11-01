"""FastAPI application entrypoint.

Wires routers under the reserved `/api/*` and `/xmltv/*` prefixes and
bootstraps the `/data` directory tree on startup via `app.storage`.
Business logic lives in `app.services`, not here (see CLAUDE.md's backend
module layout).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, lineups, m3u, refresh, sd_account, suggestions, xmltv
from app.scheduler.jobs import create_scheduler
from app.storage.paths import ensure_data_dirs


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ensure `config/`, `cache/`, and `output/` exist, and run the
    periodic SD refresh job (`app.scheduler.jobs`) for the lifetime of the
    app process.

    The scheduler is started here (not at import time) and explicitly shut
    down on app shutdown, matching the rest of this function's "bootstrap
    on startup" pattern. Stored on `app.state.scheduler` so tests/other
    code can inspect its registered jobs (e.g. to verify the refresh job
    was registered at the configured interval) without reaching into
    `app.scheduler.jobs`'s module internals.
    """
    ensure_data_dirs()
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(title="epg-editor", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(lineups.router, prefix="/api")
    app.include_router(m3u.router, prefix="/api")
    app.include_router(refresh.router, prefix="/api")
    app.include_router(suggestions.router, prefix="/api")
    app.include_router(sd_account.router, prefix="/api")
    # `/xmltv/*` is its own reserved top-level prefix (see CLAUDE.md's
    # "Reserved URL path prefixes") — registered directly on the app, not
    # nested under `/api`.
    app.include_router(xmltv.router)
    return app


app = create_app()
