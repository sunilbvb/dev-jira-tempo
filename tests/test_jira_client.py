"""Tests for Jira client."""

from unittest.mock import MagicMock
import pytest
from tempo_log.config import JiraConfig
from tempo_log.jira_client import JiraClient, JiraClientError


from tempo_log.issue_cache import IssueCache


def test_resolve_issue_id_success(tmp_path):
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"id": "10050"}
    session.get.return_value = mock_resp

    config = JiraConfig(base_url="https://company.atlassian.net", email="a@b.com", api_token="tok")
    cache = IssueCache(cache_path=tmp_path / "cache.json")
    client = JiraClient(config, session=session, cache=cache)

    issue_id = client.resolve_issue_id("PROJ-999")
    assert issue_id == 10050
    session.get.assert_called_with(
        "https://company.atlassian.net/rest/api/3/issue/PROJ-999",
        params={"fields": "id"},
        timeout=10,
    )


def test_resolve_issue_id_failure(tmp_path):
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    mock_resp.text = "Issue does not exist"
    session.get.return_value = mock_resp

    config = JiraConfig(base_url="https://company.atlassian.net", email="a@b.com", api_token="tok")
    cache = IssueCache(cache_path=tmp_path / "cache.json")
    client = JiraClient(config, session=session, cache=cache)

    with pytest.raises(JiraClientError, match="Failed to resolve issue 'PROJ-999': 404 Issue does not exist"):
        client.resolve_issue_id("PROJ-999")


def test_get_current_account_id_success():
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"accountId": "557058:xyz"}
    session.get.return_value = mock_resp

    config = JiraConfig(base_url="https://company.atlassian.net", email="a@b.com", api_token="tok")
    client = JiraClient(config, session=session)

    account_id = client.get_current_account_id()
    assert account_id == "557058:xyz"
    session.get.assert_called_with(
        "https://company.atlassian.net/rest/api/3/myself",
        timeout=10,
    )
