"""Tests for CLI entry points and command execution."""

import json
from unittest import mock
import pytest
from tempo_log.cli import build_parser, run_create, run_doctor, run_batch, run_list, run_update
from tempo_log.config import Settings, JiraConfig


def test_parser_create():
    parser = build_parser()
    args = parser.parse_args(["create", "--issue", "DEV-1", "--hours", "2"])
    assert args.command == "create"
    assert args.issue == "DEV-1"
    assert args.hours == 2.0


def test_parser_mutually_exclusive_issue():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["create", "--issue", "DEV-1", "--issue-id", "123", "--hours", "2"])


def test_run_create_invalid_hours():
    parser = build_parser()
    args = parser.parse_args(["create", "--issue-id", "100", "--hours", "0", "--account-id", "acc-1"])
    settings = Settings(tempo_api_token="dummy", jira=None, default_account_id=None)
    assert run_create(args, settings) == 1


@mock.patch("tempo_log.cli.TempoClient")
@mock.patch("tempo_log.cli.append_entry")
def test_run_create_success(mock_append, mock_tempo_class):
    mock_tempo = mock.MagicMock()
    mock_tempo.create_worklog.return_value = {"tempoWorklogId": 777}
    mock_tempo_class.return_value = mock_tempo

    parser = build_parser()
    args = parser.parse_args(["create", "--issue-id", "100", "--hours", "3.5", "--account-id", "acc-1"])
    settings = Settings(tempo_api_token="dummy", jira=None, default_account_id=None)

    exit_code = run_create(args, settings)
    assert exit_code == 0
    mock_append.assert_called_once()
    assert mock_append.call_args[1]["tempo_worklog_id"] == 777
    assert mock_append.call_args[1]["hours"] == 3.5


@mock.patch("tempo_log.cli.TempoClient")
@mock.patch("tempo_log.cli.JiraClient")
def test_run_doctor_all_ok(mock_jira_class, mock_tempo_class, capsys):
    mock_tempo = mock.MagicMock()
    mock_tempo_class.return_value = mock_tempo

    mock_jira = mock.MagicMock()
    mock_jira.get_current_account_id.return_value = "acc-999"
    mock_jira_class.return_value = mock_jira

    jira_cfg = JiraConfig("https://jira.example.com", "u@e.com", "token")
    settings = Settings(tempo_api_token="tok", jira=jira_cfg, default_account_id="acc-999")

    code = run_doctor(settings)
    assert code == 0
    out = capsys.readouterr().out
    assert "Tempo: OK" in out
    assert "Jira: OK (authenticated as accountId=acc-999)" in out


@mock.patch("tempo_log.cli.TempoClient")
def test_run_batch_success(mock_tempo_class, tmp_path):
    mock_tempo = mock.MagicMock()
    mock_tempo.create_worklog.return_value = {"tempoWorklogId": 123}
    mock_tempo_class.return_value = mock_tempo

    batch_file = tmp_path / "batch.json"
    batch_data = [
        {
            "issue_id": 101,
            "hours": 1.5,
            "date": "2026-09-24",
            "account_id": "acc-1",
            "description": "Task 1",
        }
    ]
    batch_file.write_text(json.dumps(batch_data))

    parser = build_parser()
    args = parser.parse_args(["batch", str(batch_file)])
    settings = Settings(tempo_api_token="tok", jira=None, default_account_id=None)

    code = run_batch(args, settings)
    assert code == 0
    mock_tempo.create_worklog.assert_called_once()
