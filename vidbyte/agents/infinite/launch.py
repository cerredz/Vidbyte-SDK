"""FILE: vidbyte/agents/infinite/launch.py

PURPOSE: Defines the launch_subagent tool and InfinitePair, its pipeline stage: the root or a generator hands over a batch of tasks, each task runs as a fresh generator followed by a fresh verifier that checks and fixes its work, the pair's staged memory entries are committed or dropped by the verdict, and the parent gets back one short result card per task.
ROLE IN CODEBASE: InfiniteMemoryRuntime (runtime.py) adds one InfiniteLaunchTool to the root for each run; InfinitePair adds one to each generator that is still above the depth cap. Pairs use InfiniteWorkspace (workspace.py) for context entries, commits, and the map, InfiniteRunJournal (journal.py) to record and replay pairs, and InfiniteAgentMemory (memory.py) for each child's memory tools.
ARCHITECTURE NOTE: The tool checks the whole batch before anything starts, records every new pair as started, and runs the pairs at once through ParallelPipeline, as JevBulkWorkTool does. Each pair builds plain BaseAgents with a fresh context holding the workspace map, its own history-trimming middleware, and only the extras its task card names; a pair turns every SDK, disk, or decode error into its own card, so siblings and the parent keep going. The tool is internal, so the loop's tool timeout and result cap never cut a batch; the cards are capped here instead.
FUNCTION INVENTORY: InfiniteLaunchTool.spec builds the closed task-card schema; execute is the narrated main function; _cards reads the model's tasks into task cards; _check applies the batch rules. InfinitePair.run is the narrated main function; _agent builds one child agent; _task_message and _verifier_message write the two first messages; _status, _verdict, _commit, _finish, _capped, and _error_text each do one step; render and finished_lines format a card and a list of finished pairs for a parent.
COMMON MODIFICATION PATTERNS: A new batch rule is one more check in _check with a message that says what to fix. A new task-card field adds the field to InfiniteTaskCard, one schema property and description leaf here, and its use in _task_message or _agent.
WHAT NOT TO DO IN THIS FILE: 1. Do not start any agent before the whole batch passes _check and every new pair has its pair_started record. 2. Do not catch CancelledError or BaseException in InfinitePair.run; cancelling the run must stop every pair. 3. Do not give a child a developer tool its card does not name, or a verifier the launch tool. 4. Do not pass a child's transcript to its verifier or its parent; only the capped card goes up. 5. Do not add module-level constants here.
KNOWN EDGE CASES: A batch of replays only skips ParallelPipeline, which refuses zero stages. An entry superseded between the batch check and the pair's start fails that pair. An error outside VidbyteSdkError, OSError, and ValueError escapes the pair and the call while its siblings keep running (spec EC-41). A pair whose generator raised or answered blank has status failed, no verifier, and every staged entry dropped.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 6.1 INV-4 to INV-16 and INV-26 to INV-31, and 9.2); vidbyte/agents/infinite/README.md; vidbyte/agents/jev/bulk_work.py (the pattern this follows)
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_delegation.py, tests/features/infinite_memory_agent/test_infinite_memory_verification.py, and tests/features/infinite_memory_agent/test_infinite_memory_resume.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from pathlib import Path
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.fork import AgentForker
from vidbyte.agents.infinite.journal import InfiniteRunJournal
from vidbyte.agents.infinite.memory import InfiniteAgentMemory
from vidbyte.agents.infinite.settings import InfiniteMemoryAgentSettings
from vidbyte.agents.infinite.workspace import InfiniteWorkspace
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import TextContextItem
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.constants.infinite import (
    INFINITE_CARD_TEXT_MAX_TOKENS,
    INFINITE_DEPTH_STEP,
    INFINITE_FINISHED_PAIR_LINE,
    INFINITE_GENERATOR_KEY,
    INFINITE_HISTORY_MAX_TOKENS,
    INFINITE_LAUNCH_TOOL_NAME,
    INFINITE_MAP_PRIMITIVE_ID,
    INFINITE_MAP_TITLE,
    INFINITE_MIN_AGENTS,
    INFINITE_PAIR_TURN_SECONDS,
    INFINITE_TRUNCATION_MARKER,
    INFINITE_VERDICT_PATTERN,
    INFINITE_VERIFIER_KEY,
)
from vidbyte.lib.dataclasses.agents import AgentMessage, AgentStopReason
from vidbyte.lib.dataclasses.infinite import (
    InfiniteResultCard,
    InfiniteStagedEntry,
    InfiniteTaskCard,
)
from vidbyte.lib.enums.infinite import (
    InfiniteAgentRole,
    InfiniteResultStatus,
    InfiniteVerdict,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError, VidbyteSdkError
from vidbyte.lib.util import TokenEstimate
from vidbyte.middleware import MessageHistoryCompactionMiddleware
from vidbyte.pipelines.base import BasePipeline
from vidbyte.pipelines.parallel import ParallelPipeline
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.toolsets import InfiniteMemoryAgentTools
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec


class InfiniteLaunchTool(BaseTool):
    """The launch_subagent tool: run a batch of generator and verifier pairs at once and return one result card per task."""

    def __init__(self, settings: InfiniteMemoryAgentSettings, workspace: InfiniteWorkspace, journal: InfiniteRunJournal, *, key: str, depth: int, extras: tuple[BaseTool, ...]) -> None:
        self.settings = settings
        self.workspace = workspace
        self.journal = journal
        # The launching agent's key and depth, and the developer tools
        # it may hand on to its pairs.
        self.key = key
        self.depth = depth
        self.extras = extras

    def spec(self) -> ToolSpec:
        """Return the launch_subagent declaration: 1 to max_parallel closed task cards, marked internal like JevBulkWorkTool."""
        prompts = Prompts()
        maximum = self.settings.max_parallel
        card = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_LAUNCH_NAME_DESCRIPTION)},
                "goal": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_LAUNCH_GOAL_DESCRIPTION)},
                "done_criteria": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": prompts.get(Prompt.INFINITE_MEMORY_LAUNCH_DONE_CRITERIA_DESCRIPTION)},
                "generator_prompt": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_LAUNCH_GENERATOR_PROMPT_DESCRIPTION)},
                "verifier_prompt": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_LAUNCH_VERIFIER_PROMPT_DESCRIPTION)},
                "context": {"type": "array", "items": {"type": "string"}, "description": prompts.get(Prompt.INFINITE_MEMORY_LAUNCH_CONTEXT_DESCRIPTION)},
                "tools": {"type": "array", "items": {"type": "string"}, "description": prompts.get(Prompt.INFINITE_MEMORY_LAUNCH_TOOLS_DESCRIPTION)},
            },
            "required": ["name", "goal", "done_criteria", "generator_prompt", "verifier_prompt"],
            "additionalProperties": False,
        }
        tasks = {"type": "array", "minItems": 1, "maxItems": maximum, "items": card, "description": prompts.get(Prompt.INFINITE_MEMORY_LAUNCH_TASKS_DESCRIPTION).format(max_parallel=maximum)}
        return ToolSpec(
            name=INFINITE_LAUNCH_TOOL_NAME,
            description=prompts.get(Prompt.INFINITE_MEMORY_LAUNCH_TOOL_DESCRIPTION).format(max_parallel=maximum),
            input_schema={"type": "object", "properties": {"tasks": tasks}, "required": ["tasks"], "additionalProperties": False},
            permission=ToolPermission.SAFE,
            # @intent a-batch-is-never-cut-by-tool-limits
            # A batch lasts as long as its pairs and returns capped cards,
            # so the loop's tool timeout and result cap must not apply.
            metadata={"internal": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Check the whole batch, replay finished tasks, run the new pairs at once, and return every card in task order."""
        prompts = Prompts()
        # Read the tasks and check the whole batch first, so a bad batch
        # starts nothing and the model is told exactly what to fix.
        try:
            cards = self._cards(call.arguments.get("tasks"))
            keys = tuple(f"{self.key}/{card.name}" for card in cards)
            # @intent finished-pairs-are-replayed-not-rerun
            # A name that already finished in this run returns its
            # recorded card, so a resumed or repeated launch never redoes
            # finished work.
            pairs = {key: InfinitePair(self, card, key) for card, key in zip(cards, keys, strict=True) if self.journal.finished(key) is None}
            self._check(cards, len(pairs))
        except (ConfigurationError, ToolExecutionError) as exc:
            return ToolResult.error(INFINITE_LAUNCH_TOOL_NAME, prompts.get(Prompt.INFINITE_MEMORY_LAUNCH_REJECTED_PROMPT).format(problem=exc.message))

        # @intent pairs-are-journaled-before-they-start
        # Record every new pair as started before any agent runs, so a
        # crash leaves it listed as interrupted for resume.
        for key in pairs:
            self.journal.pair_started(key)

        # Run the new pairs at the same time; a batch of replays only
        # skips this, because the pipeline needs at least one stage.
        if pairs:
            await ParallelPipeline(tuple(pairs.values())).run("")

        # Return every card in task order, replayed ones under their label.
        replayed = prompts.get(Prompt.INFINITE_MEMORY_REPLAYED_LABEL)
        texts = []
        for key in keys:
            card = self.journal.finished(key)
            if card is not None:
                texts.append(InfinitePair.render(card) if key in pairs else f"{replayed}\n{InfinitePair.render(card)}")
        return ToolResult.success(INFINITE_LAUNCH_TOOL_NAME, "\n\n".join(texts))

    def _cards(self, tasks: object) -> tuple[InfiniteTaskCard, ...]:
        # Reads the model's tasks into validated task cards, turning JSON
        # lists into tuples; any problem raises with what to fix.
        if not isinstance(tasks, list) or not tasks:
            raise ConfigurationError("tasks must be a list of task objects.")
        if len(tasks) > self.settings.max_parallel:
            raise ConfigurationError(f"tasks holds {len(tasks)} tasks, over max_parallel ({self.settings.max_parallel}); split the work over several calls.")
        fields = dataclasses.fields(InfiniteTaskCard)
        names = [field.name for field in fields]
        required = [field.name for field in fields if field.default is dataclasses.MISSING]
        cards = []
        for task in tasks:
            if not isinstance(task, dict):
                raise ConfigurationError(f"Each task must be an object with the fields {', '.join(names)}; got {task!r}.")
            unknown = [name for name in task if name not in names]
            missing = [name for name in required if name not in task]
            if unknown or missing:
                raise ConfigurationError(f"Task {task.get('name')!r} has unknown fields {unknown} and lacks the fields {missing}; use exactly {', '.join(names)}.")
            given: dict[str, Any] = {name: tuple(value) if isinstance(value, list) else value for name, value in task.items()}
            cards.append(InfiniteTaskCard(**given))
        return tuple(cards)

    def _check(self, cards: tuple[InfiniteTaskCard, ...], new: int) -> None:
        # @intent a-batch-stays-inside-its-limits
        # Names stay unique keys, a child never gains a tool its parent
        # lacks, context names only live entries, and the run never
        # starts more than max_agents agents.
        names = [card.name for card in cards]
        twice = next((name for name in names if names.count(name) > 1), None)
        if twice is not None:
            raise ConfigurationError(f"Two tasks are named {twice}; give every task in one call its own name.")
        granted = tuple(tool.spec().name for tool in self.extras)
        foreign = next((name for card in cards for name in card.tools if name not in granted), None)
        if foreign is not None:
            raise ConfigurationError(f"{foreign} is not a tool you can give to a task; name only these tools: {', '.join(granted) or 'none'}.")
        ids = tuple(int(item.removeprefix("#")) for card in cards for item in card.context if item.startswith("#"))
        if ids:
            self.workspace.entries(ids)
        started = self.journal.agents_started
        wanted = INFINITE_MIN_AGENTS * new
        if started + wanted > self.settings.max_agents:
            raise ConfigurationError(f"This batch would start {wanted} agents after the {started} already started in this run, over max_agents ({self.settings.max_agents}); launch fewer tasks.")


