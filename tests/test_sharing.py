"""Tests for team digest payload generation."""

from tempo_log.export import ExportItem
from tempo_log.sharing import build_digest_payload


def test_build_digest_payload():
    items = [
        ExportItem(date="2026-11-02", issue="PROJ-10", hours=2.5, description="Implemented OAuth2 flow\n- Details"),
        ExportItem(date="2026-11-02", issue="PROJ-20", hours=1.0, description="Reviewed PRs"),
    ]
    payload = build_digest_payload("2026-11-02", items, channel="#standup")

    assert payload["date"] == "2026-11-02"
    assert payload["total_hours"] == 3.5
    assert payload["channel"] == "#standup"
    assert "PROJ-10" in payload["text"]
    assert "PROJ-20" in payload["text"]
    assert len(payload["blocks"]) >= 3
