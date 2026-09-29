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
    assert ready[0]["description"].startswith("add login banner\n- Added banner component")


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


# --------------------------------------------------------------------------- Roadmap F1-F10 Tests


def test_f7_heading_time_end_mode():
    content = """
## 2026-09-24 10:00 UTC — PROJ-1: work completed
Time estimate: 1h | Ticket: PROJ-1 [id:1]

## 2026-09-24 11:30 UTC — PROJ-2: next completed
Time estimate: 1h | Ticket: PROJ-2 [id:2]
"""
    entries = parse_journal(content, heading_time_mode="end")
    day = [e for e in entries if e.date == "2026-09-24"]
    # With end, 10:00 minus 1h -> start is 09:00, end is 10:00
    assert day[0].start == "09:00"
    assert day[0].end == "10:00"

    report = analyze_day(entries, "2026-09-24", heading_time="end")
    # Gap between 10:00 and 11:30 is 1h30m, claimed is 1h, so no inflated warning
    assert not any("inflated" in w for w in report.day_warnings)


def test_f6_timesheet_ready_descriptions():
    content = """
## 2026-09-24 09:00 UTC — PROJ-12: add login banner — fixed
Time estimate: 30m | Ticket: PROJ-12 [id:1001]

- Added login banner component for authorization.
- Files: src/components/Banner.vue, tests/test_banner.py
- Ran `pytest tests/test_banner.py` successfully.
- Internal notes: QA verified this in staging.
- Wired multi-language localization dictionary. And more text that should be trimmed.
"""
    entries = parse_journal(content)
    desc = entries[0].description(clean=True, max_bullets=4)
    # Title stripped ticket prefix and status word
    assert desc.startswith("add login banner")
    # Dropped file paths, backticks, internal notes
    assert "Files:" not in desc
    assert "pytest" not in desc
    assert "Internal notes" not in desc
    # Kept clean bullets and trimmed to 1 sentence
    assert "- Added login banner component for authorization." in desc
    assert "- Wired multi-language localization dictionary." in desc


def test_f3_consolidate_entries():
    content = """
## 2026-09-24 09:00 UTC — PROJ-1: fix bug part 1
Time estimate: 5m | Ticket: PROJ-1 [id:101]
- Did part 1

## 2026-09-24 09:10 UTC — PROJ-1: fix bug part 2
Time estimate: 10m | Ticket: PROJ-1 [id:101]
- Did part 2

## 2026-09-24 09:30 UTC — PROJ-2: other task
Time estimate: 15m | Ticket: PROJ-2 [id:102]
- Other work

## 2026-09-24 10:00 UTC — PROJ-1: fix bug part 3
Time estimate: 15m | Ticket: PROJ-1 [id:101]
- Did part 3
"""
    entries = parse_journal(content)

    # Contiguous mode: parts 1 & 2 merge (5+10 = 15m), part 3 remains separate
    rep_contig = analyze_day(entries, "2026-09-24", round_minutes=15, consolidate="contiguous")
    tickets_contig = [p.entry.ticket for p in rep_contig.planned]
    assert tickets_contig == ["PROJ-1", "PROJ-2", "PROJ-1"]
    assert rep_contig.planned[0].rounded_minutes == 15
    assert "- Did part 1" in rep_contig.planned[0].entry.description()
    assert "- Did part 2" in rep_contig.planned[0].entry.description()

    # Day mode: all PROJ-1 entries merge (5+10+15 = 30m)
    rep_day = analyze_day(entries, "2026-09-24", round_minutes=15, consolidate="day")
    tickets_day = [p.entry.ticket for p in rep_day.planned]
    assert tickets_day == ["PROJ-1", "PROJ-2"]
    assert rep_day.planned[0].rounded_minutes == 30


def test_f4_fixed_daily_blocks():
    from tempo_log.journal_analyzer import parse_fixed_blocks

    blocks = parse_fixed_blocks("13:00-14:00@LUNCH-1:Lunch;17:00-17:30:Wrapup")
    assert len(blocks) == 2
    assert blocks[0].start == "13:00" and blocks[0].end == "14:00" and blocks[0].ticket == "LUNCH-1" and blocks[0].title == "Lunch"
    assert blocks[1].start == "17:00" and blocks[1].end == "17:30" and blocks[1].ticket is None and blocks[1].title == "Wrapup"

    content = """
## 2026-09-24 12:30 UTC — PROJ-1: work
Time estimate: 1h | Ticket: PROJ-1 [id:1]
"""
    entries = parse_journal(content)
    # Sequential layout must skip fixed lunch block (13:00-14:00)
    rep = analyze_day(entries, "2026-09-24", sequential=True, fixed_blocks=blocks, with_fixed_blocks=True)
    # PROJ-1 starts 12:30, 1h ends 13:30 which overlaps 13:00-14:00; sequential layout shifts or reserves
    assert any("Lunch (13:00-14:00) reserved" in info for info in rep.day_info)
    # with_fixed_blocks added Lunch as a loggable entry
    assert any(p.entry.title == "Lunch" for p in rep.planned)


