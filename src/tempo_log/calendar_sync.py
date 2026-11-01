"""Pure Python standard-library iCalendar (.ics) parser and meeting synchronizer.

Parses RFC 5545 VEVENT components into meeting items, calculating start/end times
and durations without third-party pip dependencies.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .plugins import MeetingCandidate

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    summary: str
    start_dt: datetime
    end_dt: datetime
    description: str = ""
    status: str = "CONFIRMED"
    location: str = ""

    @property
    def date_str(self) -> str:
        return self.start_dt.strftime("%Y-%m-%d")

    @property
    def start_clock(self) -> str:
        return self.start_dt.strftime("%H:%M")

    @property
    def end_clock(self) -> str:
        return self.end_dt.strftime("%H:%M")

    @property
    def duration_minutes(self) -> int:
        delta = self.end_dt - self.start_dt
        return max(1, int(delta.total_seconds() // 60))

    def to_meeting_candidate(self) -> MeetingCandidate:
        return MeetingCandidate(
            title=self.summary,
            start=self.start_clock,
            end=self.end_clock,
            minutes=self.duration_minutes,
            attended=self.status.upper() != "CANCELLED",
        )

    def to_fixed_block(self, issue_key: str = "MEETING") -> str:
        return f"{self.start_clock}-{self.end_clock}@{issue_key}:{self.summary}"


def _parse_ics_date(val: str) -> datetime:
    """Parse iCalendar DTSTART/DTEND string (e.g. 20261012T143000Z or 20261012T143000)."""
    val = val.strip()
    # Strip any parameters like TZID=...:value
    if ":" in val:
        val = val.split(":")[-1].strip()

    formats = [
        "%Y%m%dT%H%M%SZ",
        "%Y%m%dT%H%M%S",
        "%Y%m%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(val, fmt)
            if fmt == "%Y%m%d":
                dt = dt.replace(hour=9, minute=0)
            return dt
        except ValueError:
            continue
    # Fallback current time
    return datetime.now()


def parse_ics(content: str, target_date: str | None = None) -> list[CalendarEvent]:
    """Parse raw .ics text content into CalendarEvent list, optionally filtered by date."""
    events: list[CalendarEvent] = []

    # Unfold lines (RFC 5545 lines starting with space or tab are continuations)
    unfolded_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith((" ", "\t")) and unfolded_lines:
            unfolded_lines[-1] += line[1:]
        else:
            unfolded_lines.append(line)

    in_vevent = False
    current_props: dict[str, str] = {}

    for line in unfolded_lines:
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_vevent = True
            current_props = {}
            continue
        if line == "END:VEVENT":
            in_vevent = False
            summary = current_props.get("SUMMARY", "Meeting")
            dtstart_raw = current_props.get("DTSTART")
            dtend_raw = current_props.get("DTEND")

            if dtstart_raw:
                start_dt = _parse_ics_date(dtstart_raw)
                if dtend_raw:
                    end_dt = _parse_ics_date(dtend_raw)
                else:
                    end_dt = start_dt.replace(hour=start_dt.hour + 1)

                if end_dt <= start_dt:
                    end_dt = start_dt.replace(minute=start_dt.minute + 30)

                event = CalendarEvent(
                    summary=summary,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    description=current_props.get("DESCRIPTION", ""),
                    status=current_props.get("STATUS", "CONFIRMED"),
                    location=current_props.get("LOCATION", ""),
                )
                if target_date is None or event.date_str == target_date:
                    events.append(event)
            continue

        if in_vevent and ":" in line:
            prop, _, val = line.partition(":")
            prop_key = prop.split(";")[0].upper()
            current_props[prop_key] = val

    events.sort(key=lambda e: e.start_dt)
    return events


def parse_ics_file(file_path: Path | str, target_date: str | None = None) -> list[CalendarEvent]:
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Calendar file not found: {file_path}")
    return parse_ics(path.read_text(encoding="utf-8", errors="replace"), target_date=target_date)
