"""Configuration models and loaders for Tempo/Jira access."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .exceptions import ConfigError
from .keyring_store import get_credential


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    api_token: str
    email: str | None = None
    is_server: bool = False


@dataclass(frozen=True)
class Settings:
    tempo_api_token: str
    tempo_base_url: str = "https://api.tempo.io/4"
    jira: JiraConfig | None = None
    default_account_id: str | None = None
    tempo_daily_cap_hours: float | None = None
    tempo_round_minutes: int | None = None
    tempo_default_issue: str | None = None
    tempo_meeting_issue: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        """Load settings from environment variables or OS keyring."""
        return load_settings()


def _load_dotenv() -> None:
    """Auto-load variables from .env in CWD or ~/.tempo-log/.env into os.environ if not already set."""
    from pathlib import Path

    candidates = [Path.cwd() / ".env", Path.home() / ".tempo-log" / ".env"]
    for env_path in candidates:
        if env_path.is_file():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


def load_settings() -> Settings:
    """Load configuration from environment variables, falling back to OS keyring."""
    _load_dotenv()
    tempo_token = os.environ.get("TEMPO_API_TOKEN") or get_credential("TEMPO_API_TOKEN")
    if not tempo_token:
        raise ConfigError(
            "TEMPO_API_TOKEN is not set. Set it via environment variable or 'tempo-log auth set-token tempo <token>'."
        )

    tempo_base_url = (
        os.environ.get("TEMPO_BASE_URL")
        or get_credential("TEMPO_BASE_URL")
        or "https://api.tempo.io/4"
    )

    jira_base = os.environ.get("JIRA_BASE_URL") or get_credential("JIRA_BASE_URL")
    jira_email = os.environ.get("JIRA_EMAIL") or get_credential("JIRA_EMAIL")
    jira_token = os.environ.get("JIRA_API_TOKEN") or get_credential("JIRA_API_TOKEN")

    is_server_env = os.environ.get("JIRA_SERVER", "").lower() in ("1", "true", "yes")

    jira_config = None
    if jira_base and jira_token:
        # If email is omitted or JIRA_SERVER is true, configure for Jira Server / DC PAT
        is_server = is_server_env or (not jira_email)
        if jira_email or is_server:
            jira_config = JiraConfig(
                base_url=jira_base.rstrip("/"),
                api_token=jira_token,
                email=jira_email,
                is_server=is_server,
            )

    default_account_id = os.environ.get("JIRA_ACCOUNT_ID") or get_credential("JIRA_ACCOUNT_ID")

    daily_cap_str = os.environ.get("TEMPO_DAILY_CAP_HOURS") or get_credential("TEMPO_DAILY_CAP_HOURS")
    daily_cap = float(daily_cap_str) if daily_cap_str else None

    round_mins_str = os.environ.get("TEMPO_ROUND_MINUTES") or get_credential("TEMPO_ROUND_MINUTES")
    round_mins = int(round_mins_str) if round_mins_str else None

    default_issue = os.environ.get("TEMPO_DEFAULT_ISSUE") or get_credential("TEMPO_DEFAULT_ISSUE")
    meeting_issue = os.environ.get("TEMPO_MEETING_ISSUE") or get_credential("TEMPO_MEETING_ISSUE")

    return Settings(
        tempo_api_token=tempo_token,
        tempo_base_url=tempo_base_url,
        jira=jira_config,
        default_account_id=default_account_id,
        tempo_daily_cap_hours=daily_cap,
        tempo_round_minutes=round_mins,
        tempo_default_issue=default_issue,
        tempo_meeting_issue=meeting_issue,
    )
