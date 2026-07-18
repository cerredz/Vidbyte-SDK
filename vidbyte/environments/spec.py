"""Context Protocol Header

Description:
    Defines HarnessSpec, the declarative JSON-serializable description of how an
    agent is assembled from every configurable Vidbyte SDK surface, plus the
    dispatch tables that name middleware, tools, algorithms, and primitives.
Purpose:
    Makes harness configuration data instead of live objects so rollout pass
    rates are recordable, diffable, sweepable, and transmittable; validation
    fails at spec time, before any rollout spends tokens.
Architecture:
    - ModelSpec / LoopSpec / RuntimeSpec: Provider, loop-budget, and runtime axes.
    - ContextAlgorithmSpec / ContextPrimitiveSpec: Context-window configuration.
    - MiddlewareSpec / HarnessToolSpec / TraceSpec: Pipeline, tools, tracing.
    - HarnessSpec: Versioned aggregate with cross-field validation mirroring BaseAgent.
    - MIDDLEWARE_TABLE / TOOL_TABLE / ALGORITHM_SETTINGS_OWNERS / PRIMITIVE_TABLE:
      Single source of truth mapping spec names to SDK classes.
Relations:
    Resolved into live BaseAgents by vidbyte.environments.resolver; recorded into
    RolloutRecord.harness by vidbyte.environments.runner.
Similar Files:
    - vidbyte/agents/settings/loop.py: AgentLoopSettings mirrored by LoopSpec.
    - vidbyte/agents/runtimes/configs.py: Runtime configs mirrored by RuntimeSpec.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vidbyte.context.algorithms import (
    ErrorCorrectionAlgorithm,
    MultiProviderAgenticGraderAlgorithm,
    ProblemSpaceSearchAlgorithm,
    ReflexionAlgorithm,
    TrajectoryCheckpointAlgorithm,
)
from vidbyte.context.primitives import (
    ArtifactContextItem,
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    PlanContextItem,
    ProgressContextItem,
    ResponseContextItem,
    TaskContextItem,
    TextContextItem,
    ToolCallContextItem,
)
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.middleware.builtins import (
    AuditLogMiddleware,
    CanaryTripwireMiddleware,
    CircuitBreakerMiddleware,
    ConfusedDeputyGuardMiddleware,
    CostBudgetMiddleware,
    ExponentialBackoffRetryMiddleware,
    HoneypotToolMiddleware,
    LoopDetectionMiddleware,
    MessageHistoryCompactionMiddleware,
    ModelRetryMiddleware,
    RuntimeLimitMiddleware,
    SummaryCompactionMiddleware,
    TokenBudgetMiddleware,
    TokenRateLimitMiddleware,
    ToolPolicyMiddleware,
    ToolResultCompactionMiddleware,
    TraceReplacementCompactionMiddleware,
    TraceSummaryTailCompactionMiddleware,
)
from vidbyte.tools.builtins import (
    AttachMcpServerTool,
    CodeExecutionTool,
    ContextListTool,
    ContextRemoveTool,
    ContextUpsertTool,
    CreateHandoffTool,
    GlobTool,
    GrepTool,
    PatchTool,
    ReflexionTool,
    SearchMcpServersTool,
    SemanticSearchTool,
    TrajectoryCheckpointTool,
)
from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.document_retrieval import DocumentRetrievalTool
from vidbyte.tools.filesystem import (
    AppendTool,
    ChecksumTool,
    CopyTool,
    DeleteTool,
    DiffTool,
    ExistsTool,
    FindTool,
    ListDirTool,
    MakeDirTool,
    MoveTool,
    ReadBinaryTool,
    ReadLinesTool,
    ReadTextTool,
    ReplaceTextTool,
    StatTool,
    TouchTool,
    TreeTool,
    UnzipTool,
    WriteTextTool,
    ZipTool,
)

SPEC_VERSION = "1"

MIDDLEWARE_TABLE: dict[str, type] = {
    "audit_log": AuditLogMiddleware,
    "canary_tripwire": CanaryTripwireMiddleware,
    "circuit_breaker": CircuitBreakerMiddleware,
    "confused_deputy_guard": ConfusedDeputyGuardMiddleware,
    "cost_budget": CostBudgetMiddleware,
    "exponential_backoff_retry": ExponentialBackoffRetryMiddleware,
    "honeypot_tool": HoneypotToolMiddleware,
    "loop_detection": LoopDetectionMiddleware,
    "message_history_compaction": MessageHistoryCompactionMiddleware,
    "model_retry": ModelRetryMiddleware,
    "runtime_limits": RuntimeLimitMiddleware,
    "summary_compaction": SummaryCompactionMiddleware,
    "token_budget": TokenBudgetMiddleware,
    "token_rate_limit": TokenRateLimitMiddleware,
    "tool_policy": ToolPolicyMiddleware,
    "tool_result_compaction": ToolResultCompactionMiddleware,
    "trace_replacement_compaction": TraceReplacementCompactionMiddleware,
    "trace_summary_tail_compaction": TraceSummaryTailCompactionMiddleware,
}

# Tools whose constructor requires the resolved ContextManager instead of settings-only kwargs.
CONTEXT_MANAGER_TOOL_NAMES: frozenset[str] = frozenset(
    {"reflexion", "trajectory_checkpoint", "context_upsert", "context_list", "context_remove"}
)

# Filesystem tools take a FileSystemToolConfig; the resolver defaults root to the workspace.
# Keys equal each tool's runtime ToolSpec name so specs, permitted_tool_names, and
# model-facing schemas all share one namespace.
FILESYSTEM_TOOL_TABLE: dict[str, type] = {
    "append_text": AppendTool,
    "checksum": ChecksumTool,
    "copy": CopyTool,
    "delete": DeleteTool,
    "diff": DiffTool,
    "exists": ExistsTool,
    "find": FindTool,
    "list_dir": ListDirTool,
    "make_dir": MakeDirTool,
    "move": MoveTool,
    "read_binary": ReadBinaryTool,
    "read_lines": ReadLinesTool,
    "read_text": ReadTextTool,
    "replace_text": ReplaceTextTool,
    "stat": StatTool,
    "touch": TouchTool,
    "tree": TreeTool,
    "unzip": UnzipTool,
    "write_text": WriteTextTool,
    "zip": ZipTool,
}

TOOL_TABLE: dict[str, type] = {
    "attach_mcp_server": AttachMcpServerTool,
    "calculator": CalculatorTool,
    "code_execution": CodeExecutionTool,
    "context_list": ContextListTool,
    "context_remove": ContextRemoveTool,
    "context_upsert": ContextUpsertTool,
    "create_handoff": CreateHandoffTool,
    "document_retrieval": DocumentRetrievalTool,
    "glob": GlobTool,
    "grep": GrepTool,
    "patch_file": PatchTool,
    "reflexion": ReflexionTool,
    "search_mcp_servers": SearchMcpServersTool,
    "semantic_search": SemanticSearchTool,
    "trajectory_checkpoint": TrajectoryCheckpointTool,
    **FILESYSTEM_TOOL_TABLE,
}

ALGORITHM_SETTINGS_OWNERS: dict[str, type] = {
    "error_correction": ErrorCorrectionAlgorithm,
    "multi_provider_agentic_grader": MultiProviderAgenticGraderAlgorithm,
    "problem_space_search": ProblemSpaceSearchAlgorithm,
    "reflexion": ReflexionAlgorithm,
    "trajectory_checkpoints": TrajectoryCheckpointAlgorithm,
}

# Preset names that carry no settings-bearing algorithm dataclass.
PASSTHROUGH_ALGORITHM_PRESETS: frozenset[str] = frozenset(
    {"default", "raw_tool_outputs", "compact_tool_outputs", "hide_tool_outputs", "no_raw_tool_outputs"}
)

PRIMITIVE_TABLE: dict[str, type] = {
    "artifact": ArtifactContextItem,
    "document": DocumentContextItem,
    "environment": EnvironmentContextItem,
    "file": FileContextItem,
    "git_diff": GitDiffContextItem,
    "memory": MemoryContextItem,
    "plan": PlanContextItem,
    "progress": ProgressContextItem,
    "response": ResponseContextItem,
    "task": TaskContextItem,
    "text": TextContextItem,
    "tool_call": ToolCallContextItem,
}

_NON_LINEAR_RUNTIME_KINDS: frozenset[str] = frozenset({"mcts_search", "actor"})


def _known(names: Any) -> str:
    # Renders a sorted, comma-separated list of valid names for error messages.
    return ", ".join(sorted(names))


class ModelSpec(BaseModel):
    """Provider, model, and sampling configuration for the harness agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model: str
    temperature: float | None = None

    @model_validator(mode="after")
    def _validate_provider_and_model(self) -> "ModelSpec":
        # Validates provider and model against the SDK provider registry at spec time.
        ProviderModelRegistry.validate_provider(self.provider)
        ProviderModelRegistry.validate_model(self.model)
        return self


