"""Minimal Jira REST client used to resolve issue keys and the current user."""

from __future__ import annotations

import logging

import requests

from .config import JiraConfig
from .exceptions import JiraClientError

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10


class JiraClient:
    def __init__(self, config: JiraConfig, session: requests.Session | None = None):
        self._config = config
        self._session = session or requests.Session()
        self._session.auth = (config.email, config.api_token)

    def resolve_issue_id(self, issue_key: str) -> int:
        url = f"{self._config.base_url}/rest/api/3/issue/{issue_key}"
        logger.debug("Resolving issue id for %s", issue_key)
        response = self._session.get(
            url, params={"fields": "id"}, timeout=REQUEST_TIMEOUT_SECONDS
        )
        self._raise_for_status(response, f"resolve issue '{issue_key}'")
        return int(response.json()["id"])

    def get_current_account_id(self) -> str:
        url = f"{self._config.base_url}/rest/api/3/myself"
        logger.debug("Resolving current Jira account id")
        response = self._session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        self._raise_for_status(response, "resolve current account id")
        return response.json()["accountId"]

    @staticmethod
    def _raise_for_status(response: requests.Response, action: str) -> None:
        if response.ok:
            return
        raise JiraClientError(
            f"Failed to {action}: {response.status_code} {response.text}"
        )
