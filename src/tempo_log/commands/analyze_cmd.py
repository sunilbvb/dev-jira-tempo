"""CLI handler for 'analyze': read-only pre-submission report for a journal day."""

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
from ..journal_analyzer import analyze_day, format_report, parse_journal
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
        settings.tempo_round_minutes if settings and settings.tempo_round_minutes else 15
    )
    cap = args.cap if args.cap is not None else (settings.tempo_daily_cap_hours if settings else None)

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

    entries = parse_journal(path.read_text(encoding="utf-8"))
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
    )

    if args.json:
        payload = {
            "date": report.date,
            "total_minutes": report.total_minutes,
            "existing_minutes": report.existing_minutes,
            "cap_hours": report.cap_hours,
            "entries": [
                {**asdict(p.entry), "status": p.status, "rounded_minutes": p.rounded_minutes,
                 "planned_start": p.start, "problems": p.problems, "notes": p.notes}
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
        print(f"\nExported {len(ready)} READY entr{'y' if len(ready) == 1 else 'ies'} to {args.export} "
              f"(blocked entries left out). Upload with: tempo-log batch {args.export} --dry-run")

    return 1 if (args.strict and (report.blocked or report.day_warnings)) else 0
