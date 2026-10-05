"""FILE: vidbyte/agents/jev/compute/delegate.py

PURPOSE: Implements JevComputeDelegate, the move for the SELF_CONTAINED_STEP situation: it hands the next step the main agent stated to one fresh helper agent that receives only the user's request and the step, and writes the message that brings the helper's report back to the main agent.
ROLE IN CODEBASE: JevComputeController asks `subject` for the step to hand off, calls `run` when the budget allows, appends `message` to the main loop, and records the move.
ARCHITECTURE NOTE: The helper sees only the request and the step, which is safe because Jev's SELF_CONTAINED_STEP signs, with STATES_ALL as a veto, confirmed the step's words with the request state everything it needs; a step that leans on the run is never recognized. The gain is the main agent's context: the step's reads and tool output stay in the helper, and the main agent receives only the report. The step is the same one Jev judged, the brief's soonest next step.
COMMON MODIFICATION PATTERNS: Change what the helper is told in vidbyte/prompts/prompts/jev_compute/delegate_prompt.md and what the main agent reads in delegate_result.md; keep the run's own text filled in here.
KNOWN EDGE CASES: A step is delegated at most once per run, even while the brief still lists it because the main agent has not yet said it is done. A long report is clipped before the main agent reads it; the full report stays on the move record.
RELATED DOCS: docs/design/jev-compute-delegate.md.
TESTS: tests/test_jev_compute_delegate.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.brief import JevRunBriefEvents
from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_DELEGATE_SOURCE,
    JEV_COMPUTE_HELPER_REPORT_MAX_CHARS,
    JEV_RUN_BRIEF_REQUEST_MAX_CHARS,
)
from vidbyte.lib.dataclasses.jev import (
    JevComputeHelperResult,
    JevRunBrief,
    JevRunBriefQuote,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

# The role name a delegate helper is built under, which also names it in traces.
_ROLE = "delegate"


class JevComputeDelegate:
    """SELF_CONTAINED_STEP's move: hands the agent's next stated step to a fresh helper that sees only the request and the step."""

    def __init__(self, helpers: JevComputeHelpers) -> None:
        # Shares the controller's helper builder and loads both prompt assets once.
        self.helpers = helpers
        self._task = Prompts().get(Prompt.JEV_COMPUTE_DELEGATE_PROMPT)
        self._result = Prompts().get(Prompt.JEV_COMPUTE_DELEGATE_RESULT)
        self.begin()

    def begin(self) -> None:
        """Start a new run with no step delegated yet."""
        self._delegated: set[tuple[str, str]] = set()

    def subject(self, brief: JevRunBrief) -> JevRunBriefQuote | None:
        """Return the brief's soonest next step when it has not been delegated in this run, or None."""
        # @intent a-step-is-delegated-once
        # The brief drops a step only after the main agent's responses show it done, so the same step can be recognized
        # again in the meantime; remembering what was delegated keeps a second helper from repeating it.
        if not brief.next_steps:
            return None
        step = brief.next_steps[0]
        return None if (step.event, step.quote) in self._delegated else step

    async def run(self, request: str, step: JevRunBriefQuote) -> JevComputeHelperResult | None:
        """Hand the step to one fresh helper with only the request, and return its result, or None when it failed."""
        # @intent the-helper-sees-only-what-the-step-states
        # Jev's STATES_ALL veto confirmed the step and the request name everything the step needs, so the helper gets
        # nothing else from the run; the step is marked delegated before the helper starts, whatever its outcome.
        self._delegated.add((step.event, step.quote))
        prompt = self._task.format(request=JevRunBriefEvents.clip(request, JEV_RUN_BRIEF_REQUEST_MAX_CHARS), step=step.quote)
        return await self.helpers.run(_ROLE, prompt, source=JEV_COMPUTE_DELEGATE_SOURCE)

    def message(self, step: JevRunBriefQuote, report: str) -> str:
        """Return what the main agent reads after the helper reports: the step and the helper's clipped report."""
        return self._result.format(step=step.quote, report=JevRunBriefEvents.clip(report, JEV_COMPUTE_HELPER_REPORT_MAX_CHARS))


__all__ = ["JevComputeDelegate"]
