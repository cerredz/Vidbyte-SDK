"""Context Protocol Header

Description:
    Defines the post-run verification algorithm.
Purpose:
    Verifies complete agent attempts outside the inner loop and rebuilds the
    next attempt's initial messages after a rejected result.
Architecture note:
    - PostRunVerificationMode: wraps the normal AgentRuntime attempt callback.
Relations:
    Uses the shared AgentVerifierRuntime checkpoint evaluator and the
    PostRunVerificationModeParams / VerifierRetryContextMode contracts.
Role in codebase:
    Owns complete-attempt verification and retry request construction.
Common modification patterns:
    Change retry context selection through PostRunVerificationModeParams.
Known edge cases:
    Fresh-context retries intentionally discard prior messages and retain only
    the verifier feedback needed to guide the next attempt.
Related docs:
    docs/design/verifier-runtime-algorithms.md
Tests:
    Covered by post-run mode delegation and full SDK tests.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from vidbyte.agents.runtimes.verifier.algorithms.base import RunOnce, VerifierRuntimeMode
from vidbyte.lib.dataclasses.verifier import (
    PostRunVerificationModeParams,
    ResolutionContext,
    VerifierRetryContextMode,
    VerifierRunRequest,
    VerifierRuntimeModeKind,
    VerifierRuntimeOutcome,
)
from vidbyte.agents.runtimes.verifier.types import GateDecision

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier.runtime import AgentVerifierRuntime

POST_RUN_COMPACT_LIMIT = 12000


class PostRunVerificationMode(VerifierRuntimeMode):
    """Runs and verifies complete agent attempts, retrying rejected results."""

    kind = VerifierRuntimeModeKind.POST_RUN

    def __init__(self, params: PostRunVerificationModeParams | None = None) -> None:
        # Stores validated retry-context settings, defaulting to full history.
        self.params = params or PostRunVerificationModeParams()

    # @intent post-run-retry
    async def run(self, runtime: AgentVerifierRuntime, request: VerifierRunRequest, run_once: RunOnce) -> Any:
        # Repeats complete attempts until verification allows the result or the shared budget stops retries.
        current = request
        result: Any = None
        for _ in range(runtime.settings.params.budget.params.max_attempts):
            result = await run_once(current)
            outcome = await runtime.evaluate_result(current, result)
            if outcome.decision is not GateDecision.REJECT_AND_CONTINUE:
                return runtime.with_verifier_metadata(result)
            current = self._retry_request(current, result, outcome.feedback or "")
        return runtime.with_verifier_metadata(result)

    # @intent retry-context
    def _retry_request(self, request: VerifierRunRequest, result: Any, feedback: str) -> VerifierRunRequest:
        # Builds the next attempt's initial messages under the selected context-retention mode.
        options = dict(request.options or {})
        original = tuple(options.get("messages", ()))
        previous_output = str(getattr(result, "output", result))
        if self.params.context_mode is VerifierRetryContextMode.FULL_HISTORY:
            messages = (*original, {"role": "assistant", "content": previous_output}, {"role": "user", "content": feedback})
        elif self.params.context_mode is VerifierRetryContextMode.COMPACTED_HISTORY:
            summary = self._compact_output(previous_output)
            messages = ({"role": "user", "content": f"Previous attempt summary:\n{summary}\n\nVerifier feedback:\n{feedback}"},)
        else:
            messages = ({"role": "user", "content": feedback},)
        options["messages"] = messages
        return replace(request, options=options)

    @staticmethod
    def _compact_output(output: str) -> str:
        # Keeps retry context bounded while retaining the tail most likely to contain the final answer.
        return output if len(output) <= POST_RUN_COMPACT_LIMIT else f"...{output[-POST_RUN_COMPACT_LIMIT:]}"

    async def on_finalization(self, runtime: AgentVerifierRuntime, context: ResolutionContext) -> VerifierRuntimeOutcome:
        # Defers verification to the outer post-run wrapper so the complete result is available.
        del runtime, context
        return VerifierRuntimeOutcome(GateDecision.ALLOW_FINALIZE, None, None)


__all__ = ["PostRunVerificationMode"]
