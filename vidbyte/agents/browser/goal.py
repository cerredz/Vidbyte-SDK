"""FILE: vidbyte/agents/browser/goal.py

PURPOSE: Defines BrowserGoal, the run's goal card (the fixed goal and done criteria, and the plan, progress, and blockers the orchestrator keeps current), its patch_goal tool, the stall arithmetic of its rechecks, and the context item that pins it at the top of the orchestrator's context; and BrowserGoalCheck, the two fresh-context structured calls that derive the done criteria and recheck the goal.
ROLE IN CODEBASE: BrowserAgentRuntime (vidbyte/agents/browser/runtime.py) builds one BrowserGoal per run and one BrowserGoalCheck per run-local runtime: it upserts BrowserGoal.item() into the context, adds BrowserGoal.tool() to the orchestrator's catalog, asks BrowserGoalCheck for a verdict at every finish attempt and every recheck_every episodes, and stops the run when BrowserGoal.stalled(). BrowserEpisodeTool (episode.py) reports each finished episode through episode_finished.
ARCHITECTURE NOTE: The card is the frozen BrowserGoalCard record (vidbyte/lib/dataclasses/browser.py), so every cap is record validation and a patch either builds a whole new valid card or changes nothing. The card is rendered from the goal_card leaf and every model-facing text comes from the browser_agent prompt family, so the prompts carry no numbers. Each check is a newly built BaseAgent with fixed leaves, no tools of its own (the loop adds only isDone), and system_prompt_presets=(), as JevReviewer is (vidbyte/agents/jev/done/reviewer.py); its model calls land in the run's ledger like every nested agent's.
FUNCTION INVENTORY: BrowserGoal.card returns the card; patch is the narrated main function that changes one section; episode_finished counts an episode for the recheck cadence; recheck_due says a periodic recheck is due; rechecked applies the stall rule and records a verdict; stalled says the run must stop; item renders the card as a context item; tool returns patch_goal; bullets renders a list. _PatchGoalTool is the patch_goal tool. BrowserGoalCheck.done_when derives the criteria; recheck asks for a verdict; _agent builds a check agent.
COMMON MODIFICATION PATTERNS: A new card section adds a BrowserGoalCard field with its cap, a BrowserGoalSection member when the model may patch it, and one placeholder in the goal_card leaf.
WHAT NOT TO DO IN THIS FILE: 1. Do not let patch change goal or done_when. 2. Do not give a check agent the orchestrator's history, tools, or prompt presets. 3. Do not state a cap in a prompt; the record enforces it. 4. Do not define module-level constants; they belong in vidbyte/lib/constants/browser.py.
KNOWN EDGE CASES: A progress patch keeps one item per non-blank line, with each line's outer whitespace removed; one line over its cap refuses the whole patch. A recheck counts as a stall on stalled, or on continue with progress unchanged since the previous recheck (the first compares with the empty start); an unavailable recheck neither counts nor resets the stall count, but restarts the cadence. A gap is kept as one line of at most BROWSER_ITEM_MAX_CHARS characters.
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 6.1 INV-13 to INV-18, 8.1 D-12 to D-15, and 8.5); vidbyte/agents/browser/README.md
TESTS: tests/features/browser_agent/test_browser_agent_goal.py and tests/features/browser_agent/test_browser_agent_recheck.py
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import cast

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.browser.events import BrowserAgentEvents
from vidbyte.agents.browser.response import BrowserResponse
from vidbyte.agents.browser.settings import BrowserAgentSettings
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context.primitives import TextContextItem
from vidbyte.lib.constants.browser import (
    BROWSER_CHECK_MAX_ITERATIONS,
    BROWSER_DONE_WHEN_AGENT_NAME,
    BROWSER_GOAL_PRIMITIVE_ID,
    BROWSER_GOAL_TITLE,
    BROWSER_ITEM_MAX_CHARS,
    BROWSER_MAX_CRITERIA,
    BROWSER_PATCH_SECTION_ARGUMENT,
    BROWSER_PATCH_TEXT_ARGUMENT,
    BROWSER_PATCH_TOOL_NAME,
    BROWSER_RECHECK_AGENT_NAME,
)
from vidbyte.lib.dataclasses.browser import (
    BrowserDoneWhenPayload,
    BrowserEpisodeResult,
    BrowserGoalCard,
    BrowserRecheckResult,
    BrowserVerdictPayload,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.browser import (
    BrowserEventKind,
    BrowserGoalSection,
    BrowserVerdict,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec


class BrowserGoal:
    """The run's goal card: its sections, its patch tool, the stall count of its rechecks, and its context item."""

    def __init__(self, card: BrowserGoalCard, settings: BrowserAgentSettings, response: BrowserResponse, events: BrowserAgentEvents) -> None:
        self._card = card
        self._settings = settings
        self._response = response
        self._events = events
        # What the card shows besides its record: the latest verdict
        # and gap, and one line about the last episode.
        self._verdict: str | None = None
        self._gap: str | None = None
        self._last_episode: str | None = None
        # The recheck bookkeeping: episodes so far and since the last
        # recheck, rechecks so far, consecutive stalls, and the progress
        # the next recheck compares with.
        self._episodes = 0
        self._since_recheck = 0
        self._rechecks = 0
        self._stalls = 0
        self._compared: tuple[str, ...] = ()
        response.goal(card)

    @property
    def card(self) -> BrowserGoalCard:
        """The card as it stands after the latest accepted patch."""
        return self._card

    def patch(self, section: BrowserGoalSection | str, text: str) -> BrowserGoalCard:
        """Change one mutable section of the card and return the new card, or raise ConfigurationError and change nothing."""
        # @intent goal-and-criteria-never-change
        # Only plan, progress, and blockers can change; any other name,
        # the goal and done_when included, is refused, so the card
        # always judges the run against the task it started with.
        chosen = RecordFieldConverter.to_enum(section, BrowserGoalSection, BROWSER_PATCH_SECTION_ARGUMENT)

        # Progress only grows, by one fact per non-blank line; the plan
        # and the blockers are replaced by the text as sent.
        match chosen:
            case BrowserGoalSection.PROGRESS:
                lines = tuple(line.strip() for line in text.splitlines() if line.strip())
                card = replace(self._card, progress=(*self._card.progress, *lines))
            case BrowserGoalSection.PLAN:
                card = replace(self._card, plan=text)
            case BrowserGoalSection.BLOCKERS:
                card = replace(self._card, blockers=text)

        # The new card passed its own caps, so it replaces the old one
        # everywhere: here, on the response, and in the next call.
        self._card = card
        self._response.goal(card)
        self._events.emit(BrowserEventKind.GOAL_PATCHED, chosen.value)
        return card

    def episode_finished(self, result: BrowserEpisodeResult) -> None:
        """Count one finished episode toward the recheck cadence and keep a one-line note of it for the card."""
        self._episodes += 1
        self._since_recheck += 1
        self._last_episode = " ".join(f"{result.index} {result.outcome.value}: {result.summary}".split())[:BROWSER_ITEM_MAX_CHARS]

    def recheck_due(self) -> bool:
        """Whether recheck_every episodes have finished since the last recheck."""
        return self._since_recheck >= self._settings.recheck_every

    def rechecked(self, payload: BrowserVerdictPayload | None, *, at_finish: bool) -> BrowserRecheckResult | None:
        """Apply one recheck's verdict: restart the cadence, update the stall count, keep the verdict and gap for the card, and record the result; None when the recheck was unavailable."""
        self._since_recheck = 0
        if payload is None:
            self._events.emit(BrowserEventKind.GOAL_RECHECKED, "unavailable", episode=self._episodes)
            return None
        # @intent a-stall-is-no-progress-since-the-last-recheck
        # A stalled verdict, or a continue while progress has not
        # changed since the previous recheck, counts one more stall;
        # anything else resets the count, so a model that keeps saying
        # continue cannot keep a run going without new facts.
        progress = self._card.progress
        stalled = payload.verdict is BrowserVerdict.STALLED or (payload.verdict is BrowserVerdict.CONTINUE and progress == self._compared)
        self._stalls = self._stalls + 1 if stalled else 0
        self._compared = progress
        self._rechecks += 1
        gap = " ".join(payload.gap.split())[:BROWSER_ITEM_MAX_CHARS]
        self._verdict, self._gap = payload.verdict.value, gap
        result = BrowserRecheckResult(index=self._rechecks, episodes=self._episodes, verdict=payload.verdict, gap=gap, at_finish=at_finish, stalls=self._stalls)
        self._response.recheck(result)
        self._events.emit(BrowserEventKind.GOAL_RECHECKED, payload.verdict.value, episode=self._episodes)
        return result

    def stalled(self) -> bool:
        """Whether max_stalls rechecks in a row found no progress, so the run must stop."""
        return self._stalls >= self._settings.max_stalls

    def item(self) -> TextContextItem:
        """The card rendered from the goal_card leaf, as one context item with a fixed id, so each upsert replaces the last."""
        card = self._card
        text = Prompts().get(Prompt.BROWSER_AGENT_GOAL_CARD).format(
            goal=card.goal,
            done_when=self.bullets(card.done_when),
            plan=card.plan or "-",
            progress=self.bullets(card.progress),
            blockers=card.blockers or "-",
            verdict=self._verdict or "-",
            gap=self._gap or "-",
            last_episode=self._last_episode or "-",
        )
        return TextContextItem(title=BROWSER_GOAL_TITLE, content=text.strip(), primitive_id=BROWSER_GOAL_PRIMITIVE_ID)

    def tool(self) -> BaseTool:
        """The patch_goal tool bound to this card."""
        return _PatchGoalTool(self)

    @staticmethod
    def bullets(items: Sequence[str]) -> str:
        """Render items as one Markdown bullet each, or a dash when there are none."""
        return "\n".join(f"- {item}" for item in items) or "-"


