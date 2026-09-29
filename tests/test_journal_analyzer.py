"""Tests for the free-form journal analyzer (tempo-log analyze)."""

from __future__ import annotations

import json

from tempo_log.cli import run
from tempo_log.cli import build_parser
from tempo_log.journal_analyzer import analyze_day, format_report, parse_duration_minutes, parse_journal

JOURNAL = """
## 2026-09-24 09:00 UTC — PROJ-1: add login banner
Time estimate: 30m | Ticket: PROJ-1 [id:1001]

- Added banner component
- Wired translations

## 2026-09-24 09:30 UTC — Batch fixing QA doc
Time estimate: (logged per-ticket below)

### PROJ-2 — fixed (15m)
Trailing padding was missing.

### PROJ-3 — fixed (1h, medium)
Rewired the call button.

### PROJ-4 — already fixed (duplicate of PROJ-9)
No change needed.

## 2026-09-24 10:30 UTC — Onboarding step fixes
Time: 10:30–12:00 UTC (1h30m) | Ticket: none (recommend filing under PROJ-50)

- Fixed duplicated address text

## 2026-09-24 11:00 UTC — Quick check
Time: 11:00–11:05 UTC (5m) | Ticket: PROJ-7

- Ran a gap check

## 2026-09-25 09:00 UTC — Other day
Time estimate: 2h | Ticket: PROJ-1 [id:1001]
"""


def test_parse_duration_minutes():
    assert parse_duration_minutes("1h 30m") == 90
    assert parse_duration_minutes("2h") == 120
    assert parse_duration_minutes("45m") == 45
    assert parse_duration_minutes("(1h, medium)") == 60
    assert parse_duration_minutes("no time") is None


def test_parse_journal_sessions_and_subentries():
    entries = parse_journal(JOURNAL)
    day = [e for e in entries if e.date == "2026-09-24"]
    first = day[0]
    assert (first.ticket, first.issue_id, first.minutes, first.start) == ("PROJ-1", 1001, 30, "09:00")
    assert first.bullets == ["Added banner component", "Wired translations"]

    batch = day[1]
    assert batch.is_container
    subs = [e for e in day if e.kind == "sub"]
    assert [(s.ticket, s.minutes) for s in subs] == [("PROJ-2", 15), ("PROJ-3", 60), ("PROJ-4", None)]

    onboarding = day[5]
    assert onboarding.ticket is None
    assert onboarding.suggested_ticket == "PROJ-50"
    assert (onboarding.start, onboarding.end, onboarding.minutes) == ("10:30", "12:00", 90)


def test_analyze_flags_blockers_and_day_checks():
    entries = parse_journal(JOURNAL)
    report = analyze_day(entries, "2026-09-24", round_minutes=15, daily_cap_hours=3)

    by_ticket = {p.entry.ticket: p for p in report.planned}
    assert by_ticket["PROJ-1"].status == "READY"
    assert any("numeric issue id" in x for x in by_ticket["PROJ-2"].problems)
    assert any("No duration" in x for x in by_ticket["PROJ-4"].problems)
    assert any("billable" in n for n in by_ticket["PROJ-4"].notes)
    assert any("PROJ-50" in x for x in by_ticket[None].problems)
    assert any("5m -> 15m" in n for n in by_ticket["PROJ-7"].notes)

    # sub-entries chain after the parent heading
    assert by_ticket["PROJ-2"].start == "09:30"
    assert by_ticket["PROJ-3"].start == "09:45"

    # 30 + 15 + 60 + 90 + 15 = 3h30m > 3h cap
    assert report.total_minutes == 210
    assert any("exceeds the 3h cap" in w for w in report.day_warnings)
    assert any("Overlap" in w for w in report.day_warnings)
    assert any("PROJ-2" in s and "JIRA_API_TOKEN" in s for s in report.next_steps)
    assert "Nothing was sent to Tempo." in format_report(report)


