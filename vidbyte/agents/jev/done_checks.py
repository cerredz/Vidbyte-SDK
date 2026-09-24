"""FILE: vidbyte/agents/jev/done_checks.py

PURPOSE: Defines the contract every Jev done-criteria preset implements at a finish attempt.
ROLE IN CODEBASE: JevRuntime builds one state and at most one handoff, then runs each enabled JevDoneCheck against them.
ARCHITECTURE NOTE: A check owns its questions, thresholds, feedback, and metadata; the runtime only merges results and decides to continue.
COMMON MODIFICATION PATTERNS: Add a preset by subclassing JevDoneCheck, adding state/handoff sections, and registering it in JevRuntime._build_checks.
KNOWN EDGE CASES: Check instances are created per run, so they may keep run-local memory such as a disclosure request already sent.
RELATED DOCS: docs/design/jev-scope-coverage-done-criteria.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from vidbyte.agents.jev.presets import JevPresets
from vidbyte.agents.jev.run_state import JevRunHandoff, JevRunSnapshot, JevRunState
from vidbyte.lib.runners.decision import DecisionModelRunner


@dataclass(frozen=True, slots=True)
class JevDoneCheckContext:
    """Everything one check may read at one finish attempt."""

    state: JevRunState
    handoff: JevRunHandoff | None
    snapshot: JevRunSnapshot
    attempt: int
    decision_runner: Callable[[], DecisionModelRunner]


@dataclass(frozen=True, slots=True)
class JevDoneCheckResult:
    """One check's verdict: whether the run may end, why not, and what to report."""

    preset: JevPresets
    complete: bool
    accepted: bool
    feedback: str | None
    metadata: Mapping[str, Any]


class JevDoneCheck(ABC):
    """One named done-criteria preset evaluated at every finish attempt of a run."""

    preset: ClassVar[JevPresets]

    @abstractmethod
    def needs_handoff(self, state: JevRunState) -> bool:
        """Return whether this check reads a handoff section for this run's state."""

    @abstractmethod
    async def evaluate(self, context: JevDoneCheckContext) -> JevDoneCheckResult:
        """Classify the finish attempt and return this check's result."""


__all__ = ["JevDoneCheck", "JevDoneCheckContext", "JevDoneCheckResult"]
