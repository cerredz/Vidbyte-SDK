"""FILE: vidbyte/agents/infinite/events.py

PURPOSE: Defines InfiniteEvents, the single writer of an InfiniteMemory run's live events: one method per event kind builds a capped, typed InfiniteEvent and hands it to the developer's on_event sink, without ever letting the sink or the event's own construction change the run.
ROLE IN CODEBASE: Built once per run by InfiniteMemoryRuntime.arun (runtime.py), and once per run_handoff call by InfiniteMemoryAgent.run_handoff (agent.py), with the settings' on_event and the journal's run id, and handed explicitly to the root's InfiniteAgentMemory and InfiniteLaunchTool, to every child launch tool, and to every pair's memories (launch.py, memory.py). The records it builds live in vidbyte/lib/dataclasses/infinite.py; the caps, the key rule, and the summary templates in vidbyte/lib/constants/infinite.py. The CLI and dashboard consumers serialize each event with dataclasses.asdict.
ARCHITECTURE NOTE: Delivery is synchronous and inline, on the thread that runs the agent's event loop, at the point the change it reports is already on disk, so events arrive in the order they happen (spec INV-4, INV-5). Every public method returns at once when there is no sink, so a run without one builds nothing and logs nothing. Otherwise it runs under the _shielded context manager, builds its details with flat private helpers (cut one text, cut one list, shorten one key, label one agent, sum usage, clamp one count, pick a launcher's role, name a refusal's rule, read an agent's quota), and calls _deliver; no helper calls another helper of this class.
FUNCTION INVENTORY: run_started, run_resumed, run_finished, run_stopped (the run's life, from the runtime); agent_progress and workspace_usage (the root's tool iterations, from the runtime); handoff_written (from InfiniteMemoryAgent.run_handoff); batch_rejected (from the launch tool, a pair, and the runtime); batch_finished, subagent_launched, subagent_replayed (from the launch tool); generator_finished, verifier_started, verifier_finished, memory_committed, subagent_finished, subagent_aborted (from a pair); memory_saved, memory_staged, file_written, tool_refused (from the memory tools); memory_dropped (from the memory tools and a pair). _shielded catches, counts, and logs a failure; _deliver stamps, builds, and hands over one event and refuses a returned coroutine; _cut, _items, _key, _label, _usage, _count, _launcher_role, _rule, and _quota are the flat helpers.
COMMON MODIFICATION PATTERNS: A new event kind is one InfiniteEventKind member, one details record and DETAILS_TYPES entry in vidbyte/lib/dataclasses/infinite.py, one summary template and any new cap in vidbyte/lib/constants/infinite.py, one public method here shaped like the others, and one call at the point the change is durable.
WHAT NOT TO DO IN THIS FILE: 1. Do not catch BaseException; a KeyboardInterrupt or CancelledError raised by a sink must stop the run. 2. Do not log an exception message, a summary, or any details text; the log names the run id, the kind, and the exception's class only. 3. Do not call a model, write a file, or read settings secrets here. 4. Do not emit an event before the change it reports is on disk. 5. Do not cut a key with the truncation marker; keys are shortened by digest. 6. Do not await, schedule, or keep a coroutine a sink returns.
KNOWN EDGE CASES: A sink that raises KeyboardInterrupt stops the run (spec EC-2). A slow sink slows the run, because delivery is synchronous (EC-9). One agent run from two threads calls the sink from both, told apart by run_id (EC-10). Pairs that keep running after an error escaped their batch can deliver events after run_finished or run_stopped (EC-12). A pair key over 508 characters is shortened to ~ plus 16 hexadecimal digits of its SHA-256, a slash, and its last 490 characters, and its agents' keys add /gen or /ver (EC-30). A sink that returns a coroutine has it closed and logged as a TypeError, while a returned Task or Future is ignored (EC-32). A reply without a UsageRollup counts 0 tokens and an unknown cost. On cancellation, a pair waiting on its own nested batch may announce its abort after run_stopped (derived-events EC-3), and a pair cancelled before its first step announces no abort and stays in flight (derived-events EC-4). A sink that raises KeyboardInterrupt on subagent_finished gets subagent_aborted for the same pair, which then leaves in_flight only once (derived-events EC-10). Pair events after run_finished are counted in events_failed only if they fail, and never in that event's total (derived-events EC-17). A batch whose pipeline raises gets no batch_finished (derived-events EC-26). A note name or description with a line break can imitate the map's closing line and falsify workspace_usage's map_omitted (derived-events EC-28).
RELATED DOCS: docs/spec/infinite-memory-events/spec.md (sections 6.1, 8.5, and 9.1); docs/spec/infinite-memory-derived-events/spec.md (sections 6.1, 8.5, and 9.1); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_events_stream.py, test_infinite_memory_events_pairs.py, test_infinite_memory_events_lifecycle.py, test_infinite_memory_events_records.py, and the four test_infinite_memory_derived_*.py files
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.lib.constants.infinite import (
    INFINITE_DENIAL_LIMIT_METADATA_KEY,
    INFINITE_DENIAL_REASON_METADATA_KEY,
    INFINITE_DEPTH_STEP,
    INFINITE_EVENT_AGENT_PROGRESS_SUMMARY,
    INFINITE_EVENT_BATCH_FINISHED_SUMMARY,
    INFINITE_EVENT_FILE_CREATED_SUMMARY,
    INFINITE_EVENT_FILE_WRITTEN_SUMMARY,
    INFINITE_EVENT_GENERATOR_FINISHED_SUMMARY,
    INFINITE_EVENT_HANDOFF_WRITTEN_SUMMARY,
    INFINITE_EVENT_KEY_DIGEST_CHARS,
    INFINITE_EVENT_KEY_DIGEST_MARK,
    INFINITE_EVENT_KEY_MAX_CHARS,
    INFINITE_EVENT_LABEL_MAX_CHARS,
    INFINITE_EVENT_LINE_MAX_CHARS,
    INFINITE_EVENT_MAX_COUNT,
    INFINITE_EVENT_MAX_ITEMS,
    INFINITE_EVENT_MEMORY_COMMITTED_SUMMARY,
    INFINITE_EVENT_MEMORY_DROPPED_SUMMARY,
    INFINITE_EVENT_MEMORY_SAVED_SUMMARY,
    INFINITE_EVENT_MEMORY_STAGED_SUMMARY,
    INFINITE_EVENT_MICROSECONDS_PER_MILLISECOND,
    INFINITE_EVENT_MILLISECONDS_PER_SECOND,
    INFINITE_EVENT_PATH_MAX_CHARS,
    INFINITE_EVENT_PERCENT_SCALE,
    INFINITE_EVENT_PROGRESS_ITERATIONS,
    INFINITE_EVENT_REFUSED_SUMMARY,
    INFINITE_EVENT_RUN_FINISHED_SUMMARY,
    INFINITE_EVENT_RUN_RESUMED_SUMMARY,
    INFINITE_EVENT_RUN_STARTED_SUMMARY,
    INFINITE_EVENT_RUN_STOPPED_SUMMARY,
    INFINITE_EVENT_SUBAGENT_ABORTED_SUMMARY,
    INFINITE_EVENT_SUBAGENT_FINISHED_SUMMARY,
    INFINITE_EVENT_SUBAGENT_LAUNCHED_SUMMARY,
    INFINITE_EVENT_SUBAGENT_REPLAYED_SUMMARY,
    INFINITE_EVENT_SUMMARY_MAX_CHARS,
    INFINITE_EVENT_TEXT_MAX_CHARS,
    INFINITE_EVENT_USAGE_PERCENTS,
    INFINITE_EVENT_VERIFIER_FINISHED_SUMMARY,
    INFINITE_EVENT_VERIFIER_STARTED_SUMMARY,
    INFINITE_EVENT_WORKSPACE_USAGE_SUMMARY,
    INFINITE_GENERATOR_KEY,
    INFINITE_HANDOFF_OUTCOME_MAX_CHARS,
    INFINITE_HANDOFF_SECTION_MAX_CHARS,
    INFINITE_ITERATIONS_METADATA_KEY,
    INFINITE_KEY_SEGMENTS_PER_DEPTH,
    INFINITE_LAUNCH_TOOL_NAME,
    INFINITE_MIN_COUNT,
    INFINITE_NEW_FILES_PER_AGENT,
    INFINITE_REFUSAL_RULE_DETAILS_KEY,
    INFINITE_ROOT_DEPTH,
    INFINITE_ROOT_KEY,
    INFINITE_STOP_REASON_METADATA_KEY,
    INFINITE_TOOL_CALLS_METADATA_KEY,
    INFINITE_TRUNCATION_MARKER,
    INFINITE_USAGE_METADATA_KEY,
    INFINITE_VERIFIER_KEY,
)
from vidbyte.lib.dataclasses.infinite import (
    InfiniteAgentProgressDetails,
    InfiniteBatchFinishedDetails,
    InfiniteDroppedEntry,
    InfiniteEntry,
    InfiniteEvent,
    InfiniteEventDetails,
    InfiniteFileWrittenDetails,
    InfiniteGeneratorFinishedDetails,
    InfiniteHandoffWrittenDetails,
    InfiniteMemoryCommittedDetails,
    InfiniteMemoryDroppedDetails,
    InfiniteMemorySavedDetails,
    InfiniteMemoryStagedDetails,
    InfiniteRefusalDetails,
    InfiniteResultCard,
    InfiniteRunFinishedDetails,
    InfiniteRunResumedDetails,
    InfiniteRunStartedDetails,
    InfiniteRunStoppedDetails,
    InfiniteStagedEntry,
    InfiniteSubagentAbortedDetails,
    InfiniteSubagentFinishedDetails,
    InfiniteSubagentLaunchedDetails,
    InfiniteSubagentReplayedDetails,
    InfiniteTaskCard,
    InfiniteVerifierFinishedDetails,
    InfiniteVerifierStartedDetails,
    InfiniteWorkspaceUsageDetails,
)
from vidbyte.lib.dataclasses.tools import ToolCallContext
from vidbyte.lib.enums.infinite import (
    InfiniteAgentRole,
    InfiniteEventKind,
    InfiniteFileChange,
    InfinitePairPhase,
    InfiniteRefusalRule,
    InfiniteRefusalSource,
    InfiniteResultStatus,
    InfiniteStopCause,
    InfiniteVerdict,
)
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.outputs.text import OutputText

if TYPE_CHECKING:
    from vidbyte.agents.infinite.journal import InfiniteRunJournal
    from vidbyte.agents.infinite.launch import InfiniteLaunchTool, InfinitePair
    from vidbyte.agents.infinite.memory import InfiniteAgentMemory
    from vidbyte.agents.infinite.settings import InfiniteMemoryAgentSettings
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
    from vidbyte.context.handoff.infinite import InfiniteHandoff
    from vidbyte.lib.dataclasses.agents import AgentMessage
    from vidbyte.lib.dataclasses.strategies import AgentResult

logger = logging.getLogger(__name__)
ItemT = TypeVar("ItemT")


class InfiniteEvents:
    """The single writer of one run's events: one method per kind, each delivered to the sink at once and never allowed to change the run."""

    def __init__(self, on_event: Callable[[InfiniteEvent], None] | None, run_id: str) -> None:
        # The sink's return value is only inspected for a coroutine, so
        # it is held as returning anything.
        self.on_event: Callable[[InfiniteEvent], object] | None = on_event
        self.run_id = run_id
        # When each pair or verifier started, by key, for its duration.
        self._launched: dict[str, float] = {}
        # The pairs launched and not yet ended here, never below 0.
        self._in_flight = INFINITE_MIN_COUNT
        # The events dropped because building or delivering them
        # failed, for run_finished and run_stopped.
        self._failures = INFINITE_MIN_COUNT
        # When this writer was built, for the session's duration.
        self._opened = time.monotonic()
        # The last workspace level and map-cut state offered, so
        # usage is announced only when one of them changes.
        self._level = (INFINITE_MIN_COUNT, False)

    def run_started(self, settings: InfiniteMemoryAgentSettings, task: str, extras: tuple[str, ...]) -> None:
        """Announce a new run: the task, the model, the preset, the limits, the root's extra tools, and the seed file names."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.RUN_STARTED):
            # Only names leave the settings: never keys, the system
            # prompt, or a folder path.
            extras_shown, extras_omitted = self._items(extras)
            seeds_shown, seeds_omitted = self._items(tuple(Path(seed).name for seed in settings.workspace.seed_files))
            iterations = settings.loop.max_iterations
            details = InfiniteRunStartedDetails(
                task=self._cut(task, INFINITE_EVENT_TEXT_MAX_CHARS), model=self._cut(settings.model_name, INFINITE_EVENT_LINE_MAX_CHARS, collapse=True), preset=settings.workspace.preset,
                max_depth=self._count(settings.max_depth), max_parallel=self._count(settings.max_parallel), max_agents=self._count(settings.max_agents), max_iterations=None if iterations is None else self._count(iterations),
                extras=tuple(self._cut(name, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True) for name in extras_shown), extras_omitted=extras_omitted,
                seeds=tuple(self._cut(name, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True) for name in seeds_shown), seeds_omitted=seeds_omitted,
            )
            summary = self._cut(INFINITE_EVENT_RUN_STARTED_SUMMARY.format(task=task), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.RUN_STARTED, INFINITE_ROOT_KEY, InfiniteAgentRole.ROOT, INFINITE_ROOT_DEPTH, summary, details)

    def run_resumed(self, journal: InfiniteRunJournal) -> None:
        """Announce a resumed run: its task, how many pairs finished earlier, and which started pairs will run again."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.RUN_RESUMED):
            interrupted = journal.interrupted
            shown, omitted = self._items(interrupted)
            details = InfiniteRunResumedDetails(task=self._cut(journal.task, INFINITE_EVENT_TEXT_MAX_CHARS), finished=self._count(len(journal.cards)), interrupted=tuple(self._key(key) for key in shown), interrupted_omitted=omitted)
            summary = self._cut(INFINITE_EVENT_RUN_RESUMED_SUMMARY.format(finished=len(journal.cards), interrupted=len(interrupted)), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.RUN_RESUMED, INFINITE_ROOT_KEY, InfiniteAgentRole.ROOT, INFINITE_ROOT_DEPTH, summary, details)

    def run_finished(self, journal: InfiniteRunJournal, result: AgentResult, workspace: InfiniteWorkspace) -> None:
        """Announce a run whose journal is closed: its stop reason, the root's answer, the pairs and agents, the run's usage, the whole run's verdicts, committed entries, created notes, and deepest pair, this session's iterations, tool calls, and duration, and the events that failed."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.RUN_FINISHED):
            # The usage is the root's rollup, into which every child's
            # usage merged as it finished.
            stop_reason, answer = journal.stop_reason or "", journal.answer or ""
            tokens, cost = self._usage((result.metadata.get(INFINITE_USAGE_METADATA_KEY),))
            # The verdicts, entries, created notes, and deepest pair
            # cover the whole run across resumes, from the journal and
            # files.jsonl; the iterations, tool calls, and duration
            # cover this session, from the root's result and this
            # writer.
            cards = journal.cards
            verdicts = Counter(card.verdict for card in cards)
            deepest = max((len(key.split("/")) // INFINITE_KEY_SEGMENTS_PER_DEPTH for key in journal.started), default=INFINITE_MIN_COUNT)
            duration = int((time.monotonic() - self._opened) * INFINITE_EVENT_MILLISECONDS_PER_SECOND)
            details = InfiniteRunFinishedDetails(
                stop_reason=self._cut(stop_reason, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True), answer=self._cut(answer, INFINITE_EVENT_TEXT_MAX_CHARS),
                pairs=self._count(len(cards)), agents=self._count(journal.agents_started), tokens=tokens, cost_usd=cost,
                iterations=self._count(result.metadata.get(INFINITE_ITERATIONS_METADATA_KEY, INFINITE_MIN_COUNT)), tool_calls=self._count(result.metadata.get(INFINITE_TOOL_CALLS_METADATA_KEY, INFINITE_MIN_COUNT)), duration_ms=self._count(duration),
                passed=verdicts[InfiniteVerdict.PASSED], fixed=verdicts[InfiniteVerdict.FIXED], failed=verdicts[InfiniteVerdict.FAILED], unchecked=verdicts[InfiniteVerdict.UNCHECKED],
                committed=self._count(sum(len(card.entries) for card in cards)), files=self._count(len(workspace.descriptions(journal.run_id))), deepest=self._count(deepest), events_failed=self._count(self._failures),
            )
            summary = self._cut(INFINITE_EVENT_RUN_FINISHED_SUMMARY.format(stop_reason=stop_reason, answer=answer), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.RUN_FINISHED, INFINITE_ROOT_KEY, InfiniteAgentRole.ROOT, INFINITE_ROOT_DEPTH, summary, details)

    def run_stopped(self, error: BaseException) -> None:
        """Announce a run that raised after it opened: failed for an Exception, cancelled for any other BaseException, with the events that failed so far."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.RUN_STOPPED):
            reason = InfiniteStopCause.FAILED if isinstance(error, Exception) else InfiniteStopCause.CANCELLED
            error_type = type(error).__name__
            details = InfiniteRunStoppedDetails(reason=reason, error_type=self._cut(error_type, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True), message=self._cut(str(error), INFINITE_EVENT_TEXT_MAX_CHARS), events_failed=self._count(self._failures))
            summary = self._cut(INFINITE_EVENT_RUN_STOPPED_SUMMARY.format(reason=reason.value, error_type=error_type), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.RUN_STOPPED, INFINITE_ROOT_KEY, InfiniteAgentRole.ROOT, INFINITE_ROOT_DEPTH, summary, details)

    def agent_progress(self, settings: InfiniteMemoryAgentSettings, state: BaseAgentRuntimeLoopState) -> None:
        """Announce the root's progress every tenth tool iteration: the iteration, its cap, and the root's own model calls, tool calls, and tokens so far."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.AGENT_PROGRESS):
            # Only every tenth iteration is announced, so a long run
            # gives a steady heartbeat, never a flood.
            if state.iteration_count % INFINITE_EVENT_PROGRESS_ITERATIONS:
                return
            iterations = settings.loop.max_iterations
            details = InfiniteAgentProgressDetails(
                iteration=self._count(state.iteration_count), max_iterations=None if iterations is None else self._count(iterations),
                model_calls=self._count(state.model_call_count), tool_calls=self._count(state.tool_call_count), tokens=self._count(state.tokens_used or INFINITE_MIN_COUNT),
            )
            summary = self._cut(INFINITE_EVENT_AGENT_PROGRESS_SUMMARY.format(agent=INFINITE_ROOT_KEY, iteration=details.iteration, model_calls=details.model_calls, tool_calls=details.tool_calls), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.AGENT_PROGRESS, INFINITE_ROOT_KEY, InfiniteAgentRole.ROOT, INFINITE_ROOT_DEPTH, summary, details)

    def workspace_usage(self, workspace: InfiniteWorkspace, map_text: str) -> None:
        """Announce a change in the workspace's usage level or in whether the root's map is cut, with the files and tokens against their caps and the files the map leaves out."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.WORKSPACE_USAGE):
            # @intent usage-is-announced-on-change
            # The workspace is scanned again only because a sink
            # listens. The level is the highest percent of either cap
            # reached, in whole numbers; only a change in the level or
            # in the map's cut state is announced, and the new state is
            # kept before delivery, so a failing sink is not offered
            # the same change again.
            usage, settings = workspace.usage(), workspace.settings
            level = max((percent for percent in INFINITE_EVENT_USAGE_PERCENTS if usage.files * INFINITE_EVENT_PERCENT_SCALE >= percent * settings.max_files or usage.tokens * INFINITE_EVENT_PERCENT_SCALE >= percent * settings.max_tokens), default=INFINITE_MIN_COUNT)
            omitted = workspace.map_omitted(map_text)
            if (level, omitted > INFINITE_MIN_COUNT) == self._level:
                return
            self._level = (level, omitted > INFINITE_MIN_COUNT)
            details = InfiniteWorkspaceUsageDetails(level=level, files=self._count(usage.files), max_files=self._count(settings.max_files), tokens=self._count(usage.tokens), max_tokens=self._count(settings.max_tokens), map_omitted=self._count(omitted))
            summary = self._cut(INFINITE_EVENT_WORKSPACE_USAGE_SUMMARY.format(level=level, files=usage.files, max_files=settings.max_files, tokens=usage.tokens, max_tokens=settings.max_tokens), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.WORKSPACE_USAGE, INFINITE_ROOT_KEY, InfiniteAgentRole.ROOT, INFINITE_ROOT_DEPTH, summary, details)

    def handoff_written(self, workspace: InfiniteWorkspace, target: Path, handoff: InfiniteHandoff) -> None:
        """Announce a handoff saved to disk: its workspace-relative path, each section's length in order, and the sections cut to their caps."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.HANDOFF_WRITTEN):
            # A section that ends with the marker at exactly a handoff
            # cap was cut; the path is relative, never absolute.
            path = target.relative_to(workspace.root).as_posix()
            cut = tuple(title for title, text in handoff.sections.items() if text.endswith(INFINITE_TRUNCATION_MARKER) and len(text) in (INFINITE_HANDOFF_OUTCOME_MAX_CHARS, INFINITE_HANDOFF_SECTION_MAX_CHARS))
            shown, omitted = self._items(cut)
            details = InfiniteHandoffWrittenDetails(path=self._cut(path, INFINITE_EVENT_PATH_MAX_CHARS), sections=tuple(self._count(len(text)) for text in handoff.sections.values()), cut=tuple(self._cut(title, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True) for title in shown), cut_omitted=omitted)
            summary = self._cut(INFINITE_EVENT_HANDOFF_WRITTEN_SUMMARY.format(path=path), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.HANDOFF_WRITTEN, INFINITE_ROOT_KEY, InfiniteAgentRole.ROOT, INFINITE_ROOT_DEPTH, summary, details)

    def batch_rejected(self, launch: InfiniteLaunchTool | InfiniteAgentMemory, refused: VidbyteSdkError | ToolCallContext) -> None:
        """Announce a refused launch_subagent batch: by the launch tool, from its error, or by a middleware, from the denied call's record; with the rule it broke and the problem the launching model was told."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.BATCH_REJECTED):
            # A middleware's problem is the reason in the denied call's
            # result, or the result's text when it gives no reason; the
            # launching agent is the root or a generator.
            if isinstance(refused, ToolCallContext):
                problem = "" if refused.result is None else str(refused.result.metadata.get(INFINITE_DENIAL_REASON_METADATA_KEY) or refused.result.output)
                source = InfiniteRefusalSource.MIDDLEWARE
            else:
                problem, source = refused.message, InfiniteRefusalSource.TOOL
            role = self._launcher_role(launch.key)
            details = InfiniteRefusalDetails(tool=INFINITE_LAUNCH_TOOL_NAME, problem=self._cut(problem, INFINITE_EVENT_TEXT_MAX_CHARS), rule=self._rule(refused), source=source)
            summary = self._cut(INFINITE_EVENT_REFUSED_SUMMARY.format(tool=INFINITE_LAUNCH_TOOL_NAME, agent=self._label(launch.key), problem=problem), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.BATCH_REJECTED, self._key(launch.key, role), role, self._count(launch.depth), summary, details)

    def batch_finished(self, launch: InfiniteLaunchTool, batch: int, pairs: Sequence[InfinitePair], replayed: int, started: float) -> None:
        """Announce a batch whose pipeline returned: its offset, its pairs' verdict counts, its replays, and its duration."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.BATCH_FINISHED):
            # Every pair of a returned batch has its card; a replay
            # started nothing, so it is only counted.
            verdicts = Counter(pair.result.verdict for pair in pairs if pair.result is not None)
            role = self._launcher_role(launch.key)
            duration = int((time.monotonic() - started) * INFINITE_EVENT_MILLISECONDS_PER_SECOND)
            details = InfiniteBatchFinishedDetails(
                batch=self._count(batch), passed=verdicts[InfiniteVerdict.PASSED], fixed=verdicts[InfiniteVerdict.FIXED], failed=verdicts[InfiniteVerdict.FAILED], unchecked=verdicts[InfiniteVerdict.UNCHECKED],
                replayed=self._count(replayed), duration_ms=self._count(duration),
            )
            summary = self._cut(
                INFINITE_EVENT_BATCH_FINISHED_SUMMARY.format(agent=self._label(launch.key), batch=batch, passed=details.passed, fixed=details.fixed, failed=details.failed, unchecked=details.unchecked, replayed=replayed), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True
            )
            self._deliver(InfiniteEventKind.BATCH_FINISHED, self._key(launch.key, role), role, self._count(launch.depth), summary, details)

    def subagent_launched(self, launch: InfiniteLaunchTool, card: InfiniteTaskCard, batch: int, index: int, size: int) -> None:
        """Announce a new pair whose pair_started record is on disk: its name, keys, depth, task card cut to the event caps, attempt, place in its batch, and the tree's agents and pairs in flight."""
        if self.on_event is None:
            return
        # The pair counts as in flight before anything that can fail,
        # so a sink that raises on this event cannot leave it out.
        self._in_flight += 1
        with self._shielded(InfiniteEventKind.SUBAGENT_LAUNCHED):
            # @intent an-attempt-counts-journal-starts
            # Start the clock for this pair's generator duration. Its
            # attempt is how many times the journal recorded it
            # started, this start included, so a pair run again after
            # a resume reads 2.
            pair_key = f"{launch.key}/{card.name}"
            self._launched[pair_key] = time.monotonic()
            role = self._launcher_role(launch.key)
            parent = self._key(launch.key, role)
            criteria, criteria_omitted = self._items(card.done_criteria)
            context, context_omitted = self._items(card.context)
            tools, tools_omitted = self._items(card.tools)
            details = InfiniteSubagentLaunchedDetails(
                name=card.name, key=self._key(pair_key), parent=parent, depth=self._count(launch.depth + INFINITE_DEPTH_STEP), goal=self._cut(card.goal, INFINITE_EVENT_TEXT_MAX_CHARS),
                done_criteria=tuple(self._cut(item, INFINITE_EVENT_LINE_MAX_CHARS) for item in criteria), done_criteria_omitted=criteria_omitted,
                generator_prompt=self._cut(card.generator_prompt, INFINITE_EVENT_LINE_MAX_CHARS), verifier_prompt=self._cut(card.verifier_prompt, INFINITE_EVENT_LINE_MAX_CHARS),
                context=tuple(self._cut(item, INFINITE_EVENT_LABEL_MAX_CHARS) for item in context), context_omitted=context_omitted,
                tools=tuple(self._cut(item, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True) for item in tools), tools_omitted=tools_omitted,
                attempt=self._count(launch.journal.started.count(pair_key)), batch=self._count(batch), batch_index=self._count(index), batch_size=self._count(size),
                agents_started=self._count(launch.journal.agents_started), max_agents=self._count(launch.settings.max_agents), in_flight=self._count(self._in_flight),
            )
            summary = self._cut(INFINITE_EVENT_SUBAGENT_LAUNCHED_SUMMARY.format(agent=self._label(launch.key), name=card.name, goal=card.goal), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.SUBAGENT_LAUNCHED, parent, role, self._count(launch.depth), summary, details)

    def subagent_replayed(self, launch: InfiniteLaunchTool, card: InfiniteResultCard) -> None:
        """Announce a task whose name already finished in this run, so its recorded card is returned and nothing runs."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.SUBAGENT_REPLAYED):
            role = self._launcher_role(launch.key)
            details = InfiniteSubagentReplayedDetails(name=card.name, key=self._key(card.key), status=card.status, verdict=card.verdict)
            summary = self._cut(INFINITE_EVENT_SUBAGENT_REPLAYED_SUMMARY.format(agent=self._label(launch.key), name=card.name), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.SUBAGENT_REPLAYED, self._key(launch.key, role), role, self._count(launch.depth), summary, details)

    def generator_finished(self, memory: InfiniteAgentMemory, reply: AgentMessage, status: InfiniteResultStatus, summary: str) -> None:
        """Announce a generator's reply: its status, stop reason, cut summary, tool calls, usage, and time since its pair launched."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.GENERATOR_FINISHED):
            # A pair launched before this object existed has no start
            # time, so its duration is reported as 0.
            launched = self._launched.pop(memory.key.removesuffix(f"/{INFINITE_GENERATOR_KEY}"), None)
            duration = INFINITE_MIN_COUNT if launched is None else int((time.monotonic() - launched) * INFINITE_EVENT_MILLISECONDS_PER_SECOND)
            tokens, cost = self._usage((reply.metadata.get(INFINITE_USAGE_METADATA_KEY),))
            details = InfiniteGeneratorFinishedDetails(
                status=status, stop_reason=self._cut(str(reply.metadata.get(INFINITE_STOP_REASON_METADATA_KEY, "")), INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True), summary=self._cut(summary, INFINITE_EVENT_TEXT_MAX_CHARS),
                tool_calls=self._count(reply.metadata.get(INFINITE_TOOL_CALLS_METADATA_KEY, INFINITE_MIN_COUNT)), tokens=tokens, cost_usd=cost, duration_ms=self._count(duration),
            )
            text = self._cut(INFINITE_EVENT_GENERATOR_FINISHED_SUMMARY.format(agent=self._label(memory.key), status=status.value, summary=summary), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.GENERATOR_FINISHED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), text, details)

    def verifier_started(self, memory: InfiniteAgentMemory, staged: Sequence[InfiniteStagedEntry], files: Sequence[str]) -> None:
        """Announce a verifier about to check its pair: how many entries are staged, and the notes the generator wrote."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.VERIFIER_STARTED):
            # Start the clock for the verifier's duration. The summary
            # counts every note written, not only the five shown.
            self._launched[memory.key] = time.monotonic()
            shown, omitted = self._items(files)
            details = InfiniteVerifierStartedDetails(staged=self._count(len(staged)), files=tuple(self._cut(path, INFINITE_EVENT_LINE_MAX_CHARS) for path in shown), files_omitted=omitted)
            summary = self._cut(INFINITE_EVENT_VERIFIER_STARTED_SUMMARY.format(agent=self._label(memory.key), staged=len(staged), files=len(files)), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.VERIFIER_STARTED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def verifier_finished(self, memory: InfiniteAgentMemory, reply: AgentMessage, verdict: InfiniteVerdict) -> None:
        """Announce a verifier's reply: its verdict, stop reason, tool calls, usage, and time since it started."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.VERIFIER_FINISHED):
            # A verifier whose start was not seen reports 0 ms.
            started = self._launched.pop(memory.key, None)
            duration = INFINITE_MIN_COUNT if started is None else int((time.monotonic() - started) * INFINITE_EVENT_MILLISECONDS_PER_SECOND)
            tokens, cost = self._usage((reply.metadata.get(INFINITE_USAGE_METADATA_KEY),))
            details = InfiniteVerifierFinishedDetails(
                verdict=verdict, stop_reason=self._cut(str(reply.metadata.get(INFINITE_STOP_REASON_METADATA_KEY, "")), INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True),
                tool_calls=self._count(reply.metadata.get(INFINITE_TOOL_CALLS_METADATA_KEY, INFINITE_MIN_COUNT)), tokens=tokens, cost_usd=cost, duration_ms=self._count(duration),
            )
            summary = self._cut(INFINITE_EVENT_VERIFIER_FINISHED_SUMMARY.format(agent=self._label(memory.key), verdict=verdict.value), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.VERIFIER_FINISHED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def subagent_finished(self, pair: InfinitePair, card: InfiniteResultCard) -> None:
        """Announce a pair whose card is journaled: its outcome, cut review, committed and dropped entries, notes, usage, the class of the error its card reports, and the tree's agents and pairs in flight."""
        if self.on_event is None:
            return
        # The pair leaves the count before anything that can fail, so
        # a sink that raises on this event cannot keep it counted.
        self._in_flight = max(self._in_flight - 1, INFINITE_MIN_COUNT)
        with self._shielded(InfiniteEventKind.SUBAGENT_FINISHED):
            # Each list shows its first five items, cut to the event
            # caps, and counts the rest; the summary counts every item.
            # Notes are named once each, by their workspace-relative
            # path.
            launch = pair.launch
            role = self._launcher_role(launch.key)
            files = tuple(dict.fromkeys(launch.workspace.relative(path) for path in card.files))
            committed, committed_omitted = self._items(pair.committed)
            dropped, dropped_omitted = self._items(pair.dropped)
            files_shown, files_omitted = self._items(files)
            tokens, cost = self._usage(tuple(reply.metadata.get(INFINITE_USAGE_METADATA_KEY) for reply in pair.replies))
            details = InfiniteSubagentFinishedDetails(
                name=card.name,
                key=self._key(card.key),
                status=card.status,
                verdict=card.verdict,
                review=self._cut(card.review, INFINITE_EVENT_TEXT_MAX_CHARS),
                committed=tuple(replace(item, text=self._cut(item.text, INFINITE_EVENT_LABEL_MAX_CHARS)) for item in committed),
                committed_omitted=committed_omitted,
                dropped=tuple(replace(item, text=self._cut(item.text, INFINITE_EVENT_LABEL_MAX_CHARS), note=self._cut(item.note, INFINITE_EVENT_LABEL_MAX_CHARS)) for item in dropped),
                dropped_omitted=dropped_omitted,
                files=tuple(self._cut(path, INFINITE_EVENT_LINE_MAX_CHARS) for path in files_shown),
                files_omitted=files_omitted,
                tokens=tokens,
                cost_usd=cost,
                error_type="" if pair.error is None else self._cut(type(pair.error.__cause__ or pair.error).__name__, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True),
                agents_started=self._count(launch.journal.agents_started),
                max_agents=self._count(launch.settings.max_agents),
                in_flight=self._count(self._in_flight),
            )
            summary = self._cut(INFINITE_EVENT_SUBAGENT_FINISHED_SUMMARY.format(name=card.name, verdict=card.verdict.value, committed=len(pair.committed), dropped=len(pair.dropped), files=len(files)), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.SUBAGENT_FINISHED, self._key(launch.key, role), role, self._count(launch.depth), summary, details)

    def subagent_aborted(self, pair: InfinitePair, error: BaseException, phase: InfinitePairPhase) -> None:
        """Announce a pair that stopped without its card: failed for an Exception, cancelled otherwise, with the error's class, the step it stopped in, and the entries still staged."""
        if self.on_event is None:
            return
        # A pair whose finish was already announced left the count
        # then, so only a pair the journal has not finished leaves it
        # now, before anything that can fail.
        if pair.launch.journal.finished(pair.key) is None:
            self._in_flight = max(self._in_flight - 1, INFINITE_MIN_COUNT)
        with self._shielded(InfiniteEventKind.SUBAGENT_ABORTED):
            # The error is named by its cause's class when it wraps
            # one, as the pair's review text names it.
            launch = pair.launch
            role = self._launcher_role(launch.key)
            reason = InfiniteStopCause.FAILED if isinstance(error, Exception) else InfiniteStopCause.CANCELLED
            error_type = type(error.__cause__ or error).__name__
            details = InfiniteSubagentAbortedDetails(name=pair.card.name, key=self._key(pair.key), reason=reason, error_type=self._cut(error_type, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True), phase=phase, staged=self._count(len(pair.staged)))
            summary = self._cut(INFINITE_EVENT_SUBAGENT_ABORTED_SUMMARY.format(name=pair.card.name, reason=reason.value, phase=phase.value, error_type=error_type), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.SUBAGENT_ABORTED, self._key(launch.key, role), role, self._count(launch.depth), summary, details)

    def memory_saved(self, memory: InfiniteAgentMemory, entry: InfiniteEntry) -> None:
        """Announce an entry the root committed to entries.jsonl: its id, kind, cut text, tags, refs, the entry it replaced, and the root's quota left."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.MEMORY_SAVED):
            draft = entry.draft
            entries_left, entries_max, files_left, files_max = self._quota(memory)
            details = InfiniteMemorySavedDetails(
                id=self._count(entry.id), kind=draft.kind, text=self._cut(draft.text, INFINITE_EVENT_TEXT_MAX_CHARS), tags=draft.tags, refs=tuple(self._cut(ref, INFINITE_EVENT_LINE_MAX_CHARS) for ref in draft.refs), supersedes=draft.supersedes,
                entries_left=entries_left, entries_max=entries_max, files_left=files_left, files_max=files_max,
            )
            summary = self._cut(INFINITE_EVENT_MEMORY_SAVED_SUMMARY.format(id=entry.id, kind=draft.kind.value, text=draft.text), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.MEMORY_SAVED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def memory_staged(self, memory: InfiniteAgentMemory, staged: InfiniteStagedEntry) -> None:
        """Announce an entry a pair's agent staged for its verifier: its staged key, kind, cut text, the entry it would replace, and the agent's quota left."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.MEMORY_STAGED):
            draft = staged.draft
            entries_left, entries_max, files_left, files_max = self._quota(memory)
            details = InfiniteMemoryStagedDetails(
                key=staged.key, kind=draft.kind, text=self._cut(draft.text, INFINITE_EVENT_TEXT_MAX_CHARS), supersedes=draft.supersedes,
                entries_left=entries_left, entries_max=entries_max, files_left=files_left, files_max=files_max,
            )
            summary = self._cut(INFINITE_EVENT_MEMORY_STAGED_SUMMARY.format(agent=self._label(memory.key), key=staged.key, kind=draft.kind.value, text=draft.text), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.MEMORY_STAGED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def memory_committed(self, memory: InfiniteAgentMemory, staged: InfiniteStagedEntry, entry: InfiniteEntry) -> None:
        """Announce a staged entry committed to entries.jsonl after its verifier's pass: its new id, staged key, kind, cut text, and the entry it replaced."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.MEMORY_COMMITTED):
            draft = staged.draft
            details = InfiniteMemoryCommittedDetails(id=self._count(entry.id), key=staged.key, kind=draft.kind, text=self._cut(draft.text, INFINITE_EVENT_TEXT_MAX_CHARS), supersedes=draft.supersedes)
            summary = self._cut(INFINITE_EVENT_MEMORY_COMMITTED_SUMMARY.format(agent=self._label(memory.key), key=staged.key, id=entry.id, kind=draft.kind.value, text=draft.text), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.MEMORY_COMMITTED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def memory_dropped(self, memory: InfiniteAgentMemory, dropped: InfiniteDroppedEntry) -> None:
        """Announce a staged entry that was not committed: its staged key, a short cut of its text, the reason (the verifier, a rule, or no verdict), and the note."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.MEMORY_DROPPED):
            details = InfiniteMemoryDroppedDetails(key=dropped.key, text=self._cut(dropped.text, INFINITE_EVENT_LABEL_MAX_CHARS), reason=dropped.reason, note=self._cut(dropped.note, INFINITE_EVENT_LABEL_MAX_CHARS))
            summary = self._cut(INFINITE_EVENT_MEMORY_DROPPED_SUMMARY.format(agent=self._label(memory.key), key=dropped.key, text=dropped.text), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.MEMORY_DROPPED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def file_written(self, memory: InfiniteAgentMemory, path: str, change: InfiniteFileChange, text: str, description: str | None) -> None:
        """Announce a note whose new text is on disk: its workspace-relative path, the change, the characters written, an excerpt, a created note's description, and the agent's quota left."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.FILE_WRITTEN):
            relative = memory.workspace.relative(path)
            entries_left, entries_max, files_left, files_max = self._quota(memory)
            details = InfiniteFileWrittenDetails(
                path=self._cut(relative, INFINITE_EVENT_PATH_MAX_CHARS), change=change, added_chars=self._count(len(text)), excerpt=self._cut(text, INFINITE_EVENT_TEXT_MAX_CHARS), description=self._cut(description or "", INFINITE_EVENT_LINE_MAX_CHARS),
                entries_left=entries_left, entries_max=entries_max, files_left=files_left, files_max=files_max,
            )
            template = INFINITE_EVENT_FILE_CREATED_SUMMARY if change is InfiniteFileChange.CREATED and description else INFINITE_EVENT_FILE_WRITTEN_SUMMARY
            summary = self._cut(template.format(agent=self._label(memory.key), change=change.value, path=relative, description=description), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.FILE_WRITTEN, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def tool_refused(self, memory: InfiniteAgentMemory, tool: str, error: Exception) -> None:
        """Announce a memory tool call the tool itself refused, with the rule it broke and the problem the model was told."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.TOOL_REFUSED):
            details = InfiniteRefusalDetails(tool=self._cut(tool, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True), problem=self._cut(str(error), INFINITE_EVENT_TEXT_MAX_CHARS), rule=self._rule(error), source=InfiniteRefusalSource.TOOL)
            summary = self._cut(INFINITE_EVENT_REFUSED_SUMMARY.format(tool=tool, agent=self._label(memory.key), problem=str(error)), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.TOOL_REFUSED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    @contextmanager
    def _shielded(self, kind: InfiniteEventKind) -> Iterator[None]:
        # @intent a-broken-sink-never-breaks-the-run
        # Any Exception from building the event or from the sink drops
        # that one event and logs the run id, the kind, and the class
        # name only, never text that could hold a secret; each dropped
        # event is counted for events_failed. Interrupts and
        # cancellation are not Exceptions, so they still stop the run.
        try:
            yield
        except Exception as exc:
            self._failures += 1
            logger.warning("infinite_event_failed run_id=%s kind=%s error_type=%s", self.run_id, kind.value, type(exc).__name__)

    def _deliver(self, kind: InfiniteEventKind, agent_key: str, role: InfiniteAgentRole, depth: int, summary: str, details: InfiniteEventDetails) -> None:
        # Stamp the event in UTC to the millisecond, build it, and hand
        # it to the sink on this thread.
        now = datetime.now(timezone.utc)
        at = now.replace(microsecond=now.microsecond - now.microsecond % INFINITE_EVENT_MICROSECONDS_PER_MILLISECOND)
        event = InfiniteEvent(kind=kind, run_id=self.run_id, agent_key=agent_key, role=role, depth=depth, at=at, summary=summary, details=details)
        returned = self.on_event(event) if self.on_event is not None else None
        # @intent a-returned-coroutine-is-closed-never-awaited
        # A plain sink that returns a coroutine never ran its work, and
        # awaiting it here would break the order of events, so it is
        # closed and counted as a failure. A Task or Future the sink
        # scheduled itself is already running and is ignored.
        if inspect.iscoroutine(returned):
            returned.close()
            raise TypeError("on_event returned a coroutine; pass a plain function that only enqueues the event")

    @staticmethod
    def _cut(text: str, cap: int, *, collapse: bool = False) -> str:
        # @intent event-text-is-utf8-and-cut-with-one-marker
        # A lone surrogate becomes "?", so every event encodes as UTF-8;
        # a one-line field has every run of whitespace made one space;
        # then the text is cut to its cap, ending with the marker the
        # card texts in the same stream use.
        clean = text.encode("utf-8", errors="replace").decode("utf-8")
        return OutputText.truncate(" ".join(clean.split()) if collapse else clean, cap, marker=INFINITE_TRUNCATION_MARKER)

    @staticmethod
    def _items(values: Sequence[ItemT]) -> tuple[tuple[ItemT, ...], int]:
        # The first items of a list in their order, and how many more
        # there were, so a cut list is never lost silently.
        return tuple(values[:INFINITE_EVENT_MAX_ITEMS]), max(len(values) - INFINITE_EVENT_MAX_ITEMS, INFINITE_MIN_COUNT)

    @staticmethod
    def _key(key: str, role: InfiniteAgentRole | None = None) -> str:
        # @intent keys-are-bounded-by-digest-not-cut
        # A pair key over 508 characters becomes the mark, 16 hex digits
        # of its SHA-256, a slash, and its last 490 characters, so it
        # stays distinct and readable at its end. A generator or
        # verifier key keeps /gen or /ver after its shortened pair key,
        # so it still names its pair; root never changes.
        suffix = {InfiniteAgentRole.GENERATOR: f"/{INFINITE_GENERATOR_KEY}", InfiniteAgentRole.VERIFIER: f"/{INFINITE_VERIFIER_KEY}"}.get(role, "") if role is not None else ""
        pair = key.removesuffix(suffix) if suffix else key
        room = INFINITE_EVENT_KEY_MAX_CHARS - len(f"/{INFINITE_GENERATOR_KEY}")
        if len(pair) <= room:
            return key
        head = f"{INFINITE_EVENT_KEY_DIGEST_MARK}{hashlib.sha256(pair.encode('utf-8')).hexdigest()[:INFINITE_EVENT_KEY_DIGEST_CHARS]}/"
        return f"{head}{pair[len(pair) - room + len(head):]}{suffix}"

    @staticmethod
    def _label(key: str) -> str:
        # How a summary names an agent: root, or the last two segments
        # of its key, such as pricing/gen.
        return "/".join(key.split("/")[-2:])

    @staticmethod
    def _usage(rollups: Sequence[object]) -> tuple[int, float | None]:
        # @intent an-unknown-cost-is-none-never-zero
        # Tokens add up over every part's rollup; a part without one
        # counts none. The cost is the sum only when every part's cost
        # is complete, because a partly priced rollup understates it.
        tokens = sum(rollup.total_tokens or INFINITE_MIN_COUNT for rollup in rollups if isinstance(rollup, UsageRollup))
        known = bool(rollups) and all(isinstance(rollup, UsageRollup) and rollup.cost_complete and rollup.cost_usd is not None for rollup in rollups)
        cost = sum(rollup.cost_usd or float(INFINITE_MIN_COUNT) for rollup in rollups if isinstance(rollup, UsageRollup)) if known else None
        return min(tokens, INFINITE_EVENT_MAX_COUNT), cost

    @staticmethod
    def _count(value: int) -> int:
        # A count as an event carries it: a larger value is reported at
        # the largest count a backend stores as a 64-bit integer.
        return min(value, INFINITE_EVENT_MAX_COUNT)

    @staticmethod
    def _launcher_role(key: str) -> InfiniteAgentRole:
        # The agent holding a launch tool is the root or a generator.
        return InfiniteAgentRole.ROOT if key == INFINITE_ROOT_KEY else InfiniteAgentRole.GENERATOR

    @staticmethod
    def _rule(refused: BaseException | ToolCallContext) -> InfiniteRefusalRule:
        # @intent a-refusal-names-its-rule
        # The rule is read from what the refusal carries, never from
        # its text: a denial's limit, or the rule an error names in
        # its details. An error that names none is classed by its
        # type, and anything else is other.
        if isinstance(refused, ToolCallContext):
            named = None if refused.result is None else refused.result.metadata.get(INFINITE_DENIAL_LIMIT_METADATA_KEY)
        else:
            named = refused.details.get(INFINITE_REFUSAL_RULE_DETAILS_KEY) if isinstance(refused, VidbyteSdkError) else None
        try:
            return InfiniteRefusalRule(named)
        except ValueError:
            match refused:
                case ConfigurationError():
                    return InfiniteRefusalRule.INVALID_ARGUMENTS
                case UnicodeError():
                    return InfiniteRefusalRule.TEXT_ENCODING
                case OSError():
                    return InfiniteRefusalRule.DISK
                case _:
                    return InfiniteRefusalRule.OTHER

    @staticmethod
    def _quota(memory: InfiniteAgentMemory) -> tuple[int, int, int, int]:
        # An agent's entries and new files left of its allowance and
        # the allowance itself, as its quota line shows them, never
        # below 0 or above the count cap.
        entries_max = min(memory.workspace.settings.max_entries_per_agent, INFINITE_EVENT_MAX_COUNT)
        return max(entries_max - memory.accepted, INFINITE_MIN_COUNT), entries_max, max(INFINITE_NEW_FILES_PER_AGENT - memory.created, INFINITE_MIN_COUNT), INFINITE_NEW_FILES_PER_AGENT


__all__ = ["InfiniteEvents"]
