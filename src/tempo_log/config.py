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
    jira: JiraConfig | None = None
    default_account_id: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        """Load settings from environment variables or OS keyring."""
        return load_settings()


def load_settings() -> Settings:
    """Load configuration from environment variables, falling back to OS keyring."""
    tempo_token = os.environ.get("TEMPO_API_TOKEN") or get_credential("TEMPO_API_TOKEN")
    if not tempo_token:
        raise ConfigError(
            "TEMPO_API_TOKEN is not set. Set it via environment variable or 'tempo-log auth set-token tempo <token>'."
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

    return Settings(
        tempo_api_token=tempo_token,
        jira=jira_config,
        default_account_id=default_account_id,
    )
