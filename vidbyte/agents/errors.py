"""
FILE: vidbyte/agents/errors.py

PURPOSE:
    Defines typed, redacted diagnostic errors raised by BaseAgent and
    AgentRuntime at their configuration and execution boundaries. The classes
    retain the SDK's existing broad error categories while carrying enough
    context for a downstream coding agent to diagnose the failure safely.

ROLE IN CODEBASE:
    base.py raises construction and runner-boundary errors from this module.
    runtime.py raises tool and context-window boundary errors from this module.
    The shared vidbyte.lib.errors hierarchy remains the public compatibility
    root; this module does not own provider, MCP, or tool-package failures.

ARCHITECTURE NOTE:
    Static diagnosis belongs on the error class and invocation-specific state
    belongs at the raise site. This keeps error packets useful without placing
    prompts, credentials, raw provider payloads, or unbounded tool output in
    logs or model-visible results.

FUNCTION INVENTORY:
    - AgentDiagnosticErrorMixin.__init__: combines static context with
      allowlisted dynamic fields while preserving the inherited SDK error type.
    - AgentDiagnosticErrorMixin.to_context_packet: returns a copy of the
      self-contained safe error packet for internal diagnostics.

COMMON MODIFICATION PATTERNS:
    - Add one concrete class for one new failure mode, then use it at every
      matching raise site in base.py or runtime.py.
    - Keep new dynamic fields scalar, bounded, and free of prompt/tool content.
    - Update the matching source header and existing test reference together.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add credentials, prompt text, raw provider output, or tool
       arguments to dynamic context.
    2. Do not use one concrete error class for unrelated failure modes.
    3. Do not replace errors owned by providers, MCP, middleware, or tools;
       those packages own their own diagnostic contracts.

KNOWN EDGE CASES:
    - Tool errors can be converted to ToolResult values, so callers must pass
      only the public summary rather than the full packet to a model.
    - Existing callers catch shared SDK error bases. Every concrete class below
      deliberately subclasses the appropriate existing category.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/error_messages.md
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agentic-engineering-base-agent-runtime.md

TEST FILES:
    - tests/test_agent_base.py
    - tests/test_agent_runtime.py
    - tests/test_agent_tool_loop.py

CONCURRENCY MODEL:
    Error instances are invocation-local and immutable after construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from vidbyte.lib.errors import AgentExecutionError, ConfigurationError, PermissionDeniedError, ToolExecutionError, ToolRegistryError, VidbyteSdkError


class AgentDiagnosticErrorMixin:
    """Adds safe, static agent-context packets to compatible SDK error subclasses."""

    source_file: ClassVar[str] = "vidbyte/agents"
    source_function: ClassVar[str] = "unknown"
    description: ClassVar[str] = "An agent execution boundary rejected an invalid state."
    expected: ClassVar[str] = "The caller must satisfy the documented agent runtime contract."
    actual: ClassVar[str] = "The runtime observed an incompatible or incomplete invocation."
    blast_radius: ClassVar[tuple[str, ...]] = ("vidbyte/agents/base.py", "vidbyte/agents/runtime.py")
    possible_causes: ClassVar[tuple[str, ...]] = ("Caller configuration does not satisfy the documented contract.",)
    fix_approaches: ClassVar[tuple[str, ...]] = ("Inspect the dynamic context and the named source function before retrying.",)
    doc_links: ClassVar[tuple[str, ...]] = ("https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/agents/README.md",)
    test_files: ClassVar[tuple[str, ...]] = ("tests/test_agent_base.py", "tests/test_agent_runtime.py")

    def __init__(self, *, dynamic_context: Mapping[str, Any] | None = None) -> None:
        # Combines stable class facts with bounded invocation state without exposing secret payloads.
        safe_context = self._safe_dynamic_context(dynamic_context)
        details = {"diagnostic_error": type(self).__name__, "source_file": self.source_file, "source_function": self.source_function, "dynamic_context": safe_context}
        message = self._render_message(safe_context)
        if isinstance(self, VidbyteSdkError):
            super().__init__(message, details=details)
        else:
            super().__init__(message)
            self.details = details
        self._context_packet = self._build_context_packet(safe_context)

    def to_context_packet(self) -> dict[str, Any]:
        # Returns a detached packet so callers cannot mutate error-owned diagnostic state.
        return {key: self._copy_value(value) for key, value in self._context_packet.items()}

    def _render_message(self, dynamic_context: Mapping[str, Any]) -> str:
        # Produces a bounded human-readable summary while leaving full context in the packet.
        if not dynamic_context:
            return f"{type(self).__name__}: {self.description}"
        rendered = ", ".join(f"{key}={value}" for key, value in dynamic_context.items())
        return f"{type(self).__name__}: {self.description} ({rendered})"

    def _build_context_packet(self, dynamic_context: Mapping[str, Any]) -> dict[str, Any]:
        # Assembles the complete static-and-dynamic packet consumed by internal diagnostic tooling.
        return {"error_type": type(self).__name__, "source": {"file": self.source_file, "function": self.source_function}, "description": self.description, "expected_vs_actual": {"expected": self.expected, "actual": self.actual}, "dynamic_context": dict(dynamic_context), "blast_radius": self.blast_radius, "possible_causes": self.possible_causes, "fix_approaches": self.fix_approaches, "doc_links": self.doc_links, "test_files": self.test_files}

    @staticmethod
    def _safe_dynamic_context(dynamic_context: Mapping[str, Any] | None) -> dict[str, str | int | float | bool | None]:
        # Keeps only scalar, non-secret values so an exception is safe to log or attach to a result.
        safe: dict[str, str | int | float | bool | None] = {}
        for key, value in dict(dynamic_context or {}).items():
            key_text = str(key)
            if any(token in key_text.upper() for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH", "PROMPT", "ARGUMENT", "OUTPUT")):
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe[key_text] = value[:500] if isinstance(value, str) else value
        return safe

    @staticmethod
    def _copy_value(value: Any) -> Any:
        # Recursively copies simple packet containers before returning them to a caller.
        if isinstance(value, dict):
            return {key: AgentDiagnosticErrorMixin._copy_value(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return tuple(AgentDiagnosticErrorMixin._copy_value(item) for item in value)
        return value


class AgentNameRequiredError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.__init__"
    description = "Agent construction requires a non-empty name."
    expected = "BaseAgent must receive a stable non-empty name before it can create traces, state, or sessions."
    actual = "The caller supplied an empty or missing name."


class AgentSystemPromptRequiredError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.__init__"
    description = "Agent construction requires a non-empty system prompt."
    expected = "Every executable agent must declare the system instruction that frames its run."
    actual = "The caller supplied an empty or missing system prompt."


class NonLinearRuntimeFeatureError(AgentDiagnosticErrorMixin, ConfigurationError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.__init__"
    description = "The selected non-linear runtime does not support a requested linear-runtime feature."
    expected = "Middleware, continual tracing, context algorithms, aggregation, tool policies, tool settings, and output contracts must use compatible runtimes."
    actual = "The caller combined a non-linear runtime with an unsupported feature."
    possible_causes = ("A linear-only option was retained while changing the runtime type.",)
    fix_approaches = ("Select the linear runtime or remove the incompatible option before constructing the agent.",)

    def _render_message(self, dynamic_context: Mapping[str, Any]) -> str:
        # Preserves the established compatibility wording while adding a typed diagnostic packet.
        runtime_type = dynamic_context.get("runtime_type", "non_linear")
        feature_names = {"context_algorithm": "in-context learning algorithms", "continual_trace": "continual tracing", "multi_model_aggregation": "multi-model aggregation", "tool_error_policy": "tool_error_policy middleware", "tool_settings": "tool_settings", "output_contract": "output contracts"}
        feature = feature_names.get(str(dynamic_context.get("feature", "")), str(dynamic_context.get("feature", "requested feature")).replace("_", " "))
        return f"Agent uses non-linear runtime {runtime_type}, which does not support {feature}."


class AggregationProviderRequiredError(AgentDiagnosticErrorMixin, ConfigurationError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent._resolve_aggregate_plan"
    description = "Multi-model aggregation requires an explicit provider."
    expected = "Each generated proposer specification must identify a provider and model."
    actual = "The caller supplied multiple model names without a provider."


class LoopSettingsConflictError(AgentDiagnosticErrorMixin, ConfigurationError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent._resolve_loop_settings"
    description = "Loop settings cannot be supplied through both an object and flat keyword options."
    expected = "One canonical loop-settings source must own each limit."
    actual = "The caller supplied a settings object together with individual overrides."


class TracerAliasConflictError(AgentDiagnosticErrorMixin, ConfigurationError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent._resolve_tracer"
    description = "Only one of trace and tracer may configure an agent tracer."
    expected = "The public trace alias or the legacy tracer parameter must be the sole source of tracer configuration."
    actual = "The caller supplied both aliases."


class AgentToolMetadataRequiredError(AgentDiagnosticErrorMixin, ConfigurationError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.as_tool"
    description = "An agent exposed as a tool requires complete tool-facing metadata."
    expected = "Agent metadata must include name, description, and use cases before delegation."
    actual = "One or more required metadata fields are missing."


class AgentExecutionFailureError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.generate_reply"
    description = "The agent run failed after entering the public execution boundary."
    expected = "Input normalization, runner inference, tracing, context construction, and runtime dispatch must complete successfully."
    actual = "A non-cancellation exception escaped one of the execution phases."
    blast_radius = ("vidbyte/agents/base.py", "vidbyte/agents/runtime.py", "vidbyte/lib/runners")
    possible_causes = ("The selected runner, context, middleware, or runtime rejected the current invocation.",)
    fix_approaches = ("Inspect the chained exception type and safe dynamic phase data, then reproduce with the referenced agent tests.",)


class ActiveEventLoopExecutionError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.run"
    description = "The synchronous agent API cannot run inside an active event loop."
    expected = "Async callers must await arun or generate_reply instead of nesting asyncio.run."
    actual = "A synchronous wrapper detected an already-running event loop."


class AgentRunnerRequiredError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent._run_direct"
    description = "Direct agent execution requires an executable inferred runner."
    expected = "Provider and model configuration must resolve to a runnable model adapter."
    actual = "No runnable adapter was available for the requested direct run."


class RunnerProtocolError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent._invoke_runner"
    description = "The configured runner does not expose a supported invocation protocol."
    expected = "A runner must be callable or define run or arun."
    actual = "The runtime could not find any supported invocation method."


class ContextWindowRunnerTypeError(AgentDiagnosticErrorMixin, TypeError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._invoke_context_window_runner"
    description = "An inner context-window algorithm received an invalid runner handle."
    expected = "The inner algorithm boundary requires a RunnerHandle so it can preserve invocation helpers."
    actual = "A different object reached the context-window runner adapter."


class RuntimeUnknownToolError(AgentDiagnosticErrorMixin, ToolRegistryError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._get_tool"
    description = "The model requested a tool that is not registered in this agent runtime."
    expected = "Every parsed tool call must resolve from the agent-local catalog."
    actual = "Catalog lookup failed for the requested tool name."
    blast_radius = ("vidbyte/agents/runtime.py", "vidbyte/tools/catalog.py", "vidbyte/tools/types.py")


class RuntimeToolPermissionError(AgentDiagnosticErrorMixin, PermissionDeniedError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._check_permission"
    description = "The agent permission policy denied a model-requested tool call."
    expected = "A tool may execute only when the agent-local policy permits its declared permission."
    actual = "The policy returned DENY before the tool reached validation or execution."
    blast_radius = ("vidbyte/agents/runtime.py", "vidbyte/tools/security/permissions.py")


class RuntimeToolValidationError(AgentDiagnosticErrorMixin, ToolExecutionError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._validate_tool_call"
    description = "The model supplied invalid arguments for a registered tool."
    expected = "Tool-call arguments must satisfy the tool's declared validation contract."
    actual = "Validation returned a failure before execution began."


class RuntimeToolExecutionError(AgentDiagnosticErrorMixin, ToolExecutionError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._execute_tool"
    description = "A registered tool failed while executing within the agent runtime."
    expected = "Tool execution must return a ToolResult or raise a classified execution failure."
    actual = "The tool raised an unexpected exception during execution."
    blast_radius = ("vidbyte/agents/runtime.py", "vidbyte/tools/base.py", "vidbyte/tools/types.py")


class RuntimeToolTimeoutError(AgentDiagnosticErrorMixin, ToolExecutionError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._run_tool_execute"
    description = "A tool exceeded the configured direct-runtime execution timeout."
    expected = "Non-internal tools must finish within the configured timeout budget."
    actual = "The task remained incomplete when the timeout elapsed."


class RuntimeToolOutputSchemaError(AgentDiagnosticErrorMixin, ToolExecutionError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime.execute_tool_call"
    description = "A successful tool result did not satisfy its declared output schema."
    expected = "A tool with an output schema must return a result that validates against that schema."
    actual = "Schema validation rejected the successful tool output."


__all__ = ["ActiveEventLoopExecutionError", "AgentDiagnosticErrorMixin", "AgentExecutionFailureError", "AgentNameRequiredError", "AgentRunnerRequiredError", "AgentSystemPromptRequiredError", "AgentToolMetadataRequiredError", "AggregationProviderRequiredError", "ContextWindowRunnerTypeError", "LoopSettingsConflictError", "NonLinearRuntimeFeatureError", "RunnerProtocolError", "RuntimeToolExecutionError", "RuntimeToolOutputSchemaError", "RuntimeToolPermissionError", "RuntimeToolTimeoutError", "RuntimeToolValidationError", "RuntimeUnknownToolError", "TracerAliasConflictError"]
