"""FILE: vidbyte/agents/jev/compute/reset.py

PURPOSE: Implements JevComputeReset, the move for the REPEATING situation: it hands the problem the main agent keeps retrying to one fresh helper agent, together with the approaches that already failed and the open errors, and writes the message that brings the helper's report back to the main agent.
ROLE IN CODEBASE: JevComputeController calls `run` when Jev recognizes REPEATING and the budget allows a move, appends `message` to the main loop when the helper reports, and records the move on JevAgent.response.
ARCHITECTURE NOTE: The helper starts with a clean history, which is the point of the move: the main agent's context is anchored on the failing approaches, and a fresh agent that is told what failed but did not live through it can look for the cause instead. The stuck problem comes from JevComputeStates.stuck_problem, the same lookup Jev's REPEATING questions judged. Both texts are prompt assets.
COMMON MODIFICATION PATTERNS: Change what the helper is told in vidbyte/prompts/prompts/jev_compute/reset_prompt.md and what the main agent reads in reset_result.md; keep the run's own text filled in here.
KNOWN EDGE CASES: A brief with no stuck problem starts no helper. A long report is clipped before the main agent reads it; the full report stays on the move record.
RELATED DOCS: docs/design/jev-compute-reset.md.
TESTS: tests/test_jev_compute_reset.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.brief import JevRunBriefEvents
from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.agents.jev.compute.states import JevComputeStates
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_HELPER_REPORT_MAX_CHARS,
    JEV_COMPUTE_RESET_SOURCE,
    JEV_RUN_BRIEF_REQUEST_MAX_CHARS,
)
from vidbyte.lib.dataclasses.jev import (
    JevComputeHelperResult,
    JevRunBrief,
    JevRunBriefApproach,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

# The role name a reset helper is built under, which also names it in traces.
_ROLE = "reset"
# What the helper reads when the run has no open error recorded.
_NO_OPEN_ERRORS = "none recorded"


class JevComputeReset:
    """REPEATING's move: hands the stuck problem to a fresh helper that knows what already failed."""

    def __init__(self, helpers: JevComputeHelpers) -> None:
        # Shares the controller's helper builder and loads both prompt assets once.
        self.helpers = helpers
        self._task = Prompts().get(Prompt.JEV_COMPUTE_RESET_PROMPT)
        self._result = Prompts().get(Prompt.JEV_COMPUTE_RESET_RESULT)

    async def run(self, request: str, brief: JevRunBrief) -> tuple[str, JevComputeHelperResult | None] | None:
        """Hand the brief's stuck problem to a fresh helper; return the problem and the helper's result, or None when there is no stuck problem."""
        # @intent the-helper-knows-what-failed-but-not-how
        # The helper gets the problem, every approach already tried with its outcome and quoted evidence, and the open
        # errors, but none of the main agent's reasoning, so it avoids the failed approaches without inheriting the
        # assumptions that led to them.
        stuck = JevComputeStates.stuck_problem(brief)
        if stuck is None:
            return None
        problem, approaches = stuck
        prompt = self._task.format(
            request=JevRunBriefEvents.clip(request, JEV_RUN_BRIEF_REQUEST_MAX_CHARS),
            problem=problem,
            attempts="\n".join(self._attempt(approach) for approach in approaches),
            failures="\n".join(f"- {JevComputeStates.quote(quote)}" for quote in brief.open_failures) or _NO_OPEN_ERRORS,
        )
        return problem, await self.helpers.run(_ROLE, prompt, source=JEV_COMPUTE_RESET_SOURCE)

    def message(self, problem: str, report: str) -> str:
        """Return what the main agent reads after the helper reports: the problem and the helper's clipped report."""
        return self._result.format(problem=problem, report=JevRunBriefEvents.clip(report, JEV_COMPUTE_HELPER_REPORT_MAX_CHARS))

    @staticmethod
    def _attempt(approach: JevRunBriefApproach) -> str:
        # Renders one tried approach with its outcome and the quotes that show it.
        # @intent the-helper-sees-the-evidence-not-a-summary
        # Each approach carries the verified quotes that show it, so the helper reads what actually happened rather than
        # the brief writer's wording alone, and can tell which errors the approach produced.
        evidence = "; ".join(JevComputeStates.quote(quote) for quote in approach.evidence)
        return f"- {approach.approach} ({approach.outcome.value}): {evidence}"


__all__ = ["JevComputeReset"]
