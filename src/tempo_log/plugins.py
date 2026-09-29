"""Plugin architecture and ticket/meeting integration interfaces.

Provides plugin hook interfaces for:
- F9: Ticket suggestions from Jira or keyword mapping (`suggest_tickets`)
- F10: Meeting gap-check from calendar or email notifications (`find_meetings`)
- Local ticket mapping via .tempo-log/ticket-map.toml
"""

from __future__ import annotations

import importlib.metadata
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    """Candidate Jira ticket suggestion for ticketless work."""

    ticket: str
    summary: str
    status: str = ""
    assignee: str = ""
    score: float = 1.0


@dataclass
class MeetingCandidate:
    """Candidate meeting event found in calendar or mail."""

    title: str
    start: str
    end: str
    minutes: int
    attended: bool = True


class TicketMapper:
    """Maps keywords to tickets based on local configuration file."""

    def __init__(self, mappings: dict[str, str] | None = None) -> None:
        self.mappings: dict[str, str] = mappings or {}

    @classmethod
    def load(cls, custom_path: Path | str | None = None) -> TicketMapper:
        candidates = []
        if custom_path:
            candidates.append(Path(custom_path).expanduser())
        else:
            candidates.append(Path.cwd() / ".tempo-log" / "ticket-map.toml")
            candidates.append(Path.home() / ".tempo-log" / "ticket-map.toml")

        for path in candidates:
            if path.is_file() and tomllib:
                try:
                    data = tomllib.loads(path.read_text(encoding="utf-8"))
                    maps = data.get("mappings", data)
                    return cls({str(k).lower(): str(v) for k, v in maps.items()})
                except Exception as exc:
                    logger.warning("Could not parse ticket map at %s: %s", path, exc)

        return cls()

    def match(self, text: str) -> str | None:
        """Find matching ticket for text keywords."""
        low = text.lower()
        for kw, ticket in self.mappings.items():
            if kw in low:
                return ticket
        return None


def get_plugin_hooks() -> list[Any]:
    """Discover installed tempo_log.plugins entry points."""
    try:
        eps = importlib.metadata.entry_points()
        if hasattr(eps, "select"):
            return list(eps.select(group="tempo_log.plugins"))
        return eps.get("tempo_log.plugins", [])  # type: ignore[attr-defined]
    except Exception as exc:
        logger.debug("Error discovering plugins: %s", exc)
        return []


def suggest_tickets(
    text: str,
    jira_client: Any = None,
    mapper: TicketMapper | None = None,
) -> list[Candidate]:
    """Suggest tickets for an untagged entry using local map and installed plugins."""
    candidates: list[Candidate] = []

    # 1. Local ticket map
    if mapper is not None:
        matched = mapper.match(text)
        if matched:
            candidates.append(
                Candidate(ticket=matched, summary=f"Matched keyword mapping for '{text[:40]}'", score=2.0)
            )

    # 2. Installed plugins
    for ep in get_plugin_hooks():
        try:
            plugin = ep.load()
            if hasattr(plugin, "suggest_tickets"):
                results = plugin.suggest_tickets(text, jira_client=jira_client)
                if results:
                    candidates.extend(results)
        except Exception as exc:
            logger.debug("Plugin %s failed in suggest_tickets: %s", ep.name, exc)

    return candidates


def find_meetings(date_str: str) -> list[MeetingCandidate]:
    """Find meetings from calendar / mail plugins for a date."""
    meetings: list[MeetingCandidate] = []
    for ep in get_plugin_hooks():
        try:
            plugin = ep.load()
            if hasattr(plugin, "find_meetings"):
                results = plugin.find_meetings(date_str)
                if results:
                    meetings.extend(results)
        except Exception as exc:
            logger.debug("Plugin %s failed in find_meetings: %s", ep.name, exc)
    return meetings
