"""Analyzer for free-form session journals (read-only pre-submission report).

Unlike ``worklog_parser`` (strict ``Tempo: KEY | HH:MM-HH:MM`` lines), this
module understands a looser journal style commonly written by hand or by
coding assistants::

    ## 2026-09-24 14:28 UTC — PROJ-12: short title
    Time estimate: 1h 30m | Ticket: PROJ-12 [id:10042]

    - bullet describing the work

    ### PROJ-13 — fixed (15m)
    Paragraph describing a sub-task.

    ## 2026-09-24 17:30 UTC — Another session
    Time: 17:30–19:00 UTC (1h30m) | Ticket: none

It never talks to Tempo by itself: callers pass an optional resolver and the
already-logged worklogs, and get back a structured report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .safety import round_duration

SESSION_HEADING = re.compile(
    r"^##\s+(\d{4}-\d{2}-\d{2})"
    r"(?:\s+(\d{1,2}:\d{2}))?"
    r"(?:\s+[A-Za-z]{2,5})?"
    r"(?:\s*[—–-]+\s*(.*))?$"
)
SUB_HEADING = re.compile(r"^###\s+([A-Z][A-Z0-9]+-\d+)(?:\s*\[id:\s*(\d+)\])?\s*[—–:-]+\s*(.*)$", re.IGNORECASE)
ISSUE_KEY = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
ISSUE_ID_TAG = re.compile(r"\[id:\s*(\d+)\]", re.IGNORECASE)
DURATION = re.compile(r"(?<![\d:])(?:(\d+)\s*h(?:\s*(\d+)\s*m)?|(\d+)\s*m(?:in)?)\b", re.IGNORECASE)
TIME_RANGE = re.compile(r"(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})")
META_LINE = re.compile(r"^(time estimate|time|ticket|attended)\s*:", re.IGNORECASE)
TICKET_FIELD = re.compile(r"ticket\s*:\s*(.*)$", re.IGNORECASE)

DEFAULT_DROP_PATTERNS = [
    r"^files\s*:",
    r"^internal\s+notes\s*:",
    r"`[^`]+`",
    r"(?:^|[\s(])(?:/[a-zA-Z0-9_\.\-]+)+",
    r"(?:^|[\s(])(?:src|tests|frontend|lib|app|pkg)/[a-zA-Z0-9_\.\-/]+",
    r"\b[a-zA-Z0-9_\-]+\.(?:py|js|ts|jsx|tsx|json|md|html|css|yml|yaml|sh|sql|toml)\b",
    r"\b(?:pytest|npm\s+(?:test|run)|git\s+\w+|tempo-log\b|python[3]?\s+-m)",
]


def parse_duration_minutes(text: str) -> int | None:
    """Return total minutes for the first duration like '1h 30m', '45m', '2h' in text."""
    match = DURATION.search(text)
    if not match:
        return None
    if match.group(3):
        return int(match.group(3))
    return int(match.group(1)) * 60 + int(match.group(2) or 0)


def _fmt_minutes(minutes: int | None) -> str:
    if minutes is None:
        return "?"
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}h{m:02d}m"
    return f"{h}h" if h else f"{m}m"


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _from_minutes(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def clean_title(title: str, ticket: str | None = None, parent_title: str | None = None) -> str:
    """Clean title by stripping ticket prefix and generic status words."""
    cleaned = title.strip()
    if ticket:
        cleaned = re.sub(rf"^{re.escape(ticket)}\s*[:—–-]+\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[—–-]+\s*(fixed|done|completed|investigated|resolved)\b.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    if not cleaned or cleaned.lower() in ("fixed", "done", "completed", "investigated", "resolved"):
        if parent_title:
            cleaned = parent_title.strip()
            if ticket:
                cleaned = re.sub(rf"^{re.escape(ticket)}\s*[:—–-]+\s*", "", cleaned, flags=re.IGNORECASE)
        else:
            cleaned = title.strip()
    return cleaned or title.strip()


def clean_bullet(bullet: str) -> str:
    """Trim a bullet to one sentence and cap at 160 chars."""
    match = re.search(r"^(.*?[.!?])(?:\s+|$)", bullet)
    sentence = match.group(1) if match else bullet
    sentence = sentence.strip()
    if len(sentence) > 160:
        sentence = sentence[:157].rstrip() + "..."
    return sentence


@dataclass
class JournalEntry:
    date: str
    title: str
    line_number: int
    start: str | None = None
    end: str | None = None
    ticket: str | None = None
    issue_id: int | None = None
    minutes: int | None = None
    kind: str = "session"  # "session" | "sub"
    parent_title: str | None = None
    status: str | None = None
    suggested_ticket: str | None = None
    bullets: list[str] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    is_container: bool = False
    is_meeting: bool = False
    attended: bool = True
    heading_time: str | None = None

    def description(
        self,
        clean: bool = True,
        drop_patterns: list[str] | None = None,
        max_bullets: int = 4,
    ) -> str:
        """Title line plus bullet points with drop patterns and bullet limits."""
        title_line = clean_title(self.title, self.ticket, self.parent_title) if clean else self.title.strip()
        lines = [title_line]

        patterns = drop_patterns if drop_patterns is not None else DEFAULT_DROP_PATTERNS
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]

        points: list[str] = []
        for b in self.bullets:
            if clean and any(cp.search(b) for cp in compiled):
                continue
            cb = clean_bullet(b) if clean else b.strip()
            if cb:
                points.append(cb)

        if not points and self.body:
            for b in self.body:
                if clean and any(cp.search(b) for cp in compiled):
                    continue
                cb = clean_bullet(b) if clean else b.strip()
                if cb:
                    points.append(cb)
                    break

        if clean:
            points = points[:max_bullets]

        lines.extend(f"- {p}" for p in points)
        return "\n".join(lines)


@dataclass
class FixedBlock:
    start: str
    end: str
    ticket: str | None = None
    title: str = "Fixed block"
    issue_id: int | None = None


FIXED_BLOCK_RE = re.compile(
    r"^(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})(?:@([A-Za-z0-9_\-]+))?(?::(.*))?$"
)


def parse_fixed_blocks(conf_str: str | None) -> list[FixedBlock]:
    """Parse TEMPO_FIXED_BLOCKS config string (e.g. '14:00-15:00@LUNCH-KEY:Lunch')."""
    if not conf_str:
        return []
    blocks: list[FixedBlock] = []
    for part in conf_str.split(";"):
        part = part.strip()
        if not part:
            continue
        m = FIXED_BLOCK_RE.match(part)
        if m:
            start, end, ticket, title = m.group(1), m.group(2), m.group(3), m.group(4)
            blocks.append(
                FixedBlock(
                    start=start,
                    end=end,
                    ticket=ticket or None,
                    title=(title.strip() if title else "Fixed block"),
                )
            )
    return blocks


def parse_journal(
    content: str,
    heading_time_mode: str = "start",
    meeting_prefix: str = "Meeting:",
) -> list[JournalEntry]:
    """Parse every session / sub-entry in the journal (all dates)."""
    entries: list[JournalEntry] = []
    session: JournalEntry | None = None
    current: JournalEntry | None = None

    for idx, raw in enumerate(content.splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()

        heading = SESSION_HEADING.match(stripped)
        if heading and not stripped.startswith("###"):
            date, time_str, title = heading.group(1), heading.group(2), (heading.group(3) or "").strip()
            session = JournalEntry(date=date, title=title or "(untitled)", line_number=idx)
            session.heading_time = time_str
            if heading_time_mode == "end":
                session.end = time_str
            else:
                session.start = time_str
            key = ISSUE_KEY.match(title)
            if key:
                session.ticket = key.group(1)
            if title.lower().startswith(meeting_prefix.lower()):
                session.is_meeting = True
            entries.append(session)
            current = session
            continue

        sub = SUB_HEADING.match(stripped)
        if sub and session is not None:
            key, sub_id, rest = sub.group(1), sub.group(2), sub.group(3)
            status = rest.split("(")[0].strip(" -—–") or None
            paren = re.search(r"\(([^)]*)\)", rest)
            minutes = parse_duration_minutes(paren.group(1)) if paren else None
            title_text = f"{key}: {status}" if status else key
            current = JournalEntry(
                date=session.date,
                title=title_text,
                line_number=idx,
                ticket=key,
                minutes=minutes,
                kind="sub",
                parent_title=session.title,
                status=status,
                issue_id=int(sub_id) if sub_id else None,
            )
            if title_text.lower().startswith(meeting_prefix.lower()):
                current.is_meeting = True
            session.is_container = True
            entries.append(current)
            continue

        if current is None:
            continue

        if META_LINE.match(stripped):
            _apply_meta(current, stripped, heading_time_mode)
            continue

        if re.search(r"\battended\s*:\s*(no|false|0)\b", stripped, re.IGNORECASE):
            current.attended = False

        if stripped.startswith("- "):
            current.bullets.append(stripped[2:].strip())
        elif raw.startswith((" ", "\t")) and current.bullets and stripped:
            current.bullets[-1] += " " + stripped
        elif stripped and not stripped.startswith(("---", "#")):
            current.body.append(stripped)

    return entries


def _apply_meta(entry: JournalEntry, line: str, heading_time_mode: str = "start") -> None:
    for part in line.split("|"):
        part = part.strip()
        low = part.lower()
        if re.search(r"\battended\s*:\s*(no|false|0)\b", low):
            entry.attended = False
            continue
        ticket_field = TICKET_FIELD.match(part)
        if ticket_field:
            value = ticket_field.group(1).strip()
            id_tag = ISSUE_ID_TAG.search(value)
            if id_tag:
                entry.issue_id = int(id_tag.group(1))
            key = ISSUE_KEY.match(value)
            if key:
                entry.ticket = key.group(1)
            elif value.lower().startswith("none"):
                entry.ticket = None
                hint = ISSUE_KEY.search(value)
                if hint:
                    entry.suggested_ticket = hint.group(1)
        elif re.match(r"time(\s+estimate)?\s*:", low):
            if "per-ticket" in low or "below" in low:
                entry.is_container = True
                continue
            rng = TIME_RANGE.search(part)
            if rng:
                sh, sm, eh, em = (int(g) for g in rng.groups())
                entry.start = f"{sh:02d}:{sm:02d}"
                entry.end = f"{eh:02d}:{em:02d}"
                span = (eh * 60 + em) - (sh * 60 + sm)
                after = part[rng.end():]
                entry.minutes = parse_duration_minutes(after) or (span if span > 0 else None)
            else:
                entry.minutes = parse_duration_minutes(part.split(":", 1)[1])
                if heading_time_mode == "end" and entry.end and not entry.start and entry.minutes:
                    entry.start = _from_minutes(max(0, _to_minutes(entry.end) - entry.minutes))


def consolidate_entries(
    entries: list[JournalEntry],
    mode: str = "contiguous",
) -> list[JournalEntry]:
    """Merge entries on the same issue into one entry before rounding.

    mode: 'contiguous' (adjacent entries on same ticket) or 'day' (all entries on same ticket).
    """
    if not entries or mode not in ("contiguous", "day"):
        return list(entries)

    def _merge_group(group: list[JournalEntry]) -> JournalEntry:
        first = group[0]
        total_mins = (
            sum(e.minutes for e in group if e.minutes is not None)
            if any(e.minutes is not None for e in group)
            else None
        )

        seen_bullets: set[str] = set()
        merged_bullets: list[str] = []
        for e in group:
            for b in e.bullets:
                if b not in seen_bullets:
                    seen_bullets.add(b)
                    merged_bullets.append(b)

        seen_body: set[str] = set()
        merged_body: list[str] = []
        for e in group:
            for b in e.body:
                if b not in seen_body:
                    seen_body.add(b)
                    merged_body.append(b)

        issue_id = next((e.issue_id for e in group if e.issue_id is not None), None)

        return JournalEntry(
            date=first.date,
            title=first.title,
            line_number=first.line_number,
            start=first.start,
            end=group[-1].end if group[-1].end else None,
            ticket=first.ticket,
            issue_id=issue_id,
            minutes=total_mins,
            kind=first.kind,
            parent_title=first.parent_title,
            status=first.status,
            suggested_ticket=first.suggested_ticket,
            bullets=merged_bullets,
            body=merged_body,
            is_container=False,
            is_meeting=first.is_meeting,
            attended=first.attended,
            heading_time=first.heading_time,
        )

    if mode == "contiguous":
        result: list[JournalEntry] = []
        i = 0
        while i < len(entries):
            cur = entries[i]
            if cur.ticket is None or cur.is_container:
                result.append(cur)
                i += 1
                continue
            group = [cur]
            j = i + 1
            while j < len(entries) and entries[j].ticket == cur.ticket and not entries[j].is_container:
                group.append(entries[j])
                j += 1
            if len(group) > 1:
                result.append(_merge_group(group))
            else:
                result.append(cur)
            i = j
        return result

    if mode == "day":
        result: list[JournalEntry] = []
        seen_tickets: set[str] = set()
        ticket_groups: dict[str, list[JournalEntry]] = {}
        for e in entries:
            if e.ticket is not None and not e.is_container:
                ticket_groups.setdefault(e.ticket, []).append(e)

        for e in entries:
            if e.ticket is None or e.is_container:
                result.append(e)
            elif e.ticket not in seen_tickets:
                seen_tickets.add(e.ticket)
                group = ticket_groups[e.ticket]
                if len(group) > 1:
                    result.append(_merge_group(group))
                else:
                    result.append(e)
        return result

    return list(entries)


# --------------------------------------------------------------------------- analysis


@dataclass
class PlannedEntry:
    entry: JournalEntry
    rounded_minutes: int | None
    start: str | None
    status: str  # READY | BLOCKED | SKIP | LOGGED (#id)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    is_logged: bool = False
    clean_description: bool = True
    drop_patterns: list[str] | None = None
    max_bullets: int = 4

    def to_batch(self) -> dict[str, Any]:
        return {
            "date": self.entry.date,
            "time": f"{self.start}:00" if self.start else None,
            "issue": self.entry.ticket,
            "issue_id": self.entry.issue_id,
            "hours": round((self.rounded_minutes or 0) / 60.0, 4),
            "description": self.entry.description(
                clean=self.clean_description,
                drop_patterns=self.drop_patterns,
                max_bullets=self.max_bullets,
            ),
        }


@dataclass
class AnalysisReport:
    date: str
    planned: list[PlannedEntry] = field(default_factory=list)
    day_warnings: list[str] = field(default_factory=list)
    day_info: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    total_minutes: int = 0
    ready_minutes: int = 0
    existing_minutes: int = 0
    cap_hours: float | None = None

    @property
    def ready(self) -> list[PlannedEntry]:
        return [p for p in self.planned if p.status == "READY" and not p.is_logged]

    @property
    def blocked(self) -> list[PlannedEntry]:
        return [p for p in self.planned if p.status == "BLOCKED" and not p.is_logged]

    @property
    def logged(self) -> list[PlannedEntry]:
        return [p for p in self.planned if p.is_logged]


Resolver = Callable[[str], "int | None"]


def analyze_day(
    entries: list[JournalEntry],
    date: str,
    *,
    round_minutes: int | None = 15,
    daily_cap_hours: float | None = None,
    resolver: Resolver | None = None,
    can_lookup: bool | None = None,
    existing_worklogs: list[dict[str, Any]] | None = None,
    sequential: bool = False,
    reserved: list[tuple[str, str]] | None = None,
    consolidate: str | None = None,
    heading_time: str = "start",
    meeting_issue: str | None = None,
    fixed_blocks: list[FixedBlock] | None = None,
    with_fixed_blocks: bool = False,
    duplicate_window_minutes: int = 15,
    allow_overlap: bool = False,
    drop_patterns: list[str] | None = None,
    max_bullets: int = 4,
) -> AnalysisReport:
    """Build a pre-submission report for one date. Pure: no network unless resolver does it."""
    report = AnalysisReport(date=date, cap_hours=daily_cap_hours)
    day = [e for e in entries if e.date == date]
    if not day:
        report.day_warnings.append(f"No journal entries found for {date}.")
        return report

    # Optional consolidation before rounding
    if consolidate:
        day = consolidate_entries(day, mode=consolidate)

    loggable = [e for e in day if not e.is_container]
    containers = [e for e in day if e.is_container]
    for c in containers:
        if not any(e.kind == "sub" and e.parent_title == c.title for e in day):
            report.day_warnings.append(
                f"Line {c.line_number}: '{_short(c.title)}' says time is logged per-ticket below, "
                "but no '### KEY - status (time)' sub-entries were recognised."
            )
            continue
        report.day_info.append(
            f"Line {c.line_number}: '{c.title}' is split into per-ticket sub-entries; its own time is not logged."
        )

    # Meetings default to meeting_issue if not already set
    for e in loggable:
        if e.is_meeting and not e.ticket and meeting_issue:
            e.ticket = meeting_issue

    # Fixed blocks support
    f_blocks = fixed_blocks or []
    all_reserved: list[tuple[str, str]] = list(reserved or [])
    for fb in f_blocks:
        all_reserved.append((fb.start, fb.end))
        report.day_info.append(f"Fixed block: {fb.title} ({fb.start}-{fb.end}) reserved.")

    if with_fixed_blocks:
        for fb in f_blocks:
            fb_mins = _to_minutes(fb.end) - _to_minutes(fb.start)
            fb_entry = JournalEntry(
                date=date,
                title=fb.title,
                line_number=0,
                start=fb.start,
                end=fb.end,
                ticket=fb.ticket,
                issue_id=fb.issue_id,
                minutes=fb_mins,
            )
            loggable.append(fb_entry)

    # Resolve numeric ids (file tag wins, then resolver).
    resolve_failures: set[str] = set()
    for e in loggable:
        if e.ticket and e.issue_id is None and resolver is not None:
            try:
                e.issue_id = resolver(e.ticket)
            except Exception:  # noqa: BLE001 - reported below as missing id
                e.issue_id = None
            if e.issue_id is None:
                resolve_failures.add(e.ticket)

    # Propose start times
    sessions_by_line = {s.line_number: s for s in day if s.kind == "session"}
    cursor: int | None = None
    parent_start: dict[str, int] = {}
    for s in sessions_by_line.values():
        if s.start:
            parent_start[s.title] = _to_minutes(s.start)

    seen_tickets: dict[str, int] = {}
    for e in loggable:
        if not e.attended:
            planned = PlannedEntry(
                entry=e,
                rounded_minutes=0,
                start=e.start,
                status="SKIP",
                drop_patterns=drop_patterns,
                max_bullets=max_bullets,
            )
            planned.notes.append("Meeting not attended (skipped)")
            report.planned.append(planned)
            continue

        rounded = None
        if e.minutes is not None:
            rounded = int(round(round_duration(e.minutes / 60.0, round_minutes) * 60))
        begin: int | None = None
        if e.start:
            begin = _to_minutes(e.start)
            if e.is_meeting and round_minutes:
                begin = _snap(begin, round_minutes)
        elif e.kind == "sub" and e.parent_title in parent_start and (cursor is None or cursor < parent_start[e.parent_title]):
            begin = parent_start[e.parent_title]
        elif cursor is not None:
            begin = cursor
        if begin is not None and rounded:
            cursor = begin + rounded

        planned = PlannedEntry(
            entry=e,
            rounded_minutes=rounded,
            start=_from_minutes(begin) if begin is not None else None,
            status="READY",
            drop_patterns=drop_patterns,
            max_bullets=max_bullets,
        )

        if not e.ticket:
            hint = f" (journal suggests {e.suggested_ticket})" if e.suggested_ticket else ""
            planned.problems.append(f"No Jira ticket{hint}")
        elif e.issue_id is None:
            planned.problems.append(f"No numeric issue id for {e.ticket}")
        if e.minutes is None:
            planned.problems.append("No duration given")
        if begin is not None and begin + (rounded or 0) > 24 * 60:
            planned.problems.append("Planned time runs past midnight - earlier entries are too long")
        if planned.start is None:
            planned.notes.append("No start time; Tempo default will be used")
        if e.minutes is not None and rounded != e.minutes:
            planned.notes.append(f"Rounded {_fmt_minutes(e.minutes)} -> {_fmt_minutes(rounded)}")
        if not e.bullets:
            planned.notes.append("No bullet points; description built from paragraph text")
        if e.status and re.search(r"already|duplicate|not fixed|investigated", e.status, re.IGNORECASE):
            planned.notes.append(f"Status is '{e.status}' - confirm this is billable")
        if e.ticket:
            if e.ticket in seen_tickets:
                planned.notes.append(f"{e.ticket} also logged at line {seen_tickets[e.ticket]} - consider consolidating")
            else:
                seen_tickets[e.ticket] = e.line_number

        if planned.problems:
            planned.status = "BLOCKED"
        report.planned.append(planned)

    if sequential:
        # Attended meetings act as reserved slots for other work
        meeting_slots = [
            (
                _from_minutes(_snap(_to_minutes(p.start), round_minutes or 15)),
                _from_minutes(
                    _snap(_to_minutes(p.start) + (p.rounded_minutes or 0), round_minutes or 15)
                ),
            )
            for p in report.planned
            if p.entry.is_meeting and p.entry.attended and p.start and p.rounded_minutes
        ]
        layout_reserved = all_reserved + meeting_slots
        _layout_sequential(report, round_minutes or 15, layout_reserved)

    # Estimates vs. wall clock
    if heading_time == "end":
        ordered = [s for s in day if s.kind == "session" and s.end]
        for prev, cur in zip(ordered, ordered[1:]):
            gap = _to_minutes(cur.end) - _to_minutes(prev.end)
            claimed = cur.minutes or 0
            if gap > 0 and claimed > gap:
                report.day_warnings.append(
                    f"'{_short(cur.title)}' claims {_fmt_minutes(claimed)} but elapsed time since previous "
                    f"entry is {_fmt_minutes(gap)} ({prev.end} -> {cur.end}) - estimate may be inflated."
                )
    else:
        ordered = [s for s in day if s.kind == "session" and s.start]
        for cur, nxt in zip(ordered, ordered[1:]):
            gap = _to_minutes(nxt.start) - _to_minutes(cur.start)
            if cur.is_container:
                claimed = sum(e.minutes or 0 for e in day if e.kind == "sub" and e.parent_title == cur.title)
            else:
                claimed = cur.minutes or 0
            if gap > 0 and claimed > gap:
                report.day_warnings.append(
                    f"'{_short(cur.title)}' claims {_fmt_minutes(claimed)} but the next entry starts "
                    f"{_fmt_minutes(gap)} later ({cur.start} -> {nxt.start}) - estimate may be inflated."
                )

    # Match existing worklogs in Tempo (F2: skip already logged)
    existing = existing_worklogs or []
    report.existing_minutes = sum(int(w.get("timeSpentSeconds", 0)) // 60 for w in existing)
    matched_existing_ids: set[Any] = set()

    if existing:
        report.day_info.append(
            f"Tempo already has {len(existing)} worklog(s) for {date} totalling {_fmt_minutes(report.existing_minutes)}."
        )

        for p in report.planned:
            if p.status == "SKIP":
                continue
            matched_wl: dict[str, Any] | None = None
            for wl in existing:
                wl_issue_id = _extract_issue_id(wl)
                wl_issue_key = (
                    wl.get("issue", {}).get("key")
                    if isinstance(wl.get("issue"), dict)
                    else None
                )
                issue_match = (
                    p.entry.issue_id is not None
                    and wl_issue_id is not None
                    and str(p.entry.issue_id) == str(wl_issue_id)
                ) or (
                    p.entry.ticket
                    and wl_issue_key
                    and p.entry.ticket.upper() == str(wl_issue_key).upper()
                )
                if not issue_match:
                    continue

                wl_start = wl.get("startTime") or wl.get("time")
                wl_mins = int(wl.get("timeSpentSeconds", 0)) // 60

                time_match = False
                if p.start and wl_start:
                    p_start_m = _to_minutes(p.start)
                    p_end_m = p_start_m + (p.rounded_minutes or 0)
                    wl_start_m = _to_minutes(wl_start[:5])
                    wl_end_m = wl_start_m + wl_mins
                    overlaps = max(p_start_m, wl_start_m) < min(p_end_m, wl_end_m)
                    close_start = abs(p_start_m - wl_start_m) <= duplicate_window_minutes
                    if overlaps or close_start:
                        time_match = True
                elif not p.start and not wl_start:
                    if abs((p.rounded_minutes or 0) - wl_mins) <= duplicate_window_minutes:
                        time_match = True

                if time_match:
                    matched_wl = wl
                    break

            if matched_wl:
                wl_id = matched_wl.get("tempoWorklogId") or matched_wl.get("id") or "existing"
                p.status = f"LOGGED (#{wl_id})"
                p.is_logged = True
                p.notes.append(f"Already logged in Tempo (#{wl_id})")
                matched_existing_ids.add(wl_id)
            elif p.entry.issue_id is not None:
                existing_ids = {_extract_issue_id(w) for w in existing}
                if p.entry.issue_id in existing_ids:
                    p.notes.append("Tempo already has a worklog on this issue today - possible duplicate")

        for wl in existing:
            wl_id = wl.get("tempoWorklogId") or wl.get("id")
            if wl_id not in matched_existing_ids:
                wl_key = (
                    wl.get("issue", {}).get("key")
                    if isinstance(wl.get("issue"), dict)
                    else _extract_issue_id(wl)
                )
                wl_time = wl.get("startTime") or wl.get("time") or "-"
                wl_mins = int(wl.get("timeSpentSeconds", 0)) // 60
                report.day_info.append(
                    f"In Tempo, not in journal: #{wl_id} ({wl_key}, {_fmt_minutes(wl_mins)} at {wl_time})."
                )

    # Explicit-range overlaps in the raw journal (moot when re-laid out sequentially)
    ranged = [] if sequential else sorted((e for e in loggable if e.start and e.end), key=lambda e: e.start)
    for a, b in zip(ranged, ranged[1:]):
        if _to_minutes(b.start) < _to_minutes(a.end):
            report.day_warnings.append(
                f"Overlap: '{_short(a.title)}' ({a.start}-{a.end}) and '{_short(b.title)}' ({b.start}-{b.end})."
            )

    # Post-rounding overlap & fixed block validation (F8)
    ready_active = [p for p in report.planned if p.status == "READY" and p.start and p.rounded_minutes]
    ready_active.sort(key=lambda p: _to_minutes(p.start or "00:00"))
    for a, b in zip(ready_active, ready_active[1:]):
        a_end = _to_minutes(a.start or "00:00") + (a.rounded_minutes or 0)
        b_start = _to_minutes(b.start or "00:00")
        if b_start < a_end:
            msg = (
                f"Overlap: '{_short(a.entry.title)}' ({a.start}-{_from_minutes(a_end)}) "
                f"and '{_short(b.entry.title)}' ({b.start}-{_from_minutes(b_start + (b.rounded_minutes or 0))})."
            )
            report.day_warnings.append(msg)
            if not allow_overlap:
                a.problems.append(f"Overlaps with {b.entry.ticket or b.entry.title}")
                b.problems.append(f"Overlaps with {a.entry.ticket or a.entry.title}")
                a.status = "BLOCKED"
                b.status = "BLOCKED"

    for p in ready_active:
        p_start = _to_minutes(p.start or "00:00")
        p_end = p_start + (p.rounded_minutes or 0)
        for fb in f_blocks:
            if p.entry.title == fb.title:
                continue
            fb_start = _to_minutes(fb.start)
            fb_end = _to_minutes(fb.end)
            if max(p_start, fb_start) < min(p_end, fb_end):
                report.day_warnings.append(
                    f"Planned entry '{_short(p.entry.title)}' ({p.start}) overlaps fixed block '{fb.title}' ({fb.start}-{fb.end})."
                )
                if not allow_overlap:
                    p.problems.append(f"Overlaps fixed block {fb.title}")
                    p.status = "BLOCKED"

    report.total_minutes = sum(p.rounded_minutes or 0 for p in report.planned)
    report.ready_minutes = sum(p.rounded_minutes or 0 for p in report.ready)

    grand = report.total_minutes + report.existing_minutes
    if daily_cap_hours:
        cap = int(daily_cap_hours * 60)
        if grand > cap:
            report.day_warnings.append(
                f"Day total {_fmt_minutes(grand)} exceeds the {daily_cap_hours:g}h cap by {_fmt_minutes(grand - cap)} - trim before submitting."
            )

    starts = [e.start for e in day if e.start]
    if starts:
        report.day_info.append(f"First journal entry starts at {min(starts)}; anything earlier in the day is not in the file.")

    _build_next_steps(report, resolve_failures, resolver is not None if can_lookup is None else can_lookup)
    return report


def _snap(minutes: int, step: int) -> int:
    """Round a clock time to the nearest step (e.g. 14:28 -> 14:30 for 15)."""
    return int(round(minutes / step)) * step


def _layout_sequential(report: AnalysisReport, step: int, reserved: list[tuple[str, str]]) -> None:
    """Re-plan READY entries back to back on step boundaries, skipping reserved slots."""
    ready = [
        p for p in report.planned
        if p.status == "READY" and p.rounded_minutes and not (p.entry.is_meeting and p.entry.start)
    ]
    for p in report.planned:
        if p.status != "READY":
            p.start = None
    if not ready:
        return
    slots = sorted((_snap(_to_minutes(a), step), _snap(_to_minutes(b), step)) for a, b in reserved)
    first = min((_to_minutes(p.start) for p in ready if p.start), default=9 * 60)
    cursor = _snap(first, step)
    for p in ready:
        moved = True
        while moved:
            moved = False
            for s_start, s_end in slots:
                if cursor < s_end and cursor + (p.rounded_minutes or 0) > s_start:
                    cursor = s_end
                    moved = True
        p.start = _from_minutes(cursor)
        cursor += p.rounded_minutes or 0
        if cursor > 24 * 60:
            p.problems.append("Planned time runs past midnight - trim entries or start earlier")
            p.status = "BLOCKED"
    for s_start, s_end in slots:
        report.day_info.append(f"Reserved {_from_minutes(s_start)}-{_from_minutes(s_end)} (not filled by journal entries).")


def _short(title: str, limit: int = 48) -> str:
    return title if len(title) <= limit else title[: limit - 3] + "..."


def _extract_issue_id(entry: dict[str, Any]) -> int | str | None:
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


def _build_next_steps(report: AnalysisReport, resolve_failures: set[str], had_resolver: bool) -> None:
    no_ticket = [p for p in report.planned if not p.entry.ticket and p.status != "SKIP"]
    no_id = [p for p in report.planned if p.entry.ticket and p.entry.issue_id is None and p.status != "SKIP"]
    no_time = [p for p in report.planned if p.entry.minutes is None and p.status != "SKIP"]
    if no_ticket:
        report.next_steps.append(
            f"Assign a ticket to {len(no_ticket)} entr{'y' if len(no_ticket) == 1 else 'ies'}: add 'Ticket: KEY' to the journal "
            "or map them to TEMPO_DEFAULT_ISSUE / TEMPO_MEETING_ISSUE."
        )
    if no_id:
        keys = sorted({p.entry.ticket for p in no_id if p.entry.ticket})
        how = "Jira lookup failed; check the key" if had_resolver else "set JIRA_API_TOKEN (or add '[id:N]' after the key)"
        report.next_steps.append(f"Resolve numeric ids for {', '.join(keys)}: {how}.")
    if no_time:
        report.next_steps.append(f"Give a duration to {len(no_time)} entr{'y' if len(no_time) == 1 else 'ies'} (e.g. '(15m)'), or leave them out.")
    if any("cap" in w for w in report.day_warnings):
        report.next_steps.append("Trim inflated or overlapping entries until the day fits the cap.")
    if not report.blocked and report.ready:
        report.next_steps.append("Ready entries can be submitted with --submit or exported with --export.")


def format_report(report: AnalysisReport) -> str:
    """Human-readable plan of exactly what the tool would do."""
    out: list[str] = []
    out.append(f"=== Journal analysis for {report.date} ===\n")
    out.append(f"{'#':<3} {'Status':<14} {'Ticket':<12} {'Issue id':<9} {'Start':<6} {'Time':<14} Title")
    out.append("-" * 102)
    for i, p in enumerate(report.planned, start=1):
        e = p.entry
        t = _fmt_minutes(e.minutes)
        if p.rounded_minutes is not None and p.rounded_minutes != e.minutes:
            t += f"->{_fmt_minutes(p.rounded_minutes)}"
        out.append(
            f"{i:<3} {p.status:<14} {(e.ticket or '-'):<12} {(str(e.issue_id) if e.issue_id else '-'):<9} "
            f"{(p.start or '-'):<6} {t:<14} {_short(e.title, 40)}"
        )
        for prob in p.problems:
            out.append(f"{'':<12}[BLOCKER] {prob}")
        for note in p.notes:
            out.append(f"{'':<12}[note] {note}")

    total = _fmt_minutes(report.total_minutes)
    cap = f" / cap {report.cap_hours:g}h" if report.cap_hours else ""
    existing = f" (+{_fmt_minutes(report.existing_minutes)} already in Tempo)" if report.existing_minutes else ""
    out.append("")
    out.append(f"Total to log: {total}{existing}{cap}")
    out.append(f"Ready: {len(report.ready)}   Logged: {len(report.logged)}   Blocked: {len(report.blocked)}")

    if report.day_warnings:
        out.append("\nDay checks:")
        out.extend(f"  [WARN] {w}" for w in report.day_warnings)
    if report.day_info:
        out.append("\nInfo:")
        out.extend(f"  - {i}" for i in report.day_info)
    if report.next_steps:
        out.append("\nNext steps:")
        out.extend(f"  {n}. {s}" for n, s in enumerate(report.next_steps, start=1))
    out.append("\nNothing was sent to Tempo.")
    return "\n".join(out)
