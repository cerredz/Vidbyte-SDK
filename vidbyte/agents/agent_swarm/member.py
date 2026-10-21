"""FILE: vidbyte/agents/agent_swarm/member.py

PURPOSE: Defines three of the parts that make one ordinary agent loop into a swarm member: AgentSwarmMemberRuntime, the member's loop, which after each tool iteration compacts the agent's own history when it is due and then hands it the messages that arrived during its turn; AgentSwarmMemberAgent, the BaseAgent each member runs as; and AgentSwarmMessageTool, the run-bound message tool. The turn middleware, which records tool calls and turns every finish attempt into the end of a turn, lives in the middleware layer (vidbyte/middleware/builtins/agent_swarm_turn.py) beside the trim and observer middleware (agent_swarm_observer.py); this module imports it to build each member, so it also resolves from here.
ROLE IN CODEBASE: AgentSwarmRuntime (runtime.py) builds one AgentSwarmMemberAgent per member, holding one AgentSwarmMessageTool and the three swarm middleware; BaseAgent._runtime builds AgentSwarmMemberRuntime for it through RuntimeRegistry (vidbyte/lib/registries/runtimes.py), which resolves AgentRuntimeType.AGENT_SWARM_MEMBER. Every part calls back into the run's AgentSwarmRuntime, which owns every piece of swarm state. The compaction parts come from compaction.py. Only AgentSwarmMemberRuntime is exported from the package, so the registry can import it through the package.
ARCHITECTURE NOTE: Each member runs one long BaseAgent run for the whole swarm, so a turn end is a finish attempt that the turn middleware turns into a wait. The loop's one documented seam for changing the conversation, _after_tool_iteration, does two things in a fixed order: a compaction when one is due (a compact request is pending, or the measured context reached the trigger and, after the first compaction, the history's estimate grew by the target since the last one), then mail, so a delivered message never comes before the summary and no tool call is open at the cut. The compaction reuses ContextCompactionEngine in summarize_range mode with the member's own AgentSwarmHandoffSummarizer, and its one side call is recorded once in the member's UsageTracker, added to its token count, and reported to the swarm like a loop call. AgentSwarmRuntime is imported only for type checking and never inside a function, so the package has no import cycle; the member runtime therefore refuses a missing swarm runtime or summarizer by checking for None, which is all a plain BaseAgent or a fork can pass.
FUNCTION INVENTORY: AgentSwarmMemberRuntime.__init__ refuses construction outside a swarm and builds the compaction engine; _after_tool_iteration is the narrated main function of the seam; _estimate, _measured_context, _keep_last, _compact, and _count_side_call are its leaf helpers. AgentSwarmMessageTool.spec declares message with every agent named in its recipient description, validate_call leaves every check to the swarm, and execute posts it. AgentSwarmMemberAgent.__init__ configures the member, call_model makes one call on its runner outside the loop, and _runtime_extension_kwargs hands the swarm runtime and the summarizer to its loop.
COMMON MODIFICATION PATTERNS: A change to what a member holds (policy, compaction knobs, tool-result cap, middleware) is made in AgentSwarmMemberAgent.__init__ with its value in vidbyte/lib/constants/agent_swarm.py. A change to when or how a member compacts is made in _after_tool_iteration and its leaves. Model-facing text for the message tool comes from the agent_swarm prompt family, never from a literal here.
WHAT NOT TO DO IN THIS FILE: 1. Do not import AgentSwarmRuntime at run time; keep it under TYPE_CHECKING. 2. Do not keep swarm state in these classes; AgentSwarmRuntime owns it. 3. Do not define middleware here; the swarm middleware belong to the middleware layer. 4. Do not override any other loop hook. 5. Do not let one leaf helper of _after_tool_iteration call another; the main function sequences them. 6. Do not append mail before the compaction; the summary must come first.
KNOWN EDGE CASES: An exception in collect_messages leaves the loop and fails that member with its cause; an exception inside the message tool is a tool error the model reads. A failed summary call is recorded as model_error and keeps the history unchanged. A compaction with nothing older than the kept messages makes no side call and records nothing. When the system prompt, the tools, and the goal alone reach the trigger, a repeat automatic compaction waits until the history's estimate has grown by the target since the last one, so it costs one summary per target of new history, not one per iteration. A compact request made in the same response as isDone waits for the first tool iteration after the agent is woken, because the loop skips this seam for a finishing response. The turn middleware's own edge cases are listed in its module.
RELATED DOCS: docs/spec/agent-swarm-v2/spec.md (sections 6.1 INV-30 to INV-36, 8.1 D-4, D-10 to D-12, and 8.5); vidbyte/agents/agent_swarm/README.md; vidbyte/middleware/builtins/agent_swarm_turn.py
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py, tests/features/agent_swarm/test_agent_swarm_messaging.py and tests/features/agent_swarm/test_agent_swarm_compaction.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.agents.agent_swarm.compaction import AgentSwarmHandoffSummarizer
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.agents.settings import AgentLoopSettings, ToolSettings
from vidbyte.lib.constants.agent_swarm import (
    AGENT_SWARM_COMPACTION_TARGET_TOKENS,
    AGENT_SWARM_COMPACTION_TRIGGER_TOKENS,
    AGENT_SWARM_MESSAGE_TEXT_ARGUMENT,
    AGENT_SWARM_MESSAGE_TO_ARGUMENT,
    AGENT_SWARM_MESSAGE_TOOL_NAME,
    AGENT_SWARM_TOOL_RESULT_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmMember
from vidbyte.lib.dataclasses.agents import ProviderKeys
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.enums.agent_swarm import AgentSwarmCompactionTrigger
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError, VidbyteSdkError
from vidbyte.lib.token_usage import token_usage_from_response
from vidbyte.lib.util.text import TokenEstimate
from vidbyte.middleware.builtins.agent_swarm_observer import (
    AgentSwarmObserverMiddleware,
    AgentSwarmTrimMiddleware,
)
from vidbyte.middleware.builtins.agent_swarm_turn import AgentSwarmTurnMiddleware
from vidbyte.middleware.compaction.base import CompactionMode, CompactionStats
from vidbyte.middleware.compaction.engine import ContextCompactionEngine
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.agent_swarm.runtime import AgentSwarmRuntime


class AgentSwarmMemberRuntime(AgentRuntime):
    """The linear loop of one swarm member, which compacts its own history and receives other agents' messages between its tool iterations."""

    def __init__(self, *, swarm_runtime: AgentSwarmRuntime | None = None, summarizer: AgentSwarmHandoffSummarizer | None = None, **kwargs: Any) -> None:
        # @intent member-runtime-needs-its-swarm
        # AgentRuntimeType.AGENT_SWARM_MEMBER is selectable by string,
        # so a plain BaseAgent or a fork can reach this class without a
        # swarm; refusing here names the entry point to use instead.
        if swarm_runtime is None or summarizer is None:
            raise ConfigurationError(
                "The 'agent_swarm_member' runtime is only available through AgentSwarm; construct AgentSwarm(AgentSwarmSettings(...)) and call arun(goal) instead of BaseAgent(runtime='agent_swarm_member').",
                details={"received_swarm_runtime": type(swarm_runtime).__name__},
            )
        self.swarm_runtime = swarm_runtime
        self._summarizer = summarizer
        # One engine per member, holding the member's own summarizer.
        self._engine = ContextCompactionEngine(summarizer=summarizer)
        # The estimate of the history right after the last compaction,
        # None before the first.
        self._compacted_estimate: int | None = None
        super().__init__(**kwargs)

    async def _after_tool_iteration(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Compact this agent's history when it is due, then append the messages that arrived during this tool iteration."""
        name = self.agent_name
        # @intent compaction-runs-between-iterations-before-mail
        # A compaction is due when the agent asked for one with compact
        # (focus "" when it gave none) or when its last measured context
        # reached the trigger; a request wins, so one iteration compacts
        # once. Nothing is compacted once the swarm is stopping.
        focus = self.swarm_runtime.take_compaction_request(name)
        estimate = self._estimate(messages)
        measured = self._measured_context(estimate)
        trigger_at = self.config.compaction_trigger_tokens
        # @intent a-repeat-compaction-waits-for-new-history
        # The prompt, the tools, and the goal are never compacted, so
        # when they alone reach the trigger, every iteration would pay
        # for a summary of the last summary. After the first compaction,
        # an automatic one also waits until the history has grown by the
        # target since the last; a compact request never waits.
        target = self.config.compaction_target_tokens or 0
        grown = self._compacted_estimate is None or estimate >= self._compacted_estimate + target
        if focus is not None:
            trigger: AgentSwarmCompactionTrigger | None = AgentSwarmCompactionTrigger.TOOL
        elif trigger_at is not None and measured >= trigger_at and grown:
            trigger = AgentSwarmCompactionTrigger.AUTO
        else:
            trigger = None
        if trigger is not None and not self.swarm_runtime.stopping:
            # Hand the focus to the summarizer and forget any earlier
            # response, so a summary call is seen only when one was made.
            self._summarizer.focus = focus or ""
            self._summarizer.last_response = None
            # Keep the newest messages that fit the target and summarize
            # everything older, rewriting the live list in place.
            stats = await self._compact(messages, self._keep_last(messages))
            # A summary call was made only when something older existed;
            # record its usage once, then the compaction itself.
            if stats is not None and self._summarizer.last_response is not None:
                # Remember the rewritten history's size, so the next
                # automatic compaction waits for a target of new history.
                self._compacted_estimate = self._estimate(messages)
                await self._count_side_call(state, self._summarizer.last_response)
                await self.swarm_runtime.record_compaction(name, trigger, focus or "", measured, stats.before_count - stats.after_count + 1)

        # @intent mail-reaches-a-working-agent-between-tool-calls
        # Then the swarm hands over everything waiting for this agent at
        # once and empties its inbox in the same step, so each message is
        # appended exactly once, after the tool results and the summary.
        text = await self.swarm_runtime.collect_messages(name)
        if text:
            messages.append({"role": "user", "content": text})

    @staticmethod
    def _estimate(messages: Sequence[Mapping[str, Any]]) -> int:
        # The four-characters-per-token estimate of the history. It
        # counts each whole message, because a tool call's arguments and
        # Gemini's parts are sent too but are not content.
        return sum(TokenEstimate.count(str(message)) for message in messages)

    def _measured_context(self, estimate: int) -> int:
        # The prompt size the provider last reported for this agent, or
        # the history's estimate when it reported none.
        reported = self.swarm_runtime.last_prompt_tokens(self.agent_name)
        return reported if reported is not None else estimate

    def _keep_last(self, messages: Sequence[Mapping[str, Any]]) -> int:
        # Count the newest messages whose estimate fits the target, at
        # least one; the strategy rounds the count up to whole tool-call
        # groups itself. Each whole message is counted, as in _estimate.
        target = self.config.compaction_target_tokens or 0
        kept, used = 0, 0
        for message in reversed(messages):
            used += TokenEstimate.count(str(message))
            if used > target:
                break
            kept += 1
        return max(kept, 1)

    async def _compact(self, messages: list[dict[str, Any]], keep_last: int) -> CompactionStats | None:
        # Summarize everything older than the kept messages; a failed
        # summary call is reported and leaves the history as it was.
        try:
            compacted, stats = await self._engine.compact_provider_messages(messages, mode=CompactionMode.SUMMARIZE_RANGE, options={"keep_last": keep_last})
        except VidbyteSdkError as error:
            await self.swarm_runtime.record_model_error(self.agent_name, error)
            return None
        messages[:] = list(compacted)
        return stats

    async def _count_side_call(self, state: BaseAgentRuntimeLoopState, response: object) -> None:
        # The summary call is a real model call: it goes into this
        # agent's usage ledger and token count, and the swarm counts it
        # against its budget like a loop call. It has no runner handle,
        # so there is no runner metadata to read usage from.
        usage_record = self.usage_tracker.record_call(response)
        state.tokens_used = self._add_token_usage(state.tokens_used, token_usage_from_response(response, {}))
        await self.swarm_runtime.record_model_call(self.agent_name, usage_record.usage if usage_record is not None else None, state.model_call_count)


class AgentSwarmMessageTool(BaseTool):
    """The message tool: queue one text for any agent of the swarm, itself included, without waiting for it."""

    def __init__(self, swarm_runtime: AgentSwarmRuntime, sender: str, agents: tuple[str, ...]) -> None:
        self.swarm_runtime = swarm_runtime
        self.sender = sender
        self.agents = agents

    def spec(self) -> ToolSpec:
        """Return the message declaration, whose recipient description names every agent of the swarm."""
        prompts = Prompts()
        properties = {
            AGENT_SWARM_MESSAGE_TO_ARGUMENT: {"type": "string", "description": prompts.get(Prompt.AGENT_SWARM_MESSAGE_TO_DESCRIPTION).strip().format(agents=", ".join(self.agents))},
            AGENT_SWARM_MESSAGE_TEXT_ARGUMENT: {"type": "string", "description": prompts.get(Prompt.AGENT_SWARM_MESSAGE_TEXT_DESCRIPTION).strip()},
        }
        return ToolSpec(
            name=AGENT_SWARM_MESSAGE_TOOL_NAME,
            description=prompts.get(Prompt.AGENT_SWARM_MESSAGE_TOOL_DESCRIPTION).strip(),
            permission=ToolPermission.SAFE,
            input_schema={"type": "object", "properties": properties, "required": [AGENT_SWARM_MESSAGE_TO_ARGUMENT, AGENT_SWARM_MESSAGE_TEXT_ARGUMENT], "additionalProperties": False},
        )

    def validate_call(self, call: ToolCall) -> str | None:
        """Accept every call, so a missing or non-text argument reaches the swarm, which refuses it with its own reason."""
        # @intent the-swarm-refuses-and-records-every-bad-send
        # The loop's own check would refuse a missing argument before
        # the swarm sees it, so no message_refused event would record it.
        return None

    async def execute(self, call: ToolCall) -> ToolResult:
        """Queue the message and return the swarm's reply, or its refusal as a tool error."""
        # @intent a-refused-send-is-a-tool-error
        # The swarm checks the recipient and the text, whatever the
        # model sent, and a refusal reaches the model as a tool error it
        # can act on; nothing is queued then.
        try:
            reply = await self.swarm_runtime.post_message(self.sender, call.arguments.get(AGENT_SWARM_MESSAGE_TO_ARGUMENT), call.arguments.get(AGENT_SWARM_MESSAGE_TEXT_ARGUMENT))
        except ToolExecutionError as exc:
            return ToolResult.error(AGENT_SWARM_MESSAGE_TOOL_NAME, exc.message)
        return ToolResult.success(AGENT_SWARM_MESSAGE_TOOL_NAME, reply)


class AgentSwarmMemberAgent(BaseAgent):
    """One member of a swarm: an agent with the swarm's shared prompt, tools, policy, compaction knobs, and middleware."""

    session_persistence_supported = False

    def __init__(self, swarm_runtime: AgentSwarmRuntime, member: AgentSwarmMember, *, system_prompt: str, tools: tuple[BaseTool, ...], api_keys: ProviderKeys) -> None:
        # @intent members-get-everything-they-need-to-work
        # The swarm tools need write and execute permission, so the
        # member allows every call, as CodingAgent and
        # InfiniteMemoryAgent do. Every tool result is cut, the history
        # is compacted at the trigger and trimmed before each call, so a
        # run that lasts the whole swarm fits the model; the middleware
        # trim the history, connect turns to the swarm, and report every
        # model call and tool result, in that order.
        self.swarm_runtime = swarm_runtime
        super().__init__(
            name=member.name,
            system_prompt=system_prompt,
            runtime=AgentRuntimeType.AGENT_SWARM_MEMBER,
            tools=tools,
            permission_policy=PermissionPolicy.allow_all(),
            agent_loop_settings=AgentLoopSettings(
                tool_settings=ToolSettings(result_max_chars=AGENT_SWARM_TOOL_RESULT_MAX_CHARS),
                compaction_trigger_tokens=AGENT_SWARM_COMPACTION_TRIGGER_TOKENS,
                compaction_target_tokens=AGENT_SWARM_COMPACTION_TARGET_TOKENS,
            ),
            middleware=(AgentSwarmTrimMiddleware(swarm_runtime), AgentSwarmTurnMiddleware(swarm_runtime), AgentSwarmObserverMiddleware(swarm_runtime)),
            api_keys=api_keys,
            provider=member.provider,
            model_name=member.model_name,
        )
        # The one summarizer this member compacts its history with.
        self._summarizer = AgentSwarmHandoffSummarizer(self)

    async def call_model(self, prompt: str, *, system: str, messages: Sequence[Mapping[str, Any]]) -> object:
        """Make one call on this member's own runner, outside the loop, and return the raw response."""
        runner, _ = self._runner_for_model()
        return await self._invoke_runner(runner, prompt, system=system, messages=[dict(message) for message in messages])

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # Hands the run's AgentSwarmRuntime and this member's summarizer
        # to each AgentSwarmMemberRuntime.
        return {"swarm_runtime": self.swarm_runtime, "summarizer": self._summarizer}


__all__ = ["AgentSwarmMemberAgent", "AgentSwarmMemberRuntime", "AgentSwarmMessageTool", "AgentSwarmTurnMiddleware"]
