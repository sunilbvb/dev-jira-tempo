"""Tests for TempoService and pluggable journals."""

from unittest.mock import MagicMock
import pytest
from tempo_log.config import JiraConfig, Settings
from tempo_log.exceptions import ValidationError, TempoClientError, JiraClientError
from tempo_log.journal import MemoryJournal, NullJournal
from tempo_log.service import TempoService


def test_service_log_time_success():
    mock_tempo = MagicMock()
    mock_tempo.create_worklog.return_value = {"tempoWorklogId": 1234}

    journal = MemoryJournal()
    service = TempoService(
        tempo_token="fake-token",
        default_account_id="acc-default",
        journal=journal,
        tempo_client=mock_tempo,
    )

    res = service.log_time(
        hours=2.0,
        issue_id=999,
        description="Feature work",
        date="2026-09-24",
        time="10:00:00",
    )

    assert res == {"tempoWorklogId": 1234}
    assert len(journal.records) == 1
    rec = journal.records[0]
    assert rec["tempoWorklogId"] == 1234
    assert rec["issueId"] == 999
    assert rec["accountId"] == "acc-default"
    assert rec["hours"] == 2.0


def test_service_log_time_invalid_hours():
    service = TempoService(tempo_token="fake-token")
    with pytest.raises(ValidationError, match="Hours must be a positive number"):
        service.log_time(hours=-1.0, issue_id=999)


def test_service_resolve_issue_via_jira():
    mock_jira = MagicMock()
    mock_jira.resolve_issue_id.return_value = 888
    mock_jira.get_current_account_id.return_value = "acc-jira"

    mock_tempo = MagicMock()
    mock_tempo.create_worklog.return_value = {"tempoWorklogId": 555}

    service = TempoService(
        tempo_token="tok",
        jira_client=mock_jira,
        journal=NullJournal(),
        tempo_client=mock_tempo,
    )

    issue_id, account_id = service.resolve_issue_and_account(issue="PROJ-77")
    assert issue_id == 888
    assert account_id == "acc-jira"
    mock_jira.resolve_issue_id.assert_called_with("PROJ-77")


def test_service_resolve_issue_missing_jira():
    service = TempoService(tempo_token="tok", default_account_id="acc-1")
    with pytest.raises(ValidationError, match="Jira credentials required to resolve issue key"):
        service.resolve_issue_and_account(issue="PROJ-1")


def test_service_batch_log():
    mock_tempo = MagicMock()
    mock_tempo.create_worklog.side_effect = [
        {"tempoWorklogId": 1},
        TempoClientError("API down"),
    ]

    journal = MemoryJournal()
    service = TempoService(
        tempo_token="tok",
        default_account_id="acc-1",
        journal=journal,
        tempo_client=mock_tempo,
    )

    entries = [
        {"issue_id": 100, "hours": 1.0, "date": "2026-09-24"},
        {"issue_id": 200, "hours": 2.0, "date": "2026-09-24"},
    ]

    succeeded, failed, failures = service.batch_log(entries)
    assert succeeded == 1
    assert failed == 1
    assert len(failures) == 1
    assert len(journal.records) == 1


def test_service_check_health():
    mock_tempo = MagicMock()
    mock_tempo.list_worklogs.return_value = {}

    mock_jira = MagicMock()
    mock_jira.get_current_account_id.return_value = "acc-user"

    service = TempoService(
        tempo_token="tok",
        default_account_id="acc-user",
        tempo_client=mock_tempo,
        jira_client=mock_jira,
    )

    report = service.check_health()
    assert report["tempo_ok"] is True
    assert report["jira_ok"] is True
    assert report["jira_account_id"] == "acc-user"


def test_service_from_settings():
    settings = Settings(
        tempo_api_token="tempo-tok",
        jira=JiraConfig("https://jira.com", "u@e.com", "jtok"),
        default_account_id="acc-123",
    )
    service = TempoService.from_settings(settings, journal=NullJournal())
    assert service.default_account_id == "acc-123"
    assert service.jira_client is not None
    assert isinstance(service.journal, NullJournal)
