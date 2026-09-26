import csv
from pathlib import Path
from tempo_log.journal import DualJournal, FileJournal, SQLiteJournal


def test_sqlite_journal_init_and_append(tmp_path: Path):
    db_file = tmp_path / "test_audit.db"
    journal = SQLiteJournal(path=db_file)

    record = {
        "tempoWorklogId": 12345,
        "issueId": 101,
        "issueKey": "PROJ-101",
        "accountId": "acc-123",
        "hours": 2.5,
        "startDate": "2026-09-26",
        "startTime": "09:00:00",
        "description": "Implemented feature A",
    }
    journal.append(record)

    entries = journal.query()
    assert len(entries) == 1
    assert entries[0]["tempo_worklog_id"] == 12345
    assert entries[0]["issue_key"] == "PROJ-101"
    assert entries[0]["hours"] == 2.5


def test_sqlite_journal_query_filtering(tmp_path: Path):
    db_file = tmp_path / "test_audit.db"
    journal = SQLiteJournal(path=db_file)

    journal.append({
        "tempoWorklogId": 1,
        "issueId": 101,
        "issueKey": "PROJ-101",
        "hours": 1.0,
        "startDate": "2026-09-20",
    })
    journal.append({
        "tempoWorklogId": 2,
        "issueId": 102,
        "issueKey": "PROJ-102",
        "hours": 3.0,
        "startDate": "2026-09-25",
    })

    # Filter by issue
    p101 = journal.query(issue_key="PROJ-101")
    assert len(p101) == 1
    assert p101[0]["issue_key"] == "PROJ-101"

    # Filter by date range
    range_res = journal.query(from_date="2026-09-21", to_date="2026-09-26")
    assert len(range_res) == 1
    assert range_res[0]["issue_key"] == "PROJ-102"


def test_sqlite_journal_weekly_summary(tmp_path: Path):
    db_file = tmp_path / "test_audit.db"
    journal = SQLiteJournal(path=db_file)

    journal.append({
        "tempoWorklogId": 1,
        "issueKey": "PROJ-101",
        "hours": 2.5,
        "startDate": "2026-09-25",
    })
    journal.append({
        "tempoWorklogId": 2,
        "issueKey": "PROJ-101",
        "hours": 1.5,
        "startDate": "2026-09-25",
    })
    journal.append({
        "tempoWorklogId": 3,
        "issueKey": "PROJ-102",
        "hours": 4.0,
        "startDate": "2026-09-26",
    })

    summary = journal.weekly_summary(from_date="2026-09-20", to_date="2026-09-27")
    assert summary["total_hours"] == 8.0
    assert summary["total_entries"] == 3
    assert summary["daily_totals"]["2026-09-25"] == 4.0
    assert summary["daily_totals"]["2026-09-26"] == 4.0
    assert summary["issue_totals"]["PROJ-101"] == 4.0
    assert summary["issue_totals"]["PROJ-102"] == 4.0


def test_sqlite_journal_export_csv(tmp_path: Path):
    db_file = tmp_path / "test_audit.db"
    csv_file = tmp_path / "export.csv"
    journal = SQLiteJournal(path=db_file)

    journal.append({
        "tempoWorklogId": 1,
        "issueKey": "PROJ-101",
        "hours": 2.0,
        "startDate": "2026-09-26",
        "description": "Testing CSV export",
    })

    count = journal.export_csv(csv_file)
    assert count == 1
    assert csv_file.exists()

    with csv_file.open(encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert len(reader) == 2  # header + 1 row
        assert "tempo_worklog_id" in reader[0]
        assert "PROJ-101" in reader[1]


def test_dual_journal(tmp_path: Path):
    jsonl_file = tmp_path / "journal.jsonl"
    db_file = tmp_path / "audit.db"
    dual = DualJournal(file_path=jsonl_file, sqlite_path=db_file)

    record = {
        "tempoWorklogId": 999,
        "issueKey": "PROJ-999",
        "hours": 1.5,
        "startDate": "2026-09-26",
    }
    dual.append(record)

    file_entries = FileJournal(jsonl_file).get_recent_entries()
    assert len(file_entries) == 1
    assert file_entries[0]["tempoWorklogId"] == 999

    sqlite_entries = SQLiteJournal(db_file).query()
    assert len(sqlite_entries) == 1
    assert sqlite_entries[0]["tempo_worklog_id"] == 999
