"""Minimal Jira REST client supporting both Jira Cloud and Jira Server/Data Center."""

from __future__ import annotations

import logging
from typing import Any

import requests

from .config import JiraConfig
from .exceptions import JiraClientError

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10


class JiraClient:
    def __init__(self, config: JiraConfig, session: requests.Session | None = None):
        self._config = config
        self._session = session or requests.Session()

        # Jira Server / Data Center uses Bearer PAT auth, while Jira Cloud uses Basic Auth
        if config.is_server or not config.email:
            self._session.headers.update(
                {
                    "Authorization": f"Bearer {config.api_token}",
                    "Content-Type": "application/json",
                }
            )
        else:
            self._session.auth = (config.email, config.api_token)

    @property
    def api_version(self) -> str:
        """API version prefix: '2' for Server/DC, '3' for Cloud."""
        return "2" if self._config.is_server else "3"

    def resolve_issue_id(self, issue_key: str) -> int:
        """Resolve an issue key (e.g. PROJ-123) to its internal numeric issue ID."""
        url = f"{self._config.base_url}/rest/api/{self.api_version}/issue/{issue_key}"
        logger.debug("Resolving issue id for %s at %s", issue_key, url)
        response = self._session.get(
            url, params={"fields": "id"}, timeout=REQUEST_TIMEOUT_SECONDS
        )

        # Fallback to API v2 if v3 returns 404 (common in hybrid / Server deployments)
        if not response.ok and self.api_version == "3" and response.status_code == 404:
            fallback_url = f"{self._config.base_url}/rest/api/2/issue/{issue_key}"
            logger.debug("Attempting fallback to API v2 at %s", fallback_url)
            fallback_response = self._session.get(
                fallback_url, params={"fields": "id"}, timeout=REQUEST_TIMEOUT_SECONDS
            )
            if fallback_response.ok:
                return int(fallback_response.json()["id"])

        self._raise_for_status(response, f"resolve issue '{issue_key}'")
        return int(response.json()["id"])

    def get_current_account_id(self) -> str:
        """Resolve current authenticated user's account ID (or key/name in Jira Server/DC)."""
        url = f"{self._config.base_url}/rest/api/{self.api_version}/myself"
        logger.debug("Resolving current Jira account id at %s", url)
        response = self._session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)

        # Fallback to API v2 if v3 fails with 404
        if not response.ok and self.api_version == "3" and response.status_code == 404:
            fallback_url = f"{self._config.base_url}/rest/api/2/myself"
            fallback_response = self._session.get(fallback_url, timeout=REQUEST_TIMEOUT_SECONDS)
            if fallback_response.ok:
                data: dict[str, Any] = fallback_response.json()
                return str(data.get("accountId") or data.get("key") or data.get("name"))

        self._raise_for_status(response, "resolve current account id")
        data = response.json()
        # Jira Cloud uses 'accountId', Jira Server/DC uses 'key' or 'name'
        user_id = data.get("accountId") or data.get("key") or data.get("name")
        if not user_id:
            raise JiraClientError(f"Could not extract user identifier from response: {data}")
        return str(user_id)

    @staticmethod
    def _raise_for_status(response: requests.Response, action: str) -> None:
        if response.ok:
            return
        raise JiraClientError(
            f"Failed to {action}: {response.status_code} {response.text}"
        )
