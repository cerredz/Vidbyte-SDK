"""Context Protocol Header

PURPOSE:
    Defines the typed, redacted diagnostic errors raised by BaseAgent and
    AgentRuntime at their configuration and execution boundaries. Each class
    carries deep, static diagnosis (what the boundary expected, what it saw, the
    likely causes, and concrete fixes) so a downstream human or coding agent can
    resolve the failure without re-reading the whole runtime, while the mixin
    keeps prompts, credentials, raw provider payloads, and tool output out of
    every message and packet.
ROLE IN CODEBASE:
    base.py raises the construction and runner-boundary classes; runtime.py
    raises the tool and context-window boundary classes. Both import these from
    vidbyte.lib.errors, which re-exports this module alongside the shared SDK
    exception hierarchy in vidbyte.lib.errors.base. This module owns only agent
    execution diagnostics; providers, MCP, middleware, and tool packages own
    their own error contracts.
ARCHITECTURE:
    - AgentDiagnosticErrorMixin: base mixin that merges stable per-class facts
      with bounded, secret-filtered invocation state, renders a deep multi-line
      message, and exposes a detached diagnostic packet. Concrete classes each
      subclass the mixin plus the existing SDK error category they belong to, so
      callers that catch the broad category keep working.
    - Concrete construction/runner errors (base.py): AgentNameRequiredError,
      AgentSystemPromptRequiredError, NonLinearRuntimeFeatureError,
      AggregationProviderRequiredError, LoopSettingsConflictError,
      TracerAliasConflictError, AgentToolMetadataRequiredError,
      AgentExecutionFailureError, ActiveEventLoopExecutionError,
      AgentRunnerRequiredError, RunnerProtocolError.
    - Concrete tool/context errors (runtime.py): ContextWindowRunnerTypeError,
      RuntimeUnknownToolError, RuntimeToolPermissionError,
      RuntimeToolValidationError, RuntimeToolExecutionError,
      RuntimeToolTimeoutError, RuntimeToolOutputSchemaError.
FUNCTION INVENTORY:
    - AgentDiagnosticErrorMixin.__init__: combine static class facts with
      allowlisted dynamic fields while preserving the inherited SDK error type.
    - AgentDiagnosticErrorMixin.to_context_packet: return a detached copy of the
      self-contained safe error packet for internal diagnostics.
    - AgentDiagnosticErrorMixin._render_message: build the deep multi-line
      human-readable summary (expected/actual/cause/fix/origin/context).
    - AgentDiagnosticErrorMixin._build_context_packet / _safe_dynamic_context /
      _copy_value: assemble and defensively copy the redacted packet.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from vidbyte.lib.errors.base import (
    AgentExecutionError,
    ConfigurationError,
    PermissionDeniedError,
    ToolExecutionError,
    ToolRegistryError,
    VidbyteSdkError,
)


class AgentDiagnosticErrorMixin:
    """Adds safe, deep, static agent-context packets to compatible SDK error subclasses."""

    source_file: ClassVar[str] = "vidbyte/agents"
    source_function: ClassVar[str] = "unknown"
    description: ClassVar[str] = "An agent execution boundary rejected an invalid or incomplete state."
    expected: ClassVar[str] = "The caller must satisfy the documented agent runtime contract before this boundary runs."
    actual: ClassVar[str] = "The runtime observed an incompatible or incomplete invocation at this boundary."
    blast_radius: ClassVar[tuple[str, ...]] = ("vidbyte/agents/base.py", "vidbyte/agents/runtime.py")
    possible_causes: ClassVar[tuple[str, ...]] = ("Caller configuration does not satisfy the documented contract for this boundary.",)
    fix_approaches: ClassVar[tuple[str, ...]] = ("Inspect the dynamic context and the named source function, then correct the invocation before retrying.",)
    doc_links: ClassVar[tuple[str, ...]] = ("https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/agents/README.md",)
    test_files: ClassVar[tuple[str, ...]] = ("tests/test_agent_base.py", "tests/test_agent_runtime.py")

    def __init__(self, *, dynamic_context: Mapping[str, Any] | None = None) -> None:
        # Combines stable class facts with bounded invocation state without exposing secret payloads.
        safe_context = self._safe_dynamic_context(dynamic_context)
        details = {"diagnostic_error": type(self).__name__, "source_file": self.source_file, "source_function": self.source_function, "dynamic_context": safe_context}
        message = self._render_message(safe_context)
        # @intent preserve-broad-sdk-catch-contract
        # Every concrete class subclasses both this mixin and one existing SDK error category, so
        # existing callers that `except AgentExecutionError`/`except ToolExecutionError` keep working
        # unchanged. Route structured details through VidbyteSdkError.__init__ when that ancestor is
        # present; otherwise (e.g. plain TypeError) attach details directly so the deep packet is never
        # dropped just because the chosen category predates the SDK error base.
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
        # @intent depth-in-the-raised-message
        # The raised message is what a human or coding agent reads first, often without ever calling
        # to_context_packet(). Fold the load-bearing static diagnosis (expected vs actual, the most
        # likely cause, the first concrete fix, and the exact origin) directly into the message so a
        # failure is actionable from the traceback alone. Keep it multi-line and bounded; the full
        # structured packet still lives on the exception for tooling that wants every field.
        lines = [f"{type(self).__name__}: {self.description}"]
        lines.append(f"  Expected: {self.expected}")
        lines.append(f"  Actual:   {self.actual}")
        if self.possible_causes:
            lines.append(f"  Likely cause: {self.possible_causes[0]}")
        if self.fix_approaches:
            lines.append(f"  Suggested fix: {self.fix_approaches[0]}")
        lines.append(f"  Origin: {self.source_function} in {self.source_file}")
        if dynamic_context:
            rendered = ", ".join(f"{key}={value}" for key, value in dynamic_context.items())
            lines.append(f"  Context: {rendered}")
        return "\n".join(lines)

    def _build_context_packet(self, dynamic_context: Mapping[str, Any]) -> dict[str, Any]:
        # Assembles the complete static-and-dynamic packet consumed by internal diagnostic tooling.
        return {"error_type": type(self).__name__, "source": {"file": self.source_file, "function": self.source_function}, "description": self.description, "expected_vs_actual": {"expected": self.expected, "actual": self.actual}, "dynamic_context": dict(dynamic_context), "blast_radius": self.blast_radius, "possible_causes": self.possible_causes, "fix_approaches": self.fix_approaches, "doc_links": self.doc_links, "test_files": self.test_files}

    @staticmethod
    def _safe_dynamic_context(dynamic_context: Mapping[str, Any] | None) -> dict[str, str | int | float | bool | None]:
        # @intent redact-before-the-value-ever-lands-in-a-packet
        # A tool error can be converted to a model-visible ToolResult and any error can be logged, so a
        # single leaked key here can surface a secret to a model or an operator dashboard. Filter by
        # key name and drop non-scalar values up front rather than trusting each raise site to pass
        # only clean data; a new caller must not be able to widen the exposure by accident.
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
    expected = "BaseAgent must receive a stable, non-empty name that will identify its traces, durable-session records, and handoff artifacts for the life of the agent."
    actual = "The caller passed an empty string, None, or an omitted name, so the agent would have no stable identity to attach observability and session state to."
    possible_causes = (
        "The name was read from configuration or an environment variable that resolved to an empty string.",
        "A wrapper constructed the agent from partial user input without validating a name first.",
    )
    fix_approaches = (
        "Pass a concrete non-empty name (for example name=\"researcher\") to BaseAgent/Agent.",
        "Validate and default the name upstream before it reaches the constructor.",
    )


class AgentSystemPromptRequiredError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.__init__"
    description = "Agent construction requires a non-empty system prompt."
    expected = "Every executable agent must declare the system instruction that frames its behavior; the runtime prepends it to the model conversation on every run."
    actual = "The caller passed an empty or missing system_prompt, so the agent has no instruction to send to the model."
    possible_causes = (
        "A prompt asset or template resolved to an empty string before construction.",
        "system_prompt was left unset when copying an agent config from another source.",
    )
    fix_approaches = (
        "Provide a concrete system_prompt describing the agent's role and constraints.",
        "If the prompt is loaded from disk or a registry, assert it is non-empty before constructing the agent.",
    )


class NonLinearRuntimeFeatureError(AgentDiagnosticErrorMixin, ConfigurationError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.__init__"
    description = "The selected non-linear runtime does not support a requested linear-runtime feature."
    expected = "Middleware, continual tracing, in-context learning algorithms, multi-model aggregation, tool error policy, tool settings, and output contracts are hooks of the linear execution loop and must be used with the linear runtime."
    actual = "The caller combined a search or actor (non-linear) runtime with one of those linear-only features, which that runtime cannot honor, so the option would be silently ignored at run time."
    blast_radius = ("vidbyte/agents/base.py", "vidbyte/agents/runtime.py", "vidbyte/agents/runtimes")
    possible_causes = (
        "A linear-only option (e.g. middleware=, trace_option=, algorithm=, proposers=/aggregate=, tool_error_policy, tool_settings, output_schema) was left in place while switching runtime= to a search or actor runtime.",
        "An AgentLoopSettings object carrying a tool policy or output contract was reused across runtimes.",
    )
    fix_approaches = (
        "Select the linear runtime (AgentRuntimeType.LINEAR) to keep the requested feature.",
        "Remove the incompatible option before constructing the agent on a non-linear runtime.",
    )

    def _render_message(self, dynamic_context: Mapping[str, Any]) -> str:
        # @intent keep-established-compatibility-sentence-then-add-depth
        # Callers and tests already match on the exact phrase "does not support <feature>"; that
        # sentence is the stable public contract for this error. Render it first verbatim, then append
        # the same deep expected/actual/cause/fix diagnosis every other class provides. Reordering or
        # rewording the first line would silently break assertions that depend on it.
        runtime_type = dynamic_context.get("runtime_type", "non_linear")
        feature_names = {"context_algorithm": "in-context learning algorithms", "continual_trace": "continual tracing", "multi_model_aggregation": "multi-model aggregation", "tool_error_policy": "tool_error_policy middleware", "tool_settings": "tool_settings", "output_contract": "output contracts"}
        feature = feature_names.get(str(dynamic_context.get("feature", "")), str(dynamic_context.get("feature", "requested feature")).replace("_", " "))
        lines = [f"Agent uses non-linear runtime {runtime_type}, which does not support {feature}."]
        lines.append(f"  Expected: {self.expected}")
        lines.append(f"  Actual:   {self.actual}")
        lines.append(f"  Likely cause: {self.possible_causes[0]}")
        lines.append(f"  Suggested fix: Use AgentRuntimeType.LINEAR to keep {feature}, or drop {feature} on runtime {runtime_type}.")
        lines.append(f"  Origin: {self.source_function} in {self.source_file}")
        return "\n".join(lines)


class AggregationProviderRequiredError(AgentDiagnosticErrorMixin, ConfigurationError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent._resolve_aggregate_plan"
    description = "Multi-model aggregation requires an explicit provider."
    expected = "When model_name is a list of two or more models, each generated proposer specification must name both a provider and a model so the aggregator can route every fan-out call."
    actual = "The caller supplied a list of model names but no provider, so the proposer specs cannot be constructed."
    possible_causes = (
        "provider= was omitted while passing model_name=[...] to request multi-model aggregation.",
        "The provider was expected to be inferred per-model, which the aggregate planner does not do for a bare list.",
    )
    fix_approaches = (
        "Pass provider=... alongside the list of model names.",
        "Use explicit proposers=[ProposerSpec(provider=..., model=...), ...] to name a provider per proposer.",
    )


class LoopSettingsConflictError(AgentDiagnosticErrorMixin, ConfigurationError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent._resolve_loop_settings"
    description = "Loop settings cannot be supplied through both an AgentLoopSettings object and flat keyword overrides."
    expected = "Each agentic-loop limit must have one canonical owner: either a single agent_loop_settings object, or the flat keyword overrides (max_iterations/max_tokens/compaction_*), never both."
    actual = "The caller passed agent_loop_settings together with one or more flat overrides, so the effective limit would be ambiguous."
    possible_causes = (
        "A shared AgentLoopSettings was reused and then partially overridden with a flat keyword.",
        "Both the object form and the convenience keyword form were wired in by different layers of caller code.",
    )
    fix_approaches = (
        "Set every limit on the AgentLoopSettings object and remove the flat keyword overrides.",
        "Drop the agent_loop_settings object and pass only the flat keyword overrides.",
    )


class TracerAliasConflictError(AgentDiagnosticErrorMixin, ConfigurationError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent._resolve_tracer"
    description = "Only one of trace= and tracer= may configure an agent tracer."
    expected = "Tracer configuration must have a single source: the public trace= alias or the legacy tracer= parameter, so there is no ambiguity about which tracer is installed."
    actual = "The caller supplied both trace= and tracer=, so the intended tracer is undefined."
    possible_causes = (
        "Code was migrated from the legacy tracer= keyword to the public trace= alias but left both set.",
        "A wrapper forwarded tracer= while the caller also passed trace=.",
    )
    fix_approaches = (
        "Keep trace= (the public alias) and remove tracer=.",
        "Or keep the legacy tracer= and remove trace=.",
    )


class AgentToolMetadataRequiredError(AgentDiagnosticErrorMixin, ConfigurationError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.as_tool"
    description = "An agent exposed as a tool requires complete tool-facing metadata."
    expected = "Before an agent can be delegated to as a tool, its agent_metadata must provide a name, a description, and use_cases so a parent agent can decide when to call it."
    actual = "as_tool() was called while one or more of name, description, or use_cases was empty; the dynamic context flags exactly which fields are missing."
    possible_causes = (
        "agent_metadata was left at its empty default (AgentMetadata()).",
        "Only some metadata fields were filled in before exposing the agent as a tool.",
    )
    fix_approaches = (
        "Construct the agent with agent_metadata=AgentMetadata(name=..., description=..., use_cases=...).",
        "Fill the specific field(s) flagged missing in this error's dynamic context.",
    )


class AgentExecutionFailureError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.generate_reply"
    description = "The agent run failed after entering the public execution boundary."
    expected = "Input normalization, runner inference, trace start, context construction, and runtime dispatch must all complete so the run can produce an AgentMessage."
    actual = "A non-cancellation exception escaped one of those execution phases; it is chained as the __cause__ of this error and named by cause_type in the dynamic context."
    blast_radius = ("vidbyte/agents/base.py", "vidbyte/agents/runtime.py", "vidbyte/lib/runners")
    possible_causes = (
        "The selected runner rejected the request (bad credentials, unsupported model, provider outage).",
        "Context construction, middleware, or the runtime loop raised while processing the invocation.",
    )
    fix_approaches = (
        "Read the chained __cause__ exception and the cause_type/phase in the dynamic context to locate the failing phase.",
        "Reproduce with the referenced agent tests (tests/test_agent_base.py, tests/test_agent_runtime.py) using the same configuration.",
    )


class ActiveEventLoopExecutionError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent.run"
    description = "The synchronous agent API cannot run inside an already-running event loop."
    expected = "run()/run_sequentially() own the event loop via asyncio.run and may only be called from synchronous code with no loop running."
    actual = "A synchronous entry point (named by entrypoint in the dynamic context) detected an already-running event loop, where nesting asyncio.run would raise."
    possible_causes = (
        "run() was called from inside async code (e.g. a coroutine, a notebook cell with a running loop, or an async web handler).",
        "A framework started an event loop before the synchronous wrapper was invoked.",
    )
    fix_approaches = (
        "From async code, await agent.arun(...) / agent.generate_reply(...) instead of calling run().",
        "For sequential prompts from async code, await agent.arun_sequentially(...).",
    )


class AgentRunnerRequiredError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent._run_direct"
    description = "Direct agent execution requires an executable, inferred runner."
    expected = "Provider and model configuration must resolve to a runnable model adapter before the direct loop starts."
    actual = "No runnable adapter reached the direct execution boundary (runner was None); runner_type in the dynamic context shows which modality was being resolved."
    possible_causes = (
        "provider/model_name did not resolve to a supported adapter in lib.runners.",
        "A custom code path called the direct executor without first inferring a runner.",
    )
    fix_approaches = (
        "Supply a valid provider and model_name so Runner.from_model can build an adapter.",
        "If overriding execution, ensure a runner is inferred and passed before _run_direct.",
    )


class RunnerProtocolError(AgentDiagnosticErrorMixin, AgentExecutionError):
    source_file = "vidbyte/agents/base.py"
    source_function = "BaseAgent._invoke_runner"
    description = "The configured runner does not expose a supported invocation protocol."
    expected = "A runner must be callable, or define an async arun(message, **kwargs), or define a run(message, **kwargs) method."
    actual = "The runtime inspected the runner (runner_class in the dynamic context) and found none of callable/arun/run, so it cannot invoke the model."
    possible_causes = (
        "A non-runner object was passed where a runner was expected.",
        "A custom runner implements a differently named invocation method.",
    )
    fix_approaches = (
        "Provide a runner that is callable or defines run/arun.",
        "Adapt a custom runner to expose arun(message, **kwargs) (preferred) or run(message, **kwargs).",
    )


class ContextWindowRunnerTypeError(AgentDiagnosticErrorMixin, TypeError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._invoke_context_window_runner"
    description = "An inner context-window algorithm received an invalid runner handle."
    expected = "The inner context-window algorithm boundary requires a RunnerHandle so it can preserve the model invocation and text/metadata extraction helpers across iterations."
    actual = "A different object (named by got_type in the dynamic context) reached the context-window runner adapter instead of a RunnerHandle."
    possible_causes = (
        "A context-window algorithm was invoked with a raw runner instead of the wrapped RunnerHandle.",
        "A custom algorithm reconstructed or replaced the handle with an incompatible object.",
    )
    fix_approaches = (
        "Pass the RunnerHandle the runtime built rather than the underlying runner.",
        "In a custom algorithm, forward the handle unchanged to the runtime invocation helper.",
    )


class RuntimeUnknownToolError(AgentDiagnosticErrorMixin, ToolRegistryError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._get_tool"
    description = "The model requested a tool that is not registered in this agent runtime."
    expected = "Every parsed tool call must resolve to a tool in the agent-local catalog that was advertised to the model."
    actual = "Catalog lookup failed for the requested tool name (tool_name in the dynamic context), so there is nothing to authorize or execute."
    blast_radius = ("vidbyte/agents/runtime.py", "vidbyte/tools/catalog.py", "vidbyte/tools/types.py")
    possible_causes = (
        "The model hallucinated or misspelled a tool name that was never registered.",
        "The tool set advertised to the model diverged from the agent-local catalog (e.g. a tool was removed after the prompt was built).",
    )
    fix_approaches = (
        "Register the tool on the agent, or confirm the advertised tool schemas match the catalog.",
        "If intentional, rely on tool settings/permission policy to shape the advertised set so the model cannot request the missing tool.",
    )


class RuntimeToolPermissionError(AgentDiagnosticErrorMixin, PermissionDeniedError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._check_permission"
    description = "The agent permission policy denied a model-requested tool call."
    expected = "A tool may execute only when the agent-local PermissionPolicy permits its declared permission for the current call."
    actual = "The policy returned DENY for the requested tool (tool_name/permission in the dynamic context) before it reached validation or execution."
    blast_radius = ("vidbyte/agents/runtime.py", "vidbyte/tools/security/permissions.py")
    possible_causes = (
        "The tool's declared permission (e.g. WRITE, NETWORK) is not granted by the configured policy.",
        "A restrictive default policy was left in place for an agent that legitimately needs the tool.",
    )
    fix_approaches = (
        "Grant the tool's declared permission in the agent's PermissionPolicy if the call is intended.",
        "If the denial is correct, adjust the advertised tools or system prompt so the model stops requesting it.",
    )


class RuntimeToolValidationError(AgentDiagnosticErrorMixin, ToolExecutionError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._validate_tool_call"
    description = "The model supplied invalid arguments for a registered tool."
    expected = "Tool-call arguments must satisfy the tool's declared parameter/validation contract before execution begins."
    actual = "Validation rejected the model's arguments for the tool (tool_name in the dynamic context) before any execution ran."
    blast_radius = ("vidbyte/agents/runtime.py", "vidbyte/tools/base.py", "vidbyte/tools/types.py")
    possible_causes = (
        "A required parameter was missing, mistyped, or out of range in the model's tool call.",
        "The tool's declared schema is stricter than the model was told, so valid-looking calls are rejected.",
    )
    fix_approaches = (
        "Confirm the tool's parameter schema and the description advertised to the model agree.",
        "Loosen or correct the validation contract, or improve the tool description so the model produces valid arguments.",
    )


class RuntimeToolExecutionError(AgentDiagnosticErrorMixin, ToolExecutionError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._execute_tool"
    description = "A registered tool raised an unexpected exception while executing within the agent runtime."
    expected = "Tool execution must either return a ToolResult or raise a classified tool failure that the runtime can convert into a model-visible result."
    actual = "The tool (tool_name/cause_type in the dynamic context) raised an unclassified exception during execution."
    blast_radius = ("vidbyte/agents/runtime.py", "vidbyte/tools/base.py", "vidbyte/tools/types.py")
    possible_causes = (
        "The tool's implementation hit an unhandled error (I/O failure, bad external response, internal bug).",
        "The tool depends on state or credentials that were unavailable at call time.",
    )
    fix_approaches = (
        "Read the chained __cause__ and cause_type to find the underlying failure in the tool body.",
        "Handle expected failures inside the tool and return a ToolResult so the model can adapt on the next turn.",
    )


class RuntimeToolTimeoutError(AgentDiagnosticErrorMixin, ToolExecutionError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime._run_tool_execute"
    description = "A tool exceeded the configured direct-runtime execution timeout."
    expected = "A non-internal tool must finish within the configured per-call timeout budget so one slow tool cannot stall the whole agent loop."
    actual = "The tool task (tool_name/timeout_seconds in the dynamic context) was still running when the timeout elapsed and was cancelled."
    blast_radius = ("vidbyte/agents/runtime.py", "vidbyte/agents/settings/tool.py")
    possible_causes = (
        "The tool performs slow or blocking work (large I/O, an unbounded external request).",
        "The configured timeout is too small for this tool's normal workload.",
    )
    fix_approaches = (
        "Make the tool faster or non-blocking, or add its own internal timeout/streaming.",
        "Raise the tool timeout in the agent's tool settings if the longer runtime is expected.",
    )


class RuntimeToolOutputSchemaError(AgentDiagnosticErrorMixin, ToolExecutionError):
    source_file = "vidbyte/agents/runtime.py"
    source_function = "AgentRuntime.execute_tool_call"
    description = "A successful tool result did not satisfy its declared output schema."
    expected = "A tool that declares an output schema must return a result whose value validates against that schema before it is placed in the model conversation."
    actual = "The tool (tool_name in the dynamic context) returned successfully, but schema validation rejected its output."
    blast_radius = ("vidbyte/agents/runtime.py", "vidbyte/providers/output_schema.py")
    possible_causes = (
        "The tool's returned shape drifted away from its declared output schema.",
        "The declared output schema is stricter than what the tool actually produces.",
    )
    fix_approaches = (
        "Make the tool return a value that matches its declared output schema.",
        "Update the output schema to reflect the tool's real, intended result shape.",
    )


__all__ = [
    "ActiveEventLoopExecutionError",
    "AgentDiagnosticErrorMixin",
    "AgentExecutionFailureError",
    "AgentNameRequiredError",
    "AgentRunnerRequiredError",
    "AgentSystemPromptRequiredError",
    "AgentToolMetadataRequiredError",
    "AggregationProviderRequiredError",
    "ContextWindowRunnerTypeError",
    "LoopSettingsConflictError",
    "NonLinearRuntimeFeatureError",
    "RunnerProtocolError",
    "RuntimeToolExecutionError",
    "RuntimeToolOutputSchemaError",
    "RuntimeToolPermissionError",
    "RuntimeToolTimeoutError",
    "RuntimeToolValidationError",
    "RuntimeUnknownToolError",
    "TracerAliasConflictError",
]
