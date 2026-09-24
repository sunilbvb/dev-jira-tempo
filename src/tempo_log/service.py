"""High-level service facade for managing Tempo and Jira worklogs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .config import JiraConfig, Settings
from .exceptions import JiraClientError, TempoClientError, ValidationError
from .jira_client import JiraClient
from .journal import BaseJournal, FileJournal
from .tempo_client import TempoClient, Worklog

logger = logging.getLogger(__name__)


class TempoService:
    """Core facade combining Tempo, Jira, and Journaling for apps and CLI."""

    def __init__(
        self,
        tempo_token: str,
        jira_config: JiraConfig | None = None,
        default_account_id: str | None = None,
        journal: BaseJournal | None = None,
        tempo_client: TempoClient | None = None,
        jira_client: JiraClient | None = None,
    ):
        self.tempo_client = tempo_client or TempoClient(tempo_token)
        self.jira_client = jira_client or (JiraClient(jira_config) if jira_config else None)
        self.default_account_id = default_account_id
        self.journal = journal if journal is not None else FileJournal()

    @classmethod
    def from_settings(
        cls, settings: Settings, journal: BaseJournal | None = None
    ) -> TempoService:
        """Create a service instance from a Settings object."""
        return cls(
            tempo_token=settings.tempo_api_token,
            jira_config=settings.jira,
            default_account_id=settings.default_account_id,
            journal=journal,
        )

    def resolve_issue_and_account(
        self,
        issue: str | None = None,
        issue_id: int | None = None,
        account_id: str | None = None,
    ) -> tuple[int, str]:
        """Resolve numeric issue ID and account ID from either explicit inputs or Jira lookup."""
        resolved_account_id = account_id or self.default_account_id

        if issue_id is None:
            if not issue:
                raise ValidationError("Must provide either issue key (e.g. 'PROJ-123') or numeric issue_id.")
            if not self.jira_client:
                raise ValidationError(
                    "Jira credentials required to resolve issue key. Provide issue_id or configure Jira."
                )
            issue_id = self.jira_client.resolve_issue_id(issue)

        if resolved_account_id is None:
            if not self.jira_client:
                raise ValidationError(
                    "Must provide account_id or configure Jira to auto-detect author."
                )
            resolved_account_id = self.jira_client.get_current_account_id()

        return issue_id, resolved_account_id

    def log_time(
        self,
        hours: float,
        issue: str | None = None,
        issue_id: int | None = None,
        account_id: str | None = None,
        date: str | None = None,
        time: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Log work hours, record in journal, and return Tempo result."""
        if hours <= 0:
            raise ValidationError(f"Hours must be a positive number, got {hours}")

        resolved_issue_id, resolved_account_id = self.resolve_issue_and_account(
            issue=issue, issue_id=issue_id, account_id=account_id
        )

        start_date = date or datetime.now().strftime("%Y-%m-%d")
        start_time = time or datetime.now().strftime("%H:%M:%S")

        worklog = Worklog(
            issue_id=resolved_issue_id,
            account_id=resolved_account_id,
            hours=hours,
            start_date=start_date,
            start_time=start_time,
            description=description,
        )

        result = self.tempo_client.create_worklog(worklog)
        worklog_id = result.get("tempoWorklogId")

        record = {
            "tempoWorklogId": worklog_id,
            "issueId": resolved_issue_id,
            "accountId": resolved_account_id,
            "hours": hours,
            "startDate": start_date,
            "startTime": start_time,
            "description": description,
            "loggedAt": datetime.now().astimezone().isoformat(),
        }
        self.journal.append(record)
        return result

    def list_time(
        self,
        account_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List worklogs for account within an optional date range."""
        target_account_id = account_id or self.default_account_id
        if not target_account_id:
            raise ValidationError("Provide account_id or set JIRA_ACCOUNT_ID.")

        return self.tempo_client.list_worklogs(
            account_id=target_account_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )

    def update_time(
        self,
        worklog_id: int,
        hours: float | None = None,
        description: str | None = None,
        date: str | None = None,
        time: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing Tempo worklog."""
        return self.tempo_client.update_worklog(
            worklog_id=worklog_id,
            hours=hours,
            description=description,
            start_date=date,
            start_time=time,
        )

    def batch_log(
        self,
        entries: list[dict[str, Any]],
        stop_on_error: bool = False,
    ) -> tuple[int, int, list[str]]:
        """Process a list of worklog entries. Returns (succeeded, failed, failures)."""
        succeeded = 0
        failed = 0
        failures: list[str] = []

        for i, entry in enumerate(entries):
            label = entry.get("issue") or entry.get("issue_id") or f"entry #{i}"
            try:
                hours = float(entry["hours"])
                self.log_time(
                    hours=hours,
                    issue=entry.get("issue"),
                    issue_id=entry.get("issue_id"),
                    account_id=entry.get("account_id"),
                    date=entry.get("date"),
                    time=entry.get("time"),
                    description=entry.get("description", ""),
                )
                succeeded += 1
            except Exception as exc:
                failed += 1
                failures.append(f"{label}: {exc}")
                logger.error("Failed to submit %s: %s", label, exc)
                if stop_on_error:
                    break

        return succeeded, failed, failures

    def check_health(self) -> dict[str, Any]:
        """Verify connectivity to Tempo and Jira."""
        report: dict[str, Any] = {
            "tempo_ok": False,
            "tempo_message": "",
            "jira_ok": None,
            "jira_account_id": None,
            "jira_message": "",
            "default_account_id": self.default_account_id,
        }

        try:
            self.tempo_client.list_worklogs(limit=1)
            report["tempo_ok"] = True
            report["tempo_message"] = "TEMPO_API_TOKEN authenticates successfully."
        except TempoClientError as exc:
            report["tempo_message"] = str(exc)

        if self.jira_client:
            try:
                acc_id = self.jira_client.get_current_account_id()
                report["jira_ok"] = True
                report["jira_account_id"] = acc_id
                report["jira_message"] = f"Authenticated as accountId={acc_id}"
            except JiraClientError as exc:
                report["jira_ok"] = False
                report["jira_message"] = str(exc)
        else:
            report["jira_message"] = "Jira not configured."

        return report
