"""FILE: vidbyte/agents/browser/runtime.py

PURPOSE: Defines BrowserAgentRuntime, the BROWSER runtime: for each run of a BrowserAgent it splits the live MCP servers' tools by role, builds the goal card (deriving the done criteria when none are given), gives the orchestrator run_episode and patch_goal in place of the action tools, pins the card at the top of its context, runs the inherited linear loop, rechecks every finish in a fresh context, rebuilds the stored conversation once it passes its cap, stops a run that keeps stalling, and closes the run's record and usage.
ROLE IN CODEBASE: RuntimeRegistry (vidbyte/lib/registries/runtimes.py) resolves AgentRuntimeType.BROWSER to this class, and BaseAgent._runtime builds one per run with the collaborators from BrowserAgent._runtime_extension_kwargs (agent.py). It builds BrowserGoal and BrowserGoalCheck (goal.py) and BrowserEpisodeTool (episode.py) for the run.
ARCHITECTURE NOTE: A subclass of AgentRuntime that adds per-run setup around super().arun and uses the loop's existing hooks (_continue_finish_attempt, _after_tool_iteration, _budget_stop), as JevRuntime and InfiniteMemoryRuntime do; the loop itself is unchanged. The runtime refuses to exist without its agent's collaborators, because the enum is selectable by string. The card lives on a run-local copy of the context manager, so the agent's own manager is never changed. The rebuild goes through the shared ContextCompactionEngine, which keeps whole call/result groups for every provider.
FUNCTION INVENTORY: __init__ refuses construction outside BrowserAgent; arun is the narrated main function; _after_tool_iteration rebuilds, rechecks when due, and pins the card; _continue_finish_attempt rechecks a finish and sends a refused one back with its gap; _rebuild_history keeps only the newest call/result group once the stored conversation passes its cap; _budget_stop adds the stall stop to the loop's own budgets.
COMMON MODIFICATION PATTERNS: Per-run setup goes in arun before super().arun; per-iteration work goes in _after_tool_iteration. A new run-bound tool adds its name to BROWSER_RESERVED_TOOL_NAMES, which the clash check in arun reads.
WHAT NOT TO DO IN THIS FILE: 1. Do not start a server, emit an event, or touch the response in __init__; BaseAgent builds this class twice per run. 2. Do not change the agent's own context manager; copy it. 3. Do not summarize or edit messages by hand; the rebuild keeps whole groups through the shared engine. 4. Do not give the orchestrator an action tool.
KNOWN EDGE CASES: A caller's explicit system option replaces the system prompt and the card for that run (EC-24). After a refused final-text finish, the loop appends the model's own answer after the gap message (EC-36). A newest group that alone passes the cap is kept whole, so nothing is removed and nothing is recorded (EC-35). A run whose usage cannot be priced emits run_stopped, naming UsageAccountingError, and then raises it; a cancelled run, or one whose loop raises, emits no run_finished or run_stopped.
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 6.1 INV-14 to INV-18, INV-22, INV-23, INV-30, and 8.1 D-2, D-11, D-13); vidbyte/agents/infinite/runtime.py (the pattern this follows)
TESTS: tests/features/browser_agent/test_browser_agent_contract.py, tests/features/browser_agent/test_browser_agent_recheck.py, tests/features/browser_agent/test_browser_agent_rebuild.py, and tests/features/browser_agent/test_browser_agent_observability.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.agents.browser.episode import BrowserEpisodeTool
from vidbyte.agents.browser.events import BrowserAgentEvents
from vidbyte.agents.browser.goal import BrowserGoal, BrowserGoalCheck
from vidbyte.agents.browser.response import BrowserResponse
from vidbyte.agents.browser.settings import BrowserAgentSettings
from vidbyte.agents.browser.tools import BrowserAgentTools
from vidbyte.agents.browser.usage import BrowserAgentUsage
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.context.compaction import CompactionMode, ContextCompactionEngine
from vidbyte.context.manager import ContextManager
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.constants.browser import (
    BROWSER_HISTORY_MAX_TOKENS,
    BROWSER_MIN_COUNT,
    BROWSER_RESERVED_TOOL_NAMES,
)
from vidbyte.lib.dataclasses.agents import AgentStopReason
from vidbyte.lib.dataclasses.browser import BrowserGoalCard
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.browser import BrowserEventKind, BrowserToolRole, BrowserVerdict
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, UsageAccountingError
from vidbyte.lib.tracing import SpanContext
from vidbyte.lib.util import TokenEstimate
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.mcp import McpServerHandle
from vidbyte.tools.types import ToolCallContext

# The stop reasons of a run whose finish was accepted.
_FINISHED = (AgentStopReason.FINAL_RESPONSE.value, AgentStopReason.IS_DONE.value)


class BrowserAgentRuntime(AgentRuntime):
    """The linear loop of a BrowserAgent run, with its goal card, episodes, rechecks, and rebuilds."""

    # Set at the start of each run, before the loop calls any hook.
    goal: BrowserGoal

    def __init__(self, *, settings: BrowserAgentSettings | None = None, browser_tools: BrowserAgentTools | None = None, servers: tuple[McpServerHandle, ...] | None = None, response: BrowserResponse | None = None, events: BrowserAgentEvents | None = None, **kwargs: Any) -> None:
        # @intent browser-runtime-needs-its-agent
        # AgentRuntimeType.BROWSER is selectable by string, so a plain
        # BaseAgent or a fork can reach this class without its
        # collaborators; refusing here names the agent to use instead.
        if not isinstance(settings, BrowserAgentSettings) or not isinstance(browser_tools, BrowserAgentTools) or not isinstance(servers, tuple) or not isinstance(response, BrowserResponse) or not isinstance(events, BrowserAgentEvents):
            raise ConfigurationError(
                "The 'browser' runtime is only available through BrowserAgent; construct BrowserAgent(BrowserAgentSettings(...)) instead of BaseAgent(runtime='browser').",
                details={"received_settings": type(settings).__name__, "received_browser_tools": type(browser_tools).__name__, "received_servers": type(servers).__name__, "received_response": type(response).__name__, "received_events": type(events).__name__},
            )
        self.settings = settings
        self.browser_tools = browser_tools
        self.servers = servers
        self.response = response
        self.events = events
        super().__init__(**kwargs)
        # Building the runtime has no side effects (INV-23): the ledger
        # and the check agents only start working inside arun.
        self.usage = BrowserAgentUsage(self.usage_tracker, self.agent_name)
        self.check = BrowserGoalCheck(settings)

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        """Split the tools by role, build and pin the goal card, run the loop with run_episode and patch_goal, and close the run's record and usage."""
        # Every model call of the run, from the orchestrator, every
        # worker, and every check, lands in this agent's one ledger.
        with self.usage.scope():
            # @intent run-bound-names-belong-to-the-run
            # An MCP tool named like run_episode or patch_goal would
            # make the catalog refuse it mid-run, so refuse the run
            # before any model call.
            clash = [name for name in self.tools.names() if name in BROWSER_RESERVED_TOOL_NAMES]
            if clash:
                raise ConfigurationError(f"The tool {clash[0]!r} uses a name BrowserAgent reserves for its own tools; rename it or use another server. Reserved: {', '.join(BROWSER_RESERVED_TOOL_NAMES)}.", details={"tool": clash[0], "reserved": list(BROWSER_RESERVED_TOOL_NAMES)})

            # The workers act through the action servers' tools, so a
            # run without any cannot do its job and stops here.
            action = self.browser_tools.tools(self.servers, BrowserToolRole.ACTION)
            if not action:
                raise ConfigurationError(f"BrowserAgent '{self.agent_name}' has no tools from its {BrowserToolRole.ACTION.value!r} role servers; check that each action server starts and lists its tools.", details={"role": BrowserToolRole.ACTION.value, "servers": [handle.name for handle in self.servers]})

            # Start a fresh record and event count for this run.
            self.response.start(message)
            self.events.start()
            self.events.emit(BrowserEventKind.RUN_STARTED)

            # The card holds the task and its done criteria; when none
            # are given, one structured call writes them first.
            done_when = self.settings.done_when or await self.check.done_when(message)
            self.goal = BrowserGoal(BrowserGoalCard(goal=message, done_when=done_when), self.settings, self.response, self.events)
            self.events.emit(BrowserEventKind.GOAL_SET, str(len(done_when)))

            # The orchestrator plans and delegates: it loses the action
            # tools and gains run_episode and patch_goal, and it starts
            # from a clean context with no earlier run's history.
            episode = BrowserEpisodeTool(self.settings, action, self.goal, self.response, self.events)
            self.tools = self.tools.without(action).extend((episode, self.goal.tool()))
            context = replace(context, tools=self.tools.specs(), tool_calls=(), history=())
            run_options = dict(options or {})
            run_options.pop("tools", None)

            # Pin the card at the top of a run-local copy of the
            # context, so the agent's own context manager is unchanged.
            self.context_manager = self.context_manager.copy() if self.context_manager is not None else ContextManager()
            self.context_manager.upsert(self.goal.item(), placement=ContextWindowPlacement.TOP_OF_CONTEXT)

            # Run the inherited loop; the hooks below recheck, rebuild,
            # and stop a stalled run.
            result = await super().arun(message, handle=handle, context=context, metadata=metadata, options=run_options, trace_context=trace_context)

            # Total the run's usage before saying how it ended: a run
            # whose cost is partly unknown raises instead of returning,
            # so its last event is run_stopped, never run_finished.
            try:
                usage = self.usage.settle()
            except UsageAccountingError as exc:
                self.events.emit(BrowserEventKind.RUN_STOPPED, type(exc).__name__)
                raise

            # Say how the run ended, then close the record with the
            # run's whole usage.
            stop_reason = str(result.metadata.get("stop_reason") or "")
            self.events.emit(BrowserEventKind.RUN_FINISHED if stop_reason in _FINISHED else BrowserEventKind.RUN_STOPPED, stop_reason)
            return self.response.finished(result, usage, self.events.errors)

    async def _after_tool_iteration(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Rebuild the stored conversation once it passes its cap, run the periodic recheck when it is due, and pin the card again."""
        # @intent the-card-follows-every-iteration
        # Episodes and patches change the card between calls, and the
        # card is the orchestrator's only lasting view of the run.
        await self._rebuild_history(messages)
        if self.goal.recheck_due():
            self.goal.rechecked(await self.check.recheck(self.goal.card), at_finish=False)
        if self.context_manager is not None:
            self.context_manager.upsert(self.goal.item(), placement=ContextWindowPlacement.TOP_OF_CONTEXT)

    async def _continue_finish_attempt(self, result: AgentResult, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> bool:
        """Recheck a finish in a fresh context; accept it on done or when the recheck is unavailable, else send it back with the gap."""
        # @intent a-finish-needs-a-fresh-done-verdict
        # The orchestrator cannot judge its own long run, so a fresh
        # agent that sees only the goal, the criteria, and the progress
        # decides; an outage accepts the finish rather than block it.
        outcome = self.goal.rechecked(await self.check.recheck(self.goal.card), at_finish=True)
        if outcome is None or outcome.verdict is BrowserVerdict.DONE:
            return False
        # A refused finish skips _after_tool_iteration, so rebuild and
        # pin the card here, before the gap message is added.
        await self._rebuild_history(messages)
        if self.context_manager is not None:
            self.context_manager.upsert(self.goal.item(), placement=ContextWindowPlacement.TOP_OF_CONTEXT)
        messages.append({"role": "user", "content": Prompts().get(Prompt.BROWSER_AGENT_CONTINUE_PROMPT).format(verdict=outcome.verdict.value, gap=outcome.gap)})
        return True

    async def _rebuild_history(self, messages: list[dict[str, Any]]) -> None:
        # @intent the-orchestrator-rebuilds-instead-of-growing
        # The card carries the goal, the criteria, and every progress
        # line on each call, so once the stored conversation passes its
        # cap only the newest whole call/result group is kept. The
        # shared engine computes that group for every provider, so no
        # call is split from its results and nothing is summarized.
        if sum(TokenEstimate.count(json.dumps(dict(message), default=str)) for message in messages) <= BROWSER_HISTORY_MAX_TOKENS:
            return
        kept, stats = await ContextCompactionEngine().compact_provider_messages(messages, mode=CompactionMode.TRIM_WITH_PROVIDER_BOUNDARIES, options={"max_messages": 1})
        messages[:] = list(kept)
        if stats.removed_count > BROWSER_MIN_COUNT:
            self.response.rebuilt()
            self.events.emit(BrowserEventKind.CONTEXT_REBUILT, str(stats.removed_count))

    def _budget_stop(self, *, iteration_count: int, tokens_used: int | None, contexts: Sequence[ToolCallContext], started_at: float) -> AgentResult | None:
        # @intent a-stalled-run-stops-before-its-next-model-call
        # A run whose rechecks keep finding no progress would only
        # spend more calls, so it stops before its next model call,
        # with the card as its output; otherwise the loop's own
        # budgets apply.
        if self.goal.stalled():
            output = Prompts().get(Prompt.BROWSER_AGENT_STALLED_OUTPUT).format(card=self.goal.item().content)
            return self._stopped_result(output, stop_reason=AgentStopReason.GOAL_STALLED, iteration_count=iteration_count, tokens_used=tokens_used, contexts=contexts)
        return super()._budget_stop(iteration_count=iteration_count, tokens_used=tokens_used, contexts=contexts, started_at=started_at)


__all__ = ["BrowserAgentRuntime"]
