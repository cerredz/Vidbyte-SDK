"""FILE: vidbyte/agents/agent_swarm/runtime.py

PURPOSE: Defines AgentSwarmRuntime, one swarm run: it builds a fresh agent for every member, runs them all at once until no agent is working or the time limit is reached, and owns every piece of swarm state in between: each agent's inbox, who is working, idle, or failed, the turn count, the waits of idle agents, the decided stop reason, and the replies.
ROLE IN CODEBASE: Built by AgentSwarm.arun (swarm.py) once per run over the prepared workplace. Its post_message, collect_messages, end_turn, and record_tool_call are called only by the swarm's own member parts: the message tool and the member runtime in member.py, and the turn middleware in vidbyte/middleware/builtins/agent_swarm_turn.py. It builds AgentSwarmMemberAgent (member.py) with AgentSwarmTools (vidbyte/tools/toolsets/agent_swarm.py) and records through AgentSwarmEvents (events.py). Exported by vidbyte/agents/agent_swarm/__init__.py and vidbyte/agents/__init__.py.
ARCHITECTURE NOTE: Every agent runs on one event loop, so a block of code with no await in it runs without any other agent running in between. Every state change here (queueing a message, waking an agent, ending a turn, failing, deciding the end) happens inside such a block, together with the event that records it; delivery to on_event is awaited only afterwards. That is why nothing is ever lost or doubled: a send and the recipient's turn end cannot interleave, so whichever runs first decides; a message is taken out of its inbox in the same block that records its delivery; and because a send is queued in the sender's own step, "no agent is working" also means no message is in flight, so the end of the swarm is detected exactly, with no polling. The time limit is asyncio.timeout around one TaskGroup that owns every member task.
FUNCTION INVENTORY: arun is the narrated main function of a run; _run_member is the main function of each member task; post_message, collect_messages, end_turn, and record_tool_call are the member parts' entry points; _build_member builds one agent; _drain takes an inbox and records its deliveries; _fail marks a member failed; _end_check decides the end and releases every idle agent; _failure_text and _early_exit_text word an AGENT_FAILED event.
COMMON MODIFICATION PATTERNS: A new state change goes in one synchronous block that also records its event, followed by one await of the event flush. A new end condition belongs in _end_check.
WHAT NOT TO DO IN THIS FILE: 1. Do not put an await between a state check and the change it decides. 2. Do not wait for a recipient in post_message; only the event flush may be awaited. 3. Do not poll or sleep. 4. Do not contain any member exception other than VidbyteSdkError and a CancelledError the swarm did not request, and never swallow a CancelledError: its branch in _run_member records AGENT_FAILED only when the member task's cancelling() is 0 and no stop reason is decided, and always raises it again. 5. Do not format a member's own system prompt or a message text with str.format; only the catalog templates are formatted.
KNOWN EDGE CASES: A message to an idle agent when the turn budget is spent is queued but wakes nobody, and the swarm then ends MAX_TURNS. A member whose run returns before the swarm released it has failed, with the run's own stop reason as the cause. A CancelledError the swarm did not request, raised by a tool or by an on_event callback, fails only that agent, even an idle one, and is raised again; Python 3.11's TaskGroup ignores the cancelled task, so the other agents go on and the swarm never waits out its time limit for it. On TIMEOUT every member task still running is cancelled without an AGENT_FAILED, so only a member that failed before the limit has one, and replies is empty; when the swarm had already decided to end, the decided reason stands, and an agent still unwinding at that moment may be missing from replies. An exception from this module's own code inside a member task, or a KeyboardInterrupt, is not contained and leaves arun without a result.
RELATED DOCS: docs/spec/agent-swarm/spec.md (sections 6.1, 8.1 D-4 to D-8 and D-11, and 8.5); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_lifecycle.py, tests/features/agent_swarm/test_agent_swarm_messaging.py, and tests/features/agent_swarm/test_agent_swarm_property.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

from vidbyte.agents.agent_swarm.events import AgentSwarmEvents
from vidbyte.agents.agent_swarm.member import (
    AgentSwarmMemberAgent,
    AgentSwarmMessageTool,
)
from vidbyte.agents.agent_swarm.settings import AgentSwarmSettings
from vidbyte.lib.dataclasses.agent_swarm import (
    AgentSwarmEvent,
    AgentSwarmMember,
    AgentSwarmResult,
)
from vidbyte.lib.dataclasses.agents import AgentMessage, ProviderKeys
from vidbyte.lib.dataclasses.tools import ToolStatus
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.agent_swarm import AgentSwarmEventKind, AgentSwarmStopReason
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError, VidbyteSdkError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.toolsets.agent_swarm import AgentSwarmTools


class AgentSwarmRuntime:
    """One swarm run: the agents' inboxes, turns, wakes, failures, and ending, over one shared folder."""

    def __init__(self, settings: AgentSwarmSettings, root: Path) -> None:
        # @intent one-runtime-per-run-built-without-side-effects
        # Only checked settings and an already prepared folder path are
        # accepted; building the runtime creates nothing on disk.
        if not isinstance(settings, AgentSwarmSettings) or not isinstance(root, Path):
            raise ConfigurationError(f"AgentSwarmRuntime requires an AgentSwarmSettings instance and a Path; got {type(settings).__name__} and {type(root).__name__}.", details={"received_settings": type(settings).__name__, "received_root": type(root).__name__})
        self._settings = settings
        self._root = root
        self._ran = False
        self._events = AgentSwarmEvents(settings.on_event)
        # The swarm state, changed only in blocks with no await inside.
        self._inboxes: dict[str, list[AgentSwarmEvent]] = {member.name: [] for member in settings.agents}
        self._working: set[str] = set()
        self._failed: set[str] = set()
        self._waiting: dict[str, asyncio.Future[None]] = {}
        self._turns = 0
        self._stop_reason: AgentSwarmStopReason | None = None
        self._replies: dict[str, AgentMessage] = {}
        # The catalog texts every run needs, read once.
        prompts = Prompts()
        self._texts = {prompt: prompts.get(prompt).strip() for prompt in (Prompt.AGENT_SWARM_SYSTEM_PROMPT, Prompt.AGENT_SWARM_MESSAGE_SENT, Prompt.AGENT_SWARM_MESSAGE_UNKNOWN_RECIPIENT, Prompt.AGENT_SWARM_MESSAGE_STOPPED_RECIPIENT, Prompt.AGENT_SWARM_MESSAGE_BLANK_TEXT, Prompt.AGENT_SWARM_INBOX, Prompt.AGENT_SWARM_INBOX_MESSAGE)}

    async def arun(self, goal: str) -> AgentSwarmResult:
        """Run every agent on the goal until the swarm ends, and return the stop reason, every event, and the replies."""
        # Refuse a goal that is not text, before anything else happens,
        # so a refused call leaves this runtime unused.
        RecordFieldValidator.require_text(goal, "goal")
        # @intent a-swarm-runtime-runs-once
        # All run state lives on this object, so a second run would
        # start from the first one's inboxes, turns, and events.
        if self._ran:
            raise ConfigurationError("This AgentSwarmRuntime has already run its swarm; AgentSwarm builds a fresh runtime for every arun.", details={"field": "arun"})
        self._ran = True

        # Build a fresh agent for every member, each with an empty
        # conversation, the swarm tools, and the swarm prompt.
        agents = [self._build_member(member) for member in self._settings.agents]

        # Every agent starts working: its first turn counts against the
        # budget, and its start is recorded in member order.
        for agent in agents:
            self._working.add(agent.name)
            self._events.record(AgentSwarmEventKind.AGENT_STARTED, agent.name)
        self._turns = len(agents)

        # Deliver the start events, then run every agent at once, each
        # in its own task, until the end check releases them all. The
        # time limit cancels whatever is still running, including a slow
        # delivery of the start events.
        try:
            async with asyncio.timeout(self._settings.timeout_seconds), asyncio.TaskGroup() as group:
                await self._events.flush()
                for agent in agents:
                    group.create_task(self._run_member(agent, goal))
        except TimeoutError:
            # The time limit wins only when the swarm had not already
            # decided to end.
            self._stop_reason = self._stop_reason or AgentSwarmStopReason.TIMEOUT
        stop_reason = self._stop_reason or AgentSwarmStopReason.TIMEOUT

        # Record the end and deliver every event not delivered yet,
        # including the end itself, before returning.
        self._events.record(AgentSwarmEventKind.SWARM_ENDED, "", stop_reason=stop_reason)
        await self._events.flush()

        # The replies are each released agent's last reply, in member
        # order; a failed or cancelled agent has none.
        replies = tuple(self._replies[member.name] for member in self._settings.agents if member.name in self._replies)
        return AgentSwarmResult(stop_reason=stop_reason, events=self._events.events, replies=replies, event_error_types=self._events.error_types)

    async def _run_member(self, agent: AgentSwarmMemberAgent, goal: str) -> None:
        # @intent one-failing-agent-never-stops-the-others
        # Each agent runs one long run for the whole swarm. An SDK error
        # (BaseAgent wraps every model, turn-end, and delivery error in
        # one, with the original as its cause), a cancel the swarm did
        # not ask for, or a run that returns before the swarm released
        # it removes only this agent; anything else passes through.
        name = agent.name
        try:
            reply = await agent.arun(goal)
        except VidbyteSdkError as error:
            text = self._failure_text(error)
        except asyncio.CancelledError as cancel:
            # @intent a-stray-cancel-fails-its-agent-and-is-raised-again
            # The task group ignores a cancelled task, so an agent whose
            # tool or on_event callback raised CancelledError would stay
            # counted as working until the time limit. The swarm's own
            # cancels (the time limit, the caller) leave cancelling()
            # above zero and are only raised again, and so is a cancel
            # that comes after the swarm decided to end. The failure is
            # marked before anything awaits, so no send can wake the
            # agent first.
            task = asyncio.current_task()
            if task is not None and task.cancelling() == 0 and self._stop_reason is None:
                detail = str(cancel).strip() or "the run was cancelled, but not by the swarm"
                self._fail(name, f"CancelledError: {detail}")
                self._end_check()
            raise
        else:
            # A run that returns after the swarm released it ends
            # normally, and its reply is the agent's last turn's reply.
            if name not in self._working:
                self._replies[name] = reply
                return
            text = self._early_exit_text(reply)

        # The agent leaves the swarm: no further message is accepted for
        # it, and the end check runs, because it may have been the last
        # agent working.
        self._fail(name, text)
        self._end_check()
        await self._events.flush()

    async def post_message(self, sender: str, recipient: object, text: object) -> str:
        """Queue one message for another agent and wake it when it is idle and turns remain; never waits for the recipient."""
        # @intent a-send-is-decided-and-queued-in-one-step
        # Everything from the checks to the wake runs with no await, so
        # the recipient cannot end its turn or go idle in between:
        # either it is still working and collects the message at its
        # next tool iteration or turn end, or it is idle and this send
        # wakes it. Either way the message is delivered once, or it
        # stays queued only when no turn is left to wake it with.
        peers = [member.name for member in self._settings.agents if member.name != sender]
        if not isinstance(text, str) or not text.strip():
            raise ToolExecutionError(self._texts[Prompt.AGENT_SWARM_MESSAGE_BLANK_TEXT])
        if not isinstance(recipient, str) or recipient not in peers:
            raise ToolExecutionError(self._texts[Prompt.AGENT_SWARM_MESSAGE_UNKNOWN_RECIPIENT].format(recipient=recipient, agents=", ".join(peers)))
        if recipient in self._failed:
            raise ToolExecutionError(self._texts[Prompt.AGENT_SWARM_MESSAGE_STOPPED_RECIPIENT].format(recipient=recipient))

        # Queue the message as its own MESSAGE_SENT event, which carries
        # its id, sender, and text.
        self._inboxes[recipient].append(self._events.record(AgentSwarmEventKind.MESSAGE_SENT, sender, peer=recipient, text=text))

        # Wake an idle recipient now, counting its new turn, so the wake
        # is never lost between this send and the recipient's wait.
        if recipient in self._waiting and self._turns < self._settings.max_turns:
            self._turns += 1
            self._working.add(recipient)
            self._events.record(AgentSwarmEventKind.AGENT_WOKE, recipient)
            self._waiting.pop(recipient).set_result(None)

        # Deliver the events; this is the only thing a send waits for.
        await self._events.flush()
        return self._texts[Prompt.AGENT_SWARM_MESSAGE_SENT].format(recipient=recipient)

    async def collect_messages(self, name: str) -> str:
        """Return every message waiting for a working agent as one user message, or "" when none wait."""
        if not self._inboxes[name]:
            return ""
        text = self._drain(name)
        await self._events.flush()
        return text

    async def end_turn(self, name: str, reply: str) -> str:
        """End an agent's turn: return its next turn's messages, at once or when a message wakes it, or "" when the swarm ends."""
        # @intent a-turn-end-is-decided-in-one-step
        # The idle mark and the inbox check run with no await between
        # them, so a message accepted before this point is found here
        # and one accepted after it finds the agent idle and wakes it;
        # no message can arrive in a gap and sit unseen.
        self._events.record(AgentSwarmEventKind.AGENT_IDLE, name, text=reply)
        if self._inboxes[name] and self._turns < self._settings.max_turns:
            # Mail is already waiting and a turn is left: start the next
            # turn at once with it.
            self._turns += 1
            self._events.record(AgentSwarmEventKind.AGENT_WOKE, name)
            text = self._drain(name)
            await self._events.flush()
            return text

        # Otherwise wait idle. The end check runs now, because this may
        # have been the last agent working.
        self._working.discard(name)
        wake = asyncio.get_running_loop().create_future()
        self._waiting[name] = wake
        self._end_check()
        await self._events.flush()
        await wake

        # A send marks the agent working before it resolves the wait;
        # the end of the swarm resolves it without doing so.
        if name not in self._working:
            return ""
        text = self._drain(name)
        await self._events.flush()
        return text

    async def record_tool_call(self, name: str, tool_name: str, status: ToolStatus) -> None:
        """Record one TOOL_CALLED event for an agent's tool call and deliver it."""
        self._events.record(AgentSwarmEventKind.TOOL_CALLED, name, tool_name=tool_name, tool_status=status)
        await self._events.flush()

    def _build_member(self, member: AgentSwarmMember) -> AgentSwarmMemberAgent:
        # The member's own prompt comes first, unformatted, then the
        # swarm prompt naming it and its peers. Its tools are the swarm
        # catalog, then message, then the developer's search tool.
        peers = tuple(other.name for other in self._settings.agents if other.name != member.name)
        swarm_prompt = self._texts[Prompt.AGENT_SWARM_SYSTEM_PROMPT].format(name=member.name, agents=", ".join(peers))
        search = (self._settings.search_tool,) if self._settings.search_tool is not None else ()
        tools = (*AgentSwarmTools(self._root).all(), AgentSwarmMessageTool(self, member.name, peers), *search)
        # The settings matched the keys at construction, so api_keys is
        # the matched record.
        return AgentSwarmMemberAgent(self, member, system_prompt=f"{member.system_prompt}\n\n{swarm_prompt}", tools=tools, api_keys=cast("ProviderKeys", self._settings.api_keys))

    def _drain(self, name: str) -> str:
        # Take every waiting message out of the inbox and record its
        # delivery in the same step, so none is delivered twice; render
        # them, oldest first and each labeled with its sender, as one
        # user message. Message text is a format value, never a
        # template.
        messages, self._inboxes[name] = self._inboxes[name], []
        for sent in messages:
            self._events.record(AgentSwarmEventKind.MESSAGE_DELIVERED, name, peer=sent.agent, message_id=sent.message_id)
        blocks = "\n\n".join(self._texts[Prompt.AGENT_SWARM_INBOX_MESSAGE].format(sender=sent.agent, text=sent.text) for sent in messages)
        return self._texts[Prompt.AGENT_SWARM_INBOX].format(messages=blocks)

    def _fail(self, name: str, text: str) -> None:
        # The agent leaves the swarm and its failure is recorded; its
        # queued messages stay undelivered.
        self._working.discard(name)
        self._failed.add(name)
        self._events.record(AgentSwarmEventKind.AGENT_FAILED, name, text=text)

    def _end_check(self) -> None:
        # @intent the-swarm-ends-exactly-when-nobody-works
        # Sends are queued by working agents in their own step, so once
        # no agent is working no message is in flight and none can
        # arrive. The reason is FAILED when everyone failed, MAX_TURNS
        # when a running agent still holds mail the budget could not
        # wake it for, and QUIET otherwise; every idle agent is
        # released.
        if self._working or self._stop_reason is not None:
            return
        running = [member.name for member in self._settings.agents if member.name not in self._failed]
        if not running:
            self._stop_reason = AgentSwarmStopReason.FAILED
        elif any(self._inboxes[name] for name in running):
            self._stop_reason = AgentSwarmStopReason.MAX_TURNS
        else:
            self._stop_reason = AgentSwarmStopReason.QUIET
        for wake in self._waiting.values():
            wake.set_result(None)
        self._waiting.clear()

    @staticmethod
    def _failure_text(error: VidbyteSdkError) -> str:
        # BaseAgent wraps the real failure, such as the provider's
        # error, as the cause of a generic one, so the cause names the
        # problem.
        cause = error.__cause__ if error.__cause__ is not None else error
        detail = str(cause).strip()
        return f"{type(cause).__name__}: {detail}" if detail else type(cause).__name__

    @staticmethod
    def _early_exit_text(reply: AgentMessage) -> str:
        # A run that returned on its own, such as a middleware abort,
        # names its stop reason.
        return f"The agent's run ended before the swarm released it, with stop reason {reply.metadata.get('stop_reason') or 'unknown'}."


__all__ = ["AgentSwarmRuntime"]
