"""Tests for `app.services.refresh.refresh_all_lineups`.

Everything here goes through `httpx.MockTransport` — no real SD
credentials or network, ever (matches the rest of the suite; see
`tests/sd_client/test_client.py`'s module docstring).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.models.sd import SdLineupStationsResponse, SdProgram, SdStation, SdStationSchedule
from app.sd_client.client import SdClient
from app.services import lineups as lineups_service
from app.services import refresh as refresh_service
from app.services.xmltv import get_xmltv_output_path
from app.storage import sd_cache

FAKE_TOKEN = "fake-token-abc123"
NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)
# Matches `guide_window_dates(NOW, 3)` (the default `GUIDE_WINDOW_DAYS`).
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


def empty_status_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "account": {"maxLineups": 4}, "lineups": []})


def empty_lineup_stations_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"map": [], "stations": []})


def schedule_item(station_id: str, date: str, program_id: str, md5: str) -> dict:
    return {
        "stationID": station_id,
        "programs": [
            {
                "programID": program_id,
                "airDateTime": f"{date}T00:00:00Z",
                "duration": 1800,
            }
        ],
        "metadata": {"startDate": date, "md5": md5},
    }


def program_item(program_id: str) -> dict:
    return {"programID": program_id, "titles": [{"title120": f"Show {program_id}"}]}


def make_lineup_with_mapped_channel(*, name="Living Room Antenna", station_id="10123"):
    lineup = lineups_service.create_lineup(name)
    lineups_service.update_lineup_sd_lineup_ids(lineup.id, ["USA-OTA12345"])
    channel = lineups_service.add_channel(lineup.id, name="KGO-TV", tvg_id="KGO.us")
    lineups_service.set_channel_mapping(
        lineup.id, channel.id, sd_station_id=station_id, sd_lineup_id="USA-OTA12345"
    )
    return lineups_service.get_lineup(lineup.id)


# --- md5-driven skip/refetch -------------------------------------------------


def test_unchanged_schedule_is_skipped_and_changed_schedule_is_refetched(tmp_path):
    lineup = make_lineup_with_mapped_channel(station_id="10123")

    # Pre-cache day 0 with a known md5; days 1-2 are not cached at all.
    sd_cache.save_station_schedule(
        "10123",
        EXPECTED_DATES[0],
        SdStationSchedule.model_validate(
            schedule_item("10123", EXPECTED_DATES[0], "EP-OLD", "unchanged-md5")
        ),
        base_dir=tmp_path,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return empty_status_response(request)
        if path.endswith("/lineups/USA-OTA12345"):
            return empty_lineup_stations_response(request)
        if path.endswith("/schedules/md5"):
            return httpx.Response(
                200,
                json={
                    "10123": {
                        EXPECTED_DATES[0]: {"code": 0, "md5": "unchanged-md5"},
                        EXPECTED_DATES[1]: {"code": 0, "md5": "changed-md5-1"},
                        EXPECTED_DATES[2]: {"code": 0, "md5": "changed-md5-2"},
                    }
                },
            )
        if path.endswith("/schedules"):
            body = request.read().decode()
            # Only the two changed dates should ever be requested — day 0
            # (unchanged md5) must never be re-fetched in full.
            assert EXPECTED_DATES[0] not in body
            assert EXPECTED_DATES[1] in body
            assert EXPECTED_DATES[2] in body
            return httpx.Response(
                200,
                json=[
                    schedule_item("10123", EXPECTED_DATES[1], "EP-NEW-1", "changed-md5-1"),
                    schedule_item("10123", EXPECTED_DATES[2], "EP-NEW-2", "changed-md5-2"),
                ],
            )
        if path.endswith("/programs"):
            return httpx.Response(
                200, json=[program_item("EP-NEW-1"), program_item("EP-NEW-2")]
            )
        raise AssertionError(f"unexpected path {path}")

    sd_client = make_sd_client(handler)

    result = run(
        refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW)
    )

    assert result.scheduleDaysChecked == 3
    assert result.scheduleDaysSkippedUnchanged == 1
    assert result.scheduleDaysRefetched == 2
    assert result.programsFetched == 2
    assert result.errors == []

    # Day 0's cached entry is untouched (still the old programID).
    cached_day0 = sd_cache.load_station_schedule("10123", EXPECTED_DATES[0], base_dir=tmp_path)
    assert cached_day0.data.programs[0].programID == "EP-OLD"
    cached_day1 = sd_cache.load_station_schedule("10123", EXPECTED_DATES[1], base_dir=tmp_path)
    assert cached_day1.data.programs[0].programID == "EP-NEW-1"

    assert result.lineupsProcessed == 1
    assert result.lineupsRegenerated == 1
    output_path = get_xmltv_output_path(lineup.id, base_dir=tmp_path)
    assert output_path is not None


def test_malformed_md5_station_entry_only_falls_back_for_that_station(tmp_path):
    """Regression test (Finding 3): a well-formed station's md5 entry
    should still allow it to be skipped (unchanged) even when a *different*
    station in the same `/schedules/md5` response is reported in a
    malformed, flatter shape — the malformed one should fall back to a
    full fetch on its own, without disabling the skip optimization for the
    rest of the batch."""
    good_lineup = make_lineup_with_mapped_channel(name="Good Lineup", station_id="good-station")
    bad_lineup = make_lineup_with_mapped_channel(name="Bad Lineup", station_id="bad-station")

    # Pre-cache every date for the good station with known, matching md5s
    # so none of its days need a full refetch.
    good_md5s = {date: f"unchanged-md5-{date}" for date in EXPECTED_DATES}
    for date, md5 in good_md5s.items():
        sd_cache.save_station_schedule(
            "good-station",
            date,
            SdStationSchedule.model_validate(
                schedule_item("good-station", date, f"EP-OLD-{date}", md5)
            ),
            base_dir=tmp_path,
        )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return empty_status_response(request)
        if path.endswith("/lineups/USA-OTA12345"):
            return empty_lineup_stations_response(request)
        if path.endswith("/schedules/md5"):
            return httpx.Response(
                200,
                json={
                    "good-station": {
                        date: {"code": 0, "md5": md5} for date, md5 in good_md5s.items()
                    },
                    # Malformed: a flat per-station error object instead of
                    # the expected per-date dict shape.
                    "bad-station": {"code": 2201, "response": "STATION_NOT_FOUND"},
                },
            )
        if path.endswith("/schedules"):
            body = request.read().decode()
            # The good station's unchanged days must never be re-fetched;
            # the malformed station must fall back to a full fetch for
            # every date.
            assert "good-station" not in body
            assert "bad-station" in body
            return httpx.Response(
                200,
                json=[
                    schedule_item("bad-station", date, f"EP-{date}", f"md5-{date}")
                    for date in EXPECTED_DATES
                ],
            )
        if path.endswith("/programs"):
            return httpx.Response(
                200, json=[program_item(f"EP-{date}") for date in EXPECTED_DATES]
            )
        raise AssertionError(f"unexpected path {path}")

    sd_client = make_sd_client(handler)
    result = run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    assert result.errors == []
    # Only the bad station's 3 days were refetched; the good station's 3
    # cached, unchanged days were all skipped.
    assert result.scheduleDaysRefetched == 3
    assert result.scheduleDaysSkippedUnchanged == 3
    assert get_xmltv_output_path(good_lineup.id, base_dir=tmp_path) is not None
    assert get_xmltv_output_path(bad_lineup.id, base_dir=tmp_path) is not None


def test_missing_md5_entry_is_treated_as_needing_fetch(tmp_path):
    """A station/day the md5 check doesn't mention at all (e.g. SD hasn't
    published that far out yet) must default to "needs fetch", not be
    silently skipped."""
    make_lineup_with_mapped_channel(station_id="10123")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return empty_status_response(request)
        if path.endswith("/lineups/USA-OTA12345"):
            return empty_lineup_stations_response(request)
        if path.endswith("/schedules/md5"):
            return httpx.Response(200, json={})  # nothing reported for this station at all
        if path.endswith("/schedules"):
            return httpx.Response(
                200,
                json=[
                    schedule_item("10123", date, f"EP-{date}", f"md5-{date}")
                    for date in EXPECTED_DATES
                ],
            )
        if path.endswith("/programs"):
            return httpx.Response(
                200, json=[program_item(f"EP-{date}") for date in EXPECTED_DATES]
            )
        raise AssertionError(f"unexpected path {path}")

    sd_client = make_sd_client(handler)
    result = run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    assert result.scheduleDaysSkippedUnchanged == 0
    assert result.scheduleDaysRefetched == 3


# --- Station roster refresh --------------------------------------------------


def test_station_roster_refreshes_on_newer_modified_timestamp(tmp_path):
    make_lineup_with_mapped_channel(station_id="10123")
    old_modified = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new_modified = datetime(2026, 10, 1, tzinfo=timezone.utc)

    sd_cache.save_lineup_stations(
        "USA-OTA12345",
        SdLineupStationsResponse(stations=[SdStation(stationID="10123", name="old-name")]),
        modified=old_modified,
        fetched_at=NOW - timedelta(days=1),
        base_dir=tmp_path,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "account": {"maxLineups": 4},
                    "lineups": [
                        {"lineup": "USA-OTA12345", "modified": new_modified.isoformat()}
                    ],
                },
            )
        if path.endswith("/lineups/USA-OTA12345"):
            return httpx.Response(
                200,
                json={
                    "map": [],
                    "stations": [{"stationID": "10123", "name": "new-name"}],
                },
            )
        if path.endswith("/schedules/md5"):
            return httpx.Response(200, json={"10123": {}})
        if path.endswith("/schedules"):
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected path {path}")

    sd_client = make_sd_client(handler)
    result = run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    assert result.stationRostersRefreshed == 1
    assert result.stationRostersSkipped == 0
    cached = sd_cache.load_lineup_stations("USA-OTA12345", base_dir=tmp_path)
    assert cached.data.stations[0].name == "new-name"
    assert cached.modified == new_modified


def test_station_roster_skips_when_modified_unchanged_and_within_ttl(tmp_path):
    make_lineup_with_mapped_channel(station_id="10123")
    same_modified = datetime(2026, 1, 1, tzinfo=timezone.utc)

    sd_cache.save_lineup_stations(
        "USA-OTA12345",
        SdLineupStationsResponse(stations=[SdStation(stationID="10123", name="cached-name")]),
        modified=same_modified,
        fetched_at=NOW - timedelta(days=1),
        base_dir=tmp_path,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "account": {"maxLineups": 4},
                    "lineups": [
                        {"lineup": "USA-OTA12345", "modified": same_modified.isoformat()}
                    ],
                },
            )
        if path.endswith("/lineups/USA-OTA12345"):  # pragma: no cover
            raise AssertionError("must not re-fetch an unchanged, non-expired roster")
        if path.endswith("/schedules/md5"):
            return httpx.Response(200, json={"10123": {}})
        if path.endswith("/schedules"):
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected path {path}")

    sd_client = make_sd_client(handler)
    result = run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    assert result.stationRostersRefreshed == 0
    assert result.stationRostersSkipped == 1
    cached = sd_cache.load_lineup_stations("USA-OTA12345", base_dir=tmp_path)
    assert cached.data.stations[0].name == "cached-name"


def test_station_roster_refreshes_once_ttl_expires_even_if_unchanged(tmp_path):
    make_lineup_with_mapped_channel(station_id="10123")
    same_modified = datetime(2026, 1, 1, tzinfo=timezone.utc)

    sd_cache.save_lineup_stations(
        "USA-OTA12345",
        SdLineupStationsResponse(stations=[SdStation(stationID="10123", name="stale-name")]),
        modified=same_modified,
        fetched_at=NOW - timedelta(days=31),  # older than STATION_ROSTER_TTL (30 days)
        base_dir=tmp_path,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "account": {"maxLineups": 4},
                    "lineups": [
                        {"lineup": "USA-OTA12345", "modified": same_modified.isoformat()}
                    ],
                },
            )
        if path.endswith("/lineups/USA-OTA12345"):
            return httpx.Response(
                200,
                json={"map": [], "stations": [{"stationID": "10123", "name": "fresh-name"}]},
            )
        if path.endswith("/schedules/md5"):
            return httpx.Response(200, json={"10123": {}})
        if path.endswith("/schedules"):
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected path {path}")

    sd_client = make_sd_client(handler)
    result = run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    assert result.stationRostersRefreshed == 1
    cached = sd_cache.load_lineup_stations("USA-OTA12345", base_dir=tmp_path)
    assert cached.data.stations[0].name == "fresh-name"


# --- Program-fetch retry (Finding 1, HIGH) -----------------------------------


def test_failed_program_fetch_is_retried_on_a_later_run_with_unchanged_schedule_md5(tmp_path):
    """Regression test (Finding 1, HIGH): reproduces the reviewer's exact
    scenario — run 1 successfully fetches+caches a station's schedules but
    its `/programs` call fails; run 2 is against a healthy SD and the
    schedule's md5 hasn't changed (so no schedule re-fetch is needed/
    expected). Run 2 must still retry and successfully fetch the programs
    that failed on run 1 — not silently skip them forever because their
    schedule day's md5 is unchanged, which was the bug (`program_ids` used
    to be built only from schedule days *refetched this run*, so once a
    schedule day's md5 stops changing, a program fetch failure for that day
    could never be retried again)."""
    lineup = make_lineup_with_mapped_channel(station_id="10123")
    schedule_md5s = {date: f"stable-md5-{date}" for date in EXPECTED_DATES}
    program_ids = {date: f"EP-{date}" for date in EXPECTED_DATES}

    def md5_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "10123": {
                    date: {"code": 0, "md5": md5} for date, md5 in schedule_md5s.items()
                }
            },
        )

    # --- Run 1: schedules fetch fine, but `/programs` fails (e.g. a 5xx). ---
    def handler_run1(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return empty_status_response(request)
        if path.endswith("/lineups/USA-OTA12345"):
            return empty_lineup_stations_response(request)
        if path.endswith("/schedules/md5"):
            return md5_response(request)
        if path.endswith("/schedules"):
            return httpx.Response(
                200,
                json=[
                    schedule_item("10123", date, program_ids[date], schedule_md5s[date])
                    for date in EXPECTED_DATES
                ],
            )
        if path.endswith("/programs"):
            return httpx.Response(500, text="internal error")
        raise AssertionError(f"unexpected path {path}")

    sd_client_run1 = make_sd_client(handler_run1)
    result1 = run(
        refresh_service.refresh_all_lineups(sd_client_run1, base_dir=tmp_path, now=NOW)
    )

    # Schedules were fetched+cached fine; the program fetch failed and was
    # recorded, not silently dropped.
    assert result1.scheduleDaysRefetched == 3
    assert result1.programsFetched == 0
    programs_errors_run1 = [e for e in result1.errors if e.scope == "programs"]
    assert len(programs_errors_run1) == 1
    for date in EXPECTED_DATES:
        assert sd_cache.load_program(program_ids[date], base_dir=tmp_path) is None

    # --- Run 2: SD is healthy; schedule md5s are UNCHANGED from run 1. -----
    def handler_run2(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return empty_status_response(request)
        if path.endswith("/lineups/USA-OTA12345"):
            return empty_lineup_stations_response(request)
        if path.endswith("/schedules/md5"):
            return md5_response(request)
        if path.endswith("/schedules"):
            raise AssertionError(
                "must not re-fetch a schedule day whose md5 is unchanged — "
                "only the previously-failed program fetch should be retried"
            )
        if path.endswith("/programs"):
            body = request.read().decode()
            for date in EXPECTED_DATES:
                assert program_ids[date] in body
            return httpx.Response(
                200, json=[program_item(program_ids[date]) for date in EXPECTED_DATES]
            )
        raise AssertionError(f"unexpected path {path}")

    sd_client_run2 = make_sd_client(handler_run2)
    result2 = run(
        refresh_service.refresh_all_lineups(sd_client_run2, base_dir=tmp_path, now=NOW)
    )

    assert result2.errors == []
    assert result2.scheduleDaysRefetched == 0
    assert result2.scheduleDaysSkippedUnchanged == 3
    # The fix: run 2 actually retries and successfully fetches the programs
    # that failed on run 1, despite their schedule day's md5 being unchanged.
    assert result2.programsFetched == 3
    for date in EXPECTED_DATES:
        cached = sd_cache.load_program(program_ids[date], base_dir=tmp_path)
        assert cached is not None
        assert cached.data.titles[0].title120 == f"Show {program_ids[date]}"

    assert get_xmltv_output_path(lineup.id, base_dir=tmp_path) is not None


def test_cached_program_with_matching_schedule_md5_is_not_refetched(tmp_path):
    """The program-level md5 skip this fix adds: a program already cached
    with a matching `scheduleMd5` must not be re-fetched just because its
    schedule day happened to get refetched this run (e.g. the day's own
    md5 changed for an unrelated reason)."""
    make_lineup_with_mapped_channel(station_id="10123")

    sd_cache.save_program(
        "EP-CACHED",
        SdProgram.model_validate(
            {"programID": "EP-CACHED", "titles": [{"title120": "Already Cached"}]}
        ),
        schedule_md5="program-md5-cached",
        base_dir=tmp_path,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return empty_status_response(request)
        if path.endswith("/lineups/USA-OTA12345"):
            return empty_lineup_stations_response(request)
        if path.endswith("/schedules/md5"):
            return httpx.Response(
                200,
                json={
                    "10123": {
                        EXPECTED_DATES[0]: {"code": 0, "md5": "new-schedule-md5"},
                    }
                },
            )
        if path.endswith("/schedules"):
            body = request.read().decode()
            assert EXPECTED_DATES[0] in body
            return httpx.Response(
                200,
                json=[
                    {
                        "stationID": "10123",
                        "programs": [
                            {
                                "programID": "EP-CACHED",
                                "airDateTime": f"{EXPECTED_DATES[0]}T00:00:00Z",
                                "duration": 1800,
                                "md5": "program-md5-cached",
                            }
                        ],
                        "metadata": {
                            "startDate": EXPECTED_DATES[0],
                            "md5": "new-schedule-md5",
                        },
                    }
                ],
            )
        if path.endswith("/programs"):  # pragma: no cover
            raise AssertionError(
                "must not re-fetch a program whose scheduleMd5 already matches"
            )
        raise AssertionError(f"unexpected path {path}")

    sd_client = make_sd_client(handler)
    result = run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    assert result.errors == []
    assert result.programsFetched == 0


# --- Partial failure isolation -----------------------------------------------


def test_sd_error_coded_200_on_roster_fetch_does_not_wipe_cached_roster(tmp_path):
    """Regression test (Finding 2): an SD error body on HTTP 200 (e.g.
    `{"code": 2100, "response": "LINEUP_NOT_FOUND"}`) must not silently
    replace a good cached station roster with an empty one — the reviewer's
    exact repro. `get_lineup_stations` now raises `SdClientError` for this
    case (see `sd_client/client.py`), so the refresh pipeline's existing
    per-SD-lineup error handling records it and leaves the cache untouched."""
    make_lineup_with_mapped_channel(station_id="10123")
    old_modified = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new_modified = datetime(2026, 10, 1, tzinfo=timezone.utc)

    sd_cache.save_lineup_stations(
        "USA-OTA12345",
        SdLineupStationsResponse(stations=[SdStation(stationID="10123", name="good-name")]),
        modified=old_modified,
        fetched_at=NOW - timedelta(days=1),
        base_dir=tmp_path,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "account": {"maxLineups": 4},
                    "lineups": [
                        {"lineup": "USA-OTA12345", "modified": new_modified.isoformat()}
                    ],
                },
            )
        if path.endswith("/lineups/USA-OTA12345"):
            return httpx.Response(
                200, json={"code": 2100, "response": "LINEUP_NOT_FOUND"}
            )
        if path.endswith("/schedules/md5"):
            return httpx.Response(200, json={"10123": {}})
        if path.endswith("/schedules"):
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected path {path}")

    sd_client = make_sd_client(handler)
    result = run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    assert result.stationRostersRefreshed == 0
    errors = [e for e in result.errors if e.scope == "sd_lineup"]
    assert len(errors) == 1
    assert errors[0].id == "USA-OTA12345"

    cached = sd_cache.load_lineup_stations("USA-OTA12345", base_dir=tmp_path)
    assert cached.data.stations[0].name == "good-name"
    assert cached.modified == old_modified


def test_one_sd_lineup_roster_failure_does_not_abort_the_run(tmp_path):
    """A non-auth failure fetching one SD lineup's roster must still let
    schedule refresh + XMLTV regeneration proceed for everything else."""
    lineup = make_lineup_with_mapped_channel(station_id="10123")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return empty_status_response(request)
        if path.endswith("/lineups/USA-OTA12345"):
            return httpx.Response(500, text="internal error")
        if path.endswith("/schedules/md5"):
            return httpx.Response(200, json={"10123": {}})
        if path.endswith("/schedules"):
            return httpx.Response(
                200,
                json=[
                    schedule_item("10123", date, f"EP-{date}", f"md5-{date}")
                    for date in EXPECTED_DATES
                ],
            )
        if path.endswith("/programs"):
            return httpx.Response(
                200, json=[program_item(f"EP-{date}") for date in EXPECTED_DATES]
            )
        raise AssertionError(f"unexpected path {path}")

    sd_client = make_sd_client(handler)
    result = run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    assert len(result.errors) == 1
    assert result.errors[0].scope == "sd_lineup"
    assert result.errors[0].id == "USA-OTA12345"
    # Schedule refresh + regeneration still happened despite the roster failure.
    assert result.scheduleDaysRefetched == 3
    assert result.lineupsRegenerated == 1
    assert get_xmltv_output_path(lineup.id, base_dir=tmp_path) is not None


def test_one_station_schedule_failure_does_not_abort_other_lineups(tmp_path):
    """Two lineups, each mapped to a different station; one station's
    schedule fetch fails (non-auth) but the other lineup still gets
    refreshed and regenerated."""
    bad_lineup = make_lineup_with_mapped_channel(name="Bad Lineup", station_id="bad-station")
    good_lineup = make_lineup_with_mapped_channel(name="Good Lineup", station_id="good-station")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return empty_status_response(request)
        if path.endswith("/lineups/USA-OTA12345"):
            return empty_lineup_stations_response(request)
        if path.endswith("/schedules/md5"):
            return httpx.Response(200, json={"bad-station": {}, "good-station": {}})
        if path.endswith("/schedules"):
            body = request.read().decode()
            if "bad-station" in body:
                raise httpx.ReadTimeout("SD took too long")
            return httpx.Response(
                200,
                json=[schedule_item("good-station", EXPECTED_DATES[0], "EP001", "md5-1")],
            )
        if path.endswith("/programs"):
            return httpx.Response(200, json=[program_item("EP001")])
        raise AssertionError(f"unexpected path {path}")

    sd_client = make_sd_client(handler)
    result = run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    station_errors = [e for e in result.errors if e.scope == "station"]
    assert len(station_errors) == 1
    assert station_errors[0].id == "bad-station"

    assert result.lineupsProcessed == 2
    assert result.lineupsRegenerated == 2  # generation itself never fails here
    assert get_xmltv_output_path(good_lineup.id, base_dir=tmp_path) is not None
    assert get_xmltv_output_path(bad_lineup.id, base_dir=tmp_path) is not None


def test_auth_error_propagates_instead_of_being_collected(tmp_path):
    """An account-wide auth failure must abort the run (raise), not be
    quietly recorded as a per-item error — see module docstring."""
    make_lineup_with_mapped_channel(station_id="10123")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        return httpx.Response(403, text="TOKEN_INVALID")

    sd_client = make_sd_client(handler)

    from app.sd_client.client import SdClientError

    with pytest.raises(SdClientError) as excinfo:
        run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    assert excinfo.value.is_auth_error


# --- Trivial no-op lineups ----------------------------------------------------


def test_lineup_with_no_mapped_channels_and_no_sd_lineups_still_regenerates(tmp_path):
    lineup = lineups_service.create_lineup("Empty Lineup")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return token_response(request)
        if path.endswith("/status"):
            return empty_status_response(request)
        raise AssertionError(f"unexpected path {path} — must not speculatively fetch anything")

    sd_client = make_sd_client(handler)
    result = run(refresh_service.refresh_all_lineups(sd_client, base_dir=tmp_path, now=NOW))

    assert result.lineupsProcessed == 1
    assert result.lineupsRegenerated == 1
    assert result.stationRostersRefreshed == 0
    assert result.scheduleDaysChecked == 0
    assert get_xmltv_output_path(lineup.id, base_dir=tmp_path) is not None
