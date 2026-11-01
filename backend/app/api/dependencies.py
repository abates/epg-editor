"""Shared FastAPI dependencies for `api/` routers.

Currently just `get_sd_client`, used by every router that needs a real
`SdClient` (`api/refresh.py`, `api/suggestions.py`, `api/sd_account.py`).
Factored out into its own module (rather than living on one of those
routers) so no router has to import another router's internals just to get
a shared dependency.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import HTTPException

from app.sd_client.client import SdClient, SdCredentialsNotConfiguredError


async def get_sd_client() -> AsyncIterator[SdClient]:
    """FastAPI dependency: a real `SdClient` built from env-var credentials.

    `SdClient.from_env()` is the one and only place in the codebase that
    constructs a real `httpx.AsyncClient` (see its docstring) — this module
    deliberately never imports `httpx` itself, so there's exactly one place
    that owns the real-network timeout/transport configuration.

    A generator dependency (rather than a plain module-level call inside
    the route) so the real client is scoped per-request and explicitly
    closed afterward (`async with sd_client`, delegating to
    `SdClient.aclose()`) rather than leaked, and so tests can swap in a
    mock-transport-backed `SdClient` via
    `app.dependency_overrides[get_sd_client]` — per CLAUDE.md, no real SD
    credentials or network are ever touched in the test suite.

    Missing/empty `SD_USERNAME`/`SD_PASSWORD` raises
    `SdCredentialsNotConfiguredError` from `SdClient.from_env()`, mapped
    here to a clean 503 rather than letting it surface as a raw exception.
    """
    try:
        sd_client = SdClient.from_env()
    except SdCredentialsNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    async with sd_client:
        yield sd_client
