"""FastAPI TestClient tests for the M3U import endpoints.

Follows the same temp-data-dir pattern as `tests/api/test_lineups.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

SIMPLE_M3U = (
    "#EXTM3U\n"
    '#EXTINF:-1 tvg-id="KGO.us" tvg-name="KGO-TV" tvg-chno="7.1",KGO-TV\n'
    "http://hdhomerun.local/auto/v7.1\n"
    '#EXTINF:-1 tvg-id="KPIX.us" tvg-name="KPIX" tvg-chno="5.1",KPIX\n'
    "http://hdhomerun.local/auto/v5.1\n"
)

SIMPLE_M3U_WITH_ONE_REMOVED_AND_ONE_UPDATED = (
    "#EXTM3U\n"
    '#EXTINF:-1 tvg-id="KGO.us" tvg-name="KGO-TV HD" tvg-chno="7.2",KGO-TV HD\n'
    "http://hdhomerun.local/auto/v7.2\n"
    '#EXTINF:-1 tvg-id="NEW.us" tvg-name="New Channel" tvg-chno="9.1",New Channel\n'
    "http://hdhomerun.local/auto/v9.1\n"
)

NOT_M3U = "not an m3u file at all\njust text\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path))
    with TestClient(app) as test_client:
        yield test_client


def test_import_m3u_new_lineup(client):
    response = client.post(
        "/api/lineups/import-m3u",
        data={"name": "HDHomeRun"},
        files={"file": ("playlist.m3u", SIMPLE_M3U, "audio/x-mpegurl")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["lineup"]["name"] == "HDHomeRun"
    assert body["lineup"]["source"] == "m3u"
    assert len(body["lineup"]["channels"]) == 2
    assert len(body["result"]["added"]) == 2
    assert body["result"]["updated"] == []
    assert body["result"]["flaggedMissing"] == []
    added_tvg_ids = {c["tvgId"] for c in body["result"]["added"]}
    assert added_tvg_ids == {"KGO.us", "KPIX.us"}


def test_import_m3u_reimport_mix_of_new_updated_and_missing(client):
    create_response = client.post(
        "/api/lineups/import-m3u",
        data={"name": "HDHomeRun"},
        files={"file": ("playlist.m3u", SIMPLE_M3U, "audio/x-mpegurl")},
    )
    lineup_id = create_response.json()["lineup"]["id"]

    reimport_response = client.post(
        f"/api/lineups/{lineup_id}/import-m3u",
        files={
            "file": (
                "playlist2.m3u",
                SIMPLE_M3U_WITH_ONE_REMOVED_AND_ONE_UPDATED,
                "audio/x-mpegurl",
            )
        },
    )

    assert reimport_response.status_code == 200
    body = reimport_response.json()

    # KGO.us matched and updated.
    assert len(body["result"]["updated"]) == 1
    updated = body["result"]["updated"][0]
    assert updated["tvgId"] == "KGO.us"
    assert updated["name"] == "KGO-TV HD"
    assert updated["number"] == "7.2"

    # NEW.us is a brand-new addition.
    assert len(body["result"]["added"]) == 1
    assert body["result"]["added"][0]["tvgId"] == "NEW.us"

    # KPIX.us vanished from the new playlist -> flagged missing, not deleted.
    assert len(body["result"]["flaggedMissing"]) == 1
    missing = body["result"]["flaggedMissing"][0]
    assert missing["tvgId"] == "KPIX.us"
    assert missing["missingSince"] is not None

    lineup = client.get(f"/api/lineups/{lineup_id}").json()
    assert len(lineup["channels"]) == 3  # nothing deleted
    kpix = next(c for c in lineup["channels"] if c["tvgId"] == "KPIX.us")
    assert kpix["missingSince"] is not None


def test_import_m3u_reimport_preserves_mapping(client):
    create_response = client.post(
        "/api/lineups/import-m3u",
        data={"name": "HDHomeRun"},
        files={"file": ("playlist.m3u", SIMPLE_M3U, "audio/x-mpegurl")},
    )
    lineup = create_response.json()["lineup"]
    lineup_id = lineup["id"]
    channel_id = next(c["id"] for c in lineup["channels"] if c["tvgId"] == "KGO.us")

    client.put(
        f"/api/lineups/{lineup_id}/sd-lineups", json={"sdLineupIds": ["USA-OTA"]}
    )
    client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}/mapping",
        json={"sdStationId": "10123", "sdLineupId": "USA-OTA"},
    )

    client.post(
        f"/api/lineups/{lineup_id}/import-m3u",
        files={
            "file": (
                "playlist2.m3u",
                SIMPLE_M3U_WITH_ONE_REMOVED_AND_ONE_UPDATED,
                "audio/x-mpegurl",
            )
        },
    )

    refreshed = client.get(f"/api/lineups/{lineup_id}").json()
    kgo = next(c for c in refreshed["channels"] if c["tvgId"] == "KGO.us")
    assert kgo["name"] == "KGO-TV HD"  # metadata updated
    assert kgo["mapping"]["sdStationId"] == "10123"  # mapping preserved


def test_import_m3u_rejects_reimport_into_manual_lineup(client):
    manual_lineup_id = client.post(
        "/api/lineups", json={"name": "Manually Built"}
    ).json()["id"]

    response = client.post(
        f"/api/lineups/{manual_lineup_id}/import-m3u",
        files={"file": ("playlist.m3u", SIMPLE_M3U, "audio/x-mpegurl")},
    )

    assert response.status_code == 400
    # Nothing was added to the manual lineup.
    lineup = client.get(f"/api/lineups/{manual_lineup_id}").json()
    assert lineup["channels"] == []


def test_import_m3u_reimport_404_for_missing_lineup(client):
    response = client.post(
        "/api/lineups/does-not-exist/import-m3u",
        files={"file": ("playlist.m3u", SIMPLE_M3U, "audio/x-mpegurl")},
    )
    assert response.status_code == 404


def test_import_m3u_new_lineup_rejects_malformed_file(client):
    response = client.post(
        "/api/lineups/import-m3u",
        data={"name": "Bad"},
        files={"file": ("not-m3u.txt", NOT_M3U, "text/plain")},
    )
    assert response.status_code == 400
    # Nothing was created.
    assert client.get("/api/lineups").json() == []


def test_import_m3u_reimport_rejects_malformed_file(client):
    create_response = client.post(
        "/api/lineups/import-m3u",
        data={"name": "HDHomeRun"},
        files={"file": ("playlist.m3u", SIMPLE_M3U, "audio/x-mpegurl")},
    )
    lineup_id = create_response.json()["lineup"]["id"]

    response = client.post(
        f"/api/lineups/{lineup_id}/import-m3u",
        files={"file": ("not-m3u.txt", NOT_M3U, "text/plain")},
    )
    assert response.status_code == 400

    # Lineup untouched by the failed re-import.
    lineup = client.get(f"/api/lineups/{lineup_id}").json()
    assert len(lineup["channels"]) == 2


def test_import_m3u_rejects_oversized_upload(client):
    from app.api.m3u import MAX_UPLOAD_BYTES

    oversized = "#EXTM3U\n" + ("#" * (MAX_UPLOAD_BYTES + 1))
    response = client.post(
        "/api/lineups/import-m3u",
        data={"name": "Huge"},
        files={"file": ("huge.m3u", oversized, "audio/x-mpegurl")},
    )
    assert response.status_code == 400
