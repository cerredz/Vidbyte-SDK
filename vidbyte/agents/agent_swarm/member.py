"""FILE: vidbyte/agents/agent_swarm/member.py

PURPOSE: Defines the four parts that make one ordinary agent loop into a swarm member: AgentSwarmMemberRuntime, the member's loop, which hands it the messages that arrived during its turn after each tool iteration; AgentSwarmMemberAgent, the BaseAgent each member runs as; AgentSwarmMessageTool, the run-bound message tool; and AgentSwarmTurnMiddleware, which records tool calls and turns every finish attempt into the end of a turn.
ROLE IN CODEBASE: AgentSwarmRuntime (runtime.py) builds one AgentSwarmMemberAgent per member, holding one AgentSwarmMessageTool and one AgentSwarmTurnMiddleware; BaseAgent._runtime builds AgentSwarmMemberRuntime for it through RuntimeRegistry (vidbyte/lib/registries/runtimes.py), which resolves AgentRuntimeType.AGENT_SWARM_MEMBER. All four call back into the run's AgentSwarmRuntime, which owns every piece of swarm state. Only AgentSwarmMemberRuntime is exported, so the registry can import it through the package.
ARCHITECTURE NOTE: Each member runs one long BaseAgent run for the whole swarm, so a turn end is a finish attempt that the turn middleware turns into a wait: AgentSwarmRuntime.end_turn returns the next messages, which come back to the model as the feedback of a continued finish, or nothing once the swarm ends, which accepts the finish and lets the run return. Mid-turn delivery is the loop's one documented seam for appending to the conversation, _after_tool_iteration. AgentSwarmRuntime is imported only for type checking and never inside a function, so the package has no import cycle; the member runtime therefore refuses a missing swarm runtime by checking for None, which is all a plain BaseAgent or a fork can pass.
FUNCTION INVENTORY: AgentSwarmMemberRuntime.__init__ refuses construction outside a swarm and _after_tool_iteration appends the delivered messages; AgentSwarmMemberAgent.__init__ configures the member and _runtime_extension_kwargs hands the swarm runtime to its loop; AgentSwarmMessageTool.spec declares message with the peers as its recipient choices and execute posts it; AgentSwarmTurnMiddleware.after_tool_call records TOOL_CALLED and review_finish ends the turn.
COMMON MODIFICATION PATTERNS: A change to what a member holds (policy, history trim, tool-result cap) is made in AgentSwarmMemberAgent.__init__ with its value in vidbyte/lib/constants/agent_swarm.py. Model-facing text for the message tool comes from the agent_swarm prompt family, never from a literal here.
WHAT NOT TO DO IN THIS FILE: 1. Do not import AgentSwarmRuntime at run time; keep it under TYPE_CHECKING. 2. Do not keep swarm state in these classes; AgentSwarmRuntime owns it. 3. Do not set fail_closed to False on the turn middleware; a recording bug must stop that member rather than silently drop an event. 4. Do not override any other loop hook.
KNOWN EDGE CASES: isDone ends only the turn: on a wake the model reads the loop's provisional refusal of isDone and then the delivered messages. A turn that ends with an empty reply is still a turn end, with empty text. An exception in collect_messages or end_turn leaves the loop and fails that member with its cause; an exception in record_tool_call aborts the member through the fail-closed middleware; an exception inside the message tool is a tool error the model reads.
RELATED DOCS: docs/spec/agent-swarm/spec.md (sections 8.1 D-1 to D-3, D-9, D-10, 8.5, and 9.2); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py and tests/features/agent_swarm/test_agent_swarm_messaging.py
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.agents.settings import AgentLoopSettings, ToolSettings
from vidbyte.lib.constants.agent_swarm import (
    AGENT_SWARM_HISTORY_MAX_TOKENS,
    AGENT_SWARM_MESSAGE_TEXT_ARGUMENT,
    AGENT_SWARM_MESSAGE_TO_ARGUMENT,
    AGENT_SWARM_MESSAGE_TOOL_NAME,
    AGENT_SWARM_TOOL_RESULT_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmMember
from vidbyte.lib.dataclasses.agents import FinishReview, ProviderKeys
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.enums import AgentRuntimeStateKey, AgentRuntimeType
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError
from vidbyte.middleware import MessageHistoryCompactionMiddleware
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.agent_swarm.runtime import AgentSwarmRuntime


class AgentSwarmMemberRuntime(AgentRuntime):
    """The linear loop of one swarm member, which receives other agents' messages between its tool iterations."""

    def __init__(self, *, swarm_runtime: AgentSwarmRuntime | None = None, **kwargs: Any) -> None:
        # @intent member-runtime-needs-its-swarm
        # AgentRuntimeType.AGENT_SWARM_MEMBER is selectable by string, so
        # a plain BaseAgent or a fork can reach this class without a
        # swarm; refusing here names the entry point to use instead.
        if swarm_runtime is None:
            raise ConfigurationError(
                "The 'agent_swarm_member' runtime is only available through AgentSwarm; construct AgentSwarm(AgentSwarmSettings(...)) and call arun(goal) instead of BaseAgent(runtime='agent_swarm_member').",
                details={"received_swarm_runtime": type(swarm_runtime).__name__},
            )
        self.swarm_runtime = swarm_runtime
        super().__init__(**kwargs)

    async def _after_tool_iteration(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Append the messages that arrived during this tool iteration as one new user message."""
        # @intent mail-reaches-a-working-agent-between-tool-calls
        # The swarm hands over everything waiting for this agent at once
        # and empties its inbox in the same step, so each message is
        # appended exactly once, after the tool results it followed.
        text = await self.swarm_runtime.collect_messages(self.agent_name)
        if text:
            messages.append({"role": "user", "content": text})


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


class AgentSwarmMessageTool(BaseTool):
    """The message tool: queue one text for one other agent of the swarm, without waiting for it."""

    def __init__(self, swarm_runtime: AgentSwarmRuntime, sender: str, peers: tuple[str, ...]) -> None:
        self.swarm_runtime = swarm_runtime
        self.sender = sender
        self.peers = peers

    def spec(self) -> ToolSpec:
        """Return the message declaration, with the other agents' names as the only recipient choices."""
        prompts = Prompts()
        properties = {
            AGENT_SWARM_MESSAGE_TO_ARGUMENT: {"type": "string", "enum": list(self.peers), "description": prompts.get(Prompt.AGENT_SWARM_MESSAGE_TO_DESCRIPTION).strip()},
            AGENT_SWARM_MESSAGE_TEXT_ARGUMENT: {"type": "string", "description": prompts.get(Prompt.AGENT_SWARM_MESSAGE_TEXT_DESCRIPTION).strip()},
        }
        return ToolSpec(
            name=AGENT_SWARM_MESSAGE_TOOL_NAME,
            description=prompts.get(Prompt.AGENT_SWARM_MESSAGE_TOOL_DESCRIPTION).strip(),
            permission=ToolPermission.SAFE,
            input_schema={"type": "object", "properties": properties, "required": [AGENT_SWARM_MESSAGE_TO_ARGUMENT, AGENT_SWARM_MESSAGE_TEXT_ARGUMENT], "additionalProperties": False},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Queue the message and return the swarm's reply, or its refusal as a tool error."""
        # @intent a-refused-send-is-a-tool-error
        # The swarm checks the recipient and the text again, whatever the
        # schema allowed, and a refusal reaches the model as a tool error
        # it can act on; nothing is queued then.
        try:
            reply = await self.swarm_runtime.post_message(self.sender, call.arguments.get(AGENT_SWARM_MESSAGE_TO_ARGUMENT), call.arguments.get(AGENT_SWARM_MESSAGE_TEXT_ARGUMENT))
        except ToolExecutionError as exc:
            return ToolResult.error(AGENT_SWARM_MESSAGE_TOOL_NAME, exc.message)
        return ToolResult.success(AGENT_SWARM_MESSAGE_TOOL_NAME, reply)


class AgentSwarmMemberAgent(BaseAgent):
    """One member of a swarm: the developer's agent definition with the swarm's tools, prompt, policy, history trim, and turn middleware."""

    session_persistence_supported = False

    def __init__(self, swarm_runtime: AgentSwarmRuntime, member: AgentSwarmMember, *, system_prompt: str, tools: tuple[BaseTool, ...], api_keys: ProviderKeys) -> None:
        # @intent members-get-everything-they-need-to-work
        # The swarm tools need write and execute permission, so the
        # member allows every call, as CodingAgent and
        # InfiniteMemoryAgent do. Its history is trimmed and every tool
        # result is cut, so a run that lasts the whole swarm fits the
        # model; the turn middleware connects its turns to the swarm.
        self.swarm_runtime = swarm_runtime
        super().__init__(
            name=member.name,
            system_prompt=system_prompt,
            runtime=AgentRuntimeType.AGENT_SWARM_MEMBER,
            tools=tools,
            permission_policy=PermissionPolicy.allow_all(),
            agent_loop_settings=AgentLoopSettings(tool_settings=ToolSettings(result_max_chars=AGENT_SWARM_TOOL_RESULT_MAX_CHARS)),
            middleware=(MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=AGENT_SWARM_HISTORY_MAX_TOKENS), AgentSwarmTurnMiddleware(swarm_runtime)),
            api_keys=api_keys,
            provider=member.provider,
            model_name=member.model_name,
        )

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # Hands the run's AgentSwarmRuntime to each AgentSwarmMemberRuntime.
        return {"swarm_runtime": self.swarm_runtime}


__all__ = ["AgentSwarmMemberAgent", "AgentSwarmMemberRuntime", "AgentSwarmMessageTool", "AgentSwarmTurnMiddleware"]
