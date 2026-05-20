from __future__ import annotations


class VidbyteSdkError(Exception):
    """Base class for public Vidbyte SDK errors."""


class ConfigurationError(VidbyteSdkError):
    """Raised when SDK objects are configured incorrectly."""


class ValidationError(VidbyteSdkError):
    """Raised when runtime input or state is invalid."""


class HarnessExecutionError(VidbyteSdkError):
    """Raised when a harness cannot complete its execution contract."""

