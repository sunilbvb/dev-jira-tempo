"""CLI handler for `tempo-log export` command.

Exports timesheets and worklog history to CSV, JSON, or printable HTML format.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date as dt_date, timedelta
from pathlib import Path
from typing import Any

from ..config import Settings
from ..export import ExportItem, generate_csv, generate_html, generate_json
from ..journal import SQLiteJournal
from ..service import TempoService

logger = logging.getLogger(__name__)


def _get_service(target: Settings | TempoService | None) -> TempoService | None:
    if isinstance(target, TempoService):
        return target
    if isinstance(target, Settings):
        return TempoService(target)
    return None


def run_export(args: argparse.Namespace, target: Settings | TempoService | None = None) -> int:
    """Execute timesheet export."""
    fmt = getattr(args, "format", "csv").lower()
    from_date = getattr(args, "from_date", None)
    to_date = getattr(args, "to_date", None)
    service = _get_service(target)

    items: list[ExportItem] = []

    # Try fetching from Tempo API if remote credentials available
    if service and service.tempo_client:
        try:
            today = dt_date.today()
            f_d = from_date or (today - timedelta(days=7)).isoformat()
            t_d = to_date or today.isoformat()
            logs = service.tempo_client.list_worklogs(from_date=f_d, to_date=t_d)
            for w in logs:
                issue_info = w.get("issue", {})
                issue_key = issue_info.get("key") or str(issue_info.get("id", "UNKNOWN"))
                items.append(
                    ExportItem(
                        date=w.get("startDate", ""),
                        issue=issue_key,
                        hours=(w.get("timeSpentSeconds", 0) / 3600),
                        start_time=w.get("startTime", "")[:5],
                        tempo_id=w.get("tempoWorklogId", ""),
                        description=w.get("description", ""),
                    )
                )
        except Exception as exc:
            logger.warning("Could not fetch remote worklogs for export: %s", exc)

    # Fallback to local SQLite journal audit if no remote items fetched
    if not items:
        j = SQLiteJournal()
        logs = j.query(from_date=from_date, to_date=to_date, limit=200)
        for w in logs:
            items.append(
                ExportItem(
                    date=w.get("start_date", ""),
                    issue=w.get("issue_key") or str(w.get("issue_id", "UNKNOWN")),
                    hours=float(w.get("hours", 0.0)),
                    start_time=w.get("start_time", "")[:5],
                    tempo_id=w.get("tempo_worklog_id", ""),
                    description=w.get("description", ""),
                )
            )

    if from_date:
        items = [i for i in items if i.date >= from_date]
    if to_date:
        items = [i for i in items if i.date <= to_date]

    if fmt == "json":
        rendered = generate_json(items)
    elif fmt == "html":
        rendered = generate_html(items)
    else:
        rendered = generate_csv(items)

    out_path = getattr(args, "output", None)
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(rendered, encoding="utf-8")
        print(f"Exported {len(items)} worklogs to {p} ({fmt.upper()})")
    else:
        print(rendered)

    return 0
