"""FILE: vidbyte/workflows/subgraphs.py
PURPOSE: Defines isolated child graph delegation, bounded Send fan-out, and ordered summaries.
ROLE IN CODEBASE: graph.py compiles bindings; machine.py invokes SubgraphExecutor and joins updates.

ARCHITECTURE NOTE:
    A child receives only explicitly mapped input and lineage metadata, owns a distinct
    run/event/checkpoint stream, and returns one bounded summary. Parent and child may
    share an external workspace, but this API does not claim filesystem isolation.

PUBLIC API INVENTORY:
    ChildFailurePolicy: Fail-fast or collect behavior for child failures.
    Send: One named child invocation and deterministic join key.
    SubgraphSummary: Bounded child outcome returned to the parent.
    SubgraphBinding: Compiled child machine, mappers, writes, and budget policy.
    SubgraphExecutor: Concurrent isolated execution with input-order result assembly.

COMMON MODIFICATION PATTERNS:
    Add child metadata through Send/summary fields, not by exposing parent event history
    or child event streams to the opposite graph.

WHAT NOT TO DO IN THIS FILE:
    1. Do not share mutable parent state with child callbacks.
    2. Do not merge results in completion order.
    3. Do not imply cancellation rolls back child external effects.

KNOWN EDGE CASES:
    A child may suspend for approval or interrupt. Its summary retains the child run ID
    so the parent can suspend and resume that child before completing the join.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke uses delayed children to prove order.

CONCURRENCY MODEL:
    asyncio.Semaphore bounds active children. asyncio.gather returns results in input order;
    each child and store adapter owns its own internal synchronization.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from .budget import BudgetSnapshot, ChildBudgetPolicy, UnknownCostPolicy, UsageReport, WorkflowBudget
from .errors import WorkflowError, WorkflowErrorRecord, WorkflowSubgraphError


class ChildFailurePolicy(str, Enum):
    """Parent behavior when one child invocation raises or ends in lifecycle ERROR."""

    FAIL_FAST = "fail_fast"
    COLLECT = "collect"


@dataclass(frozen=True, slots=True)
class Send:
    """One isolated invocation of a named child graph."""

    subgraph: str
    input: Any
    key: str
    budget: WorkflowBudget | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes lookup/join identities and protects lineage metadata.
        object.__setattr__(self, "subgraph", _required_text(self.subgraph, "Send.subgraph"))
        object.__setattr__(self, "key", _required_text(self.key, "Send.key"))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class SubgraphSummary:
    """Bounded child result retained by the parent without importing child events."""

    key: str
    child_run_id: str
    lifecycle: Any
    terminal: str | None
    update: Mapping[str, Any]
    usage: UsageReport
    error: WorkflowErrorRecord | None = None
    pending: Any | None = None
    effective_budget: WorkflowBudget | None = None

    def __post_init__(self) -> None:
        # Freezes join updates and validates stable child identity.
        object.__setattr__(self, "key", _required_text(self.key, "SubgraphSummary.key"))
        object.__setattr__(self, "child_run_id", _required_text(self.child_run_id, "SubgraphSummary.child_run_id"))
        object.__setattr__(self, "update", MappingProxyType(deepcopy(dict(self.update))))


@dataclass(frozen=True, slots=True)
class SubgraphBinding:
    """Compiled child machine and explicit parent/child state mapping boundary."""

    name: str
    machine: Any
    input_mapper: Callable[[Any, Send], Any]
    summary_mapper: Callable[[Any, Send], Mapping[str, Any]]
    writes: frozenset[str]
    budget: ChildBudgetPolicy = field(default_factory=ChildBudgetPolicy)
    failure_policy: ChildFailurePolicy = ChildFailurePolicy.FAIL_FAST

    def __post_init__(self) -> None:
        # Validates mapping callables and immutable write/failure declarations.
        object.__setattr__(self, "name", _required_text(self.name, "SubgraphBinding.name"))
        if not callable(self.input_mapper) or not callable(self.summary_mapper):
            raise TypeError("SubgraphBinding input_mapper and summary_mapper must be callable.")
        object.__setattr__(self, "writes", frozenset(self.writes))
        policy = self.failure_policy if isinstance(self.failure_policy, ChildFailurePolicy) else ChildFailurePolicy(self.failure_policy)
        object.__setattr__(self, "failure_policy", policy)


class SubgraphExecutor:
    """Runs isolated child machines concurrently and returns input-ordered summaries."""

    def __init__(self, bindings: Mapping[str, SubgraphBinding], *, max_concurrency: int) -> None:
        # Freezes compiled bindings and creates the per-execution concurrency bound.
        if max_concurrency <= 0:
            raise ValueError("SubgraphExecutor.max_concurrency must be positive.")
        self.bindings = MappingProxyType(dict(bindings))
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def execute(self, sends: Sequence[Send], *, parent_state: Any, parent_run_id: str, invocation_id: str, metadata: Mapping[str, Any], store: Any, parent_budget: WorkflowBudget | None = None, parent_snapshot: BudgetSnapshot | None = None) -> tuple[SubgraphSummary, ...]:
        # Validates the batch, launches isolated children, and assembles input-order results.
        self._validate_sends(sends)
        reservations = _reserved_child_budgets(sends, self.bindings, parent_budget, parent_snapshot)
        tasks = [asyncio.create_task(self._execute_one(send, parent_state=parent_state, parent_run_id=parent_run_id, invocation_id=invocation_id, metadata=metadata, store=store, parent_budget=parent_budget, effective_budget=reservations[index])) for index, send in enumerate(sends)]
        indexes = {task: index for index, task in enumerate(tasks)}
        outcomes: list[SubgraphSummary | BaseException | None] = [None] * len(tasks)
        pending = set(tasks)
        try:
            while pending:
                completed, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in completed:
                    index = indexes[task]
                    try:
                        outcomes[index] = task.result()
                    except asyncio.CancelledError:
                        raise
                    except BaseException as exc:
                        outcomes[index] = exc
                        binding = self.bindings[sends[index].subgraph]
                        if binding.failure_policy is ChildFailurePolicy.FAIL_FAST:
                            for other in pending:
                                other.cancel()
                            await asyncio.gather(*pending, return_exceptions=True)
                            raise WorkflowSubgraphError("Child subgraph failed under fail-fast policy.", details={"subgraph": sends[index].subgraph, "key": sends[index].key, "cause_type": type(exc).__name__, "cause": str(exc)[:1000]}) from exc
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return self._normalize_outcomes(sends, tuple(item for item in outcomes if item is not None))

    async def _execute_one(self, send: Send, *, parent_state: Any, parent_run_id: str, invocation_id: str, metadata: Mapping[str, Any], store: Any, parent_budget: WorkflowBudget | None, effective_budget: WorkflowBudget) -> SubgraphSummary:
        # Starts or resumes one deterministic child lineage under the shared semaphore.
        binding = self.bindings[send.subgraph]
        async with self.semaphore:
            child_run_id = _planned_child_run_id(parent_run_id, invocation_id, send)
            child_state = binding.input_mapper(deepcopy(parent_state), send)
            recursion_depth = int(metadata.get("workflow_recursion_depth", 0) or 0) + 1
            if parent_budget is not None and recursion_depth > parent_budget.max_recursion_depth:
                raise WorkflowSubgraphError("Child subgraph recursion depth exceeded.", details={"subgraph": send.subgraph, "key": send.key, "recursion_depth": recursion_depth, "max_recursion_depth": parent_budget.max_recursion_depth})
            lineage = {**dict(metadata), **dict(send.metadata), "parent_run_id": parent_run_id, "parent_invocation_id": invocation_id, "send_key": send.key, "subgraph": send.subgraph, "workflow_recursion_depth": recursion_depth}
            machine = binding.machine._with_budget(effective_budget)
            existing = await store.events(child_run_id, through_sequence=1)
            try:
                if not existing:
                    result = await machine.arun(child_state, run_id=child_run_id, metadata=lineage, store=store)
                else:
                    result = await machine.inspect(child_run_id, store=store)
                    if getattr(result.lifecycle, "value", result.lifecycle) == "running":
                        result = await machine.aresume(child_run_id, store=store)
            except WorkflowError as exc:
                if binding.failure_policy is not ChildFailurePolicy.COLLECT or not hasattr(exc, "result"):
                    raise
                result = exc.result
            if getattr(result.lifecycle, "value", result.lifecycle) != "finished":
                return SubgraphSummary(send.key, child_run_id, result.lifecycle, result.terminal, {}, result.usage, result.error, result.pending, effective_budget)
            update = binding.summary_mapper(result, send)
            if not isinstance(update, Mapping):
                raise WorkflowSubgraphError("Subgraph summary mapper must return a mapping.", details={"subgraph": send.subgraph, "key": send.key, "actual_type": type(update).__name__})
            undeclared = set(update) - set(binding.writes)
            if undeclared:
                raise WorkflowSubgraphError("Subgraph summary mapper wrote undeclared parent channels.", details={"subgraph": send.subgraph, "key": send.key, "undeclared": sorted(undeclared), "allowed": sorted(binding.writes)})
            return SubgraphSummary(send.key, child_run_id, result.lifecycle, result.terminal, update, result.usage, result.error, result.pending, effective_budget)

    def _validate_sends(self, sends: Sequence[Send]) -> None:
        # Rejects unknown subgraphs and duplicate join keys before launching any child.
        keys: set[str] = set()
        for send in sends:
            if not isinstance(send, Send):
                raise WorkflowSubgraphError("WorkflowCommand.sends must contain Send values.", details={"actual_type": type(send).__name__})
            if send.subgraph not in self.bindings:
                raise WorkflowSubgraphError("Send references an unknown compiled subgraph.", details={"subgraph": send.subgraph, "known": sorted(self.bindings)})
            if send.key in keys:
                raise WorkflowSubgraphError("Send keys must be unique within one fan-out.", details={"key": send.key})
            keys.add(send.key)

    def _normalize_outcomes(self, sends: Sequence[Send], outcomes: Sequence[SubgraphSummary | BaseException]) -> tuple[SubgraphSummary, ...]:
        # Converts collect-policy failures and raises fail-fast errors in input order.
        summaries: list[SubgraphSummary] = []
        for send, outcome in zip(sends, outcomes, strict=True):
            if not isinstance(outcome, BaseException):
                summaries.append(outcome)
                continue
            binding = self.bindings[send.subgraph]
            if binding.failure_policy is ChildFailurePolicy.FAIL_FAST:
                raise WorkflowSubgraphError("Child subgraph failed under fail-fast policy.", details={"subgraph": send.subgraph, "key": send.key, "cause_type": type(outcome).__name__, "cause": str(outcome)[:1000]}) from outcome
            summaries.append(SubgraphSummary(send.key, f"wrun_failed_{uuid4().hex}", "error", None, {}, UsageReport.zero(), WorkflowErrorRecord.from_error(outcome)))
        return tuple(summaries)


def _effective_child_budget(binding: SubgraphBinding, send: Send, parent: WorkflowBudget | None, reservation: WorkflowBudget | None = None) -> WorkflowBudget:
    # Derives the strictest compiled, explicit, and proportional child ceiling.
    child = binding.machine._definition.settings.budget
    requested = send.budget or binding.budget.budget
    effective = _stricter_budget(child, requested) if requested is not None else child
    if binding.budget.fraction is not None and parent is not None:
        effective = _stricter_budget(effective, _fractional_budget(parent, binding.budget.fraction))
    if reservation is not None:
        effective = _stricter_budget(effective, reservation)
    return effective


def _planned_child_run_id(parent_run_id: str, invocation_id: str, send: Send) -> str:
    # Derives a stable opaque run ID so crash replay cannot duplicate one Send lineage.
    material = f"{parent_run_id}\x1f{invocation_id}\x1f{send.subgraph}\x1f{send.key}".encode("utf-8")
    return f"wrun_{sha256(material).hexdigest()[:32]}"


def _reserved_child_budgets(sends: Sequence[Send], bindings: Mapping[str, SubgraphBinding], parent: WorkflowBudget | None, snapshot: BudgetSnapshot | None) -> tuple[WorkflowBudget, ...]:
    # Reserves equal deterministic slices so concurrent siblings cannot overclaim remainder.
    if parent is None or snapshot is None:
        return tuple(_effective_child_budget(bindings[send.subgraph], send, parent) for send in sends)
    reservation = _remaining_slice(parent, snapshot, len(sends))
    return tuple(_effective_child_budget(bindings[send.subgraph], send, parent, reservation) for send in sends)


def _remaining_slice(parent: WorkflowBudget, snapshot: BudgetSnapshot, count: int) -> WorkflowBudget:
    # Converts root remaining counters into one conservative per-sibling reservation.
    def integer(limit: int | None, actual: int | None, name: str) -> int | None:
        if limit is None:
            return None
        if actual is None:
            raise WorkflowSubgraphError("Cannot reserve child budget from unknown parent usage.", details={"counter": name, "limit": limit})
        remaining = limit - actual
        share = remaining // count
        if share <= 0:
            raise WorkflowSubgraphError("Parent budget cannot reserve a positive slice for every child.", details={"counter": name, "remaining": remaining, "child_count": count})
        return share

    def number(limit: float | None, actual: float | None, name: str) -> float | None:
        if limit is None:
            return None
        if actual is None:
            raise WorkflowSubgraphError("Cannot reserve child budget from unknown parent usage.", details={"counter": name, "limit": limit})
        remaining = limit - actual
        share = remaining / count
        if share <= 0:
            raise WorkflowSubgraphError("Parent budget cannot reserve a positive slice for every child.", details={"counter": name, "remaining": remaining, "child_count": count})
        return share

    usage = snapshot.usage
    return WorkflowBudget(
        max_super_steps=integer(parent.max_super_steps, snapshot.super_steps, "super_steps") or 1,
        max_transitions=integer(parent.max_transitions, snapshot.transitions, "transitions") or 1,
        max_model_calls=integer(parent.max_model_calls, usage.model_calls, "model_calls"),
        max_tool_calls=integer(parent.max_tool_calls, usage.tool_calls, "tool_calls"),
        max_tokens=integer(parent.max_tokens, usage.total_tokens, "tokens"),
        max_cost_usd=number(parent.max_cost_usd, usage.cost_usd, "cost_usd"),
        timeout_seconds=parent.timeout_seconds,
        max_subgraph_concurrency=min(parent.max_subgraph_concurrency, count),
        max_recursion_depth=parent.max_recursion_depth,
        max_detour_depth=parent.max_detour_depth,
        unknown_cost_policy=parent.unknown_cost_policy,
    )


def _fractional_budget(value: WorkflowBudget, fraction: float) -> WorkflowBudget:
    # Converts parent ceilings to a positive deterministic child slice.
    def integer(item: int | None) -> int | None:
        return None if item is None else max(1, int(item * fraction))

    def number(item: float | None) -> float | None:
        return None if item is None else item * fraction

    return WorkflowBudget(
        max_super_steps=integer(value.max_super_steps) or 1,
        max_transitions=integer(value.max_transitions) or 1,
        max_model_calls=integer(value.max_model_calls),
        max_tool_calls=integer(value.max_tool_calls),
        max_tokens=integer(value.max_tokens),
        max_cost_usd=number(value.max_cost_usd),
        timeout_seconds=number(value.timeout_seconds),
        max_subgraph_concurrency=integer(value.max_subgraph_concurrency) or 1,
        max_recursion_depth=integer(value.max_recursion_depth) or 1,
        max_detour_depth=integer(value.max_detour_depth) or 1,
        unknown_cost_policy=value.unknown_cost_policy,
    )


def _stricter_budget(left: WorkflowBudget, right: WorkflowBudget) -> WorkflowBudget:
    # Intersects two ceilings so child overrides can never widen compiled policy.
    def minimum(a: Any, b: Any) -> Any:
        if a is None:
            return b
        if b is None:
            return a
        return min(a, b)

    return WorkflowBudget(
        max_super_steps=min(left.max_super_steps, right.max_super_steps),
        max_transitions=min(left.max_transitions, right.max_transitions),
        max_model_calls=minimum(left.max_model_calls, right.max_model_calls),
        max_tool_calls=minimum(left.max_tool_calls, right.max_tool_calls),
        max_tokens=minimum(left.max_tokens, right.max_tokens),
        max_cost_usd=minimum(left.max_cost_usd, right.max_cost_usd),
        timeout_seconds=minimum(left.timeout_seconds, right.timeout_seconds),
        max_subgraph_concurrency=min(left.max_subgraph_concurrency, right.max_subgraph_concurrency),
        max_recursion_depth=min(left.max_recursion_depth, right.max_recursion_depth),
        max_detour_depth=min(left.max_detour_depth, right.max_detour_depth),
        unknown_cost_policy=UnknownCostPolicy.FAIL_CLOSED if UnknownCostPolicy.FAIL_CLOSED in (left.unknown_cost_policy, right.unknown_cost_policy) else UnknownCostPolicy.FAIL_OPEN,
    )


def _required_text(value: str, field_name: str) -> str:
    # Normalizes lookup/join identifiers and reports the precise empty field.
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty.")
    return text


__all__ = [
    "ChildFailurePolicy",
    "Send",
    "SubgraphBinding",
    "SubgraphExecutor",
    "SubgraphSummary",
]
