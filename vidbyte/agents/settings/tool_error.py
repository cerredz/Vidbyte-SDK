"""
FILE: vidbyte/agents/settings/tool_error.py

PURPOSE:
    Defines tool-error retry policy settings for agent loops. Gives AgentLoopSettings a validated nested policy for deciding when failed tool calls should retry, continue, or abort the run.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/agents layer, which owns agent construction, runtime dispatch, handoff, fork, and execution state.
    It should be read with `vidbyte/agents/settings/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.errors: imported by this file.

FUNCTION INVENTORY:
    - UnrecoverableAction (class): public or navigational symbol owned here.
    - ToolErrorPolicy (class): public or navigational symbol owned here.
    - ToolErrorPolicy (export): public or navigational symbol owned here.
    - UnrecoverableAction (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - ConfigurationError: raised, returned, or imported by this file. Keep context safe and grepable.
    - ValueError: raised, returned, or imported by this file. Keep context safe and grepable.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; scripts/test-agent-behavior.py, scripts/test-new-runners.py, and agent-runtime scripts when changing behavior.

CONCURRENCY MODEL:
    - No explicit concurrency primitive; keep future mutable state local to calls unless documented here.
"""
from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from vidbyte.lib.errors import ConfigurationError

_DEFAULT_RETRY_ON = frozenset(("timeout", "rate_limited", "upstream_error"))


class UnrecoverableAction(str, Enum):
    """Controls what the runtime does after a terminal tool error."""

    CONTINUE = "continue"
    ABORT_RUN = "abort_run"


class ToolErrorPolicy:
    """Validated settings for tool-error retry and abort behavior."""

    def __init__(
        self,
        *,
        max_retries_per_tool_call: int = 0,
        retry_on: Iterable[object] | None = None,
        retry_backoff_base_seconds: float = 0.5,
        retry_backoff_multiplier: float = 2.0,
        retry_backoff_cap_seconds: float = 30.0,
        retry_only_idempotent: bool = True,
        on_unrecoverable: UnrecoverableAction | str = UnrecoverableAction.CONTINUE,
        max_total_tool_errors: int | None = None,
    ) -> None:
        self.max_retries_per_tool_call = max_retries_per_tool_call
        self.retry_on = self._normalize_retry_on(retry_on)
        self.retry_backoff_base_seconds = retry_backoff_base_seconds
        self.retry_backoff_multiplier = retry_backoff_multiplier
        self.retry_backoff_cap_seconds = retry_backoff_cap_seconds
        self.retry_only_idempotent = retry_only_idempotent
        self.on_unrecoverable = self._normalize_unrecoverable_action(on_unrecoverable)
        self.max_total_tool_errors = max_total_tool_errors
        self._validate()

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
