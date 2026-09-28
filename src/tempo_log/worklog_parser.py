"""Parser for markdown worklog files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedWorklogEntry:
    date: str
    issue: str
    start_time: str
    end_time: str
    hours: float
    description: str
    line_number: int
    is_skip: bool = False


@dataclass
class WorklogParseResult:
    entries: list[ParsedWorklogEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


TEMPO_LINE_REGEX = re.compile(
    r"^Tempo:\s*([^\s|]+)\s*\|\s*(\d{1,2}:\d{2})\s*[-\u2013\u2014]\s*(\d{1,2}:\d{2})\s*$",
    re.IGNORECASE,
)
DATE_HEADING_REGEX = re.compile(r"^#+\s*(\d{4}-\d{2}-\d{2})")


def parse_markdown_worklog(content: str) -> WorklogParseResult:
    """Parse a markdown worklog document into worklog entries and errors."""
    result = WorklogParseResult()
    current_date: str | None = None
    current_entry: ParsedWorklogEntry | None = None
    description_bullets: list[str] = []

    lines = content.splitlines()

    def finalize_current():
        nonlocal current_entry, description_bullets
        if current_entry:
            if description_bullets:
                current_entry.description = "\n".join(description_bullets)
            if not current_entry.is_skip:
                result.entries.append(current_entry)
            current_entry = None
            description_bullets = []

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Check date heading ## YYYY-MM-DD
        date_match = DATE_HEADING_REGEX.match(stripped)
        if date_match:
            finalize_current()
            dt_str = date_match.group(1)
            try:
                datetime.strptime(dt_str, "%Y-%m-%d")
                current_date = dt_str
            except ValueError:
                result.errors.append(
                    f"Line {idx}: Invalid date format '{dt_str}'. Expected YYYY-MM-DD."
                )
                current_date = None
            continue

        # Check Tempo: line
        if stripped.lower().startswith("tempo:"):
            finalize_current()
            if not current_date:
                result.errors.append(
                    f"Line {idx}: 'Tempo:' entry found before any valid '## YYYY-MM-DD' date heading."
                )
                continue

            if stripped.lower().replace(" ", "") in ("tempo:skip", "tempo:skip|"):
                current_entry = ParsedWorklogEntry(
                    date=current_date,
                    issue="skip",
                    start_time="00:00:00",
                    end_time="00:00:00",
                    hours=0.0,
                    description="",
                    line_number=idx,
                    is_skip=True,
                )
                continue

            match = TEMPO_LINE_REGEX.match(stripped)
            if not match:
                result.errors.append(
                    f"Line {idx}: Malformed Tempo line '{stripped}'. Expected format 'Tempo: KEY | HH:MM-HH:MM'."
                )
                continue

            issue_key = match.group(1).strip()
            start_t = match.group(2).strip()
            end_t = match.group(3).strip()

            try:
                sh, sm = map(int, start_t.split(":"))
                eh, em = map(int, end_t.split(":"))
                start_mins = sh * 60 + sm
                end_mins = eh * 60 + em
                if end_mins <= start_mins:
                    result.errors.append(
                        f"Line {idx}: End time ({end_t}) must be at or after start time ({start_t})."
                    )
                    continue
                hours = (end_mins - start_mins) / 60.0
            except ValueError:
                result.errors.append(f"Line {idx}: Invalid time range '{start_t}-{end_t}'.")
                continue

            is_skip = issue_key.lower() == "skip"
            current_entry = ParsedWorklogEntry(
                date=current_date,
                issue=issue_key,
                start_time=f"{sh:02d}:{sm:02d}:00",
                end_time=f"{eh:02d}:{em:02d}:00",
                hours=hours,
                description="",
                line_number=idx,
                is_skip=is_skip,
            )
            continue

        # Check description bullets under an active Tempo entry
        if current_entry:
            if stripped.startswith("- "):
                description_bullets.append(stripped)
                continue
            elif stripped == "" or stripped.startswith("#"):
                finalize_current()

    finalize_current()
    return result
