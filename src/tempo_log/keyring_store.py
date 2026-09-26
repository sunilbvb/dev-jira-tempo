"""OS Keyring / Secret Storage integration for securely storing tokens."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SERVICE_NAME = "dev-jira-tempo"


def _get_keyring_module() -> Any | None:
    """Safely import keyring if installed."""
    try:
        import keyring
        return keyring
    except ImportError:
        logger.debug("keyring package not installed.")
        return None


def is_keyring_available() -> bool:
    """Check if keyring backend is usable."""
    kr = _get_keyring_module()
    if kr is None:
        return False
    try:
        backend = kr.get_keyring()
        # Ensure it's not a fail backend
        return backend.priority > 0
    except Exception as exc:
        logger.debug("Error checking keyring backend: %s", exc)
        return False


def set_credential(key: str, value: str) -> None:
    """Store a secret in the OS keyring."""
    kr = _get_keyring_module()
    if kr is None:
        raise RuntimeError(
            "keyring is not installed. Install via: pip install keyring"
        )
    kr.set_password(SERVICE_NAME, key, value)


def get_credential(key: str) -> str | None:
    """Retrieve a secret from the OS keyring, or None if not found or unavailable."""
    kr = _get_keyring_module()
    if kr is None:
        return None
    try:
        return kr.get_password(SERVICE_NAME, key)
    except Exception as exc:
        logger.debug("Could not read from keyring: %s", exc)
        return None


def delete_credential(key: str) -> bool:
    """Delete a secret from the OS keyring."""
    kr = _get_keyring_module()
    if kr is None:
        return False
    try:
        kr.delete_password(SERVICE_NAME, key)
        return True
    except Exception as exc:
        logger.debug("Could not delete from keyring: %s", exc)
        return False
