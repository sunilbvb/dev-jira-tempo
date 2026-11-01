"""Tests for persistent keyword-to-ticket mapper."""

from pathlib import Path
from tempo_log.ticket_mapper import TicketMapper


def test_ticket_mapper_match(tmp_path: Path):
    map_file = tmp_path / "ticket-map.toml"
    mapper = TicketMapper(filepath=map_file)
    mapper.add_mapping("standup", "MEET-101")
    mapper.add_mapping("bugfix", "CORE-404")

    assert mapper.match("Daily team standup call") == "MEET-101"
    assert mapper.match("Critical bugfix in authentication") == "CORE-404"
    assert mapper.match("Lunch break") is None


def test_ticket_mapper_save_and_reload(tmp_path: Path):
    map_file = tmp_path / "ticket-map.toml"
    mapper1 = TicketMapper(filepath=map_file)
    mapper1.add_mapping("deployment", "OPS-200")
    mapper1.save()

    assert map_file.exists()
    content = map_file.read_text(encoding="utf-8")
    assert '"deployment" = "OPS-200"' in content

    mapper2 = TicketMapper.load(custom_path=map_file)
    assert mapper2.match("Doing production deployment") == "OPS-200"
