"""Unified exception hierarchy for tempo_log."""

from __future__ import annotations


class TempoLogError(Exception):
    """Base exception for all tempo_log errors."""


class ConfigError(TempoLogError, RuntimeError):
    """Raised when configuration is missing or invalid."""


class TempoClientError(TempoLogError, RuntimeError):
    """Raised when a Tempo API call fails."""


class JiraClientError(TempoLogError, RuntimeError):
    """Raised when a Jira API call fails."""


class ValidationError(TempoLogError, ValueError):
    """Raised when parameters or payload values are invalid."""
