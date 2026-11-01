"""Pure scheduling helpers: round durations up and lay entries out on a day
without overlaps, around an optional fixed break."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class ScheduleError(ValueError):
    """Raised when entries cannot be scheduled within the configured limits."""


@dataclass(frozen=True)
class ScheduleConfig:
    start_candidates: tuple[str, ...] = ("10:00",)
    round_minutes: int = 15
    max_day_minutes: int = 12 * 60
    break_issue: str | None = None
    break_start: str = "14:00"
    break_minutes: int = 60
    break_description: str = "Lunch:\n- Lunch break"


@dataclass
class Item:
    """A unit of work to place on the day. `minutes` is already rounded."""

    issue: str | int
    minutes: int
    description: str = ""
    start: int | None = field(default=None)  # minutes since midnight
    fixed_start: int | None = field(default=None)  # real start, e.g. a call

    @property
    def hours(self) -> float:
        return self.minutes / 60


def parse_clock(value: str) -> int:
    hours, minutes = value.split(":")[:2]
    return int(hours) * 60 + int(minutes)


def format_clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}:00"


def round_up(minutes: float, step: int) -> int:
    """Round up to the next `step` minutes, with a minimum of one step."""
    if minutes <= 0:
        raise ScheduleError(f"Duration must be positive, got {minutes} minutes.")
    return max(step, int(math.ceil(minutes / step)) * step)


def _place(items: list[Item], start: int, break_at: int | None) -> tuple[list[Item], list[Item], int]:
    """Place items in order from `start`; once one does not fit before the
    break, it and every later item go after the break. Returns
    (before, after, gap_minutes_before_break)."""
    before: list[Item] = []
    after: list[Item] = []
    cursor = start
    for item in items:
        if not after and (break_at is None or cursor + item.minutes <= break_at):
            item.start = cursor
            cursor += item.minutes
            before.append(item)
        else:
            after.append(item)
    gap = (break_at - cursor) if break_at is not None else 0
    return before, after, max(gap, 0)


def build_schedule(items: list[Item], config: ScheduleConfig) -> list[Item]:
    """Return items (plus the break entry, if configured) with start times
    set, back to back and without overlaps."""
    work_minutes = sum(i.minutes for i in items)
    total = work_minutes + (config.break_minutes if config.break_issue else 0)
    if total > config.max_day_minutes:
        raise ScheduleError(
            f"Scheduled time is {total / 60:g}h, above the {config.max_day_minutes / 60:g}h daily cap."
        )

    break_at = parse_clock(config.break_start) if config.break_issue else None

    best = None
    for candidate in config.start_candidates:
        trial = [Item(i.issue, i.minutes, i.description) for i in items]
        before, after, gap = _place(trial, parse_clock(candidate), break_at)
        if best is None or gap < best[0]:
            best = (gap, before, after)
    assert best is not None
    _, before, after = best

    placed = list(before)
    cursor = break_at + config.break_minutes if break_at is not None else (
        before[-1].start + before[-1].minutes if before else 0
    )
    if break_at is not None:
        placed.append(
            Item(config.break_issue, config.break_minutes, config.break_description, break_at)
        )
    for item in after:
        item.start = cursor
        cursor += item.minutes
        placed.append(item)

    placed.sort(key=lambda i: i.start)
    return placed


def _floor(minutes: int, step: int) -> int:
    return minutes - minutes % step


def build_day(
    items: list[Item],
    config: ScheduleConfig,
    reserved: list[tuple[int, int]] | None = None,
) -> list[Item]:
    """Lay out a day where some items (calls) keep their real start time.

    Fixed items are placed first at their start rounded down to the step
    (pushed later only to avoid overlapping another fixed item). The break
    goes at its configured time, or at the nearest free window if a fixed
    item is in the way. The remaining items fill the free time in order and
    are split across gaps when they do not fit in one.
    """
    step = config.round_minutes
    total = sum(i.minutes for i in items) + (config.break_minutes if config.break_issue else 0)
    if total > config.max_day_minutes:
        raise ScheduleError(
            f"Scheduled time is {total / 60:g}h, above the {config.max_day_minutes / 60:g}h daily cap."
        )

    fixed = sorted((i for i in items if i.fixed_start is not None), key=lambda i: i.fixed_start)
    work = [i for i in items if i.fixed_start is None]

    placed: list[Item] = []
    busy: list[tuple[int, int]] = list(reserved or [])
    cursor_end = 0
    for item in fixed:
        start = max(_floor(item.fixed_start, step), cursor_end)
        while not all(start + item.minutes <= b0 or start >= b1 for b0, b1 in busy):
            start = min(b1 for b0, b1 in busy if not (start + item.minutes <= b0 or start >= b1))
        placed.append(Item(item.issue, item.minutes, item.description, start))
        busy.append((start, start + item.minutes))
        cursor_end = start + item.minutes

    def free(start: int, end: int) -> bool:
        return all(end <= b0 or start >= b1 for b0, b1 in busy)

    if config.break_issue:
        wanted = parse_clock(config.break_start)
        found = None
        for delta in range(0, 12 * 60, step):
            for candidate in (wanted + delta, wanted - delta):
                if candidate >= 0 and free(candidate, candidate + config.break_minutes):
                    found = candidate
                    break
            if found is not None:
                break
        if found is None:
            raise ScheduleError("No free window for the break.")
        placed.append(Item(config.break_issue, config.break_minutes, config.break_description, found))
        busy.append((found, found + config.break_minutes))

    busy.sort()
    first_busy = busy[0][0] if busy else None

    best = None
    for candidate in config.start_candidates:
        day_start = parse_clock(candidate)
        if first_busy is not None:
            day_start = min(day_start, first_busy)
        pieces: list[Item] = []
        queue = [[i, i.minutes] for i in work]
        cursor = day_start
        gap_total = 0
        idx = 0
        guard = 0
        while idx < len(queue) and guard < 10000:
            guard += 1
            nxt = next((b0 for b0, b1 in busy if b0 >= cursor), None)
            inside = next((b1 for b0, b1 in busy if b0 <= cursor < b1), None)
            if inside is not None:
                cursor = inside
                continue
            room = (nxt - cursor) if nxt is not None else None
            item, remaining = queue[idx]
            if room is None or remaining <= room:
                pieces.append(Item(item.issue, remaining, item.description, cursor))
                cursor += remaining
                idx += 1
            elif room >= step and (remaining - room >= step or room >= remaining):
                pieces.append(Item(item.issue, room, item.description, cursor))
                queue[idx][1] = remaining - room
                cursor += room
            else:
                gap_total += room
                cursor = nxt
        if best is None or gap_total < best[0]:
            best = (gap_total, pieces)
    assert best is not None
    placed.extend(best[1])
    placed.sort(key=lambda i: i.start)
    return placed
