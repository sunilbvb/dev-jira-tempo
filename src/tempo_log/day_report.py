"""Summarise one day of worklogs: total, overlaps, gaps and rule violations."""

from __future__ import annotations

from dataclasses import dataclass

from .schedule import format_clock


@dataclass(frozen=True)
class DayEntry:
    worklog_id: int
    start: int  # minutes since midnight
    minutes: int
    issue: str
    title: str = ""

    @property
    def end(self) -> int:
        return self.start + self.minutes


def analyse(entries: list[DayEntry], round_minutes: int, max_day_minutes: int) -> dict:
    ordered = sorted(entries, key=lambda e: (e.start, e.worklog_id))
    overlaps, gaps, off_step = [], [], []
    for prev, cur in zip(ordered, ordered[1:]):
        if cur.start < prev.end:
            overlaps.append((prev, cur))
        elif cur.start > prev.end:
            gaps.append((prev.end, cur.start))
    for e in ordered:
        if e.minutes % round_minutes:
            off_step.append(e)
    total = sum(e.minutes for e in ordered)
    return {
        "entries": ordered,
        "total_minutes": total,
        "overlaps": overlaps,
        "gaps": gaps,
        "off_step": off_step,
        "over_cap": total > max_day_minutes,
    }


def render(report: dict, max_day_minutes: int) -> list[str]:
    lines = []
    for e in report["entries"]:
        lines.append(
            f"{e.worklog_id}  {format_clock(e.start)[:5]}-{format_clock(e.end)[:5]}  "
            f"{e.minutes / 60:g}h  {e.issue}  {e.title}"
        )
    lines.append(f"Total: {report['total_minutes'] / 60:g}h across {len(report['entries'])} entries.")
    for a, b in report["overlaps"]:
        lines.append(f"OVERLAP: {a.worklog_id} ({a.issue}) and {b.worklog_id} ({b.issue})")
    for start, end in report["gaps"]:
        lines.append(f"Gap: {format_clock(start)[:5]}-{format_clock(end)[:5]} ({end - start}m)")
    for e in report["off_step"]:
        lines.append(f"Not on the rounding step: {e.worklog_id} ({e.minutes}m)")
    if report["over_cap"]:
        lines.append(f"OVER the {max_day_minutes / 60:g}h daily cap.")
    return lines
