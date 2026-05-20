from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class VidbyteSdkError(Exception):
    """Base class for public Vidbyte SDK errors."""


class HarnessConfigurationError(VidbyteSdkError):
    """Raised when a harness is configured with invalid inputs."""


class HarnessExecutionError(VidbyteSdkError):
    """Raised when a harness fails during execution."""


class EvaluationError(HarnessExecutionError):
    """Raised when a harness evaluator cannot score runtime state."""


class ExploitSuccessError(HarnessExecutionError):
    """Raised when a red-team attack triggers a fatal finding."""

    def __init__(
        self,
        message: str,
        *,
        payload: str,
        severity: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.payload = payload
        self.severity = severity
        self.metadata = dict(metadata or {})
