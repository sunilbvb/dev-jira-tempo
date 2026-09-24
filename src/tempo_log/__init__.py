"""tempo_log: Fast, modular SDK and CLI for Tempo Timesheets and Jira."""

from __future__ import annotations

from .config import JiraConfig, Settings, load_settings
from .exceptions import (
    ConfigError,
    JiraClientError,
    TempoClientError,
    TempoLogError,
    ValidationError,
)
from .jira_client import JiraClient
from .journal import (
    BaseJournal,
    FileJournal,
    MemoryJournal,
    NullJournal,
    append_entry,
    journal_path,
)
from .service import TempoService
from .tempo_client import TempoClient, Worklog

__version__ = "0.1.0"

__all__ = [
    "BaseJournal",
    "ConfigError",
    "FileJournal",
    "JiraClient",
    "JiraClientError",
    "JiraConfig",
    "MemoryJournal",
    "NullJournal",
    "Settings",
    "TempoClient",
    "TempoClientError",
    "TempoLogError",
    "TempoService",
    "ValidationError",
    "Worklog",
    "append_entry",
    "journal_path",
    "load_settings",
]
