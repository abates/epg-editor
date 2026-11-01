"""Health-check endpoint and data-directory bootstrap tests."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok_and_bootstraps_data_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path))

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    assert (tmp_path / "config").is_dir()
    assert (tmp_path / "cache").is_dir()
    assert (tmp_path / "output").is_dir()
