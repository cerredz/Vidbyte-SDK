"""FILE: vidbyte/middleware/builtins/agent_swarm_turn.py

PURPOSE: Defines AgentSwarmTurnMiddleware, the middleware every AgentSwarm member runs with: it records each of the member's tool calls as a TOOL_CALLED swarm event, and it turns each finish attempt into the end of the member's turn, which either continues the same run with the messages that woke the agent or accepts the finish once the swarm has ended.
ROLE IN CODEBASE: Built once per member by AgentSwarmMemberAgent.__init__ (vidbyte/agents/agent_swarm/member.py), which imports it from here, so it also resolves as vidbyte.agents.agent_swarm.member.AgentSwarmTurnMiddleware. Called by vidbyte/agents/runtime.py through MiddlewarePipeline: after_tool_call after every tool call and review_finish at every finish attempt. Both hooks call back into the run's AgentSwarmRuntime (vidbyte/agents/agent_swarm/runtime.py), which owns every piece of swarm state. Its sibling vidbyte/middleware/builtins/agent_swarm_observer.py holds the trim that runs before it and the observer that runs after it, which report model calls, failed attempts, and tool outcomes. Not re-exported from vidbyte.middleware.builtins.
ARCHITECTURE NOTE: Each member runs one long BaseAgent run for the whole swarm, so a turn end is a finish attempt that this middleware turns into a wait: AgentSwarmRuntime.end_turn returns the next messages, which come back to the model as the feedback of a continued finish, or nothing once the swarm ends, which accepts the finish and lets the run return. AgentSwarmRuntime is imported only for type checking, so the middleware layer never imports the agents layer at run time.
FUNCTION INVENTORY: AgentSwarmTurnMiddleware.__init__ keeps the run's AgentSwarmRuntime; after_tool_call records TOOL_CALLED for every tool call except the loop's internal ones; review_finish ends the turn and returns the FinishReview.
COMMON MODIFICATION PATTERNS: A change to what a turn end records or returns is made in AgentSwarmRuntime.end_turn, not here; this class only connects the loop's hooks to the swarm.
WHAT NOT TO DO IN THIS FILE: 1. Do not import AgentSwarmRuntime at run time; keep it under TYPE_CHECKING. 2. Do not keep swarm state here; AgentSwarmRuntime owns it. 3. Do not set fail_closed to False; a recording bug must stop that member rather than silently drop a TOOL_CALLED event. 4. Do not add this class to vidbyte.middleware.builtins; only AgentSwarm builds it.
KNOWN EDGE CASES: isDone ends only the turn: on a wake the model reads the loop's provisional refusal of isDone and then the delivered messages. A turn that ends with an empty reply is still a turn end, with empty text. An exception in end_turn leaves the loop and fails that member with its cause; an exception in record_tool_call aborts the member through the fail-closed middleware.
RELATED DOCS: docs/spec/agent-swarm-v2/spec.md (sections 8.1 D-8, D-16 and 8.5); vidbyte/agents/agent_swarm/README.md; vidbyte/middleware/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py, tests/features/agent_swarm/test_agent_swarm_lifecycle.py, and tests/features/agent_swarm/test_agent_swarm_messaging.py
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.agents import FinishReview
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.enums import AgentRuntimeStateKey
from vidbyte.middleware.base import AgentMiddleware

if TYPE_CHECKING:
    from vidbyte.agents.agent_swarm.runtime import AgentSwarmRuntime


class AgentSwarmTurnMiddleware(AgentMiddleware):
    """Records each tool call as a swarm event and turns each finish attempt into the end of a turn."""

    def __init__(self, swarm_runtime: AgentSwarmRuntime) -> None:
        self.swarm_runtime = swarm_runtime

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Record a TOOL_CALLED event for every tool call except the loop's own internal ones, such as isDone."""
        if ctx.tool_call is not None and ctx.tool_result is not None and not ctx.tool_is_internal:
            await self.swarm_runtime.record_tool_call(ctx.agent_name, ctx.tool_call.tool_name, ctx.tool_result.status)
        return MiddlewareDecision.continue_()

    async def review_finish(self, ctx: MiddlewareContext) -> FinishReview:
        """End the agent's turn: continue with the next messages when it is woken, or accept the finish once the swarm ends."""
        # @intent a-finish-is-the-end-of-a-turn
        # The reply that ends the turn is isDone's answer when the model
        # called it, else the model's last text. The swarm decides what
        # happens next: new messages continue this same run as the next
        # turn, and an empty answer means the swarm has ended.
        run_state: Mapping[Any, Any] = ctx.run_state
        outputs = run_state.get(AgentRuntimeStateKey.ITERATION_OUTPUTS.value, ())
        reply = ctx.tool_result.output if ctx.tool_result is not None else (outputs[-1] if outputs else "")
        text = await self.swarm_runtime.end_turn(ctx.agent_name, reply)
        return FinishReview.continue_with(text) if text else FinishReview.accept()


__all__ = ["AgentSwarmTurnMiddleware"]
