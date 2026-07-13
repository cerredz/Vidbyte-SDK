"""FILE: vidbyte/workflows/graph.py
PURPOSE: Declares, validates, fingerprints, and freezes agent-harness workflow graphs.
ROLE IN CODEBASE: SDK users build here; machine.py alone executes compiled definitions.

ARCHITECTURE NOTE:
    The mutable builder owns declarations only. Compilation validates every statically
    possible destination and state dependency, then snapshots an immutable definition.
    Outcome edges and command-goto edges use separate lookup tables, so model output can
    never invent a target. Cycles are intentionally legal and bounded at runtime.

PUBLIC API INVENTORY:
    StateGraph: Stage, terminal, transition, command, branch, detour, and child builder.
    compile(): Static validation plus stable definition identity and runtime creation.

COMMON MODIFICATION PATTERNS:
    Put declaration invariants in _GraphCompiler and execution behavior in machine.py.
    Include every behavior-affecting stable field in _definition_structure.

WHAT NOT TO DO IN THIS FILE:
    1. Do not invoke stages, validators, routers, models, or child graphs.
    2. Do not store current stage, run counters, events, or checkpoint state.
    3. Do not infer fallback destinations for unknown outcomes or command targets.
    4. Do not reject cycles merely because a graph is not a DAG.

KNOWN EDGE CASES:
    Python callback bodies and credentials cannot be fingerprinted. Durable callers must
    supply and bump graph version when hidden behavior changes.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke covers all declaration families.

CONCURRENCY:
    Builders are not thread-safe. Compiled records are immutable and share no run state.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Collection, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Generic

from .approval import ApprovalGate, RiskLevel
from .budget import ChildBudgetPolicy
from .capabilities import AgentModelRoute, StageCapabilities
from .contracts import MachineStatus, RouteTarget, Router, Stage, StagePolicy, StateMachineSettings, StateT, TerminalStatus, Validator
from .detours import DetourReturnMode, DetourRule
from .errors import WorkflowDefinitionError
from .events import workflow_json_value
from .persistence import WorkflowDefinitionRecord
from .state import StateCommitMode, StateSchema
from .subgraphs import ChildFailurePolicy, SubgraphBinding


@dataclass(frozen=True, slots=True)
class _StageDefinition(Generic[StateT]):
    """Immutable executable stage plus state and agent execution policy."""

    stage: Stage[StateT]
    validators: tuple[Validator[StateT], ...]
    policy: StagePolicy
    reads: frozenset[str]
    writes: frozenset[str]
    capabilities: StageCapabilities | None
    model_route: AgentModelRoute | None


@dataclass(frozen=True, slots=True)
class _DirectRoute(Generic[StateT]):
    """One statically declared target and ordered transition policy."""

    target: str
    guards: tuple[Validator[StateT], ...]
    approval: ApprovalGate | None = None
    risk: RiskLevel = RiskLevel.LOW


@dataclass(frozen=True, slots=True)
class _BranchRoute(Generic[StateT]):
    """One bounded router and branch-key destination map."""

    router: Router[StateT]
    routes: Mapping[str, _DirectRoute[StateT]]


@dataclass(frozen=True, slots=True)
class _DetourDefinition:
    """One signal rule and declared validation-path entry/return behavior."""

    rule: DetourRule
    target: str
    return_mode: DetourReturnMode
    rejection_outcome: str | None


@dataclass(frozen=True, slots=True)
class _CompiledGraph(Generic[StateT]):
    """Complete immutable definition snapshot consumed by StateMachine."""

    name: str
    version: str | None
    definition_id: str
    definition_record: WorkflowDefinitionRecord
    state_schema: StateSchema[StateT]
    stages: Mapping[str, _StageDefinition[StateT]]
    entry: str
    terminals: Mapping[str, TerminalStatus]
    routes: Mapping[tuple[str, str], _DirectRoute[StateT] | _BranchRoute[StateT]]
    command_routes: Mapping[tuple[str, str], _DirectRoute[StateT]]
    detours: tuple[_DetourDefinition, ...]
    subgraphs: Mapping[str, SubgraphBinding]
    settings: StateMachineSettings


class StateGraph(Generic[StateT]):
    """Mutable builder for typed, cyclic, guarded, resumable workflow graphs."""

    def __init__(
        self,
        state_type: Any,
        *,
        name: str = "workflow",
        version: str | None = None,
        state_schema: StateSchema[StateT] | None = None,
        state_validator: Callable[[Any], StateT] | None = None,
        state_cloner: Callable[[StateT], StateT] = deepcopy,
    ) -> None:
        # Compiles a root-compatible schema unless the caller supplies explicit channels.
        if state_schema is not None and not isinstance(state_schema, StateSchema):
            raise WorkflowDefinitionError("StateGraph.state_schema must be StateSchema when provided.", details={"actual_type": type(state_schema).__name__})
        if state_validator is not None and not callable(state_validator):
            raise WorkflowDefinitionError("StateGraph.state_validator must be callable when provided.", details={"actual_type": type(state_validator).__name__})
        if not callable(state_cloner):
            raise WorkflowDefinitionError("StateGraph.state_cloner must be callable.", details={"actual_type": type(state_cloner).__name__})
        self._name = _required_text(name, "graph name")
        self._version = _optional_text(version, "graph version")
        self._state_schema = state_schema or StateSchema.root(state_type, validator=state_validator, cloner=state_cloner)
        if state_schema is not None and state_schema.state_type != state_type:
            raise WorkflowDefinitionError("StateGraph.state_type must match StateSchema.state_type.", details={"graph": self._name})
        self._stages: dict[str, _StageDefinition[StateT]] = {}
        self._entry: str | None = None
        self._terminals: dict[str, TerminalStatus] = {}
        self._routes: dict[tuple[str, str], _DirectRoute[StateT] | _BranchRoute[StateT]] = {}
        self._command_routes: dict[tuple[str, str], _DirectRoute[StateT]] = {}
        self._detours: list[_DetourDefinition] = []
        self._subgraphs: dict[str, SubgraphBinding] = {}

    def add_stage(
        self,
        name: str,
        stage: Stage[StateT],
        *,
        validators: Sequence[Validator[StateT]] = (),
        policy: StagePolicy | None = None,
        reads: Collection[str] = (),
        writes: Collection[str] = (),
        capabilities: StageCapabilities | None = None,
        model_route: AgentModelRoute | None = None,
    ) -> "StateGraph[StateT]":
        # Declares one uniquely named stage with statically visible data/policy boundaries.
        stage_name = _required_text(name, "stage name")
        self._assert_name_is_available(stage_name)
        if not callable(getattr(stage, "run", None)):
            raise WorkflowDefinitionError("Workflow stage must provide a callable run(context) method.", details={"stage": stage_name, "actual_type": type(stage).__name__})
        resolved_policy = policy or StagePolicy()
        if not isinstance(resolved_policy, StagePolicy):
            raise WorkflowDefinitionError("StateGraph.add_stage policy must be StagePolicy.", details={"stage": stage_name, "actual_type": type(resolved_policy).__name__})
        if capabilities is not None and not isinstance(capabilities, StageCapabilities):
            raise WorkflowDefinitionError("StateGraph.add_stage capabilities must be StageCapabilities.", details={"stage": stage_name})
        if model_route is not None and not isinstance(model_route, AgentModelRoute):
            raise WorkflowDefinitionError("StateGraph.add_stage model_route must be AgentModelRoute.", details={"stage": stage_name})
        resolved_reads = _normalized_names(reads, "stage read channel")
        resolved_writes = _normalized_names(writes, "stage write channel")
        if self._state_schema.root_compatible:
            resolved_reads = resolved_reads or frozenset({"__root__"})
            resolved_writes = resolved_writes or frozenset({"__root__"})
        self._stages[stage_name] = _StageDefinition(stage, _validated_guards(validators, owner=f"stage:{stage_name}"), resolved_policy, resolved_reads, resolved_writes, capabilities, model_route)
        return self

    def set_entry(self, name: str) -> "StateGraph[StateT]":
        # Selects the sole initial stage; existence is checked after all declarations.
        self._entry = _required_text(name, "entry stage")
        return self

    def add_terminal(self, name: str, *, status: MachineStatus = MachineStatus.SUCCEEDED) -> "StateGraph[StateT]":
        # Declares one named normal completion outcome, successful or failed.
        terminal = _required_text(name, "terminal name")
        self._assert_name_is_available(terminal)
        try:
            resolved = status if isinstance(status, TerminalStatus) else TerminalStatus(status)
        except (TypeError, ValueError) as exc:
            raise WorkflowDefinitionError("Terminal status must be 'succeeded' or 'failed'.", details={"terminal": terminal}) from exc
        self._terminals[terminal] = resolved
        return self

    def add_transition(
        self,
        source: str,
        target: str,
        *,
        on: str = "success",
        guards: Sequence[Validator[StateT]] = (),
        approval: ApprovalGate | None = None,
        risk: RiskLevel = RiskLevel.LOW,
    ) -> "StateGraph[StateT]":
        # Declares one semantic-outcome route to a known-at-compile destination.
        key = self._route_key(source, on)
        self._assert_route_is_available(key)
        self._routes[key] = _direct_route(target, guards, approval, risk, owner=f"transition:{key[0]}:{key[1]}")
        return self

    def add_branch(
        self,
        source: str,
        router: Router[StateT],
        routes: Mapping[str, str | RouteTarget[StateT]],
        *,
        on: str = "success",
    ) -> "StateGraph[StateT]":
        # Declares one first-class conditional route with a closed branch key set.
        key = self._route_key(source, on)
        self._assert_route_is_available(key)
        if not callable(getattr(router, "route", None)):
            raise WorkflowDefinitionError("Workflow router must provide route(context).", details={"source": key[0], "actual_type": type(router).__name__})
        if not isinstance(routes, Mapping) or not routes:
            raise WorkflowDefinitionError("StateGraph.add_branch routes must be a non-empty mapping.", details={"source": key[0], "outcome": key[1]})
        normalized: dict[str, _DirectRoute[StateT]] = {}
        for raw_branch, raw_target in routes.items():
            branch = _required_text(raw_branch, "branch key")
            if branch in normalized:
                raise WorkflowDefinitionError("Normalized branch keys must be unique.", details={"source": key[0], "branch": branch})
            if isinstance(raw_target, RouteTarget):
                normalized[branch] = _direct_route(raw_target.target, raw_target.guards, raw_target.approval, raw_target.risk, owner=f"branch:{key[0]}:{key[1]}:{branch}")
            elif isinstance(raw_target, str):
                normalized[branch] = _direct_route(raw_target, (), None, RiskLevel.LOW, owner=f"branch:{key[0]}:{key[1]}:{branch}")
            else:
                raise WorkflowDefinitionError("Branch targets must be stage names or RouteTarget values.", details={"source": key[0], "branch": branch, "actual_type": type(raw_target).__name__})
        self._routes[key] = _BranchRoute(router, MappingProxyType(normalized))
        return self

    def add_command_transition(
        self,
        source: str,
        target: str,
        *,
        guards: Sequence[Validator[StateT]] = (),
        approval: ApprovalGate | None = None,
        risk: RiskLevel = RiskLevel.LOW,
    ) -> "StateGraph[StateT]":
        # Authorizes one exact WorkflowCommand.goto destination for one source stage.
        key = (_required_text(source, "command source"), _required_text(target, "command target"))
        if key in self._command_routes:
            raise WorkflowDefinitionError("A command source/target pair may be declared only once.", details={"source": key[0], "target": key[1]})
        self._command_routes[key] = _direct_route(target, guards, approval, risk, owner=f"command:{key[0]}:{key[1]}")
        return self

    def add_detour(
        self,
        rule: DetourRule,
        *,
        target: str,
        return_mode: DetourReturnMode = DetourReturnMode.RETRY_SOURCE,
        rejection_outcome: str | None = None,
    ) -> "StateGraph[StateT]":
        # Registers one ordered signal matcher and a bounded declared return strategy.
        if not isinstance(rule, DetourRule):
            raise WorkflowDefinitionError("StateGraph.add_detour rule must be DetourRule.", details={"actual_type": type(rule).__name__})
        if any(item.rule.rule_id == rule.rule_id for item in self._detours):
            raise WorkflowDefinitionError("Detour rule IDs must be unique.", details={"rule_id": rule.rule_id})
        mode = return_mode if isinstance(return_mode, DetourReturnMode) else DetourReturnMode(return_mode)
        self._detours.append(_DetourDefinition(rule, _required_text(target, "detour target"), mode, _optional_text(rejection_outcome, "detour rejection outcome")))
        return self

    def add_subgraph(
        self,
        name: str,
        machine: Any,
        *,
        input_mapper: Callable[[Any, Any], Any],
        summary_mapper: Callable[[Any, Any], Mapping[str, Any]],
        writes: Collection[str],
        budget: ChildBudgetPolicy | None = None,
        failure_policy: ChildFailurePolicy = ChildFailurePolicy.FAIL_FAST,
    ) -> "StateGraph[StateT]":
        # Binds one isolated compiled child and explicit parent update boundary.
        subgraph_name = _required_text(name, "subgraph name")
        if subgraph_name in self._subgraphs:
            raise WorkflowDefinitionError("Subgraph names must be unique.", details={"subgraph": subgraph_name})
        if not callable(getattr(machine, "arun", None)) or not getattr(machine, "definition_id", None):
            raise WorkflowDefinitionError("StateGraph.add_subgraph machine must be a compiled StateMachine.", details={"subgraph": subgraph_name, "actual_type": type(machine).__name__})
        binding = SubgraphBinding(subgraph_name, machine, input_mapper, summary_mapper, _normalized_names(writes, "subgraph write channel"), budget or ChildBudgetPolicy(), failure_policy)
        self._subgraphs[subgraph_name] = binding
        return self

    def compile(self, *, settings: StateMachineSettings | None = None) -> Any:
        # Validates and freezes the declaration before constructing the runtime façade.
        from .machine import StateMachine

        resolved = settings or StateMachineSettings()
        if not isinstance(resolved, StateMachineSettings):
            raise WorkflowDefinitionError("StateGraph.compile settings must be StateMachineSettings.", details={"actual_type": type(resolved).__name__})
        return StateMachine(_GraphCompiler(self, resolved).compile())

    def _assert_name_is_available(self, name: str) -> None:
        # Prevents ambiguity across executable and terminal node namespaces.
        if name in self._stages or name in self._terminals:
            raise WorkflowDefinitionError("Workflow node names must be unique across stages and terminals.", details={"node": name, "graph": self._name})

    def _route_key(self, source: str, outcome: str) -> tuple[str, str]:
        # Normalizes a semantic outcome route key without changing case semantics.
        return (_required_text(source, "route source"), _required_text(outcome, "route outcome"))

    def _assert_route_is_available(self, key: tuple[str, str]) -> None:
        # Rejects direct/branch ambiguity for one semantic source/outcome pair.
        if key in self._routes:
            raise WorkflowDefinitionError("A source/outcome pair can have only one transition or branch.", details={"source": key[0], "outcome": key[1]})


class _GraphCompiler(Generic[StateT]):
    """Runs static policy/control/data checks and creates one definition snapshot."""

    def __init__(self, graph: StateGraph[StateT], settings: StateMachineSettings) -> None:
        # Retains the builder only for the duration of this synchronous compilation.
        self.graph = graph
        self.settings = settings

    def compile(self) -> _CompiledGraph[StateT]:
        # Executes all checks before calculating the durable definition identity.
        self._validate_required_nodes()
        self._validate_state_dependencies()
        self._validate_routes()
        self._validate_profiles()
        self._validate_recovery_routes()
        self._validate_reachability()
        structure = self._definition_structure()
        canonical = json.dumps(workflow_json_value(structure), sort_keys=True, separators=(",", ":"))
        definition_id = f"wfdef_{sha256(canonical.encode('utf-8')).hexdigest()}"
        record = WorkflowDefinitionRecord(definition_id, self.graph._name, self.graph._version, structure, state_schema_id=self.graph._state_schema.fingerprint_id)
        return _CompiledGraph(
            self.graph._name,
            self.graph._version,
            definition_id,
            record,
            self.graph._state_schema,
            MappingProxyType(dict(self.graph._stages)),
            self.graph._entry or "",
            MappingProxyType(dict(self.graph._terminals)),
            MappingProxyType(self._snapshot_routes()),
            MappingProxyType(dict(self.graph._command_routes)),
            tuple(self.graph._detours),
            MappingProxyType(dict(self.graph._subgraphs)),
            self.settings,
        )

    def _validate_required_nodes(self) -> None:
        # Requires an entry, terminal, and some outbound authority from every stage.
        if not self.graph._stages:
            raise WorkflowDefinitionError("StateGraph requires at least one stage before compile().", details={"graph": self.graph._name})
        if self.graph._entry not in self.graph._stages:
            raise WorkflowDefinitionError("StateGraph entry must name a declared stage.", details={"graph": self.graph._name, "entry": self.graph._entry})
        if not self.graph._terminals:
            raise WorkflowDefinitionError("StateGraph requires at least one terminal before compile().", details={"graph": self.graph._name})
        outcome_sources = {source for source, _ in self.graph._routes}
        command_sources = {source for source, _ in self.graph._command_routes}
        detour_return_sources = {detour.target for detour in self.graph._detours}
        missing = sorted(set(self.graph._stages) - outcome_sources - command_sources - detour_return_sources)
        if missing:
            raise WorkflowDefinitionError("Every stage requires at least one outcome or command edge.", details={"graph": self.graph._name, "stages": missing})

    def _validate_state_dependencies(self) -> None:
        # Checks stage and child read/write declarations against compiled channels.
        channels = set(self.graph._state_schema.channels)
        for stage, definition in self.graph._stages.items():
            unknown = (set(definition.reads) | set(definition.writes)) - channels
            if unknown:
                raise WorkflowDefinitionError("Stage references unknown state channels.", details={"stage": stage, "unknown_channels": sorted(unknown), "known_channels": sorted(channels)})
        for name, binding in self.graph._subgraphs.items():
            unknown = set(binding.writes) - channels
            if unknown:
                raise WorkflowDefinitionError("Subgraph writes unknown parent channels.", details={"subgraph": name, "unknown_channels": sorted(unknown)})
            immediate = {channel for channel in binding.writes if self.graph._state_schema.channels[channel].commit_mode is StateCommitMode.IMMEDIATE}
            if immediate:
                raise WorkflowDefinitionError("Subgraph summaries may write only transition-bound channels.", details={"subgraph": name, "immediate_channels": sorted(immediate)})

    def _validate_routes(self) -> None:
        # Rejects unknown sources/targets across every edge family and detour entry.
        stages = set(self.graph._stages)
        targets = stages | set(self.graph._terminals)
        for (source, outcome), route in self.graph._routes.items():
            if source not in stages:
                raise WorkflowDefinitionError("Outcome route source must be a declared stage.", details={"source": source, "outcome": outcome})
            for target in _route_targets(route):
                if target not in targets:
                    raise WorkflowDefinitionError("Outcome route target must be a declared stage or terminal.", details={"source": source, "outcome": outcome, "target": target})
        for (source, target), route in self.graph._command_routes.items():
            if source not in stages or target not in targets or route.target != target:
                raise WorkflowDefinitionError("Command edge must connect a declared source to a declared target.", details={"source": source, "target": target})
        for detour in self.graph._detours:
            if detour.target not in stages:
                raise WorkflowDefinitionError("Detour target must be a declared executable stage.", details={"rule_id": detour.rule.rule_id, "target": detour.target})

    def _validate_profiles(self) -> None:
        # Rejects execution policy on opaque stages that cannot enforce agent boundaries.
        for stage_name, definition in self.graph._stages.items():
            if definition.capabilities is None and definition.model_route is None:
                continue
            support = getattr(definition.stage, "supports_execution_policy", False)
            supported = support() if callable(support) else bool(support)
            if not supported:
                raise WorkflowDefinitionError("Capabilities/model routing require a policy-aware stage adapter.", details={"stage": stage_name, "stage_type": type(definition.stage).__name__})

    def _validate_recovery_routes(self) -> None:
        # Requires declared recovery outcomes for errors, approval rejection, and detours.
        for stage_name, definition in self.graph._stages.items():
            if definition.policy.error_outcome and (stage_name, definition.policy.error_outcome) not in self.graph._routes:
                raise WorkflowDefinitionError("StagePolicy.error_outcome requires a declared route.", details={"stage": stage_name, "outcome": definition.policy.error_outcome})
        for (source, _), route in [*self.graph._routes.items(), *self.graph._command_routes.items()]:
            direct_routes = (route,) if isinstance(route, _DirectRoute) else tuple(route.routes.values())
            for direct in direct_routes:
                if direct.approval is not None and (source, direct.approval.rejection_outcome) not in self.graph._routes:
                    raise WorkflowDefinitionError("Approval rejection requires a declared semantic recovery route.", details={"source": source, "outcome": direct.approval.rejection_outcome})
                if direct.risk > RiskLevel.LOW and direct.approval is None:
                    raise WorkflowDefinitionError("Risky transitions require ApprovalGate to declare rejection behavior.", details={"source": source, "target": direct.target, "risk": direct.risk.name})
        for detour in self.graph._detours:
            if detour.rejection_outcome is not None:
                missing = [stage for stage in self.graph._stages if (stage, detour.rejection_outcome) not in self.graph._routes]
                if len(missing) == len(self.graph._stages):
                    raise WorkflowDefinitionError("Detour rejection outcome must be declared from at least one source stage.", details={"rule_id": detour.rule.rule_id, "outcome": detour.rejection_outcome})

    def _validate_reachability(self) -> None:
        # Traverses ordinary, command, and detour edges while preserving legal cycles.
        adjacency: dict[str, list[str]] = {}
        for (source, _), route in self.graph._routes.items():
            adjacency.setdefault(source, []).extend(_route_targets(route))
        for (source, target) in self.graph._command_routes:
            adjacency.setdefault(source, []).append(target)
        for source in self.graph._stages:
            adjacency.setdefault(source, []).extend(detour.target for detour in self.graph._detours)
        reachable: set[str] = set()
        pending: deque[str] = deque([self.graph._entry or ""])
        while pending:
            node = pending.popleft()
            if node in reachable:
                continue
            reachable.add(node)
            pending.extend(target for target in adjacency.get(node, ()) if target not in reachable)
        unreachable = sorted(set(self.graph._stages) - reachable)
        if unreachable:
            raise WorkflowDefinitionError("Every declared stage must be reachable from the entry stage.", details={"stages": unreachable})
        if not (set(self.graph._terminals) & reachable):
            raise WorkflowDefinitionError("At least one terminal must be statically reachable.", details={"entry": self.graph._entry})

    def _snapshot_routes(self) -> dict[tuple[str, str], _DirectRoute[StateT] | _BranchRoute[StateT]]:
        # Copies nested branch maps so later builder mutation cannot affect execution.
        return {key: (_BranchRoute(route.router, MappingProxyType(dict(route.routes))) if isinstance(route, _BranchRoute) else route) for key, route in self.graph._routes.items()}

    def _definition_structure(self) -> dict[str, Any]:
        # Produces canonical behavior identity without serializing live executable objects.
        budget = self.settings.budget
        stages = []
        for name, item in sorted(self.graph._stages.items()):
            capabilities = None
            if item.capabilities is not None:
                capabilities = {
                    "tools": {"mode": item.capabilities.tools.mode.value, "names": list(item.capabilities.tools.names)},
                    "action_guards": [_component_fingerprint(guard) for guard in item.capabilities.action_policy.guards],
                }
            model_profile = item.model_route
            model_route = None if model_profile is None else {
                "provider": model_profile.provider,
                "model_name": model_profile.model_name,
                "temperature": model_profile.temperature,
                "runner_options": _safe_runner_options(model_profile.runner_options),
                "max_iterations": model_profile.max_iterations,
                "loop_settings": _component_config(model_profile.loop_settings),
                "model_retry": _component_config(model_profile.model_retry),
                "middleware_factories": [_component_name(factory) for factory in model_profile.middleware_factories],
            }
            stages.append({"name": name, "component": _component_name(item.stage), "validators": [_component_fingerprint(value) for value in item.validators], "policy": _component_config(item.policy), "reads": sorted(item.reads), "writes": sorted(item.writes), "capabilities": capabilities, "model_route": model_route})
        routes = []
        for (source, outcome), compiled_route in sorted(self.graph._routes.items()):
            if isinstance(compiled_route, _DirectRoute):
                routes.append({"source": source, "outcome": outcome, "kind": "direct", **_route_fingerprint(compiled_route)})
            else:
                routes.append({"source": source, "outcome": outcome, "kind": "branch", "router": _component_fingerprint(compiled_route.router), "routes": {key: _route_fingerprint(value) for key, value in sorted(compiled_route.routes.items())}})
        commands = [{"source": source, "target": target, **_route_fingerprint(route)} for (source, target), route in sorted(self.graph._command_routes.items())]
        detours = [{"rule_id": item.rule.rule_id, "matcher": dict(item.rule.matcher.fingerprint()), "target": item.target, "return_mode": item.return_mode.value, "rejection_outcome": item.rejection_outcome} for item in self.graph._detours]
        subgraphs = [{"name": name, "definition_id": binding.machine.definition_id, "writes": sorted(binding.writes), "budget": _component_config(binding.budget), "failure_policy": binding.failure_policy.value} for name, binding in sorted(self.graph._subgraphs.items())]
        return {
            "name": self.graph._name,
            "version": self.graph._version,
            "state_schema": dict(self.graph._state_schema.fingerprint()),
            "entry": self.graph._entry,
            "terminals": {name: status.value for name, status in sorted(self.graph._terminals.items())},
            "stages": stages,
            "routes": routes,
            "command_routes": commands,
            "detours": detours,
            "subgraphs": subgraphs,
            "settings": {
                "budget": {name: getattr(budget, name).value if hasattr(getattr(budget, name), "value") else getattr(budget, name) for name in ("max_super_steps", "max_transitions", "max_model_calls", "max_tool_calls", "max_tokens", "max_cost_usd", "timeout_seconds", "max_subgraph_concurrency", "max_recursion_depth", "max_detour_depth", "unknown_cost_policy")},
                "validator_error_policy": self.settings.validator_error_policy.value,
                "validation_error_outcome": self.settings.validation_error_outcome,
                "record_state_snapshots": self.settings.record_state_snapshots,
            },
        }


def _direct_route(target: str, guards: Sequence[Validator[StateT]], approval: ApprovalGate | None, risk: RiskLevel, *, owner: str) -> _DirectRoute[StateT]:
    # Normalizes one route's guards and approval/risk policy.
    if approval is not None and not isinstance(approval, ApprovalGate):
        raise WorkflowDefinitionError("Transition approval must be ApprovalGate when provided.", details={"owner": owner})
    try:
        resolved_risk = risk if isinstance(risk, RiskLevel) else RiskLevel(risk)
    except (TypeError, ValueError) as exc:
        raise WorkflowDefinitionError("Transition risk is invalid.", details={"owner": owner, "risk": str(risk)}) from exc
    return _DirectRoute(_required_text(target, "transition target"), _validated_guards(guards, owner=owner), approval, resolved_risk)


def _validated_guards(validators: Sequence[Validator[StateT]], *, owner: str) -> tuple[Validator[StateT], ...]:
    # Freezes ordered gates and verifies their structural validation boundary.
    resolved = tuple(validators)
    for validator in resolved:
        if not callable(getattr(validator, "validate", None)):
            raise WorkflowDefinitionError("Workflow validators must provide validate(context).", details={"owner": owner, "actual_type": type(validator).__name__})
    return resolved


def _route_targets(route: _DirectRoute[Any] | _BranchRoute[Any]) -> tuple[str, ...]:
    # Returns every statically possible destination for validation/reachability.
    return (route.target,) if isinstance(route, _DirectRoute) else tuple(value.target for value in route.routes.values())


def _route_fingerprint(route: _DirectRoute[Any]) -> dict[str, Any]:
    # Converts one edge's stable behavior into canonical identity data.
    return {"target": route.target, "guards": [_component_fingerprint(value) for value in route.guards], "approval": _component_config(route.approval), "risk": route.risk.name}


def _component_name(value: Any) -> str:
    # Derives a stable explicit/class identity without serializing live object reprs.
    if value is None:
        return ""
    explicit = getattr(value, "name", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    module = getattr(value, "__module__", value.__class__.__module__)
    qualified = getattr(value, "__qualname__", value.__class__.__qualname__)
    return f"{module}.{qualified}"


def _component_config(value: Any) -> Any:
    # Extracts dataclass/slot configuration through declared fields only.
    if value is None:
        return None
    fields = getattr(value, "__dataclass_fields__", {})
    if fields:
        result: dict[str, Any] = {}
        for name in fields:
            item = getattr(value, name)
            result[name] = _stable_value(item)
        return result
    return {"component": _component_name(value)}


def _component_fingerprint(value: Any) -> Any:
    # Prefers explicit stable identity over executable inspection when provided.
    declared = getattr(value, "definition_fingerprint", None)
    if callable(declared):
        declared = declared()
    if isinstance(declared, Mapping):
        return _stable_value(declared)
    return {"component": _component_name(value)}


def _stable_value(value: Any) -> Any:
    # Recursively converts declared component configuration without object reprs.
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, type) or callable(value):
        return _component_name(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _stable_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_stable_value(item) for item in value]
    if getattr(value, "__dataclass_fields__", None):
        return _component_config(value)
    return {"component": _component_name(value)}


def _safe_runner_options(value: Mapping[str, Any]) -> dict[str, Any]:
    # Fingerprints behavioral options while excluding credential-like values entirely.
    sensitive_terms = ("api_key", "apikey", "token", "secret", "password", "credential", "authorization")
    return {str(key): _stable_value(item) for key, item in value.items() if not any(term in str(key).casefold() for term in sensitive_terms)}


def _normalized_names(values: Collection[str], field_name: str) -> frozenset[str]:
    # Normalizes a declared channel set and rejects accidental scalar strings.
    if isinstance(values, str):
        raise WorkflowDefinitionError(f"{field_name}s must be a collection, not one string.", details={"value": values})
    try:
        return frozenset(_required_text(value, field_name) for value in values)
    except TypeError as exc:
        raise WorkflowDefinitionError(f"{field_name}s must be a collection of strings.", details={"actual_type": type(values).__name__}) from exc


def _required_text(value: str, field_name: str) -> str:
    # Normalizes required graph identifiers with field-specific diagnostics.
    if not isinstance(value, str):
        raise WorkflowDefinitionError(f"Workflow {field_name} must be a string.", details={"field": field_name, "actual_type": type(value).__name__})
    text = value.strip()
    if not text:
        raise WorkflowDefinitionError(f"Workflow {field_name} cannot be empty.", details={"field": field_name})
    return text


def _optional_text(value: str | None, field_name: str) -> str | None:
    # Normalizes optional graph identifiers without inventing versions/outcomes.
    if value is None:
        return None
    return _required_text(value, field_name)


__all__ = ["StateGraph"]
