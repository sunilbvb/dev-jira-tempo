"""Submission safety checks: duration rounding, duplicate detection, and daily cap/overlap warnings."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any


def round_duration(hours: float, round_minutes: int | None = None) -> float:
    """Round hours up to nearest round_minutes increment.

    If round_minutes is None or <= 0, returns original hours.
    """
    if hours <= 0 or not round_minutes or round_minutes <= 0:
        return hours

    mins = hours * 60.0
    # Avoid float precision artifacts (e.g., 15.000000000000002)
    mins_rounded = math.ceil(round(mins, 6) / round_minutes) * round_minutes
    return round(mins_rounded / 60.0, 4)


def _normalize_time(t_str: str) -> str:
    """Normalize time string to HH:MM:SS."""
    if not t_str:
        return "00:00:00"
    parts = t_str.split(":")
    if len(parts) == 2:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:00"
    if len(parts) == 3:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"
    return t_str


def _time_to_minutes(t_str: str) -> int:
    """Convert HH:MM or HH:MM:SS string to minutes from midnight."""
    norm = _normalize_time(t_str)
    try:
        parts = norm.split(":")
        h, m = int(parts[0]), int(parts[1])
        return (h * 60 + m) % (24 * 60)
    except (ValueError, IndexError):
        return 0


def _minutes_to_time(mins: int) -> str:
    """Convert minutes from midnight to HH:MM string."""
    h = (mins // 60) % 24
    m = mins % 60
    return f"{h:02d}:{m:02d}"


def _extract_issue_id(entry: dict[str, Any]) -> int | str | None:
    """Safely extract issue identifier (numeric id or string key) from a dict."""
    issue_val = entry.get("issue")
    issue_id = None
    if isinstance(issue_val, dict):
        issue_id = issue_val.get("id")
    elif issue_val is not None:
        issue_id = issue_val
    if not issue_id:
        issue_id = entry.get("issue_id") or entry.get("issueId")
    if issue_id is not None:
        try:
            return int(issue_id)
        except (ValueError, TypeError):
            return str(issue_id)
    return None


def find_duplicates(
    candidate_entries: list[dict[str, Any]],
    existing_worklogs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compare candidate entries against existing Tempo worklogs.

    Returns tuple of (unique_entries, duplicate_entries). Matching is based on
    (issue_id, start_date, start_time). Intra-batch duplicates within candidates are also caught.
    """
    existing_set: set[tuple[int | str | None, str, str]] = set()

    for wl in existing_worklogs:
        issue_id = _extract_issue_id(wl)
        date = wl.get("startDate") or wl.get("date")
        time_str = _normalize_time(wl.get("startTime") or wl.get("time") or "")
        if date:
            existing_set.add((issue_id, str(date), time_str))

    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen_keys: set[tuple[int | str | None, str, str]] = set()

    for entry in candidate_entries:
        issue_id = _extract_issue_id(entry)
        date = entry.get("date") or entry.get("startDate")
        time_str = _normalize_time(entry.get("time") or entry.get("startTime") or "")

        key = (issue_id, str(date) if date else "", time_str)
        if key in existing_set or key in seen_keys:
            duplicates.append(entry)
        else:
            unique.append(entry)
            seen_keys.add(key)

    return unique, duplicates


def validate_submission_safety(
    candidate_entries: list[dict[str, Any]],
    existing_worklogs: list[dict[str, Any]] | None = None,
    daily_cap_hours: float | None = None,
) -> list[str]:
    """Validate candidate entries for daily hours cap and time range overlaps.

    Returns a list of human-readable warning strings.
    """
    warnings: list[str] = []
    existing = existing_worklogs or []

    # 1. Daily Cap Check
    daily_hours: dict[str, float] = {}
    daily_existing_hours: dict[str, float] = {}

    for wl in existing:
        date = str(wl.get("startDate") or wl.get("date") or "")
        sec = wl.get("timeSpentSeconds")
        try:
            h = float(sec) / 3600.0 if sec is not None else float(wl.get("hours", 0) or 0)
        except (ValueError, TypeError):
            h = 0.0
        if date:
            daily_hours[date] = daily_hours.get(date, 0.0) + h
            daily_existing_hours[date] = daily_existing_hours.get(date, 0.0) + h

    for entry in candidate_entries:
        date = str(entry.get("date") or entry.get("startDate") or "")
        try:
            h = float(entry.get("hours", 0) or 0)
        except (ValueError, TypeError):
            h = 0.0
        if date:
            daily_hours[date] = daily_hours.get(date, 0.0) + h

    if daily_cap_hours is not None and daily_cap_hours > 0:
        for date, total_h in sorted(daily_hours.items()):
            if total_h > daily_cap_hours:
                exist_h = daily_existing_hours.get(date, 0.0)
                new_h = total_h - exist_h
                warnings.append(
                    f"Date {date}: Total hours ({total_h:.2f}h = {exist_h:.2f}h existing + {new_h:.2f}h new) exceed daily cap of {daily_cap_hours:.2f}h."
                )

    # 2. Overlap Check
    # Group all entries (existing + candidate) by date
    by_date: dict[str, list[dict[str, Any]]] = {}

    for wl in existing:
        date = str(wl.get("startDate") or wl.get("date") or "")
        if not date:
            continue
        sec = wl.get("timeSpentSeconds")
        try:
            h = float(sec) / 3600.0 if sec is not None else float(wl.get("hours", 0) or 0)
        except (ValueError, TypeError):
            h = 0.0
        if h <= 0:
            continue
        raw_t = wl.get("startTime") or wl.get("time")
        if not raw_t:
            continue
        t_str = str(raw_t)
        label = f"Existing worklog #{wl.get('id', wl.get('tempoWorklogId', ''))}"
        by_date.setdefault(date, []).append(
            {"label": label, "start": _time_to_minutes(t_str), "hours": h, "time_str": t_str}
        )

    for i, entry in enumerate(candidate_entries):
        date = str(entry.get("date") or entry.get("startDate") or "")
        if not date:
            continue
        try:
            h = float(entry.get("hours", 0) or 0)
        except (ValueError, TypeError):
            h = 0.0
        if h <= 0:
            continue
        raw_t = entry.get("time") or entry.get("startTime")
        if not raw_t:
            continue
        t_str = str(raw_t)
        issue_label = entry.get("issue") or entry.get("issue_id") or f"Entry #{i+1}"
        by_date.setdefault(date, []).append(
            {"label": str(issue_label), "start": _time_to_minutes(t_str), "hours": h, "time_str": t_str}
        )

    for date, items in sorted(by_date.items()):
        # Check all pairs in items
        n = len(items)
        for i in range(n):
            for j in range(i + 1, n):
                item1 = items[i]
                item2 = items[j]

                start1 = item1["start"]
                end1 = start1 + int(round(item1["hours"] * 60))
                start2 = item2["start"]
                end2 = start2 + int(round(item2["hours"] * 60))

                # Overlap condition: start1 < end2 and start2 < end1
                if start1 < end2 and start2 < end1:
                    range1 = f"{_minutes_to_time(start1)}-{_minutes_to_time(end1)}"
                    range2 = f"{_minutes_to_time(start2)}-{_minutes_to_time(end2)}"
                    warnings.append(
                        f"Date {date}: Time overlap between '{item1['label']}' ({range1}) and '{item2['label']}' ({range2})."
                    )

    return warnings
