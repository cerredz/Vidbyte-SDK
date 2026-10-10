"""FILE: vidbyte/lib/runners/decision.py

PURPOSE: Semantic transport runner for calibrated decision models: validates a DecisionModelConfig, builds the provider adapter, runs one JevDecisionRequest, and lists the models the account can use.
ROLE IN CODEBASE: DecisionModelHelper uses this runner to send Jev requests; other callers can use it for direct programmatic decisions.
ARCHITECTURE NOTE: Mirrors EmbeddingModelRunner: the runner owns config validation and the transport, and `ModelProviders.decision()` owns adapter selection. Agents never build it through Runner.build, because decision models cannot drive an agent loop.
COMMON MODIFICATION PATTERNS: Keep provider calls as thin pass-throughs; request shaping belongs to vidbyte/lib/dataclasses/jev.py and wire handling to `vidbyte/providers/systemone.py` (every System One host), `vidbyte/providers/openai_decisions.py` (OpenAI Decisions), and `vidbyte/providers/typesafe.py` (TypeSafe-specific managed gateway, model list, and run close). Put shared question scoring in vidbyte/lib/jev/decision.py.
KNOWN EDGE CASES: Construction raises ConfigurationError when no API key resolves, which callers that must fail open treat as "decision model unavailable". DecisionModelHelper.score_noul needs no key and returns None when any named answer is missing or is not a noul answer.
RELATED DOCS: docs/design/jev-agent-scaffold.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevModelCard
from vidbyte.lib.enums.usage import UsageKind
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.lib.usage_ledger import active_usage_ledger
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
        # Sends one decision request, records its usage in the run's active ledger, and returns its normalized answers and usage.
        # @intent runner-is-a-pass-through
        # Provider errors propagate unchanged so the caller owns the fail-open policy.
        # @intent every-jev-call-reaches-the-run-ledger
        # Every Jev call, from DecisionModelHelper or a direct runner caller, passes through here, so this is the one
        # place a decision call is metered; a failed call that TypeSafe still billed is recorded before it propagates.
        ledger = active_usage_ledger()
        try:
            response = await self._provider.run_decision(request=request, transport=self._transport, config=self._config)
        except VidbyteSdkError as exc:
            billed = exc.details.get("usage")
            if ledger is not None and isinstance(billed, Mapping):
                ledger.record_billed_failure(self._provider.provider, self._config.resolved_model(), billed, kind=UsageKind.DECISION)
            raise
        if ledger is not None:
            ledger.record_call(response, kind=UsageKind.DECISION)
        return response

    async def alist_models(self) -> tuple[JevModelCard, ...]:
        # Returns the model IDs and aliases (GET /v1/models) this account can pass as DecisionModelConfig.model.
        # @intent model-listing-is-a-pass-through
        # Aliases move when TypeSafe ships a release; listing lets callers pin a versioned ID
        # themselves, and provider errors propagate unchanged exactly as they do for arun.
        return await self._provider.list_models(transport=self._transport, config=self._config)

    async def aclose_run(self, run_id: str) -> None:
        # Closes one managed run on Vidbyte's gateway (POST /api/v1/models/runs/{run_id}/close).
        # @intent run-close-is-a-pass-through
        # Errors propagate unchanged; JevManagedRun owns the policy that a failed close never fails a run.
        await self._provider.close_run(run_id=run_id, transport=self._transport, config=self._config)

    def model_name(self) -> str:
        # Return the configured model identifier string.
        return self._config.resolved_model()


__all__ = ["DecisionModelRunner"]
