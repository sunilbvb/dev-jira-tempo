"""Journal abstractions for storing local records of created worklogs."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_JOURNAL_PATH = Path.home() / ".tempo-log" / "journal.jsonl"
DEFAULT_SQLITE_PATH = Path.home() / ".tempo-log" / "audit.db"


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

    def get_recent_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        """Read recent entries from file."""
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").strip().splitlines()
            entries: list[dict[str, Any]] = []
            for line in lines[-limit:]:
                if line.strip():
                    entries.append(json.loads(line))
            return entries
        except Exception:
            return []


class SQLiteJournal(BaseJournal):
    """SQLite-based journal supporting relational queries, summaries, and exports."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DEFAULT_SQLITE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    CURRENT_SCHEMA_VERSION = 1

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
                """
            )
            cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            row = cursor.fetchone()
            current_ver = row["version"] if row else 0

            if current_ver == 0:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS worklogs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tempo_worklog_id INTEGER,
                        issue_id INTEGER,
                        issue_key TEXT,
                        account_id TEXT,
                        hours REAL,
                        start_date TEXT,
                        start_time TEXT,
                        description TEXT,
                        logged_at TEXT
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON worklogs(start_date)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_issue ON worklogs(issue_id)")
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (self.CURRENT_SCHEMA_VERSION,))
                current_ver = self.CURRENT_SCHEMA_VERSION

            self._run_migrations(conn, current_ver)

    def _run_migrations(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Run incremental schema migrations if current DB version < CURRENT_SCHEMA_VERSION."""
        # Future migration steps can be added here (e.g., if from_version < 2: ...)
        pass

    def append(self, record: dict[str, Any]) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO worklogs (
                    tempo_worklog_id, issue_id, issue_key, account_id,
                    hours, start_date, start_time, description, logged_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("tempoWorklogId"),
                    record.get("issueId"),
                    record.get("issueKey"),
                    record.get("accountId"),
                    record.get("hours", 0.0),
                    record.get("startDate"),
                    record.get("startTime"),
                    record.get("description", ""),
                    record.get("loggedAt") or datetime.now(timezone.utc).isoformat(),
                ),
            )

    def query(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        issue_key: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query worklogs with optional date range and issue filter."""
        clauses = []
        params = []
        if from_date:
            clauses.append("start_date >= ?")
            params.append(from_date)
        if to_date:
            clauses.append("start_date <= ?")
            params.append(to_date)
        if issue_key:
            clauses.append("issue_key = ?")
            params.append(issue_key)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM worklogs{where} ORDER BY start_date DESC, start_time DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def weekly_summary(
        self, from_date: str | None = None, to_date: str | None = None
    ) -> dict[str, Any]:
        """Aggregate total hours grouped by day and issue."""
        clauses = []
        params = []
        if from_date:
            clauses.append("start_date >= ?")
            params.append(from_date)
        if to_date:
            clauses.append("start_date <= ?")
            params.append(to_date)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._get_connection() as conn:
            total_cursor = conn.execute(f"SELECT SUM(hours) as total_hours, COUNT(*) as count FROM worklogs{where}", params)
            total_row = total_cursor.fetchone()
            total_hours = total_row["total_hours"] or 0.0
            count = total_row["count"] or 0

            days_cursor = conn.execute(
                f"SELECT start_date, SUM(hours) as day_hours FROM worklogs{where} GROUP BY start_date ORDER BY start_date",
                params,
            )
            daily_totals = {row["start_date"]: row["day_hours"] for row in days_cursor.fetchall()}

            issues_cursor = conn.execute(
                f"SELECT COALESCE(issue_key, CAST(issue_id AS TEXT)) as issue, SUM(hours) as issue_hours FROM worklogs{where} GROUP BY issue ORDER BY issue_hours DESC",
                params,
            )
            issue_totals = {row["issue"]: row["issue_hours"] for row in issues_cursor.fetchall()}

        return {
            "total_hours": round(total_hours, 2),
            "total_entries": count,
            "daily_totals": daily_totals,
            "issue_totals": issue_totals,
        }

    def export_csv(self, filepath: Path | str) -> int:
        """Export all recorded worklogs to a CSV file."""
        target = Path(filepath)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM worklogs ORDER BY start_date ASC")
            rows = cursor.fetchall()
            headers = [
                "id",
                "tempo_worklog_id",
                "issue_id",
                "issue_key",
                "account_id",
                "hours",
                "start_date",
                "start_time",
                "description",
                "logged_at",
            ] if not rows else rows[0].keys()

            with target.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow(tuple(row))
            return len(rows)


class MemoryJournal(BaseJournal):
    """In-memory journal for testing or transient environments."""

    def __init__(self):
        self.records: list[dict[str, Any]] = []

    def append(self, record: dict[str, Any]) -> None:
        self.records.append(record)


class DualJournal(BaseJournal):
    """Logs to both file journal (JSONL) and SQLite audit database."""

    def __init__(
        self,
        file_path: Path | str | None = None,
        sqlite_path: Path | str | None = None,
    ):
        self.file_journal = FileJournal(file_path)
        self.sqlite_journal = SQLiteJournal(sqlite_path)

    def append(self, record: dict[str, Any]) -> None:
        try:
            self.file_journal.append(record)
        except Exception:
            pass
        try:
            self.sqlite_journal.append(record)
        except Exception:
            pass


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
