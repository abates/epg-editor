"""Tests confirming FastAPI's interactive docs live under the reserved
`/api` prefix (CLAUDE.md's "Reserved URL path prefixes"), not at their
default top-level paths, so they can't collide with an SPA client-side
route.

Uses the same per-test "set env vars, build a fresh app" pattern as
`tests/api/test_static.py` (see that module's docstring for why: `app.main.app`
is built once at import time, before a test gets a chance to point
`EPG_EDITOR_FRONTEND_DIR` at a disposable fixture directory). A frontend
fixture is included here too so the "old default paths" assertions can
confirm they now fall through to the ordinary SPA fallback (serving
`index.html`) rather than just asserting "not 200" without saying what they
do return.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def frontend_dir(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa shell</html>", encoding="utf-8")
    return dist


@pytest.fixture
def client(frontend_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("EPG_EDITOR_FRONTEND_DIR", str(frontend_dir))
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as test_client:
        yield test_client


def test_docs_served_under_api_prefix(client):
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "swagger-ui" in response.text.lower()


def test_redoc_served_under_api_prefix(client):
    response = client.get("/api/redoc")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "redoc" in response.text.lower()


def test_openapi_schema_served_under_api_prefix(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    body = response.json()
    assert body["info"]["title"] == "epg-editor"


def test_default_docs_path_falls_back_to_spa_not_docs(client):
    """`/docs` is not reserved, so a GET to it with no matching route now
    falls through to the SPA `index.html` fallback like any other unmatched
    non-API path -- it no longer serves Swagger UI at the old default.
    """
    response = client.get("/docs")
    assert response.status_code == 200
    assert response.text == "<html>spa shell</html>"


def test_default_redoc_path_falls_back_to_spa_not_redoc(client):
    response = client.get("/redoc")
    assert response.status_code == 200
    assert response.text == "<html>spa shell</html>"


def test_default_openapi_json_path_falls_back_to_spa_not_schema(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.text == "<html>spa shell</html>"
