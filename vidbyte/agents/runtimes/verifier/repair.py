"""Context Protocol Header

Description:
    Defines VerifierRepairStrategy.
Purpose:
    Decides what mechanically happens to the next attempt after a rejected
    finalization: continue the same conversation, restart fresh with a
    summary, restrict the next attempt's edit scope, or (not yet implemented)
    fork into parallel repair attempts.
Architecture:
    - VerifierRepairStrategy: repair() dispatches to one private method per
      mode. VerifierRepairStrategyParams (validated dataclass: which
      RepairMode, and branch_width for PARALLEL_BRANCHING) lives in
      vidbyte.lib.dataclasses.verifier, not here, per review feedback on
      PR #349.
Relations:
    Consumes vidbyte.agents.runtimes.verifier.types.RepairContext, produces
    RepairOutcome, consumed by AgentVerifierRuntime.
Similar Files:
    - vidbyte/agents/contract.py: the feedback-then-continue shape this
      module's IN_PLACE_CONTINUE mode extends with a mechanical dimension.
"""

from __future__ import annotations

import re

from vidbyte.lib.dataclasses.verifier import RepairContext, RepairMode, RepairOutcome, VerificationAttempt, VerifierRepairStrategyParams

_PATH_TOKEN_PATTERN = re.compile(r"[\w][\w./\\-]*\.[A-Za-z0-9]{1,10}(?::\d+)?")


class VerifierRepairStrategy:
    """Decides what mechanically happens to the next attempt after a rejected finalization."""

    def __init__(self, params: VerifierRepairStrategyParams) -> None:
        # Stores the already-validated configuration for this repair strategy instance.
        self.params = params

    async def repair(self, context: RepairContext) -> RepairOutcome:
        """Builds the RepairOutcome for the next attempt under the configured RepairMode."""
        handlers = {
            RepairMode.IN_PLACE_CONTINUE: self._in_place_continue,
            RepairMode.FRESH_RESTART_WITH_SUMMARY: self._fresh_restart,
            RepairMode.TARGETED_SCOPE: self._targeted_scope,
            RepairMode.PARALLEL_BRANCHING: self._parallel_branch,
        }
        return await handlers[self.params.mode](context)

    async def _in_place_continue(self, context: RepairContext) -> RepairOutcome:
        # The simplest repair: append the already-rendered feedback and keep the same conversation going.
        message = {"role": "user", "content": context.feedback_text}
        return RepairOutcome(injected_messages=(message,), restart_session=False, scope_lock=None)

    async def _fresh_restart(self, context: RepairContext) -> RepairOutcome:
        # Throws away conversational continuity in exchange for a clean-room attempt informed by full history.
        summary = self._summarize_history(context.ledger)
        message = {"role": "user", "content": summary}
        return RepairOutcome(injected_messages=(message,), restart_session=True, scope_lock=None)

    async def _targeted_scope(self, context: RepairContext) -> RepairOutcome:
        # Same message as in-place repair, plus an edit-scope constraint derived from the failing diagnostics.
        message = {"role": "user", "content": context.feedback_text}
        scope = self._extract_scope(context.attempt) if self.params.scope_lock else ()
        return RepairOutcome(injected_messages=(message,), restart_session=False, scope_lock=scope or None)

    async def _parallel_branch(self, context: RepairContext) -> RepairOutcome:
        # Not implemented: forking the agent's session mid-run is not a confirmed runtime capability yet.
        del context
        raise NotImplementedError(
            "RepairMode.PARALLEL_BRANCHING requires forking the agent's session mid-run, which is not a "
            "confirmed capability of this runtime today. See docs/design/verifier-runtime.md Non-Goals."
        )

    def _extract_scope(self, attempt: VerificationAttempt) -> tuple[str, ...]:
        # Best-effort file/symbol extraction from failing diagnostics; finding nothing means no restriction.
        failed_diagnostics = " ".join(v.diagnostics for v in attempt.aggregated.verdicts if not v.passed)
        matches = _PATH_TOKEN_PATTERN.findall(failed_diagnostics)
        return tuple(sorted(set(matches)))

    def _summarize_history(self, ledger: object) -> str:
        # Renders each past attempt's number, pass/fail, and failing verifier names into a short digest.
        lines = ["A previous attempt in this run did not pass verification. History:"]
        for attempt in ledger.history():  # type: ignore[attr-defined]
            status = "PASSED" if attempt.aggregated.passed else "FAILED"
            failing_names = ", ".join(v.verifier_name for v in attempt.aggregated.verdicts if not v.passed)
            line = f"- Attempt {attempt.attempt_number}: {status}"
            if failing_names:
                line += f" (failing: {failing_names})"
            lines.append(line)
        return "\n".join(lines)


__all__ = ["VerifierRepairStrategy", "VerifierRepairStrategyParams"]
