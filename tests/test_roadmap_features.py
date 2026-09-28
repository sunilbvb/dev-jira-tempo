"""Unit tests for roadmap features (configurable base URL, fallbacks, rounding, CLI from-worklog)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tempo_log.cli import build_parser, run
from tempo_log.config import Settings
from tempo_log.exceptions import ValidationError
from tempo_log.service import TempoService
from tempo_log.tempo_client import TempoClient


def test_tempo_client_configurable_base_url():
    session = MagicMock()
    client = TempoClient("token", session=session, base_url="https://tempo.custom.com/v4/")
    assert client.base_url == "https://tempo.custom.com/v4"

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"tempoWorklogId": 123}
    session.post.return_value = mock_resp

    from tempo_log.tempo_client import Worklog

    wl = Worklog(issue_id=1, account_id="acc1", hours=1.0, start_date="2026-09-24", start_time="10:00:00")
    client.create_worklog(wl)

    session.post.assert_called_once()
    assert session.post.call_args[0][0] == "https://tempo.custom.com/v4/worklogs"


def test_fallback_issues_resolution():
    settings = Settings(
        tempo_api_token="token",
        tempo_default_issue="PROJ-DEFAULT",
        tempo_meeting_issue="PROJ-MEETING",
    )
    mock_jira = MagicMock()
    mock_jira.resolve_issue_id.side_effect = lambda k: 100 if k == "PROJ-DEFAULT" else 200

    service = TempoService(
        tempo_token="token",
        jira_client=mock_jira,
        default_account_id="acc-1",
        settings=settings,
    )

    # Test 'default' fallback
    issue_id, acc_id = service.resolve_issue_and_account(issue="default")
    assert issue_id == 100

    # Test 'meeting' fallback
    issue_id, acc_id = service.resolve_issue_and_account(issue="meeting")
    assert issue_id == 200

    # Test missing fallback raises ValidationError
    service_no_fallback = TempoService(tempo_token="token", jira_client=mock_jira)
    with pytest.raises(ValidationError, match="TEMPO_DEFAULT_ISSUE is not configured"):
        service_no_fallback.resolve_issue_and_account(issue="default")


def test_cli_from_worklog_preview(tmp_path, capsys, monkeypatch):
    worklog_file = tmp_path / "worklog.md"
    worklog_file.write_text(
        """
## 2026-09-24

Tempo: 10001 | 13:00-14:00
- Work description
""",
        encoding="utf-8",
    )

    parser = build_parser()
    args = parser.parse_args(["from-worklog", str(worklog_file), "--from", "2026-09-24"])

    service = MagicMock()
    service.settings = Settings(tempo_api_token="token")
    service.resolve_issue_and_account.return_value = (10001, "acc-1")

    monkeypatch.setattr("tempo_log.cli.load_settings", lambda: Settings(tempo_api_token="token"))
    monkeypatch.setattr("tempo_log.cli.TempoService.from_settings", lambda s: service)

    exit_code = run(args)
    assert exit_code == 0

    captured = capsys.readouterr().out
    assert "Worklog Import Preview" in captured
    assert "10001" in captured
    assert "Preview mode complete" in captured


def test_cli_from_worklog_submit_strict_warnings(tmp_path):
    worklog_file = tmp_path / "worklog.md"
    worklog_file.write_text(
        """
## 2026-09-24

Tempo: 10001 | 13:00-14:00
- Entry 1

Tempo: 10002 | 13:30-14:30
- Entry 2 overlap
""",
        encoding="utf-8",
    )

    parser = build_parser()
    args = parser.parse_args(["from-worklog", str(worklog_file), "--submit", "--strict"])

    service = MagicMock()
    service.settings = Settings(tempo_api_token="token")
    service.resolve_issue_and_account.side_effect = lambda issue: (int(issue), "acc-1")

    # Routing to run_from_worklog directly via CLI module helper
    from tempo_log.cli import run_from_worklog

    exit_code = run_from_worklog(args, target=service)
    assert exit_code == 1  # Blocked by strict due to overlap warning
