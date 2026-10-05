"""FILE: vidbyte/agents/jev/compute/reset.py

PURPOSE: Implements the fresh-agent move: it gives one linear helper the user request, verified brief, exact run facts, and bounded numbered event tail, then returns its report to the main agent.
ROLE IN CODEBASE: JevComputeController calls `run` when FRESH_AGENT is selected and the run-local budget allows it.
ARCHITECTURE NOTE: The helper reads the same shared verified state as recognition. Its prompt makes no claims about structured approaches or open failures because the current brief does not contain those fields.
COMMON MODIFICATION PATTERNS: Keep helper input sourced from JevComputeStates.build and keep prompt text in `vidbyte/prompts/prompts/jev_compute/`.
KNOWN EDGE CASES: A helper outage or empty report returns None; a long report is clipped before the main agent reads it.
RELATED DOCS: docs/design/jev-compute-reset.md.
TESTS: tests/test_jev_compute_reset.py.
"""

from __future__ import annotations

import json

from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.agents.jev.compute.states import JevComputeStates
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_HELPER_REPORT_MAX_CHARS,
    JEV_COMPUTE_RESET_SOURCE,
)
from vidbyte.lib.dataclasses.jev import JevComputeHelperResult, JevRunBrief, JevRunFacts
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_ROLE = "fresh_agent"


class JevComputeReset:
    """Run one fresh helper using the verified state collected at the latest checkpoint."""

    def __init__(self, helpers: JevComputeHelpers) -> None:
        self.helpers = helpers
        self._task = Prompts().get(Prompt.JEV_COMPUTE_RESET_PROMPT)
        self._result = Prompts().get(Prompt.JEV_COMPUTE_RESET_RESULT)

    async def run(
        self,
        request: str,
        brief: JevRunBrief,
        facts: JevRunFacts,
        events: JevRunEventLog,
    ) -> JevComputeHelperResult | None:
        """Start a fresh helper with the same bounded verified evidence used to select its option."""
        # @intent helper-input-matches-recognition-state
        # The helper sees the exact facts and verified brief plus only the bounded, numbered event tail; it must not
        # be told that unstructured approaches or failures exist when the current brief records no such fields.
        state = JevComputeStates.build(request, brief, facts, events)
        prompt = self._task.format(
            request=state["request"],
            brief=state["brief"],
            facts=json.dumps(state["facts"], sort_keys=True),
            recent=state["recent"],
        )
        return await self.helpers.run(_ROLE, prompt, source=JEV_COMPUTE_RESET_SOURCE)

    def message(self, report: str) -> str:
        """Return what the main agent reads after the helper reports, with the report clipped to its configured bound."""
        return self._result.format(report=JevComputeStates.clip(report, JEV_COMPUTE_HELPER_REPORT_MAX_CHARS))


__all__ = ["JevComputeReset"]
