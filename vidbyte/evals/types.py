"""Context Protocol Header

Description:
    Declares the typed data representation structures for the evaluation module.
Purpose:
    Enforces unified schema boundaries for inputs and results throughout the run, persistence,
    and comparison lifecycle of the Vidbyte SDK evaluation harness.
Architecture:
    - EvalCase: Input payload defining prompt, expected outcome, tags, custom grader, and templates.
    - GraderResult: Direct feedback containing the normalized score, passed flag, and reason.
    - EvalResult: Container for single case execution metrics, actual responses, and metadata.
    - EvalSuiteResult: Aggregated suite run results with derived helper stats (pass rate, mean score).
Relations:
    Related to vidbyte.evals.base (BaseGrader reference) and vidbyte.evals.runner (consumes these types).
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vidbyte.evals.base import BaseGrader
    from vidbyte.evals.templates.base import EvalTemplate


@dataclass(frozen=True)
class EvalCase:
    """Represents a single evaluation test case containing a prompt, expected answer, tags, grader, and templates."""

    prompt: str
    expected: Any | None = None
    tags: tuple[str, ...] = ()
    grader: BaseGrader | None = None
    templates: tuple[EvalTemplate | str | Mapping[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraderResult:
    """Holds the evaluation metrics for a graded output, including a score, status, and feedback reason."""

    score: float
    passed: bool
    reason: str = ""


@dataclass(frozen=True)
class EvalResult:
    """Contains the complete execution lifecycle details of a single evaluation case run."""

    case: EvalCase
    actual: str
    grader_result: GraderResult
    latency_ms: float
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalSuiteResult:
    """Summarizes the full execution metrics and aggregated statistics of an entire evaluation suite run."""

    suite_name: str
    model: str
    results: tuple[EvalResult, ...]
    measured_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def pass_rate(self) -> float:
        # Calculates the ratio of successfully passed cases in the suite run.
        if not self.results:
            return 0.0
        passed_count = sum(1 for r in self.results if r.grader_result.passed)
        return passed_count / len(self.results)

    @property
    def mean_score(self) -> float:
        # Computes the mathematical average score across all executed cases in the suite.
        if not self.results:
            return 0.0
        return statistics.mean(r.grader_result.score for r in self.results)

    @property
    def p95_latency_ms(self) -> float:
        # Resolves the 95th percentile execution latency across all case runs in the suite.
        if not self.results:
            return 0.0
        latencies = sorted(r.latency_ms for r in self.results)
        idx = int(len(latencies) * 0.95)
        return latencies[min(idx, len(latencies) - 1)]
