"""Interactive TUI Dashboard and weekly summary viewer."""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from typing import Any

from .journal import DEFAULT_SQLITE_PATH, SQLiteJournal
from .timer import get_active_timer, start_timer, stop_timer


def _get_week_bounds(target_date: date | None = None) -> tuple[str, str]:
    """Return Monday and Sunday dates (YYYY-MM-DD) for target date's week."""
    cur = target_date or date.today()
    start = cur - timedelta(days=cur.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


def render_dashboard_plain(journal: SQLiteJournal | None = None) -> str:
    """Render terminal dashboard in plain ANSI text."""
    j = journal or SQLiteJournal()
    active = get_active_timer()
    today_str = date.today().isoformat()
    mon_str, sun_str = _get_week_bounds()

    week_summary = j.weekly_summary(from_date=mon_str, to_date=sun_str)
    today_summary = j.weekly_summary(from_date=today_str, to_date=today_str)

    lines = []
    lines.append("=" * 64)
    lines.append("              TEMPO WORKLOG CONSOLE & DASHBOARD              ")
    lines.append("=" * 64)

    # Active Timer Panel
    lines.append("\n[ LIVE TIMER ]")
    if active:
        target = active.issue or str(active.issue_id)
        lines.append(f"  ● RUNNING: {target} ({active.formatted_duration})")
        lines.append(f"    Started at: {active.started_at}")
        if active.description:
            lines.append(f"    Desc:       {active.description}")
        lines.append(f"    Billable:   ~{active.elapsed_hours}h")
    else:
        lines.append("  ○ IDLE (No active timer running)")

    # Metrics Panel
    today_hours = today_summary.get("total_hours", 0.0)
    week_hours = week_summary.get("total_hours", 0.0)

    lines.append("\n[ TIME SUMMARY ]")
    lines.append(f"  Today ({today_str}):     {today_hours:5.2f} / 8.00h  ({min(100, int(today_hours / 8.0 * 100))}%)")
    lines.append(f"  This Week ({mon_str} -> {sun_str}): {week_hours:5.2f} / 40.00h ({min(100, int(week_hours / 40.0 * 100))}%)")

    # Issue breakdown this week
    issue_totals = week_summary.get("issue_totals", {})
    if issue_totals:
        lines.append("\n[ WEEKLY ISSUES ]")
        for issue_key, hrs in sorted(issue_totals.items(), key=lambda x: x[1], reverse=True)[:5]:
            bar = "█" * int(hrs * 2)
            lines.append(f"  {issue_key:12} {hrs:5.2f}h {bar}")

    # Recent 5 Worklogs
    recent = j.query(limit=5)
    lines.append("\n[ RECENT AUDIT LOGS ]")
    if recent:
        for r in recent:
            ikey = r.get("issue_key") or str(r.get("issue_id")) or "-"
            h = r.get("hours", 0.0)
            d = r.get("start_date", "")
            desc = (r.get("description") or "")[:30]
            lines.append(f"  {d} | {ikey:10} | {h:4.2f}h | {desc}")
    else:
        lines.append("  No local audit records found yet.")

    lines.append("\n" + "=" * 64)
    return "\n".join(lines)


def render_dashboard_rich(journal: SQLiteJournal | None = None) -> Any:
    """Render rich terminal dashboard using rich library if available."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
    except ImportError:
        return None

    j = journal or SQLiteJournal()
    active = get_active_timer()
    today_str = date.today().isoformat()
    mon_str, sun_str = _get_week_bounds()

    week_summary = j.weekly_summary(from_date=mon_str, to_date=sun_str)
    today_summary = j.weekly_summary(from_date=today_str, to_date=today_str)
    today_hours = today_summary.get("total_hours", 0.0)
    week_hours = week_summary.get("total_hours", 0.0)

    console = Console()

    # Timer display
    if active:
        timer_text = Text()
        timer_text.append(f"● RUNNING: {active.issue or active.issue_id} ", style="bold green")
        timer_text.append(f"[{active.formatted_duration}]", style="bold yellow")
        timer_text.append(f"\nStarted: {active.started_at} | Billable: ~{active.elapsed_hours}h")
        if active.description:
            timer_text.append(f"\nDescription: {active.description}", style="italic")
        timer_panel = Panel(timer_text, title="Active Timer", border_style="green")
    else:
        timer_panel = Panel("○ Idle (No active timer)", title="Active Timer", border_style="dim")

    # Metrics table
    metrics_table = Table(show_header=True, header_style="bold cyan", expand=True)
    metrics_table.add_column("Period")
    metrics_table.add_column("Logged", justify="right")
    metrics_table.add_column("Target", justify="right")
    metrics_table.add_column("Progress")

    def progress_bar(val: float, target: float) -> str:
        pct = min(1.0, val / target) if target > 0 else 0
        filled = int(pct * 20)
        return f"[{'=' * filled}{' ' * (20 - filled)}] {int(pct * 100)}%"

    metrics_table.add_row(f"Today ({today_str})", f"{today_hours:.2f}h", "8.00h", progress_bar(today_hours, 8.0))
    metrics_table.add_row(f"Week ({mon_str} to {sun_str})", f"{week_hours:.2f}h", "40.00h", progress_bar(week_hours, 40.0))

    # Recent table
    recent = j.query(limit=5)
    recent_table = Table(show_header=True, header_style="bold magenta", expand=True)
    recent_table.add_column("Date", width=12)
    recent_table.add_column("Issue", width=12)
    recent_table.add_column("Hours", justify="right", width=8)
    recent_table.add_column("Description")

    for r in recent:
        ikey = r.get("issue_key") or str(r.get("issue_id")) or "-"
        recent_table.add_row(
            str(r.get("start_date", "")),
            ikey,
            f"{r.get('hours', 0.0):.2f}h",
            str(r.get("description", ""))[:40],
        )

    console.print(timer_panel)
    console.print(metrics_table)
    console.print(recent_table)
    return True


def display_dashboard(journal: SQLiteJournal | None = None) -> None:
    """Print the dashboard once using Rich if available, otherwise plain text."""
    if render_dashboard_rich(journal):
        return
    print(render_dashboard_plain(journal))


def run_interactive_tui(service: Any) -> None:
    """Run an interactive TUI dashboard loop in the terminal."""
    journal = SQLiteJournal()
    print("\nStarting Interactive Tempo Dashboard (Press 'q' to quit, 'h' for help)...")
    time.sleep(0.5)

    while True:
        # Clear screen
        print("\033[2J\033[H", end="")
        display_dashboard(journal)

        print("\nActions: [s] Start Timer | [x] Stop & Log | [d] Discard Timer | [l] Quick Log | [r] Refresh | [q] Quit")
        try:
            choice = input("\nSelect option > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting dashboard.")
            break

        if choice in ("q", "quit", "exit"):
            print("Goodbye!")
            break
        elif choice == "r":
            continue
        elif choice == "s":
            issue = input("Enter Jira issue key (e.g. PROJ-123): ").strip()
            if not issue:
                print("Issue key required.")
                time.sleep(1)
                continue
            desc = input("Description (optional): ").strip()
            try:
                start_timer(issue=issue, description=desc)
                print(f"Timer started for {issue}!")
            except Exception as exc:
                print(f"Error: {exc}")
            time.sleep(1.5)
        elif choice == "x":
            active = get_active_timer()
            if not active:
                print("No active timer running.")
                time.sleep(1)
                continue
            hrs = active.elapsed_hours
            print(f"Stopping timer for {active.issue or active.issue_id} ({hrs}h)...")
            try:
                stopped = stop_timer()
                service.log_time(
                    hours=stopped.elapsed_hours,
                    issue=stopped.issue,
                    issue_id=stopped.issue_id,
                    description=stopped.description,
                )
                print(f"Successfully logged {hrs}h to Tempo!")
            except Exception as exc:
                print(f"Failed to log: {exc}")
            time.sleep(1.5)
        elif choice == "d":
            try:
                stop_timer(discard=True)
                print("Active timer discarded.")
            except Exception as exc:
                print(f"Error: {exc}")
            time.sleep(1)
        elif choice == "l":
            issue = input("Enter Jira issue key: ").strip()
            hours_str = input("Hours (e.g. 1.5): ").strip()
            desc = input("Description: ").strip()
            try:
                h = float(hours_str)
                service.log_time(hours=h, issue=issue, description=desc)
                print(f"Successfully logged {h}h!")
            except Exception as exc:
                print(f"Error: {exc}")
            time.sleep(1.5)
        elif choice == "h":
            print("\nHelp:\n  s: Start stopwatch\n  x: Stop stopwatch and log to Tempo\n  d: Discard active stopwatch\n  l: Log hours manually\n  r: Refresh\n  q: Quit")
            input("Press Enter to continue...")
