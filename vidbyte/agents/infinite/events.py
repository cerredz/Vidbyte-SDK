"""FILE: vidbyte/agents/infinite/events.py

PURPOSE: Defines InfiniteEvents, the single writer of an InfiniteMemory run's live events: one method per event kind builds a capped, typed InfiniteEvent and hands it to the developer's on_event sink, without ever letting the sink or the event's own construction change the run.
ROLE IN CODEBASE: Built once per run by InfiniteMemoryRuntime.arun (runtime.py) with the settings' on_event and the journal's run id, and handed explicitly to the root's InfiniteAgentMemory and InfiniteLaunchTool, to every child launch tool, and to every pair's memories (launch.py, memory.py). The records it builds live in vidbyte/lib/dataclasses/infinite.py; the caps, the key rule, and the summary templates in vidbyte/lib/constants/infinite.py. The CLI and dashboard consumers serialize each event with dataclasses.asdict.
ARCHITECTURE NOTE: Delivery is synchronous and inline, on the thread that runs the agent's event loop, at the point the change it reports is already on disk, so events arrive in the order they happen (spec INV-4, INV-5). Every public method returns at once when there is no sink, so a run without one builds nothing and logs nothing. Otherwise it runs under the _shielded context manager, builds its details with flat private helpers (cut one text, cut one list, shorten one key, label one agent, sum usage, clamp one count, pick a launcher's role), and calls _deliver; no helper calls another helper of this class.
FUNCTION INVENTORY: run_started, run_resumed, run_finished, run_stopped (the run's life, from the runtime); batch_rejected, subagent_launched, subagent_replayed (from the launch tool); generator_finished, subagent_finished (from a pair); memory_saved, memory_staged, memory_dropped, file_written, tool_refused (from the memory tools). _shielded catches and logs a failure; _deliver stamps, builds, and hands over one event and refuses a returned coroutine; _cut, _items, _key, _label, _usage, _count, and _launcher_role are the flat helpers.
COMMON MODIFICATION PATTERNS: A new event kind is one InfiniteEventKind member, one details record and DETAILS_TYPES entry in vidbyte/lib/dataclasses/infinite.py, one summary template and any new cap in vidbyte/lib/constants/infinite.py, one public method here shaped like the others, and one call at the point the change is durable.
WHAT NOT TO DO IN THIS FILE: 1. Do not catch BaseException; a KeyboardInterrupt or CancelledError raised by a sink must stop the run. 2. Do not log an exception message, a summary, or any details text; the log names the run id, the kind, and the exception's class only. 3. Do not call a model, write a file, or read settings secrets here. 4. Do not emit an event before the change it reports is on disk. 5. Do not cut a key with the truncation marker; keys are shortened by digest. 6. Do not await, schedule, or keep a coroutine a sink returns.
KNOWN EDGE CASES: A sink that raises KeyboardInterrupt stops the run (spec EC-2). A slow sink slows the run, because delivery is synchronous (EC-9). One agent run from two threads calls the sink from both, told apart by run_id (EC-10). Pairs that keep running after an error escaped their batch can deliver events after run_finished or run_stopped (EC-12). A pair key over 508 characters is shortened to ~ plus 16 hexadecimal digits of its SHA-256, a slash, and its last 490 characters, and its agents' keys add /gen or /ver (EC-30). A sink that returns a coroutine has it closed and logged as a TypeError, while a returned Task or Future is ignored (EC-32). A reply without a UsageRollup counts 0 tokens and an unknown cost.
RELATED DOCS: docs/spec/infinite-memory-events/spec.md (sections 6.1, 8.5, and 9.1); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_events_stream.py, test_infinite_memory_events_pairs.py, test_infinite_memory_events_lifecycle.py, and test_infinite_memory_events_records.py
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.lib.constants.infinite import (
    INFINITE_DEPTH_STEP,
    INFINITE_EVENT_FILE_CREATED_SUMMARY,
    INFINITE_EVENT_FILE_WRITTEN_SUMMARY,
    INFINITE_EVENT_GENERATOR_FINISHED_SUMMARY,
    INFINITE_EVENT_KEY_DIGEST_CHARS,
    INFINITE_EVENT_KEY_DIGEST_MARK,
    INFINITE_EVENT_KEY_MAX_CHARS,
    INFINITE_EVENT_LABEL_MAX_CHARS,
    INFINITE_EVENT_LINE_MAX_CHARS,
    INFINITE_EVENT_MAX_COUNT,
    INFINITE_EVENT_MAX_ITEMS,
    INFINITE_EVENT_MEMORY_DROPPED_SUMMARY,
    INFINITE_EVENT_MEMORY_SAVED_SUMMARY,
    INFINITE_EVENT_MEMORY_STAGED_SUMMARY,
    INFINITE_EVENT_MICROSECONDS_PER_MILLISECOND,
    INFINITE_EVENT_MILLISECONDS_PER_SECOND,
    INFINITE_EVENT_PATH_MAX_CHARS,
    INFINITE_EVENT_REFUSED_SUMMARY,
    INFINITE_EVENT_RUN_FINISHED_SUMMARY,
    INFINITE_EVENT_RUN_RESUMED_SUMMARY,
    INFINITE_EVENT_RUN_STARTED_SUMMARY,
    INFINITE_EVENT_RUN_STOPPED_SUMMARY,
    INFINITE_EVENT_SUBAGENT_FINISHED_SUMMARY,
    INFINITE_EVENT_SUBAGENT_LAUNCHED_SUMMARY,
    INFINITE_EVENT_SUBAGENT_REPLAYED_SUMMARY,
    INFINITE_EVENT_SUMMARY_MAX_CHARS,
    INFINITE_EVENT_TEXT_MAX_CHARS,
    INFINITE_GENERATOR_KEY,
    INFINITE_LAUNCH_TOOL_NAME,
    INFINITE_MIN_COUNT,
    INFINITE_ROOT_DEPTH,
    INFINITE_ROOT_KEY,
    INFINITE_STOP_REASON_METADATA_KEY,
    INFINITE_TOOL_CALLS_METADATA_KEY,
    INFINITE_TRUNCATION_MARKER,
    INFINITE_USAGE_METADATA_KEY,
    INFINITE_VERIFIER_KEY,
)
from vidbyte.lib.dataclasses.infinite import (
    InfiniteDroppedEntry,
    InfiniteEntry,
    InfiniteEvent,
    InfiniteEventDetails,
    InfiniteFileWrittenDetails,
    InfiniteGeneratorFinishedDetails,
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
    InfiniteSubagentFinishedDetails,
    InfiniteSubagentLaunchedDetails,
    InfiniteSubagentReplayedDetails,
    InfiniteTaskCard,
)
from vidbyte.lib.enums.infinite import (
    InfiniteAgentRole,
    InfiniteEventKind,
    InfiniteFileChange,
    InfiniteResultStatus,
    InfiniteStopCause,
)
from vidbyte.lib.outputs.text import OutputText

if TYPE_CHECKING:
    from vidbyte.agents.infinite.journal import InfiniteRunJournal
    from vidbyte.agents.infinite.launch import InfiniteLaunchTool, InfinitePair
    from vidbyte.agents.infinite.memory import InfiniteAgentMemory
    from vidbyte.agents.infinite.settings import InfiniteMemoryAgentSettings
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
        # When each pair was launched, by pair key, for its generator's
        # duration.
        self._launched: dict[str, float] = {}

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

    def run_finished(self, journal: InfiniteRunJournal, result: AgentResult) -> None:
        """Announce a run whose journal is closed: its stop reason, the root's answer, the pairs and agents, and the run's usage."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.RUN_FINISHED):
            # The usage is the root's rollup, into which every child's
            # usage merged as it finished.
            stop_reason, answer = journal.stop_reason or "", journal.answer or ""
            tokens, cost = self._usage((result.metadata.get(INFINITE_USAGE_METADATA_KEY),))
            details = InfiniteRunFinishedDetails(
                stop_reason=self._cut(stop_reason, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True), answer=self._cut(answer, INFINITE_EVENT_TEXT_MAX_CHARS),
                pairs=self._count(len(journal.cards)), agents=self._count(journal.agents_started), tokens=tokens, cost_usd=cost,
            )
            summary = self._cut(INFINITE_EVENT_RUN_FINISHED_SUMMARY.format(stop_reason=stop_reason, answer=answer), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.RUN_FINISHED, INFINITE_ROOT_KEY, InfiniteAgentRole.ROOT, INFINITE_ROOT_DEPTH, summary, details)

    def run_stopped(self, error: BaseException) -> None:
        """Announce a run that raised after it opened: failed for an Exception, cancelled for any other BaseException."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.RUN_STOPPED):
            reason = InfiniteStopCause.FAILED if isinstance(error, Exception) else InfiniteStopCause.CANCELLED
            error_type = type(error).__name__
            details = InfiniteRunStoppedDetails(reason=reason, error_type=self._cut(error_type, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True), message=self._cut(str(error), INFINITE_EVENT_TEXT_MAX_CHARS))
            summary = self._cut(INFINITE_EVENT_RUN_STOPPED_SUMMARY.format(reason=reason.value, error_type=error_type), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.RUN_STOPPED, INFINITE_ROOT_KEY, InfiniteAgentRole.ROOT, INFINITE_ROOT_DEPTH, summary, details)

    def batch_rejected(self, launch: InfiniteLaunchTool, problem: str) -> None:
        """Announce a launch_subagent batch the launch tool refused, with the problem the launching model was told."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.BATCH_REJECTED):
            role = self._launcher_role(launch.key)
            details = InfiniteRefusalDetails(tool=INFINITE_LAUNCH_TOOL_NAME, problem=self._cut(problem, INFINITE_EVENT_TEXT_MAX_CHARS))
            summary = self._cut(INFINITE_EVENT_REFUSED_SUMMARY.format(tool=INFINITE_LAUNCH_TOOL_NAME, agent=self._label(launch.key), problem=problem), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.BATCH_REJECTED, self._key(launch.key, role), role, self._count(launch.depth), summary, details)

    def subagent_launched(self, launch: InfiniteLaunchTool, card: InfiniteTaskCard) -> None:
        """Announce a new pair whose pair_started record is on disk: its name, keys, depth, and task card cut to the event caps."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.SUBAGENT_LAUNCHED):
            # Start the clock for this pair's generator duration.
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

    def subagent_finished(self, pair: InfinitePair, card: InfiniteResultCard) -> None:
        """Announce a pair whose card is journaled: its outcome, cut review, committed and dropped entries, notes, and usage."""
        if self.on_event is None:
            return
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
            )
            summary = self._cut(INFINITE_EVENT_SUBAGENT_FINISHED_SUMMARY.format(name=card.name, verdict=card.verdict.value, committed=len(pair.committed), dropped=len(pair.dropped), files=len(files)), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.SUBAGENT_FINISHED, self._key(launch.key, role), role, self._count(launch.depth), summary, details)

    def memory_saved(self, memory: InfiniteAgentMemory, entry: InfiniteEntry) -> None:
        """Announce an entry the root committed to entries.jsonl: its id, kind, cut text, tags, refs, and the entry it replaced."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.MEMORY_SAVED):
            draft = entry.draft
            details = InfiniteMemorySavedDetails(id=self._count(entry.id), kind=draft.kind, text=self._cut(draft.text, INFINITE_EVENT_TEXT_MAX_CHARS), tags=draft.tags, refs=tuple(self._cut(ref, INFINITE_EVENT_LINE_MAX_CHARS) for ref in draft.refs), supersedes=draft.supersedes)
            summary = self._cut(INFINITE_EVENT_MEMORY_SAVED_SUMMARY.format(id=entry.id, kind=draft.kind.value, text=draft.text), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.MEMORY_SAVED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def memory_staged(self, memory: InfiniteAgentMemory, staged: InfiniteStagedEntry) -> None:
        """Announce an entry a pair's agent staged for its verifier: its staged key, kind, cut text, and the entry it would replace."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.MEMORY_STAGED):
            draft = staged.draft
            details = InfiniteMemoryStagedDetails(key=staged.key, kind=draft.kind, text=self._cut(draft.text, INFINITE_EVENT_TEXT_MAX_CHARS), supersedes=draft.supersedes)
            summary = self._cut(INFINITE_EVENT_MEMORY_STAGED_SUMMARY.format(agent=self._label(memory.key), key=staged.key, kind=draft.kind.value, text=draft.text), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.MEMORY_STAGED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def memory_dropped(self, memory: InfiniteAgentMemory, dropped: InfiniteDroppedEntry) -> None:
        """Announce a staged entry the verifier dropped: its staged key, a short cut of its text, the reason, and the note."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.MEMORY_DROPPED):
            details = InfiniteMemoryDroppedDetails(key=dropped.key, text=self._cut(dropped.text, INFINITE_EVENT_LABEL_MAX_CHARS), reason=dropped.reason, note=self._cut(dropped.note, INFINITE_EVENT_LABEL_MAX_CHARS))
            summary = self._cut(INFINITE_EVENT_MEMORY_DROPPED_SUMMARY.format(agent=self._label(memory.key), key=dropped.key, text=dropped.text), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.MEMORY_DROPPED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def file_written(self, memory: InfiniteAgentMemory, path: str, change: InfiniteFileChange, text: str, description: str | None) -> None:
        """Announce a note whose new text is on disk: its workspace-relative path, the change, the characters written, an excerpt, and a created note's description."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.FILE_WRITTEN):
            relative = memory.workspace.relative(path)
            details = InfiniteFileWrittenDetails(path=self._cut(relative, INFINITE_EVENT_PATH_MAX_CHARS), change=change, added_chars=self._count(len(text)), excerpt=self._cut(text, INFINITE_EVENT_TEXT_MAX_CHARS), description=self._cut(description or "", INFINITE_EVENT_LINE_MAX_CHARS))
            template = INFINITE_EVENT_FILE_CREATED_SUMMARY if change is InfiniteFileChange.CREATED and description else INFINITE_EVENT_FILE_WRITTEN_SUMMARY
            summary = self._cut(template.format(agent=self._label(memory.key), change=change.value, path=relative, description=description), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.FILE_WRITTEN, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    def tool_refused(self, memory: InfiniteAgentMemory, tool: str, problem: str) -> None:
        """Announce a memory tool call the tool itself refused, with the problem the model was told."""
        if self.on_event is None:
            return
        with self._shielded(InfiniteEventKind.TOOL_REFUSED):
            details = InfiniteRefusalDetails(tool=self._cut(tool, INFINITE_EVENT_LABEL_MAX_CHARS, collapse=True), problem=self._cut(problem, INFINITE_EVENT_TEXT_MAX_CHARS))
            summary = self._cut(INFINITE_EVENT_REFUSED_SUMMARY.format(tool=tool, agent=self._label(memory.key), problem=problem), INFINITE_EVENT_SUMMARY_MAX_CHARS, collapse=True)
            self._deliver(InfiniteEventKind.TOOL_REFUSED, self._key(memory.key, memory.role), memory.role, self._count(memory.depth), summary, details)

    @contextmanager
    def _shielded(self, kind: InfiniteEventKind) -> Iterator[None]:
        # @intent a-broken-sink-never-breaks-the-run
        # Any Exception from building the event or from the sink drops
        # that one event and logs the run id, the kind, and the class
        # name only, never text that could hold a secret. Interrupts
        # and cancellation are not Exceptions, so they still stop the
        # run.
        try:
            yield
        except Exception as exc:
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


__all__ = ["InfiniteEvents"]
