from __future__ import annotations

from typing import Any, Mapping


class VidbyteSdkError(Exception):
    """Base class for SDK errors with safe optional details."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})


class ToolExecutionError(VidbyteSdkError):
    """Raised when tool metadata or execution fails."""


class StrategyExecutionError(VidbyteSdkError):
    """Raised when a strategy cannot produce a result."""


class AgentExecutionError(VidbyteSdkError):
    """Raised when an agent cannot generate a reply."""


class AgentRegistryError(VidbyteSdkError):
    """Raised when local agent discovery fails."""
