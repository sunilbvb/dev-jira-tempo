"""Parse a markdown worklog into worklog items.

Format (headings and blocks may repeat; see README for details):

    ## 2026-10-12 (Short title for the block)
    Time: 10:00-10:30 (30m) | Ticket: PROJ-123 [id:10042]
    - First detail
    - Second detail

A block is a `Time:` line plus the `- ` bullets that follow it. The title is
the text after the date in the nearest `##`/`###` heading. The duration comes
from the `(30m)` / `(1h 15m)` marker, or from the time range when absent. A
block whose ticket is not a key (e.g. `none`) is reported as unassigned.
Blocks on the same ticket are merged into one item.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DATE_HEADING = re.compile(r"^#{2,3}\s+(\d{4}-\d{2}-\d{2})?\s*(?:[—–-]\s*)?(.*)$")
TIME_LINE = re.compile(r"^Time:\s*(.*)$")
RANGE = re.compile(r"(\d{1,2}):(\d{2})\s*[–—-]\s*(\d{1,2}):(\d{2})")
DURATION = re.compile(r"\((?:(\d+)h)?\s*(?:(\d+)m)?[^)]*\)")
KEY = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
ISSUE_ID = re.compile(r"\[id:(\d+)\]")


@dataclass
class Block:
    date: str
    title: str
    minutes: int
    issue: str | int | None
    bullets: list[str] = field(default_factory=list)
    skip_reason: str | None = None
    meeting: bool = False
    start_minute: int | None = None


def _title_from_heading(text: str) -> str:
    text = text.strip()
    match = re.match(r"^\((.*)\)$", text)
    return (match.group(1) if match else text).strip(" :")


def _minutes(time_part: str) -> int | None:
    duration = DURATION.search(time_part)
    if duration and (duration.group(1) or duration.group(2)):
        return int(duration.group(1) or 0) * 60 + int(duration.group(2) or 0)
    span = RANGE.search(time_part)
    if span:
        start = int(span.group(1)) * 60 + int(span.group(2))
        end = int(span.group(3)) * 60 + int(span.group(4))
        if end < start:
            end += 24 * 60
        return end - start
    return None


def _range_start(time_part: str) -> int | None:
    span = RANGE.search(time_part)
    return int(span.group(1)) * 60 + int(span.group(2)) if span else None


def parse_blocks(text: str, date: str) -> list[Block]:
    """Return the blocks that belong to `date`, in file order."""
    blocks: list[Block] = []
    heading_date: str | None = None
    heading_title = ""
    parent_title = ""
    current: Block | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        heading = DATE_HEADING.match(line) if line.startswith("#") else None
        if heading:
            if heading.group(1):
                heading_date = heading.group(1)
            heading_title = _title_from_heading(heading.group(2))
            if line.startswith("## "):
                parent_title = heading_title
            elif KEY.match(heading_title) and parent_title:
                heading_title = parent_title
            current = None
            continue

        time_line = TIME_LINE.match(line.strip())
        if time_line:
            current = None
            if heading_date != date:
                continue
            body = time_line.group(1)
            time_part, _, ticket_part = body.partition("|")
            minutes = _minutes(time_part)
            if minutes is None:
                continue
            issue_id = ISSUE_ID.search(ticket_part)
            key = KEY.search(ticket_part)
            ticket = ticket_part.split("Ticket:", 1)[-1].strip().lower()
            issue: str | int | None = None
            reason = None
            if "sub-block" in ticket or "see below" in ticket or "not for timesheet" in raw.lower() + heading_title.lower():
                reason = "container or note block, not for the timesheet"
            elif issue_id:
                issue = int(issue_id.group(1))
            elif key:
                issue = key.group(1)
            else:
                reason = "no ticket"
            current = Block(
                date, heading_title, minutes, issue, [], reason,
                meeting="meeting" in time_part.lower(),
                start_minute=_range_start(time_part),
            )
            blocks.append(current)
            continue

        if current is not None and line.lstrip().startswith("- "):
            bullet = line.lstrip()[2:].strip()
            if "not for timesheet" in bullet.lower():
                current.skip_reason = "marked not for the timesheet"
            else:
                current.bullets.append(bullet)

    return blocks


@dataclass
class MergedItem:
    issue: str | int
    minutes: int
    titles: list[str]
    bullets: list[str]
    fixed_start: int | None = None

    def description(self) -> str:
        title = self.titles[0]
        if len(self.titles) > 1:
            title = f"{title} (+{len(self.titles) - 1} related)"
        lines = [f"{title}:"] if title else []
        lines += [f"- {b}" for b in self.bullets]
        return "\n".join(lines)


def _dedupe_meetings(blocks: list[Block], window: int = 15) -> list[Block]:
    """Drop duplicate records of one meeting: same ticket and a start time
    within `window` minutes. The longer record is kept; bullets are joined."""
    kept: list[Block] = []
    for block in blocks:
        twin = next(
            (
                k
                for k in kept
                if block.meeting
                and k.meeting
                and block.issue is not None
                and k.issue == block.issue
                and block.start_minute is not None
                and k.start_minute is not None
                and abs(k.start_minute - block.start_minute) <= window
            ),
            None,
        )
        if twin is None:
            kept.append(block)
            continue
        for bullet in block.bullets:
            if bullet not in twin.bullets:
                twin.bullets.append(bullet)
        if block.minutes > twin.minutes:
            twin.minutes = block.minutes
            twin.title = block.title
    return kept


def merge_by_issue(blocks: list[Block]) -> list[MergedItem]:
    """Merge assigned work blocks on the same ticket into one item, keeping
    the order in which each ticket first appears. Meetings (a `meeting` marker
    on the Time line) are only merged with the same-titled meeting."""
    merged: dict[object, MergedItem] = {}
    for block in _dedupe_meetings(blocks):
        if block.issue is None or block.skip_reason:
            continue
        key = (block.issue, block.title) if block.meeting else block.issue
        item = merged.get(key)
        if item is None:
            merged[key] = MergedItem(
                block.issue,
                block.minutes,
                [block.title],
                list(block.bullets),
                block.start_minute if block.meeting else None,
            )
        else:
            item.minutes += block.minutes
            if block.title and block.title not in item.titles:
                item.titles.append(block.title)
            item.bullets.extend(block.bullets)
    return list(merged.values())
