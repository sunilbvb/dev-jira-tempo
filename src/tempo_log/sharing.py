"""Team worklog digest sharing via HTTP Webhooks (Slack, Discord, Teams).

Uses Python standard library urllib (no requests or external pip libraries).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .export import ExportItem

logger = logging.getLogger(__name__)


def build_digest_payload(date_str: str, items: list[ExportItem], channel: str | None = None) -> dict[str, Any]:
    """Build multi-platform compatible webhook JSON payload."""
    total_hours = sum(i.hours for i in items)
    issues = sorted({i.issue for i in items})

    bullets = []
    for i in items:
        clean_desc = i.description.splitlines()[0] if i.description else "Task completed"
        bullets.append(f"• *{i.issue}* ({i.hours:.2f}h): {clean_desc}")

    text_summary = f"*Daily Worklog Digest for {date_str}*\n" + f"Total Logged: *{total_hours:.2f}h* across {len(issues)} issues\n\n" + "\n".join(bullets)

    payload: dict[str, Any] = {
        "text": text_summary,
        "date": date_str,
        "total_hours": round(total_hours, 2),
        "issues": issues,
    }

    # Slack Block Kit structure
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📋 Worklog Summary: {date_str}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Total Hours: *{total_hours:.2f}h* | Tickets: `{', '.join(issues)}`",
            },
        },
        {"type": "divider"},
    ]
    for b in bullets:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": b},
        })
    payload["blocks"] = blocks

    if channel:
        payload["channel"] = channel

    return payload


def send_webhook(webhook_url: str, payload: dict[str, Any], timeout: int = 10) -> tuple[bool, str]:
    """Send payload to webhook URL using urllib."""
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data_bytes,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "tempo-log-cli"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return (True, body or "OK")
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="replace")
        return (False, f"HTTP {exc.code}: {err_msg}")
    except Exception as exc:
        return (False, str(exc))