class InfinitePair(BasePipeline):
    """One pipeline stage: a generator does one task, a verifier checks and fixes its work, and their staged entries are committed or dropped."""

    def __init__(self, launch: InfiniteLaunchTool, card: InfiniteTaskCard, key: str) -> None:
        self.launch = launch
        self.card = card
        self.key = key
        self.result: InfiniteResultCard | None = None
        self.criteria = "\n".join(f"- {item}" for item in card.done_criteria)
        # The generator and the verifier share the staged and dropped
        # lists, so the verifier can review and drop what was staged.
        self.staged: list[InfiniteStagedEntry] = []
        self.dropped: list[str] = []
        self.entries: list[int] = []

    async def run(self, prompt: str) -> str:
        """Run the generator, then its verifier, commit or drop the staged entries, record the card, and return its text."""
        launch = self.launch
        status, verdict, summary, review = InfiniteResultStatus.FAILED, InfiniteVerdict.UNCHECKED, "", ""
        # Each child gets its own memory tools over this pair's shared
        # staged and dropped lists, and the card lists the files both wrote.
        writer =InfiniteAgentMemory(launch.workspace, key=f"{self.key}/{INFINITE_GENERATOR_KEY}", role=InfiniteAgentRole.GENERATOR, run_id=launch.journal.run_id, staged=self.staged, dropped=self.dropped)
        checker = InfiniteAgentMemory(launch.workspace, key=f"{self.key}/{INFINITE_VERIFIER_KEY}", role=InfiniteAgentRole.VERIFIER, run_id=launch.journal.run_id, staged=self.staged, dropped=self.dropped)
        # @intent one-failed-pair-never-sinks-its-siblings
        # Every SDK, disk, or decode error, up to and including the card
        # and its journal record, becomes this pair's own card, so
        # siblings and the parent keep going; cancellation is not
        # caught, so stopping the run stops every pair.
        try:
            # Build the generator with a fresh context and send it the
            # task card, the entries and paths it names, and its quota.
            reply = await self._agent(writer).arun(self._task_message(writer))
            summary = self._capped(reply.content.strip())
            status = self._status(reply)

            # @intent sibling-generators-finish-before-verifiers-judge
            # Give the sibling pairs a turn first, so the pairs of one
            # batch move forward together even when a model answers at
            # once, and every generator has staged before a verdict.
            await asyncio.sleep(INFINITE_PAIR_TURN_SECONDS)

            # Unless the generator failed, a fresh verifier gets the
            # outcome, never the transcript, checks it, and fixes it.
            if status is not InfiniteResultStatus.FAILED:
                review = (await self._agent(checker).arun(self._verifier_message(checker, status, summary, tuple(writer.files_written)))).content
                verdict = self._verdict(review)

            # @intent only-judged-entries-reach-memory
            # Staged entries are committed only after a verdict; with
            # none, every staged entry is dropped below.
            if verdict is not InfiniteVerdict.UNCHECKED:
                self._commit()

            # Drop what was not committed and record the card, with the
            # files both agents wrote.
            card = self._finish(status, verdict, summary, self._capped(review), (*writer.files_written, *checker.files_written))
        except (VidbyteSdkError, OSError, ValueError) as exc:
            # After an error the work counts as unjudged, and the error
            # becomes the review.
            card = self._finish(status, InfiniteVerdict.UNCHECKED, summary, self._capped(self._error_text(exc)), (*writer.files_written, *checker.files_written))

        # Hand the parent only the capped card.
        return self.render(card)

    def _agent(self, memory: InfiniteAgentMemory) -> BaseAgent:
        # @intent children-start-fresh-with-only-what-they-need
        # A child gets the parent's model, provider settings, and
        # permission policy, the role's rules, a map of the workspace,
        # its own history trim, and only the extras its card names;
        # agent-bound extras are cloned as in a fork.
        launch, settings = self.launch, self.launch.settings
        granted = tuple(tool for tool in launch.extras if tool.spec().name in self.card.tools)
        level = launch.depth + INFINITE_DEPTH_STEP
        delegation: tuple[BaseTool, ...] = ()
        match memory.role:
            case InfiniteAgentRole.GENERATOR:
                rules = Prompts().get(Prompt.INFINITE_MEMORY_GENERATOR_SYSTEM_PROMPT)
                if level < settings.max_depth:
                    delegation = (InfiniteLaunchTool(settings, launch.workspace, launch.journal, key=memory.key, depth=level, extras=granted),)
            case _:
                rules = Prompts().get(Prompt.INFINITE_MEMORY_VERIFIER_SYSTEM_PROMPT)
        context = ContextManager()
        context.upsert(TextContextItem(title=INFINITE_MAP_TITLE, content=launch.workspace.map_text(), primitive_id=INFINITE_MAP_PRIMITIVE_ID), placement=ContextWindowPlacement.TOP_OF_CONTEXT)
        return BaseAgent(
            name=f"{settings.name}/{memory.key}",
            system_prompt=f"{settings.system_prompt}\n\n{rules}",
            provider=settings.provider,
            model_name=settings.model_name,
            api_key=settings.api_key,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            tools=(*InfiniteMemoryAgentTools.get_tools(Path(settings.root_dir), launch.workspace.root, launch.workspace.settings.max_tokens), *memory.tools(), *delegation, *(AgentForker._clone_tool(tool, None, None) for tool in granted)),
            permission_policy=settings.permission_policy,
            agent_loop_settings=settings.loop,
            context_manager=context,
            middleware=(MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS),),
        )

    def _task_message(self, memory: InfiniteAgentMemory) -> str:
        # The generator's first message: the card, the named entries
        # pasted in, the named paths listed, its own finished children
        # (after a resume), and its quota.
        launch, card = self.launch, self.card
        ids = tuple(int(item.removeprefix("#")) for item in card.context if item.startswith("#"))
        entries = launch.workspace.entries(ids) if ids else ()
        pasted = "\n".join(f"#{entry.id}: {entry.draft.text}" for entry in entries) or "-"
        paths = "\n".join(f"- {item}" for item in card.context if not item.startswith("#")) or "-"
        finished = self.finished_lines(launch.journal.finished_children(memory.key))
        return Prompts().get(Prompt.INFINITE_MEMORY_TASK_PROMPT).format(goal=card.goal, criteria=self.criteria, instructions=card.generator_prompt, entries=pasted, paths=paths, finished=finished, quota=memory.quota())

    def _verifier_message(self, memory: InfiniteAgentMemory, status: InfiniteResultStatus, summary: str, written: tuple[str, ...]) -> str:
        # The verifier's first message: its instructions, the card, and
        # what the generator reported, staged, and wrote.
        staged = "\n".join(f"- {item.key} ({item.draft.kind.value}): {item.draft.text}" for item in self.staged) or "-"
        files = "\n".join(f"- {path}" for path in written) or "-"
        return Prompts().get(Prompt.INFINITE_MEMORY_VERIFIER_TASK_PROMPT).format(instructions=self.card.verifier_prompt, goal=self.card.goal, criteria=self.criteria, status=status.value, summary=summary or "-", staged=staged, files=files, quota=memory.quota())

    @staticmethod
    def _status(reply: AgentMessage) -> InfiniteResultStatus:
        # A blank reply is a failure; a normal finish is done, and any
        # other stop with a reply is partial work worth verifying.
        if not reply.content.strip():
            return InfiniteResultStatus.FAILED
        match reply.metadata.get("stop_reason"):
            case AgentStopReason.FINAL_RESPONSE | AgentStopReason.IS_DONE:
                return InfiniteResultStatus.DONE
            case _:
                return InfiniteResultStatus.PARTIAL

    @staticmethod
    def _verdict(review: str) -> InfiniteVerdict:
        # @intent the-last-verdict-line-wins
        # The verifier may change its mind while it writes, so the last
        # VERDICT line decides; no line means nobody judged the work.
        found = re.findall(INFINITE_VERDICT_PATTERN, review)
        return InfiniteVerdict(found[-1].lower()) if found else InfiniteVerdict.UNCHECKED

    def _commit(self) -> None:
        # @intent staged-entries-are-checked-again-at-commit
        # Siblings may have committed since these entries were staged,
        # so each is checked again; one that now breaks a rule is
        # dropped with the reason, and the others still commit.
        launch = self.launch
        for item in tuple(self.staged):
            try:
                entry = launch.workspace.commit_entry(item.draft, by=item.author, verified_by=f"{self.key}/{INFINITE_VERIFIER_KEY}", run=launch.journal.run_id)
            except ToolExecutionError as exc:
                self.dropped.append(f"{item.key} ({item.draft.text}): {exc.message}")
            else:
                self.entries.append(entry.id)
            self.staged.remove(item)

    def _finish(self, status: InfiniteResultStatus, verdict: InfiniteVerdict, summary: str, review: str, files: tuple[str, ...]) -> InfiniteResultCard:
        # Every entry still staged is dropped with the verdict as its
        # reason; then the card is built and the pair recorded finished.
        self.dropped.extend(f"{item.key} ({item.draft.text}): not committed, because the verdict is {verdict.value}" for item in self.staged)
        self.staged.clear()
        self.result = InfiniteResultCard(name=self.card.name, key=self.key, status=status, verdict=verdict, summary=summary, review=review, entries=tuple(self.entries), dropped=tuple(self.dropped), files=tuple(dict.fromkeys(files)))
        self.launch.journal.pair_finished(self.key, self.result)
        return self.result

    @staticmethod
    def _capped(text: str) -> str:
        # A card's texts are capped, so one long reply never fills the
        # parent's context; cut text ends with the marker.
        if TokenEstimate.count(text) <= INFINITE_CARD_TEXT_MAX_TOKENS:
            return text
        return f"{TokenEstimate.cut(text, INFINITE_CARD_TEXT_MAX_TOKENS)}{INFINITE_TRUNCATION_MARKER}"

    @staticmethod
    def _error_text(error: BaseException) -> str:
        # A runner's failure arrives wrapped, with the provider's message
        # as its cause, so the cause is the most useful text to report.
        cause = str(error.__cause__ or "").strip()
        return cause or str(error).strip() or type(error).__name__

    @staticmethod
    def render(card: InfiniteResultCard) -> str:
        """Return a result card as the text its parent reads, with the joined dropped entries and files each cut to the card cap."""
        # @intent a-rendered-card-stays-small
        # The journal keeps both lists whole, but the parent reads each
        # joined list cut like the summary and the review, so a card
        # never grows with the number of entries or files.
        lists = {"dropped": "; ".join(card.dropped) or "-", "files": ", ".join(card.files) or "-"}
        cut = {field: text if TokenEstimate.count(text) <= INFINITE_CARD_TEXT_MAX_TOKENS else f"{TokenEstimate.cut(text, INFINITE_CARD_TEXT_MAX_TOKENS)}{INFINITE_TRUNCATION_MARKER}" for field, text in lists.items()}
        return Prompts().get(Prompt.INFINITE_MEMORY_RESULT_CARD).format(name=card.name, key=card.key, status=card.status.value, verdict=card.verdict.value, summary=card.summary or "-", review=card.review or "-", entries=", ".join(f"#{number}" for number in card.entries) or "-", **cut)

    @staticmethod
    def finished_lines(cards: tuple[InfiniteResultCard, ...]) -> str:
        """Return one short line per finished pair (name, status, verdict, and entry ids), or "-" when none finished."""
        return "\n".join(INFINITE_FINISHED_PAIR_LINE.format(name=card.name, status=card.status.value, verdict=card.verdict.value, entries=", ".join(f"#{number}" for number in card.entries) or "-") for card in cards) or "-"


__all__ = ["InfiniteLaunchTool", "InfinitePair"]
