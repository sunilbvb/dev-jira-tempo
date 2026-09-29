"""CLI handler for 'analyze': read-only pre-submission report for a journal day, or submit."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from datetime import date as date_cls
from pathlib import Path
from typing import Any

from ..config import Settings
from ..issue_cache import IssueCache
from ..journal_analyzer import (
    AnalysisReport,
    PlannedEntry,
    _fmt_minutes,
    analyze_day,
    format_report,
    parse_fixed_blocks,
    parse_journal,
)
from ..service import TempoService

logger = logging.getLogger(__name__)


def _make_resolver(service: TempoService | None, offline: bool):
    cache = IssueCache()
    jira = service.jira_client if service is not None else None

    def resolve(key: str) -> int | None:
        cached = cache.get(key)
        if cached is not None:
            return cached
        if offline or jira is None:
            return None
        return jira.resolve_issue_id(key)

    return resolve


def run_analyze(args: argparse.Namespace, target: Settings | TempoService | None) -> int:
    path = Path(args.file).expanduser()
    if not path.exists():
        logger.error("Journal file not found: %s", args.file)
        return 1

    service = TempoService.from_settings(target) if isinstance(target, Settings) else target
    settings = service.settings if service is not None else None

    round_mins = args.round_minutes if args.round_minutes is not None else (
        settings.tempo_round_minutes
        if settings and isinstance(settings.tempo_round_minutes, int)
        else 15
    )
    cap = args.cap if args.cap is not None else (
        settings.tempo_daily_cap_hours
        if settings and isinstance(settings.tempo_daily_cap_hours, (int, float))
        else None
    )

    heading_time = getattr(args, "heading_time", None) or (
        settings.tempo_heading_time
        if settings and isinstance(settings.tempo_heading_time, str)
        else "start"
    )
    meeting_prefix = (
        settings.tempo_meeting_prefix
        if settings and isinstance(settings.tempo_meeting_prefix, str)
        else "Meeting:"
    )
    meeting_issue = getattr(args, "meeting_issue", None) or (
        settings.tempo_meeting_issue
        if settings and isinstance(settings.tempo_meeting_issue, str)
        else None
    )
    fixed_blocks_conf = (
        settings.tempo_fixed_blocks
        if settings and isinstance(settings.tempo_fixed_blocks, str)
        else None
    )
    fixed_blocks = parse_fixed_blocks(fixed_blocks_conf)
    with_fixed_blocks = bool(getattr(args, "with_fixed_blocks", False))
    duplicate_window = (
        settings.tempo_duplicate_window_minutes
        if settings and isinstance(settings.tempo_duplicate_window_minutes, int)
        else 15
    )
    drop_patterns = (
        settings.tempo_description_drop_patterns
        if settings and isinstance(settings.tempo_description_drop_patterns, list)
        else None
    )
    max_bullets = (
        settings.tempo_description_max_bullets
        if settings and isinstance(settings.tempo_description_max_bullets, int)
        else 4
    )
    consolidate = getattr(args, "consolidate", None)
    allow_overlap = bool(getattr(args, "allow_overlap", False))
    trim = bool(getattr(args, "trim", False))

    entries = parse_journal(
        path.read_text(encoding="utf-8"),
        heading_time_mode=heading_time,
        meeting_prefix=meeting_prefix,
    )

    # Determine dates to analyze
    if getattr(args, "all_dates", False):
        dates_to_analyze = sorted(set(e.date for e in entries if e.date))
    elif args.date and ".." in args.date:
        start_d, end_d = args.date.split("..", 1)
        start_d, end_d = start_d.strip(), end_d.strip()
        dates_to_analyze = sorted(set(e.date for e in entries if e.date and start_d <= e.date <= end_d))
    else:
        dates_to_analyze = [args.date or date_cls.today().isoformat()]

    if not dates_to_analyze:
        logger.error("No dates found to analyze.")
        return 1

    reports: list[AnalysisReport] = []
    has_errors = False

    for day in dates_to_analyze:
        existing: list[dict[str, Any]] = []
        if service is not None and not args.offline:
            try:
                acc = service.default_account_id
                if not acc and service.jira_client:
                    acc = service.jira_client.get_current_account_id()
                if acc:
                    res = service.list_time(account_id=acc, from_date=day, to_date=day, limit=1000)
                    existing = res if isinstance(res, list) else res.get("results", res.get("worklogs", []))
            except Exception as exc:  # noqa: BLE001 - analysis still useful without it
                logger.warning("Could not fetch existing Tempo worklogs for %s: %s", day, exc)

        rep = analyze_day(
            entries,
            day,
            round_minutes=round_mins,
            daily_cap_hours=cap,
            resolver=_make_resolver(service, args.offline),
            can_lookup=bool(service is not None and service.jira_client is not None and not args.offline),
            existing_worklogs=existing,
            sequential=args.sequential,
            reserved=[tuple(r.split("-", 1)) for r in (args.reserve or [])],
            consolidate=consolidate,
            heading_time=heading_time,
            meeting_issue=meeting_issue,
            fixed_blocks=fixed_blocks,
            with_fixed_blocks=with_fixed_blocks,
            duplicate_window_minutes=duplicate_window,
            allow_overlap=allow_overlap,
            drop_patterns=drop_patterns,
            max_bullets=max_bullets,
            trim=trim,
        )
        reports.append(rep)
        if rep.blocked or rep.day_warnings:
            has_errors = True

    if args.json:
        payloads = [
            {
                "date": rep.date,
                "total_minutes": rep.total_minutes,
                "ready_minutes": rep.ready_minutes,
                "existing_minutes": rep.existing_minutes,
                "cap_hours": rep.cap_hours,
                "entries": [
                    {
                        **asdict(p.entry),
                        "status": p.status,
                        "rounded_minutes": p.rounded_minutes,
                        "planned_start": p.start,
                        "problems": p.problems,
                        "notes": p.notes,
                        "is_logged": p.is_logged,
                    }
                    for p in rep.planned
                ],
                "day_warnings": rep.day_warnings,
                "day_info": rep.day_info,
                "next_steps": rep.next_steps,
            }
            for rep in reports
        ]
        print(json.dumps(payloads if len(payloads) > 1 else payloads[0], indent=2))
    else:
        for rep in reports:
            print(format_report(rep))
            if len(reports) > 1:
                print("\n" + "=" * 80 + "\n")

    all_ready: list[PlannedEntry] = [p for rep in reports for p in rep.ready]
    all_blocked: list[PlannedEntry] = [p for rep in reports for p in rep.blocked if not p.is_logged]

    if args.export:
        ready_payload = [p.to_batch() for p in all_ready]
        Path(args.export).write_text(json.dumps(ready_payload, indent=2), encoding="utf-8")
        print(
            f"\nExported {len(ready_payload)} READY entr{'y' if len(ready_payload) == 1 else 'ies'} to {args.export} "
            f"(blocked entries left out). Upload with: tempo-log batch {args.export} --dry-run"
        )

    if getattr(args, "submit", False):
        if args.offline or service is None:
            logger.error("--submit requires online access and Tempo credentials.")
            return 1

        if all_blocked:
            logger.error(
                "Cannot submit: %d entry/entries are BLOCKED. Fix them or remove them before submitting.",
                len(all_blocked),
            )
            return 1

        if not all_ready:
            print("\nNothing to upload. All entries are already logged or skipped.")
            return 0

        total_mins = sum(p.rounded_minutes or 0 for p in all_ready)
        day_count_str = f" across {len(reports)} days" if len(reports) > 1 else ""
        print(
            f"\nPlan: {len(all_ready)} entr{'y' if len(all_ready) == 1 else 'ies'} "
            f"({_fmt_minutes(total_mins)}){day_count_str} ready to upload."
        )

        if not getattr(args, "yes", False):
            try:
                confirm = input(f"Upload {len(all_ready)} entries to Tempo? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "n"
            if confirm not in ("y", "yes"):
                print("Submission cancelled.")
                return 0

        batch_payload = [p.to_batch() for p in all_ready]
        succeeded, failed, failures = service.batch_log(
            batch_payload,
            stop_on_error=True,
            rollback_on_error=True,
            allow_duplicates=True,
        )
        if failed > 0:
            logger.error(
                "Submission failed (%d succeeded, %d failed - rolled back): %s",
                succeeded,
                failed,
                failures,
            )
            return 1

        print(f"\nSuccessfully uploaded {succeeded} worklog(s) to Tempo.")

    return 1 if (args.strict and has_errors) else 0
