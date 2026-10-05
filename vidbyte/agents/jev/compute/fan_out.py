"""FILE: vidbyte/agents/jev/compute/fan_out.py

PURPOSE: Implements JevComputeFanOut, the move for the EACH_OF_SEVERAL situation: it hands each pending item of the group the main agent is working through to its own helper agent, runs the helpers in parallel, and writes the message that brings every item's report back to the main agent.
ROLE IN CODEBASE: JevComputeController asks `subject` for the items that can still be handed out, cuts that plan to the helpers the budget allows, calls `run`, appends `message` to the main loop, and records the move.
ARCHITECTURE NOTE: No model writes the subtasks: the verified run brief already holds the group, its pending items, and the agent's own quoted plan, and Jev's EACH_OF_SEVERAL signs confirmed the plan applies the same, independent work to each item. So each helper's prompt is built by code from those quotes plus its one item, the items can always run in parallel, and the main agent, which receives every report, combines the results itself.
COMMON MODIFICATION PATTERNS: Change what each helper is told in vidbyte/prompts/prompts/jev_compute/fan_out_prompt.md and what the main agent reads in fan_out_result.md; keep parallelism in JevComputeSettings.max_parallel_helpers.
KNOWN EDGE CASES: An item is handed out at most once per run, even when the brief still lists it as pending because the main agent has not yet reported it done. A failed helper's item is reported back as still the main agent's to do. Reports are clipped to an even share of a total budget.
RELATED DOCS: docs/design/jev-compute-fan-out.md.
TESTS: tests/test_jev_compute_fan_out.py.
"""

from __future__ import annotations

import asyncio

from vidbyte.agents.jev.brief import JevRunBriefEvents
from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.agents.jev.compute.states import JevComputeStates
from vidbyte.agents.jev.settings import JevComputeSettings
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_EACH_OF_SEVERAL_MIN_PENDING,
    JEV_COMPUTE_FAN_OUT_REPORTS_MAX_CHARS,
    JEV_COMPUTE_FAN_OUT_SOURCE,
    JEV_RUN_BRIEF_REQUEST_MAX_CHARS,
)
from vidbyte.lib.dataclasses.jev import (
    JevComputeFanOutPlan,
    JevComputeFanOutReport,
    JevRunBrief,
    JevRunBriefItem,
)
from vidbyte.lib.enums.jev import JevRunBriefItemStatus
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

# The role name fan-out helpers are built under, which also names them in traces.
_ROLE = "fan-out"
# What the main agent reads for an item whose helper failed, and when no item is left to it.
_FAILED_REPORT = "The helper for this item failed, so this item is still yours to do."
_NOTHING_LEFT = "none"


class JevComputeFanOut:
    """EACH_OF_SEVERAL's move: one helper per pending item of the group, run in parallel, each repeating the agent's own plan on its item."""

    def __init__(self, helpers: JevComputeHelpers, compute: JevComputeSettings) -> None:
        # Shares the controller's helper builder, fixes the parallelism, and loads both prompt assets once.
        self.helpers = helpers
        self.parallel = compute.max_parallel_helpers
        self._task = Prompts().get(Prompt.JEV_COMPUTE_FAN_OUT_PROMPT)
        self._result = Prompts().get(Prompt.JEV_COMPUTE_FAN_OUT_RESULT)
        self.begin()

    def begin(self) -> None:
        """Start a new run with no item handed out yet."""
        self._handed: set[tuple[str, str]] = set()

    def subject(self, brief: JevRunBrief) -> JevComputeFanOutPlan | None:
        """Return every pending item of the busiest group not yet handed out, with the agent's plan, or None when too few remain."""
        # @intent an-item-is-handed-out-once
        # The brief marks an item done only after the main agent's own responses say so, so the same group can be
        # recognized again before that happens; skipping items already handed out keeps a second fan-out from
        # redoing work a helper already did.
        group = JevComputeStates.busiest_group(brief)
        if group is None:
            return None
        items = tuple(item for item in brief.items if item.group == group and item.status is JevRunBriefItemStatus.PENDING and (group, item.name) not in self._handed)
        if len(items) < JEV_COMPUTE_EACH_OF_SEVERAL_MIN_PENDING:
            return None
        return JevComputeFanOutPlan(group=group, items=items, plan=JevComputeStates.plan(brief))

    async def run(self, request: str, brief: JevRunBrief, plan: JevComputeFanOutPlan) -> tuple[JevComputeFanOutReport, ...]:
        """Run one helper per item of the plan, at most `max_parallel_helpers` at once, and return their reports in item order."""
        # @intent independent-items-run-in-parallel
        # Jev's EACH_OF_SEVERAL veto already ruled out items whose work depends on each other, so helpers never wait
        # on one another; the semaphore only bounds how many run at once, and every item is marked handed out before
        # its helper starts, whatever the helper's outcome.
        self._handed.update((plan.group, item.name) for item in plan.items)
        limit = asyncio.Semaphore(self.parallel)
        clipped_request = JevRunBriefEvents.clip(request, JEV_RUN_BRIEF_REQUEST_MAX_CHARS)
        rendered_plan = "\n".join(JevComputeStates.quote(quote) for quote in plan.plan)
        rendered_brief = brief.render()

        async def one(item: JevRunBriefItem) -> JevComputeFanOutReport:
            # Builds this item's prompt from the shared plan and runs its helper when a slot is free.
            # @intent one-item-per-helper
            # Each helper is told only its own item, so no two helpers are given the same work and a failed helper's
            # item comes back to the main agent as one named item rather than as an unknown share of the group.
            prompt = self._task.format(request=clipped_request, brief=rendered_brief, plan=rendered_plan, group=plan.group, item=item.name)
            async with limit:
                return JevComputeFanOutReport(item=item, result=await self.helpers.run(_ROLE, prompt, source=f"{JEV_COMPUTE_FAN_OUT_SOURCE}:{item.id}"))

        return tuple(await asyncio.gather(*(one(item) for item in plan.items)))

    def message(self, plan: JevComputeFanOutPlan, reports: tuple[JevComputeFanOutReport, ...]) -> str:
        """Return what the main agent reads after the fan-out: every item's clipped report and the items still left to it."""
        share = JEV_COMPUTE_FAN_OUT_REPORTS_MAX_CHARS // max(len(reports), 1)
        rendered = "\n\n".join(f"### {report.item.name}\n{self.report(report, share)}" for report in reports)
        left = "\n".join(f"- {item.name}" for item in plan.left) or _NOTHING_LEFT
        return self._result.format(group=plan.group, count=len(reports), reports=rendered, left=left)

    @staticmethod
    def report(report: JevComputeFanOutReport, limit: int) -> str:
        """Return one item's report clipped to `limit`, or the note that its helper failed."""
        return _FAILED_REPORT if report.result is None else JevRunBriefEvents.clip(report.result.output, limit)


__all__ = ["JevComputeFanOut"]
