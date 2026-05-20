from __future__ import annotations

from typing import Any, Mapping


class VidbyteSdkError(Exception):
    """Base class for public Vidbyte SDK errors."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


class ToolRegistrationError(VidbyteSdkError):
    """Raised when a tool cannot be registered."""


class ToolValidationError(VidbyteSdkError):
    """Raised when a tool call cannot be validated."""


class ToolExecutionError(VidbyteSdkError):
    """Raised when a tool cannot be executed."""


class StrategyExecutionError(VidbyteSdkError):
    """Raised when a strategy cannot execute."""

