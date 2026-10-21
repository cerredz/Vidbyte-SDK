"""FILE: vidbyte/middleware/builtins/agent_swarm_observer.py

PURPOSE: Defines the two middleware that let an AgentSwarm see and bound its members' loops: AgentSwarmObserverMiddleware, which reports every model response, failed model attempt, and tool result to the swarm and refuses further model calls once the swarm is stopping, and AgentSwarmTrimMiddleware, the provider-boundary history trim that also reports how many messages each trimmed call dropped.
ROLE IN CODEBASE: Built once per member by AgentSwarmMemberAgent.__init__ (vidbyte/agents/agent_swarm/member.py), in the order trim, turn (the sibling vidbyte/middleware/builtins/agent_swarm_turn.py), observer. Called by vidbyte/agents/runtime.py through MiddlewarePipeline at before_model_call, after_model_response, on_model_error, and after_tool_call. Every hook calls back into the run's AgentSwarmRuntime (vidbyte/agents/agent_swarm/runtime.py), which owns every piece of swarm state and records every event. Not re-exported from vidbyte.middleware.builtins.
ARCHITECTURE NOTE: Two classes because they do two jobs: the observer only reports and refuses, and the trim only rewrites the outgoing history, reusing MessageHistoryCompactionMiddleware's trim_with_provider_boundaries mode unchanged and reading the drop count from that mode's own result. The pipeline does not pass one middleware's transform metadata to the next, so the trim reports its own drop rather than leaving it to the observer. AgentSwarmRuntime is imported only for type checking, so the middleware layer never imports the agents layer at run time.
FUNCTION INVENTORY: AgentSwarmObserverMiddleware.__init__ keeps the run's AgentSwarmRuntime; before_model_call refuses a call once the swarm is stopping; after_model_response reports the call's usage and refuses the next step once the swarm is stopping; on_model_error reports a failed attempt and lets the loop decide its retry; after_tool_call reports every non-internal tool result. AgentSwarmTrimMiddleware.__init__ configures the trim; before_model_call trims and reports the drop when the history changed.
COMMON MODIFICATION PATTERNS: A change to what an observation records is made in the matching AgentSwarmRuntime.record_* method, not here; these classes only connect the loop's hooks to the swarm. A new observation adds one hook here and one record_* method on the runtime.
WHAT NOT TO DO IN THIS FILE: 1. Do not import AgentSwarmRuntime at run time; keep it under TYPE_CHECKING. 2. Do not keep swarm state here; AgentSwarmRuntime owns it. 3. Do not set fail_closed to False; a recording bug must stop that member rather than silently drop an event. 4. Do not return anything but continue from on_model_error; the loop's own retry and fallback decide what a failed attempt means. 5. Do not add these classes to vidbyte.middleware.builtins; only AgentSwarm builds them.
KNOWN EDGE CASES: A recording bug raises inside a hook, and the fail-closed pipeline turns it into a middleware abort, so the member's run returns on its own and the swarm records agent_exited with text middleware_abort. after_tool_call sees the raw tool result before the loop's result cap, so the truncation count is exact. A call already sent to the provider when the swarm starts stopping still returns and is still reported; only the next call is refused.
RELATED DOCS: docs/spec/agent-swarm-v2/spec.md (sections 8.1 D-8, D-9 and 8.5, and 6.1 INV-22 to INV-27); vidbyte/agents/agent_swarm/README.md; vidbyte/middleware/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_observer.py, tests/features/agent_swarm/test_agent_swarm_stop.py and tests/features/agent_swarm/test_agent_swarm_contract.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_HISTORY_MAX_TOKENS
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.middleware.compaction.base import CompactionMode
from vidbyte.middleware.compaction.context_compaction import (
    MessageHistoryCompactionMiddleware,
)

if TYPE_CHECKING:
    from vidbyte.agents.agent_swarm.runtime import AgentSwarmRuntime

# The abort reason every member's loop returns with once the swarm has
# decided to stop.
_STOPPING_REASON = "agent_swarm_stopping"


class AgentSwarmObserverMiddleware(AgentMiddleware):
    """Reports a member's model calls, failed attempts, and tool results to the swarm, and refuses model calls once it stops."""

    def __init__(self, swarm_runtime: AgentSwarmRuntime) -> None:
        self.swarm_runtime = swarm_runtime

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Refuse the model call once the swarm is stopping, so no paid call starts after the decision."""
        # @intent no-paid-call-after-the-stop-decision
        # Once the swarm has decided to stop, every further model call of
        # every member is refused here, before anything is sent.
        if self.swarm_runtime.stopping:
            return MiddlewareDecision.abort(_STOPPING_REASON)
        return MiddlewareDecision.continue_()

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Report the response's usage to the swarm, then refuse the next step when the swarm is now stopping."""
        # Report the call first, because this call may be the one that
        # spends the swarm's token budget and decides the stop.
        await self.swarm_runtime.record_model_call(ctx.agent_name, ctx.model_usage, ctx.model_call_count)
        # Then stop this member at once when the swarm is stopping, so it
        # neither runs the response's tools nor calls the model again.
        if self.swarm_runtime.stopping:
            return MiddlewareDecision.abort(_STOPPING_REASON)
        return MiddlewareDecision.continue_()

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Report the failed model attempt and let the loop's own retry and fallback decide what happens next."""
        # @intent model-errors-are-observed-never-decided
        # Every failed attempt is recorded, even one a retry later absorbs,
        # and the decision always continues, so the loop's retry policy is
        # untouched by the swarm.
        if ctx.error is not None:
            await self.swarm_runtime.record_model_error(ctx.agent_name, ctx.error)
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Report every tool result except the loop's own internal ones, such as isDone."""
        if ctx.tool_call is not None and ctx.tool_result is not None and not ctx.tool_is_internal:
            await self.swarm_runtime.record_tool_outcome(ctx.agent_name, ctx.tool_call, ctx.tool_result)
        return MiddlewareDecision.continue_()


class AgentSwarmTrimMiddleware(MessageHistoryCompactionMiddleware):
    """Trims a member's outgoing history at provider boundaries and reports how many messages each trimmed call dropped."""

    name = "AgentSwarmTrimMiddleware"

    def __init__(self, swarm_runtime: AgentSwarmRuntime) -> None:
        # The same trim trim_with_provider_boundaries builds, capped at the
        # swarm's history limit.
        super().__init__(mode=CompactionMode.TRIM_WITH_PROVIDER_BOUNDARIES, max_tokens=AGENT_SWARM_HISTORY_MAX_TOKENS)
        self.swarm_runtime = swarm_runtime

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Trim the outgoing history, and report the drop to the swarm when the trim changed it."""
        # Let the parent trim the history this call will carry.
        decision = await super().before_model_call(ctx)
        # @intent the-drop-count-comes-from-the-trim-itself
        # Report only a call the trim really changed, with the count the
        # trim's own statistics give, never an estimate.
        transform = decision.transform
        if transform is not None and transform.metadata.get("changed"):
            dropped = int(transform.metadata["before_count"]) - int(transform.metadata["after_count"])
            await self.swarm_runtime.record_history_trim(ctx.agent_name, dropped)
        return decision


__all__ = ["AgentSwarmObserverMiddleware", "AgentSwarmTrimMiddleware"]
