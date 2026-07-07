"""
FILE: vidbyte/middleware/builtins/canary_tripwire.py

PURPOSE:
    Provides data exfiltration detection middleware using canary watermark tokens. Lets developers detect prompt-injection-driven exfiltration attacks where adversarial content in tool results drives the model to reproduce internal content.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - CanaryTripwireMiddleware (class): public or navigational symbol owned here.
    - CanaryTripwireMiddleware (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - ValueError: raised, returned, or imported by this file. Keep context safe and grepable.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; scripts/test-security-middleware.py and compaction-related scripts when changing middleware behavior.

CONCURRENCY MODEL:
    - Review async/task state carefully; this file participates in agent, middleware, tool, or actor execution.
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