def test_f5_meetings_first_class_and_attended_no():
    content = """
## 2026-09-24 10:00 UTC — Meeting: Team Standup
Time: 10:00–10:30 UTC (30m)

- Reviewed sprint board

## 2026-09-24 14:00 UTC — Meeting: Optional Sync
Time: 14:00–14:30 UTC (30m)
Attended: no

- Skipped due to client demo
"""
    entries = parse_journal(content, meeting_prefix="Meeting:")
    assert entries[0].is_meeting
    assert entries[0].attended is True
    assert entries[1].is_meeting
    assert entries[1].attended is False

    rep = analyze_day(entries, "2026-09-24", meeting_issue="MEET-100")
    by_title = {p.entry.title: p for p in rep.planned}
    # Meeting defaults to meeting_issue
    assert by_title["Meeting: Team Standup"].entry.ticket == "MEET-100"
    assert by_title["Meeting: Team Standup"].status in ("READY", "BLOCKED")
    # Unattended meeting is marked SKIP
    assert by_title["Meeting: Optional Sync"].status == "SKIP"
    assert any("Meeting not attended (skipped)" in n for n in by_title["Meeting: Optional Sync"].notes)


def test_f8_overlap_checks_after_rounding():
    content = """
## 2026-09-24 09:00 UTC — PROJ-1: task 1
Time estimate: 20m | Ticket: PROJ-1 [id:1]
Time: 09:00-09:20 UTC

## 2026-09-24 09:15 UTC — PROJ-2: task 2
Time estimate: 20m | Ticket: PROJ-2 [id:2]
Time: 09:15-09:35 UTC
"""
    entries = parse_journal(content)
    # Without allow_overlap, overlap between rounded 09:00-09:30 and 09:15-09:45 blocks
    rep_blocked = analyze_day(entries, "2026-09-24", allow_overlap=False)
    assert rep_blocked.planned[0].status == "BLOCKED"
    assert any("Overlaps" in p for p in rep_blocked.planned[0].problems)

    # With allow_overlap, warns but remains READY
    rep_allowed = analyze_day(entries, "2026-09-24", allow_overlap=True)
    assert rep_allowed.planned[0].status == "READY"
    assert any("Overlap" in w for w in rep_allowed.day_warnings)


def test_f2_skip_what_is_already_logged():
    content = """
## 2026-09-24 09:00 UTC — PROJ-1: task 1
Time estimate: 30m | Ticket: PROJ-1 [id:1001]
Time: 09:00-09:30 UTC

## 2026-09-24 10:00 UTC — PROJ-2: task 2
Time estimate: 45m | Ticket: PROJ-2 [id:1002]
Time: 10:00-10:45 UTC
"""
    existing_worklogs = [
        {
            "id": 9999,
            "tempoWorklogId": 9999,
            "issue": {"id": 1001, "key": "PROJ-1"},
            "startDate": "2026-09-24",
            "startTime": "09:00:00",
            "timeSpentSeconds": 1800,
        },
        {
            "id": 8888,
            "tempoWorklogId": 8888,
            "issue": {"id": 5005, "key": "EXTERNAL-1"},
            "startDate": "2026-09-24",
            "startTime": "15:00:00",
            "timeSpentSeconds": 3600,
        },
    ]
    entries = parse_journal(content)
    report = analyze_day(entries, "2026-09-24", existing_worklogs=existing_worklogs)

    # PROJ-1 matches existing worklog #9999 -> LOGGED
    by_ticket = {p.entry.ticket: p for p in report.planned}
    assert by_ticket["PROJ-1"].status == "LOGGED (#9999)"
    assert by_ticket["PROJ-1"].is_logged is True
    assert by_ticket["PROJ-1"] not in report.ready

    # PROJ-2 is not in Tempo -> READY
    assert by_ticket["PROJ-2"].status == "READY"
    assert by_ticket["PROJ-2"] in report.ready

    # Unmatched Tempo worklog #8888 listed in day_info
    assert any("In Tempo, not in journal: #8888" in info for info in report.day_info)


def test_f1_submit_from_analyze(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from tempo_log.commands.analyze_cmd import run_analyze

    journal = tmp_path / "journal.md"
    journal.write_text(
        """
## 2026-09-24 09:00 UTC — PROJ-1: new work
Time estimate: 30m | Ticket: PROJ-1 [id:1001]
- Added feature
""",
        encoding="utf-8",
    )
    mock_service = MagicMock()
    mock_service.default_account_id = "acc123"
    mock_service.jira_client = None
    mock_service.list_time.return_value = []
    mock_service.batch_log.return_value = (1, 0, [])

    args = build_parser().parse_args(
        ["analyze", str(journal), "-d", "2026-09-24", "--submit", "--yes"]
    )
    rc = run_analyze(args, mock_service)
    assert rc == 0
    assert mock_service.batch_log.called
    call_args = mock_service.batch_log.call_args[0][0]
    assert len(call_args) == 1
    assert call_args[0]["issue_id"] == 1001


def test_f9_f10_plugins_and_ticket_mapping(tmp_path):
    from tempo_log.plugins import Candidate, MeetingCandidate, TicketMapper, suggest_tickets, find_meetings

    map_file = tmp_path / "ticket-map.toml"
    map_file.write_text(
        """
[mappings]
"onboarding" = "PROJ-50"
"login" = "PROJ-1"
""",
        encoding="utf-8",
    )
    mapper = TicketMapper.load(map_file)
    assert mapper.match("Fix onboarding screen bug") == "PROJ-50"
    assert mapper.match("Update login page button") == "PROJ-1"
    assert mapper.match("Database migration") is None

    suggestions = suggest_tickets("Working on the onboarding flow", mapper=mapper)
    assert len(suggestions) == 1
    assert suggestions[0].ticket == "PROJ-50"

    meetings = find_meetings("2026-09-24")
    assert isinstance(meetings, list)