class _PatchGoalTool(BaseTool):
    """The patch_goal tool: changes the plan, progress, or blockers of the run's goal card."""

    def __init__(self, goal: BrowserGoal) -> None:
        self._goal = goal

    def spec(self) -> ToolSpec:
        """Return the patch_goal declaration, with every description taken from the prompt family."""
        prompts = Prompts()
        section = {"type": "string", "enum": [member.value for member in BrowserGoalSection], "description": prompts.get(Prompt.BROWSER_AGENT_PATCH_GOAL_SECTION_DESCRIPTION)}
        text = {"type": "string", "description": prompts.get(Prompt.BROWSER_AGENT_PATCH_GOAL_TEXT_DESCRIPTION)}
        return ToolSpec(
            name=BROWSER_PATCH_TOOL_NAME,
            description=prompts.get(Prompt.BROWSER_AGENT_PATCH_GOAL_DESCRIPTION),
            input_schema={"type": "object", "properties": {BROWSER_PATCH_SECTION_ARGUMENT: section, BROWSER_PATCH_TEXT_ARGUMENT: text}, "required": [BROWSER_PATCH_SECTION_ARGUMENT, BROWSER_PATCH_TEXT_ARGUMENT], "additionalProperties": False},
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Apply the patch and return the changed section's name, or a refusal the model can act on."""
        prompts = Prompts()
        # @intent a-refused-patch-says-what-to-change
        # A refused patch changes nothing and tells the model why; a
        # full progress section gets its own note, because no shorter
        # line will fit and the run should finish with what it holds.
        try:
            text = RecordFieldValidator.require_text(call.arguments.get(BROWSER_PATCH_TEXT_ARGUMENT), BROWSER_PATCH_TEXT_ARGUMENT, allow_blank=True)
            self._goal.patch(str(call.arguments.get(BROWSER_PATCH_SECTION_ARGUMENT)), text)
        except ConfigurationError as exc:
            if exc.details.get("field") == "BrowserGoalCard.progress":
                return ToolResult.error(BROWSER_PATCH_TOOL_NAME, prompts.get(Prompt.BROWSER_AGENT_PROGRESS_FULL))
            return ToolResult.error(BROWSER_PATCH_TOOL_NAME, prompts.get(Prompt.BROWSER_AGENT_PATCH_REFUSED).format(problem=exc.message))
        return ToolResult.success(BROWSER_PATCH_TOOL_NAME, str(call.arguments.get(BROWSER_PATCH_SECTION_ARGUMENT)))


class BrowserGoalCheck:
    """The two fresh-context structured calls of a run: deriving the done criteria, and rechecking the goal against the recorded progress."""

    def __init__(self, settings: BrowserAgentSettings) -> None:
        self._settings = settings

    async def done_when(self, goal: str) -> tuple[str, ...]:
        """Turn the run's message into done criteria with one structured call; any failure propagates before the run acts."""
        # @intent a-run-without-criteria-never-starts
        # A run that cannot judge done should not start a long browser
        # session, so a failed or off-schema call raises (fail closed).
        agent = self._agent(BROWSER_DONE_WHEN_AGENT_NAME, Prompt.BROWSER_AGENT_DONE_WHEN_SYSTEM_PROMPT, BrowserDoneWhenPayload, self._settings.model_name)
        reply = await agent.arun(goal)
        criteria = cast("BrowserDoneWhenPayload", reply.structured).criteria
        lines = (" ".join(item.split())[:BROWSER_ITEM_MAX_CHARS] for item in criteria)
        return tuple(line for line in lines if line)[:BROWSER_MAX_CRITERIA]

    async def recheck(self, card: BrowserGoalCard) -> BrowserVerdictPayload | None:
        """Ask a fresh agent whether the goal is done from the goal, the criteria, and the progress only; None when it is unavailable."""
        model = self._settings.recheck_model_name or self._settings.model_name
        agent = self._agent(BROWSER_RECHECK_AGENT_NAME, Prompt.BROWSER_AGENT_RECHECK_SYSTEM_PROMPT, BrowserVerdictPayload, model)
        prompt = Prompts().get(Prompt.BROWSER_AGENT_RECHECK_PROMPT).format(goal=card.goal, done_when=BrowserGoal.bullets(card.done_when), progress=BrowserGoal.bullets(card.progress))
        # @intent the-recheck-fails-open
        # A recheck outage or an off-schema verdict must not block a
        # finish or end a run; the caller accepts the finish instead.
        try:
            reply = await agent.arun(prompt)
        except VidbyteSdkError:
            return None
        return reply.structured if isinstance(reply.structured, BrowserVerdictPayload) else None

    def _agent(self, name: str, system: Prompt, schema: type, model: str) -> BaseAgent:
        # @intent checks-see-only-what-they-are-given
        # A new agent per check, with a fixed prompt, no tools of its
        # own, and no presets, so nothing of the orchestrator's run
        # reaches it but the message it is sent.
        settings = self._settings
        return BaseAgent(
            name=name.format(name=settings.name),
            system_prompt=Prompts().get(system),
            agent_loop_settings=AgentLoopSettings(max_iterations=BROWSER_CHECK_MAX_ITERATIONS),
            api_keys=settings.api_keys,
            model_mode=settings.model_mode,
            provider=settings.provider,
            model_name=model,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=schema,
            system_prompt_presets=(),
        )


__all__ = ["BrowserGoal", "BrowserGoalCheck"]
