"""Tests for `tempo-log day-report` CLI command."""

from pathlib import Path
from tempo_log.cli import build_parser, run

SAMPLE_JOURNAL = """## 2026-11-02 Morning
Time: 09:00-10:00 (1h) | Ticket: PROJ-1
- Task A

## 2026-11-02 Afternoon
Time: 11:00-12:00 (1h) | Ticket: PROJ-2
- Task B
"""


def test_day_report_cli_detects_gap(tmp_path: Path, capsys):
    f = tmp_path / "journal.md"
    f.write_text(SAMPLE_JOURNAL, encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(["day-report", "--file", str(f), "--date", "2026-11-02"])
    res = run(args)

    assert res == 0
    captured = capsys.readouterr().out
    assert "Day Audit Report for 2026-11-02" in captured
    assert "Gap: 10:00-11:00 (60m)" in captured
    assert "Total: 2h across 2 entries" in captured
