from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class CandidateResult:
    """Successful candidate output from one strategy."""

    index: int
    strategy_name: str
    output: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CandidateFailure:
    """Failed candidate execution summary."""

    index: int
    strategy_name: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class EvaluationDecision:
    """Evaluator decision selecting the best candidate output."""

    selected_index: int
    final_output: str
    grades: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class DagNode:
    """A node in a verified multi-agent orchestration DAG."""

    id: str
    question: str
    depends_on: tuple[str, ...] = ()
    preferred_capability: str | None = None


@dataclass(frozen=True, slots=True)
class Verification:
    """Verifier decision for a synthesized multi-agent answer."""

    approved: bool
    score: float
    gaps: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(slots=True)
class NodeState:
    """Mutable execution state for one DAG node."""

    node: DagNode
    output: str | None = None
    failed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProposerSpec:
    """One proposer in a Mixture-of-Agents aggregation: a provider + model, optional label and prompt override."""

    provider: str
    model: str
    label: str | None = None
    system_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class AggregateConfig:
    """Immutable settings for an aggregate (mixture-of-agents) run."""

    synthesis_system_prompt: str | None = None
    synthesis_prompt_template: str | None = None
    max_candidate_chars: int = 8000
    max_concurrency: int | None = None
    per_proposer_timeout: float | None = None
    min_successful: int = 1
