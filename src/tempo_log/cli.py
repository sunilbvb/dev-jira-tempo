"""Command-line entry point for managing Tempo worklogs and developer workflows."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .commands import (
    run_batch,
    run_create,
    run_doctor,
    run_from_worklog,
    run_list,
    run_update,
)
from .completion import generate_completion, get_recent_issues
from .config import ConfigError, Settings, load_settings
from .exceptions import TempoLogError, ValidationError
from .git_hook import install_hook, parse_commit_message, run_git_hook, uninstall_hook
from .journal import DEFAULT_SQLITE_PATH, SQLiteJournal, journal_path
from .keyring_store import (
    delete_credential,
    get_credential,
    is_keyring_available,
    set_credential,
)
from .service import TempoService
from .timer import get_active_timer, start_timer, stop_timer
from .tui import display_dashboard, run_interactive_tui

logger = logging.getLogger(__name__)

KEYRING_ALIAS_MAP = {
    "tempo": "TEMPO_API_TOKEN",
    "tempo_token": "TEMPO_API_TOKEN",
    "tempo_api_token": "TEMPO_API_TOKEN",
    "tempo_base": "TEMPO_BASE_URL",
    "tempo_base_url": "TEMPO_BASE_URL",
    "jira": "JIRA_API_TOKEN",
    "jira_token": "JIRA_API_TOKEN",
    "jira_api_token": "JIRA_API_TOKEN",
    "jira_base": "JIRA_BASE_URL",
    "jira_base_url": "JIRA_BASE_URL",
    "base_url": "JIRA_BASE_URL",
    "jira_email": "JIRA_EMAIL",
    "email": "JIRA_EMAIL",
    "account_id": "JIRA_ACCOUNT_ID",
    "jira_account_id": "JIRA_ACCOUNT_ID",
    "daily_cap": "TEMPO_DAILY_CAP_HOURS",
    "daily_cap_hours": "TEMPO_DAILY_CAP_HOURS",
    "round_minutes": "TEMPO_ROUND_MINUTES",
    "default_issue": "TEMPO_DEFAULT_ISSUE",
    "meeting_issue": "TEMPO_MEETING_ISSUE",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tempo-log", description="Manage Tempo (Jira time-tracking) worklogs."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. create
    create_parser = subparsers.add_parser("create", help="Log new time to Tempo.")
    issue_group = create_parser.add_mutually_exclusive_group(required=True)
    issue_group.add_argument(
        "-i", "--issue", help="Issue key, e.g. PROJ-123 (requires JIRA_* env vars)."
    )
    issue_group.add_argument(
        "--issue-id", type=int, help="Numeric Jira issue id (skips Jira lookup)."
    )
    create_parser.add_argument(
        "-a", "--account-id", help="Jira accountId (skips Jira lookup for the author)."
    )
    create_parser.add_argument(
        "-H", "--hours", type=float, required=True, help="Hours to log, e.g. 2.5."
    )
    create_parser.add_argument(
        "-d",
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Worklog date as YYYY-MM-DD (default: today).",
    )
    create_parser.add_argument(
        "-t",
        "--time",
        default=datetime.now().strftime("%H:%M:%S"),
        help="Worklog start time as HH:MM:SS (default: now).",
    )
    create_parser.add_argument(
        "-m", "--desc", "--description", dest="description", default="", help="Worklog description."
    )

    # 2. list
    list_parser = subparsers.add_parser("list", help="List existing worklogs.")
    list_parser.add_argument(
        "-a", "--account-id", help="Jira accountId to list worklogs for (default: JIRA_ACCOUNT_ID)."
    )
    list_parser.add_argument("-F", "--from", dest="from_date", help="Start date YYYY-MM-DD.")
    list_parser.add_argument("-T", "--to", dest="to_date", help="End date YYYY-MM-DD.")
    list_parser.add_argument("-n", "--limit", type=int, default=50, help="Max results (default 50).")
    list_parser.add_argument("--offset", type=int, default=0, help="Pagination offset.")

    # 3. update
    update_parser = subparsers.add_parser("update", help="Update an existing worklog.")
    update_parser.add_argument("worklog_id", type=int, help="Numeric Tempo worklog ID.")
    update_parser.add_argument("-H", "--hours", type=float, help="New hours value.")
    update_parser.add_argument("-m", "--desc", "--description", dest="description", help="New description.")
    update_parser.add_argument("-d", "--date", help="New start date YYYY-MM-DD.")
    update_parser.add_argument("-t", "--time", help="New start time HH:MM:SS.")

    # 4. batch
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
    batch_parser.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Bypass duplicate detection and submit all entries.",
    )
    batch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate batch entries without submitting worklogs.",
    )
    batch_parser.add_argument(
        "--rollback-on-error",
        action="store_true",
        help="Automatically delete created worklogs if batch encounters an error.",
    )

    # 5. from-worklog
    from_worklog_parser = subparsers.add_parser(
        "from-worklog",
        help="Import and preview worklogs from a markdown journal file.",
        description="Parse markdown worklogs (## YYYY-MM-DD heading, Tempo: KEY | HH:MM-HH:MM line, bullets).",
    )
    from_worklog_parser.add_argument("file", help="Path to markdown worklog file.")
    from_worklog_parser.add_argument("-F", "--from", dest="from_date", help="Start date YYYY-MM-DD.")
    from_worklog_parser.add_argument("-T", "--to", dest="to_date", help="End date YYYY-MM-DD.")
    from_worklog_parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit worklogs to Tempo (default is preview only).",
    )
    from_worklog_parser.add_argument(
        "--strict",
        action="store_true",
        help="Abort submission if any daily cap or overlap warnings exist.",
    )
    from_worklog_parser.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Bypass duplicate detection and submit all entries.",
    )
    from_worklog_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate worklog entries without submitting to Tempo.",
    )
    from_worklog_parser.add_argument(
        "--rollback-on-error",
        action="store_true",
        help="Automatically delete created worklogs if batch encounters an error.",
    )

    # 6. doctor
    subparsers.add_parser(
        "doctor", help="Check that Tempo (and Jira, if configured) credentials work."
    )

    # 6. start (Timer)
    start_parser = subparsers.add_parser("start", help="Start live stopwatch timer.")
    timer_issue_group = start_parser.add_mutually_exclusive_group(required=True)
    timer_issue_group.add_argument("-i", "--issue", help="Jira issue key, e.g. PROJ-123.")
    timer_issue_group.add_argument("--issue-id", type=int, help="Numeric Jira issue ID.")
    start_parser.add_argument(
        "-m", "--desc", "--description", dest="description", default="", help="Work description."
    )

    # 7. stop (Timer)
    stop_parser = subparsers.add_parser("stop", help="Stop active timer and log to Tempo.")
    stop_parser.add_argument(
        "--discard", action="store_true", help="Discard timer without logging to Tempo."
    )
    stop_parser.add_argument(
        "-a", "--account-id", help="Jira accountId to log as (default: detected or configured)."
    )

    # 8. status (Timer)
    subparsers.add_parser("status", help="Show active stopwatch status.")

    # 9. tui (Interactive Dashboard)
    tui_parser = subparsers.add_parser("tui", help="Launch interactive terminal dashboard.")
    tui_parser.add_argument(
        "--once", action="store_true", help="Print dashboard snapshot and exit."
    )

    # 10. ui / web (Interactive Web Console)
    ui_parser = subparsers.add_parser("ui", help="Launch Tempo Web Console (HTML dashboard).")
    ui_parser.add_argument("--port", type=int, default=18114, help="Port to serve on (default: 18114).")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1).")
    ui_parser.add_argument("--terminal", action="store_true", help="Launch terminal TUI instead of web dashboard.")
    ui_parser.add_argument("--once", action="store_true", help="Print terminal dashboard snapshot and exit.")

    # 10. summary (SQLite Audit Log & Metrics)
    summary_parser = subparsers.add_parser("summary", help="View weekly summary and audit log.")
    summary_parser.add_argument("-F", "--from", dest="from_date", help="Filter from date (YYYY-MM-DD).")
    summary_parser.add_argument("-T", "--to", dest="to_date", help="Filter to date (YYYY-MM-DD).")
    summary_parser.add_argument("-i", "--issue", dest="issue_key", help="Filter by issue key.")
    summary_parser.add_argument("-n", "--limit", type=int, default=20, help="Audit entries limit.")
    summary_parser.add_argument("--export-csv", help="Export audit records to specified CSV filepath.")

    # 11. auth (OS Keyring Storage)
    auth_parser = subparsers.add_parser("auth", help="Manage credentials in OS keyring.")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_action", required=True)

    auth_set = auth_subparsers.add_parser("set-token", help="Store token in OS keyring.")
    auth_set.add_argument(
        "key", help="Credential key (tempo, jira, base_url, email, account_id)"
    )
    auth_set.add_argument("value", help="Secret token or value to store")

    auth_get = auth_subparsers.add_parser("get-token", help="Retrieve token from OS keyring.")
    auth_get.add_argument("key", help="Credential key to lookup")

    auth_del = auth_subparsers.add_parser("delete-token", help="Delete token from OS keyring.")
    auth_del.add_argument("key", help="Credential key to delete")

    auth_subparsers.add_parser("status", help="Check OS keyring status.")

    # 12. completion (Shell Tab-Completion)
    comp_parser = subparsers.add_parser("completion", help="Generate shell autocompletion script.")
    comp_parser.add_argument(
        "--shell", choices=["bash", "zsh", "fish"], help="Target shell for script generation."
    )
    comp_parser.add_argument(
        "--list-issues", action="store_true", help="Print recent issue keys for completion."
    )

    # 13. git-hook (Git Auto-Worklog Hook)
    hook_parser = subparsers.add_parser("git-hook", help="Git commit auto-worklog hook.")
    hook_subparsers = hook_parser.add_subparsers(dest="hook_action", required=True)

    hook_install = hook_subparsers.add_parser("install", help="Install git post-commit hook.")
    hook_install.add_argument("--repo", default=".", help="Target git repository path (default: .).")

    hook_uninstall = hook_subparsers.add_parser("uninstall", help="Uninstall git post-commit hook.")
    hook_uninstall.add_argument("--repo", default=".", help="Target git repository path (default: .).")

    hook_run = hook_subparsers.add_parser("run", help="Run hook against latest commit or custom msg.")
    hook_run.add_argument("--msg", help="Commit message to parse instead of git HEAD.")
    hook_run.add_argument("--repo", default=".", help="Target git repository path (default: .).")

    hook_check = hook_subparsers.add_parser("check", help="Dry-run parse a commit message.")
    hook_check.add_argument("msg", help="Commit message string to test.")

    return parser


def _get_service(target: Settings | TempoService) -> Any:
    if isinstance(target, Settings):
        return TempoService.from_settings(target)
    return target
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


def run_start(args: argparse.Namespace) -> int:
    try:
        state = start_timer(
            issue=args.issue,
            issue_id=args.issue_id,
            description=args.description,
        )
        target = state.issue or str(state.issue_id)
        print(f"Timer started for {target} at {state.started_at}.")
        if state.description:
            print(f"Description: {state.description}")
        return 0
    except ValidationError as exc:
        logger.error(str(exc))
        return 1


def run_status() -> int:
    active = get_active_timer()
    if not active:
        print("No active timer running.")
        return 0
    target = active.issue or str(active.issue_id)
    print(f"Active Timer: {target}")
    print(f"  Duration:    {active.formatted_duration} (~{active.elapsed_hours}h)")
    print(f"  Started At:  {active.started_at}")
    if active.description:
        print(f"  Description: {active.description}")
    return 0


def run_stop(args: argparse.Namespace, target: Settings | TempoService | None = None) -> int:
    if args.discard:
        try:
            stopped = stop_timer(discard=True)
            print(f"Timer for {stopped.issue or stopped.issue_id} discarded.")
            return 0
        except ValidationError as exc:
            logger.error(str(exc))
            return 1

    active = get_active_timer()
    if not active:
        logger.error("No active timer running.")
        return 1

    hrs = active.elapsed_hours
    target_name = active.issue or str(active.issue_id)
    print(f"Stopping timer for {target_name} ({active.formatted_duration} -> {hrs}h)...")

    if target is None:
        try:
            settings = load_settings()
            service = TempoService.from_settings(settings)
        except ConfigError as exc:
            logger.error(str(exc))
            return 1
    else:
        service = _get_service(target)

    try:
        stopped = stop_timer()
        result = service.log_time(
            hours=hrs,
            issue=stopped.issue,
            issue_id=stopped.issue_id,
            account_id=args.account_id,
            description=stopped.description,
        )
        worklog_id = result.get("tempoWorklogId")
        print(f"Logged {hrs}h for {target_name}. Tempo worklog ID: {worklog_id}")
        return 0
    except Exception as exc:
        logger.error("Failed to log stopped timer: %s", exc)
        return 1


def run_summary(args: argparse.Namespace) -> int:
    journal = SQLiteJournal()
    if args.export_csv:
        count = journal.export_csv(args.export_csv)
        print(f"Exported {count} worklogs to {args.export_csv}")
        return 0

    display_dashboard(journal)
    return 0


def run_tui(args: argparse.Namespace, target: Settings | TempoService | None = None) -> int:
    if args.once:
        display_dashboard(SQLiteJournal())
        return 0

    if target is None:
        try:
            settings = load_settings()
            service = TempoService.from_settings(settings)
        except ConfigError:
            service = None
    else:
        service = _get_service(target)

    run_interactive_tui(service)
    return 0


def run_ui(args: argparse.Namespace, target: Settings | TempoService | None = None) -> int:
    if getattr(args, "terminal", False) or getattr(args, "once", False):
        return run_tui(args, target)

    port = getattr(args, "port", 18114)
    host = getattr(args, "host", "127.0.0.1")
    print(f"🚀 Starting Tempo Web Console on http://localhost:{port} (host: {host})")
    print("Press Ctrl+C to stop.")
    try:
        from .web_server import run_server
        run_server(port=port, host=host)
        return 0
    except Exception as exc:
        logger.error("Web server error: %s", exc)
        return 1


def run_auth(args: argparse.Namespace) -> int:
    action = args.auth_action
    if action == "status":
        avail = is_keyring_available()
        print(f"OS Keyring available: {'YES' if avail else 'NO (install keyring package)'}")
        return 0

    key = KEYRING_ALIAS_MAP.get(args.key.lower(), args.key)

    if action == "set-token":
        try:
            set_credential(key, args.value)
            print(f"Stored credential for '{key}' in OS keyring.")
            return 0
        except Exception as exc:
            logger.error("Failed to store credential: %s", exc)
            return 1

    if action == "get-token":
        val = get_credential(key)
        if val:
            print(f"{key}: {val[:4]}...{val[-4:] if len(val) > 8 else ''}")
            return 0
        print(f"No credential found for '{key}'.")
        return 1

    if action == "delete-token":
        if delete_credential(key):
            print(f"Deleted credential for '{key}'.")
            return 0
        print(f"Failed to delete credential for '{key}'.")
        return 1

    return 1


def run_completion(args: argparse.Namespace) -> int:
    if args.list_issues:
        issues = get_recent_issues()
        for issue in issues:
            print(issue)
        return 0

    if args.shell:
        try:
            script = generate_completion(args.shell)
            print(script)
            return 0
        except ValueError as exc:
            logger.error(str(exc))
            return 1

    logger.error("Provide --shell [bash|zsh|fish] or --list-issues.")
    return 1


def run_hook_command(args: argparse.Namespace, target: Settings | TempoService | None = None) -> int:
    action = args.hook_action
    if action == "install":
        try:
            path = install_hook(repo_path=args.repo)
            print(f"Git auto-worklog hook installed to {path}")
            return 0
        except Exception as exc:
            logger.error(str(exc))
            return 1

    if action == "uninstall":
        if uninstall_hook(repo_path=args.repo):
            print("Git hook uninstalled.")
            return 0
        print("No git hook found to uninstall.")
        return 1

    if action == "check":
        info = parse_commit_message(args.msg)
        if info:
            print(f"Matched Issue:  {info.issue_key}")
            print(f"Duration:       {info.hours}h")
            print(f"Description:    {info.description}")
            return 0
        print("No worklog pattern matched in commit message.")
        return 1

    if action == "run":
        if target is None:
            try:
                settings = load_settings()
                service = TempoService.from_settings(settings)
            except ConfigError as exc:
                logger.debug("Credentials not available for git-hook: %s", exc)
                return 0
        else:
            service = _get_service(target)

        res = run_git_hook(service=service, commit_msg=args.msg, repo_path=args.repo)
        if res:
            print(f"Auto-logged {res['hours']}h to {res['issue']}: {res['description']}")
        return 0

    return 1


def run(args: argparse.Namespace) -> int:
    # Commands that do NOT require API credentials or settings
    if args.command == "start":
        return run_start(args)
    if args.command == "status":
        return run_status()
    if args.command == "summary":
        return run_summary(args)
    if args.command == "auth":
        return run_auth(args)
    if args.command == "completion":
        return run_completion(args)
    if args.command == "git-hook" and args.hook_action in ("install", "uninstall", "check"):
        return run_hook_command(args)
    if args.command == "stop" and args.discard:
        return run_stop(args)

    # Commands that may run without settings or handle them lazily
    if args.command == "tui":
        return run_tui(args)
    if args.command in ("ui", "web"):
        return run_ui(args)
    if args.command == "git-hook" and args.hook_action == "run":
        return run_hook_command(args)

    # Commands that strictly require credentials
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
    if args.command == "from-worklog":
        return run_from_worklog(args, service)
    if args.command == "doctor":
        return run_doctor(service)
    if args.command == "stop":
        return run_stop(args, service)

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
