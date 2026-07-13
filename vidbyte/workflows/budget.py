"""FILE: vidbyte/workflows/budget.py
PURPOSE: Owns deterministic workflow usage aggregation and layered resource ceilings.
ROLE IN CODEBASE: Used by machine.py and subgraphs.py; it never selects routes or invokes agents.

ARCHITECTURE NOTE:
    BudgetLedger is the imperative accounting shell around immutable public records.
    Counters are charged before the boundary they protect. Child graphs receive an
    explicit slice and still charge usage to the root ledger owned by machine.py.

PUBLIC API INVENTORY:
    UsageReport: Additive model/tool/token/cost evidence with honest unknown values.
    WorkflowBudget: Root or child limits for steps, calls, economics, and depth.
    ChildBudgetPolicy: Rules for deriving a bounded child slice.
    CostModel / StaticCostModel: Optional deterministic token-price calculation.
    BudgetSnapshot / BudgetLedger: Persistable counters and runtime enforcement.

COMMON MODIFICATION PATTERNS:
    Add a ceiling to WorkflowBudget, persist its counter in BudgetSnapshot, charge it
    at the owning runtime boundary, and include it in graph definition fingerprints.

WHAT NOT TO DO IN THIS FILE:
    1. Do not infer token or dollar usage from text length.
    2. Do not treat unknown usage as zero under a hard ceiling.
    3. Do not choose recovery routes; machine.py owns control flow.

KNOWN EDGE CASES:
    Provider replies may omit tokens or cost. Unknown components stay unknown; a hard
    cost ceiling fails closed unless the caller explicitly configures fail-open.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke exercises every counter boundary.

CONCURRENCY MODEL:
    One BudgetLedger belongs to one run task. Concurrent child reservations are made
    by the parent runtime before tasks launch, so this class needs no internal lock.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from time import monotonic
from typing import Protocol, runtime_checkable

from .errors import WorkflowBudgetError


class UnknownCostPolicy(str, Enum):
    """Policy applied when a hard dollar ceiling sees unpriceable usage."""

    FAIL_CLOSED = "fail_closed"
    FAIL_OPEN = "fail_open"


@dataclass(frozen=True, slots=True)
class UsageReport:
    """Monotonic usage reported by one stage, validator, child, or whole run."""

    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        # Rejects negative or non-finite usage before it can weaken a budget.
        for name in ("model_calls", "tool_calls"):
            _require_non_negative_int(getattr(self, name), f"UsageReport.{name}")
        for name in ("input_tokens", "output_tokens", "total_tokens"):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative_int(value, f"UsageReport.{name}")
        if self.cost_usd is not None:
            _require_non_negative_number(self.cost_usd, "UsageReport.cost_usd")
            object.__setattr__(self, "cost_usd", float(self.cost_usd))
        object.__setattr__(self, "provider", _optional_text(self.provider))
        object.__setattr__(self, "model", _optional_text(self.model))

    def combined_with(self, other: "UsageReport") -> "UsageReport":
        # Adds monotonic counts while keeping mixed or missing dimensions unknown.
        return UsageReport(
            model_calls=self.model_calls + other.model_calls,
            tool_calls=self.tool_calls + other.tool_calls,
            input_tokens=_sum_optional_int(self.input_tokens, other.input_tokens),
            output_tokens=_sum_optional_int(self.output_tokens, other.output_tokens),
            total_tokens=_sum_optional_int(self.total_tokens, other.total_tokens),
            cost_usd=_sum_optional_float(self.cost_usd, other.cost_usd),
            provider=_same_optional(self.provider, other.provider),
            model=_same_optional(self.model, other.model),
        )

    @classmethod
    def zero(cls) -> "UsageReport":
        # Creates a known-zero accumulator that can absorb known usage precisely.
        return cls(input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0)


@dataclass(frozen=True, slots=True)
class WorkflowBudget:
    """Global or child ceilings enforced across every workflow execution layer."""

    max_super_steps: int = 100
    max_transitions: int = 100
    max_model_calls: int | None = None
    max_tool_calls: int | None = None
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    timeout_seconds: float | None = None
    max_subgraph_concurrency: int = 8
    max_recursion_depth: int = 8
    max_detour_depth: int = 4
    unknown_cost_policy: UnknownCostPolicy = UnknownCostPolicy.FAIL_CLOSED

    def __post_init__(self) -> None:
        # Validates every ceiling once so execution checks remain branch-light.
        for name in ("max_super_steps", "max_transitions", "max_subgraph_concurrency", "max_recursion_depth", "max_detour_depth"):
            _require_positive_int(getattr(self, name), f"WorkflowBudget.{name}")
        for name in ("max_model_calls", "max_tool_calls", "max_tokens"):
            value = getattr(self, name)
            if value is not None:
                _require_positive_int(value, f"WorkflowBudget.{name}")
        for name in ("max_cost_usd", "timeout_seconds"):
            value = getattr(self, name)
            if value is not None:
                _require_positive_number(value, f"WorkflowBudget.{name}")
                object.__setattr__(self, name, float(value))
        policy = self.unknown_cost_policy if isinstance(self.unknown_cost_policy, UnknownCostPolicy) else UnknownCostPolicy(self.unknown_cost_policy)
        object.__setattr__(self, "unknown_cost_policy", policy)


@dataclass(frozen=True, slots=True)
class ChildBudgetPolicy:
    """Optional overrides used to derive a child budget from parent remaining limits."""

    budget: WorkflowBudget | None = None
    fraction: float | None = None

    def __post_init__(self) -> None:
        # Keeps proportional child reservations bounded and deterministic.
        if self.fraction is not None:
            if not isinstance(self.fraction, (int, float)) or isinstance(self.fraction, bool) or not isfinite(self.fraction) or not 0 < self.fraction <= 1:
                raise ValueError("ChildBudgetPolicy.fraction must be in (0, 1].")
            object.__setattr__(self, "fraction", float(self.fraction))


@runtime_checkable
class CostModel(Protocol):
    """Deterministically prices token usage for a provider/model pair."""

    def estimate(self, usage: UsageReport) -> float | None:
        # Returns estimated dollars, or None when the report cannot be priced.
        ...


@dataclass(frozen=True, slots=True)
class StaticCostModel:
    """Prices token reports from caller-owned per-million-token rates."""

    prices: Mapping[tuple[str, str], tuple[float, float]] = field(default_factory=dict)

    def estimate(self, usage: UsageReport) -> float | None:
        # Computes cost only when provider, model, tokens, and rates are all known.
        if usage.provider is None or usage.model is None or usage.input_tokens is None or usage.output_tokens is None:
            return None
        rates = self.prices.get((usage.provider, usage.model))
        if rates is None:
            return None
        input_rate, output_rate = rates
        return (usage.input_tokens * input_rate + usage.output_tokens * output_rate) / 1_000_000


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Persistable resource counters for checkpoint and replay projection."""

    super_steps: int = 0
    transitions: int = 0
    stage_visits: Mapping[str, int] = field(default_factory=dict)
    detour_depth: int = 0
    recursion_depth: int = 0
    usage: UsageReport = field(default_factory=UsageReport.zero)


