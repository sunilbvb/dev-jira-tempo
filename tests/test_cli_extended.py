from pathlib import Path
from unittest import mock
import pytest
from tempo_log.cli import (
    build_parser,
    run_auth,
    run_completion,
    run_hook_command,
    run_start,
    run_status,
    run_stop,
    run_summary,
    run_tui,
)
from tempo_log.timer import get_active_timer, start_timer


def test_cli_timer_workflow(tmp_path: Path):
    timer_file = tmp_path / "active_timer.json"
    parser = build_parser()

    with mock.patch("tempo_log.timer.timer_path", return_value=timer_file):
        # 1. Start timer
        args_start = parser.parse_args(["start", "--issue", "PROJ-777", "--desc", "Unit testing"])
        assert run_start(args_start) == 0
        assert timer_file.exists()

        # 2. Check status
        assert run_status() == 0

        # 3. Discard timer
        args_stop_discard = parser.parse_args(["stop", "--discard"])
        assert run_stop(args_stop_discard) == 0
        assert not timer_file.exists()


def test_cli_stop_and_log(tmp_path: Path):
    timer_file = tmp_path / "active_timer.json"
    parser = build_parser()

    with mock.patch("tempo_log.timer.timer_path", return_value=timer_file):
        start_timer(issue="PROJ-888", description="Fixing bugs", path=timer_file)
        assert timer_file.exists()

        mock_service = mock.MagicMock()
        mock_service.log_time.return_value = {"tempoWorklogId": 9999}

        args_stop = parser.parse_args(["stop"])
        ret = run_stop(args_stop, target=mock_service)
        assert ret == 0
        assert not timer_file.exists()
        mock_service.log_time.assert_called_once()


def test_cli_summary(tmp_path: Path):
    parser = build_parser()
    args = parser.parse_args(["summary"])
    assert run_summary(args) == 0

    csv_out = tmp_path / "export.csv"
    args_export = parser.parse_args(["summary", "--export-csv", str(csv_out)])
    assert run_summary(args_export) == 0
    assert csv_out.exists()


def test_cli_tui_once():
    parser = build_parser()
    args = parser.parse_args(["tui", "--once"])
    assert run_tui(args) == 0


def test_cli_auth():
    parser = build_parser()
    args_status = parser.parse_args(["auth", "status"])
    assert run_auth(args_status) == 0

    with mock.patch("tempo_log.cli.set_credential") as mock_set:
        args_set = parser.parse_args(["auth", "set-token", "tempo", "my-secret-token"])
        assert run_auth(args_set) == 0
        mock_set.assert_called_once_with("TEMPO_API_TOKEN", "my-secret-token")


def test_cli_completion():
    parser = build_parser()
    args_bash = parser.parse_args(["completion", "--shell", "bash"])
    assert run_completion(args_bash) == 0

    args_issues = parser.parse_args(["completion", "--list-issues"])
    assert run_completion(args_issues) == 0


def test_cli_git_hook():
    parser = build_parser()
    args_check = parser.parse_args(["git-hook", "check", "PROJ-123: 1.5h - Test commit"])
    assert run_hook_command(args_check) == 0

    args_check_invalid = parser.parse_args(["git-hook", "check", "Just normal commit"])
    assert run_hook_command(args_check_invalid) == 1
