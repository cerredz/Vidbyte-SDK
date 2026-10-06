"""FILE: vidbyte/agents/jev/compute/delegate.py

PURPOSE: Implements JevComputeDelegate, the move for the SELF_CONTAINED_STEP situation: it gives one fresh helper the original request, JEV run state, and verified mid-run brief as typed context, then writes the message that brings the helper's report back to the main agent.
ROLE IN CODEBASE: JevComputeController checks whether the same context was already delegated, calls `run` when the budget allows, appends `message` to the main loop, and records the move.
ARCHITECTURE NOTE: `JevComputeHelpers` builds the helper with the main agent's system prompt, model, tools, and permissions. The request stays the helper's prompt; a `ContextManager` carries the available JEV run state and the verified brief. The helper receives no delegate-specific task prompt, and the main agent reads only its clipped report.
COMMON MODIFICATION PATTERNS: Change the typed context assembled here and the report message in `delegate_result.md`; keep helper construction in `JevComputeHelpers`.
KNOWN EDGE CASES: The same request, state, and rendered brief are delegated at most once per run. A long report is clipped before the main agent reads it; the full report stays on the move record. When no run state exists, only the request and brief are supplied.
RELATED DOCS: docs/design/jev-compute-delegate.md.
TESTS: tests/test_jev_compute_delegate.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.brief import JevRunBriefEvents
from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.context import ContextManager, TextContextItem
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_DELEGATE_SOURCE,
    JEV_COMPUTE_HELPER_REPORT_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevComputeHelperResult,
    JevRunBrief,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

# The role name a delegate helper is built under, which also names it in traces.
_ROLE = "delegate"


class JevComputeDelegate:
    """SELF_CONTAINED_STEP's move: gives a fresh helper the request and available JEV state and brief as typed context."""

    def __init__(self, helpers: JevComputeHelpers) -> None:
        # Shares the controller's helper builder and loads the report message once.
        self.helpers = helpers
        self._result = Prompts().get(Prompt.JEV_COMPUTE_DELEGATE_RESULT)
        self.begin()

    def begin(self) -> None:
        """Start a new run with no helper context delegated yet."""
        self._delegated: set[tuple[str, str, str]] = set()

    def already_attempted(self, request: str, run_state: str, brief: JevRunBrief) -> bool:
        """Return whether this exact helper context has already been delegated in the current run."""
        return self._key(request, run_state, brief) in self._delegated

    async def run(self, request: str, run_state: str, brief: JevRunBrief) -> JevComputeHelperResult | None:
        """Give a fresh helper the request, available run state, and brief; return its result or None when it failed."""
        # @intent a-fresh-helper-gets-only-the-current-jev-context
        # The helper's system prompt already matches the main agent. The request stays the prompt, and the state and
        # verified brief travel as typed context; remember the context before starting so a failed attempt is not repeated.
        self._delegated.add(self._key(request, run_state, brief))
        items: list[TextContextItem] = []
        if run_state:
            items.append(TextContextItem(title="JEV run state", content=run_state, source="jev_run_state"))
        items.append(TextContextItem(title="JEV mid-run brief", content=brief.render(), source="jev_run_brief"))
        agent_input = AgentInput(prompt=request, context_manager=ContextManager(tuple(items)))
        return await self.helpers.run(_ROLE, agent_input, source=JEV_COMPUTE_DELEGATE_SOURCE)

    def message(self, report: str) -> str:
        """Return what the main agent reads after the helper reports: its clipped report."""
        return self._result.format(report=JevRunBriefEvents.clip(report, JEV_COMPUTE_HELPER_REPORT_MAX_CHARS))

    @staticmethod
    def _key(request: str, run_state: str, brief: JevRunBrief) -> tuple[str, str, str]:
        """Identify the helper context without relying on a next-step field in the brief."""
        # @intent an-unchanged-helper-context-runs-once
        # Include every user-visible input so repeat recognition cannot repeat work, but new state or a new brief can run.
        return request, run_state, brief.render()


__all__ = ["JevComputeDelegate"]