class BudgetLedger:
    """Charges resource boundaries and raises before a configured ceiling is crossed."""

    def __init__(self, budget: WorkflowBudget, *, cost_model: CostModel | None = None, snapshot: BudgetSnapshot | None = None) -> None:
        # Restores counters from a checkpoint or starts one isolated run ledger.
        self.budget = budget
        self.cost_model = cost_model
        self._started = monotonic()
        restored = snapshot or BudgetSnapshot()
        self.super_steps = restored.super_steps
        self.transitions = restored.transitions
        self.stage_visits = dict(restored.stage_visits)
        self.detour_depth = restored.detour_depth
        self.recursion_depth = restored.recursion_depth
        self.usage = restored.usage

    def consume_super_step(self, stage: str) -> int:
        # Charges one stage entry after checking time and per-run step bounds.
        self.check_timeout()
        self.super_steps += 1
        self._assert_limit("super_steps", self.super_steps, self.budget.max_super_steps)
        self.stage_visits[stage] = self.stage_visits.get(stage, 0) + 1
        return self.super_steps

    def assert_stage_visits(self, stage: str, limit: int | None) -> None:
        # Enforces one stage's cap across retries, cycles, detours, and resume.
        if limit is not None:
            self._assert_limit(f"stage_visits:{stage}", self.stage_visits.get(stage, 0), limit)

    def consume_transition(self) -> int:
        # Charges every selected transition, including recovery and detour edges.
        self.transitions += 1
        self._assert_limit("transitions", self.transitions, self.budget.max_transitions)
        return self.transitions

    def add_usage(self, usage: UsageReport) -> UsageReport:
        # Aggregates one component report and immediately enforces economic ceilings.
        priced = self._price_usage(usage)
        self.usage = priced if _is_zero_usage(self.usage) else self.usage.combined_with(priced)
        self._assert_optional_limit("model_calls", self.usage.model_calls, self.budget.max_model_calls)
        self._assert_optional_limit("tool_calls", self.usage.tool_calls, self.budget.max_tool_calls)
        self._assert_unknown_or_limit("tokens", self.usage.total_tokens, self.budget.max_tokens)
        self._assert_cost()
        return self.usage

    def enter_detour(self) -> int:
        # Charges one nested detour before control leaves the interrupted path.
        self.detour_depth += 1
        self._assert_limit("detour_depth", self.detour_depth, self.budget.max_detour_depth)
        return self.detour_depth

    def leave_detour(self) -> int:
        # Releases one detour frame after validating stack balance.
        if self.detour_depth <= 0:
            raise WorkflowBudgetError("Cannot leave a detour when the budget stack is empty.", details={"counter": "detour_depth"})
        self.detour_depth -= 1
        return self.detour_depth

    def check_timeout(self) -> None:
        # Fails before new work when elapsed time has crossed the run ceiling.
        if self.budget.timeout_seconds is not None:
            self._assert_limit("elapsed_seconds", monotonic() - self._started, self.budget.timeout_seconds)

    def snapshot(self) -> BudgetSnapshot:
        # Returns immutable counters suitable for checkpoint serialization.
        return BudgetSnapshot(self.super_steps, self.transitions, dict(self.stage_visits), self.detour_depth, self.recursion_depth, self.usage)

    def _price_usage(self, usage: UsageReport) -> UsageReport:
        # Fills missing cost only through the caller-provided deterministic model.
        if usage.cost_usd is not None or self.cost_model is None:
            return usage
        estimate = self.cost_model.estimate(usage)
        if estimate is None:
            return usage
        return UsageReport(usage.model_calls, usage.tool_calls, usage.input_tokens, usage.output_tokens, usage.total_tokens, estimate, usage.provider, usage.model)

    def _assert_cost(self) -> None:
        # Applies fail-closed unknown-cost semantics only when a hard ceiling exists.
        limit = self.budget.max_cost_usd
        if limit is None:
            return
        if self.usage.cost_usd is None:
            if self.budget.unknown_cost_policy is UnknownCostPolicy.FAIL_CLOSED:
                raise WorkflowBudgetError("Workflow cost is unknown under a hard cost ceiling.", details={"counter": "cost_usd", "limit": limit})
            return
        self._assert_limit("cost_usd", self.usage.cost_usd, limit)

    def _assert_optional_limit(self, counter: str, actual: int, limit: int | None) -> None:
        # Skips unconfigured count ceilings and enforces configured ones uniformly.
        if limit is not None:
            self._assert_limit(counter, actual, limit)

    def _assert_unknown_or_limit(self, counter: str, actual: int | None, limit: int | None) -> None:
        # Rejects unknown token use when a corresponding hard token ceiling exists.
        if limit is None:
            return
        if actual is None:
            raise WorkflowBudgetError(f"Workflow {counter} usage is unknown under a hard ceiling.", details={"counter": counter, "limit": limit})
        self._assert_limit(counter, actual, limit)

    @staticmethod
    def _assert_limit(counter: str, actual: float, limit: float) -> None:
        # Raises one structured error only after a counter strictly exceeds its ceiling.
        if actual > limit:
            raise WorkflowBudgetError(f"Workflow {counter} budget exceeded: {actual} > {limit}.", details={"counter": counter, "actual": actual, "limit": limit})


