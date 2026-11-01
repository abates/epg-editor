"""Tests for `app.sd_client.client.SdClient` against a mocked HTTP transport.

No real network call is made anywhere in this file: every request is routed
through `httpx.MockTransport`, which returns fixture JSON. This also means
no real `SD_USERNAME`/`SD_PASSWORD` are ever required — fake credentials
are passed explicitly to `SdClient`.
"""

from __future__ import annotations

import asyncio
from collections import Counter

import httpx
import pytest

from app.sd_client.client import SdClient, SdClientError, SdCredentialsNotConfiguredError

FAKE_USERNAME = "fake-user"
FAKE_PASSWORD = "fake-password"
FAKE_TOKEN = "fake-token-abc123"


def run(coro):
    """Run an async test body without pulling in a pytest-asyncio dependency."""
    return asyncio.run(coro)


def make_client(handler, **kwargs) -> SdClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return SdClient(
        http_client, username=FAKE_USERNAME, password=FAKE_PASSWORD, **kwargs
    )


def token_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "message": "OK",
            "serverID": "fake-server",
            "datetime": "2026-10-29T00:00:00Z",
            "token": FAKE_TOKEN,
        },
    )


def test_get_token_fetches_and_caches(tmp_path):
    call_counts: Counter[str] = Counter()

    def handler(request: httpx.Request) -> httpx.Response:
        call_counts[request.url.path] += 1
        assert request.url.path.endswith("/token")
        body = request.read()
        assert FAKE_PASSWORD.encode() not in body  # only the SHA1 hash travels
        return token_response(request)

    client = make_client(handler)

    async def scenario():
        first = await client.get_token()
        second = await client.get_token()
        return first, second

    first, second = run(scenario())

    assert first == second == FAKE_TOKEN
    assert call_counts["/20141201/token"] == 1  # second call used the cache


def test_get_token_force_refresh_bypasses_cache():
    call_counts: Counter[str] = Counter()

    def handler(request: httpx.Request) -> httpx.Response:
        call_counts[request.url.path] += 1
        return token_response(request)

    client = make_client(handler)

    async def scenario():
        await client.get_token()
        await client.get_token(force_refresh=True)

    run(scenario())

    assert call_counts["/20141201/token"] == 2


def test_get_token_without_credentials_raises():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should never reach the network")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = SdClient(http_client, username=None, password=None)

    with pytest.raises(SdClientError):
        run(client.get_token())


def test_list_account_lineups():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        assert request.url.path.endswith("/lineups")
        assert request.headers["token"] == FAKE_TOKEN
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

    client = make_client(handler)
    result = run(client.list_account_lineups())

    assert len(result.lineups) == 1
    assert result.lineups[0].lineup == "USA-OTA12345"
    assert result.lineups[0].name == "Bay Area Antenna"


def test_add_and_remove_account_lineup():
    seen_methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        seen_methods.append(request.method)
        assert request.url.path.endswith("/lineups/USA-OTA12345")
        return httpx.Response(
            200,
            json={"response": "OK", "code": 0, "changesRemaining": 4},
        )

    client = make_client(handler)

    async def scenario():
        add_result = await client.add_account_lineup("USA-OTA12345")
        remove_result = await client.remove_account_lineup("USA-OTA12345")
        return add_result, remove_result

    add_result, remove_result = run(scenario())

    assert seen_methods == ["PUT", "DELETE"]
    assert add_result.code == 0
    assert add_result.changesRemaining == 4
    assert remove_result.code == 0


def test_add_account_lineup_raises_on_sd_error_code():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        return httpx.Response(
            200,
            json={"response": "LINEUP_ALREADY_IN_ACCOUNT", "code": 2504, "message": "Lineup already in account."},
        )

    client = make_client(handler)

    with pytest.raises(SdClientError):
        run(client.add_account_lineup("USA-OTA12345"))


def test_get_lineup_stations():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        assert request.url.path.endswith("/lineups/USA-OTA12345")
        return httpx.Response(
            200,
            json={
                "map": [{"stationID": "10123", "channel": "7.1"}],
                "stations": [
                    {
                        "stationID": "10123",
                        "name": "KGO-TV",
                        "callsign": "KGO",
                        "affiliate": "ABC",
                        "logo": {"URL": "https://example.test/logo.png"},
                    }
                ],
                "metadata": {"lineup": "USA-OTA12345"},
            },
        )

    client = make_client(handler)
    result = run(client.get_lineup_stations("USA-OTA12345"))

    assert result.stations[0].stationID == "10123"
    assert result.stations[0].callsign == "KGO"
    assert result.map[0].channel == "7.1"