class LoopSpec(BaseModel):
    """Agentic-loop budgets mirroring AgentLoopSettings field-for-field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_iterations: int | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, gt=0)
    max_tool_calls: int | None = Field(default=None, gt=0)
    max_parallel_tool_calls: int | None = Field(default=None, gt=0)
    max_retries: int | None = Field(default=None, gt=0)
    timeout_seconds: float | None = Field(default=None, gt=0.0)
    context_window_budget: int | None = Field(default=None, gt=0)
    compaction_trigger_tokens: int | None = Field(default=None, gt=0)
    compaction_target_tokens: int | None = Field(default=None, gt=0)
    allowed_tools: tuple[str, ...] | None = None

    @model_validator(mode="after")
    def _validate_compaction_pair(self) -> "LoopSpec":
        # Mirrors AgentLoopSettings: compaction target must stay below the trigger.
        if (
            self.compaction_trigger_tokens is not None
            and self.compaction_target_tokens is not None
            and self.compaction_target_tokens >= self.compaction_trigger_tokens
        ):
            raise ValueError(
                f"compaction_target_tokens ({self.compaction_target_tokens}) must be less than "
                f"compaction_trigger_tokens ({self.compaction_trigger_tokens})."
            )
        return self


class RuntimeSpec(BaseModel):
    """Execution-runtime selection with actor-topology settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["linear", "mcts_search", "actor"] = "linear"
    topology: Literal["actor_model", "actor_model_p2p", "actor_model_broadcast"] = "actor_model_p2p"
    dynamic_actors: bool = False
    max_loop: int = Field(default=20, ge=1)
    termination_mode: Literal["coordinator", "quiescence"] = "coordinator"
    worker_model: str | None = None

    @model_validator(mode="after")
    def _validate_worker_model(self) -> "RuntimeSpec":
        # Actor worker models must exist in the provider registry.
        if self.worker_model is not None:
            ProviderModelRegistry.validate_model(self.worker_model)
        return self


