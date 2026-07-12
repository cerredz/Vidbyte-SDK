"""FILE: vidbyte/workflows/graph.py
PURPOSE: Builds, validates, and freezes outcome-addressed workflow graph definitions.
ROLE IN CODEBASE: Called by SDK users; produces the immutable definition consumed only by machine.py.

ARCHITECTURE NOTE:
    StateGraph is mutable declaration state. compile() performs complete static
    validation and snapshots definitions so later builder edits cannot alter a
    running StateMachine. Routes are keyed by (source, semantic outcome), making
    declaration order irrelevant and arbitrary declared jumps natural.

PUBLIC API INVENTORY:
    StateGraph(state_type, ...): Mutable typed graph builder.
    add_stage(): Declares a stage, ordered validators, and StagePolicy.
    set_entry(): Selects the sole initial stage.
    add_terminal(): Declares a named success or failure terminal.
    add_transition(): Declares one direct outcome route and ordered guards.
    add_branch(): Declares one bounded conditional branch for an outcome.
    compile(): Validates and returns an immutable StateMachine snapshot.

COMMON MODIFICATION PATTERNS:
    Add static graph invariants to _GraphCompiler. Add runtime semantics to
    machine.py. Extend branch declaration through immutable internal route
    records rather than exposing current-stage mutation on the builder.

WHAT NOT TO DO IN THIS FILE:
    1. Do not execute stages, validators, guards, routers, or observers.
    2. Do not keep current run state, counters, histories, or ledgers.
    3. Do not infer a fallback target for an undeclared outcome.
    4. Do not reject cycles; runtime transition limits bound them.

KNOWN EDGE CASES:
    Targets may be declared after routes and are validated only at compile time.
    A reachable cycle is legal when at least one terminal is statically reachable.
    Pydantic-incompatible ordinary classes use strict isinstance validation.

COMMON ERRORS:
    WorkflowDefinitionError identifies malformed declarations and reachability.
    State validation/cloning failures become WorkflowStateError in machine.py.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/validated-state-machine-workflows.md

TESTS:
    No feature-specific test file is added by the approved no-tests design.
    Inline smoke covers ambiguity, reachability, branches, cycles, and jumps.

CONCURRENCY:
    Builders are not thread-safe. Compiled definitions are immutable snapshots;
    machine.py keeps all per-run mutable state local to one arun() invocation.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Generic

from pydantic import TypeAdapter

from vidbyte.workflows.contracts import MachineStatus, RouteTarget, Router, Stage, StagePolicy, StateMachineSettings, StateT, Validator
from vidbyte.workflows.errors import WorkflowDefinitionError


@dataclass(frozen=True, slots=True)
class _StageDefinition(Generic[StateT]):
    """Immutable stage, validator, and policy declaration."""

    stage: Stage[StateT]
    validators: tuple[Validator[StateT], ...]
    policy: StagePolicy


@dataclass(frozen=True, slots=True)
class _DirectRoute(Generic[StateT]):
    """One target and its ordered transition guards."""

    target: str
    guards: tuple[Validator[StateT], ...]


@dataclass(frozen=True, slots=True)
class _BranchRoute(Generic[StateT]):
    """One bounded router and branch-key destination map."""

    router: Router[StateT]
    routes: Mapping[str, _DirectRoute[StateT]]


@dataclass(frozen=True, slots=True)
class _CompiledGraph(Generic[StateT]):
    """Immutable definition snapshot consumed by StateMachine."""

    name: str
    state_contract: _StateContract[StateT]
    stages: Mapping[str, _StageDefinition[StateT]]
    entry: str
    terminals: Mapping[str, MachineStatus]
    routes: Mapping[tuple[str, str], _DirectRoute[StateT] | _BranchRoute[StateT]]
    settings: StateMachineSettings


class _StateContract(Generic[StateT]):
    """Normalizes and clones user-defined workflow state."""

    def __init__(self, state_type: type[StateT], validator: Callable[[Any], StateT] | None, cloner: Callable[[StateT], StateT]) -> None:
        # Compiles the preferred Pydantic adapter with an ordinary-class fallback.
        self.state_type = state_type
        self._validator = validator
        self._cloner = cloner
        self._adapter = self._build_adapter(state_type) if validator is None else None

    def validate(self, value: Any) -> StateT:
        # Normalizes one value and verifies the declared runtime state type.
        if self._validator is not None:
            resolved = self._validator(value)
        elif self._adapter is not None:
            resolved = self._adapter.validate_python(value)
        else:
            resolved = value
        if not isinstance(resolved, self.state_type):
            raise TypeError(f"Expected workflow state {self.state_type.__name__}, got {type(resolved).__name__}.")
        return resolved

    def clone(self, value: StateT) -> StateT:
        # Produces one attempt-local state value through the configured cloner.
        return self._cloner(value)

    @staticmethod
    def _build_adapter(state_type: type[StateT]) -> TypeAdapter[Any] | None:
        # Uses Pydantic where supported and falls back for arbitrary ordinary classes.
        try:
            return TypeAdapter(state_type)
        except Exception:
            return None


class StateGraph(Generic[StateT]):
    """Mutable builder for a typed, validated, non-linear workflow graph."""

    def __init__(self, state_type: type[StateT], *, name: str = "workflow", state_validator: Callable[[Any], StateT] | None = None, state_cloner: Callable[[StateT], StateT] = deepcopy) -> None:
        # Initializes an empty declaration and compiles its state boundary once.
        if not isinstance(state_type, type):
            raise WorkflowDefinitionError("StateGraph.state_type must be a runtime class.", details={"state_type": type(state_type).__name__})
        if state_validator is not None and not callable(state_validator):
            raise WorkflowDefinitionError("StateGraph.state_validator must be callable when provided.", details={"state_type": state_type.__name__})
        if not callable(state_cloner):
            raise WorkflowDefinitionError("StateGraph.state_cloner must be callable.", details={"state_type": state_type.__name__})
        self._name = _required_text(name, "graph name")
        self._state_contract = _StateContract(state_type, state_validator, state_cloner)
        self._stages: dict[str, _StageDefinition[StateT]] = {}
        self._entry: str | None = None
        self._terminals: dict[str, MachineStatus] = {}
        self._routes: dict[tuple[str, str], _DirectRoute[StateT] | _BranchRoute[StateT]] = {}

    def add_stage(self, name: str, stage: Stage[StateT], *, validators: Sequence[Validator[StateT]] = (), policy: StagePolicy | None = None) -> StateGraph[StateT]:
        # Declares one uniquely named executable stage and its ordered gates.
        stage_name = _required_text(name, "stage name")
        self._assert_name_is_available(stage_name)
        if not callable(getattr(stage, "run", None)):
            raise WorkflowDefinitionError("Workflow stage must provide a callable run(context) method.", details={"stage": stage_name, "actual_type": type(stage).__name__})
        resolved_validators = _validated_guards(validators, owner=f"stage:{stage_name}")
        resolved_policy = policy or StagePolicy()
        if not isinstance(resolved_policy, StagePolicy):
            raise WorkflowDefinitionError("StateGraph.add_stage policy must be StagePolicy.", details={"stage": stage_name, "actual_type": type(resolved_policy).__name__})
        self._stages[stage_name] = _StageDefinition(stage=stage, validators=resolved_validators, policy=resolved_policy)
        return self

    def set_entry(self, name: str) -> StateGraph[StateT]:
        # Selects the sole initial stage; existence is checked at compile time.
        self._entry = _required_text(name, "entry stage")
        return self

    def add_terminal(self, name: str, *, status: MachineStatus = MachineStatus.SUCCEEDED) -> StateGraph[StateT]:
        # Declares one named terminal and its success or failure result status.
        terminal = _required_text(name, "terminal name")
        self._assert_name_is_available(terminal)
        resolved_status = status if isinstance(status, MachineStatus) else MachineStatus(status)
        self._terminals[terminal] = resolved_status
        return self

    def add_transition(self, source: str, target: str, *, on: str = "success", guards: Sequence[Validator[StateT]] = ()) -> StateGraph[StateT]:
        # Declares one direct outcome route to any stage or terminal.
        key = self._route_key(source, on)
        self._assert_route_is_available(key)
        route = _DirectRoute(target=_required_text(target, "transition target"), guards=_validated_guards(guards, owner=f"transition:{key[0]}:{key[1]}"))
        self._routes[key] = route
        return self

    def add_branch(self, source: str, router: Router[StateT], routes: Mapping[str, str | RouteTarget[StateT]], *, on: str = "success") -> StateGraph[StateT]:
        # Declares one bounded conditional route for a source/outcome pair.
        key = self._route_key(source, on)
        self._assert_route_is_available(key)
        if not callable(getattr(router, "route", None)):
            raise WorkflowDefinitionError("Workflow router must provide a callable route(context) method.", details={"source": key[0], "outcome": key[1], "actual_type": type(router).__name__})
        normalized_routes = self._normalize_branch_routes(key, routes)
        self._routes[key] = _BranchRoute(router=router, routes=MappingProxyType(normalized_routes))
        return self

    def compile(self, *, settings: StateMachineSettings | None = None) -> StateMachine[StateT]:
        # Validates the complete declaration and returns an immutable runtime.
        from vidbyte.workflows.machine import StateMachine

        resolved_settings = settings or StateMachineSettings()
        if not isinstance(resolved_settings, StateMachineSettings):
            raise WorkflowDefinitionError("StateGraph.compile settings must be StateMachineSettings.", details={"actual_type": type(resolved_settings).__name__})
        definition = _GraphCompiler(self, resolved_settings).compile()
        return StateMachine(definition)

    def _assert_name_is_available(self, name: str) -> None:
        # Prevents stage/terminal collisions at the earliest declaration point.
        if name in self._stages or name in self._terminals:
            raise WorkflowDefinitionError("Workflow node names must be unique across stages and terminals.", details={"node": name, "graph": self._name})

    def _route_key(self, source: str, outcome: str) -> tuple[str, str]:
        # Normalizes one source/outcome pair without changing case semantics.
        return (_required_text(source, "route source"), _required_text(outcome, "route outcome"))

    def _assert_route_is_available(self, key: tuple[str, str]) -> None:
        # Rejects ambiguous direct/branch declarations for the same outcome.
        if key in self._routes:
            raise WorkflowDefinitionError("A source/outcome pair can have only one direct transition or branch.", details={"source": key[0], "outcome": key[1], "graph": self._name})

    def _normalize_branch_routes(self, key: tuple[str, str], routes: Mapping[str, str | RouteTarget[StateT]]) -> dict[str, _DirectRoute[StateT]]:
        # Converts branch declarations to immutable direct destinations.
        if not routes:
            raise WorkflowDefinitionError("StateGraph.add_branch requires at least one branch key.", details={"source": key[0], "outcome": key[1]})
        normalized: dict[str, _DirectRoute[StateT]] = {}
        for raw_branch, raw_target in routes.items():
            branch = _required_text(raw_branch, "branch key")
            if branch in normalized:
                raise WorkflowDefinitionError("Normalized branch keys must be unique.", details={"source": key[0], "outcome": key[1], "branch": branch})
            normalized[branch] = self._normalize_route_target(raw_target, key, branch)
        return normalized

    def _normalize_route_target(self, value: str | RouteTarget[StateT], key: tuple[str, str], branch: str) -> _DirectRoute[StateT]:
        # Converts a bare target or guarded RouteTarget into one internal route.
        if isinstance(value, RouteTarget):
            guards = _validated_guards(value.guards, owner=f"branch:{key[0]}:{key[1]}:{branch}")
            return _DirectRoute(target=value.target, guards=guards)
        if isinstance(value, str):
            return _DirectRoute(target=_required_text(value, "branch target"), guards=())
        raise WorkflowDefinitionError("Branch targets must be stage names or RouteTarget values.", details={"source": key[0], "outcome": key[1], "branch": branch, "actual_type": type(value).__name__})


class _GraphCompiler(Generic[StateT]):
    """Runs static graph checks and creates one immutable definition snapshot."""

    def __init__(self, graph: StateGraph[StateT], settings: StateMachineSettings) -> None:
        # Stores one builder snapshot source and already-validated settings.
        self._graph = graph
        self._settings = settings

    def compile(self) -> _CompiledGraph[StateT]:
        # Orchestrates static checks before copying every mutable declaration.
        self._validate_required_nodes()
        self._validate_routes()
        self._validate_stage_recovery_routes()
        self._validate_reachability()
        return _CompiledGraph(name=self._graph._name, state_contract=self._graph._state_contract, stages=MappingProxyType(dict(self._graph._stages)), entry=self._graph._entry or "", terminals=MappingProxyType(dict(self._graph._terminals)), routes=MappingProxyType(self._snapshot_routes()), settings=self._settings)

    def _validate_required_nodes(self) -> None:
        # Requires an entry stage, at least one terminal, and outgoing stage routes.
        if not self._graph._stages:
            raise WorkflowDefinitionError("StateGraph requires at least one stage before compile().", details={"graph": self._graph._name})
        if self._graph._entry not in self._graph._stages:
            raise WorkflowDefinitionError("StateGraph entry must name a declared stage.", details={"graph": self._graph._name, "entry": self._graph._entry})
        if not self._graph._terminals:
            raise WorkflowDefinitionError("StateGraph requires at least one terminal before compile().", details={"graph": self._graph._name})
        sources = {source for source, _ in self._graph._routes}
        missing = sorted(set(self._graph._stages) - sources)
        if missing:
            raise WorkflowDefinitionError("Every nonterminal stage requires at least one outgoing route.", details={"graph": self._graph._name, "stages": tuple(missing)})

    def _validate_routes(self) -> None:
        # Rejects unknown route sources and targets after all declarations exist.
        known_targets = set(self._graph._stages) | set(self._graph._terminals)
        for (source, outcome), route in self._graph._routes.items():
            if source not in self._graph._stages:
                raise WorkflowDefinitionError("Workflow route source must be a declared stage.", details={"graph": self._graph._name, "source": source, "outcome": outcome})
            for target in _route_targets(route):
                if target not in known_targets:
                    raise WorkflowDefinitionError("Workflow route target must be a declared stage or terminal.", details={"graph": self._graph._name, "source": source, "outcome": outcome, "target": target})

    def _validate_stage_recovery_routes(self) -> None:
        # Requires every configured stage error outcome to have one explicit route.
        for stage_name, definition in self._graph._stages.items():
            outcome = definition.policy.error_outcome
            if outcome is not None and (stage_name, outcome) not in self._graph._routes:
                raise WorkflowDefinitionError("StagePolicy.error_outcome requires a declared route from its stage.", details={"graph": self._graph._name, "stage": stage_name, "outcome": outcome})

    def _validate_reachability(self) -> None:
        # Traverses direct and branch edges while permitting cycles through a visited set.
        reachable = self._reachable_nodes(self._graph._entry or "")
        unreachable_stages = sorted(set(self._graph._stages) - reachable)
        if unreachable_stages:
            raise WorkflowDefinitionError("Every declared stage must be reachable from the entry stage.", details={"graph": self._graph._name, "stages": tuple(unreachable_stages)})
        reachable_terminals = sorted(set(self._graph._terminals) & reachable)
        if not reachable_terminals:
            raise WorkflowDefinitionError("At least one terminal must be reachable from the entry stage.", details={"graph": self._graph._name, "entry": self._graph._entry})

    def _reachable_nodes(self, entry: str) -> set[str]:
        # Computes graph reachability without treating declaration order as topology.
        adjacency: dict[str, list[str]] = {}
        for (source, _), route in self._graph._routes.items():
            adjacency.setdefault(source, []).extend(_route_targets(route))
        reachable: set[str] = set()
        pending: deque[str] = deque([entry])
        while pending:
            node = pending.popleft()
            if node in reachable:
                continue
            reachable.add(node)
            pending.extend(target for target in adjacency.get(node, ()) if target not in reachable)
        return reachable

    def _snapshot_routes(self) -> dict[tuple[str, str], _DirectRoute[StateT] | _BranchRoute[StateT]]:
        # Copies nested branch maps so builder mutation cannot affect the runtime.
        snapshot: dict[tuple[str, str], _DirectRoute[StateT] | _BranchRoute[StateT]] = {}
        for key, route in self._graph._routes.items():
            if isinstance(route, _BranchRoute):
                snapshot[key] = _BranchRoute(router=route.router, routes=MappingProxyType(dict(route.routes)))
            else:
                snapshot[key] = route
        return snapshot


def _validated_guards(validators: Sequence[Validator[StateT]], *, owner: str) -> tuple[Validator[StateT], ...]:
    # Freezes ordered gates and verifies their structural validate() boundary.
    resolved = tuple(validators)
    for validator in resolved:
        if not callable(getattr(validator, "validate", None)):
            raise WorkflowDefinitionError("Workflow validators must provide a callable validate(context) method.", details={"owner": owner, "actual_type": type(validator).__name__})
    return resolved


def _route_targets(route: _DirectRoute[StateT] | _BranchRoute[StateT]) -> tuple[str, ...]:
    # Returns every statically possible destination for reachability analysis.
    if isinstance(route, _DirectRoute):
        return (route.target,)
    return tuple(destination.target for destination in route.routes.values())


def _required_text(value: str, field_name: str) -> str:
    # Normalizes one graph identifier without changing its case semantics.
    text = value.strip()
    if not text:
        raise WorkflowDefinitionError(f"Workflow {field_name} cannot be empty.", details={"field": field_name})
    return text


__all__ = ["StateGraph"]
