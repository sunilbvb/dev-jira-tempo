"""Local record of worklogs this tool has created, for later lookup/updates
without needing to re-query Tempo."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_JOURNAL_PATH = Path.home() / ".tempo-log" / "journal.jsonl"


def journal_path() -> Path:
    override = os.environ.get("TEMPO_LOG_JOURNAL")
    return Path(override) if override else DEFAULT_JOURNAL_PATH


def append_entry(
    tempo_worklog_id: int,
    issue_id: int,
    account_id: str,
    hours: float,
    start_date: str,
    start_time: str,
    description: str,
) -> None:
    path = journal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "tempoWorklogId": tempo_worklog_id,
        "issueId": issue_id,
        "accountId": account_id,
        "hours": hours,
        "startDate": start_date,
        "startTime": start_time,
        "description": description,
        "loggedAt": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")
