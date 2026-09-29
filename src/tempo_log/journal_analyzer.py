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
META_LINE = re.compile(r"^(time estimate|time|ticket)\s*:", re.IGNORECASE)
TICKET_FIELD = re.compile(r"ticket\s*:\s*(.*)$", re.IGNORECASE)


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

    def description(self) -> str:
        """Title line plus bullet points (file lists are dropped)."""
        lines = [self.title.strip()]
        points = [b for b in self.bullets if not b.lower().startswith("files:")]
        if not points and self.body:
            points = [" ".join(self.body)[:300]]
        lines.extend(f"- {p}" for p in points)
        return "\n".join(lines)


def parse_journal(content: str) -> list[JournalEntry]:
    """Parse every session / sub-entry in the journal (all dates)."""
    entries: list[JournalEntry] = []
    session: JournalEntry | None = None
    current: JournalEntry | None = None

    for idx, raw in enumerate(content.splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()

        heading = SESSION_HEADING.match(stripped)
        if heading and not stripped.startswith("###"):
            date, start, title = heading.group(1), heading.group(2), (heading.group(3) or "").strip()
            session = JournalEntry(date=date, title=title or "(untitled)", start=start, line_number=idx)
            key = ISSUE_KEY.match(title)
            if key:
                session.ticket = key.group(1)
            entries.append(session)
            current = session
            continue

        sub = SUB_HEADING.match(stripped)
        if sub and session is not None:
            key, sub_id, rest = sub.group(1), sub.group(2), sub.group(3)
            status = rest.split("(")[0].strip(" -—–") or None
            paren = re.search(r"\(([^)]*)\)", rest)
            minutes = parse_duration_minutes(paren.group(1)) if paren else None
            current = JournalEntry(
                date=session.date,
                title=f"{key}: {status}" if status else key,
                line_number=idx,
                ticket=key,
                minutes=minutes,
                kind="sub",
                parent_title=session.title,
                status=status,
                issue_id=int(sub_id) if sub_id else None,
            )
            session.is_container = True
            entries.append(current)
            continue

        if current is None:
            continue

        if META_LINE.match(stripped):
            _apply_meta(current, stripped)
            continue

        if stripped.startswith("- "):
            current.bullets.append(stripped[2:].strip())
        elif raw.startswith((" ", "\t")) and current.bullets and stripped:
            current.bullets[-1] += " " + stripped
        elif stripped and not stripped.startswith(("---", "#")):
            current.body.append(stripped)

    return entries


def _apply_meta(entry: JournalEntry, line: str) -> None:
    for part in line.split("|"):
        part = part.strip()
        low = part.lower()
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


# --------------------------------------------------------------------------- analysis


@dataclass
class PlannedEntry:
    entry: JournalEntry
    rounded_minutes: int | None
    start: str | None
    status: str  # READY | BLOCKED | SKIP
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_batch(self) -> dict[str, Any]:
        return {
            "date": self.entry.date,
            "time": f"{self.start}:00" if self.start else None,
            "issue": self.entry.ticket,
            "issue_id": self.entry.issue_id,
            "hours": round((self.rounded_minutes or 0) / 60.0, 4),
            "description": self.entry.description(),
        }


@dataclass
class AnalysisReport:
    date: str
    planned: list[PlannedEntry] = field(default_factory=list)
    day_warnings: list[str] = field(default_factory=list)
    day_info: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    total_minutes: int = 0
    existing_minutes: int = 0
    cap_hours: float | None = None

    @property
    def ready(self) -> list[PlannedEntry]:
        return [p for p in self.planned if p.status == "READY"]

    @property
    def blocked(self) -> list[PlannedEntry]:
        return [p for p in self.planned if p.status == "BLOCKED"]


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
) -> AnalysisReport:
    """Build a pre-submission report for one date. Pure: no network unless resolver does it."""
    report = AnalysisReport(date=date, cap_hours=daily_cap_hours)
    day = [e for e in entries if e.date == date]
    if not day:
        report.day_warnings.append(f"No journal entries found for {date}.")
        return report

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

    # Propose start times: explicit start, else follow the previous entry.
    sessions_by_line = {s.line_number: s for s in day if s.kind == "session"}
    cursor: int | None = None
    parent_start: dict[str, int] = {}
    for s in sessions_by_line.values():
        if s.start:
            parent_start[s.title] = _to_minutes(s.start)

    seen_tickets: dict[str, int] = {}
    for e in loggable:
        rounded = None
        if e.minutes is not None:
            rounded = int(round(round_duration(e.minutes / 60.0, round_minutes) * 60))
        begin: int | None = None
        if e.start:
            begin = _to_minutes(e.start)
        elif e.kind == "sub" and e.parent_title in parent_start and (cursor is None or cursor < parent_start[e.parent_title]):
            begin = parent_start[e.parent_title]
        elif cursor is not None:
            begin = cursor
        if begin is not None and rounded:
            cursor = begin + rounded

        planned = PlannedEntry(entry=e, rounded_minutes=rounded, start=_from_minutes(begin) if begin is not None else None, status="READY")

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

    report.total_minutes = sum(p.rounded_minutes or 0 for p in report.planned)

    if sequential:
        _layout_sequential(report, round_minutes or 15, reserved or [])

    # Estimates vs. wall clock between consecutive session headings.
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

    # Explicit-range overlaps (moot when entries are re-laid out back to back).
    ranged = [] if sequential else sorted((e for e in loggable if e.start and e.end), key=lambda e: e.start)
    for a, b in zip(ranged, ranged[1:]):
        if _to_minutes(b.start) < _to_minutes(a.end):
            report.day_warnings.append(f"Overlap: '{_short(a.title)}' ({a.start}-{a.end}) and '{_short(b.title)}' ({b.start}-{b.end}).")

    # Already in Tempo.
    existing = existing_worklogs or []
    report.existing_minutes = sum(int(w.get("timeSpentSeconds", 0)) // 60 for w in existing)
    if existing:
        report.day_info.append(f"Tempo already has {len(existing)} worklog(s) for {date} totalling {_fmt_minutes(report.existing_minutes)}.")
        existing_ids = {w.get("issue", {}).get("id") for w in existing}
        for p in report.planned:
            if p.entry.issue_id is not None and p.entry.issue_id in existing_ids:
                p.notes.append("Tempo already has a worklog on this issue today - possible duplicate")

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
    ready = [p for p in report.planned if p.status == "READY" and p.rounded_minutes]
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
                if cursor < s_end and cursor + p.rounded_minutes > s_start:
                    cursor = s_end
                    moved = True
        p.start = _from_minutes(cursor)
        cursor += p.rounded_minutes
        if cursor > 24 * 60:
            p.problems.append("Planned time runs past midnight - trim entries or start earlier")
            p.status = "BLOCKED"
    for s_start, s_end in slots:
        report.day_info.append(f"Reserved {_from_minutes(s_start)}-{_from_minutes(s_end)} (not filled by journal entries).")


def _short(title: str, limit: int = 48) -> str:
    return title if len(title) <= limit else title[: limit - 3] + "..."


def _build_next_steps(report: AnalysisReport, resolve_failures: set[str], had_resolver: bool) -> None:
    no_ticket = [p for p in report.planned if not p.entry.ticket]
    no_id = [p for p in report.planned if p.entry.ticket and p.entry.issue_id is None]
    no_time = [p for p in report.planned if p.entry.minutes is None]
    if no_ticket:
        report.next_steps.append(
            f"Assign a ticket to {len(no_ticket)} entr{'y' if len(no_ticket) == 1 else 'ies'}: add 'Ticket: KEY' to the journal "
            "or map them to TEMPO_DEFAULT_ISSUE / TEMPO_MEETING_ISSUE."
        )
    if no_id:
        keys = sorted({p.entry.ticket for p in no_id})
        how = "Jira lookup failed; check the key" if had_resolver else "set JIRA_API_TOKEN (or add '[id:N]' after the key)"
        report.next_steps.append(f"Resolve numeric ids for {', '.join(keys)}: {how}.")
    if no_time:
        report.next_steps.append(f"Give a duration to {len(no_time)} entr{'y' if len(no_time) == 1 else 'ies'} (e.g. '(15m)'), or leave them out.")
    if any("cap" in w for w in report.day_warnings):
        report.next_steps.append("Trim inflated or overlapping entries until the day fits the cap.")
    if not report.blocked and report.planned:
        report.next_steps.append("All entries are ready: export with --export and upload with 'tempo-log batch'.")


def format_report(report: AnalysisReport) -> str:
    """Human-readable plan of exactly what the tool would do."""
    out: list[str] = []
    out.append(f"=== Journal analysis for {report.date} ===\n")
    out.append(f"{'#':<3} {'Status':<8} {'Ticket':<12} {'Issue id':<9} {'Start':<6} {'Time':<14} Title")
    out.append("-" * 96)
    for i, p in enumerate(report.planned, start=1):
        e = p.entry
        t = _fmt_minutes(e.minutes)
        if p.rounded_minutes is not None and p.rounded_minutes != e.minutes:
            t += f"->{_fmt_minutes(p.rounded_minutes)}"
        out.append(
            f"{i:<3} {p.status:<8} {(e.ticket or '-'):<12} {(str(e.issue_id) if e.issue_id else '-'):<9} "
            f"{(p.start or '-'):<6} {t:<14} {_short(e.title, 44)}"
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
    out.append(f"Ready: {len(report.ready)}   Blocked: {len(report.blocked)}")

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
