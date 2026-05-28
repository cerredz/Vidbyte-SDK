"""Context Protocol Header

Description:
    Provides data exfiltration detection middleware using canary watermark tokens.
Purpose:
    Lets developers detect prompt-injection-driven exfiltration attacks where
    adversarial content in tool results drives the model to reproduce internal content.
Architecture:
    - CanaryTripwireMiddleware: Probabilistically tracks canary tokens alongside tool
      results and scans model output for leaked canaries.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime middleware hooks.
"""

from __future__ import annotations

import random

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class CanaryTripwireMiddleware(AgentMiddleware):
    """Detect data exfiltration by tracking canary tokens in tool results."""

    def __init__(self, *, watermark_prefix: str = "VIDBYTE-CANARY-", inject_probability: float = 0.3, abort_reason: str = "canary_leaked", random_seed: int | None = None) -> None:
        # Configures canary generation parameters and initializes the internal canary ledger.
        if inject_probability <= 0.0 or inject_probability > 1.0:
            raise ValueError("inject_probability must be in (0.0, 1.0].")
        self._watermark_prefix = watermark_prefix
        self._inject_probability = inject_probability
        self._abort_reason = abort_reason
        self._rng = random.Random(random_seed)
        self._canaries: dict[str, str] = {}

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Clears canary ledger at the start of each run to prevent cross-run leakage.
        del ctx
        self._canaries.clear()
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Probabilistically generates a canary token and records it in the internal ledger.
        if ctx.tool_is_internal or ctx.tool_result is None:
            return MiddlewareDecision.continue_()
        if self._rng.random() < self._inject_probability:
            canary = self._generate_canary()
            tool_name = ctx.tool_call.tool_name if ctx.tool_call else "unknown"
            self._canaries[canary] = tool_name
        return MiddlewareDecision.continue_()

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Scans model output for leaked canary strings and aborts if found.
        if not self._canaries:
            return MiddlewareDecision.continue_()
        text = self._extract_model_text(ctx.model_response)
        if not text:
            return MiddlewareDecision.continue_()
        return self._scan_for_leaked_canaries(text)

    def _generate_canary(self) -> str:
        # Builds a unique canary string from the configured prefix and 8 random hex bytes.
        hex_chars = "".join(f"{self._rng.randint(0, 255):02x}" for _ in range(8))
        return f"{self._watermark_prefix}{hex_chars}"

    def _scan_for_leaked_canaries(self, text: str) -> MiddlewareDecision:
        # Returns abort if any active canary appears in the given text.
        for canary, tool_name in self._canaries.items():
            if canary in text:
                return MiddlewareDecision.abort(
                    self._abort_reason,
                    metadata={"leaked_canary": canary, "source_tool": tool_name},
                )
        return MiddlewareDecision.continue_()

    @staticmethod
    def _extract_model_text(model_response: object | None) -> str:
        # Extracts text content from a model response object via .text or str() fallback.
        if model_response is None:
            return ""
        text = getattr(model_response, "text", None)
        if isinstance(text, str):
            return text
        return str(model_response)


__all__ = ["CanaryTripwireMiddleware"]
