"""FILE: vidbyte/agents/browser/episode.py

PURPOSE: Defines BrowserEpisodeTool, the run_episode tool of a BrowserAgent run: it starts one fresh worker agent that holds only the action servers' tools, under the action cap, the screenshot cap, and the observation diet, runs it on one page-level task with its own done check, and turns what the worker returned (or how it failed) into one episode card: a BrowserEpisodeResult on the response and a capped card text for the orchestrator.
ROLE IN CODEBASE: BrowserAgentRuntime (vidbyte/agents/browser/runtime.py) builds one per run with the live action tools and adds it to the orchestrator's catalog. It reports each card to BrowserGoal.episode_finished (goal.py), BrowserResponse.episode (response.py), and BrowserAgentEvents (events.py).
ARCHITECTURE NOTE: The worker is a plain BaseAgent with output_schema=BrowserEpisodePayload, so its card is structured output. Every cap is existing loop or middleware code (spec D-9, D-10): max_tool_calls is the action cap, ToolSettings.max_calls_per_tool caps each screenshot tool, and the tool-output sliding window plus the provider-boundary trim bound what the worker sees. A worker stopped at its cap or by a schema miss raises OutputSchemaViolationError after its reply was recorded, so the stuck card is built from worker.last_reply's own tool calls: the exact action count and, as evidence, the start of the newest successful observation. The workers of one run share the same bridged tool objects, so they act on one server process and one browser session. Tool calls in one turn run one after another, so episodes never overlap (spec D-22).
FUNCTION INVENTORY: spec declares run_episode; execute is the narrated main function; _worker builds the worker agent; _card turns the worker's reply into a card; _stuck builds a stuck card; _text renders the card text for the orchestrator.
COMMON MODIFICATION PATTERNS: A new per-episode cap is a BrowserAgentSettings field applied in _worker through existing loop or middleware settings, never a number in a prompt.
WHAT NOT TO DO IN THIS FILE: 1. Do not catch BaseException or CancelledError; a cancelled episode records no card. 2. Do not give the worker search, fetch, developer, or orchestrator tools. 3. Do not act on ready_to_submit; it is only reported. 4. Do not put the recipe's arguments, the task, or page text in an event.
KNOWN EDGE CASES: A worker that raises before replying gives a stuck card with actions None and no evidence, and its stop reason is the caught error's type name (a provider error arrives wrapped as AgentExecutionError). The recipe holds what the worker typed, in process memory only (spec EC-31). A screenshot tool is any action tool whose name contains "screenshot" in any case; one named otherwise is bounded only by the action cap.
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 6.1 INV-6 to INV-12, 8.1 D-8 to D-10, D-17, D-22, D-23, and D-27, and 8.5); vidbyte/agents/browser/README.md
TESTS: tests/features/browser_agent/test_browser_agent_episode.py
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.browser.events import BrowserAgentEvents
from vidbyte.agents.browser.goal import BrowserGoal
from vidbyte.agents.browser.response import BrowserResponse
from vidbyte.agents.browser.settings import BrowserAgentSettings
from vidbyte.agents.settings import AgentLoopSettings, ToolSettings
from vidbyte.context.compaction import CompactionMode
from vidbyte.lib.constants.browser import (
    BROWSER_CARD_CUT_MARKER,
    BROWSER_CARD_MAX_TOKENS,
    BROWSER_EPISODE_AGENT_NAME,
    BROWSER_EPISODE_DONE_WHEN_ARGUMENT,
    BROWSER_EPISODE_REPLY_TURNS,
    BROWSER_EPISODE_TASK_ARGUMENT,
    BROWSER_EPISODE_TOOL_NAME,
    BROWSER_ITEM_MAX_CHARS,
    BROWSER_MAX_ITEMS,
    BROWSER_SCREENSHOT_MARKER,
    BROWSER_STALE_OBSERVATION_CHARS,
    BROWSER_SUMMARY_MAX_CHARS,
    BROWSER_WORKER_HISTORY_MAX_TOKENS,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.browser import (
    BrowserEpisodePayload,
    BrowserEpisodeResult,
    BrowserRecipeStep,
)
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.browser import BrowserEpisodeOutcome, BrowserEventKind
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import (
    ConfigurationError,
    OutputSchemaViolationError,
    VidbyteSdkError,
)
from vidbyte.lib.util import TokenEstimate
from vidbyte.middleware import MessageHistoryCompactionMiddleware
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools._internal import IS_DONE_TOOL_NAME
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec


class BrowserEpisodeTool(BaseTool):
    """The run_episode tool: one fresh, capped worker per page-level task, returning one capped card."""

    def __init__(self, settings: BrowserAgentSettings, action_tools: tuple[BaseTool, ...], goal: BrowserGoal, response: BrowserResponse, events: BrowserAgentEvents) -> None:
        self._settings = settings
        self._action_tools = action_tools
        self._goal = goal
        self._response = response
        self._events = events
        # Episodes are numbered from one within the run.
        self._episodes = 0

    def spec(self) -> ToolSpec:
        """Return the run_episode declaration: a task and its done check, every description from the prompt family, marked internal."""
        prompts = Prompts()
        task = {"type": "string", "description": prompts.get(Prompt.BROWSER_AGENT_RUN_EPISODE_TASK_DESCRIPTION)}
        done_when = {"type": "string", "description": prompts.get(Prompt.BROWSER_AGENT_RUN_EPISODE_DONE_WHEN_DESCRIPTION)}
        return ToolSpec(
            name=BROWSER_EPISODE_TOOL_NAME,
            description=prompts.get(Prompt.BROWSER_AGENT_RUN_EPISODE_DESCRIPTION),
            input_schema={"type": "object", "properties": {BROWSER_EPISODE_TASK_ARGUMENT: task, BROWSER_EPISODE_DONE_WHEN_ARGUMENT: done_when}, "required": [BROWSER_EPISODE_TASK_ARGUMENT, BROWSER_EPISODE_DONE_WHEN_ARGUMENT], "additionalProperties": False},
            permission=ToolPermission.SAFE,
            # @intent an-episode-is-not-one-tool-call-of-budget
            # An episode lasts as long as its worker and returns a
            # capped card, so the orchestrator's tool budget, timeout,
            # and result cap do not apply; the worker's caps bound it.
            metadata={"internal": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run one episode with a fresh worker and return its capped card; a worker failure becomes a stuck card."""
        # Read the task and its check; a call without them starts
        # nothing and tells the model what to fix.
        try:
            task = RecordFieldValidator.require_text(call.arguments.get(BROWSER_EPISODE_TASK_ARGUMENT), BROWSER_EPISODE_TASK_ARGUMENT)
            done_when = RecordFieldValidator.require_text(call.arguments.get(BROWSER_EPISODE_DONE_WHEN_ARGUMENT), BROWSER_EPISODE_DONE_WHEN_ARGUMENT)
        except ConfigurationError as exc:
            return ToolResult.error(BROWSER_EPISODE_TOOL_NAME, exc.message)
        self._episodes += 1
        index = self._episodes
        self._events.emit(BrowserEventKind.EPISODE_STARTED, episode=index)

        # Build a fresh worker that holds only the browser tools, under
        # the action cap, the screenshot cap, and the observation diet,
        # and brief it with the task and its check alone.
        worker = self._worker(index)
        prompt = Prompts().get(Prompt.BROWSER_AGENT_EPISODE_PROMPT).format(index=index, task=task, done_when=done_when)

        # @intent every-episode-returns-one-card
        # Run the worker and turn its reply into a card. A cap stop or
        # a reply that never matched the card's shape raises after the
        # reply was recorded, so its own calls give a stuck card with
        # evidence; any other SDK, OS, or value error gives a stuck card
        # naming the error. Cancellation propagates and records nothing.
        try:
            reply = await worker.arun(prompt)
            result = self._card(index, task, done_when, reply, worker)
        except OutputSchemaViolationError:
            result = self._stuck(index, task, done_when, worker.last_reply, None, worker)
        except (VidbyteSdkError, OSError, ValueError) as exc:
            result = self._stuck(index, task, done_when, None, type(exc).__name__, worker)

        # Record the card on the goal's cadence and on the response,
        # then tell the sink how the episode ended; the recipe event
        # names only its step count, never what was typed.
        self._goal.episode_finished(result)
        self._response.episode(result)
        self._events.emit(BrowserEventKind.EPISODE_FINISHED, result.outcome.value, episode=index)
        if result.recipe:
            self._events.emit(BrowserEventKind.RECIPE_RECORDED, str(len(result.recipe)), episode=index)

        # Hand the orchestrator only the card text, within its cap.
        return ToolResult.success(BROWSER_EPISODE_TOOL_NAME, self._text(result))

    def _worker(self, index: int) -> BaseAgent:
        # @intent worker-caps-live-in-code
        # The action cap is the loop's tool-call budget, which the
        # worker sees in its loop settings; each screenshot tool is
        # capped per episode and a denied call lets it go on; older
        # observations are cut per tool and the whole history is
        # trimmed at provider boundaries. The prompt states no numbers.
        settings = self._settings
        screenshots = {tool.spec().name: settings.max_screenshots for tool in self._action_tools if BROWSER_SCREENSHOT_MARKER in tool.spec().name.lower()}
        loop = AgentLoopSettings(max_iterations=settings.max_actions + BROWSER_EPISODE_REPLY_TURNS, max_tool_calls=settings.max_actions, tool_settings=ToolSettings(max_calls_per_tool=screenshots))
        window = MessageHistoryCompactionMiddleware.tool_output_sliding_window(keep_recent=settings.keep_observations, window_mode=CompactionMode.TRUNCATE_TOOL_RESULTS, max_chars=BROWSER_STALE_OBSERVATION_CHARS)
        trim = MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=BROWSER_WORKER_HISTORY_MAX_TOKENS)
        return BaseAgent(
            name=BROWSER_EPISODE_AGENT_NAME.format(name=settings.name, index=index),
            system_prompt=f"{settings.system_prompt}\n\n{Prompts().get(Prompt.BROWSER_AGENT_WORKER_SYSTEM_PROMPT)}",
            tools=self._action_tools,
            permission_policy=settings.permission_policy,
            agent_loop_settings=loop,
            middleware=(window, trim),
            api_keys=settings.api_keys,
            model_mode=settings.model_mode,
            provider=settings.provider,
            model_name=settings.episode_model_name or settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=BrowserEpisodePayload,
        )

    def _card(self, index: int, task: str, done_when: str, reply: AgentMessage, worker: BaseAgent) -> BrowserEpisodeResult:
        # The worker's own card, cut to the record's caps: the first
        # items in the worker's order, each cut to its cap, blanks
        # dropped. Every browser call counts as an action, denied and
        # failed ones included, because that is what the action cap
        # counts; a done card also keeps its successful calls as its
        # recipe.
        payload = reply.structured
        if not isinstance(payload, BrowserEpisodePayload):
            raise OutputSchemaViolationError("The worker's reply is not a BrowserEpisodePayload.", raw_output=reply.content)
        facts, urls, evidence = (tuple(item for item in (value.strip()[:BROWSER_ITEM_MAX_CHARS] for value in values) if item)[:BROWSER_MAX_ITEMS] for values in (payload.facts, payload.urls, payload.evidence))
        calls = [context for context in reply.metadata.get("tool_calls", ()) if context.tool_name != IS_DONE_TOOL_NAME]
        succeeded = [context for context in calls if context.state is ToolCallState.SUCCEEDED]
        recipe = tuple(BrowserRecipeStep(tool=context.tool_name, arguments=json.dumps(dict(context.arguments))) for context in succeeded) if payload.outcome is BrowserEpisodeOutcome.DONE else ()
        return BrowserEpisodeResult(
            index=index,
            task=task,
            done_when=done_when,
            outcome=payload.outcome,
            summary=payload.summary[:BROWSER_SUMMARY_MAX_CHARS],
            facts=facts,
            urls=urls,
            evidence=evidence,
            recipe=recipe,
            actions=len(calls),
            tokens=worker.get_usage().total_tokens,
            stop_reason=str(reply.metadata.get("stop_reason") or ""),
        )

    def _stuck(self, index: int, task: str, done_when: str, reply: AgentMessage | None, error: str | None, worker: BaseAgent) -> BrowserEpisodeResult:
        # A stuck card built by code. After a recorded reply it carries
        # the exact action count and, as evidence, the start of the
        # newest observation that succeeded, with no marker; after an
        # error raised before any reply it carries neither.
        calls: Sequence[ToolCallContext] = [context for context in reply.metadata.get("tool_calls", ()) if context.tool_name != IS_DONE_TOOL_NAME] if reply is not None else ()
        succeeded = [context.result.output for context in calls if context.state is ToolCallState.SUCCEEDED and context.result is not None]
        reason = error or (str(reply.metadata.get("stop_reason") or "") if reply is not None else "")
        return BrowserEpisodeResult(
            index=index,
            task=task,
            done_when=done_when,
            outcome=BrowserEpisodeOutcome.STUCK,
            summary=Prompts().get(Prompt.BROWSER_AGENT_STUCK_SUMMARY).format(reason=reason).strip()[:BROWSER_SUMMARY_MAX_CHARS],
            evidence=(succeeded[-1][:BROWSER_STALE_OBSERVATION_CHARS],) if succeeded and succeeded[-1].strip() else (),
            actions=len(calls) if reply is not None else None,
            tokens=worker.get_usage().total_tokens,
            stop_reason=reason,
        )

    @staticmethod
    def _text(result: BrowserEpisodeResult) -> str:
        # @intent the-orchestrator-sees-only-a-capped-card
        # Only this text reaches the orchestrator, never the pages the
        # worker saw, and it is cut to the card's token cap; the full
        # record stays on the response.
        text = Prompts().get(Prompt.BROWSER_AGENT_RESULT_CARD).format(
            index=result.index,
            outcome=result.outcome.value,
            summary=result.summary or "-",
            facts=BrowserGoal.bullets(result.facts),
            urls=BrowserGoal.bullets(result.urls),
            evidence=BrowserGoal.bullets(result.evidence),
        )
        return TokenEstimate.cap(text.strip(), BROWSER_CARD_MAX_TOKENS, BROWSER_CARD_CUT_MARKER)


__all__ = ["BrowserEpisodeTool"]
