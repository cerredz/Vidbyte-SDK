"""FILE: vidbyte/agents/agent_swarm/runtime.py

PURPOSE: Defines AgentSwarmRuntime, one swarm run: it builds a fresh agent for every member, runs them all at once until no agent is working, the token budget is spent, or the time limit is reached, and owns every piece of swarm state in between: each agent's inbox, who is working, idle, or out, the turn and token counts, the waits of idle agents, each agent's measured context and pending compaction request, each file's last writer, the decided stop reason, and the replies.
ROLE IN CODEBASE: Built by AgentSwarm.arun (swarm.py) once per run over the prepared workplace. Its entry points are called only by the swarm's own member parts: post_message by the message tool and collect_messages, take_compaction_request, last_prompt_tokens, and record_compaction by the member runtime (member.py); request_compaction by the compact tool (compaction.py); end_turn and record_tool_call by the turn middleware (vidbyte/middleware/builtins/agent_swarm_turn.py); stopping, record_model_call, record_model_error, record_tool_outcome, and record_history_trim by the observer and trim middleware (vidbyte/middleware/builtins/agent_swarm_observer.py); the member runtime also reads stopping before it compacts, and calls record_model_call and record_model_error for its summary call. It builds AgentSwarmMemberAgent (member.py) with AgentSwarmTools (vidbyte/tools/toolsets/agent_swarm.py) and records through AgentSwarmEvents (events.py). Exported by vidbyte/agents/agent_swarm/__init__.py and vidbyte/agents/__init__.py.
ARCHITECTURE NOTE: Every agent runs on one event loop, so a block of code with no await in it runs without any other agent running in between. Every state change here (queueing a message, waking an agent, ending a turn, removing an agent, counting tokens, deciding the stop) happens inside such a block, together with the events that record it; delivery to on_event is awaited only afterwards. That is why nothing is ever lost or doubled: a send and the recipient's turn end cannot interleave, so whichever runs first decides; a message leaves its inbox in the same block that records its delivery or its undelivery; and because a send is queued in the sender's own step, "no agent is working" also means no message is in flight, so the end of the swarm is detected exactly, with no polling. The stop reason is set in one place, _stop, which in the same block marks every queued message undelivered and releases every idle agent; from then on the observer middleware refuses every further model call. The time limit is asyncio.timeout around one TaskGroup that owns every member task.
FUNCTION INVENTORY: arun is the narrated main function of a run; _run_member is the main function of each member task; post_message and end_turn are the narrated main functions of a send and of a turn end; collect_messages, record_tool_call, record_tool_outcome, record_model_call, record_model_error, record_history_trim, request_compaction, take_compaction_request, last_prompt_tokens, record_compaction, and stopping are the member parts' other entry points. Helpers: _render_system_prompt renders the shared sections for one member; _build_member builds one agent; _refuse records and raises one refused send; _drain takes an inbox and records its deliveries; _fail removes a member and marks its mail undelivered; _stop records the decided stop reason; _end_reason decides the end reason once nobody works, and its caller passes it to _stop; _changed_path and _command_failure classify one tool result (the file it changed, the command failure it reports); _failure_text, _early_exit_text, and _budget_total only read their arguments.
COMMON MODIFICATION PATTERNS: A new state change goes in one synchronous block that also records its event, followed by one await of the event flush. A new end condition belongs in _end_reason, and every stop goes through _stop. A new observation adds one record_* entry point here and one hook in the observer middleware.
WHAT NOT TO DO IN THIS FILE: 1. Do not put an await between a state check and the change it decides. 2. Do not wait for a recipient in post_message; only the event flush may be awaited. 3. Do not poll or sleep. 4. Do not contain any member exception other than VidbyteSdkError and a CancelledError, and never swallow a CancelledError: its branch in _run_member records without flushing and always raises it again. 5. Do not format a message text or a focus with str.format; only the catalog templates are formatted. 6. Do not set the stop reason anywhere but _stop.
KNOWN EDGE CASES: A message to an idle agent when the turn budget is spent is queued with one wake_refused and wakes nobody, and the swarm then ends MAX_TURNS and marks it undelivered. A message to an agent that failed or exited, or any message sent once the stop is decided, is a success that says the recipient stopped, recorded as sent and then undelivered. A run that returns before the stop is decided has exited, named by the loop's own stop reason (middleware_abort for a recording bug); one that returns after the decision is released. A CancelledError the swarm did not request, raised by a tool or by an on_event callback, fails only that agent, even an idle one, and is raised again; Python 3.11's TaskGroup ignores the cancelled task, so the other agents go on. On TIMEOUT each member task still running records agent_cancelled, working or idle, without flushing, and _stop records the same for members whose task never ran, so replies is empty; the final flush delivers them; when the swarm had already decided to stop, the decided reason stands. The token budget counts total_tokens, else input plus output, missing values as zero, so a provider that reports no usage never reaches it; a call already in flight at the decision still returns and is counted. Each member's run is told its own provider, so the loop reads its tool calls in that provider's shape even when the runner object does not name it. An exception from this module's own code inside a member task, or a KeyboardInterrupt, is not contained and leaves arun without a result.
RELATED DOCS: docs/spec/agent-swarm-v2/spec.md (sections 6.1 INV-1 to INV-17, 8.1 D-4 to D-6, D-13 and D-14, 8.5 and 9.1); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_lifecycle.py, tests/features/agent_swarm/test_agent_swarm_messaging.py, tests/features/agent_swarm/test_agent_swarm_stop.py, tests/features/agent_swarm/test_agent_swarm_observer.py, tests/features/agent_swarm/test_agent_swarm_compaction.py and tests/features/agent_swarm/test_agent_swarm_property.py
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import NoReturn, cast

from vidbyte.agents.agent_swarm.compaction import AgentSwarmCompactTool
from vidbyte.agents.agent_swarm.events import AgentSwarmEvents
from vidbyte.agents.agent_swarm.member import (
    AgentSwarmMemberAgent,
    AgentSwarmMessageTool,
)
from vidbyte.lib.constants.agent_swarm import (
    AGENT_SWARM_FILE_TOOL_PATH_ARGUMENTS,
    AGENT_SWARM_SHELL_TIME_LIMIT_ERROR,
    AGENT_SWARM_SHELL_TOOL_NAME,
    AGENT_SWARM_TOOL_RESULT_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agent_swarm import (
    AgentSwarmEvent,
    AgentSwarmMember,
    AgentSwarmResult,
    AgentSwarmSettings,
)
from vidbyte.lib.dataclasses.agents import AgentMessage, ProviderKeys
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult, ToolStatus
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.agent_swarm import (
    AgentSwarmAgentState,
    AgentSwarmCompactionTrigger,
    AgentSwarmEventKind,
    AgentSwarmFolderState,
    AgentSwarmStopReason,
    AgentSwarmWebSearch,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError, VidbyteSdkError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.toolsets.agent_swarm import AgentSwarmTools

# The shared system prompt's sections in order (web search only when a
# search tool is selected), and the other catalog texts a run reads.
_SECTIONS = (Prompt.AGENT_SWARM_SYSTEM_ENVIRONMENT, Prompt.AGENT_SWARM_SYSTEM_TOOLS, Prompt.AGENT_SWARM_SYSTEM_WEB_SEARCH, Prompt.AGENT_SWARM_SYSTEM_MESSAGING, Prompt.AGENT_SWARM_SYSTEM_TURNS, Prompt.AGENT_SWARM_SYSTEM_GOAL, Prompt.AGENT_SWARM_SYSTEM_INSTRUCTIONS, Prompt.AGENT_SWARM_SYSTEM_OBJECTIVE, Prompt.AGENT_SWARM_SYSTEM_THOROUGHNESS)
_REPLIES = (Prompt.AGENT_SWARM_MESSAGE_SENT, Prompt.AGENT_SWARM_MESSAGE_UNKNOWN_RECIPIENT, Prompt.AGENT_SWARM_MESSAGE_STOPPED_RECIPIENT, Prompt.AGENT_SWARM_MESSAGE_BLANK_TEXT, Prompt.AGENT_SWARM_INBOX, Prompt.AGENT_SWARM_INBOX_MESSAGE, Prompt.AGENT_SWARM_COMPACT_REQUESTED)


class AgentSwarmRuntime:
    """One swarm run: the agents' inboxes, turns, wakes, token budget, compaction requests, failures, and stop, over one shared folder."""

    def __init__(self, settings: AgentSwarmSettings, root: Path, *, workplace_created: bool) -> None:
        # @intent one-runtime-per-run-built-without-side-effects
        # Only checked settings and an already prepared folder path are
        # accepted; building the runtime creates nothing on disk.
        if not isinstance(settings, AgentSwarmSettings) or not isinstance(root, Path):
            raise ConfigurationError(f"AgentSwarmRuntime requires an AgentSwarmSettings instance and a Path; got {type(settings).__name__} and {type(root).__name__}.", details={"received_settings": type(settings).__name__, "received_root": type(root).__name__})
        self._settings = settings
        self._root = root
        self._workplace_created = workplace_created
        self._names = tuple(member.name for member in settings.agents)
        self._ran = False
        self._events = AgentSwarmEvents(settings.on_event)
        # The swarm state, changed only in blocks with no await inside.
        self._inboxes: dict[str, list[AgentSwarmEvent]] = {name: [] for name in self._names}
        self._working: set[str] = set()
        self._failed: set[str] = set()
        self._waiting: dict[str, asyncio.Future[None]] = {}
        self._turns = 0
        self._tokens_used = 0
        self._stop_reason: AgentSwarmStopReason | None = None
        self._replies: dict[str, AgentMessage] = {}
        self._last_prompt_tokens: dict[str, int | None] = {}
        self._last_writer: dict[str, str] = {}
        self._compaction_requests: dict[str, str] = {}
        # One search tool for every agent, built once around the
        # developer's key.
        self._search_tool: BaseTool | None = None
        if settings.web_search is not None:
            self._search_tool = AgentSwarmTools.search_tool_for(AgentSwarmWebSearch(settings.web_search), str(settings.web_search_api_key))
        prompts = Prompts()
        self._texts = {prompt: prompts.get(prompt).strip() for prompt in (*_SECTIONS, *_REPLIES)}

    async def arun(self, goal: str) -> AgentSwarmResult:
        """Run every agent on the goal until the swarm stops, and return the stop reason, every event, and the replies."""
        # Refuse a goal that is not text before anything happens, so a
        # refused call leaves this runtime unused.
        RecordFieldValidator.require_text(goal, "goal")
        # @intent a-swarm-runtime-runs-once
        # All run state lives on this object, so a second run would
        # start from the first one's inboxes, turns, and events.
        if self._ran:
            raise ConfigurationError("This AgentSwarmRuntime has already run its swarm; AgentSwarm builds a fresh runtime for every arun.", details={"field": "arun"})
        self._ran = True
        # Start the event clock now, so every event's time counts from
        # the start of the run.
        self._events = AgentSwarmEvents(self._settings.on_event)

        # Record the shared folder first, and whether this run
        # created it.
        folder_state = AgentSwarmFolderState.CREATED if self._workplace_created else AgentSwarmFolderState.EXISTED
        self._events.record(AgentSwarmEventKind.WORKPLACE_PREPARED, "", path=str(self._root), folder_state=folder_state)
        # Build a fresh agent for every member, with an empty history,
        # the swarm tools, and the shared prompt rendered for it.
        agents: list[AgentSwarmMemberAgent] = []
        for member in self._settings.agents:
            agents.append(self._build_member(member, self._render_system_prompt(member.name)))
            self._events.record(AgentSwarmEventKind.AGENT_CREATED, member.name)
        # Every agent starts working: its first turn counts against the
        # budget, and its start is recorded in member order.
        for agent in agents:
            self._working.add(agent.name)
            self._events.record(AgentSwarmEventKind.AGENT_STARTED, agent.name)
        self._turns = len(agents)
        # Deliver the start events, then run every agent in its own task
        # until every task has ended. The time limit cancels whatever is
        # still running, even a slow delivery of the start events.
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(self._settings.timeout_seconds), asyncio.TaskGroup() as group:
                await self._events.flush()
                for agent in agents:
                    group.create_task(self._run_member(agent, goal))
        # The time limit decides the stop only when nothing decided
        # it before.
        if self._stop_reason is None:
            self._stop(AgentSwarmStopReason.TIMEOUT)
        stop_reason = self._stop_reason or AgentSwarmStopReason.TIMEOUT
        # Record the end and deliver every event not delivered yet, the
        # end included.
        self._events.record(AgentSwarmEventKind.SWARM_ENDED, "", stop_reason=stop_reason)
        await self._events.flush()
        # The replies are each released agent's last reply, in member
        # order; a failed, exited, or cancelled agent has none.
        replies = tuple(self._replies[name] for name in self._names if name in self._replies)
        return AgentSwarmResult(stop_reason=stop_reason, events=self._events.events, replies=replies, event_error_types=self._events.error_types)

    async def _run_member(self, agent: AgentSwarmMemberAgent, goal: str) -> None:
        # @intent one-failing-agent-never-stops-the-others
        # One long run per agent, ending in exactly one terminal event.
        # An SDK error (BaseAgent wraps every model, turn-end, and
        # delivery error, with the original as its cause), a cancel the
        # swarm did not ask for, or a run that returns before the stop
        # removes only this agent; anything else passes through.
        name = agent.name
        try:
            # The run is told the member's provider, so the loop reads
            # its tool calls in that provider's shape.
            reply = await agent.arun(goal, provider=agent.runner_config.provider)
        except VidbyteSdkError as error:
            self._fail(name, AgentSwarmEventKind.AGENT_FAILED, self._failure_text(error))
        except asyncio.CancelledError as cancel:
            # @intent a-stray-cancel-fails-its-agent-and-is-raised-again
            # The task group ignores a cancelled task, so a tool or
            # callback that raised CancelledError would leave the agent
            # counted as working until the time limit; that cancel fails
            # the agent. The swarm's own cancels leave cancelling()
            # above zero; they, and a cancel after the stop, only record
            # agent_cancelled without flushing, because the task is
            # being torn down and the last flush delivers it.
            task = asyncio.current_task()
            if task is not None and task.cancelling() == 0 and self._stop_reason is None:
                detail = str(cancel).strip() or "the run was cancelled, but not by the swarm"
                self._fail(name, AgentSwarmEventKind.AGENT_FAILED, f"CancelledError: {detail}")
                reason = self._end_reason()
                if reason is not None:
                    self._stop(reason)
            else:
                state = AgentSwarmAgentState.WORKING if name in self._working else AgentSwarmAgentState.IDLE
                self._working.discard(name)
                self._waiting.pop(name, None)
                self._events.record(AgentSwarmEventKind.AGENT_CANCELLED, name, agent_state=state)
            raise
        else:
            # A run that returns once the agent was released or the stop
            # was decided ends normally, and its reply is kept.
            if name not in self._working or self._stop_reason is not None:
                self._working.discard(name)
                self._replies[name] = reply
                self._events.record(AgentSwarmEventKind.AGENT_RELEASED, name)
                await self._events.flush()
                return
            self._fail(name, AgentSwarmEventKind.AGENT_EXITED, self._early_exit_text(reply))
        # The agent has left the swarm, and it may have been the last
        # one working.
        reason = self._end_reason()
        if reason is not None:
            self._stop(reason)
        await self._events.flush()

    async def post_message(self, sender: str, recipient: object, text: object) -> str:
        """Queue one message for any agent and wake it when it is idle and turns remain; never waits for the recipient."""
        # @intent a-send-is-decided-and-queued-in-one-step
        # Everything from the checks to the wake runs with no await, so
        # the recipient cannot end its turn in between: either it is
        # working and collects the message later, or it is idle and this
        # send wakes it, or refuses the wake when no turn is left.
        # First refuse text that is not a non-blank string, then a name
        # that is no agent of this swarm; nothing is queued then.
        peer = "" if recipient is None else str(recipient)
        if not isinstance(text, str) or not text.strip():
            await self._refuse(sender, peer, self._texts[Prompt.AGENT_SWARM_MESSAGE_BLANK_TEXT])
        if not isinstance(recipient, str) or recipient not in self._inboxes:
            await self._refuse(sender, peer, self._texts[Prompt.AGENT_SWARM_MESSAGE_UNKNOWN_RECIPIENT].format(recipient=str(recipient), agents=", ".join(self._names)))
        # Record the message as its own MESSAGE_SENT event, which
        # carries its id, sender, and text.
        sent = self._events.record(AgentSwarmEventKind.MESSAGE_SENT, sender, peer=recipient, text=text)
        # An agent that has left, or any agent once the swarm is
        # stopping, never receives it: it is undelivered at once, and
        # the sender is told so as a success.
        if recipient in self._failed or self._stop_reason is not None:
            self._events.record(AgentSwarmEventKind.MESSAGE_UNDELIVERED, recipient, peer=sender, message_id=sent.message_id)
            await self._events.flush()
            return self._texts[Prompt.AGENT_SWARM_MESSAGE_STOPPED_RECIPIENT].format(recipient=recipient)
        # Queue it, and wake an idle recipient now, counting its new
        # turn, so the wake is never lost; with no turn left, refuse
        # the wake.
        self._inboxes[recipient].append(sent)
        if recipient in self._waiting:
            if self._turns < self._settings.max_turns:
                self._turns += 1
                self._working.add(recipient)
                self._events.record(AgentSwarmEventKind.AGENT_WOKE, recipient)
                self._waiting.pop(recipient).set_result(None)
            else:
                self._events.record(AgentSwarmEventKind.WAKE_REFUSED, recipient, peer=sender, message_id=sent.message_id)
        # Deliver the events; this is the only thing a send waits for.
        await self._events.flush()
        return self._texts[Prompt.AGENT_SWARM_MESSAGE_SENT].format(recipient=recipient)

    async def collect_messages(self, name: str) -> str:
        """Return every message waiting for a working agent as one user message, or "" when none wait or the swarm is stopping."""
        if self._stop_reason is not None or not self._inboxes[name]:
            return ""
        text = self._drain(name)
        await self._events.flush()
        return text

    async def end_turn(self, name: str, reply: str) -> str:
        """End an agent's turn: return its next turn's messages, at once or when a message wakes it, or "" when the swarm stops."""
        # @intent a-turn-end-is-decided-in-one-step
        # The idle mark and the inbox check run with no await between
        # them, so a message accepted before is found here and one
        # accepted after finds the agent idle and wakes it; none can
        # sit unseen.
        self._events.record(AgentSwarmEventKind.AGENT_IDLE, name, text=reply)
        # Once the stop is decided no turn starts: the run returns, and
        # the agent is released.
        if self._stop_reason is not None:
            self._working.discard(name)
            await self._events.flush()
            return ""
        # Mail is already waiting and a turn is left: start the next
        # turn at once with it.
        if self._inboxes[name] and self._turns < self._settings.max_turns:
            self._turns += 1
            self._events.record(AgentSwarmEventKind.AGENT_WOKE, name)
            text = self._drain(name)
            await self._events.flush()
            return text
        # Otherwise wait idle, refusing one wake per message that no
        # turn is left for; the end check runs, as this may be the last
        # agent working.
        for sent in self._inboxes[name]:
            self._events.record(AgentSwarmEventKind.WAKE_REFUSED, name, peer=sent.agent, message_id=sent.message_id)
        self._working.discard(name)
        wake = asyncio.get_running_loop().create_future()
        self._waiting[name] = wake
        reason = self._end_reason()
        if reason is not None:
            self._stop(reason)
        await self._events.flush()
        await wake
        # A send marks the agent working before it resolves the wait;
        # the stop resolves it without doing so.
        if self._stop_reason is not None or name not in self._working:
            self._working.discard(name)
            return ""
        text = self._drain(name)
        await self._events.flush()
        return text

    async def record_tool_call(self, name: str, tool_name: str, status: ToolStatus) -> None:
        """Record one TOOL_CALLED event for an agent's tool call and deliver it."""
        self._events.record(AgentSwarmEventKind.TOOL_CALLED, name, tool_name=tool_name, tool_status=status)
        await self._events.flush()

    async def record_tool_outcome(self, name: str, call: ToolCall, result: ToolResult) -> None:
        """Record what one raw tool result shows beyond its status: a cut result, a changed file, or a failed command."""
        # The model sees at most the cap, so the exact count it lost
        # is recorded.
        omitted = len(result.output) - AGENT_SWARM_TOOL_RESULT_MAX_CHARS
        if omitted > 0:
            self._events.record(AgentSwarmEventKind.TOOL_RESULT_TRUNCATED, name, tool_name=call.tool_name, omitted_chars=omitted)
        # A successful write_text or patch_file names the file's
        # absolute path, and the previous writer when another agent
        # wrote it last.
        path = self._changed_path(call, result)
        if path is not None:
            previous = self._last_writer.get(path, "")
            self._events.record(AgentSwarmEventKind.FILE_CHANGED, name, path=path, peer=previous if previous != name else "")
            self._last_writer[path] = name
        # A bash command stopped at its time limit, or one that
        # exited non-zero.
        failure = self._command_failure(call, result)
        if failure is not None:
            self._events.record(AgentSwarmEventKind.COMMAND_FAILED, name, text=failure)
        await self._events.flush()

    async def record_model_call(self, name: str, usage: object | None, model_calls: int) -> None:
        """Record one model call's usage, count it against the token budget, and decide max_tokens when the budget is reached."""
        # @intent the-budget-is-decided-in-the-call-that-spends-it
        # The call is recorded with its billed input, output, and cached
        # input (zeros when unreported), and the stop is decided in the
        # same step, so no agent can start a paid call between the call
        # that spent the budget and the decision.
        self._events.record(AgentSwarmEventKind.MODEL_CALLED, name, input_tokens=int(getattr(usage, "input_tokens", None) or 0), output_tokens=int(getattr(usage, "output_tokens", None) or 0), cached_tokens=int(getattr(usage, "cached_input_tokens", None) or 0), model_calls=model_calls)
        # Every prompt token the provider counted, cached or fresh, is
        # this agent's measured context for its next compaction check.
        prompt_tokens = getattr(usage, "total_prompt_tokens", None)
        if isinstance(prompt_tokens, int):
            self._last_prompt_tokens[name] = prompt_tokens
        self._tokens_used += self._budget_total(usage)
        if self._stop_reason is None and self._tokens_used >= self._settings.max_tokens:
            self._stop(AgentSwarmStopReason.MAX_TOKENS)
        await self._events.flush()

    async def record_model_error(self, name: str, error: BaseException) -> None:
        """Record one failed model attempt as "<Type>: <message>"."""
        self._events.record(AgentSwarmEventKind.MODEL_ERROR, name, text=f"{type(error).__name__}: {error}")
        await self._events.flush()

    async def record_history_trim(self, name: str, messages_dropped: int) -> None:
        """Record how many messages the trim left out of one model call."""
        self._events.record(AgentSwarmEventKind.HISTORY_TRIMMED, name, messages_dropped=messages_dropped)
        await self._events.flush()

    async def request_compaction(self, name: str, focus: object) -> str:
        """Keep one pending compaction request for an agent, replacing an earlier one's focus, and return the compact tool's reply."""
        # @intent one-pending-compaction-per-agent
        # A later request replaces the earlier one's focus.
        self._compaction_requests[name] = focus.strip() if isinstance(focus, str) else ""
        await self._events.flush()
        return self._texts[Prompt.AGENT_SWARM_COMPACT_REQUESTED]

    def take_compaction_request(self, name: str) -> str | None:
        """Remove and return an agent's pending focus ("" without one), or None when no request is pending."""
        # @intent one-pending-compaction-per-agent
        # Taking the request clears it, so it compacts one iteration.
        return self._compaction_requests.pop(name, None)

    def last_prompt_tokens(self, name: str) -> int | None:
        """Return the last full prompt size the provider reported for an agent, or None when it reported none."""
        return self._last_prompt_tokens.get(name)

    async def record_compaction(self, name: str, trigger: AgentSwarmCompactionTrigger, focus: str, input_tokens: int, messages_dropped: int) -> None:
        """Record one rewrite of an agent's history: why, with what focus, at what measured context, and how many messages it summarized."""
        self._events.record(AgentSwarmEventKind.COMPACTION, name, compaction_trigger=trigger, text=focus, input_tokens=input_tokens, messages_dropped=messages_dropped)
        await self._events.flush()

    @property
    def stopping(self) -> bool:
        """Return True once the stop reason is decided."""
        return self._stop_reason is not None

    def _render_system_prompt(self, name: str) -> str:
        # The sections joined by one blank line, rendered with only the
        # agent's name, its peers, the workplace, and the search tool's
        # name; values are never parsed as templates.
        search_tool = self._search_tool.name if self._search_tool is not None else ""
        values = {"name": name, "peers": ", ".join(other for other in self._names if other != name), "workplace": str(self._root), "search_tool": search_tool}
        sections = [section for section in _SECTIONS if self._search_tool is not None or section is not Prompt.AGENT_SWARM_SYSTEM_WEB_SEARCH]
        return "\n\n".join(self._texts[section].format(**values) for section in sections)

    def _build_member(self, member: AgentSwarmMember, system_prompt: str) -> AgentSwarmMemberAgent:
        # The five workplace tools, message, compact, then the search
        # tool; the loop adds isDone last. The settings matched the
        # keys, so api_keys is the matched record.
        search = (self._search_tool,) if self._search_tool is not None else ()
        tools = (*AgentSwarmTools(self._root).all(), AgentSwarmMessageTool(self, member.name, self._names), AgentSwarmCompactTool(self, member.name), *search)
        return AgentSwarmMemberAgent(self, member, system_prompt=system_prompt, tools=tools, api_keys=cast("ProviderKeys", self._settings.api_keys))

    async def _refuse(self, sender: str, peer: str, reason: str) -> NoReturn:
        # A refused send is recorded with the attempted name as text and
        # reaches the model as a tool error it can act on.
        self._events.record(AgentSwarmEventKind.MESSAGE_REFUSED, sender, peer=peer, text=reason)
        await self._events.flush()
        raise ToolExecutionError(reason)

    def _drain(self, name: str) -> str:
        # Take every waiting message out and record its delivery in the
        # same step, so none is delivered twice; render them oldest
        # first, each labeled with its sender, as one user message whose
        # texts are values, never templates.
        messages, self._inboxes[name] = self._inboxes[name], []
        for sent in messages:
            self._events.record(AgentSwarmEventKind.MESSAGE_DELIVERED, name, peer=sent.agent, message_id=sent.message_id)
        blocks = "\n\n".join(self._texts[Prompt.AGENT_SWARM_INBOX_MESSAGE].format(sender=sent.agent, text=sent.text) for sent in messages)
        return self._texts[Prompt.AGENT_SWARM_INBOX].format(messages=blocks)

    def _fail(self, name: str, kind: AgentSwarmEventKind, text: str) -> None:
        # The agent leaves with its failure or exit recorded, and every
        # message waiting for it is marked undelivered in the same step.
        self._working.discard(name)
        self._failed.add(name)
        self._waiting.pop(name, None)
        self._events.record(kind, name, text=text)
        for sent in self._inboxes[name]:
            self._events.record(AgentSwarmEventKind.MESSAGE_UNDELIVERED, name, peer=sent.agent, message_id=sent.message_id)
        self._inboxes[name] = []

    def _stop(self, reason: AgentSwarmStopReason) -> None:
        # @intent the-stop-is-decided-once-in-one-step
        # On the time limit a member still counted as working never ran
        # a cancel branch of its own (its task never started), so it is
        # cancelled here. Then the decision is recorded, every queued
        # message is marked undelivered in member order, and every idle
        # agent is released, so its turn end returns "".
        self._stop_reason = reason
        if reason is AgentSwarmStopReason.TIMEOUT:
            for name in self._names:
                if name in self._working:
                    self._working.discard(name)
                    self._events.record(AgentSwarmEventKind.AGENT_CANCELLED, name, agent_state=AgentSwarmAgentState.WORKING)
        self._events.record(AgentSwarmEventKind.SWARM_STOPPING, "", stop_reason=reason)
        for name in self._names:
            for sent in self._inboxes[name]:
                self._events.record(AgentSwarmEventKind.MESSAGE_UNDELIVERED, name, peer=sent.agent, message_id=sent.message_id)
            self._inboxes[name] = []
        for wake in self._waiting.values():
            if not wake.done():
                wake.set_result(None)
        self._waiting.clear()

    def _end_reason(self) -> AgentSwarmStopReason | None:
        # @intent the-swarm-ends-exactly-when-nobody-works
        # Sends are queued by working agents in their own step, so once
        # nobody works no message is in flight. The reason is FAILED
        # when every agent failed or exited, MAX_TURNS when a running
        # agent holds mail no turn was left for, and QUIET otherwise.
        # Each caller passes the reason to _stop in the same step.
        if self._working or self._stop_reason is not None:
            return None
        running = [name for name in self._names if name not in self._failed]
        if not running:
            return AgentSwarmStopReason.FAILED
        if any(self._inboxes[name] for name in running):
            return AgentSwarmStopReason.MAX_TURNS
        return AgentSwarmStopReason.QUIET

    def _changed_path(self, call: ToolCall, result: ToolResult) -> str | None:
        # The absolute path of the file a successful write_text or
        # patch_file changed: the call's own path argument, resolved
        # against the workplace. None for any other call.
        argument = AGENT_SWARM_FILE_TOOL_PATH_ARGUMENTS.get(call.tool_name)
        raw = call.arguments.get(argument) if argument is not None else None
        if result.status is ToolStatus.SUCCESS and isinstance(raw, str) and raw.strip():
            return str((self._root / raw).resolve())
        return None

    @staticmethod
    def _command_failure(call: ToolCall, result: ToolResult) -> str | None:
        # What a failed bash command reports: the time-limit error, or
        # its non-zero exit code. None for a command that succeeded and
        # for every other tool.
        if call.tool_name != AGENT_SWARM_SHELL_TOOL_NAME:
            return None
        if result.metadata.get("error") == AGENT_SWARM_SHELL_TIME_LIMIT_ERROR:
            return AGENT_SWARM_SHELL_TIME_LIMIT_ERROR
        exit_code = result.metadata.get("exit_code")
        return f"exit code {exit_code}" if type(exit_code) is int and exit_code else None

    @staticmethod
    def _budget_total(usage: object | None) -> int:
        # total_tokens when reported, else input plus output, a missing
        # value counting as zero.
        total = getattr(usage, "total_tokens", None)
        if isinstance(total, int):
            return total
        return int(getattr(usage, "input_tokens", None) or 0) + int(getattr(usage, "output_tokens", None) or 0)

    @staticmethod
    def _failure_text(error: VidbyteSdkError) -> str:
        # BaseAgent wraps the real failure, such as the provider's
        # error, as the cause of a generic one, so the cause names it.
        cause = error.__cause__ if error.__cause__ is not None else error
        detail = str(cause).strip()
        return f"{type(cause).__name__}: {detail}" if detail else type(cause).__name__

    @staticmethod
    def _early_exit_text(reply: AgentMessage) -> str:
        # A run that returned on its own is named by the loop's own stop
        # reason value, such as middleware_abort.
        stop = reply.metadata.get("stop_reason")
        return str(getattr(stop, "value", stop) or "unknown")


__all__ = ["AgentSwarmRuntime"]
