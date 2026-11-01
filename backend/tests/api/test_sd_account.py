"""Tests for `/api/sd-account/lineups` and `/api/sd-account/limit`.

Per CLAUDE.md, no real SD credentials or network are touched here: the
`get_sd_client` FastAPI dependency (shared with `api/sync.py`) is
overridden with a mock-transport-backed `SdClient` for every test that
needs to reach "SD"; the missing-credentials test deliberately leaves
that dependency un-overridden so the real `SdClient.from_env()` path runs.

These routes manage the user's *SD account* lineups, not epg-editor's own
persisted lineups — `test_never_touches_lineups_json` confirms that
distinction holds: `config/lineups.json` is never created or modified by
any of these routes.
"""

from __future__ import annotations

import json

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


def test_missing_sd_credentials_returns_clean_503_on_list(client, monkeypatch):
    monkeypatch.delenv("SD_USERNAME", raising=False)
    monkeypatch.delenv("SD_PASSWORD", raising=False)

    response = client.get("/api/sd-account/lineups")

    assert response.status_code == 503
    assert "credentials" in response.json()["detail"].lower()


def test_missing_sd_credentials_returns_clean_503_on_add(client, monkeypatch):
    monkeypatch.delenv("SD_USERNAME", raising=False)
    monkeypatch.delenv("SD_PASSWORD", raising=False)

    response = client.post("/api/sd-account/lineups", json={"lineupId": "USA-OTA12345"})

    assert response.status_code == 503


def test_missing_sd_credentials_returns_clean_503_on_remove(client, monkeypatch):
    monkeypatch.delenv("SD_USERNAME", raising=False)
    monkeypatch.delenv("SD_PASSWORD", raising=False)

    response = client.delete("/api/sd-account/lineups/USA-OTA12345")

    assert response.status_code == 503


def test_missing_sd_credentials_returns_clean_503_on_limit(client, monkeypatch):
    monkeypatch.delenv("SD_USERNAME", raising=False)
    monkeypatch.delenv("SD_PASSWORD", raising=False)

    response = client.get("/api/sd-account/limit")

    assert response.status_code == 503


def test_list_sd_account_lineups_returns_the_mocked_lineups(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        assert request.url.path.endswith("/lineups")
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "lineups": [
                    {
                        "lineup": "USA-OTA12345",
                        "name": "Bay Area Antenna",
                        "transport": "Antenna",
                        "location": "94102",
                        "uri": "/20141201/lineups/USA-OTA12345",
                    }
                ],
            },
        )

    override_sd_client_with(handler)

    response = client.get("/api/sd-account/lineups")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "lineup": "USA-OTA12345",
            "name": "Bay Area Antenna",
            "transport": "Antenna",
            "location": "94102",
            "uri": "/20141201/lineups/USA-OTA12345",
        }
    ]


def test_list_sd_account_lineups_sd_rejection_returns_clean_502(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"code": 401, "message": "Invalid credentials"})
        raise AssertionError("should never get past the token request")

    override_sd_client_with(handler)

    response = client.get("/api/sd-account/lineups")

    assert response.status_code == 502


def test_list_sd_account_lineups_sd_error_coded_200_returns_clean_502(client):
    """A token that succeeds but an error-coded 200 from `/lineups` itself
    (e.g. an account-level failure) must also surface as a 502 — not as a
    200 with a misleadingly-empty `[]` body."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        assert request.url.path.endswith("/lineups")
        return httpx.Response(200, json={"code": 4003, "response": "INVALID_USER"})

    override_sd_client_with(handler)

    response = client.get("/api/sd-account/lineups")

    assert response.status_code == 502


def test_add_sd_account_lineup_returns_the_mocked_response(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        assert request.method == "PUT"
        assert request.url.path.endswith("/lineups/USA-OTA12345")
        return httpx.Response(
            200,
            json={
                "response": "OK",
                "code": 0,
                "message": "Added lineup.",
                "changesRemaining": 254,
            },
        )

    override_sd_client_with(handler)

    response = client.post("/api/sd-account/lineups", json={"lineupId": "USA-OTA12345"})

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "OK"
    assert body["code"] == 0
    assert body["changesRemaining"] == 254


def test_add_sd_account_lineup_sd_rejection_returns_clean_502(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        return httpx.Response(
            200,
            json={
                "response": "INVALID_LINEUP",
                "code": 2105,
                "message": "The lineup you submitted doesn't exist.",
            },
        )

    override_sd_client_with(handler)

    response = client.post("/api/sd-account/lineups", json={"lineupId": "does-not-exist"})

    assert response.status_code == 502
    assert "doesn't exist" in response.json()["detail"].lower()


@pytest.mark.parametrize("bad_lineup_id", ["", "USA/OTA12345", "USA-OTA?12345", "foo bar"])
def test_add_sd_account_lineup_rejects_malformed_lineup_id_with_422(client, bad_lineup_id):
    """`lineupId` must be rejected before it ever reaches the SD client —
    an empty string or one containing `/`/`?`/whitespace could otherwise
    alter the request's target path/query when interpolated via f-string
    in `sd_client/client.py`."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should never reach the network")

    override_sd_client_with(handler)

    response = client.post("/api/sd-account/lineups", json={"lineupId": bad_lineup_id})

    assert response.status_code == 422