def test_resolver_fills_ids_and_existing_worklogs_counted():
    entries = parse_journal(JOURNAL)
    ids = {"PROJ-2": 1002, "PROJ-3": 1003, "PROJ-4": 1004, "PROJ-7": 1007}
    existing = [{"issue": {"id": 1001}, "timeSpentSeconds": 1800}]
    report = analyze_day(entries, "2026-09-24", resolver=ids.get, existing_worklogs=existing)

    by_ticket = {p.entry.ticket: p for p in report.planned}
    assert by_ticket["PROJ-3"].status == "READY"
    assert report.existing_minutes == 30
    assert any("possible duplicate" in n for n in by_ticket["PROJ-1"].notes)


def test_analyze_unknown_date():
    report = analyze_day(parse_journal(JOURNAL), "2026-01-01")
    assert not report.planned
    assert "No journal entries" in report.day_warnings[0]


def test_cli_offline_export(tmp_path, capsys):
    journal = tmp_path / "journal.md"
    journal.write_text(JOURNAL, encoding="utf-8")
    out = tmp_path / "ready.json"
    args = build_parser().parse_args(
        ["analyze", str(journal), "-d", "2026-09-24", "--offline", "--cap", "12", "--export", str(out)]
    )
    assert run(args) == 0
    printed = capsys.readouterr().out
    assert "Journal analysis for 2026-09-24" in printed
    ready = json.loads(out.read_text())
    assert [r["issue_id"] for r in ready] == [1001]
    assert ready[0]["time"] == "09:00:00"
    assert ready[0]["description"].startswith("PROJ-1: add login banner\n- Added banner component")


def test_cli_strict_exits_nonzero(tmp_path):
    journal = tmp_path / "journal.md"
    journal.write_text(JOURNAL, encoding="utf-8")
    args = build_parser().parse_args(["analyze", str(journal), "-d", "2026-09-24", "--offline", "--strict"])
    assert run(args) == 1


def test_sub_heading_with_inline_id():
    content = """
## 2026-09-24 09:30 UTC — Batch
Time estimate: (logged per-ticket below)

### PROJ-2 [id:1002] — fixed (15m)
Done.
"""
    sub = [e for e in parse_journal(content) if e.kind == "sub"][0]
    assert (sub.ticket, sub.issue_id, sub.minutes, sub.status) == ("PROJ-2", 1002, 15, "fixed")


def test_container_without_recognised_subs_warns():
    content = """
## 2026-09-24 09:30 UTC — Batch
Time estimate: (logged per-ticket below)

### something unparseable
"""
    report = analyze_day(parse_journal(content), "2026-09-24")
    assert any("no '### KEY" in w for w in report.day_warnings)


def test_sequential_layout_snaps_and_skips_reserved():
    content = """
## 2026-09-24 14:28 UTC — PROJ-1: first
Time estimate: 30m | Ticket: PROJ-1 [id:1]

## 2026-09-24 14:29 UTC — PROJ-2: second
Time estimate: 20m | Ticket: PROJ-2 [id:2]

## 2026-09-24 14:40 UTC — PROJ-3: third
Time estimate: 1h | Ticket: PROJ-3 [id:3]
"""
    report = analyze_day(parse_journal(content), "2026-09-24", sequential=True, reserved=[("15:30", "16:30")])
    starts = [(p.entry.ticket, p.start) for p in report.planned]
    # 14:28 -> 14:30; PROJ-2 30m ends 15:30; PROJ-3 (1h) must skip the reserved hour
    assert starts == [("PROJ-1", "14:30"), ("PROJ-2", "15:00"), ("PROJ-3", "16:30")]
    assert not any("Overlap" in w for w in report.day_warnings)


def test_sequential_layout_blocks_past_midnight():
    content = """
## 2026-09-24 23:00 UTC — PROJ-1: late
Time estimate: 2h | Ticket: PROJ-1 [id:1]
"""
    report = analyze_day(parse_journal(content), "2026-09-24", sequential=True)
    assert report.planned[0].status == "BLOCKED"
    assert any("midnight" in x for x in report.planned[0].problems)
