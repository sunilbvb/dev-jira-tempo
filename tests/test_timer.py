from pathlib import Path
import pytest
from tempo_log.exceptions import ValidationError
from tempo_log.timer import (
    TimerState,
    get_active_timer,
    start_timer,
    stop_timer,
)


def test_start_timer_creates_file(tmp_path: Path):
    state_file = tmp_path / "test_timer.json"
    state = start_timer(issue="PROJ-101", description="Working on auth", path=state_file)
    assert state.issue == "PROJ-101"
    assert state.description == "Working on auth"
    assert state_file.exists()

    active = get_active_timer(state_file)
    assert active is not None
    assert active.issue == "PROJ-101"
    assert active.description == "Working on auth"
    assert active.elapsed_hours >= 0.1
    assert ":" in active.formatted_duration


def test_start_timer_already_running_raises(tmp_path: Path):
    state_file = tmp_path / "test_timer.json"
    start_timer(issue="PROJ-101", path=state_file)
    with pytest.raises(ValidationError, match="A timer is already running"):
        start_timer(issue="PROJ-102", path=state_file)


def test_start_timer_no_issue_raises(tmp_path: Path):
    state_file = tmp_path / "test_timer.json"
    with pytest.raises(ValidationError, match="Provide either --issue or --issue-id"):
        start_timer(path=state_file)


def test_stop_timer_success(tmp_path: Path):
    state_file = tmp_path / "test_timer.json"
    start_timer(issue_id=456, description="Refactoring", path=state_file)
    stopped = stop_timer(path=state_file)
    assert stopped.issue_id == 456
    assert stopped.description == "Refactoring"
    assert not state_file.exists()


def test_stop_timer_none_running_raises(tmp_path: Path):
    state_file = tmp_path / "test_timer.json"
    with pytest.raises(ValidationError, match="No active timer running"):
        stop_timer(path=state_file)
