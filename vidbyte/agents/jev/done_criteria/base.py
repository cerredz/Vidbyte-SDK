"""FILE: vidbyte/agents/jev/done_criteria/base.py

PURPOSE: Defines typed criterion results, the subclass contract, and Jev's composite completion policy.
ROLE IN CODEBASE: JevRuntime consumes JevDoneCriteria; concrete criterion subclasses provide deterministic pass/fail behavior.
ARCHITECTURE NOTE: Completion criteria are local policy; this module does not call providers or own agent-loop state.
FUNCTION INVENTORY: JevDoneCriterion.evaluate -> JevDoneCriterionResult; JevDoneCriteria evaluates and combines criterion results.
COMMON MODIFICATION PATTERNS: Add a criterion subclass and result metadata, then cover it through tests/test_jev_done_criteria.py.
WHAT NOT TO DO: Do not add model calls here; provider and loop orchestration belong in vidbyte/agents/jev/runtime.py and vidbyte/agents/runtime.py.
KNOWN EDGE CASES: Empty criteria accept completion and emit no metadata; multiple criteria require every criterion to pass.
RELATED DOCS: docs/design/jev-done-criteria.md.
TESTS: tests/test_jev_done_criteria.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class JevDoneCriterionResult:
    """One criterion's completion decision, model feedback, and public result metadata."""

    is_met: bool
    continuation_prompt: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class JevDoneCriterion(ABC):
    """Base contract implemented by each deterministic Jev completion criterion."""

    @abstractmethod
    def evaluate(self, *, elapsed_seconds: float) -> JevDoneCriterionResult:
        # Returns this criterion's decision without mutating shared agent or run state.
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class JevDoneCriteriaResult:
    """Combined outcome of evaluating all criteria for one finish attempt."""

    is_met: bool
    continuation_prompt: str | None
    metadata: Mapping[str, Any]


class JevDoneCriteria:
    """Evaluates configured Jev criteria with all-required completion semantics."""

    def __init__(self, criteria: Sequence[JevDoneCriterion] = ()) -> None:
        # Retains a stable immutable policy snapshot for one runtime instance.
        self._criteria = tuple(criteria)

    def evaluate(self, *, elapsed_seconds: float) -> JevDoneCriteriaResult:
        # Evaluates each criterion once and aggregates its feedback and metadata.
        results = tuple(criterion.evaluate(elapsed_seconds=elapsed_seconds) for criterion in self._criteria)
        unmet_prompts = tuple(result.continuation_prompt for result in results if not result.is_met)
        metadata = self._combined_metadata(results)
        return JevDoneCriteriaResult(not unmet_prompts, "\n\n".join(unmet_prompts) or None, metadata)

    @staticmethod
    def _combined_metadata(results: Sequence[JevDoneCriterionResult]) -> Mapping[str, Any]:
        # Merges criterion metadata in declaration order so later criteria can intentionally refine a key.
        return {key: value for result in results for key, value in result.metadata.items()}


__all__ = ["JevDoneCriteria", "JevDoneCriteriaResult", "JevDoneCriterion", "JevDoneCriterionResult"]
