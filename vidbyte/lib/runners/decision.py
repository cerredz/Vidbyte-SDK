"""FILE: vidbyte/lib/runners/decision.py

PURPOSE: Semantic runner for calibrated decision models: validates a DecisionModelConfig, builds the provider adapter, runs one JevDecisionRequest, lists the models the account can use, and scores a set of noul answers against a threshold.
ROLE IN CODEBASE: Jev runtime capabilities and applications call this runner for programmatic decisions; JevPreflightGate calls score_noul to turn a preset's answers into a pass or fail.
ARCHITECTURE NOTE: Mirrors EmbeddingModelRunner: the runner owns config validation and the transport, and `ModelProviders.decision()` owns adapter selection. Agents never build it through Runner.build, because decision models cannot drive an agent loop.
COMMON MODIFICATION PATTERNS: Keep the calls a thin pass-through; request shaping belongs to vidbyte/lib/dataclasses/jev.py and wire handling to vidbyte/providers/typesafe.py. Put any rule that turns Jev's probabilities into a yes or no next to score_noul.
KNOWN EDGE CASES: Construction raises ConfigurationError when no API key resolves, which callers that must fail open treat as "decision model unavailable". score_noul needs no key and returns None when any named answer is missing or is not a noul answer.
RELATED DOCS: docs/design/jev-agent-scaffold.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevModelCard, JevNoulScore
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.providers import ModelProviders


class DecisionModelRunner:
    """Semantic runner for calibrated decision models such as TypeSafe Jev."""

    def __init__(self, config: DecisionModelConfig | None = None, *, transport: HttpTransport | None = None) -> None:
        # Validates the config (including the API key), then binds the transport and provider adapter.
        # @intent missing-key-fails-at-construction
        # Resolving the key here, not on the first call, lets fail-open callers detect a missing
        # key once and disable themselves instead of paying a failed request per decision.
        self._config = config or DecisionModelConfig()
        self._config.validate()
        self._transport = transport or HttpTransport()
        self._provider = ModelProviders.decision(self._config)

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Sends one decision request and returns its normalized answers and usage.
        # @intent runner-is-a-pass-through
        # Provider errors propagate unchanged so the caller owns the fail-open policy.
        return await self._provider.run_decision(request=request, transport=self._transport, config=self._config)

    async def alist_models(self) -> tuple[JevModelCard, ...]:
        # Returns the model IDs and aliases (GET /v1/models) this account can pass as DecisionModelConfig.model.
        # @intent model-listing-is-a-pass-through
        # Aliases move when TypeSafe ships a release; listing lets callers pin a versioned ID
        # themselves, and provider errors propagate unchanged exactly as they do for arun.
        return await self._provider.list_models(transport=self._transport, config=self._config)

    @staticmethod
    def score_noul(answers: Mapping[str, JevAnswer] | None, names: Sequence[str], threshold: float) -> JevNoulScore | None:
        """Average P(yes) over the named noul answers and decide yes when the mean reaches `threshold`."""
        # @intent every-named-answer-counts
        # Callers phrase every question so yes means satisfied, so the mean needs no inversion. A score
        # built from only some of the answers would look confident while hiding a gap, so any missing
        # or non-noul answer returns None and the caller treats the decision as unavailable.
        found = {name: None if answers is None else answers.get(name) for name in names}
        noul = {name: answer for name, answer in found.items() if answer is not None and answer.question_type is JevQuestionType.NOUL}
        if not noul or len(noul) != len(found):
            return None
        score = math.fsum(answer.probabilities[JEV_NOUL_TRUE] for answer in noul.values()) / len(noul)
        return JevNoulScore(score=score, passed=score >= threshold, answers=noul)

    def model_name(self) -> str:
        # Return the configured model identifier string.
        return self._config.model


__all__ = ["DecisionModelRunner"]
