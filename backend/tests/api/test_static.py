"""Tests for the static-frontend serving in `app.api.static`.

Uses `EPG_EDITOR_FRONTEND_DIR` (and `EPG_EDITOR_DATA_DIR`, since the app
bootstraps the data dir on startup regardless) to point at a disposable
fixture directory standing in for the real `frontend/dist` build output, so
these tests don't depend on a real frontend build existing next to the
backend.

`app.main.app` is built once at import time (`create_app()` runs at module
scope in `app.main`), so `register_static_frontend` already ran against
whatever `EPG_EDITOR_FRONTEND_DIR` was set to at import time -- before these
tests get a chance to set it per-test. Each test therefore constructs a
fresh app via `app.main.create_app()` *after* setting the env var, rather
than reusing the module-level `app` singleton.
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
    assets = dist / "assets"
    assets.mkdir()
    (assets / "main.js").write_text("console.log('hi');", encoding="utf-8")
    (dist / "favicon.ico").write_text("fake-favicon", encoding="utf-8")
    return dist


@pytest.fixture
def client(frontend_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("EPG_EDITOR_FRONTEND_DIR", str(frontend_dir))
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as test_client:
        yield test_client


def test_root_serves_index_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "<html>spa shell</html>"


def test_deep_spa_route_falls_back_to_index_html(client):
    response = client.get("/some/deep/client/route")
    assert response.status_code == 200
    assert response.text == "<html>spa shell</html>"


def test_existing_asset_under_assets_dir_is_served_not_index(client):
    response = client.get("/assets/main.js")
    assert response.status_code == 200
    assert response.text == "console.log('hi');"


def test_existing_top_level_asset_is_served_not_index(client):
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.text == "fake-favicon"


def test_unmatched_api_subpath_still_404s_not_index_html(client):
    response = client.get("/api/this-path-does-not-exist")
    assert response.status_code == 404
    assert response.text != "<html>spa shell</html>"


def test_bare_api_prefix_still_404s(client):
    response = client.get("/api")
    assert response.status_code == 404


def test_unmatched_xmltv_subpath_still_404s_not_index_html(client):
    response = client.get("/xmltv/this-path-does-not-exist")
    assert response.status_code == 404
    assert response.text != "<html>spa shell</html>"


def test_bare_xmltv_prefix_still_404s(client):
    response = client.get("/xmltv")
    assert response.status_code == 404


def test_real_api_health_endpoint_still_works(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_asset_file_404s_not_index_html(client):
    response = client.get("/assets/missing-file-that-does-not-exist.js")
    assert response.status_code == 404
    assert response.text != "<html>spa shell</html>"


def test_bare_assets_prefix_404s_not_index_html(client):
    response = client.get("/assets/")
    assert response.status_code == 404
    assert response.text != "<html>spa shell</html>"


def test_app_raised_404_under_api_keeps_original_detail_not_index_html(client):
    """Regression test for the docstring-accuracy fix: a 404 explicitly
    raised by `app.api.lineups` (not a routing miss) must pass through the
    static-frontend exception handler unchanged -- same status, same JSON
    `detail` -- because it's reserved via `/api`, not because the handler
    tells routing misses apart from app-raised 404s.
    """
    response = client.get("/api/lineups/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "lineup 'does-not-exist' not found"}


def test_null_byte_in_path_returns_clean_response_not_500(client):
    response = client.get("/foo%00bar")
    assert response.status_code == 200
    assert response.text == "<html>spa shell</html>"


def test_null_byte_in_assets_path_404s_not_500(client):
    response = client.get("/assets/foo%00bar")
    assert response.status_code == 404


def test_non_get_to_unmatched_non_reserved_path_404s_not_405(client):
    response = client.delete("/some/deep/client/route")
    assert response.status_code == 404
    assert response.text != "<html>spa shell</html>"


def test_missing_frontend_dir_does_not_crash_app_startup(tmp_path, monkeypatch):
    missing_dir = tmp_path / "does" / "not" / "exist"
    monkeypatch.setenv("EPG_EDITOR_FRONTEND_DIR", str(missing_dir))
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path / "data"))

    with TestClient(create_app()) as test_client:
        response = test_client.get("/")
        health_response = test_client.get("/api/health")

    assert response.status_code == 404
    assert health_response.status_code == 200


def test_missing_frontend_dir_logs_a_warning(tmp_path, monkeypatch, caplog):
    missing_dir = tmp_path / "does" / "not" / "exist"
    monkeypatch.setenv("EPG_EDITOR_FRONTEND_DIR", str(missing_dir))
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path / "data"))

    with caplog.at_level("WARNING", logger="app.api.static"):
        with TestClient(create_app()):
            pass

    assert any(
        "Static frontend not found" in record.message for record in caplog.records
    )
