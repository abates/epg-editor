"""FastAPI TestClient tests for the manual lineup/channel/mapping API.

Follows the same temp-data-dir pattern as `tests/test_health.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.lineup import LineupsFile
from app.storage.paths import CONFIG_DIRNAME


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path))
    with TestClient(app) as test_client:
        yield test_client


def test_create_and_list_lineups(client):
    create_response = client.post("/api/lineups", json={"name": "Living Room Antenna"})
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Living Room Antenna"
    assert created["source"] == "manual"
    assert created["channels"] == []
    assert created["sdLineupIds"] == []

    list_response = client.get("/api/lineups")
    assert list_response.status_code == 200
    assert [lineup["id"] for lineup in list_response.json()] == [created["id"]]


def test_get_lineup_404_when_missing(client):
    response = client.get("/api/lineups/does-not-exist")
    assert response.status_code == 404


def test_add_edit_remove_channel(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]

    add_response = client.post(
        f"/api/lineups/{lineup_id}/channels",
        json={"name": "KGO-TV", "number": "7.1", "tvgId": "KGO.us"},
    )
    assert add_response.status_code == 201
    channel = add_response.json()
    assert channel["name"] == "KGO-TV"
    assert channel["number"] == "7.1"
    assert channel["mapping"] is None
    assert channel["missingSince"] is None
    channel_id = channel["id"]

    edit_response = client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}",
        json={"name": "KGO HD"},
    )
    assert edit_response.status_code == 200
    assert edit_response.json()["name"] == "KGO HD"
    assert edit_response.json()["number"] == "7.1"  # untouched field preserved

    lineup_after_edit = client.get(f"/api/lineups/{lineup_id}").json()
    assert len(lineup_after_edit["channels"]) == 1

    remove_response = client.delete(f"/api/lineups/{lineup_id}/channels/{channel_id}")
    assert remove_response.status_code == 204

    lineup_after_remove = client.get(f"/api/lineups/{lineup_id}").json()
    assert lineup_after_remove["channels"] == []


def test_delete_lineup(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]
    other_id = client.post("/api/lineups", json={"name": "Other"}).json()["id"]

    response = client.delete(f"/api/lineups/{lineup_id}")
    assert response.status_code == 204

    list_response = client.get("/api/lineups")
    assert [lineup["id"] for lineup in list_response.json()] == [other_id]

    assert client.get(f"/api/lineups/{lineup_id}").status_code == 404


def test_delete_lineup_404_when_missing(client):
    response = client.delete("/api/lineups/does-not-exist")
    assert response.status_code == 404


def test_update_sd_lineup_ids(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]

    response = client.put(
        f"/api/lineups/{lineup_id}/sd-lineups",
        json={"sdLineupIds": ["USA-OTA12345", "USA-CABLE67890"]},
    )
    assert response.status_code == 200
    assert response.json()["sdLineupIds"] == ["USA-OTA12345", "USA-CABLE67890"]


def test_set_channel_mapping_happy_path(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]
    client.put(
        f"/api/lineups/{lineup_id}/sd-lineups",
        json={"sdLineupIds": ["USA-OTA12345"]},
    )
    channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "KGO-TV"}
    ).json()["id"]

    response = client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}/mapping",
        json={"sdStationId": "10123", "sdLineupId": "USA-OTA12345", "confirmed": True},
    )

    assert response.status_code == 200
    mapping = response.json()["mapping"]
    assert mapping["sdStationId"] == "10123"
    assert mapping["sdLineupId"] == "USA-OTA12345"
    assert mapping["confirmed"] is True
    assert mapping["confirmedAt"] is not None


def test_update_channel_explicit_null_clears_field_omitted_field_unchanged(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]
    channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels",
        json={"name": "KGO-TV", "logoUrl": "https://example.test/kgo.png"},
    ).json()["id"]

    # Omitting `logoUrl` entirely leaves it unchanged.
    response = client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}",
        json={"name": "KGO HD"},
    )
    assert response.status_code == 200
    assert response.json()["logoUrl"] == "https://example.test/kgo.png"

    # Explicitly sending `null` clears it.
    response = client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}",
        json={"logoUrl": None},
    )
    assert response.status_code == 200
    assert response.json()["logoUrl"] is None
    assert response.json()["name"] == "KGO HD"  # untouched by the second request


def test_update_channel_rejects_null_name_without_corrupting_disk(client, tmp_path):
    """Regression: `{"name": null}` must be rejected (400), not written to
    disk — `Channel.name` is required/non-nullable. A prior regression let
    this through via raw `setattr` with no re-validation, writing
    `name: null` into `config/lineups.json` and making every subsequent
    `GET /api/lineups` 500 with a `ValidationError`.
    """
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]
    channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "KGO-TV"}
    ).json()["id"]

    response = client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}",
        json={"name": None},
    )
    assert response.status_code == 400

    # The on-disk file is untouched: still valid, and the channel's name
    # is still what it was before the rejected request.
    lineups_path = tmp_path / CONFIG_DIRNAME / "lineups.json"
    on_disk = LineupsFile.model_validate_json(lineups_path.read_text(encoding="utf-8"))
    reloaded_channel = on_disk.lineups[0].channels[0]
    assert reloaded_channel.name == "KGO-TV"

    # And the API itself is still healthy, not 500ing on every read.
    get_response = client.get("/api/lineups")
    assert get_response.status_code == 200
    assert get_response.json()[0]["channels"][0]["name"] == "KGO-TV"


def test_update_sd_lineup_ids_rejects_removal_with_confirmed_mapping(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]
    client.put(
        f"/api/lineups/{lineup_id}/sd-lineups",
        json={"sdLineupIds": ["USA-OTA12345"]},
    )
    channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "KGO-TV"}
    ).json()["id"]
    client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}/mapping",
        json={"sdStationId": "10123", "sdLineupId": "USA-OTA12345", "confirmed": True},
    )

    response = client.put(
        f"/api/lineups/{lineup_id}/sd-lineups", json={"sdLineupIds": []}
    )

    assert response.status_code == 400

    # Confirm nothing changed: association and mapping both survive.
    lineup = client.get(f"/api/lineups/{lineup_id}").json()
    assert lineup["sdLineupIds"] == ["USA-OTA12345"]
    assert lineup["channels"][0]["mapping"]["sdLineupId"] == "USA-OTA12345"


def test_concurrent_channel_creation_does_not_lose_updates(client):
    from concurrent.futures import ThreadPoolExecutor

    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]
    concurrency = 40

    def add_one(index: int):
        return client.post(
            f"/api/lineups/{lineup_id}/channels", json={"name": f"Channel {index}"}
        )

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        responses = list(pool.map(add_one, range(concurrency)))

    assert all(response.status_code == 201 for response in responses)

    lineup = client.get(f"/api/lineups/{lineup_id}").json()
    assert len(lineup["channels"]) == concurrency


def test_add_channel_rejects_empty_name(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]

    response = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": ""}
    )

    assert response.status_code == 400
    assert client.get(f"/api/lineups/{lineup_id}").json()["channels"] == []


def test_add_channel_rejects_whitespace_only_name(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]

    response = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "   "}
    )

    assert response.status_code == 400
    assert client.get(f"/api/lineups/{lineup_id}").json()["channels"] == []


def test_add_channel_still_accepts_normal_name(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]

    response = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "KGO-TV"}
    )

    assert response.status_code == 201
    assert response.json()["name"] == "KGO-TV"


def test_update_channel_rejects_empty_name_without_corrupting_disk(client, tmp_path):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]
    channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "KGO-TV"}
    ).json()["id"]

    response = client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}",
        json={"name": ""},
    )
    assert response.status_code == 400

    lineups_path = tmp_path / CONFIG_DIRNAME / "lineups.json"
    on_disk = LineupsFile.model_validate_json(lineups_path.read_text(encoding="utf-8"))
    assert on_disk.lineups[0].channels[0].name == "KGO-TV"

    get_response = client.get("/api/lineups")
    assert get_response.status_code == 200
    assert get_response.json()[0]["channels"][0]["name"] == "KGO-TV"


def test_update_channel_rejects_whitespace_only_name_without_corrupting_disk(
    client, tmp_path
):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]
    channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "KGO-TV"}
    ).json()["id"]

    response = client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}",
        json={"name": "   "},
    )
    assert response.status_code == 400

    lineups_path = tmp_path / CONFIG_DIRNAME / "lineups.json"
    on_disk = LineupsFile.model_validate_json(lineups_path.read_text(encoding="utf-8"))
    assert on_disk.lineups[0].channels[0].name == "KGO-TV"


def test_update_channel_still_accepts_normal_name(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]
    channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "KGO-TV"}
    ).json()["id"]

    response = client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}",
        json={"name": "KGO HD"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "KGO HD"


def test_set_channel_mapping_rejects_unassociated_sd_lineup(client):
    lineup_id = client.post("/api/lineups", json={"name": "Lineup"}).json()["id"]
    # No sdLineupIds associated with this lineup at all.
    channel_id = client.post(
        f"/api/lineups/{lineup_id}/channels", json={"name": "KGO-TV"}
    ).json()["id"]

    response = client.put(
        f"/api/lineups/{lineup_id}/channels/{channel_id}/mapping",
        json={"sdStationId": "10123", "sdLineupId": "USA-OTA12345", "confirmed": True},
    )

    assert response.status_code == 400

    # Confirm nothing was persisted.
    lineup = client.get(f"/api/lineups/{lineup_id}").json()
    assert lineup["channels"][0]["mapping"] is None
