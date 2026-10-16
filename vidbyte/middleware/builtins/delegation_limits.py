"""FILE: vidbyte/middleware/builtins/delegation_limits.py

PURPOSE: Defines DelegationLimitsMiddleware, which holds one delegating tool to a depth cap and a batch cap: it denies the tool's call when the agent already sits at the deepest allowed level, or when the call carries more tasks than one call may.
ROLE IN CODEBASE: Attached by InfiniteMemoryAgent (vidbyte/agents/infinite/agent.py) to its root at depth 0, and by InfinitePair (vidbyte/agents/infinite/launch.py) to every generator one level deeper than its parent, each with the DelegationLimits record its settings build; runs in AgentRuntime's before_tool_call hook. Follows ReadonlyPathsMiddleware (readonly_paths.py), which denies an edit the same way.
ARCHITECTURE NOTE: Deterministic limits belong in code, not in the prompt (PR #1084 review): the model is told only that limits exist, and this middleware decides. The runtime calls before_tool_call for internal tools too, and a denial keeps the internal marker, so it works for launch_subagent, which is internal. A denial is returned to the model as "Tool denied by middleware: <reason>", and the reason names the limit, its value, and what to do instead. The agent-count cap is not here: it depends on how many agents a run has started, which only the tool's own journal knows.
FUNCTION INVENTORY: DelegationLimitsMiddleware.__init__ checks the record and the depth; before_tool_call is the narrated main function.
COMMON MODIFICATION PATTERNS: A new per-call delegation limit is one more field on DelegationLimits (vidbyte/lib/dataclasses/middleware.py) and one more check here, with a reason that names the field and its value. A new delegating agent attaches this middleware to each agent that holds its delegating tool, with that agent's depth.
WHAT NOT TO DO IN THIS FILE: 1. Do not deny a call whose task list is not a list; let the tool run so the model sees the tool's own error. 2. Do not count tasks the tool will replay rather than start; the batch cap is about the size of one call, and replay is the tool's business. 3. Do not hold the agent's settings object; it carries API keys.
KNOWN EDGE CASES: depth is the agent's own level, so an agent at max_depth may still use every other tool; only starting a deeper level is refused. A call over both caps names the depth cap, because splitting the batch would not help. Another tool with the same name as the delegating tool would be checked too, which InfiniteMemoryAgent prevents by reserving the name.
RELATED DOCS: vidbyte/middleware/README.md (Built-in middleware); vidbyte/agents/infinite/README.md
TESTS: tests/test_delegation_limits_middleware.py and tests/features/infinite_memory_agent/test_infinite_memory_delegation.py
"""

from __future__ import annotations

from vidbyte.lib.constants.delegation import DELEGATION_ROOT_DEPTH
from vidbyte.lib.dataclasses.middleware import (
    DelegationLimits,
    MiddlewareContext,
    MiddlewareDecision,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.middleware.base import AgentMiddleware


class DelegationLimitsMiddleware(AgentMiddleware):
    """Deny a delegating tool's call at the depth cap, or when it carries more tasks than the batch cap."""

    def __init__(self, limits: DelegationLimits, *, depth: int) -> None:
        # The caps come as a validated record; depth is this agent's own
        # level, 0 for the agent the developer built.
        self._limits = RecordFieldConverter.require_instance(limits, "DelegationLimitsMiddleware.limits", DelegationLimits)
        self._depth = RecordFieldValidator.require_int(depth, "DelegationLimitsMiddleware.depth", minimum=DELEGATION_ROOT_DEPTH)

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Deny the delegating tool's call when it breaks a cap; let every other call through."""
        limits = self._limits
        # Only the delegating tool is checked; every other call passes
        # untouched.
        call = ctx.tool_call
        if call is None or call.tool_name != limits.tool_name:
            return MiddlewareDecision.continue_()

        # @intent the-depth-cap-stops-delegation-not-work
        # At the deepest allowed level the agent keeps every other tool;
        # only another level of subagents is refused, and the model is
        # told to do the work itself. This check comes first, because
        # splitting the batch would not help.
        if self._depth >= limits.max_depth:
            return MiddlewareDecision.deny_tool(
                f"{limits.tool_name} is not available here: this agent is at depth {self._depth}, and max_depth ({limits.max_depth}) allows no deeper subagents. Do this work yourself with your other tools.",
                metadata={"limit": "max_depth", "depth": self._depth, "max_depth": limits.max_depth},
            )

        # @intent the-batch-cap-is-counted-before-anything-starts
        # A call with more tasks than one call may carry is refused
        # whole, before any task starts, so the model splits it instead
        # of losing part of it. A task list that is not a list is left
        # to the tool, which reports its own error.
        tasks = call.arguments.get(limits.batch_argument)
        if isinstance(tasks, list) and len(tasks) > limits.max_parallel:
            return MiddlewareDecision.deny_tool(
                f"This {limits.tool_name} call carries {len(tasks)} tasks, over max_parallel ({limits.max_parallel}); nothing was started. Split the tasks over several calls of at most {limits.max_parallel} each.",
                metadata={"limit": "max_parallel", "tasks": len(tasks), "max_parallel": limits.max_parallel},
            )

        # Within both caps, the call runs as usual.
        return MiddlewareDecision.continue_()


__all__ = ["DelegationLimitsMiddleware"]
