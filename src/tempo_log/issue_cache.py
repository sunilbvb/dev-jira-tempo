"""Local persistent cache for Jira issue keys to numeric IDs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path.home() / ".tempo-log" / "issue_cache.json"


class IssueCache:
    """Local JSON cache mapping issue keys (e.g. 'PROJ-123') to numeric issue IDs."""

    def __init__(self, cache_path: Path | str | None = None):
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self._cache: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._cache = {str(k).upper(): int(v) for k, v in data.items()}
            except Exception as exc:
                logger.warning("Failed to load issue cache from %s: %s", self.cache_path, exc)
                self._cache = {}

    def save(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as exc:
            logger.warning("Failed to save issue cache to %s: %s", self.cache_path, exc)

    def get(self, key: str) -> int | None:
        return self._cache.get(key.upper())

    def set(self, key: str, issue_id: int) -> None:
        self._cache[key.upper()] = issue_id
        self.save()