def test_remove_sd_account_lineup_rejects_malformed_lineup_id_with_422(client):
    """A path value containing a character outside the allowed pattern
    (but not a `/`, which routing itself already blocks — see the test
    below) must fail path-param validation with a 422, not reach the SD
    client."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should never reach the network")

    override_sd_client_with(handler)

    response = client.delete("/api/sd-account/lineups/USA-OTA%3F12345")

    assert response.status_code == 422


def test_remove_sd_account_lineup_with_encoded_slash_is_rejected_by_routing(client):
    """A `/` in the path segment (even percent-encoded) doesn't match this
    route at all — Starlette's default `str` path-param type never spans
    `/` — so this comes back 404 rather than reaching the handler. Included
    to document that a `lineupId` containing `/` can't reach the SD client
    via this path regardless of the `Path(pattern=...)` constraint."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should never reach the network")

    override_sd_client_with(handler)

    response = client.delete("/api/sd-account/lineups/USA%2FOTA12345")

    assert response.status_code == 404


def test_remove_sd_account_lineup_returns_the_mocked_response(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        assert request.method == "DELETE"
        assert request.url.path.endswith("/lineups/USA-OTA12345")
        return httpx.Response(
            200,
            json={
                "response": "OK",
                "code": 0,
                "message": "Deleted lineup.",
                "changesRemaining": 253,
            },
        )

    override_sd_client_with(handler)

    response = client.delete("/api/sd-account/lineups/USA-OTA12345")

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "OK"
    assert body["changesRemaining"] == 253


def test_remove_sd_account_lineup_sd_rejection_returns_clean_502(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        return httpx.Response(
            200, json={"response": "LINEUP_NOT_IN_ACCOUNT", "code": 2503, "message": "Not subscribed."}
        )

    override_sd_client_with(handler)

    response = client.delete("/api/sd-account/lineups/USA-OTA12345")

    assert response.status_code == 502


def test_get_sd_account_limit_returns_max_lineups_and_used_count(client):
    """`lineupsUsed` counts every entry including `isDeleted` ones (the
    conservative assumption — see `services/sd_account.py`); the deleted
    one is still separately surfaced via `deletedLineupCount`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        assert request.url.path.endswith("/status")
        return httpx.Response(
            200,
            json={
                "code": 0,
                "account": {"maxLineups": 4, "messages": []},
                "lineups": [
                    {"lineup": "USA-OTA12345", "uri": "/x"},
                    {"lineup": "USA-WI61859-DEFAULT", "isDeleted": True},
                ],
            },
        )

    override_sd_client_with(handler)

    response = client.get("/api/sd-account/limit")

    assert response.status_code == 200
    assert response.json() == {
        "maxLineups": 4,
        "lineupsUsed": 2,
        "deletedLineupCount": 1,
    }


def test_get_sd_account_limit_sd_rejection_returns_clean_502(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"code": 401, "message": "Invalid credentials"})
        raise AssertionError("should never get past the token request")

    override_sd_client_with(handler)

    response = client.get("/api/sd-account/limit")

    assert response.status_code == 502


def test_get_sd_account_limit_sd_error_coded_200_returns_clean_502(client):
    """A token that succeeds but an error-coded 200 from `/status` itself
    must surface as a 502 — not as a 200 with `maxLineups=None,
    lineupsUsed=0` as if that were a real (empty) answer. Reproduces the
    reviewer's exact repro scenario."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        assert request.url.path.endswith("/status")
        return httpx.Response(200, json={"code": 4003, "response": "INVALID_USER"})

    override_sd_client_with(handler)

    response = client.get("/api/sd-account/limit")

    assert response.status_code == 502


def test_sd_account_routes_never_touch_lineups_json(client, tmp_path):
    """These are pure read-through/write-through calls to SD, not
    epg-editor's own persisted state (per CLAUDE.md's module layering and
    the brief for this change) — `config/lineups.json` must not exist (or,
    if some other earlier test action created it, must be unmodified) as a
    result of driving every one of these routes."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"code": 0, "account": {"maxLineups": 4}, "lineups": []})
        if request.method == "GET":
            return httpx.Response(200, json={"code": 0, "lineups": []})
        return httpx.Response(200, json={"response": "OK", "code": 0, "changesRemaining": 1})

    override_sd_client_with(handler)

    assert client.get("/api/sd-account/lineups").status_code == 200
    assert client.post("/api/sd-account/lineups", json={"lineupId": "USA-OTA12345"}).status_code == 200
    assert client.delete("/api/sd-account/lineups/USA-OTA12345").status_code == 200
    assert client.get("/api/sd-account/limit").status_code == 200

    lineups_json_path = tmp_path / "config" / "lineups.json"
    assert not lineups_json_path.exists()
