"""Tests for `POST /api/refresh-now`.

Per CLAUDE.md, no real SD credentials or network are touched here: the
`get_sd_client` FastAPI dependency (shared with every other SD-backed
router, see `app.api.dependencies`) is overridden with a mock-transport-
backed `SdClient` for every test that needs to reach "SD"; the missing-
credentials test deliberately leaves it un-overridden so the real
`SdClient.from_env()` path runs.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_sd_client
from app.main import app
from app.sd_client.client import SdClient

FAKE_TOKEN = "fake-token-abc123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path))
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_sd_client, None)


def token_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "token": FAKE_TOKEN})


def empty_status_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "account": {"maxLineups": 4}, "lineups": []})


def override_sd_client_with(handler) -> None:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    sd_client = SdClient(http_client, username="fake-user", password="fake-password")
    app.dependency_overrides[get_sd_client] = lambda: sd_client


def test_missing_sd_credentials_returns_clean_503(client, monkeypatch):
    monkeypatch.delenv("SD_USERNAME", raising=False)
    monkeypatch.delenv("SD_PASSWORD", raising=False)

    response = client.post("/api/refresh-now")

    assert response.status_code == 503
    assert "credentials" in response.json()["detail"].lower()


def test_no_lineups_succeeds_trivially_with_full_result_shape(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/status"):
            return empty_status_response(request)
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)

    response = client.post("/api/refresh-now")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "lineupsProcessed": 0,
        "lineupsRegenerated": 0,
        "stationRostersRefreshed": 0,
        "stationRostersSkipped": 0,
        "scheduleDaysChecked": 0,
        "scheduleDaysRefetched": 0,
        "scheduleDaysSkippedUnchanged": 0,
        "programsFetched": 0,
        "errors": [],
    }


def test_sd_auth_failure_returns_clean_502(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"code": 401, "message": "Invalid credentials"})
        raise AssertionError("should never get past the token request")

    override_sd_client_with(handler)

    response = client.post("/api/refresh-now")

    assert response.status_code == 502
    assert "invalid credentials" in response.json()["detail"].lower()


def test_is_a_global_endpoint_not_nested_under_lineups(client):
    """This is explicitly the all-lineups pipeline — assert it lives at the
    top-level `/api/refresh-now` path, not nested under `/api/lineups/...`
    (there's no per-lineup variant of this endpoint; the earlier per-lineup
    `sync-and-generate` stopgap this superseded has been removed
    entirely — see docs/backlog.md item 29)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/status"):
            return empty_status_response(request)
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)

    response = client.post("/api/refresh-now")
    assert response.status_code == 200

    # Not a sub-route of /api/lineups/{lineup_id}/... — a real lineup id of
    # literally "refresh-now" would 404 (no such lineup) rather than ever
    # dispatching to this pipeline.
    not_found = client.get("/api/lineups/refresh-now")
    assert not_found.status_code == 404


def test_refresh_now_does_not_touch_the_scheduler(client):
    """Triggering the manual endpoint must not reschedule/reset the
    APScheduler job's own timer — see `app.scheduler.jobs`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/status"):
            return empty_status_response(request)
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)

    scheduler = client.app.state.scheduler
    job_before = scheduler.get_job("sd-refresh")
    next_run_before = job_before.next_run_time

    response = client.post("/api/refresh-now")
    assert response.status_code == 200

    job_after = scheduler.get_job("sd-refresh")
    assert job_after.next_run_time == next_run_before
