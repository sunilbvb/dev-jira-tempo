"""Persistent keyword-to-ticket mapping engine.

Supports loading and saving mappings in .tempo-log/ticket-map.toml using
standard library string formatting (zero external dependencies).
"""

from __future__ import annotations

import logging
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


class TicketMapper:
    """Maps keywords to tickets based on local configuration file."""

    def __init__(self, mappings: dict[str, str] | None = None, filepath: Path | None = None) -> None:
        self.mappings: dict[str, str] = mappings or {}
        self.filepath: Path | None = filepath

    @classmethod
    def default_path(cls) -> Path:
        local_dir = Path.cwd() / ".tempo-log"
        return local_dir / "ticket-map.toml"

    @classmethod
    def load(cls, custom_path: Path | str | None = None) -> TicketMapper:
        candidates: list[Path] = []
        if custom_path:
            candidates.append(Path(custom_path).expanduser())
        else:
            candidates.append(Path.cwd() / ".tempo-log" / "ticket-map.toml")
            candidates.append(Path.home() / ".tempo-log" / "ticket-map.toml")

        for path in candidates:
            if path.is_file():
                if tomllib:
                    try:
                        data = tomllib.loads(path.read_text(encoding="utf-8"))
                        maps = data.get("mappings", data)
                        return cls({str(k).lower(): str(v) for k, v in maps.items()}, filepath=path)
                    except Exception as exc:
                        logger.warning("Could not parse ticket map at %s: %s", path, exc)
                else:
                    # Fallback line-by-line parser for simple key = "value"
                    mappings: dict[str, str] = {}
                    for line in path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip().strip('"\'').lower()
                            v = v.strip().strip('"\'')
                            mappings[k] = v
                    return cls(mappings, filepath=path)

        return cls(filepath=cls.default_path())

    def match(self, text: str) -> str | None:
        """Find matching ticket for text keywords."""
        low = text.lower()
        for kw, ticket in self.mappings.items():
            if kw in low:
                return ticket
        return None

    def add_mapping(self, keyword: str, ticket: str) -> None:
        """Add or update a keyword mapping."""
        self.mappings[keyword.lower().strip()] = ticket.strip().upper()

    def save(self, path: Path | None = None) -> Path:
        """Persist mappings to TOML file."""
        target = path or self.filepath or self.default_path()
        target.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# tempo-log Keyword to Jira Ticket Map",
            "# Automatically matches journal phrases to tickets",
            "",
            "[mappings]",
        ]
        for kw in sorted(self.mappings.keys()):
            ticket = self.mappings[kw]
            lines.append(f'"{kw}" = "{ticket}"')
        lines.append("")

        target.write_text("\n".join(lines), encoding="utf-8")
        self.filepath = target
        return target
