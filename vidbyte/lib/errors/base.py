from __future__ import annotations

from typing import Any


class VidbyteSdkError(Exception):
    """Base exception for Vidbyte SDK failures."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(VidbyteSdkError):
    """Raised when runner or provider configuration is invalid."""


class UnsupportedProviderError(VidbyteSdkError):
    """Raised when a provider does not support a requested capability."""


class ProviderSelectionError(VidbyteSdkError):
    """Raised when no SDK provider adapter matches a requested capability."""


class ProviderRequestError(VidbyteSdkError):
    """Raised when a provider request fails or returns an invalid response."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        response_excerpt: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"provider": provider}
        if status_code is not None:
            details["status_code"] = status_code
        if response_excerpt:
            details["response_excerpt"] = response_excerpt[:500]
        super().__init__(message, details=details)
        self.provider = provider
        self.status_code = status_code
        self.response_excerpt = response_excerpt


class ToolExecutionError(VidbyteSdkError):
    """Raised when an SDK tool cannot complete safely."""


class StrategyExecutionError(VidbyteSdkError):
    """Raised when a prompt strategy cannot complete."""
