"""Tests for `app.services.xmltv`.

Generated output is validated against a vendored copy of the real XMLTV
DTD (`tests/fixtures/xmltv.dtd`, see `tests/fixtures/README.md` for
provenance) using `lxml`, not just checked for well-formedness — this
catches structural bugs (wrong element order/nesting, missing required
attributes) that plain `ElementTree` parsing wouldn't.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from lxml import etree

from app.models.lineup import Channel, ChannelMapping, Lineup, LineupSource
from app.models.sd import (
    SdProgram,
    SdProgramDescriptionEntry,
    SdProgramTitle,
    SdScheduleProgram,
    SdStationSchedule,
)
from app.services import xmltv as xmltv_service
from app.storage import sd_cache

DTD_PATH = Path(__file__).parent.parent / "fixtures" / "xmltv.dtd"


def validate_against_dtd(xml_text: str) -> None:
    dtd = etree.DTD(str(DTD_PATH))
    document = etree.fromstring(xml_text.encode("utf-8"))
    assert dtd.validate(document), dtd.error_log


def make_lineup(channels: list[Channel]) -> Lineup:
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    return Lineup(
        id="living-room",
        name="Living Room Antenna",
        source=LineupSource.MANUAL,
        createdAt=now,
        updatedAt=now,
        sdLineupIds=["USA-OTA12345"],
        channels=channels,
    )


def test_empty_lineup_produces_minimal_valid_document(tmp_path):
    lineup = make_lineup(channels=[])

    xml_text = xmltv_service.build_xmltv_document(lineup, base_dir=tmp_path)

    validate_against_dtd(xml_text)
    assert "<channel" not in xml_text
    assert "<programme" not in xml_text


def test_channel_with_no_confirmed_mapping_is_skipped_not_errored(tmp_path):
    unmapped_channel = Channel(id="ch1", name="Unmapped Channel")
    needs_review_channel = Channel(
        id="ch2",
        name="Needs Review Channel",
        mapping=ChannelMapping(confirmed=False, suggestions=[]),
    )
    lineup = make_lineup(channels=[unmapped_channel, needs_review_channel])

    xml_text = xmltv_service.build_xmltv_document(lineup, base_dir=tmp_path)

    validate_against_dtd(xml_text)
    assert "<channel" not in xml_text
    assert "<programme" not in xml_text


def test_confirmed_mapping_with_cached_data_produces_programmes(tmp_path):
    channel = Channel(
        id="ch1",
        name="KGO-TV",
        tvgId="KGO.us",
        logoUrl="https://example.test/kgo.png",
        mapping=ChannelMapping(
            sdStationId="10123",
            sdLineupId="USA-OTA12345",
            confirmed=True,
            confirmedAt=datetime(2026, 10, 29, tzinfo=timezone.utc),
        ),
    )
    lineup = make_lineup(channels=[channel])

    schedule = SdStationSchedule(
        stationID="10123",
        programs=[
            SdScheduleProgram(
                programID="EP01234560001",
                airDateTime=datetime(2026, 10, 29, 0, 0, tzinfo=timezone.utc),
                duration=1800,
            ),
            SdScheduleProgram(
                programID="EP01234560002",
                airDateTime=datetime(2026, 10, 29, 0, 30, tzinfo=timezone.utc),
                duration=1800,
            ),
        ],
    )
    sd_cache.save_station_schedule("10123", "2026-10-29", schedule, base_dir=tmp_path)

    program_one = SdProgram(
        programID="EP01234560001",
        titles=[SdProgramTitle(title120="Nightly News")],
        descriptions={
            "description100": [
                SdProgramDescriptionEntry(description="Local and national news.")
            ]
        },
    )
    sd_cache.save_program("EP01234560001", program_one, base_dir=tmp_path)
    # Deliberately leave EP01234560002's program metadata uncached, to
    # exercise the "schedule exists but program metadata doesn't" fallback.

    xml_text = xmltv_service.build_xmltv_document(
        lineup, now=datetime(2026, 10, 29, tzinfo=timezone.utc), base_dir=tmp_path
    )

    validate_against_dtd(xml_text)

    document = etree.fromstring(xml_text.encode("utf-8"))
    channel_els = document.findall("channel")
    assert len(channel_els) == 1
    assert channel_els[0].get("id") == "KGO.us"
    assert channel_els[0].find("display-name").text == "KGO-TV"
    assert channel_els[0].find("icon").get("src") == "https://example.test/kgo.png"

    programme_els = document.findall("programme")
    assert len(programme_els) == 2
    assert programme_els[0].get("channel") == "KGO.us"
    assert programme_els[0].get("start") == "20261029000000 +0000"
    assert programme_els[0].get("stop") == "20261029003000 +0000"
    assert programme_els[0].find("title").text == "Nightly News"
    assert programme_els[0].find("desc").text == "Local and national news."

    # Second programme: schedule cached, program metadata not cached.
    assert programme_els[1].find("title").text == "Unknown"
    assert programme_els[1].find("desc") is None


def test_duplicate_tvg_id_is_skipped_not_merged(tmp_path, caplog):
    # Two confirmed-mapped channels sharing a tvgId would otherwise produce
    # two <channel> elements with the same id attribute, which a consumer
    # effectively merges — keep the first, skip (and log) the rest, don't
    # crash generation.
    first = Channel(
        id="ch1",
        name="KGO-TV (first)",
        tvgId="KGO.us",
        mapping=ChannelMapping(
            sdStationId="10123", sdLineupId="USA-OTA12345", confirmed=True
        ),
    )
    duplicate = Channel(
        id="ch2",
        name="KGO-TV (duplicate)",
        tvgId="KGO.us",
        mapping=ChannelMapping(
            sdStationId="10124", sdLineupId="USA-OTA12345", confirmed=True
        ),
    )
    lineup = make_lineup(channels=[first, duplicate])

    with caplog.at_level("WARNING"):
        xml_text = xmltv_service.build_xmltv_document(lineup, base_dir=tmp_path)

    validate_against_dtd(xml_text)
    document = etree.fromstring(xml_text.encode("utf-8"))
    channel_els = document.findall("channel")
    assert len(channel_els) == 1
    assert channel_els[0].get("id") == "KGO.us"
    assert channel_els[0].find("display-name").text == "KGO-TV (first)"
    assert any("duplicate" in record.message.lower() for record in caplog.records)


def test_generate_xmltv_writes_file_atomically(tmp_path):
    channel = Channel(
        id="ch1",
        name="KGO-TV",
        mapping=ChannelMapping(
            sdStationId="10123", sdLineupId="USA-OTA12345", confirmed=True
        ),
    )
    lineup = make_lineup(channels=[channel])

    output_path = xmltv_service.generate_xmltv(lineup, base_dir=tmp_path)

    assert output_path.is_file()
    assert output_path.name == "living-room.xml"
    validate_against_dtd(output_path.read_text(encoding="utf-8"))


def test_generate_xmltv_for_lineup_id_raises_not_found(tmp_path):
    from app.services.lineups import NotFoundError

    with pytest.raises(NotFoundError):
        xmltv_service.generate_xmltv_for_lineup_id("does-not-exist", base_dir=tmp_path)
