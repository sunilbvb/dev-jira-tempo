"""CLI subcommand handlers for worklogs (create, list, update, batch, from-worklog, doctor)."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from ..config import Settings
from ..exceptions import TempoLogError
from ..journal import journal_path
from ..safety import find_duplicates, round_duration, validate_submission_safety
from ..service import TempoService


def _get_service(target: Settings | TempoService) -> TempoService:
    if isinstance(target, Settings):
        return TempoService.from_settings(target)
    return target
from ..worklog_parser import parse_markdown_worklog

logger = logging.getLogger(__name__)


def run_create(args: argparse.Namespace, target: Settings | TempoService) -> int:
    service = _get_service(target)
    log_kwargs: dict[str, Any] = {
        "hours": args.hours,
        "date": args.date,
        "time": args.time,
        "description": args.description,
        "account_id": args.account_id,
    }
    if args.issue_id is not None:
        log_kwargs["issue_id"] = args.issue_id
    if args.issue:
        log_kwargs["issue"] = args.issue

    try:
        resolved_issue_id, _ = service.resolve_issue_and_account(
            issue=args.issue, issue_id=args.issue_id, account_id=args.account_id
        )
        if args.issue_id:
            log_kwargs["issue_id"] = args.issue_id
        if args.issue:
            log_kwargs["issue"] = args.issue
        result = service.log_time(**log_kwargs)
    except (TempoLogError, ValueError) as exc:
        logger.error(str(exc))
        return 1

    worklog_id = result.get("tempoWorklogId")
    print(f"Logged {args.hours}h on issue {resolved_issue_id}. Tempo worklog ID: {worklog_id}")
    return 0


def run_list(args: argparse.Namespace, target: Settings | TempoService) -> int:
    service = _get_service(target)
    try:
        result = service.list_time(
            account_id=args.account_id,
            from_date=args.from_date,
            to_date=args.to_date,
            limit=args.limit,
            offset=args.offset,
        )
    except (TempoLogError, ValueError) as exc:
        logger.error(str(exc))
        return 1

    results = result.get("results", result.get("worklogs", []))
    if not results:
        print("No worklogs found.")
        return 0

    for entry in results:
        issue_id = entry.get("issue", {}).get("id")
        hours = entry.get("timeSpentSeconds", 0) / 3600
        print(
            f"{entry.get('tempoWorklogId')}\t{entry.get('startDate')} "
            f"{entry.get('startTime')}\tissue={issue_id}\t{hours}h\t"
            f"{entry.get('description', '')}"
        )
    total = result.get("metadata", {}).get("count", len(results))
    print(f"\n{total} worklog(s) shown (limit={args.limit}, offset={args.offset}).")
    return 0


def run_update(args: argparse.Namespace, target: Settings | TempoService) -> int:
    service = _get_service(target)
    try:
        service.update_time(
            args.worklog_id,
            hours=args.hours,
            description=args.description,
            date=args.date,
            time=args.time,
        )
        print(f"Successfully updated worklog {args.worklog_id}.")
        return 0
    except (TempoLogError, ValueError) as exc:
        logger.error(str(exc))
        return 1


def run_batch(args: argparse.Namespace, target: Settings | TempoService) -> int:
    try:
        with open(args.file, encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read %s: %s", args.file, exc)
        return 1

    if not isinstance(entries, list):
        logger.error("Batch file must contain a JSON list of entries.")
        return 1

    service = _get_service(target)
    allow_dups = getattr(args, "allow_duplicates", False)
    dry_run_flag = getattr(args, "dry_run", False)
    rollback_flag = getattr(args, "rollback_on_error", False)
    stop_err_flag = getattr(args, "stop_on_error", False)

    succeeded, failed, failures = service.batch_log(
        entries,
        stop_on_error=stop_err_flag,
        allow_duplicates=allow_dups,
        dry_run=dry_run_flag,
        rollback_on_error=rollback_flag,
    )

    print(f"\n{succeeded} succeeded, {failed} failed.")
    if failures:
        print("Failures:")
        for line in failures:
            print(f"  - {line}")
    print(f"Journal: {journal_path()}")
    return 1 if failed else 0


def run_from_worklog(args: argparse.Namespace, target: Settings | TempoService) -> int:
    path = Path(args.file)
    if not path.exists():
        logger.error("Worklog file not found: %s", args.file)
        return 1

    content = path.read_text(encoding="utf-8")
    parse_result = parse_markdown_worklog(content)

    if parse_result.errors:
        print("Parse Errors:")
        for err in parse_result.errors:
            print(f"  - {err}")

    filtered = parse_result.entries
    if getattr(args, "from_date", None):
        filtered = [e for e in filtered if e.date >= args.from_date]
    if getattr(args, "to_date", None):
        filtered = [e for e in filtered if e.date <= args.to_date]

    if not filtered:
        print("No matching worklog entries found in specified date range.")
        return 0

    service = _get_service(target)
    round_mins = service.settings.tempo_round_minutes if service.settings else None
    daily_cap = service.settings.tempo_daily_cap_hours if service.settings else None

    candidate_entries: list[dict[str, Any]] = []
    resolution_errors: list[str] = []

    for entry in filtered:
        orig_hours = entry.hours
        rounded_hours = round_duration(orig_hours, round_mins)

        resolved_issue_key = entry.issue
        issue_id = None
        try:
            resolved_id, _ = service.resolve_issue_and_account(issue=entry.issue)
            issue_id = resolved_id
        except Exception as exc:
            resolution_errors.append(f"Line {entry.line_number} [{entry.date} {entry.issue}]: {exc}")

        candidate_entries.append(
            {
                "date": entry.date,
                "time": entry.start_time,
                "issue": resolved_issue_key,
                "issue_id": issue_id,
                "orig_hours": orig_hours,
                "hours": rounded_hours,
                "description": entry.description,
                "line_number": entry.line_number,
            }
        )

    existing_worklogs: list[dict[str, Any]] = []
    if candidate_entries:
        min_date = min(e["date"] for e in candidate_entries)
        max_date = max(e["date"] for e in candidate_entries)
        try:
            acc_id = service.default_account_id
            if not acc_id and service.jira_client:
                acc_id = service.jira_client.get_current_account_id()
            if acc_id:
                res = service.list_time(account_id=acc_id, from_date=min_date, to_date=max_date, limit=1000)
                existing_worklogs = res.get("results", res.get("worklogs", []))
                if isinstance(res, list):
                    existing_worklogs = res
        except Exception as exc:
            logger.warning("Could not fetch existing worklogs: %s", exc)

    allow_dups = getattr(args, "allow_duplicates", False)
    if allow_dups:
        unique_entries = candidate_entries
        duplicate_entries: list[dict[str, Any]] = []
    else:
        unique_entries, duplicate_entries = find_duplicates(candidate_entries, existing_worklogs)

    warnings = validate_submission_safety(candidate_entries, existing_worklogs, daily_cap)

    print("\n--- Worklog Import Preview ---")
    print(f"{'Date':<12} {'Issue':<12} {'Time':<10} {'Hours (Orig -> Round)':<22} {'Status'}")
    print("-" * 75)

    for entry in candidate_entries:
        is_dup = entry in duplicate_entries
        status = "DUPLICATE (skip)" if is_dup else ("ERROR" if entry["issue_id"] is None else "READY")
        hours_str = f"{entry['orig_hours']:.2f}h"
        if entry["hours"] != entry["orig_hours"]:
            hours_str += f" -> {entry['hours']:.2f}h"

        print(f"{entry['date']:<12} {entry['issue']:<12} {entry['time'][:5]:<10} {hours_str:<22} {status}")

    if duplicate_entries:
        print(f"\nSkipped {len(duplicate_entries)} duplicate entry/entries (use --allow-duplicates to submit anyway).")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  [WARN] {w}")

    if resolution_errors:
        print("\nErrors:")
        for err in resolution_errors:
            print(f"  [ERROR] {err}")

    if not getattr(args, "submit", False):
        print("\nPreview mode complete. Re-run with --submit to log hours to Tempo.")
        return 0

    if resolution_errors:
        logger.error("Cannot submit worklog with unresolvable issue keys.")
        return 1

    if warnings and getattr(args, "strict", False):
        logger.error("Submission blocked by --strict due to safety warnings.")
        return 1

    if not unique_entries:
        print("No new entries to submit.")
        return 0

    print(f"\nSubmitting {len(unique_entries)} worklog entry/entries to Tempo...")
    dry_run_flag = getattr(args, "dry_run", False)
    rollback_flag = getattr(args, "rollback_on_error", False)
    succeeded, failed, failures = service.batch_log(
        unique_entries,
        stop_on_error=False,
        allow_duplicates=True,
        dry_run=dry_run_flag,
        rollback_on_error=rollback_flag,
    )

    print(f"\nResult: {succeeded} succeeded, {failed} failed.")
    if failures:
        for f in failures:
            print(f"  - {f}")
        return 1

    return 0


def run_doctor(target: Settings | TempoService) -> int:
    service = _get_service(target)
    report = service.check_health()

    if report["tempo_ok"]:
        print("Tempo: OK (TEMPO_API_TOKEN authenticates).")
    else:
        print(f"Tempo: FAILED - {report['tempo_message']}")

    if report["jira_ok"] is True:
        print(f"Jira: OK ({report['jira_message']}).")
    elif report["jira_ok"] is False:
        print(f"Jira: FAILED - {report['jira_message']}")
    else:
        print("Jira: not configured (JIRA_BASE_URL/JIRA_EMAIL/JIRA_API_TOKEN unset).")

    if report["default_account_id"]:
        print(f"JIRA_ACCOUNT_ID: set ({report['default_account_id']}).")
    else:
        print("JIRA_ACCOUNT_ID: not set.")

    ok = report["tempo_ok"] and (report["jira_ok"] is not False)
    return 0 if ok else 1
