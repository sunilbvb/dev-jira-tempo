from pathlib import Path
from unittest import mock
from tempo_log.git_hook import (
    install_hook,
    parse_commit_message,
    run_git_hook,
    uninstall_hook,
)


def test_parse_commit_message_colon_syntax():
    msg = "PROJ-123: 1.5h - Fix login page redirect issue"
    info = parse_commit_message(msg)
    assert info is not None
    assert info.issue_key == "PROJ-123"
    assert info.hours == 1.5
    assert "Fix login page redirect issue" in info.description


def test_parse_commit_message_paren_syntax():
    msg = "PROJ-456 (2h 30m) Implemented user dashboard"
    info = parse_commit_message(msg)
    assert info is not None
    assert info.issue_key == "PROJ-456"
    assert info.hours == 2.5
    assert "Implemented user dashboard" in info.description


def test_parse_commit_message_time_tag():
    msg = "PROJ-789 Update database migrations #time 45m"
    info = parse_commit_message(msg)
    assert info is not None
    assert info.issue_key == "PROJ-789"
    assert info.hours == 0.75
    assert "Update database migrations" in info.description


def test_parse_commit_message_no_match():
    assert parse_commit_message("Refactored code structure") is None
    assert parse_commit_message("PROJ-123 without any duration") is None
    assert parse_commit_message("") is None


def test_install_and_uninstall_hook(tmp_path: Path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    hook_file = install_hook(repo_path=tmp_path)
    assert hook_file.exists()
    content = hook_file.read_text()
    assert "tempo-log git-hook run" in content

    assert uninstall_hook(repo_path=tmp_path) is True
    assert not hook_file.exists()


def test_run_git_hook_success():
    service = mock.MagicMock()
    service.log_time.return_value = {"tempoWorklogId": 888}

    res = run_git_hook(
        service=service,
        commit_msg="PROJ-321: 2h - Clean up styling",
    )
    assert res is not None
    assert res["issue"] == "PROJ-321"
    assert res["hours"] == 2.0
    service.log_time.assert_called_once_with(
        hours=2.0,
        issue="PROJ-321",
        description="Clean up styling",
    )
