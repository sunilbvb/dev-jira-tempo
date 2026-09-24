"""Command-line entry point for managing Tempo worklogs.

Required env var:
  TEMPO_API_TOKEN     Tempo -> Settings -> API Integration -> New token

Optional env vars (only needed to auto-resolve an issue key like "PROJ-123"
to a numeric Jira issue id, and/or to auto-detect your accountId):
  JIRA_BASE_URL        e.g. https://yourcompany.atlassian.net
  JIRA_EMAIL           your Jira login email
  JIRA_API_TOKEN       Jira API token

If you already know your numeric issueId and Jira accountId, pass
--issue-id and --account-id directly and skip the Jira env vars. You can
also set JIRA_ACCOUNT_ID as a default so --account-id isn't required on
every call.

Examples:
  tempo-log create --issue PROJ-123 --hours 2.5 --description "Code review"
  tempo-log create --issue-id 10042 --account-id 557058:abc... --hours 1
  tempo-log list --from 2026-09-01 --to 2026-09-17
  tempo-log update 25234 --description "Updated description" --hours 1.5
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from .config import ConfigError, load_settings
from .jira_client import JiraClient, JiraClientError
from .journal import append_entry, journal_path
from .tempo_client import TempoClient, TempoClientError, Worklog

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


def _resolve_issue_and_account(args, settings) -> tuple[int, str] | None:
    issue_id = args.issue_id
    account_id = args.account_id or settings.default_account_id

    if issue_id is None or account_id is None:
        if settings.jira is None:
            logger.error(
                "Provide --issue-id and --account-id (or set JIRA_ACCOUNT_ID), "
                "or set JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN to auto-resolve them."
            )
            return None

        jira_client = JiraClient(settings.jira)
        try:
            if issue_id is None:
                if not args.issue:
                    logger.error("Provide --issue (key) or --issue-id (numeric).")
                    return None
                issue_id = jira_client.resolve_issue_id(args.issue)
            if account_id is None:
                account_id = jira_client.get_current_account_id()
        except JiraClientError as exc:
            logger.error(str(exc))
            return None

    return issue_id, account_id


def run_create(args: argparse.Namespace, settings) -> int:
    if args.hours <= 0:
        logger.error("Hours must be a positive number, got %s", args.hours)
        return 1

    resolved = _resolve_issue_and_account(args, settings)
    if resolved is None:
        return 1
    issue_id, account_id = resolved

    worklog = Worklog(
        issue_id=issue_id,
        account_id=account_id,
        hours=args.hours,
        start_date=args.date,
        start_time=args.time,
        description=args.description,
    )

    tempo_client = TempoClient(settings.tempo_api_token)
    try:
        result = tempo_client.create_worklog(worklog)
    except TempoClientError as exc:
        logger.error(str(exc))
        return 1

    worklog_id = result.get("tempoWorklogId")
    append_entry(
        tempo_worklog_id=worklog_id,
        issue_id=issue_id,
        account_id=account_id,
        hours=args.hours,
        start_date=args.date,
        start_time=args.time,
        description=args.description,
    )

    print(f"Logged {args.hours}h on issue {issue_id}. Tempo worklog ID: {worklog_id}")
    return 0


def run_batch(args: argparse.Namespace, settings) -> int:
    try:
        with open(args.file) as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read %s: %s", args.file, exc)
        return 1

    if not isinstance(entries, list):
        logger.error("Batch file must contain a JSON list of entries.")
        return 1

    tempo_client = TempoClient(settings.tempo_api_token)
    jira_client = JiraClient(settings.jira) if settings.jira else None

    succeeded = 0
    failed = 0
    failures: list[str] = []

    for i, entry in enumerate(entries):
        label = entry.get("issue") or entry.get("issue_id") or f"entry #{i}"
        try:
            issue_id = entry.get("issue_id")
            if issue_id is None:
                if not entry.get("issue"):
                    raise ValueError("entry has neither issue_id nor issue")
                if jira_client is None:
                    raise ValueError(
                        "issue key given but JIRA_* env vars aren't configured"
                    )
                issue_id = jira_client.resolve_issue_id(entry["issue"])

            account_id = entry.get("account_id") or settings.default_account_id
            if not account_id:
                raise ValueError("no account_id given and JIRA_ACCOUNT_ID not set")

            hours = float(entry["hours"])
            start_date = entry["date"]
            start_time = entry.get("time", "10:00:00")
            description = entry.get("description", "")

            worklog = Worklog(
                issue_id=issue_id,
                account_id=account_id,
                hours=hours,
                start_date=start_date,
                start_time=start_time,
                description=description,
            )
            result = tempo_client.create_worklog(worklog)
            worklog_id = result.get("tempoWorklogId")
            append_entry(
                tempo_worklog_id=worklog_id,
                issue_id=issue_id,
                account_id=account_id,
                hours=hours,
                start_date=start_date,
                start_time=start_time,
                description=description,
            )
            succeeded += 1
        except (TempoClientError, JiraClientError, ValueError, KeyError) as exc:
            failed += 1
            failures.append(f"{label}: {exc}")
            logger.error("Failed to submit %s: %s", label, exc)
            if args.stop_on_error:
                break

    print(f"\n{succeeded} succeeded, {failed} failed.")
    if failures:
        print("Failures:")
        for line in failures:
            print(f"  - {line}")
    print(f"Journal: {journal_path()}")
    return 1 if failed else 0


def run_doctor(settings) -> int:
    ok = True

    tempo_client = TempoClient(settings.tempo_api_token)
    try:
        tempo_client.list_worklogs(limit=1)
        print("Tempo: OK (TEMPO_API_TOKEN authenticates).")
    except TempoClientError as exc:
        ok = False
        print(f"Tempo: FAILED - {exc}")

    if settings.jira:
        jira_client = JiraClient(settings.jira)
        try:
            account_id = jira_client.get_current_account_id()
            print(f"Jira: OK (authenticated as accountId={account_id}).")
        except JiraClientError as exc:
            ok = False
            print(f"Jira: FAILED - {exc}")
    else:
        print("Jira: not configured (JIRA_BASE_URL/JIRA_EMAIL/JIRA_API_TOKEN unset).")

    if settings.default_account_id:
        print(f"JIRA_ACCOUNT_ID: set ({settings.default_account_id}).")
    else:
        print("JIRA_ACCOUNT_ID: not set.")

    return 0 if ok else 1


def run_list(args: argparse.Namespace, settings) -> int:
    account_id = args.account_id or settings.default_account_id
    if not account_id:
        logger.error("Provide --account-id or set JIRA_ACCOUNT_ID.")
        return 1

    tempo_client = TempoClient(settings.tempo_api_token)
    try:
        result = tempo_client.list_worklogs(
            account_id=account_id,
            from_date=args.from_date,
            to_date=args.to_date,
            limit=args.limit,
            offset=args.offset,
        )
    except TempoClientError as exc:
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


def run_update(args: argparse.Namespace, settings) -> int:
    tempo_client = TempoClient(settings.tempo_api_token)
    try:
        tempo_client.update_worklog(
            args.worklog_id,
            hours=args.hours,
            description=args.description,
            start_date=args.date,
            start_time=args.time,
        )
    except (TempoClientError, ValueError) as exc:
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

    if args.command == "create":
        return run_create(args, settings)
    if args.command == "list":
        return run_list(args, settings)
    if args.command == "update":
        return run_update(args, settings)
    if args.command == "batch":
        return run_batch(args, settings)
    if args.command == "doctor":
        return run_doctor(settings)

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
