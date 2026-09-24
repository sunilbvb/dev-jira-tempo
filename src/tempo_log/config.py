"""Configuration models and loaders for Tempo/Jira access."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .exceptions import ConfigError


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    email: str
    api_token: str


@dataclass(frozen=True)
class Settings:
    tempo_api_token: str
    jira: JiraConfig | None = None
    default_account_id: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        """Load settings from environment variables."""
        return load_settings()


def load_settings() -> Settings:
    """Load configuration from environment variables."""
    tempo_token = os.environ.get("TEMPO_API_TOKEN")
    if not tempo_token:
        raise ConfigError("TEMPO_API_TOKEN environment variable is not set.")

    jira_base = os.environ.get("JIRA_BASE_URL")
    jira_email = os.environ.get("JIRA_EMAIL")
    jira_token = os.environ.get("JIRA_API_TOKEN")

    jira_config = None
    if jira_base and jira_email and jira_token:
        jira_config = JiraConfig(
            base_url=jira_base.rstrip("/"), email=jira_email, api_token=jira_token
        )

    default_account_id = os.environ.get("JIRA_ACCOUNT_ID")

    return Settings(
        tempo_api_token=tempo_token,
        jira=jira_config,
        default_account_id=default_account_id,
    )
