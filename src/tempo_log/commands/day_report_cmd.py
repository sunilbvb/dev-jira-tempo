"""CLI handler for `tempo-log day-report` command.

Audits one day of worklogs (from Tempo API or journal file), detecting gaps,
overlaps, off-step durations, and 12h cap violations using day_report.py.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date as dt_date
from pathlib import Path
from typing import Any

from ..config import Settings
from ..day_report import DayEntry, analyse, render
from ..schedule import parse_clock
from ..service import TempoService
from ..worklog_parser import parse_markdown_worklog

logger = logging.getLogger(__name__)


def _get_service(target: Settings | TempoService | None) -> TempoService | None:
    if isinstance(target, TempoService):
        return target
    if isinstance(target, Settings):
        return TempoService(target)
    return None


def run_day_report(args: argparse.Namespace, target: Settings | TempoService | None = None) -> int:
    """Analyze and render day audit for worklog timeline."""
    target_date = getattr(args, "date", None) or dt_date.today().isoformat()
    service = _get_service(target)
    round_minutes = getattr(args, "round_minutes", None) or (
        service.settings.tempo_round_minutes if service and service.settings else 15
    )
    cap_hours = getattr(args, "cap_hours", None) or (
        service.settings.tempo_daily_cap_hours if service and service.settings else 12.0
    )
    max_day_minutes = int(cap_hours * 60)

    entries: list[DayEntry] = []

    # Source 1: file provided
    file_path = getattr(args, "file", None)
    if file_path:
        p = Path(file_path)
        if not p.is_file():
            logger.error("Day-report source file not found: %s", file_path)
            return 1
        content = p.read_text(encoding="utf-8")
        from ..worklog_import import parse_blocks
        blocks = parse_blocks(content, target_date)
        if blocks:
            for idx, b in enumerate(blocks, 1):
                start_m = b.start_minute if b.start_minute is not None else (idx * 30 + 540)
                entries.append(
                    DayEntry(
                        worklog_id=idx,
                        start=start_m,
                        minutes=b.minutes,
                        issue=str(b.issue or "UNASSIGNED"),
                        title=b.title,
                    )
                )
        else:
            parsed = parse_markdown_worklog(content)
            day_entries = [e for e in parsed.entries if e.date == target_date]
            for idx, e in enumerate(day_entries, 1):
                start_m = parse_clock(e.start_time) if e.start_time else (idx * 30 + 540)
                mins = int(round(e.hours * 60))
                entries.append(
                    DayEntry(
                        worklog_id=idx,
                        start=start_m,
                        minutes=mins,
                        issue=e.issue,
                        title=e.description.splitlines()[0] if e.description else "",
                    )
                )
    else:
        # Source 2: fetch from Tempo API if service available
        if service and service.tempo_client:
            try:
                worklogs = service.tempo_client.list_worklogs(from_date=target_date, to_date=target_date)
                for w in worklogs:
                    start_str = w.get("startTime", "09:00:00")
                    start_m = parse_clock(start_str[:5])
                    sec = w.get("timeSpentSeconds", 0)
                    mins = sec // 60
                    issue_info = w.get("issue", {})
                    issue_key = issue_info.get("key") or str(issue_info.get("id", "UNKNOWN"))
                    desc = w.get("description", "")
                    entries.append(
                        DayEntry(
                            worklog_id=w.get("tempoWorklogId", 0),
                            start=start_m,
                            minutes=mins,
                            issue=issue_key,
                            title=desc.splitlines()[0] if desc else "",
                        )
                    )
            except Exception as exc:
                logger.warning("Could not fetch remote worklogs from Tempo: %s", exc)

    if not entries:
        if getattr(args, "json", False):
            print(json.dumps({"date": target_date, "entries": [], "total_minutes": 0, "message": "No entries found"}))
        else:
            print(f"No worklog entries found for {target_date}.")
        return 0

    report = analyse(entries, round_minutes=round_minutes, max_day_minutes=max_day_minutes)

    if getattr(args, "json", False):
        json_out = {
            "date": target_date,
            "total_minutes": report["total_minutes"],
            "total_hours": report["total_minutes"] / 60,
            "over_cap": report["over_cap"],
            "overlaps_count": len(report["overlaps"]),
            "gaps_count": len(report["gaps"]),
            "off_step_count": len(report["off_step"]),
            "entries": [
                {
                    "worklog_id": e.worklog_id,
                    "start": e.start,
                    "minutes": e.minutes,
                    "issue": e.issue,
                    "title": e.title,
                }
                for e in report["entries"]
            ],
            "gaps": [{"start": g[0], "end": g[1], "minutes": g[1] - g[0]} for g in report["gaps"]],
        }
        print(json.dumps(json_out, indent=2))
        return 0

    rendered_lines = render(report, max_day_minutes=max_day_minutes)
    print(f"\n--- Day Audit Report for {target_date} ---")
    for line in rendered_lines:
        print(line)
    print("------------------------------------------\n")
    return 0
