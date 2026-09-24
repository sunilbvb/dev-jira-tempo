"""Minimal Tempo REST client used to create worklogs."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

TEMPO_BASE_URL = "https://api.tempo.io/4"
REQUEST_TIMEOUT_SECONDS = 10


class TempoClientError(RuntimeError):
    """Raised when a Tempo API call fails."""


@dataclass(frozen=True)
class Worklog:
    issue_id: int
    account_id: str
    hours: float
    start_date: str
    start_time: str
    description: str = ""

    def to_payload(self) -> dict:
        return {
            "issueId": self.issue_id,
            "authorAccountId": self.account_id,
            "timeSpentSeconds": int(round(self.hours * 3600)),
            "startDate": self.start_date,
            "startTime": self.start_time,
            "description": self.description,
        }


class TempoClient:
    def __init__(self, api_token: str, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            }
        )

    def create_worklog(self, worklog: Worklog) -> dict:
        logger.debug("Submitting worklog for issue id %s", worklog.issue_id)
        response = self._session.post(
            f"{TEMPO_BASE_URL}/worklogs",
            json=worklog.to_payload(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if not response.ok:
            raise TempoClientError(
                f"Failed to create worklog: {response.status_code} {response.text}"
            )
        return response.json()

    def list_worklogs(
        self,
        account_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        params = {"limit": limit, "offset": offset}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        url = (
            f"{TEMPO_BASE_URL}/worklogs/user/{account_id}"
            if account_id
            else f"{TEMPO_BASE_URL}/worklogs"
        )
        logger.debug("Listing worklogs from %s (params=%s)", url, params)
        response = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        if not response.ok:
            raise TempoClientError(
                f"Failed to list worklogs: {response.status_code} {response.text}"
            )
        return response.json()

    def get_worklog(self, worklog_id: int) -> dict:
        response = self._session.get(
            f"{TEMPO_BASE_URL}/worklogs/{worklog_id}", timeout=REQUEST_TIMEOUT_SECONDS
        )
        if not response.ok:
            raise TempoClientError(
                f"Failed to get worklog {worklog_id}: {response.status_code} {response.text}"
            )
        return response.json()

    def update_worklog(self, worklog_id: int, **fields) -> dict:
        """Update a worklog. Accepts any of: hours, description, start_date,
        start_time. Tempo's PUT requires the full payload, so this fetches
        the existing worklog first and merges in only the changed fields."""
        overrides = {
            "hours": fields.get("hours"),
            "description": fields.get("description"),
            "start_date": fields.get("start_date"),
            "start_time": fields.get("start_time"),
        }
        if not any(v is not None for v in overrides.values()):
            raise ValueError("No fields provided to update.")

        existing = self.get_worklog(worklog_id)
        payload = {
            "issueId": existing["issue"]["id"],
            "authorAccountId": existing["author"]["accountId"],
            "timeSpentSeconds": (
                int(round(overrides["hours"] * 3600))
                if overrides["hours"] is not None
                else existing["timeSpentSeconds"]
            ),
            "startDate": overrides["start_date"] or existing["startDate"],
            "startTime": overrides["start_time"] or existing["startTime"],
            "description": (
                overrides["description"]
                if overrides["description"] is not None
                else existing.get("description", "")
            ),
        }

        logger.debug("Updating worklog %s with %s", worklog_id, payload)
        response = self._session.put(
            f"{TEMPO_BASE_URL}/worklogs/{worklog_id}",
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if not response.ok:
            raise TempoClientError(
                f"Failed to update worklog {worklog_id}: {response.status_code} {response.text}"
            )
        return response.json()
