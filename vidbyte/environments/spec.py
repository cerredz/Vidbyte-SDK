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
    - Name dispatch tables live in vidbyte.lib.config.harness_tables (the single
      source of truth mapping spec names to SDK classes); this module only validates
      names against them.
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

from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.config.harness_tables import (
    VIDBYTE_ALGORITHM_SETTINGS_OWNERS,
    VIDBYTE_MIDDLEWARE_TABLE,
    VIDBYTE_PASSTHROUGH_ALGORITHM_PRESETS,
    VIDBYTE_PRIMITIVE_TABLE,
    VIDBYTE_TOOL_TABLE,
)
from vidbyte.lib.registries.models import ProviderModelRegistry

SPEC_VERSION = "1"

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
        if self.preset in VIDBYTE_PASSTHROUGH_ALGORITHM_PRESETS:
            if self.settings:
                raise ValueError(f"Preset '{self.preset}' accepts no settings; got {_known(self.settings)}.")
            return self
        owner = VIDBYTE_ALGORITHM_SETTINGS_OWNERS[self.preset]
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
        if self.kind not in VIDBYTE_PRIMITIVE_TABLE:
            raise ValueError(
                f"Unknown context primitive kind '{self.kind}'. Valid kinds: {_known(VIDBYTE_PRIMITIVE_TABLE)}."
            )
        valid_placements = {member.value for member in ContextWindowPlacement}
        if self.placement not in valid_placements:
            raise ValueError(
                f"Unknown placement '{self.placement}'. Valid placements: {_known(valid_placements)}."
            )
        return self


class MiddlewareSpec(BaseModel):
    """One middleware pipeline entry named against VIDBYTE_MIDDLEWARE_TABLE."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_name(self) -> "MiddlewareSpec":
        # Middleware names must exist in the dispatch table.
        if self.name not in VIDBYTE_MIDDLEWARE_TABLE:
            raise ValueError(
                f"Unknown middleware '{self.name}'. Valid middleware: {_known(VIDBYTE_MIDDLEWARE_TABLE)}."
            )
        return self


class HarnessToolSpec(BaseModel):
    """One requested prebuilt tool named against VIDBYTE_TOOL_TABLE."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_name(self) -> "HarnessToolSpec":
        # Tool names must exist in the dispatch table.
        if self.name not in VIDBYTE_TOOL_TABLE:
            raise ValueError(f"Unknown tool '{self.name}'. Valid tools: {_known(VIDBYTE_TOOL_TABLE)}.")
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
        if self.context_algorithm.preset not in VIDBYTE_PASSTHROUGH_ALGORITHM_PRESETS:
            raise ValueError(
                f"Runtime '{self.runtime.kind}' does not support context-window algorithm "
                f"'{self.context_algorithm.preset}'."
            )


__all__ = [
    "SPEC_VERSION",
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
