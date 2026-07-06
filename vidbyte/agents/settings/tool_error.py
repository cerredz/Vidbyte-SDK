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
        error_verbosity: ErrorVerbosity | str = ErrorVerbosity.STANDARD,
        include_remediation_hint: bool = True,
        mark_provider_error_flag: bool = True,
        redact_exception_details: bool = True,
        on_unrecoverable: UnrecoverableAction | str = UnrecoverableAction.CONTINUE,
        max_total_tool_errors: int | None = None,
    ) -> None:
        # Stores policy knobs and validates them before runtime use.
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
        # Converts policy rendering knobs into formatter options.
        return ToolErrorRenderOptions(
            error_verbosity=self.error_verbosity,
            include_remediation_hint=self.include_remediation_hint,
            mark_provider_error_flag=self.mark_provider_error_flag,
            redact_exception_details=self.redact_exception_details,
        )

    def _validate(self) -> None:
        # Raises ConfigurationError when numeric policy values are inconsistent.
        if self.max_retries_per_tool_call < 0:
            raise ConfigurationError("ToolErrorPolicy.max_retries_per_tool_call must be non-negative.")
        if self.retry_backoff_base_seconds < 0:
            raise ConfigurationError("ToolErrorPolicy.retry_backoff_base_seconds must be non-negative.")
        if self.retry_backoff_multiplier < 1:
            raise ConfigurationError("ToolErrorPolicy.retry_backoff_multiplier must be greater than or equal to 1.")
        if self.retry_backoff_cap_seconds < self.retry_backoff_base_seconds:
            raise ConfigurationError("ToolErrorPolicy.retry_backoff_cap_seconds must be greater than or equal to retry_backoff_base_seconds.")
        if self.max_total_tool_errors is not None and self.max_total_tool_errors <= 0:
            raise ConfigurationError("ToolErrorPolicy.max_total_tool_errors must be greater than zero when provided.")

    @staticmethod
    def _normalize_retry_on(retry_on: Iterable[object] | None) -> frozenset[str]:
        # Converts enum-like or string retry kinds into stable lowercase strings.
        if retry_on is None:
            return _DEFAULT_RETRY_ON
        return frozenset(str(getattr(item, "value", item)).strip().lower() for item in retry_on if str(getattr(item, "value", item)).strip())

    @staticmethod
    def _normalize_error_verbosity(value: ErrorVerbosity | str) -> ErrorVerbosity:
        # Converts string verbosity values into the shared formatter enum.
        try:
            return value if isinstance(value, ErrorVerbosity) else ErrorVerbosity(str(value).lower())
        except ValueError as exc:
            raise ConfigurationError(f"ToolErrorPolicy.error_verbosity must be one of {[item.value for item in ErrorVerbosity]}.") from exc

    @staticmethod
    def _normalize_unrecoverable_action(value: UnrecoverableAction | str) -> UnrecoverableAction:
        # Converts string terminal-error actions into the policy enum.
        try:
            return value if isinstance(value, UnrecoverableAction) else UnrecoverableAction(str(value).lower())
        except ValueError as exc:
            raise ConfigurationError(f"ToolErrorPolicy.on_unrecoverable must be one of {[item.value for item in UnrecoverableAction]}.") from exc

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
