"""FILE: vidbyte/lib/jev/decision.py

PURPOSE: Provides the shared decision-model operations used by Jev question callers: send a normalized request and score named noul answers.
ROLE IN CODEBASE: JevAgent gates, tool selection, and done checks use DecisionModelHelper so transport and threshold behavior have one canonical implementation.
ARCHITECTURE NOTE: This shared-library helper composes DecisionModelRunner and owns answer scoring; feature-specific thresholds and fail-open actions stay with their callers.
COMMON MODIFICATION PATTERNS: Add provider-independent Jev answer handling here, and pass the request, answer names, and threshold from the caller.
KNOWN EDGE CASES: Runner construction and provider errors propagate to callers, which apply their own fail-open policy. Missing or non-noul answers score as unavailable.
RELATED DOCS: skills/jev-agent/SKILL.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py and tests/test_jev_done.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevNoulScore
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse


class DecisionModelHelper:
    """Canonical request and answer helpers for Jev decision questions."""

    def __init__(self, config: DecisionModelConfig | None = None) -> None:
        self._config = config

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        """Send one Jev request and return its normalized answers and usage."""
        return await DecisionModelRunner(self._config).arun(request)

    @staticmethod
    def score_noul(
        answers: Mapping[str, JevAnswer] | None,
        names: Sequence[str],
        threshold: float,
        veto: float | None = None,
    ) -> JevNoulScore | None:
        """Score every named noul answer against its threshold and optional per-answer veto."""
        found = {name: None if answers is None else answers.get(name) for name in names}
        noul = {name: answer for name, answer in found.items() if answer is not None and answer.question_type is JevQuestionType.NOUL}
        if not noul or len(noul) != len(found):
            return None
        yes = [answer.probabilities[JEV_NOUL_TRUE] for answer in noul.values()]
        score = math.fsum(yes) / len(yes)
        vetoed = veto is not None and min(yes) < veto
        return JevNoulScore(score=score, passed=score >= threshold and not vetoed, answers=noul)

    @classmethod
    def noul_passes(
        cls,
        answers: Mapping[str, JevAnswer] | None,
        name: str,
        threshold: float,
    ) -> bool | None:
        """Return whether one named noul answer meets its threshold, or None when it cannot be scored."""
        verdict = cls.score_noul(answers, (name,), threshold)
        return None if verdict is None else verdict.passed


__all__ = ["DecisionModelHelper"]
