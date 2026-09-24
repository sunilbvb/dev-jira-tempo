"""Tests for local journal logging."""

import json
from pathlib import Path
from unittest import mock

from tempo_log.journal import append_entry, journal_path


def test_journal_path_env_override(tmp_path: Path):
    custom_path = str(tmp_path / "custom_journal.jsonl")
    with mock.patch.dict("os.environ", {"TEMPO_LOG_JOURNAL": custom_path}):
        assert journal_path() == Path(custom_path)


def test_append_entry(tmp_path: Path):
    target = tmp_path / "sub" / "journal.jsonl"
    with mock.patch.dict("os.environ", {"TEMPO_LOG_JOURNAL": str(target)}):
        append_entry(
            tempo_worklog_id=999,
            issue_id=101,
            account_id="acc-1",
            hours=2.5,
            start_date="2026-09-24",
            start_time="14:00:00",
            description="Testing journal",
        )

        assert target.exists()
        lines = target.read_text().strip().split("\n")
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["tempoWorklogId"] == 999
        assert record["issueId"] == 101
        assert record["accountId"] == "acc-1"
        assert record["hours"] == 2.5
        assert record["startDate"] == "2026-09-24"
        assert record["startTime"] == "14:00:00"
        assert record["description"] == "Testing journal"
        assert "loggedAt" in record
