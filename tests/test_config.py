"""Tests for configuration loading."""

import os
from unittest import mock

import pytest
from tempo_log.config import ConfigError, load_settings


def test_load_settings_missing_token():
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ConfigError, match="TEMPO_API_TOKEN"):
            load_settings()


def test_load_settings_minimal():
    env = {"TEMPO_API_TOKEN": "secret-tempo-token"}
    with mock.patch.dict(os.environ, env, clear=True):
        settings = load_settings()
        assert settings.tempo_api_token == "secret-tempo-token"
        assert settings.jira is None
        assert settings.default_account_id is None


def test_load_settings_full():
    env = {
        "TEMPO_API_TOKEN": "secret-tempo-token",
        "JIRA_BASE_URL": "https://test.atlassian.net/",
        "JIRA_EMAIL": "user@example.com",
        "JIRA_API_TOKEN": "jira-token",
        "JIRA_ACCOUNT_ID": "acc-123",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = load_settings()
        assert settings.tempo_api_token == "secret-tempo-token"
        assert settings.default_account_id == "acc-123"
        assert settings.jira is not None
        assert settings.jira.base_url == "https://test.atlassian.net"
        assert settings.jira.email == "user@example.com"
        assert settings.jira.api_token == "jira-token"


def test_load_settings_partial_jira_ignored():
    env = {
        "TEMPO_API_TOKEN": "secret-tempo-token",
        "JIRA_BASE_URL": "https://test.atlassian.net",
        # Missing JIRA_EMAIL and JIRA_API_TOKEN
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = load_settings()
        assert settings.jira is None
