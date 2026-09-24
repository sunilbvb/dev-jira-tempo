#!/usr/bin/env python3
"""Example: Using tempo_log SDK in a custom application or script."""

import os
from tempo_log import (
    JiraConfig,
    MemoryJournal,
    TempoService,
    ValidationError,
    TempoClientError,
)


def main():
    # 1. Fetch credentials from environment or your app's secret vault
    tempo_token = os.environ.get("TEMPO_API_TOKEN", "mock_tempo_token")
    jira_base_url = os.environ.get("JIRA_BASE_URL", "https://example.atlassian.net")
    jira_email = os.environ.get("JIRA_EMAIL", "developer@example.com")
    jira_token = os.environ.get("JIRA_API_TOKEN", "mock_jira_token")

    # 2. Setup configuration
    jira_config = JiraConfig(
        base_url=jira_base_url,
        email=jira_email,
        api_token=jira_token,
    )

    # 3. Create the service (using MemoryJournal to keep records in memory)
    service = TempoService(
        tempo_token=tempo_token,
        jira_config=jira_config,
        journal=MemoryJournal(),
    )

    print("--- 1. Health Check ---")
    health = service.check_health()
    print(f"Tempo status: {'OK' if health['tempo_ok'] else 'FAILED'}")
    print(f"Jira status:  {'OK' if health['jira_ok'] else 'FAILED'}")

    print("\n--- 2. Logging Time ---")
    try:
        # One method resolves issue key, author accountId, submits, and logs audit
        result = service.log_time(
            issue="PROJ-101",
            hours=1.5,
            description="Working on backend API optimization",
        )
        print("Logged successfully! Tempo Worklog ID:", result.get("tempoWorklogId"))
    except (ValidationError, TempoClientError) as exc:
        print(f"Could not log time: {exc}")

    print("\n--- 3. Listing Logged Hours ---")
    try:
        logs = service.list_time(from_date="2026-09-01", to_date="2026-09-24", limit=5)
        for entry in logs.get("results", []):
            print(f"- Worklog {entry['tempoWorklogId']}: {entry['timeSpentSeconds'] / 3600}h on {entry['startDate']}")
    except Exception as exc:
        print(f"Could not list worklogs: {exc}")


if __name__ == "__main__":
    main()
