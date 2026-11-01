"""Timesheet export generator for CSV, JSON, and printable HTML formats.

Pure Python standard library (no extra template or rendering pip dependencies).
"""

from __future__ import annotations

import csv
import html
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ExportItem:
    date: str
    issue: str
    hours: float
    description: str
    tempo_id: int | str = ""
    start_time: str = ""


def generate_csv(items: list[ExportItem]) -> str:
    """Generate CSV string for items."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Date", "Issue", "Hours", "StartTime", "TempoID", "Description"])
    for i in items:
        writer.writerow([i.date, i.issue, f"{i.hours:.2f}", i.start_time, i.tempo_id, i.description])
    return buf.getvalue()


def generate_json(items: list[ExportItem]) -> str:
    """Generate structured JSON representation."""
    data = {
        "total_items": len(items),
        "total_hours": round(sum(i.hours for i in items), 2),
        "worklogs": [
            {
                "date": i.date,
                "issue": i.issue,
                "hours": i.hours,
                "start_time": i.start_time,
                "tempo_id": i.tempo_id,
                "description": i.description,
            }
            for i in items
        ],
    }
    return json.dumps(data, indent=2)


def generate_html(items: list[ExportItem], title: str = "Tempo Timesheet Report") -> str:
    """Generate clean, standalone printable HTML report."""
    total_hours = sum(i.hours for i in items)
    issues_summary: dict[str, float] = {}
    for i in items:
        issues_summary[i.issue] = issues_summary.get(i.issue, 0.0) + i.hours

    summary_rows = "".join(
        f"<tr><td><code>{html.escape(k)}</code></td><td>{v:.2f}h</td></tr>"
        for k, v in sorted(issues_summary.items(), key=lambda x: x[1], reverse=True)
    )

    worklog_rows = "".join(
        f"""<tr>
            <td>{html.escape(i.date)}</td>
            <td><strong>{html.escape(i.issue)}</strong></td>
            <td>{i.start_time or '-'}</td>
            <td>{i.hours:.2f}h</td>
            <td><small>{html.escape(str(i.tempo_id or '-'))}</small></td>
            <td>{html.escape(i.description).replace(chr(10), '<br>')}</td>
        </tr>"""
        for i in items
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 30px; color: #1e293b; background: #fff; }}
  h1 {{ margin-bottom: 4px; color: #0f172a; }}
  .meta {{ color: #64748b; font-size: 14px; margin-bottom: 24px; }}
  .summary-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 24px; max-width: 400px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 13px; vertical-align: top; }}
  th {{ background: #f1f5f9; font-weight: 600; color: #475569; }}
  code {{ background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
  .badge {{ display: inline-block; padding: 3px 8px; border-radius: 9999px; font-size: 12px; background: #dbeafe; color: #1e40af; font-weight: 500; }}
  @media print {{ body {{ margin: 0; }} }}
</style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="meta">Generated automatically by tempo-log &bull; Total Time: <span class="badge">{total_hours:.2f} Hours</span></div>

  <div class="summary-card">
    <h3 style="margin-top:0; margin-bottom: 8px; font-size: 14px;">Hours by Issue</h3>
    <table>
      <thead><tr><th>Issue</th><th>Hours</th></tr></thead>
      <tbody>{summary_rows}</tbody>
    </table>
  </div>

  <h3>Detailed Worklog Entries</h3>
  <table>
    <thead>
      <tr>
        <th style="width:100px;">Date</th>
        <th style="width:110px;">Issue</th>
        <th style="width:70px;">Start</th>
        <th style="width:70px;">Hours</th>
        <th style="width:80px;">ID</th>
        <th>Description</th>
      </tr>
    </thead>
    <tbody>{worklog_rows}</tbody>
  </table>
</body>
</html>"""
