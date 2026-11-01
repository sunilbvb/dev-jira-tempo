"""Tests for `tempo-log schedule` CLI command."""

from pathlib import Path
from tempo_log.cli import build_parser, run

SAMPLE_WORKLOG = """## 2026-11-02 Core Backend
Time: 09:00-11:00 (2h) | Ticket: PROJ-101
- Wrote API endpoints

## 2026-11-02 Frontend UI
Time: 11:30-13:30 (2h) | Ticket: PROJ-102
- Built layout
"""


def test_schedule_cli_execution(tmp_path: Path, capsys):
    f = tmp_path / "worklog.md"
    f.write_text(SAMPLE_WORKLOG, encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(["schedule", str(f), "--date", "2026-11-02", "--start", "09:00"])
    res = run(args)

    assert res == 0
    captured = capsys.readouterr().out
    assert "Planned Day Schedule for 2026-11-02" in captured
    assert "PROJ-101" in captured
    assert "PROJ-102" in captured
    assert "Total: 4.00h" in captured


def test_schedule_cli_json(tmp_path: Path, capsys):
    f = tmp_path / "worklog.md"
    f.write_text(SAMPLE_WORKLOG, encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(["schedule", str(f), "--date", "2026-11-02", "--json"])
    res = run(args)

    assert res == 0
    captured = capsys.readouterr().out
    assert '"total_hours": 4.0' in captured
    assert '"issue": "PROJ-101"' in captured
