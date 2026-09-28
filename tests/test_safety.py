"""Unit tests for submission safety module (rounding, duplicates, daily cap, overlaps)."""

from __future__ import annotations

import pytest

from tempo_log.safety import (
    find_duplicates,
    round_duration,
    validate_submission_safety,
)


def test_round_duration_none_or_zero():
    assert round_duration(1.23, None) == 1.23
    assert round_duration(1.23, 0) == 1.23


def test_round_duration_exact_multiples():
    # 15 min increments
    assert round_duration(1.0, 15) == 1.0  # 60 min
    assert round_duration(0.25, 15) == 0.25  # 15 min
    assert round_duration(0.5, 15) == 0.5  # 30 min


def test_round_duration_just_above_boundary():
    # 15 min = 0.25h. 16 min = 0.266667h -> rounded to 30 min = 0.5h
    assert round_duration(0.266667, 15) == 0.5
    # 1 min = 0.016667h -> rounded to 15 min = 0.25h
    assert round_duration(0.016667, 15) == 0.25


def test_find_duplicates():
    existing = [
        {"issueId": 10001, "startDate": "2026-09-24", "startTime": "13:41:00"},
        {"issue": {"id": 10002}, "startDate": "2026-09-24", "startTime": "16:00:00"},
    ]

    candidates = [
        {"issue_id": 10001, "date": "2026-09-24", "time": "13:41:00", "label": "dup1"},
        {"issue_id": 10001, "date": "2026-09-24", "time": "14:00:00", "label": "new1"},
        {"issue_id": 10002, "date": "2026-09-24", "time": "16:00:00", "label": "dup2"},
    ]

    unique, dups = find_duplicates(candidates, existing)
    assert len(unique) == 1
    assert unique[0]["label"] == "new1"
    assert len(dups) == 2


def test_validate_submission_safety_daily_cap():
    existing = [
        {"startDate": "2026-09-24", "timeSpentSeconds": 14400},  # 4.0h
    ]
    candidates = [
        {"date": "2026-09-24", "hours": 5.0, "time": "13:00:00"},  # 5.0h -> Total 9.0h
    ]

    # With 8.0h cap -> warning
    warnings = validate_submission_safety(candidates, existing, daily_cap_hours=8.0)
    assert len(warnings) == 1
    assert "exceed daily cap of 8.00h" in warnings[0]

    # Without cap -> no cap warning
    no_cap_warnings = validate_submission_safety(candidates, existing, daily_cap_hours=None)
    assert len(no_cap_warnings) == 0


def test_validate_submission_safety_overlap():
    candidates = [
        {"date": "2026-09-24", "hours": 2.0, "time": "13:00:00", "issue": "PROJ-1"},  # 13:00 - 15:00
        {"date": "2026-09-24", "hours": 1.0, "time": "14:30:00", "issue": "PROJ-2"},  # 14:30 - 15:30 -> Overlap
    ]

    warnings = validate_submission_safety(candidates, existing_worklogs=[], daily_cap_hours=None)
    assert len(warnings) == 1
    assert "Time overlap between 'PROJ-1'" in warnings[0]


def test_find_duplicates_intra_candidate_and_string_keys():
    existing = [
        {"issue": "PROJ-100", "startDate": "2026-09-24", "startTime": "10:00:00"},
    ]
    candidates = [
        {"issue": "PROJ-100", "date": "2026-09-24", "time": "10:00:00", "label": "dup_existing"},
        {"issue": "PROJ-200", "date": "2026-09-24", "time": "11:00:00", "label": "candidate_1"},
        {"issue": "PROJ-200", "date": "2026-09-24", "time": "11:00:00", "label": "candidate_2_dup_internal"},
    ]
    unique, dups = find_duplicates(candidates, existing)
    assert len(unique) == 1
    assert unique[0]["label"] == "candidate_1"
    assert len(dups) == 2
    dup_labels = [d["label"] for d in dups]
    assert "dup_existing" in dup_labels
    assert "candidate_2_dup_internal" in dup_labels

