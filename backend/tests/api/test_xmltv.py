"""Tests for the `/xmltv/{lineup_id}.xml` static-serving endpoint.

Per CLAUDE.md, XMLTV is never generated on-the-fly — these tests write a
fixture file directly into the temp output dir rather than running full
generation, as suggested by the task brief.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path))
    with TestClient(app) as test_client:
        yield test_client


def test_404_when_no_file_generated_yet(client):
    response = client.get("/xmltv/living-room.xml")
    assert response.status_code == 404


def test_200_with_xml_content_type_once_generated(client, tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<tv></tv>\n'
    (output_dir / "living-room.xml").write_text(fixture_xml, encoding="utf-8")

    response = client.get("/xmltv/living-room.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert response.text == fixture_xml


def test_404_not_500_for_malformed_lineup_id(client):
    # `safe_segment` raises `ValueError` for a path segment that sanitizes
    # to exactly `..` — there's no real path-traversal risk (the ValueError
    # prevents the bad path from ever being used), but the route must
    # still 404 rather than letting the exception bubble up as a 500.
    response = client.get("/xmltv/..xml")
    assert response.status_code != 500

    response = client.get("/xmltv/%2E%2E.xml")
    assert response.status_code == 404


def test_route_is_not_under_api_prefix(client):
    # /xmltv/* is its own reserved top-level prefix per CLAUDE.md, not
    # nested under /api — confirm it isn't accidentally double-registered.
    response = client.get("/api/xmltv/living-room.xml")
    assert response.status_code == 404


def test_head_404_when_no_file_generated_yet(client):
    # Regression test: @router.get(...) alone only registers GET in
    # FastAPI, so a HEAD existence-check (used by the frontend to detect
    # whether a lineup's XMLTV has been generated yet) must still resolve
    # to a real 404 rather than a 405.
    response = client.head("/xmltv/living-room.xml")
    assert response.status_code == 404


def test_head_200_once_generated(client, tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<tv></tv>\n'
    (output_dir / "living-room.xml").write_text(fixture_xml, encoding="utf-8")

    response = client.head("/xmltv/living-room.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert response.content == b""
