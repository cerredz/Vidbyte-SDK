"""FILE: vidbyte/workflows/capabilities.py
PURPOSE: Enforces per-stage tool visibility, model routing, and independent action safety.
ROLE IN CODEBASE: graph.py stores profiles; AgentStage resolves tools and injects middleware.

ARCHITECTURE NOTE:
    Visibility removes tool schemas before the model runs. Action guards operate again
    at the execution boundary, so allowing Bash or an editor never implies every command
    or path is safe. Injected middleware is newly constructed for each stage invocation.

PUBLIC API INVENTORY:
    ToolVisibilityMode / ToolVisibility: Inherit, none, exact, or read-only catalogs.
    StageCapabilities / AgentModelRoute / ModelRetryPolicy: Per-stage execution profile.
    ActionContext / ActionDecision / ActionGuard / ActionPolicy: Safety contracts.
    CommandArgumentGuard / PathActionGuard / EditBudgetGuard: Built-in action policies.
    ActionImpact / ActionImpactEstimator / CallableImpactEstimator: Edit accounting.
    ToolCapabilityResolver / ActionPolicyMiddleware: Agent integration helpers.

COMMON MODIFICATION PATTERNS:
    Add a guard as a pure evaluate method with a stable guard_id. Stateful accounting
    belongs in a fresh middleware/guard instance, never a shared graph definition object.

WHAT NOT TO DO IN THIS FILE:
    1. Do not expose denied tools to the model and rely only on rejection afterward.
    2. Do not interpret shell text by executing it.
    3. Do not silently allow unmeasurable mutations in strict edit-budget mode.

KNOWN EDGE CASES:
    Custom/MCP tools without inspectable ToolSpec fail closed for READ_ONLY selection.
    Exact tool names must resolve once; duplicate names are ambiguous and rejected.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline adversarial smoke covers visibility,
    command/path denial, edit reservations, and unknown estimator behavior.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatchcase
from math import isfinite
import re
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.dataclasses.tools import ToolCall, ToolPermission, ToolSpec, ToolStatus
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.middleware.base import AgentMiddleware

from .detours import WorkflowSignal
from .errors import WorkflowCapabilityError


class ToolVisibilityMode(str, Enum):
    """How a stage derives the model-visible tool catalog from its base agent."""

    INHERIT = "inherit"
    NONE = "none"
    EXACT = "exact"
    READ_ONLY = "read_only"


@dataclass(frozen=True, slots=True)
class ToolVisibility:
    """One immutable model-visible tool selection rule."""

    mode: ToolVisibilityMode = ToolVisibilityMode.INHERIT
    names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Normalizes mode and exact tool names while rejecting contradictory settings.
        mode = self.mode if isinstance(self.mode, ToolVisibilityMode) else ToolVisibilityMode(self.mode)
        names = tuple(_required_text(name, "ToolVisibility.names item") for name in self.names)
        if mode is not ToolVisibilityMode.EXACT and names:
            raise ValueError("ToolVisibility.names is valid only for EXACT mode.")
        if mode is ToolVisibilityMode.EXACT and len(set(names)) != len(names):
            raise ValueError("ToolVisibility exact names must be unique.")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "names", names)

    @classmethod
    def inherit(cls) -> "ToolVisibility":
        # Keeps the base agent's complete tool catalog visible.
        return cls(ToolVisibilityMode.INHERIT)

    @classmethod
    def none(cls) -> "ToolVisibility":
        # Removes every user tool schema from the stage agent.
        return cls(ToolVisibilityMode.NONE)

    @classmethod
    def exact(cls, *names: str) -> "ToolVisibility":
        # Selects exactly the named tools in caller order.
        return cls(ToolVisibilityMode.EXACT, tuple(names))

    @classmethod
    def read_only(cls) -> "ToolVisibility":
        # Selects only tools whose ToolSpec permission is SAFE or READ.
        return cls(ToolVisibilityMode.READ_ONLY)


@dataclass(frozen=True, slots=True)
class ModelRetryPolicy:
    """Per-stage deterministic model retry settings."""

    max_attempts: int = 2
    sleep_seconds: float = 0.0

    def __post_init__(self) -> None:
        # Rejects invalid retry counts and non-finite delays at graph construction.
        if not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool) or self.max_attempts <= 0:
            raise ValueError("ModelRetryPolicy.max_attempts must be positive.")
        if not isinstance(self.sleep_seconds, (int, float)) or isinstance(self.sleep_seconds, bool) or not isfinite(self.sleep_seconds) or self.sleep_seconds < 0:
            raise ValueError("ModelRetryPolicy.sleep_seconds must be finite and non-negative.")
        object.__setattr__(self, "sleep_seconds", float(self.sleep_seconds))


@dataclass(frozen=True, slots=True)
class AgentModelRoute:
    """Provider/model/thinking/loop overrides applied to one fresh stage fork."""

    provider: ModelProvider | str | None = None
    model_name: str | None = None
    temperature: float | None = None
    runner_options: Mapping[str, Any] = field(default_factory=dict)
    max_iterations: int | None = None
    loop_settings: AgentLoopSettings | None = None
    model_retry: ModelRetryPolicy | None = None
    middleware_factories: tuple[Callable[[], AgentMiddleware], ...] = ()

    def __post_init__(self) -> None:
        # Validates immutable route values and per-invocation middleware factories.
        if self.temperature is not None:
            if not isinstance(self.temperature, (int, float)) or isinstance(self.temperature, bool) or not isfinite(self.temperature):
                raise ValueError("AgentModelRoute.temperature must be finite.")
            object.__setattr__(self, "temperature", float(self.temperature))
        if self.max_iterations is not None and (not isinstance(self.max_iterations, int) or isinstance(self.max_iterations, bool) or self.max_iterations <= 0):
            raise ValueError("AgentModelRoute.max_iterations must be positive when provided.")
        if self.loop_settings is not None and not isinstance(self.loop_settings, AgentLoopSettings):
            raise TypeError("AgentModelRoute.loop_settings must be AgentLoopSettings.")
        if self.model_retry is not None and not isinstance(self.model_retry, ModelRetryPolicy):
            raise TypeError("AgentModelRoute.model_retry must be ModelRetryPolicy.")
        if any(not callable(factory) for factory in self.middleware_factories):
            raise TypeError("AgentModelRoute.middleware_factories must contain callables.")
        object.__setattr__(self, "provider", self.provider.value if isinstance(self.provider, ModelProvider) else _optional_text(self.provider))
        object.__setattr__(self, "model_name", _optional_text(self.model_name))
        object.__setattr__(self, "runner_options", MappingProxyType(dict(self.runner_options)))
        object.__setattr__(self, "middleware_factories", tuple(self.middleware_factories))


@dataclass(frozen=True, slots=True)
class ActionImpact:
    """Estimated workspace mutation size used by cumulative stage edit budgets."""

    changed_lines: int | None
    paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Rejects negative estimates and normalizes impacted paths.
        if self.changed_lines is not None and (not isinstance(self.changed_lines, int) or isinstance(self.changed_lines, bool) or self.changed_lines < 0):
            raise ValueError("ActionImpact.changed_lines must be non-negative or None.")
        object.__setattr__(self, "paths", tuple(str(path) for path in self.paths))


@runtime_checkable
class ActionImpactEstimator(Protocol):
    """Deterministically estimates one tool call without executing it."""

    def estimate(self, call: ToolCall) -> ActionImpact:
        # Returns changed-line and path evidence, or an unknown changed-line value.
        ...


@dataclass(frozen=True, slots=True)
class CallableImpactEstimator:
    """Wraps a custom deterministic impact estimator under a stable ID."""

    estimator_id: str
    callback: Callable[[ToolCall], ActionImpact]

    def __post_init__(self) -> None:
        # Validates durable identity and callback shape before policy use.
        object.__setattr__(self, "estimator_id", _required_text(self.estimator_id, "CallableImpactEstimator.estimator_id"))
        if not callable(self.callback):
            raise TypeError("CallableImpactEstimator.callback must be callable.")

    def estimate(self, call: ToolCall) -> ActionImpact:
        # Delegates one pure estimate and enforces the typed result contract.
        result = self.callback(call)
        if not isinstance(result, ActionImpact):
            raise WorkflowCapabilityError("Impact estimator returned the wrong contract.", details={"estimator_id": self.estimator_id, "actual_type": type(result).__name__})
        return result


@dataclass(frozen=True, slots=True)
class ActionContext:
    """Bounded stage and tool-call facts visible to deterministic action guards."""

    stage: str
    call: ToolCall
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActionDecision:
    """One deterministic allow/deny result with bounded safe evidence."""

    allowed: bool
    code: str = "allowed"
    reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes decision identifiers and protects diagnostic metadata.
        object.__setattr__(self, "code", _required_text(self.code, "ActionDecision.code"))
        object.__setattr__(self, "reason", str(self.reason).strip())
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @classmethod
    def allow(cls, *, metadata: Mapping[str, Any] | None = None) -> "ActionDecision":
        # Builds an allowed action decision with optional safe evidence.
        return cls(True, metadata=metadata or {})

    @classmethod
    def deny(cls, code: str, reason: str, *, metadata: Mapping[str, Any] | None = None) -> "ActionDecision":
        # Builds a denied action decision that middleware returns before execution.
        return cls(False, code=code, reason=reason, metadata=metadata or {})


@runtime_checkable
class ActionGuard(Protocol):
    """Independent deterministic action safety rule."""

    @property
    def guard_id(self) -> str:
        # Returns a stable identity included in graph definition fingerprints.
        ...

    def evaluate(self, context: ActionContext) -> ActionDecision:
        # Allows or denies one call before permission checks and execution.
        ...


@dataclass(frozen=True, slots=True)
class CommandArgumentGuard:
    """Allows command prefixes and blocks deny patterns in one configured argument."""

    tool_names: frozenset[str]
    argument: str = "command"
    allow_prefixes: tuple[str, ...] = ()
    deny_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Compiles validation-safe rule inputs while preserving case-sensitive matching.
        object.__setattr__(self, "tool_names", frozenset(_required_text(name, "CommandArgumentGuard.tool_names item") for name in self.tool_names))
        object.__setattr__(self, "argument", _required_text(self.argument, "CommandArgumentGuard.argument"))
        object.__setattr__(self, "allow_prefixes", tuple(_required_text(item, "CommandArgumentGuard.allow_prefixes item") for item in self.allow_prefixes))
        object.__setattr__(self, "deny_patterns", tuple(_required_text(item, "CommandArgumentGuard.deny_patterns item") for item in self.deny_patterns))
        for pattern in self.deny_patterns:
            re.compile(pattern)

    @property
    def guard_id(self) -> str:
        # Identifies the versioned command argument safety contract.
        return "command_argument:v1"

    @property
    def definition_fingerprint(self) -> Mapping[str, Any]:
        # Includes every behavior-affecting command policy field in graph identity.
        return MappingProxyType({"guard_id": self.guard_id, "tool_names": sorted(self.tool_names), "argument": self.argument, "allow_prefixes": self.allow_prefixes, "deny_patterns": self.deny_patterns})

    def evaluate(self, context: ActionContext) -> ActionDecision:
        # Denies matching commands before considering a configured prefix allowlist.
        if context.call.tool_name not in self.tool_names:
            return ActionDecision.allow()
        value = context.call.arguments.get(self.argument)
        if not isinstance(value, str):
            return ActionDecision.deny("command_argument_missing", f"Tool argument {self.argument!r} must be a string.", metadata={"tool_name": context.call.tool_name, "argument": self.argument})
        for pattern in self.deny_patterns:
            if re.search(pattern, value):
                return ActionDecision.deny("command_pattern_denied", "Command matched a denied action pattern.", metadata={"tool_name": context.call.tool_name, "argument": self.argument, "pattern": pattern})
        if self.allow_prefixes and not any(value.startswith(prefix) for prefix in self.allow_prefixes):
            return ActionDecision.deny("command_prefix_not_allowed", "Command does not start with an allowed prefix.", metadata={"tool_name": context.call.tool_name, "argument": self.argument})
        return ActionDecision.allow()


@dataclass(frozen=True, slots=True)
class PathActionGuard:
    """Applies allow and deny globs to configured path arguments."""

    tool_names: frozenset[str]
    path_arguments: tuple[str, ...] = ("path",)
    allowed_globs: tuple[str, ...] = ()
    denied_globs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Normalizes path rules before any tool call reaches the guard.
        object.__setattr__(self, "tool_names", frozenset(_required_text(name, "PathActionGuard.tool_names item") for name in self.tool_names))
        object.__setattr__(self, "path_arguments", tuple(_required_text(item, "PathActionGuard.path_arguments item") for item in self.path_arguments))
        object.__setattr__(self, "allowed_globs", tuple(_required_text(item, "PathActionGuard.allowed_globs item") for item in self.allowed_globs))
        object.__setattr__(self, "denied_globs", tuple(_required_text(item, "PathActionGuard.denied_globs item") for item in self.denied_globs))

    @property
    def guard_id(self) -> str:
        # Identifies the versioned normalized path policy contract.
        return "path_action:v1"

    @property
    def definition_fingerprint(self) -> Mapping[str, Any]:
        # Includes normalized allow/deny path policy in graph identity.
        return MappingProxyType({"guard_id": self.guard_id, "tool_names": sorted(self.tool_names), "path_arguments": self.path_arguments, "allowed_globs": self.allowed_globs, "denied_globs": self.denied_globs})

    def evaluate(self, context: ActionContext) -> ActionDecision:
        # Denies absent, blocked, or non-allowlisted paths for configured tools.
        if context.call.tool_name not in self.tool_names:
            return ActionDecision.allow()
        paths = [context.call.arguments.get(name) for name in self.path_arguments if name in context.call.arguments]
        normalized = [str(path).replace("\\", "/") for path in paths if isinstance(path, (str, bytes))]
        if not normalized:
            return ActionDecision.deny("path_argument_missing", "No configured path argument was present.", metadata={"tool_name": context.call.tool_name, "path_arguments": self.path_arguments})
        for path in normalized:
            if any(fnmatchcase(path, pattern) for pattern in self.denied_globs):
                return ActionDecision.deny("path_denied", "Tool path matched a denied glob.", metadata={"tool_name": context.call.tool_name, "path": path})
            if self.allowed_globs and not any(fnmatchcase(path, pattern) for pattern in self.allowed_globs):
                return ActionDecision.deny("path_not_allowed", "Tool path did not match an allowed glob.", metadata={"tool_name": context.call.tool_name, "path": path})
        return ActionDecision.allow()


class EditBudgetGuard:
    """Reserves and commits estimated changed lines across one stage agent invocation."""

    def __init__(self, max_changed_lines: int, *, estimators: Mapping[str, ActionImpactEstimator] | None = None, mutating_tools: Sequence[str] = ("patch_file", "replace_text", "write_text"), strict: bool = True) -> None:
        # Creates per-invocation counters and installs built-in estimators by default.
        if not isinstance(max_changed_lines, int) or isinstance(max_changed_lines, bool) or max_changed_lines <= 0:
            raise ValueError("EditBudgetGuard.max_changed_lines must be positive.")
        self.max_changed_lines = max_changed_lines
        self.estimators = {**_builtin_estimators(), **dict(estimators or {})}
        self.mutating_tools = frozenset(mutating_tools)
        self.strict = strict
        self.committed_lines = 0
        self._reservations: dict[str, int] = {}

    @property
    def guard_id(self) -> str:
        # Identifies the versioned changed-line reservation contract.
        return "edit_budget:v1"

    @property
    def definition_fingerprint(self) -> Mapping[str, Any]:
        # Includes caps and stable estimator identities without callback serialization.
        estimators = {
            name: str(getattr(estimator, "estimator_id", f"{type(estimator).__module__}.{type(estimator).__qualname__}"))
            for name, estimator in sorted(self.estimators.items())
        }
        return MappingProxyType({"guard_id": self.guard_id, "max_changed_lines": self.max_changed_lines, "mutating_tools": sorted(self.mutating_tools), "strict": self.strict, "estimators": estimators})

    def evaluate(self, context: ActionContext) -> ActionDecision:
        # Reserves an estimate before execution or fails closed when it cannot be measured.
        call = context.call
        if call.tool_name not in self.mutating_tools:
            return ActionDecision.allow()
        estimator = self.estimators.get(call.tool_name)
        impact = estimator.estimate(call) if estimator is not None else ActionImpact(None)
        if impact.changed_lines is None:
            if self.strict:
                return ActionDecision.deny("edit_impact_unknown", "Mutating tool has no measurable changed-line impact in strict mode.", metadata={"tool_name": call.tool_name})
            return ActionDecision.allow(metadata={"impact_unknown": True, "tool_name": call.tool_name})
        reserved = sum(self._reservations.values())
        if self.committed_lines + reserved + impact.changed_lines > self.max_changed_lines:
            return ActionDecision.deny("edit_budget_exceeded", "Tool call would exceed the stage changed-line budget.", metadata={"tool_name": call.tool_name, "estimated_lines": impact.changed_lines, "committed_lines": self.committed_lines, "reserved_lines": reserved, "limit": self.max_changed_lines})
        key = call.call_id or f"{call.tool_name}:{id(call)}"
        self._reservations[key] = impact.changed_lines
        return ActionDecision.allow(metadata={"reservation_key": key, "estimated_lines": impact.changed_lines, "paths": impact.paths})

    def finalize(self, call: ToolCall, *, succeeded: bool) -> None:
        # Commits successful reservations and releases failed or denied tool calls.
        key = call.call_id or f"{call.tool_name}:{id(call)}"
        reserved = self._reservations.pop(key, 0)
        if succeeded:
            self.committed_lines += reserved


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    """Ordered independent action guards applied before every visible tool executes."""

    guards: tuple[ActionGuard, ...] = ()

    def __post_init__(self) -> None:
        # Validates structural guard contracts and preserves declaration order.
        if any(not isinstance(guard, ActionGuard) for guard in self.guards):
            raise TypeError("ActionPolicy.guards must satisfy ActionGuard.")
        object.__setattr__(self, "guards", tuple(self.guards))


@dataclass(frozen=True, slots=True)
class StageCapabilities:
    """Per-stage model-visible tools plus independent execution-time action guards."""

    tools: ToolVisibility = field(default_factory=ToolVisibility.inherit)
    action_policy: ActionPolicy = field(default_factory=ActionPolicy)


class ToolCapabilityResolver:
    """Resolves an exact safe tool tuple before a stage agent is forked."""

    @classmethod
    def resolve(cls, tools: Sequence[object], visibility: ToolVisibility) -> tuple[object, ...]:
        # Applies visibility mode after rejecting duplicate or uninspectable tool specs.
        items = tuple(tools)
        if visibility.mode is ToolVisibilityMode.INHERIT:
            return items
        if visibility.mode is ToolVisibilityMode.NONE:
            return ()
        indexed = cls._index(items)
        if visibility.mode is ToolVisibilityMode.EXACT:
            missing = [name for name in visibility.names if name not in indexed]
            if missing:
                raise WorkflowCapabilityError("Exact stage tool visibility references missing tools.", details={"missing": missing, "available": sorted(indexed)})
            return tuple(indexed[name][0] for name in visibility.names)
        return tuple(tool for tool, spec in indexed.values() if spec.permission in {ToolPermission.SAFE, ToolPermission.READ})

    @classmethod
    def _index(cls, tools: Sequence[object]) -> dict[str, tuple[object, ToolSpec]]:
        # Builds a unique name/spec index and fails closed on opaque tool objects.
        indexed: dict[str, tuple[object, ToolSpec]] = {}
        for tool in tools:
            spec = cls._spec(tool)
            if spec.name in indexed:
                raise WorkflowCapabilityError("Stage tool names are ambiguous.", details={"tool_name": spec.name})
            indexed[spec.name] = (tool, spec)
        return indexed

    @staticmethod
    def _spec(tool: object) -> ToolSpec:
        # Resolves ToolSpec through the SDK structural contract with safe diagnostics.
        callback = getattr(tool, "spec", None)
        if not callable(callback):
            raise WorkflowCapabilityError("Stage tool is not inspectable for capability selection.", details={"tool_type": type(tool).__name__})
        try:
            spec = callback()
        except Exception as exc:
            raise WorkflowCapabilityError("Stage tool spec resolution failed.", details={"tool_type": type(tool).__name__, "cause_type": type(exc).__name__}) from exc
        if not isinstance(spec, ToolSpec):
            raise WorkflowCapabilityError("Stage tool spec has the wrong contract.", details={"tool_type": type(tool).__name__, "spec_type": type(spec).__name__})
        return spec


class ActionPolicyMiddleware(AgentMiddleware):
    """Runs state-machine guards before caller middleware reaches tool execution."""

    name = "workflow_action_policy"

    def __init__(self, stage: str, policy: ActionPolicy) -> None:
        # Captures one fresh ordered guard set and evidence buffers for the stage run.
        self.stage = stage
        try:
            self.policy = deepcopy(policy)
        except Exception as exc:
            raise WorkflowCapabilityError("Action policy guards must be cloneable per stage invocation.", details={"stage": stage, "policy_type": type(policy).__name__}) from exc
        self.decisions: list[ActionDecision] = []
        self.signals: list[WorkflowSignal] = []

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Denies on the first guard rejection and records only bounded safe evidence.
        if ctx.tool_call is None or ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        context = ActionContext(self.stage, ctx.tool_call, ctx.metadata)
        for guard in self.policy.guards:
            decision = guard.evaluate(context)
            self.decisions.append(decision)
            if not decision.allowed:
                return MiddlewareDecision.deny_tool(decision.code, metadata={"guard_id": guard.guard_id, "reason": decision.reason, **dict(decision.metadata)})
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Finalizes edit reservations and converts successful calls into bounded signals.
        if ctx.tool_call is None or ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        succeeded = ctx.tool_result is not None and ctx.tool_result.status is ToolStatus.SUCCESS
        for guard in self.policy.guards:
            finalize = getattr(guard, "finalize", None)
            if callable(finalize):
                finalize(ctx.tool_call, succeeded=succeeded)
        if succeeded:
            data = _signal_data(ctx.tool_call, ctx.tool_result.metadata if ctx.tool_result else {})
            self.signals.append(WorkflowSignal("tool.succeeded", ctx.tool_call.tool_name, data))
            if ctx.tool_call.tool_name in {"patch_file", "replace_text", "write_text"} and "path" in data:
                self.signals.append(WorkflowSignal("file.changed", ctx.tool_call.tool_name, data))
        return MiddlewareDecision.continue_()


class _PatchImpactEstimator:
    """Estimates patch_file changed lines from a unified-diff-like argument."""

    def estimate(self, call: ToolCall) -> ActionImpact:
        # Counts added/removed content lines while excluding diff headers.
        patch = str(call.arguments.get("patch", call.arguments.get("diff", "")))
        changed = sum(1 for line in patch.splitlines() if (line.startswith("+") and not line.startswith("+++")) or (line.startswith("-") and not line.startswith("---")))
        return ActionImpact(changed, _call_paths(call))


class _ReplaceImpactEstimator:
    """Estimates replace_text changed lines from old and new text arguments."""

    def estimate(self, call: ToolCall) -> ActionImpact:
        # Uses the larger old/new line count as a conservative changed-line estimate.
        old_text = str(call.arguments.get("old_text", call.arguments.get("old", "")))
        new_text = str(call.arguments.get("new_text", call.arguments.get("new", "")))
        return ActionImpact(max(_line_count(old_text), _line_count(new_text)), _call_paths(call))


class _WriteImpactEstimator:
    """Estimates write_text changed lines from the replacement content."""

    def estimate(self, call: ToolCall) -> ActionImpact:
        # Counts the full written content because overwrite impact cannot be smaller safely.
        text = str(call.arguments.get("text", call.arguments.get("content", "")))
        return ActionImpact(_line_count(text), _call_paths(call))


def _builtin_estimators() -> dict[str, ActionImpactEstimator]:
    # Returns fresh stateless built-in estimators keyed by SDK mutating tool names.
    return {"patch_file": _PatchImpactEstimator(), "replace_text": _ReplaceImpactEstimator(), "write_text": _WriteImpactEstimator()}


def _signal_data(call: ToolCall, result_metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    # Builds bounded signal data from path-like arguments and safe result metadata.
    data: dict[str, Any] = {"call_id": call.call_id}
    for key in ("path", "file_path", "target_path"):
        value = call.arguments.get(key, result_metadata.get(key))
        if isinstance(value, str) and value:
            data["path"] = value
            break
    return data


def _call_paths(call: ToolCall) -> tuple[str, ...]:
    # Extracts normalized path-like tool arguments for impact evidence.
    paths = [call.arguments.get(key) for key in ("path", "file_path", "target_path")]
    return tuple(str(path).replace("\\", "/") for path in paths if isinstance(path, str) and path)


def _line_count(value: str) -> int:
    # Counts one logical changed line for non-empty text without a trailing newline.
    return 0 if not value else len(value.splitlines()) or 1


def _required_text(value: str, field_name: str) -> str:
    # Normalizes policy identifiers and reports the precise empty field.
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty.")
    return text


def _optional_text(value: str | None) -> str | None:
    # Normalizes optional provider/model identifiers without inventing values.
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "ActionContext",
    "ActionDecision",
    "ActionGuard",
    "ActionImpact",
    "ActionImpactEstimator",
    "ActionPolicy",
    "ActionPolicyMiddleware",
    "AgentModelRoute",
    "CallableImpactEstimator",
    "CommandArgumentGuard",
    "EditBudgetGuard",
    "ModelRetryPolicy",
    "PathActionGuard",
    "StageCapabilities",
    "ToolCapabilityResolver",
    "ToolVisibility",
    "ToolVisibilityMode",
]
