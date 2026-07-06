"""Context Protocol Header

Description:
    Defines tool-error retry and rendering policy settings for agent loops.
Purpose:
    Gives AgentLoopSettings a validated nested policy for deciding when failed
    tool calls should retry, continue, render hints, or abort the run.
Architecture:
    - UnrecoverableAction: Runtime action for terminal tool errors.
    - ToolErrorPolicy: Validated developer-facing policy object.
Relations:
    Used by vidbyte.agents.settings.loop and ToolErrorPolicyMiddleware.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tools import ErrorVerbosity, ToolErrorRenderOptions

_DEFAULT_RETRY_ON = frozenset(("timeout", "rate_limited", "upstream_error"))


class UnrecoverableAction(str, Enum):
    """Controls what the runtime does after a terminal tool error."""

    CONTINUE = "continue"
    ABORT_RUN = "abort_run"


class ToolErrorPolicy:
    """Validated settings for tool-error retry, rendering, and abort behavior."""

    def __init__(
        self,
        *,
        max_retries_per_tool_call: int = 0,
        retry_on: Iterable[object] | None = None,
        retry_backoff_base_seconds: float = 0.5,
        retry_backoff_multiplier: float = 2.0,
        retry_backoff_cap_seconds: float = 30.0,
        retry_only_idempotent: bool = True,
        error_verbosity: ErrorVerbosity | str = ErrorVerbosity.FULL,
        include_remediation_hint: bool = True,
        mark_provider_error_flag: bool = True,
        redact_exception_details: bool = False,
        on_unrecoverable: UnrecoverableAction | str = UnrecoverableAction.CONTINUE,
        max_total_tool_errors: int | None = None,
    ) -> None:
        self.max_retries_per_tool_call = max_retries_per_tool_call
        self.retry_on = self._normalize_retry_on(retry_on)
        self.retry_backoff_base_seconds = retry_backoff_base_seconds
        self.retry_backoff_multiplier = retry_backoff_multiplier
        self.retry_backoff_cap_seconds = retry_backoff_cap_seconds
        self.retry_only_idempotent = retry_only_idempotent
        self.error_verbosity = self._normalize_error_verbosity(error_verbosity)
        self.include_remediation_hint = include_remediation_hint
        self.mark_provider_error_flag = mark_provider_error_flag
        self.redact_exception_details = redact_exception_details
        self.on_unrecoverable = self._normalize_unrecoverable_action(on_unrecoverable)
        self.max_total_tool_errors = max_total_tool_errors
        self._validate()

    def to_render_options(self) -> ToolErrorRenderOptions:
        return ToolErrorRenderOptions(
            error_verbosity=self.error_verbosity,
            include_remediation_hint=self.include_remediation_hint,
            mark_provider_error_flag=self.mark_provider_error_flag,
            redact_exception_details=self.redact_exception_details,
        )

    def _validate(self) -> None:
        self._require_non_negative("max_retries_per_tool_call", self.max_retries_per_tool_call)
        self._require_non_negative("retry_backoff_base_seconds", self.retry_backoff_base_seconds)
        self._require_at_least("retry_backoff_multiplier", self.retry_backoff_multiplier, 1)
        self._require_at_least(
            "retry_backoff_cap_seconds",
            self.retry_backoff_cap_seconds,
            self.retry_backoff_base_seconds,
            minimum_name="retry_backoff_base_seconds",
        )
        self._require_positive_if_present("max_total_tool_errors", self.max_total_tool_errors)

    @staticmethod
    def _normalize_retry_on(retry_on: Iterable[object] | None) -> frozenset[str]:
        if retry_on is None:
            return _DEFAULT_RETRY_ON
        return frozenset(
            normalized
            for item in retry_on
            if (normalized := ToolErrorPolicy._normalize_retry_kind(item))
        )

    @staticmethod
    def _normalize_error_verbosity(value: ErrorVerbosity | str) -> ErrorVerbosity:
        try:
            return value if isinstance(value, ErrorVerbosity) else ErrorVerbosity(str(value).lower())
        except ValueError as exc:
            allowed = ToolErrorPolicy._enum_values(ErrorVerbosity)
            raise ConfigurationError(f"ToolErrorPolicy.error_verbosity must be one of {allowed}.") from exc

    @staticmethod
    def _normalize_unrecoverable_action(value: UnrecoverableAction | str) -> UnrecoverableAction:
        try:
            return value if isinstance(value, UnrecoverableAction) else UnrecoverableAction(str(value).lower())
        except ValueError as exc:
            allowed = ToolErrorPolicy._enum_values(UnrecoverableAction)
            raise ConfigurationError(f"ToolErrorPolicy.on_unrecoverable must be one of {allowed}.") from exc

    @staticmethod
    def _normalize_retry_kind(value: object) -> str:
        return str(getattr(value, "value", value)).strip().lower()

    @staticmethod
    def _enum_values(enum_type: type[Enum]) -> list[str]:
        return [item.value for item in enum_type]

    @staticmethod
    def _require_non_negative(name: str, value: int | float) -> None:
        if value < 0:
            raise ConfigurationError(f"ToolErrorPolicy.{name} must be non-negative.")

    @staticmethod
    def _require_at_least(
        name: str,
        value: int | float,
        minimum: int | float,
        *,
        minimum_name: str | None = None,
    ) -> None:
        if value >= minimum:
            return
        target = minimum_name or str(minimum)
        raise ConfigurationError(f"ToolErrorPolicy.{name} must be greater than or equal to {target}.")

    @staticmethod
    def _require_positive_if_present(name: str, value: int | None) -> None:
        if value is not None and value <= 0:
            raise ConfigurationError(f"ToolErrorPolicy.{name} must be greater than zero when provided.")

    def __repr__(self) -> str:
        # Returns a compact developer-readable representation of non-default policy values.
        return (
            "ToolErrorPolicy("
            f"max_retries_per_tool_call={self.max_retries_per_tool_call!r}, "
            f"retry_on={tuple(sorted(self.retry_on))!r}, "
            f"on_unrecoverable={self.on_unrecoverable.value!r}, "
            f"max_total_tool_errors={self.max_total_tool_errors!r}"
            ")"
        )


__all__ = ["ToolErrorPolicy", "UnrecoverableAction"]
