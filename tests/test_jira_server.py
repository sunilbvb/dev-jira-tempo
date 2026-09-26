from unittest import mock
import requests
from tempo_log.config import JiraConfig
from tempo_log.jira_client import JiraClient


def test_jira_server_pat_auth_header():
    # When is_server is True, auth header must be Bearer PAT, not Basic auth
    cfg = JiraConfig(
        base_url="https://jira.internal.corp",
        api_token="personal-access-token",
        is_server=True,
    )
    client = JiraClient(cfg)
    assert client._session.headers["Authorization"] == "Bearer personal-access-token"


def test_jira_server_get_current_account_id_username():
    cfg = JiraConfig(
        base_url="https://jira.internal.corp",
        api_token="personal-access-token",
        is_server=True,
    )
    client = JiraClient(cfg)

    fake_resp = mock.MagicMock(spec=requests.Response)
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "name": "john.doe",
        "key": "JDOE",
    }

    with mock.patch("requests.Session.get", return_value=fake_resp):
        acc = client.get_current_account_id()
        assert acc == "JDOE"


def test_jira_cloud_get_current_account_id():
    cfg = JiraConfig(
        base_url="https://myorg.atlassian.net",
        api_token="cloud-api-token",
        email="user@myorg.com",
        is_server=False,
    )
    client = JiraClient(cfg)
    assert client._session.auth == ("user@myorg.com", "cloud-api-token")

    fake_resp = mock.MagicMock(spec=requests.Response)
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "accountId": "557058:f5813ae3-4b6e-40d2-a720-72f6a7359480"
    }

    with mock.patch("requests.Session.get", return_value=fake_resp):
        acc = client.get_current_account_id()
        assert acc == "557058:f5813ae3-4b6e-40d2-a720-72f6a7359480"
