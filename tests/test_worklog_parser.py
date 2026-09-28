"""Unit tests for markdown worklog parser."""

from __future__ import annotations

import pytest

from tempo_log.worklog_parser import parse_markdown_worklog


def test_parse_valid_worklog():
    content = """
## 2026-09-24

Tempo: PROJ-123 | 13:41-13:56
- Fixed plan name truncation
- Neutral colour when no active plan

Tempo: meeting | 16:33-17:03
- Reviewed currency handling with backend

Tempo: skip
- Ignored notes
"""
    res = parse_markdown_worklog(content)
    assert len(res.errors) == 0
    assert len(res.entries) == 2

    e1 = res.entries[0]
    assert e1.date == "2026-09-24"
    assert e1.issue == "PROJ-123"
    assert e1.start_time == "13:41:00"
    assert e1.end_time == "13:56:00"
    assert pytest.approx(e1.hours, 0.001) == 0.25
    assert "- Fixed plan name truncation" in e1.description

    e2 = res.entries[1]
    assert e2.issue == "meeting"
    assert pytest.approx(e2.hours, 0.001) == 0.5


def test_parse_malformed_lines():
    content = """
## 2026-09-24
Tempo: invalid_line
Tempo: PROJ-1 | 15:00-14:00
"""
    res = parse_markdown_worklog(content)
    assert len(res.errors) >= 2


def test_parse_entry_before_date_heading():
    content = """
Tempo: PROJ-100 | 10:00-11:00
- Floating entry
"""
    res = parse_markdown_worklog(content)
    assert len(res.errors) == 1
    assert "before any valid" in res.errors[0]