class ContextAlgorithmSpec(BaseModel):
    """Context-window algorithm preset plus validated per-algorithm settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    preset: Literal[
        "default",
        "raw_tool_outputs",
        "compact_tool_outputs",
        "hide_tool_outputs",
        "no_raw_tool_outputs",
        "reflexion",
        "multi_provider_agentic_grader",
        "trajectory_checkpoints",
        "problem_space_search",
        "error_correction",
    ] = "default"
    tool_result_admission: Literal["raw", "compact", "hide_raw"] | None = None
    max_tool_result_chars: int | None = Field(default=None, gt=0)
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_settings_keys(self) -> "ContextAlgorithmSpec":
        # Settings keys must match the preset's algorithm dataclass fields exactly.
        if self.preset in PASSTHROUGH_ALGORITHM_PRESETS:
            if self.settings:
                raise ValueError(f"Preset '{self.preset}' accepts no settings; got {_known(self.settings)}.")
            return self
        owner = ALGORITHM_SETTINGS_OWNERS[self.preset]
        valid = {field.name for field in dataclasses.fields(owner)}
        unknown = set(self.settings) - valid
        if unknown:
            raise ValueError(
                f"Unknown settings for context algorithm '{self.preset}': {_known(unknown)}. "
                f"Valid settings: {_known(valid)}."
            )
        return self


class ContextPrimitiveSpec(BaseModel):
    """One context primitive to inject, with placement and managed-registry flag."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    fields: dict[str, Any] = Field(default_factory=dict)
    placement: str = ContextWindowPlacement.END_OF_CONTEXT.value
    managed: bool = False

    @model_validator(mode="after")
    def _validate_kind_and_placement(self) -> "ContextPrimitiveSpec":
        # Kind must name a known primitive and placement must be a valid enum value.
        if self.kind not in PRIMITIVE_TABLE:
            raise ValueError(
                f"Unknown context primitive kind '{self.kind}'. Valid kinds: {_known(PRIMITIVE_TABLE)}."
            )
        valid_placements = {member.value for member in ContextWindowPlacement}
        if self.placement not in valid_placements:
            raise ValueError(
                f"Unknown placement '{self.placement}'. Valid placements: {_known(valid_placements)}."
            )
        return self


