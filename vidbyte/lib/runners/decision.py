"""FILE: vidbyte/lib/runners/decision.py

PURPOSE: Semantic runner for calibrated decision models: validates a DecisionModelConfig, builds the provider adapter, and runs one JevDecisionRequest.
ROLE IN CODEBASE: `vidbyte/tools/classifier/jev_decide.py` calls this runner; applications may also call it directly for programmatic Jev decisions.
ARCHITECTURE NOTE: Mirrors EmbeddingModelRunner: the runner owns config validation and the transport, and `ModelProviders.decision()` owns adapter selection. Agents never build it through Runner.build, because decision models cannot drive an agent loop.
COMMON MODIFICATION PATTERNS: Keep this a thin pass-through; request shaping belongs to vidbyte/lib/dataclasses/jev.py and wire handling to vidbyte/providers/typesafe.py.
KNOWN EDGE CASES: Construction raises ConfigurationError when no API key resolves, which callers that must fail open treat as "decision model unavailable".
RELATED DOCS: docs/design/jev-decide-tool.md.
TESTS: tests/test_jev_decide_tool.py and scripts/test_jev_decide_tool.py.
"""

from __future__ import annotations

from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevDecisionRequest
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

    def model_name(self) -> str:
        # Return the configured model identifier string.
        return self._config.model


__all__ = ["DecisionModelRunner"]
