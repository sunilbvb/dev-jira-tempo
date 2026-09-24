"""Command-line entry point for managing Tempo worklogs."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from .config import ConfigError, Settings, load_settings
from .exceptions import TempoLogError
from .journal import journal_path
from .service import TempoService

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tempo-log", description="Manage Tempo (Jira time-tracking) worklogs."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Log new time to Tempo.")
    issue_group = create_parser.add_mutually_exclusive_group(required=True)
    issue_group.add_argument(
        "--issue", help="Issue key, e.g. PROJ-123 (requires JIRA_* env vars)."
    )
    issue_group.add_argument(
        "--issue-id", type=int, help="Numeric Jira issue id (skips Jira lookup)."
    )
    create_parser.add_argument(
        "--account-id", help="Jira accountId (skips Jira lookup for the author)."
    )
    create_parser.add_argument(
        "--hours", type=float, required=True, help="Hours to log, e.g. 2.5."
    )
    create_parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Worklog date as YYYY-MM-DD (default: today).",
    )
    create_parser.add_argument(
        "--time",
        default=datetime.now().strftime("%H:%M:%S"),
        help="Worklog start time as HH:MM:SS (default: now).",
    )
    create_parser.add_argument("--description", default="", help="Worklog description.")

    list_parser = subparsers.add_parser("list", help="List existing worklogs.")
    list_parser.add_argument(
        "--account-id", help="Jira accountId to list worklogs for (default: JIRA_ACCOUNT_ID)."
    )
    list_parser.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD.")
    list_parser.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD.")
    list_parser.add_argument("--limit", type=int, default=50, help="Max results (default 50).")
    list_parser.add_argument("--offset", type=int, default=0, help="Pagination offset.")

    update_parser = subparsers.add_parser("update", help="Update an existing worklog.")
    update_parser.add_argument("worklog_id", type=int, help="Numeric Tempo worklog ID.")
    update_parser.add_argument("--hours", type=float, help="New hours value.")
    update_parser.add_argument("--description", help="New description.")
    update_parser.add_argument("--date", help="New start date YYYY-MM-DD.")
    update_parser.add_argument("--time", help="New start time HH:MM:SS.")

    batch_parser = subparsers.add_parser(
        "batch",
        help="Create many worklogs from a JSON file in one process.",
        description=(
            "JSON file: a list of objects, each with issue_id (int) or issue (key), "
            "hours (float), date (YYYY-MM-DD), time (HH:MM:SS, optional), "
            "description (optional), account_id (optional, falls back to "
            "JIRA_ACCOUNT_ID)."
        ),
    )
    batch_parser.add_argument("file", help="Path to a JSON file of worklog entries.")
    batch_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Abort the batch on the first failed entry (default: continue).",
    )

    subparsers.add_parser(
        "doctor", help="Check that Tempo (and Jira, if configured) credentials work."
    )

    return parser


def _get_service(target: Settings | TempoService) -> Any:
    if isinstance(target, Settings):
        return TempoService.from_settings(target)
    return target


def run_create(args: argparse.Namespace, target: Settings | TempoService) -> int:
    if args.hours <= 0:
        logger.error("Hours must be a positive number, got %s", args.hours)
        return 1

    service = _get_service(target)
    try:
        issue_id, account_id = service.resolve_issue_and_account(
            issue=args.issue, issue_id=args.issue_id, account_id=args.account_id
        )
        result = service.log_time(
            hours=args.hours,
            issue_id=issue_id,
            account_id=account_id,
            date=args.date,
            time=args.time,
            description=args.description,
        )
    except (TempoLogError, ValueError) as exc:
        logger.error(str(exc))
        return 1

    worklog_id = result.get("tempoWorklogId")
    print(f"Logged {args.hours}h on issue {issue_id}. Tempo worklog ID: {worklog_id}")
    return 0


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
    succeeded, failed, failures = service.batch_log(
        entries, stop_on_error=args.stop_on_error
    )

    print(f"\n{succeeded} succeeded, {failed} failed.")
    if failures:
        print("Failures:")
        for line in failures:
            print(f"  - {line}")
    print(f"Journal: {journal_path()}")
    return 1 if failed else 0


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

    for entry in result.get("results", []):
        issue_id = entry.get("issue", {}).get("id")
        hours = entry.get("timeSpentSeconds", 0) / 3600
        print(
            f"{entry.get('tempoWorklogId')}\t{entry.get('startDate')} "
            f"{entry.get('startTime')}\tissue={issue_id}\t{hours}h\t"
            f"{entry.get('description', '')}"
        )
    total = result.get("metadata", {}).get("count", len(result.get("results", [])))
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
    except (TempoLogError, ValueError) as exc:
        logger.error(str(exc))
        return 1

    print(f"Updated worklog {args.worklog_id}.")
    return 0


def run(args: argparse.Namespace) -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        logger.error(str(exc))
        return 1

    service = TempoService.from_settings(settings)

    if args.command == "create":
        return run_create(args, service)
    if args.command == "list":
        return run_list(args, service)
    if args.command == "update":
        return run_update(args, service)
    if args.command == "batch":
        return run_batch(args, service)
    if args.command == "doctor":
        return run_doctor(service)

    logger.error("Unknown command: %s", args.command)
    return 1


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    sys.exit(run(args))


if __name__ == "__main__":
    main()
