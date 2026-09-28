import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
import pytest
import requests

from tempo_log.web_server import TempoWebHandler


TEST_TOKEN = "test-secret-web-token"


@pytest.fixture(scope="module")
def server():
    os.environ["TEMPO_WEB_TOKEN"] = TEST_TOKEN
    # Start on dynamic test port (e.g. 18234)
    server_address = ("127.0.0.1", 18234)
    httpd = ThreadingHTTPServer(server_address, TempoWebHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:18234"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture(scope="module")
def auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


def test_get_health_endpoint(server, auth_headers):
    resp = requests.get(f"{server}/api/health", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "keyring_available" in data
    assert "tempo_ok" in data


def test_get_config_endpoint(server, auth_headers):
    resp = requests.get(f"{server}/api/config", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "tempo_token_set" in data
    assert "jira_base_url" in data
    assert "is_server" in data


def test_post_config_endpoint(server, auth_headers, tmp_path):
    with mock.patch("tempo_log.web_server.Path") as mock_path:
        env_mock = tmp_path / ".env"
        mock_path.return_value = env_mock

        payload = {
            "tempo_token": "test-tempo-token-12345",
            "jira_base_url": "https://company.atlassian.net",
            "jira_email": "dev@company.com",
            "jira_token": "jira-tok",
            "is_server": False,
            "use_keyring": False,
        }
        resp = requests.post(f"{server}/api/config", json=payload, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_timer_lifecycle_endpoints(server, auth_headers, tmp_path):
    timer_file = tmp_path / "test_active_timer.json"
    with mock.patch("tempo_log.timer.timer_path", return_value=timer_file):
        # 1. Initially idle
        resp_idle = requests.get(f"{server}/api/timer", headers=auth_headers)
        assert resp_idle.status_code == 200
        assert resp_idle.json()["active"] is False

        # 2. Start timer
        start_payload = {"issue": "PROJ-999", "description": "Web UI testing"}
        resp_start = requests.post(f"{server}/api/timer/start", json=start_payload, headers=auth_headers)
        assert resp_start.status_code == 200
        assert resp_start.json()["status"] == "started"

        # 3. Check active timer
        resp_active = requests.get(f"{server}/api/timer", headers=auth_headers)
        assert resp_active.status_code == 200
        assert resp_active.json()["active"] is True
        assert resp_active.json()["issue"] == "PROJ-999"

        # 4. Discard timer
        resp_discard = requests.post(f"{server}/api/timer/discard", headers=auth_headers)
        assert resp_discard.status_code == 200
        assert resp_discard.json()["status"] == "discarded"


def test_summary_and_worklogs_endpoints(server, auth_headers):
    resp_sum = requests.get(f"{server}/api/summary", headers=auth_headers)
    assert resp_sum.status_code == 200
    assert "total_hours" in resp_sum.json()

    resp_logs = requests.get(f"{server}/api/worklogs?limit=5", headers=auth_headers)
    assert resp_logs.status_code == 200
    assert "worklogs" in resp_logs.json()


def test_serve_static_index_html(server):
    resp = requests.get(f"{server}/")
    assert resp.status_code == 200
    assert "dev-jira-tempo" in resp.text
    assert "ui.css" in resp.text


def test_no_wildcard_cors(server, auth_headers):
    resp = requests.get(f"{server}/api/health", headers=auth_headers)
    assert "Access-Control-Allow-Origin" not in resp.headers


def test_web_auth_token_protection(server):
    # 1. Unauthenticated request should fail with 401
    unauth_resp = requests.get(f"{server}/api/health")
    assert unauth_resp.status_code == 401
    assert "Unauthorized" in unauth_resp.json()["error"]

    # 2. URL parameter token is rejected (must be header)
    url_token_resp = requests.get(f"{server}/api/health?token={TEST_TOKEN}")
    assert url_token_resp.status_code == 401

    # 3. Authenticated request with Bearer header succeeds
    auth_resp = requests.get(
        f"{server}/api/health",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert auth_resp.status_code == 200

    # 4. Authenticated request with X-Auth-Token header succeeds
    xauth_resp = requests.get(
        f"{server}/api/health",
        headers={"X-Auth-Token": TEST_TOKEN},
    )
    assert xauth_resp.status_code == 200

    # 5. Invalid token fails with 401
    bad_token_resp = requests.get(
        f"{server}/api/health",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert bad_token_resp.status_code == 401

    # 6. When server has no token configured, requests fail with 401
    with mock.patch.dict("os.environ", {"TEMPO_WEB_TOKEN": "", "WEB_AUTH_TOKEN": ""}):
        no_conf_resp = requests.get(
            f"{server}/api/health",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert no_conf_resp.status_code == 401
        assert "not configured" in no_conf_resp.json()["error"]


