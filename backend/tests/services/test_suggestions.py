"""Tests for `app.services.suggestions`.

Everything here goes through `httpx.MockTransport` — no real SD
credentials or network, ever (matches the rest of the suite; see
`tests/sd_client/test_client.py`'s module docstring).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.sd_client.client import SdClient
from app.services import lineups as lineups_service
from app.services import suggestions as suggestions_service
from app.storage import sd_cache

FAKE_TOKEN = "fake-token-abc123"


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


def make_lineup(sd_lineup_ids: list[str]) -> str:
    lineup = lineups_service.create_lineup("Living Room Antenna")
    lineups_service.update_lineup_sd_lineup_ids(lineup.id, sd_lineup_ids)
    return lineup.id


def lineup_stations_handler(sd_lineup_id: str, stations: list[dict], calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith(f"/lineups/{sd_lineup_id}"):
            calls.append(sd_lineup_id)
            return stations_response(stations)
        raise AssertionError(f"unexpected path {request.url.path}")

    return handler


# --- Obvious match scores high -----------------------------------------------


def test_obvious_match_scores_high_and_is_top_suggestion(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    channel = lineups_service.add_channel(lineup_id, name="KGO-TV")

    calls: list[str] = []
    sd_client = make_sd_client(
        lineup_stations_handler(
            "USA-OTA12345", [kgo_station(), fox_station()], calls
        )
    )

    result = run(
        suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path)
    )

    assert result.lineupId == lineup_id
    assert result.stationPoolSize == 2
    assert result.channelsScored == 1
    assert calls == ["USA-OTA12345"]

    updated = lineups_service.get_lineup(lineup_id)
    updated_channel = next(c for c in updated.channels if c.id == channel.id)
    assert updated_channel.mapping is not None
    top = updated_channel.mapping.suggestions[0]
    assert top.sdStationId == "10123"
    assert top.score > 0.95


def test_obvious_non_match_scores_low(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="Ghost Channel")

    calls: list[str] = []
    sd_client = make_sd_client(
        lineup_stations_handler(
            "USA-OTA12345", [kgo_station(), fox_station()], calls
        )
    )

    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    updated = lineups_service.get_lineup(lineup_id)
    suggestions = updated.channels[0].mapping.suggestions
    # Still populated (up to the candidate pool size), but nothing clears
    # the bulk-accept threshold for a genuine non-match.
    assert all(s.score < suggestions_service.BULK_ACCEPT_THRESHOLD for s in suggestions)


# --- Recomputed, not accumulated ---------------------------------------------


def test_suggestions_are_recomputed_not_accumulated_on_second_run(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    calls: list[str] = []
    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station()], calls)
    )

    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))
    first = lineups_service.get_lineup(lineup_id).channels[0].mapping.suggestions
    assert len(first) == 1

    # Run again against a now-larger candidate pool (cache was already
    # populated by the first run, so this second run's handler is never
    # actually invoked for the station list — it's just here to prove the
    # suggestions list reflects a fresh computation, not an accumulation,
    # by re-deriving from the same single cached station each time).
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))
    second = lineups_service.get_lineup(lineup_id).channels[0].mapping.suggestions

    assert len(second) == 1
    assert second == first


def test_second_run_reflects_changed_sd_lineup_ids_not_stale_suggestions(tmp_path):
    """A more decisive recompute-vs-accumulate check: associate a second SD
    lineup between runs and confirm the suggestion list grows to include
    the new candidate rather than just appending onto old state."""
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    calls: list[str] = []
    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station()], calls)
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))
    first = lineups_service.get_lineup(lineup_id).channels[0].mapping.suggestions
    assert {s.sdStationId for s in first} == {"10123"}

    lineups_service.update_lineup_sd_lineup_ids(lineup_id, ["USA-OTA12345", "USA-CABLE999"])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station()])
        if request.url.path.endswith("/lineups/USA-CABLE999"):
            return stations_response([fox_station()])
        raise AssertionError(f"unexpected path {request.url.path}")

    sd_client2 = make_sd_client(handler)
    run(suggestions_service.generate_suggestions(lineup_id, sd_client2, base_dir=tmp_path))
    second = lineups_service.get_lineup(lineup_id).channels[0].mapping.suggestions

    assert {s.sdStationId for s in second} == {"10123", "10456"}


# --- No speculative bulk-fetching ---------------------------------------------


def test_only_fetches_stations_for_associated_sd_lineup_ids(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station()])
        raise AssertionError(
            f"must not fetch any SD lineup other than the associated one: {request.url.path}"
        )

    sd_client = make_sd_client(handler)
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))


def test_cache_hit_skips_the_network_call_entirely(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    from app.models.sd import SdLineupStationsResponse, SdStation

    sd_cache.save_lineup_stations(
        "USA-OTA12345",
        SdLineupStationsResponse(stations=[SdStation(**kgo_station())]),
        base_dir=tmp_path,
    )

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("must not touch the network on a cache hit")

    sd_client = make_sd_client(handler)
    result = run(
        suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path)
    )
    assert result.stationPoolSize == 1


# --- Union + dedup across multiple SD lineups --------------------------------


def test_station_pool_unions_and_dedups_across_sd_lineups(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345", "USA-CABLE999"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return token_response(request)
        if request.url.path.endswith("/lineups/USA-OTA12345"):
            return stations_response([kgo_station(), fox_station()])
        if request.url.path.endswith("/lineups/USA-CABLE999"):
            # Same station (10123) appears again in the second SD lineup —
            # must be deduped, not double-counted/double-scored.
            return stations_response([kgo_station()])
        raise AssertionError(f"unexpected path {request.url.path}")

    sd_client = make_sd_client(handler)
    result = run(
        suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path)
    )

    assert result.stationPoolSize == 2
    suggestions = lineups_service.get_lineup(lineup_id).channels[0].mapping.suggestions
    assert len(suggestions) == 2
    assert len({s.sdStationId for s in suggestions}) == 2


# --- Top-N cutoff -------------------------------------------------------------


def test_caps_suggestions_at_max_per_channel(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    stations = [
        {"stationID": f"S{i}", "name": f"KGO-TV {i}", "callsign": "KGO", "affiliate": "ABC"}
        for i in range(10)
    ]

    sd_client = make_sd_client(lineup_stations_handler("USA-OTA12345", stations, []))
    result = run(
        suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path)
    )

    assert result.stationPoolSize == 10
    suggestions = lineups_service.get_lineup(lineup_id).channels[0].mapping.suggestions
    assert len(suggestions) == suggestions_service.MAX_SUGGESTIONS_PER_CHANNEL
    # Sorted descending by score.
    scores = [s.score for s in suggestions]
    assert scores == sorted(scores, reverse=True)


def test_name_only_tie_break_keeps_genuine_name_match_in_top_n(tmp_path):
    """A secondary tie-break (Finding 3): when several stations tie on the
    primary score purely by sharing an `affiliate` match, a station whose
    own *name* genuinely resembles the channel should be preferred over
    affiliate-only ties so pool-insertion order alone can't push it out of
    the top-N cutoff."""
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="ABC")

    # 5 "noise" stations: tie at the maximum score purely via an exact
    # `affiliate` match ("ABC" vs "ABC"), but their own `name` has nothing
    # in common with the channel.
    noise_stations = [
        {
            "stationID": f"N{i}",
            "name": f"Random Place {i}",
            "callsign": f"WXX{i}",
            "affiliate": "ABC",
        }
        for i in range(5)
    ]
    # The genuine match: also ties at the maximum primary score (its
    # `affiliate` matches too), but its `name` *also* matches the channel
    # directly -- a strictly better candidate once ties are broken.
    # Placed last so a naive stable sort (no tie-break) would drop it from
    # the top 5 behind the 5 affiliate-only noise stations.
    genuine_station = {
        "stationID": "GENUINE",
        "name": "ABC",
        "callsign": "WABC",
        "affiliate": "ABC",
    }

    sd_client = make_sd_client(
        lineup_stations_handler(
            "USA-OTA12345", noise_stations + [genuine_station], []
        )
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    suggestions = lineups_service.get_lineup(lineup_id).channels[0].mapping.suggestions
    assert len(suggestions) == suggestions_service.MAX_SUGGESTIONS_PER_CHANNEL
    station_ids = [s.sdStationId for s in suggestions]
    assert "GENUINE" in station_ids
    # The tie-break ranks it ahead of the affiliate-only noise entries.
    assert station_ids[0] == "GENUINE"


# --- Confirmed channels are still recomputed (suggestions only) -------------


def test_confirmed_channel_suggestions_recomputed_but_mapping_untouched(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    channel = lineups_service.add_channel(lineup_id, name="KGO-TV")
    lineups_service.set_channel_mapping(
        lineup_id, channel.id, sd_station_id="10123", sd_lineup_id="USA-OTA12345"
    )

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station(), fox_station()], [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    updated = lineups_service.get_lineup(lineup_id).channels[0]
    assert updated.mapping.confirmed is True
    assert updated.mapping.sdStationId == "10123"
    assert len(updated.mapping.suggestions) == 2


def test_lineup_not_found_raises(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should never reach the network")

    sd_client = make_sd_client(handler)
    with pytest.raises(lineups_service.NotFoundError):
        run(
            suggestions_service.generate_suggestions(
                "does-not-exist", sd_client, base_dir=tmp_path
            )
        )


# --- Bulk accept --------------------------------------------------------------


def test_bulk_accept_confirms_at_or_above_threshold_leaves_below_alone(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    good_channel = lineups_service.add_channel(lineup_id, name="KGO-TV")
    bad_channel = lineups_service.add_channel(lineup_id, name="Ghost Channel")

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station(), fox_station()], [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    result = suggestions_service.bulk_accept_suggestions(lineup_id)

    assert result.lineupId == lineup_id
    assert result.threshold == suggestions_service.BULK_ACCEPT_THRESHOLD
    confirmed_ids = {c.channelId for c in result.confirmed}
    assert good_channel.id in confirmed_ids
    assert bad_channel.id not in confirmed_ids

    updated = lineups_service.get_lineup(lineup_id)
    good_updated = next(c for c in updated.channels if c.id == good_channel.id)
    bad_updated = next(c for c in updated.channels if c.id == bad_channel.id)
    assert good_updated.mapping.confirmed is True
    assert good_updated.mapping.sdStationId == "10123"
    assert good_updated.mapping.confirmedAt is not None
    assert bad_updated.mapping.confirmed is False
    # Suggestions remain visible even for the untouched channel.
    assert bad_updated.mapping.suggestions


def test_bulk_accept_does_not_touch_already_confirmed_channels(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    channel = lineups_service.add_channel(lineup_id, name="KGO-TV")
    lineups_service.set_channel_mapping(
        lineup_id, channel.id, sd_station_id="99999", sd_lineup_id="USA-OTA12345"
    )

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station(), fox_station()], [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    result = suggestions_service.bulk_accept_suggestions(lineup_id)

    assert result.confirmedCount == 0
    updated = lineups_service.get_lineup(lineup_id).channels[0]
    # Untouched — still points at the manually-set station, not the
    # higher-scoring suggestion that bulk-accept would otherwise prefer.
    assert updated.mapping.sdStationId == "99999"


def test_bulk_accept_skips_channel_with_no_mapping(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")
    # Never ran generate_suggestions — no mapping at all.

    result = suggestions_service.bulk_accept_suggestions(lineup_id)
    assert result.confirmedCount == 0


def test_bulk_accept_custom_threshold(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    channel = lineups_service.add_channel(lineup_id, name="Antenna TV")

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station()], [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    # With the default threshold this channel's weak match isn't accepted.
    default_result = suggestions_service.bulk_accept_suggestions(lineup_id)
    assert default_result.confirmedCount == 0

    # A much lower custom threshold does accept it (proves `threshold` is
    # actually respected, not hardcoded).
    low_result = suggestions_service.bulk_accept_suggestions(lineup_id, threshold=0.0)
    assert low_result.confirmedCount == 1
    assert low_result.confirmed[0].channelId == channel.id


def test_bulk_accept_lineup_not_found_raises(tmp_path):
    with pytest.raises(lineups_service.NotFoundError):
        suggestions_service.bulk_accept_suggestions("does-not-exist")


def test_bulk_accept_skips_channel_with_tied_top_suggestions_for_different_stations(
    tmp_path,
):
    """Regression test for the peer-reviewer's "FOX" probe: a channel named
    exactly like a bare network affiliate scores a perfect 1.0 against
    *every* station sharing that affiliate. `bulk_accept_suggestions` must
    not silently confirm an arbitrary one of those tied candidates — it
    should leave the channel for manual review instead."""
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="FOX")

    # Five different stations, all affiliated with "FOX" in different
    # markets -- none of their `name`/`callsign` fields match "FOX" at all,
    # so the *only* reason each ties at the maximum score is the shared
    # `affiliate` field.
    fox_affiliate_stations = [
        {
            "stationID": f"2000{i}",
            "name": f"Channel {i} Local",
            "callsign": f"WFX{i}",
            "affiliate": "FOX",
        }
        for i in range(5)
    ]

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", fox_affiliate_stations, [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    suggestions = lineups_service.get_lineup(lineup_id).channels[0].mapping.suggestions
    # Sanity check the premise: all top suggestions genuinely tie at a
    # perfect score, pointing at different stations.
    assert all(s.score == 1.0 for s in suggestions)
    assert len({s.sdStationId for s in suggestions}) == len(suggestions)

    result = suggestions_service.bulk_accept_suggestions(lineup_id)

    assert result.confirmedCount == 0
    assert result.confirmed == []

    updated = lineups_service.get_lineup(lineup_id).channels[0]
    assert updated.mapping.confirmed is False
    assert updated.mapping.sdStationId is None
    # Suggestions remain visible for manual review.
    assert updated.mapping.suggestions


def test_enrich_lineup_suggestions_populates_name_and_callsign_from_cache(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station(), fox_station()], [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    lineup = lineups_service.get_lineup(lineup_id)
    # The in-memory `Lineup` fresh off `get_lineup` has no display fields
    # yet -- only the enrichment step below should populate them.
    assert all(s.stationName is None for s in lineup.channels[0].mapping.suggestions)

    enriched = suggestions_service.enrich_lineup_suggestions(lineup, base_dir=tmp_path)

    top = next(
        s for s in enriched.channels[0].mapping.suggestions if s.sdStationId == "10123"
    )
    assert top.stationName == "KGO-TV"
    assert top.callsign == "KGO"

    # The original, un-enriched object passed in must be untouched (this
    # is a pure, non-mutating enrichment step).
    assert all(s.stationName is None for s in lineup.channels[0].mapping.suggestions)


def test_enrich_lineup_suggestions_leaves_fields_none_on_cache_miss(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station()], [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    # Evict the cache entirely -- simulates a disassociated SD lineup or a
    # cleared cache directory.
    sd_cache.invalidate_lineup_stations("USA-OTA12345", base_dir=tmp_path)

    lineup = lineups_service.get_lineup(lineup_id)
    enriched = suggestions_service.enrich_lineup_suggestions(lineup, base_dir=tmp_path)

    suggestion = enriched.channels[0].mapping.suggestions[0]
    assert suggestion.sdStationId == "10123"
    assert suggestion.stationName is None
    assert suggestion.callsign is None
    assert suggestion.logoUrl is None


def test_enrich_lineups_suggestions_handles_a_list(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station()], [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    enriched = suggestions_service.enrich_lineups_suggestions(
        lineups_service.list_lineups(), base_dir=tmp_path
    )
    lineup = next(l for l in enriched if l.id == lineup_id)
    assert lineup.channels[0].mapping.suggestions[0].stationName == "KGO-TV"


def test_enrich_channel_suggestions_populates_name_and_callsign_from_cache(tmp_path):
    """Single-`Channel` sibling of `enrich_lineup_suggestions` — needed by
    every `api/lineups.py` route that returns a bare `Channel` (e.g.
    `update_channel`), not just the whole-`Lineup` GET routes."""
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station(), fox_station()], [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    channel = lineups_service.get_lineup(lineup_id).channels[0]
    # Fresh off storage, no display fields yet.
    assert all(s.stationName is None for s in channel.mapping.suggestions)

    enriched = suggestions_service.enrich_channel_suggestions(channel, base_dir=tmp_path)

    top = next(
        s for s in enriched.mapping.suggestions if s.sdStationId == "10123"
    )
    assert top.stationName == "KGO-TV"
    assert top.callsign == "KGO"

    # Pure, non-mutating: the original object passed in is untouched.
    assert all(s.stationName is None for s in channel.mapping.suggestions)


def test_enrich_channel_suggestions_leaves_fields_none_on_cache_miss(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    lineups_service.add_channel(lineup_id, name="KGO-TV")

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station()], [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    sd_cache.invalidate_lineup_stations("USA-OTA12345", base_dir=tmp_path)

    channel = lineups_service.get_lineup(lineup_id).channels[0]
    enriched = suggestions_service.enrich_channel_suggestions(channel, base_dir=tmp_path)

    suggestion = enriched.mapping.suggestions[0]
    assert suggestion.sdStationId == "10123"
    assert suggestion.stationName is None
    assert suggestion.callsign is None
    assert suggestion.logoUrl is None


def test_enrich_channel_suggestions_noop_for_channel_with_no_mapping(tmp_path):
    lineup_id = make_lineup(["USA-OTA12345"])
    channel = lineups_service.add_channel(lineup_id, name="KGO-TV")

    # No mapping at all yet -- must not raise, just return as-is.
    enriched = suggestions_service.enrich_channel_suggestions(channel, base_dir=tmp_path)
    assert enriched.mapping is None


def test_bulk_accept_confirms_when_top_is_uniquely_highest_despite_other_high_scores(
    tmp_path,
):
    """Companion to the tie-skip test above: a clear (non-tied) winner above
    threshold must still be auto-confirmed even when other suggestions also
    clear the threshold, as long as they don't tie with the top score."""
    lineup_id = make_lineup(["USA-OTA12345"])
    channel = lineups_service.add_channel(lineup_id, name="KGO-TV")

    sd_client = make_sd_client(
        lineup_stations_handler("USA-OTA12345", [kgo_station(), fox_station()], [])
    )
    run(suggestions_service.generate_suggestions(lineup_id, sd_client, base_dir=tmp_path))

    result = suggestions_service.bulk_accept_suggestions(lineup_id)

    confirmed_ids = {c.channelId for c in result.confirmed}
    assert channel.id in confirmed_ids
    updated = lineups_service.get_lineup(lineup_id).channels[0]
    assert updated.mapping.confirmed is True
    assert updated.mapping.sdStationId == "10123"