def _sum_optional_int(left: int | None, right: int | None) -> int | None:
    # Adds known integer dimensions and preserves uncertainty on either side.
    return None if left is None or right is None else left + right


def _sum_optional_float(left: float | None, right: float | None) -> float | None:
    # Adds known monetary dimensions and preserves uncertainty on either side.
    return None if left is None or right is None else left + right


def _same_optional(left: str | None, right: str | None) -> str | None:
    # Keeps a provider/model label only when all accumulated usage agrees.
    return left if left is not None and left == right else None


def _is_zero_usage(value: UsageReport) -> bool:
    # Recognizes the pristine accumulator without confusing later mixed-provider None.
    return value.model_calls == 0 and value.tool_calls == 0 and value.input_tokens == 0 and value.output_tokens == 0 and value.total_tokens == 0 and value.cost_usd == 0.0 and value.provider is None and value.model is None


def _optional_text(value: str | None) -> str | None:
    # Normalizes optional provider/model labels without inventing empty identifiers.
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_non_negative_int(value: int, field_name: str) -> None:
    # Rejects booleans and negative counters with the precise public field name.
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")


def _require_positive_int(value: int, field_name: str) -> None:
    # Rejects booleans and non-positive configured integer ceilings.
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be an integer greater than zero.")


def _require_non_negative_number(value: float, field_name: str) -> None:
    # Rejects booleans, negatives, NaN, and infinity from monetary evidence.
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number.")


def _require_positive_number(value: float, field_name: str) -> None:
    # Rejects booleans, non-positive numbers, NaN, and infinity from ceilings.
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be a finite number greater than zero.")


__all__ = [
    "BudgetLedger",
    "BudgetSnapshot",
    "ChildBudgetPolicy",
    "CostModel",
    "StaticCostModel",
    "UnknownCostPolicy",
    "UsageReport",
    "WorkflowBudget",
]
