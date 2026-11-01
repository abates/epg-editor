"""Tests for `app.services.sd_account`.

Everything here goes through `httpx.MockTransport` — no real SD
credentials or network, ever (matches the rest of the suite; see
`tests/sd_client/test_client.py`'s module docstring).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.sd_client.client import SdClient
from app.services import sd_account as sd_account_service

FAKE_TOKEN = "fake-token-abc123"


def run(coro):
    return asyncio.run(coro)


def make_sd_client(handler) -> SdClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return SdClient(http_client, username="fake-user", password="fake-password")


def token_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "token": FAKE_TOKEN})


def test_list_account_lineups_returns_the_lineups_list():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
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
                    }
                ],
            },
        )

    sd_client = make_sd_client(handler)
    result = run(sd_account_service.list_account_lineups(sd_client))

    assert len(result) == 1
    assert result[0].lineup == "USA-OTA12345"
    assert result[0].name == "Bay Area Antenna"


def test_add_and_remove_account_lineup_return_sd_response():
    seen_methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        seen_methods.append(request.method)
        return httpx.Response(
            200, json={"response": "OK", "code": 0, "changesRemaining": 4}
        )

    sd_client = make_sd_client(handler)

    async def scenario():
        add_result = await sd_account_service.add_account_lineup(sd_client, "USA-OTA12345")
        remove_result = await sd_account_service.remove_account_lineup(
            sd_client, "USA-OTA12345"
        )
        return add_result, remove_result

    add_result, remove_result = run(scenario())

    assert seen_methods == ["PUT", "DELETE"]
    assert add_result.code == 0
    assert add_result.changesRemaining == 4
    assert remove_result.code == 0


def test_get_account_lineup_limit_counts_deleted_lineups_as_still_used():
    """Conservative assumption (per review): SD's docs only say a deleted
    entry "may no longer be valid," not that it has freed up a slot — so
    `lineupsUsed` must count it, while `deletedLineupCount` still surfaces
    how many of those counted entries are flagged deleted."""

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
                    {"lineup": "USA-CA00053-X", "uri": "/y"},
                    {"lineup": "USA-WI61859-DEFAULT", "isDeleted": True},
                ],
            },
        )

    sd_client = make_sd_client(handler)
    result = run(sd_account_service.get_account_lineup_limit(sd_client))

    assert result.maxLineups == 4
    assert result.lineupsUsed == 3
    assert result.deletedLineupCount == 1


def test_get_account_lineup_limit_handles_missing_account_object():
    """Defensive: SD's documented shape always includes `account`, but a
    malformed/partial response shouldn't crash this — `maxLineups` should
    come back `None` rather than raising."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        return httpx.Response(200, json={"code": 0, "lineups": []})

    sd_client = make_sd_client(handler)
    result = run(sd_account_service.get_account_lineup_limit(sd_client))

    assert result.maxLineups is None
    assert result.lineupsUsed == 0
    assert result.deletedLineupCount == 0


def test_list_account_lineups_sd_error_coded_200_raises():
    """SD can return HTTP 200 with an error payload on `/lineups` itself
    (not just at the token stage) — e.g. `{"code": 4003, "response":
    "INVALID_USER"}`. That must raise, not validate as "zero lineups."""
    from app.sd_client.client import SdClientError

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        assert request.url.path.endswith("/lineups")
        return httpx.Response(200, json={"code": 4003, "response": "INVALID_USER"})

    sd_client = make_sd_client(handler)

    with pytest.raises(SdClientError):
        run(sd_account_service.list_account_lineups(sd_client))


def test_get_account_lineup_limit_sd_error_coded_200_raises():
    """Same scenario as above, but against `/status` — reproduces the
    reviewer's exact repro: an error-coded 200 response must not come back
    as `maxLineups=None, lineupsUsed=0` as if that were a real answer."""
    from app.sd_client.client import SdClientError

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        assert request.url.path.endswith("/status")
        return httpx.Response(200, json={"code": 4003, "response": "INVALID_USER"})

    sd_client = make_sd_client(handler)

    with pytest.raises(SdClientError):
        run(sd_account_service.get_account_lineup_limit(sd_client))


def test_add_account_lineup_sd_rejection_raises(monkeypatch):
    from app.sd_client.client import SdClientError

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        return httpx.Response(
            200,
            json={
                "response": "LINEUP_ALREADY_IN_ACCOUNT",
                "code": 2504,
                "message": "Lineup already in account.",
            },
        )

    sd_client = make_sd_client(handler)

    with pytest.raises(SdClientError):
        run(sd_account_service.add_account_lineup(sd_client, "USA-OTA12345"))
