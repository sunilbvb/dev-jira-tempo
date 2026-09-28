"""Unit tests for local issue key caching."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tempo_log.config import JiraConfig
from tempo_log.issue_cache import IssueCache
from tempo_log.jira_client import JiraClient


def test_issue_cache_get_set(tmp_path):
    cache_file = tmp_path / "issue_cache.json"
    cache = IssueCache(cache_path=cache_file)

    assert cache.get("PROJ-123") is None

    cache.set("PROJ-123", 10052)
    assert cache.get("PROJ-123") == 10052
    assert cache.get("proj-123") == 10052  # Case-insensitive

    # Verify file persistence
    new_cache = IssueCache(cache_path=cache_file)
    assert new_cache.get("PROJ-123") == 10052


def test_jira_client_uses_cached_key(tmp_path):
    cache_file = tmp_path / "issue_cache.json"
    cache = IssueCache(cache_path=cache_file)
    cache.set("PROJ-999", 99999)

    mock_session = MagicMock()
    config = JiraConfig(base_url="https://jira.test", api_token="pat", is_server=True)
    client = JiraClient(config=config, session=mock_session, cache=cache)

    # Calling resolve_issue_id should hit cache and NOT trigger session GET call
    issue_id = client.resolve_issue_id("PROJ-999")
    assert issue_id == 99999
    mock_session.get.assert_not_called()
