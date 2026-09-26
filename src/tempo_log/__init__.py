"""tempo_log: Fast, modular SDK and CLI for Tempo Timesheets and Jira."""

from __future__ import annotations

from .completion import generate_completion, get_recent_issues
from .config import JiraConfig, Settings, load_settings
from .exceptions import (
    ConfigError,
    JiraClientError,
    TempoClientError,
    TempoLogError,
    ValidationError,
)
from .git_hook import (
    WorklogCommitInfo,
    install_hook,
    parse_commit_message,
    run_git_hook,
    uninstall_hook,
)
from .jira_client import JiraClient
from .journal import (
    BaseJournal,
    DualJournal,
    FileJournal,
    MemoryJournal,
    NullJournal,
    SQLiteJournal,
    append_entry,
    journal_path,
)
from .keyring_store import (
    delete_credential,
    get_credential,
    is_keyring_available,
    set_credential,
)
from .service import TempoService
from .tempo_client import TempoClient, Worklog
from .timer import (
    TimerState,
    get_active_timer,
    start_timer,
    stop_timer,
    timer_path,
)
from .tui import (
    display_dashboard,
    render_dashboard_plain,
    render_dashboard_rich,
    run_interactive_tui,
)
from .web_server import run_server

__version__ = "0.1.0"

__all__ = [
    "BaseJournal",
    "ConfigError",
    "DualJournal",
    "FileJournal",
    "JiraClient",
    "JiraClientError",
    "JiraConfig",
    "MemoryJournal",
    "NullJournal",
    "SQLiteJournal",
    "Settings",
    "TempoClient",
    "TempoClientError",
    "TempoLogError",
    "TempoService",
    "TimerState",
    "ValidationError",
    "Worklog",
    "WorklogCommitInfo",
    "append_entry",
    "delete_credential",
    "display_dashboard",
    "generate_completion",
    "get_active_timer",
    "get_credential",
    "get_recent_issues",
    "install_hook",
    "is_keyring_available",
    "journal_path",
    "load_settings",
    "parse_commit_message",
    "render_dashboard_plain",
    "render_dashboard_rich",
    "run_git_hook",
    "run_interactive_tui",
    "run_server",
    "set_credential",
    "start_timer",
    "stop_timer",
    "timer_path",
    "uninstall_hook",
]
