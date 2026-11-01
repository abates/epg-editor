"""Tests for `POST /api/lineups/{lineup_id}/suggestions` and
`POST /api/lineups/{lineup_id}/bulk-accept-suggestions`.

Per CLAUDE.md, no real SD credentials or network are touched here: the
`get_sd_client` FastAPI dependency (shared with `api/sync.py`) is
overridden with a mock-transport-backed `SdClient` for every test that
needs to reach "SD".
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


def stations_response(stations: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"map": [], "stations": stations})


def kgo_station() -> dict:
    return {"stationID": "10123", "name": "KGO-TV", "callsign": "KGO", "affiliate": "ABC"}


def fox_station() -> dict:
    return {
        "stationID": "10456",
        "name": "FOX 5 New York",
        "callsign": "WNYW",
        "affiliate": "FOX",
    }


def override_sd_client_with(handler) -> None:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    sd_client = SdClient(http_client, username="fake-user", password="fake-password")
    app.dependency_overrides[get_sd_client] = lambda: sd_client


def create_lineup_with_channel(client, lineup_name="Living Room Antenna", channel_name="KGO-TV"):
    lineup_id = client.post("/api/lineups", json={"name": lineup_name}).json()["id"]
    client.put(
        f"/api/lineups/{lineup_id}/sd-lineups", json={"sdLineupIds": ["USA-OTA12345"]}
    )
    channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": channel_name}
    ).json()["id"]
    return lineup_id, channel_id


def test_lineup_not_found_returns_404(client):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("must not call SD for a lineup that doesn't exist")

    override_sd_client_with(handler)

    response = client.post("/api/lineups/does-not-exist/suggestions")
    assert response.status_code == 404


def test_bulk_accept_lineup_not_found_returns_404(client):
    response = client.post("/api/lineups/does-not-exist/bulk-accept-suggestions")
    assert response.status_code == 404


def test_generate_suggestions_end_to_end(client):
    lineup_id, channel_id = create_lineup_with_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station(), fox_station()])
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)

    response = client.post(f"/api/lineups/{lineup_id}/suggestions")

    assert response.status_code == 200
    body = response.json()
    assert body["lineupId"] == lineup_id
    assert body["stationPoolSize"] == 2
    assert body["channelsScored"] == 1
    assert body["channelSuggestionCounts"] == [
        {"channelId": channel_id, "suggestionCount": 2}
    ]

    lineup = client.get(f"/api/lineups/{lineup_id}").json()
    suggestions = lineup["channels"][0]["mapping"]["suggestions"]
    assert suggestions[0]["sdStationId"] == "10123"
    assert suggestions[0]["score"] > 0.95


def test_generate_suggestions_sd_auth_failure_returns_clean_502(client):
    lineup_id, _ = create_lineup_with_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"code": 401, "message": "Invalid credentials"})
        raise AssertionError("should never get past the token request")

    override_sd_client_with(handler)

    response = client.post(f"/api/lineups/{lineup_id}/suggestions")
    assert response.status_code == 502


def test_generate_suggestions_only_fetches_associated_sd_lineups(client):
    lineup_id, _ = create_lineup_with_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station()])
        raise AssertionError(f"must not fetch unassociated SD lineup: {request.url.path}")

    override_sd_client_with(handler)

    response = client.post(f"/api/lineups/{lineup_id}/suggestions")
    assert response.status_code == 200


def test_bulk_accept_end_to_end(client):
    lineup_id, channel_id = create_lineup_with_channel(client)
    bad_channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "Ghost Channel"}
    ).json()["id"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station(), fox_station()])
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)
    generate_response = client.post(f"/api/lineups/{lineup_id}/suggestions")
    assert generate_response.status_code == 200

    bulk_response = client.post(f"/api/lineups/{lineup_id}/bulk-accept-suggestions")
    assert bulk_response.status_code == 200
    body = bulk_response.json()
    confirmed_ids = {c["channelId"] for c in body["confirmed"]}
    assert channel_id in confirmed_ids
    assert bad_channel_id not in confirmed_ids
    assert body["threshold"] == pytest.approx(0.92)

    lineup = client.get(f"/api/lineups/{lineup_id}").json()
    good_channel = next(c for c in lineup["channels"] if c["id"] == channel_id)
    assert good_channel["mapping"]["confirmed"] is True
    assert good_channel["mapping"]["sdStationId"] == "10123"


def test_bulk_accept_does_not_require_sd_client(client):
    """No SD client dependency override at all — proves the bulk-accept
    route never touches SD (it's dependency-free on purpose)."""
    lineup_id = client.post("/api/lineups", json={"name": "Empty Lineup"}).json()["id"]

    response = client.post(f"/api/lineups/{lineup_id}/bulk-accept-suggestions")
    assert response.status_code == 200
    assert response.json()["confirmedCount"] == 0
