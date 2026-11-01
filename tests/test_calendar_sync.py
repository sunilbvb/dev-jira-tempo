"""Tests for RFC 5545 iCalendar parser without third-party dependencies."""

from pathlib import Path
from tempo_log.calendar_sync import parse_ics, parse_ics_file

SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:evt1@test
DTSTART:20261102T090000Z
DTEND:20261102T093000Z
SUMMARY:Morning Sync
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
UID:evt2@test
DTSTART:20261102T140000Z
DTEND:20261102T150000Z
SUMMARY:Design Review
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
UID:evt3@test
DTSTART:20261103T110000Z
DTEND:20261103T114500Z
SUMMARY:Next Day Meeting
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_date_filtering():
    events = parse_ics(SAMPLE_ICS, target_date="2026-11-02")
    assert len(events) == 2
    assert events[0].summary == "Morning Sync"
    assert events[0].duration_minutes == 30
    assert events[0].start_clock == "09:00"
    assert events[0].end_clock == "09:30"
    assert events[1].summary == "Design Review"
    assert events[1].duration_minutes == 60


def test_to_fixed_block():
    events = parse_ics(SAMPLE_ICS, target_date="2026-11-02")
    assert events[0].to_fixed_block("MEET-1") == "09:00-09:30@MEET-1:Morning Sync"


def test_parse_ics_file(tmp_path: Path):
    f = tmp_path / "cal.ics"
    f.write_text(SAMPLE_ICS, encoding="utf-8")
    events = parse_ics_file(f, target_date="2026-11-03")
    assert len(events) == 1
    assert events[0].summary == "Next Day Meeting"
    assert events[0].duration_minutes == 45
