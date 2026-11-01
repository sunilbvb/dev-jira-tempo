"""CLI handler for `tempo-log schedule` command.

Builds an optimized timeline for a day's worklog without overlaps,
supporting break reservation, 15-minute rounding, and daily cap checks.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date as dt_date
from pathlib import Path
from typing import Any

from ..config import Settings
from ..schedule import Item, ScheduleConfig, ScheduleError, build_day, format_clock, parse_clock, round_up
from ..service import TempoService
from ..worklog_import import parse_blocks, merge_by_issue

logger = logging.getLogger(__name__)


def run_schedule(args: argparse.Namespace, target: Settings | TempoService | None = None) -> int:
    """Build and display a day schedule from a worklog or journal file."""
    path = Path(args.file)
    if not path.is_file():
        logger.error("Schedule source file not found: %s", args.file)
        return 1

    content = path.read_text(encoding="utf-8")
    target_date = getattr(args, "date", None) or dt_date.today().isoformat()

    # Parse blocks using worklog_import
    blocks = parse_blocks(content, target_date)
    if not blocks:
        # Try finding any blocks if target_date has none
        logger.warning("No blocks found matching date %s in %s", target_date, args.file)
        if getattr(args, "json", False):
            print(json.dumps({"error": "No worklog blocks found for date", "date": target_date}))
        else:
            print(f"No worklog blocks found for date: {target_date}")
        return 0

    merged = merge_by_issue(blocks)
    step = getattr(args, "round_minutes", None) or 15
    cap = getattr(args, "cap_hours", None) or 12

    items: list[Item] = []
    for m in merged:
        issue_ref = m.issue or "UNASSIGNED"
        rounded_mins = round_up(m.minutes, step)
        desc = m.description()
        items.append(
            Item(
                issue=issue_ref,
                minutes=rounded_mins,
                description=desc.strip(),
                fixed_start=m.fixed_start if m.fixed_start is not None else None,
            )
        )

    # Schedule Configuration
    start_time = getattr(args, "start", None) or "09:00"
    config = ScheduleConfig(
        start_candidates=(start_time,),
        round_minutes=step,
        max_day_minutes=int(cap * 60),
        break_issue=getattr(args, "break_issue", None),
        break_start=getattr(args, "break_start", None) or "13:00",
        break_minutes=getattr(args, "break_minutes", None) or 60,
        break_description=getattr(args, "break_desc", None) or "Lunch:\n- Lunch break",
    )

    reserved_slots: list[tuple[int, int]] = []
    if getattr(args, "reserve", None):
        for slot in args.reserve:
            try:
                s_str, e_str = slot.split("-", 1)
                reserved_slots.append((parse_clock(s_str.strip()), parse_clock(e_str.strip())))
            except Exception as exc:
                logger.warning("Could not parse reserved slot '%s': %s", slot, exc)

    try:
        scheduled = build_day(items, config, reserved=reserved_slots if reserved_slots else None)
    except ScheduleError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(exc), "status": "FAILED"}))
        else:
            print(f"Scheduling Error: {exc}")
        return 1

    if getattr(args, "json", False):
        out = {
            "date": target_date,
            "total_minutes": sum(i.minutes for i in scheduled),
            "total_hours": sum(i.minutes for i in scheduled) / 60,
            "items": [
                {
                    "issue": str(i.issue),
                    "minutes": i.minutes,
                    "hours": i.hours,
                    "start": format_clock(i.start)[:5] if i.start is not None else None,
                    "end": format_clock(i.start + i.minutes)[:5] if i.start is not None else None,
                    "description": i.description,
                }
                for i in scheduled
            ],
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"\nPlanned Day Schedule for {target_date}:")
    print("=" * 68)
    print(f"{'TIME':<13} {'ISSUE':<14} {'HOURS':<8} {'TITLE'}")
    print("-" * 68)
    for i in scheduled:
        start_fmt = format_clock(i.start)[:5] if i.start is not None else "--:--"
        end_fmt = format_clock(i.start + i.minutes)[:5] if i.start is not None else "--:--"
        first_line = i.description.splitlines()[0] if i.description else "(no description)"
        print(f"{start_fmt}-{end_fmt}   {str(i.issue):<14} {i.hours:<8.2f} {first_line[:30]}")

    tot_mins = sum(i.minutes for i in scheduled)
    print("=" * 68)
    print(f"Total: {tot_mins / 60:.2f}h across {len(scheduled)} items.\n")
    return 0
