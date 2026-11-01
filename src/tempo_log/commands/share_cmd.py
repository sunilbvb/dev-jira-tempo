"""CLI handler for `tempo-log share` command.

Posts daily worklog digest to team chat webhooks (Slack / Discord / Teams).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date as dt_date
from typing import Any

from ..config import Settings
from ..export import ExportItem
from ..journal import SQLiteJournal
from ..service import TempoService
from ..sharing import build_digest_payload, send_webhook

logger = logging.getLogger(__name__)


def _get_service(target: Settings | TempoService | None) -> TempoService | None:
    if isinstance(target, TempoService):
        return target
    if isinstance(target, Settings):
        return TempoService(target)
    return None


def run_share(args: argparse.Namespace, target: Settings | TempoService | None = None) -> int:
    """Share worklogs to webhook."""
    target_date = getattr(args, "date", None) or dt_date.today().isoformat()
    webhook_url = getattr(args, "webhook", None) or os.getenv("TEMPO_SHARE_WEBHOOK")
    channel = getattr(args, "channel", None) or os.getenv("TEMPO_SHARE_CHANNEL")
    dry_run = getattr(args, "dry_run", False)

    service = _get_service(target)
    items: list[ExportItem] = []

    # Try fetching from Tempo API
    if service and service.tempo_client:
        try:
            logs = service.tempo_client.list_worklogs(from_date=target_date, to_date=target_date)
            for w in logs:
                issue_info = w.get("issue", {})
                issue_key = issue_info.get("key") or str(issue_info.get("id", "UNKNOWN"))
                items.append(
                    ExportItem(
                        date=w.get("startDate", target_date),
                        issue=issue_key,
                        hours=(w.get("timeSpentSeconds", 0) / 3600),
                        start_time=w.get("startTime", "")[:5],
                        tempo_id=w.get("tempoWorklogId", ""),
                        description=w.get("description", ""),
                    )
                )
        except Exception as exc:
            logger.warning("Could not fetch remote worklogs: %s", exc)

    # Fallback to local SQLite journal
    if not items:
        j = SQLiteJournal()
        logs = j.query(from_date=target_date, to_date=target_date, limit=100)
        for w in logs:
            items.append(
                ExportItem(
                    date=w.get("start_date", target_date),
                    issue=w.get("issue_key") or str(w.get("issue_id", "UNKNOWN")),
                    hours=float(w.get("hours", 0.0)),
                    start_time=w.get("start_time", "")[:5],
                    tempo_id=w.get("tempo_worklog_id", ""),
                    description=w.get("description", ""),
                )
            )

    if not items:
        print(f"No worklog entries found to share for {target_date}.")
        return 0

    payload = build_digest_payload(target_date, items, channel=channel)

    if dry_run or not webhook_url:
        print(f"\n[DRY RUN] Webhook Digest Payload for {target_date}:")
        print("=" * 60)
        print(payload["text"])
        print("=" * 60)
        if not webhook_url:
            print("Note: Set --webhook URL or TEMPO_SHARE_WEBHOOK to send live.")
        return 0

    success, msg = send_webhook(webhook_url, payload)
    if success:
        print(f"Successfully shared worklog digest to webhook: {msg}")
        return 0
    else:
        logger.error("Failed to share worklog to webhook: %s", msg)
        print(f"Webhook delivery failed: {msg}")
        return 1