def test_get_schedules_and_get_programs():
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
                                "programID": "EP01234560001",
                                "airDateTime": "2026-10-29T00:00:00Z",
                                "duration": 1800,
                                "md5": "abc123",
                            }
                        ],
                        "metadata": {"md5": "day-md5", "startDate": "2026-10-29"},
                    }
                ],
            )
        if request.url.path.endswith("/programs"):
            return httpx.Response(
                200,
                json=[
                    {
                        "programID": "EP01234560001",
                        "titles": [{"title120": "Nightly News"}],
                        "episodeTitle150": "Tuesday, October 29, 2026",
                    }
                ],
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    from app.models.sd import SdScheduleRequest

    client = make_client(handler)

    async def scenario():
        schedules = await client.get_schedules(
            [SdScheduleRequest(stationID="10123", date=["2026-10-29"])]
        )
        programs = await client.get_programs(["EP01234560001"])
        return schedules, programs

    schedules, programs = run(scenario())

    assert schedules[0].stationID == "10123"
    assert schedules[0].programs[0].programID == "EP01234560001"
    assert programs[0].titles[0].title120 == "Nightly News"


def test_from_env_raises_specific_error_when_credentials_missing(monkeypatch):
    # `from_env()` must never touch the network when credentials are
    # missing/empty — pass a transport that errors if hit, to prove it.
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should never reach the network")

    monkeypatch.delenv("SD_USERNAME", raising=False)
    monkeypatch.delenv("SD_PASSWORD", raising=False)
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(SdCredentialsNotConfiguredError):
        SdClient.from_env(http_client)


def test_from_env_raises_when_password_is_empty_string(monkeypatch):
    # An empty string is "not configured", not a valid (blank) password.
    monkeypatch.setenv("SD_USERNAME", FAKE_USERNAME)
    monkeypatch.setenv("SD_PASSWORD", "")
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: token_response(request))
    )

    with pytest.raises(SdCredentialsNotConfiguredError):
        SdClient.from_env(http_client)


def test_from_env_reads_credentials_from_environment(monkeypatch):
    monkeypatch.setenv("SD_USERNAME", FAKE_USERNAME)
    monkeypatch.setenv("SD_PASSWORD", FAKE_PASSWORD)

    seen_bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_bodies.append(request.read())
        return token_response(request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = SdClient.from_env(http_client)

    token = run(client.get_token())

    assert token == FAKE_TOKEN
    assert FAKE_USERNAME.encode() in seen_bodies[0]
    assert FAKE_PASSWORD.encode() not in seen_bodies[0]  # only the SHA1 hash travels


def test_non_200_response_raises_sd_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        return httpx.Response(500, text="internal error")

    client = make_client(handler)

    with pytest.raises(SdClientError) as excinfo:
        run(client.get_lineup_stations("USA-OTA12345"))

    assert excinfo.value.status_code == 500


# --- Transport-level failures are wrapped, not left to escape raw ----------
# (These reproduce the peer-review probe: a timeout/connection error talking
# to SD must come out as `SdClientError` so `services/sync.py`'s per-station
# `except SdClientError` actually catches it instead of a raw httpx
# exception aborting the whole sync.)


def test_transport_timeout_is_wrapped_as_sd_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        raise httpx.ReadTimeout("timed out talking to SD")

    client = make_client(handler)

    with pytest.raises(SdClientError) as excinfo:
        run(client.get_lineup_stations("USA-OTA12345"))

    assert "timed out" in str(excinfo.value)


def test_transport_connect_error_is_wrapped_as_sd_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        raise httpx.ConnectError("could not connect to SD")

    client = make_client(handler)

    with pytest.raises(SdClientError):
        run(client.get_lineup_stations("USA-OTA12345"))


def test_non_json_response_body_is_wrapped_as_sd_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        return httpx.Response(200, text="<html>not json</html>")

    client = make_client(handler)

    with pytest.raises(SdClientError):
        run(client.get_lineup_stations("USA-OTA12345"))


def test_response_failing_validation_is_wrapped_as_sd_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            # Missing the required `stationID` field entirely.
            return httpx.Response(200, json=[{"programs": []}])
        raise AssertionError(f"unexpected path {request.url.path}")

    from app.models.sd import SdScheduleRequest

    client = make_client(handler)

    with pytest.raises(SdClientError):
        run(client.get_schedules([SdScheduleRequest(stationID="10123", date=["2026-10-29"])]))


def test_top_level_sd_error_object_instead_of_array_is_wrapped():
    """SD can return a single error object (not the expected array) for an
    account-wide failure on a list-returning endpoint like `/schedules`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            return httpx.Response(
                200, json={"code": 4003, "response": "ACCOUNT_LOCKOUT"}
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    from app.models.sd import SdScheduleRequest

    client = make_client(handler)

    with pytest.raises(SdClientError) as excinfo:
        run(client.get_schedules([SdScheduleRequest(stationID="10123", date=["2026-10-29"])]))

    assert excinfo.value.sd_code == 4003
    assert excinfo.value.is_auth_error


# --- `SdClientError.is_auth_error` classification ---------------------------


@pytest.mark.parametrize("status_code", [401, 403])
def test_is_auth_error_true_for_auth_http_statuses(status_code):
    err = SdClientError("boom", status_code=status_code)
    assert err.is_auth_error


def test_is_auth_error_true_for_account_sd_code_range():
    err = SdClientError("boom", sd_code=4006)
    assert err.is_auth_error


def test_is_auth_error_false_for_ordinary_data_error():
    err = SdClientError("boom", status_code=400)
    assert not err.is_auth_error


# --- `from_env()` owns the real client's timeout config ---------------------


def test_from_env_constructs_a_client_with_a_generous_timeout_by_default(monkeypatch):
    monkeypatch.setenv("SD_USERNAME", FAKE_USERNAME)
    monkeypatch.setenv("SD_PASSWORD", FAKE_PASSWORD)

    from app.sd_client.client import DEFAULT_HTTP_TIMEOUT

    client = SdClient.from_env()
    try:
        timeout = client._http.timeout  # noqa: SLF001 — whitebox check of from_env's wiring
        assert timeout.connect == DEFAULT_HTTP_TIMEOUT
        assert DEFAULT_HTTP_TIMEOUT > 5.0  # strictly more generous than httpx's 5s default
    finally:
        run(client.aclose())
