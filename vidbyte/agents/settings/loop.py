"""
FILE: vidbyte/agents/settings/loop.py

PURPOSE:
    Defines AgentLoopSettings, the canonical configuration object for all parameters that govern the agentic execution loop. Consolidates loop budget and behavioral constraints into a single validated class, replacing scattered flat kwargs with a structured developer-facing abstraction.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/agents layer, which owns agent construction, runtime dispatch, handoff, fork, and execution state.
    It should be read with `vidbyte/agents/settings/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.agents.settings.tool_error: imported by this file.
    - vidbyte.lib.errors: imported by this file.

FUNCTION INVENTORY:
    - AgentLoopSettings (class): public or navigational symbol owned here.

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

from vidbyte.agents.settings.tool_error import ToolErrorPolicy
from vidbyte.lib.errors import ConfigurationError

_POSITIVE_INT_FIELDS = (
    "max_iterations",
    "max_tokens",
    "max_tool_calls",
    "max_parallel_tool_calls",
    "max_retries",
    "context_window_budget",
    "compaction_trigger_tokens",
    "compaction_target_tokens",
)


class AgentLoopSettings:
    """Validated configuration object for all parameters governing the agentic execution loop."""

    def __init__(
        self,
        *,
        max_iterations: int | None = None,
        max_tokens: int | None = None,
        max_tool_calls: int | None = None,
        max_parallel_tool_calls: int | None = None,
        max_retries: int | None = None,
        timeout_seconds: float | None = None,
        context_window_budget: int | None = None,
        compaction_trigger_tokens: int | None = None,
        compaction_target_tokens: int | None = None,
        allowed_tools: tuple[str, ...] | None = None,
        tool_error_policy: ToolErrorPolicy | None = None,
    ) -> None:
        # Stores all loop parameters as instance attributes, then validates them immediately.
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.max_tool_calls = max_tool_calls
        self.max_parallel_tool_calls = max_parallel_tool_calls
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.context_window_budget = context_window_budget
        self.compaction_trigger_tokens = compaction_trigger_tokens
        self.compaction_target_tokens = compaction_target_tokens
        self.allowed_tools = allowed_tools
        self.tool_error_policy = tool_error_policy
        self._validate()

    def _validate(self) -> None:
        # Raises ConfigurationError for any constraint violation found on this settings object.
        self._validate_positive_int_fields()
        self._validate_timeout_seconds()
        self._validate_compaction_pair()
        self._validate_tool_error_policy()

    def _validate_positive_int_fields(self) -> None:
        # Each integer field must be strictly positive when provided.
        for field_name in _POSITIVE_INT_FIELDS:
            value = getattr(self, field_name)
            if value is not None and value <= 0:
                raise ConfigurationError(
                    f"AgentLoopSettings.{field_name} must be greater than zero when provided, got {value}."
                )

    def _validate_timeout_seconds(self) -> None:
        # timeout_seconds must be a positive float when provided.
        if self.timeout_seconds is not None and self.timeout_seconds <= 0.0:
            raise ConfigurationError(
                f"AgentLoopSettings.timeout_seconds must be greater than zero when provided, got {self.timeout_seconds}."
            )

    def _validate_compaction_pair(self) -> None:
        # compaction_target_tokens must be less than compaction_trigger_tokens when both are set.
        if (
            self.compaction_trigger_tokens is not None
            and self.compaction_target_tokens is not None
            and self.compaction_target_tokens >= self.compaction_trigger_tokens
        ):
            raise ConfigurationError(
                f"AgentLoopSettings.compaction_target_tokens ({self.compaction_target_tokens}) "
                f"must be less than compaction_trigger_tokens ({self.compaction_trigger_tokens})."
            )

    def _validate_tool_error_policy(self) -> None:
        # Ensures the nested policy is either absent or already validated by its own class.
        if self.tool_error_policy is not None and not isinstance(self.tool_error_policy, ToolErrorPolicy):
            raise ConfigurationError("AgentLoopSettings.tool_error_policy must be a ToolErrorPolicy instance when provided.")

    def to_runtime_config(self) -> "AgentRuntimeConfig":
        # Converts the subset of fields understood by the internal runtime into AgentRuntimeConfig.
        from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
        return AgentRuntimeConfig(
            max_iterations=self.max_iterations,
            max_tokens=self.max_tokens,
            max_tool_calls=self.max_tool_calls,
            compaction_trigger_tokens=self.compaction_trigger_tokens,
            compaction_target_tokens=self.compaction_target_tokens,
        )

    def __repr__(self) -> str:
        # Returns a compact developer-readable string showing only non-None fields.
        fields = {
            name: getattr(self, name)
            for name in (
                "max_iterations",
                "max_tokens",
                "max_tool_calls",
                "max_parallel_tool_calls",
                "max_retries",
                "timeout_seconds",
                "context_window_budget",
                "compaction_trigger_tokens",
                "compaction_target_tokens",
                "allowed_tools",
                "tool_error_policy",
            )
            if getattr(self, name) is not None
        }
        pairs = ", ".join(f"{k}={v!r}" for k, v in fields.items())
        return f"AgentLoopSettings({pairs})"