class MiddlewareSpec(BaseModel):
    """One middleware pipeline entry named against MIDDLEWARE_TABLE."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_name(self) -> "MiddlewareSpec":
        # Middleware names must exist in the dispatch table.
        if self.name not in MIDDLEWARE_TABLE:
            raise ValueError(
                f"Unknown middleware '{self.name}'. Valid middleware: {_known(MIDDLEWARE_TABLE)}."
            )
        return self


class HarnessToolSpec(BaseModel):
    """One requested prebuilt tool named against TOOL_TABLE."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_name(self) -> "HarnessToolSpec":
        # Tool names must exist in the dispatch table.
        if self.name not in TOOL_TABLE:
            raise ValueError(f"Unknown tool '{self.name}'. Valid tools: {_known(TOOL_TABLE)}.")
        return self


class TraceSpec(BaseModel):
    """Tracer selection and continual-trace configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tracer: Literal["null", "debug"] = "null"
    continual: bool = False
    schema_preset: Literal["action"] = "action"
    schema_fields: dict[str, str] | None = None
    every_n_iterations: int = Field(default=5, gt=0)
    max_trace_iterations: int = Field(default=3, ge=1, le=3)


class HarnessSpec(BaseModel):
    """Versioned declarative description of a harness agent built from SDK primitives."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str = SPEC_VERSION
    name: str = Field(min_length=1)
    system_prompt: str | None = None
    system_prompt_ref: str | None = None
    model: ModelSpec
    runtime: RuntimeSpec = Field(default_factory=RuntimeSpec)
    loop: LoopSpec = Field(default_factory=LoopSpec)
    context_algorithm: ContextAlgorithmSpec = Field(default_factory=ContextAlgorithmSpec)
    context_primitives: tuple[ContextPrimitiveSpec, ...] = ()
    middleware: tuple[MiddlewareSpec, ...] = ()
    tools: tuple[HarnessToolSpec, ...] = ()
    trace: TraceSpec = Field(default_factory=TraceSpec)
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "HarnessSpec":
        # Enforces prompt exclusivity, duplicate names, and non-linear runtime limits.
        self._validate_prompt_choice()
        self._validate_unique_names()
        self._validate_runtime_compatibility()
        return self

    def _validate_prompt_choice(self) -> None:
        # Exactly one of system_prompt / system_prompt_ref must be provided.
        if (self.system_prompt is None) == (self.system_prompt_ref is None):
            raise ValueError("Provide exactly one of system_prompt or system_prompt_ref.")

    def _validate_unique_names(self) -> None:
        # Duplicate middleware or tool entries are almost always sweep-authoring mistakes.
        middleware_names = [entry.name for entry in self.middleware]
        if len(middleware_names) != len(set(middleware_names)):
            raise ValueError(f"Duplicate middleware names in spec: {middleware_names}.")
        tool_names = [entry.name for entry in self.tools]
        if len(tool_names) != len(set(tool_names)):
            raise ValueError(f"Duplicate tool names in spec: {tool_names}.")

    def _validate_runtime_compatibility(self) -> None:
        # Mirrors BaseAgent: non-linear runtimes reject middleware, continual trace, and algorithms.
        if self.runtime.kind not in _NON_LINEAR_RUNTIME_KINDS:
            return
        if self.middleware:
            raise ValueError(f"Runtime '{self.runtime.kind}' does not support middleware.")
        if self.trace.continual:
            raise ValueError(f"Runtime '{self.runtime.kind}' does not support continual tracing.")
        if self.context_algorithm.preset not in PASSTHROUGH_ALGORITHM_PRESETS:
            raise ValueError(
                f"Runtime '{self.runtime.kind}' does not support context-window algorithm "
                f"'{self.context_algorithm.preset}'."
            )


__all__ = [
    "ALGORITHM_SETTINGS_OWNERS",
    "CONTEXT_MANAGER_TOOL_NAMES",
    "FILESYSTEM_TOOL_TABLE",
    "MIDDLEWARE_TABLE",
    "PASSTHROUGH_ALGORITHM_PRESETS",
    "PRIMITIVE_TABLE",
    "SPEC_VERSION",
    "TOOL_TABLE",
    "ContextAlgorithmSpec",
    "ContextPrimitiveSpec",
    "HarnessSpec",
    "HarnessToolSpec",
    "LoopSpec",
    "MiddlewareSpec",
    "ModelSpec",
    "RuntimeSpec",
    "TraceSpec",
]
