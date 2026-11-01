"""Tests for `POST /api/lineups/{lineup_id}/sync-and-generate`.

Per CLAUDE.md, no real SD credentials or network are touched here: the
`get_sd_client` FastAPI dependency is overridden with a mock-transport-
backed `SdClient` for every test that needs to actually reach "SD" (success
and SD-error-mapping cases); the missing-credentials test deliberately
leaves that dependency un-overridden so the real `SdClient.from_env()` path
runs — it must fail on missing env vars before ever touching httpx.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.sync import get_sd_client
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


def override_sd_client_with(handler) -> None:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    sd_client = SdClient(http_client, username="fake-user", password="fake-password")
    app.dependency_overrides[get_sd_client] = lambda: sd_client


def create_lineup_with_mapped_channel(client, station_id="10123") -> str:
    lineup_id = client.post("/api/lineups", json={"name": "Living Room Antenna"}).json()["id"]
    client.put(
        f"/api/lineups/{lineup_id}/sd-lineups", json={"sdLineupIds": ["USA-OTA12345"]}
    )
    channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "KGO-TV", "tvgId": "KGO.us"}
    ).json()["id"]
    client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}/mapping",
        json={"sdStationId": station_id, "sdLineupId": "USA-OTA12345"},
    )
    return lineup_id


def test_missing_sd_credentials_returns_clean_503(client, monkeypatch):
    monkeypatch.delenv("SD_USERNAME", raising=False)
    monkeypatch.delenv("SD_PASSWORD", raising=False)
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]

    response = client.post(f"/api/lineups/{lineup_id}/sync-and-generate")

    assert response.status_code == 503
    assert "credentials" in response.json()["detail"].lower()


def test_lineup_not_found_returns_404(client):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("must not call SD for a lineup that doesn't exist")

    override_sd_client_with(handler)

    response = client.post("/api/lineups/does-not-exist/sync-and-generate")

    assert response.status_code == 404


def test_successful_sync_and_generate_end_to_end(client):
    lineup_id = create_lineup_with_mapped_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            return httpx.Response(
                200,
                json=[
                    {
                        "stationID": "10123",
                        "programs": [
                            {
                                "programID": "EP001",
                                "airDateTime": "2026-10-29T00:00:00Z",
                                "duration": 1800,
                            }
                        ],
                        "metadata": {"startDate": "2026-10-29"},
                    }
                ],
            )
        if request.url.path.endswith("/programs"):
            return httpx.Response(
                200, json=[{"programID": "EP001", "titles": [{"title120": "Nightly News"}]}]
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)

    response = client.post(f"/api/lineups/{lineup_id}/sync-and-generate")

    assert response.status_code == 200
    body = response.json()
    assert body["lineupId"] == lineup_id
    assert body["stationsSynced"] == 1
    assert body["channelsGenerated"] == 1
    assert body["stationErrors"] == []
    assert body["errors"] == []

    xmltv_response = client.get(f"/xmltv/{lineup_id}.xml")
    assert xmltv_response.status_code == 200
    assert "KGO.us" in xmltv_response.text


def test_sd_auth_failure_returns_clean_502(client):
    lineup_id = create_lineup_with_mapped_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"code": 401, "message": "Invalid credentials"})
        raise AssertionError("should never get past the token request")

    override_sd_client_with(handler)

    response = client.post(f"/api/lineups/{lineup_id}/sync-and-generate")

    assert response.status_code == 502
    assert "invalid credentials" in response.json()["detail"].lower()


def test_transport_timeout_on_one_station_does_not_500(client):
    """End-to-end version of the peer-review probe: a timeout talking to SD
    for one station must not escape as a raw 500 — the route should still
    return 200 with the failure recorded in the response body."""
    lineup_id = create_lineup_with_mapped_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            raise httpx.ReadTimeout("SD took too long")
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)

    response = client.post(f"/api/lineups/{lineup_id}/sync-and-generate")

    assert response.status_code == 200
    body = response.json()
    assert body["stationsSynced"] == 0
    assert len(body["stationErrors"]) == 1
    assert body["stationErrors"][0]["sdStationId"] == "10123"


def test_auth_level_sd_error_on_station_fetch_returns_clean_502(client):
    """A 403/auth-level failure discovered mid-sync (not just at the initial
    token request) must also surface as a clean 502, not be collected as a
    per-station data error."""
    lineup_id = create_lineup_with_mapped_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            return httpx.Response(403, text="TOKEN_INVALID")
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)

    response = client.post(f"/api/lineups/{lineup_id}/sync-and-generate")

    assert response.status_code == 502


def test_zero_confirmed_channels_succeeds_trivially(client):
    lineup_id = client.post("/api/lineups", json={"name": "Empty Lineup"}).json()["id"]

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("must not make any SD request when nothing is mapped")

    override_sd_client_with(handler)

    response = client.post(f"/api/lineups/{lineup_id}/sync-and-generate")

    assert response.status_code == 200
    body = response.json()
    assert body["stationsSynced"] == 0
    assert body["channelsGenerated"] == 0

    xmltv_response = client.get(f"/xmltv/{lineup_id}.xml")
    assert xmltv_response.status_code == 200
