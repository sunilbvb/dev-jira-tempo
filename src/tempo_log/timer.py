"""Live stopwatch timer for tracking elapsed work time before logging to Tempo."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exceptions import ValidationError

DEFAULT_TIMER_PATH = Path.home() / ".tempo-log" / "active_timer.json"


def timer_path() -> Path:
    """Return default or configured timer state file path."""
    override = os.environ.get("TEMPO_LOG_TIMER_STATE")
    return Path(override) if override else DEFAULT_TIMER_PATH


@dataclass
class TimerState:
    issue: str | None
    issue_id: int | None
    description: str
    started_at: str  # ISO string

    @property
    def start_datetime(self) -> datetime:
        return datetime.fromisoformat(self.started_at)

    @property
    def elapsed_seconds(self) -> float:
        now = datetime.now(timezone.utc)
        start = self.start_datetime
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        return max(0.0, (now - start).total_seconds())

    @property
    def elapsed_hours(self) -> float:
        # Minimum resolution 0.1h (6 minutes) or round to 2 decimal places
        hrs = self.elapsed_seconds / 3600.0
        return max(0.1, round(hrs, 2))

    @property
    def formatted_duration(self) -> str:
        secs = int(self.elapsed_seconds)
        hours, remainder = divmod(secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue": self.issue,
            "issue_id": self.issue_id,
            "description": self.description,
            "started_at": self.started_at,
        }


def get_active_timer(path: Path | None = None) -> TimerState | None:
    """Retrieve currently active timer, or None if idle."""
    target = path or timer_path()
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return TimerState(
            issue=data.get("issue"),
            issue_id=data.get("issue_id"),
            description=data.get("description", ""),
            started_at=data["started_at"],
        )
    except Exception:
        return None


def start_timer(
    issue: str | None = None,
    issue_id: int | None = None,
    description: str = "",
    path: Path | None = None,
) -> TimerState:
    """Start tracking a new work session."""
    target = path or timer_path()
    existing = get_active_timer(target)
    if existing:
        target_name = existing.issue or existing.issue_id or "unassigned"
        raise ValidationError(
            f"A timer is already running for {target_name} (started at {existing.started_at}). "
            "Run 'tempo-log stop' before starting a new timer."
        )

    if not issue and not issue_id:
        raise ValidationError("Provide either --issue or --issue-id to start a timer.")

    state = TimerState(
        issue=issue,
        issue_id=issue_id,
        description=description,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    return state


def stop_timer(discard: bool = False, path: Path | None = None) -> TimerState:
    """Stop active timer and return the state for logging."""
    target = path or timer_path()
    existing = get_active_timer(target)
    if not existing:
        raise ValidationError("No active timer running. Start one with 'tempo-log start --issue <KEY>'.")

    # Remove state file
    try:
        target.unlink(missing_ok=True)
    except Exception:
        pass

    return existing
