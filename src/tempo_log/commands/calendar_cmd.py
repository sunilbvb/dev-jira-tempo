"""CLI handler for `tempo-log calendar` command.

Parses iCalendar (.ics) files, listing meetings or exporting them as fixed blocks.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from ..calendar_sync import parse_ics_file

logger = logging.getLogger(__name__)


def run_calendar(args: argparse.Namespace, target: Any = None) -> int:
    """Execute calendar command: parse and format .ics events."""
    file_path = args.file
    target_date = getattr(args, "date", None)
    issue_key = getattr(args, "issue_key", None) or "MEETING"

    try:
        events = parse_ics_file(file_path, target_date=target_date)
    except Exception as exc:
        logger.error("Could not parse calendar file: %s", exc)
        return 1

    if getattr(args, "as_fixed_blocks", False):
        blocks = [e.to_fixed_block(issue_key=issue_key) for e in events]
        joined = ";".join(blocks)
        if getattr(args, "json", False):
            print(json.dumps({"fixed_blocks": joined, "blocks": blocks}))
        else:
            print(joined)
        return 0

    if getattr(args, "json", False):
        out = [
            {
                "summary": e.summary,
                "date": e.date_str,
                "start": e.start_clock,
                "end": e.end_clock,
                "duration_minutes": e.duration_minutes,
                "status": e.status,
            }
            for e in events
        ]
        print(json.dumps(out, indent=2))
        return 0

    print(f"\nFound {len(events)} Calendar Events" + (f" for {target_date}" if target_date else "") + ":")
    print("=" * 65)
    print(f"{'DATE':<12} {'TIME':<13} {'MIN':<6} {'STATUS':<11} {'SUMMARY'}")
    print("-" * 65)
    for e in events:
        print(f"{e.date_str:<12} {e.start_clock}-{e.end_clock}   {e.duration_minutes:<6} {e.status:<11} {e.summary[:30]}")
    print("=" * 65 + "\n")
    return 0
