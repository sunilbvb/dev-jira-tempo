"""Tests for CLI entry points and command execution."""

import json
from unittest import mock
import pytest
from tempo_log.cli import (
    build_parser,
    run_create,
    run_doctor,
    run_batch,
    run_list,
    run_update,
)
from tempo_log.config import Settings


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


def test_run_create_success():
    service = mock.MagicMock()
    service.resolve_issue_and_account.return_value = (100, "acc-1")
    service.log_time.return_value = {"tempoWorklogId": 777}

    parser = build_parser()
    args = parser.parse_args(["create", "--issue-id", "100", "--hours", "3.5", "--account-id", "acc-1"])

    exit_code = run_create(args, service)
    assert exit_code == 0
    service.log_time.assert_called_once_with(
        hours=3.5,
        issue_id=100,
        account_id="acc-1",
        date=args.date,
        time=args.time,
        description="",
    )


def test_run_doctor_all_ok(capsys):
    service = mock.MagicMock()
    service.check_health.return_value = {
        "tempo_ok": True,
        "tempo_message": "TEMPO_API_TOKEN authenticates.",
        "jira_ok": True,
        "jira_account_id": "acc-999",
        "jira_message": "authenticated as accountId=acc-999",
        "default_account_id": "acc-999",
    }

    code = run_doctor(service)
    assert code == 0
    out = capsys.readouterr().out
    assert "Tempo: OK" in out
    assert "Jira: OK (authenticated as accountId=acc-999)" in out


def test_run_batch_success(tmp_path):
    service = mock.MagicMock()
    service.batch_log.return_value = (1, 0, [])

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

    code = run_batch(args, service)
    assert code == 0
    service.batch_log.assert_called_once()


def test_run_list_success(capsys):
    service = mock.MagicMock()
    service.list_time.return_value = {
        "results": [
            {
                "tempoWorklogId": 12,
                "startDate": "2026-09-24",
                "startTime": "10:00:00",
                "issue": {"id": 99},
                "timeSpentSeconds": 7200,
                "description": "Work",
            }
        ],
        "metadata": {"count": 1},
    }
    parser = build_parser()
    args = parser.parse_args(["list", "--account-id", "acc-1"])
    assert run_list(args, service) == 0
    out = capsys.readouterr().out
    assert "12\t2026-09-24 10:00:00\tissue=99\t2.0h\tWork" in out


def test_run_update_success(capsys):
    service = mock.MagicMock()
    service.update_time.return_value = {"tempoWorklogId": 12}
    parser = build_parser()
    args = parser.parse_args(["update", "12", "--hours", "3.0"])
    assert run_update(args, service) == 0
    service.update_time.assert_called_once_with(
        12, hours=3.0, description=None, date=None, time=None
    )
