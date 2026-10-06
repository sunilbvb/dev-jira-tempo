"""Pytest global configuration and fixtures."""

from unittest import mock
import pytest


@pytest.fixture(autouse=True)
def isolate_local_dotenv():
    """Prevent developer local .env file from leaking into isolated unit tests."""
    with mock.patch("tempo_log.config._load_dotenv"):
        yield
