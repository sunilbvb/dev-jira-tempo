"""Tests for timesheet CSV, JSON, and printable HTML generator."""

from tempo_log.export import ExportItem, generate_csv, generate_html, generate_json


def test_generate_csv():
    items = [
        ExportItem(date="2026-11-02", issue="PROJ-1", hours=1.5, description="Feature A", tempo_id=101, start_time="09:00"),
        ExportItem(date="2026-11-02", issue="PROJ-2", hours=2.0, description="Bugfix B", tempo_id=102, start_time="11:00"),
    ]
    csv_out = generate_csv(items)
    assert "Date,Issue,Hours,StartTime,TempoID,Description" in csv_out
    assert "2026-11-02,PROJ-1,1.50,09:00,101,Feature A" in csv_out
    assert "2026-11-02,PROJ-2,2.00,11:00,102,Bugfix B" in csv_out


def test_generate_json():
    items = [
        ExportItem(date="2026-11-02", issue="PROJ-1", hours=1.25, description="Feature A"),
    ]
    json_out = generate_json(items)
    assert '"total_items": 1' in json_out
    assert '"total_hours": 1.25' in json_out
    assert '"issue": "PROJ-1"' in json_out


def test_generate_html():
    items = [
        ExportItem(date="2026-11-02", issue="PROJ-1", hours=3.0, description="Development"),
    ]
    html_out = generate_html(items, title="Weekly Review")
    assert "<title>Weekly Review</title>" in html_out
    assert "3.00 Hours" in html_out
    assert "PROJ-1" in html_out
