"""Journal abstractions for storing local records of created worklogs."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_JOURNAL_PATH = Path.home() / ".tempo-log" / "journal.jsonl"


def journal_path() -> Path:
    """Return default or configured journal file path."""
    override = os.environ.get("TEMPO_LOG_JOURNAL")
    return Path(override) if override else DEFAULT_JOURNAL_PATH


class BaseJournal(ABC):
    """Abstract base class for worklog journaling."""

    @abstractmethod
    def append(self, record: dict[str, Any]) -> None:
        """Append a worklog record to the journal."""


class FileJournal(BaseJournal):
    """File-based journal appending JSONL records to disk."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else journal_path()

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


class MemoryJournal(BaseJournal):
    """In-memory journal for testing or transient environments."""

    def __init__(self):
        self.records: list[dict[str, Any]] = []

    def append(self, record: dict[str, Any]) -> None:
        self.records.append(record)


class NullJournal(BaseJournal):
    """No-op journal that discards audit records."""

    def append(self, record: dict[str, Any]) -> None:
        pass


def append_entry(
    tempo_worklog_id: int,
    issue_id: int,
    account_id: str,
    hours: float,
    start_date: str,
    start_time: str,
    description: str,
    path: Path | str | None = None,
) -> None:
    """Legacy helper: append an entry to the file journal."""
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
    FileJournal(path=path).append(record)
