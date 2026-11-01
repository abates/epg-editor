"""Tests for `app.services.sync.sync_and_generate`.

Everything here goes through `httpx.MockTransport` — no real SD
credentials or network, ever (matches the rest of the suite; see
`tests/sd_client/test_client.py`'s module docstring). The mock-backed
`SdClient` is constructed directly and passed in, exactly the way the
brief calls for (never via `SdClient.from_env()`, which is covered
separately in `tests/sd_client/test_client.py` and `tests/api/test_sync.py`).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.sd_client.client import SdClient
from app.services import lineups as lineups_service
from app.services import sync as sync_service
from app.services.xmltv import get_xmltv_output_path
from app.storage import sd_cache

FAKE_TOKEN = "fake-token-abc123"
NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)
# Matches `guide_window_dates(NOW, 3)`.
EXPECTED_DATES = ["2026-10-29", "2026-10-30", "2026-10-31"]


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path))


def run(coro):
    return asyncio.run(coro)


def make_sd_client(handler) -> SdClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return SdClient(http_client, username="fake-user", password="fake-password")


def token_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "token": FAKE_TOKEN})


def schedule_item(station_id: str, date: str, program_id: str) -> dict:
    return {
        "stationID": station_id,
        "programs": [
            {
                "programID": program_id,
                "airDateTime": f"{date}T00:00:00Z",
                "duration": 1800,
            }
        ],
        "metadata": {"startDate": date, "md5": f"{station_id}-{date}-md5"},
    }


def program_item(program_id: str) -> dict:
    return {"programID": program_id, "titles": [{"title120": f"Show {program_id}"}]}


def make_lineup_with_mapped_channel(*, station_id="10123"):
    lineup = lineups_service.create_lineup("Living Room Antenna")
    lineups_service.update_lineup_sd_lineup_ids(lineup.id, ["USA-OTA12345"])
    channel = lineups_service.add_channel(lineup.id, name="KGO-TV", tvg_id="KGO.us")
    lineups_service.set_channel_mapping(
        lineup.id, channel.id, sd_station_id=station_id, sd_lineup_id="USA-OTA12345"
    )
    return lineups_service.get_lineup(lineup.id)


# --- Successful end-to-end sync ---------------------------------------------


def test_successful_sync_and_generate_caches_data_and_writes_xmltv(tmp_path):
    lineup = make_lineup_with_mapped_channel(station_id="10123")
    program_ids = ["EP001", "EP002", "EP003"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            body = request.read().decode()
            assert "10123" in body
            return httpx.Response(
                200,
                json=[
                    schedule_item("10123", date, program_id)
                    for date, program_id in zip(EXPECTED_DATES, program_ids)
                ],
            )
        if request.url.path.endswith("/programs"):
            return httpx.Response(200, json=[program_item(pid) for pid in program_ids])
        raise AssertionError(f"unexpected path {request.url.path}")

    sd_client = make_sd_client(handler)

    result = run(
        sync_service.sync_and_generate(lineup.id, sd_client, base_dir=tmp_path, now=NOW)
    )

    assert result.lineupId == lineup.id
    assert result.stationsSynced == 1
    assert result.scheduleDaysFetched == 3
    assert result.programsFetched == 3
    assert result.channelsGenerated == 1
    assert result.stationErrors == []
    assert result.errors == []

    for date, program_id in zip(EXPECTED_DATES, program_ids):
        cached = sd_cache.load_station_schedule("10123", date, base_dir=tmp_path)
        assert cached is not None
        assert cached.data.programs[0].programID == program_id
        assert sd_cache.load_program(program_id, base_dir=tmp_path) is not None

    output_path = get_xmltv_output_path(lineup.id, base_dir=tmp_path)
    assert output_path is not None
    xml_text = output_path.read_text(encoding="utf-8")
    assert '<channel id="KGO.us">' in xml_text
    assert "Show EP001" in xml_text


# --- Missing SD credentials never reaches this layer -------------------------
# (SdClient.from_env() is what raises for missing credentials — see
# tests/sd_client/test_client.py and tests/api/test_sync.py. This module
# always constructs SdClient directly, as the brief specifies.)


# --- Partial failure: one bad station doesn't abort the whole sync ----------


def test_partial_failure_one_station_does_not_abort_sync(tmp_path):
    lineup = lineups_service.create_lineup("Living Room Antenna")
    lineups_service.update_lineup_sd_lineup_ids(lineup.id, ["USA-OTA12345"])
    good_channel = lineups_service.add_channel(lineup.id, name="KGO-TV", tvg_id="KGO.us")
    lineups_service.set_channel_mapping(
        lineup.id, good_channel.id, sd_station_id="10123", sd_lineup_id="USA-OTA12345"
    )
    bad_channel = lineups_service.add_channel(lineup.id, name="Ghost Channel", tvg_id="GHOST.us")
    lineups_service.set_channel_mapping(
        lineup.id, bad_channel.id, sd_station_id="99999", sd_lineup_id="USA-OTA12345"
    )
    lineup = lineups_service.get_lineup(lineup.id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            body = request.read().decode()
            if "99999" in body:
                return httpx.Response(400, text="invalid station id")
            assert "10123" in body
            return httpx.Response(
                200,
                json=[schedule_item("10123", date, "EP001") for date in EXPECTED_DATES],
            )
        if request.url.path.endswith("/programs"):
            return httpx.Response(200, json=[program_item("EP001")])
        raise AssertionError(f"unexpected path {request.url.path}")

    sd_client = make_sd_client(handler)

    result = run(
        sync_service.sync_and_generate(lineup.id, sd_client, base_dir=tmp_path, now=NOW)
    )

    assert result.stationsSynced == 1
    assert result.scheduleDaysFetched == 3
    assert result.channelsGenerated == 2
    assert len(result.stationErrors) == 1
    assert result.stationErrors[0].sdStationId == "99999"
    assert result.errors == []

    # Generation still ran with whatever succeeded.
    output_path = get_xmltv_output_path(lineup.id, base_dir=tmp_path)
    assert output_path is not None
    xml_text = output_path.read_text(encoding="utf-8")
    assert '<channel id="KGO.us">' in xml_text
    # The failed station's channel is still listed (its confirmed mapping
    # is real — build_xmltv_document just can't find cached airings for
    # it), per services.xmltv's "no crash, no data" handling.
    assert '<channel id="GHOST.us">' in xml_text


def test_programs_fetch_failure_is_collected_not_raised(tmp_path):
    lineup = make_lineup_with_mapped_channel(station_id="10123")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            return httpx.Response(
                200,
                json=[schedule_item("10123", date, "EP001") for date in EXPECTED_DATES],
            )
        if request.url.path.endswith("/programs"):
            return httpx.Response(500, text="internal error")
        raise AssertionError(f"unexpected path {request.url.path}")

    sd_client = make_sd_client(handler)

    result = run(
        sync_service.sync_and_generate(lineup.id, sd_client, base_dir=tmp_path, now=NOW)
    )

    assert result.stationsSynced == 1
    assert result.scheduleDaysFetched == 3
    assert result.programsFetched == 0
    assert len(result.errors) == 1
    assert "program" in result.errors[0].lower()

    # Generation still ran despite the programs-fetch failure.
    output_path = get_xmltv_output_path(lineup.id, base_dir=tmp_path)
    assert output_path is not None


# --- SD auth failure propagates (not swallowed as a per-station error) ------


def test_sd_auth_failure_propagates_uncaught(tmp_path):
    lineup = make_lineup_with_mapped_channel(station_id="10123")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(
                200, json={"code": 401, "message": "Invalid credentials"}
            )
        raise AssertionError("should never get past the token request")

    sd_client = make_sd_client(handler)

    from app.sd_client.client import SdClientError

    with pytest.raises(SdClientError):
        run(
            sync_service.sync_and_generate(
                lineup.id, sd_client, base_dir=tmp_path, now=NOW
            )
        )


# --- Zero confirmed-mapped channels: trivial success, no SD calls at all ----


def test_zero_confirmed_channels_succeeds_without_touching_sd(tmp_path):
    lineup = lineups_service.create_lineup("Empty Lineup")
    # An unconfirmed suggestion-only channel shouldn't count either.
    lineups_service.add_channel(lineup.id, name="Unmapped Channel")

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("must not make any SD request when nothing is mapped")

    sd_client = make_sd_client(handler)

    result = run(
        sync_service.sync_and_generate(lineup.id, sd_client, base_dir=tmp_path, now=NOW)
    )

    assert result.stationsSynced == 0
    assert result.scheduleDaysFetched == 0
    assert result.programsFetched == 0
    assert result.channelsGenerated == 0
    assert result.stationErrors == []
    assert result.errors == []

    output_path = get_xmltv_output_path(lineup.id, base_dir=tmp_path)
    assert output_path is not None
    xml_text = output_path.read_text(encoding="utf-8")
    assert "<channel" not in xml_text


def test_transport_error_on_one_station_is_collected_not_raised(tmp_path):
    """Reproduces the peer-review probe: station A times out, station B
    must still be attempted, and generation still runs with whatever
    succeeded — rather than a raw transport exception aborting the sync."""
    lineup = lineups_service.create_lineup("Living Room Antenna")
    lineups_service.update_lineup_sd_lineup_ids(lineup.id, ["USA-OTA12345"])
    timeout_channel = lineups_service.add_channel(lineup.id, name="Timeout Channel", tvg_id="TIMEOUT.us")
    lineups_service.set_channel_mapping(
        lineup.id, timeout_channel.id, sd_station_id="10123", sd_lineup_id="USA-OTA12345"
    )
    good_channel = lineups_service.add_channel(lineup.id, name="KGO-TV", tvg_id="KGO.us")
    lineups_service.set_channel_mapping(
        lineup.id, good_channel.id, sd_station_id="20456", sd_lineup_id="USA-OTA12345"
    )
    lineup = lineups_service.get_lineup(lineup.id)

    attempted_stations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            body = request.read().decode()
            if "10123" in body:
                attempted_stations.append("10123")
                raise httpx.ReadTimeout("SD took too long")
            attempted_stations.append("20456")
            assert "20456" in body
            return httpx.Response(
                200,
                json=[schedule_item("20456", date, "EP001") for date in EXPECTED_DATES],
            )
        if request.url.path.endswith("/programs"):
            return httpx.Response(200, json=[program_item("EP001")])
        raise AssertionError(f"unexpected path {request.url.path}")

    sd_client = make_sd_client(handler)

    result = run(
        sync_service.sync_and_generate(lineup.id, sd_client, base_dir=tmp_path, now=NOW)
    )

    # Both stations were attempted — the timeout on the first didn't stop
    # the loop from reaching the second.
    assert attempted_stations == ["10123", "20456"]
    assert result.stationsSynced == 1
    assert len(result.stationErrors) == 1
    assert result.stationErrors[0].sdStationId == "10123"
    assert "timed out" in result.stationErrors[0].message.lower() or "SD took too long" in result.stationErrors[0].message

    # Generation still ran with whatever succeeded.
    output_path = get_xmltv_output_path(lineup.id, base_dir=tmp_path)
    assert output_path is not None
    xml_text = output_path.read_text(encoding="utf-8")
    assert '<channel id="KGO.us">' in xml_text


def test_schedule_item_with_sd_error_code_is_collected_not_silently_empty(tmp_path):
    """Reproduces the peer-review probe: SD reports a per-station schedule
    problem (e.g. 7100 SCHEDULE_QUEUED) as a normal-looking 200 item with no
    real schedule data. That must surface as a station error, not a
    silent "synced successfully with zero entries"."""
    lineup = make_lineup_with_mapped_channel(station_id="10123")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            return httpx.Response(
                200,
                json=[
                    {
                        "stationID": "10123",
                        "code": 7100,
                        "response": "SCHEDULE_QUEUED",
                    }
                ],
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    sd_client = make_sd_client(handler)

    result = run(
        sync_service.sync_and_generate(lineup.id, sd_client, base_dir=tmp_path, now=NOW)
    )

    assert result.scheduleDaysFetched == 0
    assert result.programsFetched == 0
    assert len(result.stationErrors) == 1
    assert result.stationErrors[0].sdStationId == "10123"
    assert "7100" in result.stationErrors[0].message
    assert "SCHEDULE_QUEUED" in result.stationErrors[0].message

    assert sd_cache.load_station_schedule("10123", "2026-10-29", base_dir=tmp_path) is None


def test_program_item_with_sd_error_code_is_collected_not_cached_blank(tmp_path):
    lineup = make_lineup_with_mapped_channel(station_id="10123")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            return httpx.Response(
                200,
                json=[schedule_item("10123", date, "EP001") for date in EXPECTED_DATES],
            )
        if request.url.path.endswith("/programs"):
            return httpx.Response(
                200,
                json=[{"programID": "EP001", "code": 7020, "response": "PROGRAMID_QUEUED"}],
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    sd_client = make_sd_client(handler)

    result = run(
        sync_service.sync_and_generate(lineup.id, sd_client, base_dir=tmp_path, now=NOW)
    )

    assert result.programsFetched == 0
    assert len(result.errors) == 1
    assert "7020" in result.errors[0]
    assert "EP001" in result.errors[0]
    assert sd_cache.load_program("EP001", base_dir=tmp_path) is None


# --- Auth/account-level per-station failures stop the sync (not collected) --


def test_auth_level_station_error_stops_the_loop_and_propagates(tmp_path):
    """Reproduces the peer-review probe: an auth/account-level SD error on
    the *first* station's fetch must stop immediately — no further
    stations or the programs call should be attempted — rather than being
    collected like a per-station data error and reported as "completed
    with partial failures"."""
    lineup = lineups_service.create_lineup("Living Room Antenna")
    lineups_service.update_lineup_sd_lineup_ids(lineup.id, ["USA-OTA12345"])
    for idx, station_id in enumerate(["10123", "20456", "30789", "40012"]):
        channel = lineups_service.add_channel(
            lineup.id, name=f"Channel {idx}", tvg_id=f"CH{idx}.us"
        )
        lineups_service.set_channel_mapping(
            lineup.id, channel.id, sd_station_id=station_id, sd_lineup_id="USA-OTA12345"
        )
    lineup = lineups_service.get_lineup(lineup.id)

    schedules_attempted = 0
    programs_attempted = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal schedules_attempted, programs_attempted
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/schedules"):
            schedules_attempted += 1
            return httpx.Response(403, text="TOKEN_INVALID")
        if request.url.path.endswith("/programs"):  # pragma: no cover
            programs_attempted += 1
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected path {request.url.path}")

    sd_client = make_sd_client(handler)

    from app.sd_client.client import SdClientError

    with pytest.raises(SdClientError):
        run(
            sync_service.sync_and_generate(
                lineup.id, sd_client, base_dir=tmp_path, now=NOW
            )
        )

    assert schedules_attempted == 1
    assert programs_attempted == 0


def test_lineup_not_found_raises(tmp_path):
    from app.services.lineups import NotFoundError

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should never reach the network")

    sd_client = make_sd_client(handler)

    with pytest.raises(NotFoundError):
        run(
            sync_service.sync_and_generate(
                "does-not-exist", sd_client, base_dir=tmp_path, now=NOW
            )
        )
