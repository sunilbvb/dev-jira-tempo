"""Tests for Tempo client."""

from unittest.mock import MagicMock
import pytest
from tempo_log.tempo_client import TempoClient, TempoClientError, Worklog


def test_worklog_to_payload():
    w = Worklog(
        issue_id=123,
        account_id="acc-1",
        hours=1.5,
        start_date="2026-09-24",
        start_time="09:30:00",
        description="Daily standup",
    )
    payload = w.to_payload()
    assert payload == {
        "issueId": 123,
        "authorAccountId": "acc-1",
        "timeSpentSeconds": 5400,
        "startDate": "2026-09-24",
        "startTime": "09:30:00",
        "description": "Daily standup",
    }


def test_create_worklog_success():
    session = MagicMock()
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"tempoWorklogId": 456}
    session.post.return_value = mock_response

    client = TempoClient("dummy-token", session=session)
    w = Worklog(123, "acc-1", 1.0, "2026-09-24", "10:00:00")
    res = client.create_worklog(w)

    assert res == {"tempoWorklogId": 456}
    session.post.assert_called_once()
    args, kwargs = session.post.call_args
    assert "https://api.tempo.io/4/worklogs" in args[0]
    assert kwargs["json"]["issueId"] == 123


def test_create_worklog_failure():
    session = MagicMock()
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    session.post.return_value = mock_response

    client = TempoClient("dummy-token", session=session)
    w = Worklog(123, "acc-1", 1.0, "2026-09-24", "10:00:00")
    with pytest.raises(TempoClientError, match="Failed to create worklog: 401 Unauthorized"):
        client.create_worklog(w)


def test_list_worklogs():
    session = MagicMock()
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"results": [{"tempoWorklogId": 1}]}
    session.get.return_value = mock_response

    client = TempoClient("dummy-token", session=session)
    res = client.list_worklogs(account_id="acc-1", from_date="2026-09-01", to_date="2026-09-10")

    assert res == {"results": [{"tempoWorklogId": 1}]}
    args, kwargs = session.get.call_args
    assert "https://api.tempo.io/4/worklogs/user/acc-1" in args[0]
    assert kwargs["params"]["from"] == "2026-09-01"
    assert kwargs["params"]["to"] == "2026-09-10"


def test_update_worklog():
    session = MagicMock()

    get_resp = MagicMock()
    get_resp.ok = True
    get_resp.json.return_value = {
        "tempoWorklogId": 50,
        "issue": {"id": 100},
        "author": {"accountId": "acc-1"},
        "timeSpentSeconds": 3600,
        "startDate": "2026-09-20",
        "startTime": "09:00:00",
        "description": "Old desc",
    }
    session.get.return_value = get_resp

    put_resp = MagicMock()
    put_resp.ok = True
    put_resp.json.return_value = {"tempoWorklogId": 50, "timeSpentSeconds": 7200}
    session.put.return_value = put_resp

    client = TempoClient("dummy-token", session=session)
    res = client.update_worklog(50, hours=2.0, description="New desc")

    assert res == {"tempoWorklogId": 50, "timeSpentSeconds": 7200}
    session.get.assert_called_with("https://api.tempo.io/4/worklogs/50", timeout=10)
    args, kwargs = session.put.call_args
    assert "https://api.tempo.io/4/worklogs/50" in args[0]
    assert kwargs["json"]["timeSpentSeconds"] == 7200
    assert kwargs["json"]["description"] == "New desc"
    assert kwargs["json"]["startDate"] == "2026-09-20"


def test_update_worklog_no_fields():
    client = TempoClient("dummy-token", session=MagicMock())
    with pytest.raises(ValueError, match="No fields provided to update"):
        client.update_worklog(50)
