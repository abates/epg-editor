"""Tests for `POST /api/lineups/{lineup_id}/suggestions` and
`POST /api/lineups/{lineup_id}/bulk-accept-suggestions`.

Per CLAUDE.md, no real SD credentials or network are touched here: the
`get_sd_client` FastAPI dependency (shared with `api/sync.py`) is
overridden with a mock-transport-backed `SdClient` for every test that
needs to reach "SD".
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.sync import get_sd_client
from app.main import app
from app.sd_client.client import SdClient
from app.storage import sd_cache

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


# --- Checkpoint 25: suggestion display enrichment (station name/call sign) --


def test_get_lineup_enriches_suggestions_with_station_name_and_callsign(client):
    """`GET /api/lineups/{lineup_id}` must surface enough for a human to
    actually judge a suggestion — not just a bare SD station id."""
    lineup_id, channel_id = create_lineup_with_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station(), fox_station()])
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)
    assert client.post(f"/api/lineups/{lineup_id}/suggestions").status_code == 200

    lineup = client.get(f"/api/lineups/{lineup_id}").json()
    suggestions = lineup["channels"][0]["mapping"]["suggestions"]
    assert len(suggestions) == 2

    top = next(s for s in suggestions if s["sdStationId"] == "10123")
    assert top["stationName"] == "KGO-TV"
    assert top["callsign"] == "KGO"

    other = next(s for s in suggestions if s["sdStationId"] == "10456")
    assert other["stationName"] == "FOX 5 New York"
    assert other["callsign"] == "WNYW"


def test_list_lineups_also_enriches_suggestions(client):
    """`GET /api/lineups` drives the same suggestion-review UI as the
    single-lineup fetch (see `SuggestionsPanel.tsx`'s re-fetch pattern) —
    must get the same enrichment, not just `GET /api/lineups/{id}`."""
    lineup_id, channel_id = create_lineup_with_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station()])
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)
    assert client.post(f"/api/lineups/{lineup_id}/suggestions").status_code == 200

    lineups = client.get("/api/lineups").json()
    lineup = next(l for l in lineups if l["id"] == lineup_id)
    suggestion = lineup["channels"][0]["mapping"]["suggestions"][0]
    assert suggestion["stationName"] == "KGO-TV"
    assert suggestion["callsign"] == "KGO"


def test_suggestion_with_logo_includes_logo_url_with_no_extra_sd_call(client):
    """`SdStation.logo.URL` already comes back inline with
    `get_lineup_stations` — no separate SD "get logos" call should ever be
    made for this."""
    lineup_id, channel_id = create_lineup_with_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return httpx.Response(
                200,
                json={
                    "map": [],
                    "stations": [
                        {
                            "stationID": "10123",
                            "name": "KGO-TV",
                            "callsign": "KGO",
                            "affiliate": "ABC",
                            "logo": {"URL": "https://example.test/kgo-logo.png"},
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)
    assert client.post(f"/api/lineups/{lineup_id}/suggestions").status_code == 200

    lineup = client.get(f"/api/lineups/{lineup_id}").json()
    suggestion = lineup["channels"][0]["mapping"]["suggestions"][0]
    assert suggestion["logoUrl"] == "https://example.test/kgo-logo.png"


def test_suggestion_display_fields_none_when_station_not_in_cache(client, tmp_path):
    """Cache evicted / SD lineup disassociated since the suggestion was
    generated: enrichment must fall back to `None` display fields rather
    than erroring, so the frontend can fall back to the raw id."""
    lineup_id, channel_id = create_lineup_with_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station(), fox_station()])
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)
    assert client.post(f"/api/lineups/{lineup_id}/suggestions").status_code == 200

    # Simulate the cache being evicted after suggestions were generated.
    sd_cache.invalidate_lineup_stations("USA-OTA12345", base_dir=tmp_path)

    response = client.get(f"/api/lineups/{lineup_id}")
    assert response.status_code == 200
    suggestions = response.json()["channels"][0]["mapping"]["suggestions"]
    assert len(suggestions) == 2
    for suggestion in suggestions:
        assert suggestion["stationName"] is None
        assert suggestion["callsign"] is None
        assert suggestion["logoUrl"] is None
        # The raw id is still present for the frontend's fallback display.
        assert suggestion["sdStationId"] in {"10123", "10456"}


def test_update_channel_response_is_enriched_without_a_follow_up_get(client):
    """Follow-on review finding: `PUT /api/lineups/{lineup_id}/channels/
    {channel_id}` must enrich suggestion display fields on *its own
    response* (not just a subsequent `GET`) -- `ChannelRow.tsx`'s
    `handleEditSubmit` replaces local channel state straight from this
    response, so an unenriched response would make a pending suggestion's
    name/call sign disappear from the UI until the next full page re-fetch."""
    lineup_id, channel_id = create_lineup_with_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station(), fox_station()])
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)
    assert client.post(f"/api/lineups/{lineup_id}/suggestions").status_code == 200

    response = client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}",
        json={"name": "KGO-TV HD"},
    )
    assert response.status_code == 200
    suggestions = response.json()["mapping"]["suggestions"]
    assert len(suggestions) == 2
    top = next(s for s in suggestions if s["sdStationId"] == "10123")
    assert top["stationName"] == "KGO-TV"
    assert top["callsign"] == "KGO"


def test_enriched_display_fields_never_persisted_to_lineups_json(client, tmp_path):
    """The enrichment must be response-only: the raw `config/lineups.json`
    on disk must keep the minimal `{sdStationId, sdLineupId, score}` shape
    documented in docs/data-model.md, even after a response has served the
    enriched fields."""
    lineup_id, channel_id = create_lineup_with_channel(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station(), fox_station()])
        raise AssertionError(f"unexpected path {request.url.path}")

    override_sd_client_with(handler)
    assert client.post(f"/api/lineups/{lineup_id}/suggestions").status_code == 200

    # Drive both enriched-read routes to make sure neither one's response
    # construction leaks back into a write.
    assert client.get(f"/api/lineups/{lineup_id}").status_code == 200
    assert client.get("/api/lineups").status_code == 200

    raw = json.loads((tmp_path / "config" / "lineups.json").read_text())
    raw_lineup = next(l for l in raw["lineups"] if l["id"] == lineup_id)
    raw_suggestions = raw_lineup["channels"][0]["mapping"]["suggestions"]
    assert raw_suggestions  # sanity: suggestions were actually generated
    for suggestion in raw_suggestions:
        # The minimal documented shape's required fields are present...
        assert suggestion["sdStationId"]
        assert suggestion["sdLineupId"]
        assert isinstance(suggestion["score"], (int, float))
        # ...and the display-only enrichment fields (present as keys, since
        # `MappingSuggestion` always declares them, but never *populated*
        # by anything that writes back to `config/lineups.json` — see
        # `models/lineup.py`'s `MappingSuggestion` docstring) are null on
        # disk even though the two `GET` responses above served non-null
        # values for these exact suggestions.
        assert suggestion.get("stationName") is None
        assert suggestion.get("callsign") is None
        assert suggestion.get("logoUrl") is None
