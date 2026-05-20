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
