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

    day = args.date or date_cls.today().isoformat()
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
            logger.warning("Could not fetch existing Tempo worklogs: %s", exc)

    entries = parse_journal(
        path.read_text(encoding="utf-8"),
        heading_time_mode=heading_time,
        meeting_prefix=meeting_prefix,
    )
    report = analyze_day(
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
    )

    if args.json:
        payload = {
            "date": report.date,
            "total_minutes": report.total_minutes,
            "existing_minutes": report.existing_minutes,
            "cap_hours": report.cap_hours,
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
                for p in report.planned
            ],
            "day_warnings": report.day_warnings,
            "day_info": report.day_info,
            "next_steps": report.next_steps,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(report))

    if args.export:
        ready = [p.to_batch() for p in report.ready]
        Path(args.export).write_text(json.dumps(ready, indent=2), encoding="utf-8")
        print(
            f"\nExported {len(ready)} READY entr{'y' if len(ready) == 1 else 'ies'} to {args.export} "
            f"(blocked entries left out). Upload with: tempo-log batch {args.export} --dry-run"
        )

    if getattr(args, "submit", False):
        if args.offline or service is None:
            logger.error("--submit requires online access and Tempo credentials.")
            return 1

        active_blocked = [p for p in report.blocked if not p.is_logged]
        if active_blocked:
            logger.error(
                "Cannot submit: %d entry/entries are BLOCKED. Fix them or remove them before submitting.",
                len(active_blocked),
            )
            return 1

        to_upload = report.ready
        if not to_upload:
            print("\nNothing to upload. All entries are already logged or skipped.")
            return 0

        print(
            f"\nPlan: {len(to_upload)} entr{'y' if len(to_upload) == 1 else 'ies'} "
            f"({_fmt_minutes(sum(p.rounded_minutes or 0 for p in to_upload))}) ready to upload."
        )

        if not getattr(args, "yes", False):
            try:
                confirm = input(f"Upload {len(to_upload)} entries to Tempo? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "n"
            if confirm not in ("y", "yes"):
                print("Submission cancelled.")
                return 0

        batch_payload = [p.to_batch() for p in to_upload]
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

    return 1 if (args.strict and (report.blocked or report.day_warnings)) else 0
