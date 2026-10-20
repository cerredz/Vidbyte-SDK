"""FILE: vidbyte/agents/infinite/runtime.py

PURPOSE: Defines InfiniteMemoryRuntime, the INFINITE_MEMORY runtime: for each run of an InfiniteMemoryAgent it opens or continues the run's journal, adds the root's run-bound tools (launch_subagent and the memory tools), clears what earlier runs of the same agent left in the context, keeps the workspace map at the top of the root's context, runs the inherited linear loop, and records how the run ended; it builds the run's InfiniteEvents (events.py), announces the run's start or resumption, its finish, or why it stopped, and after each tool iteration the root's denied launches, a change in workspace usage, and every tenth iteration's progress, and returns the journal's run id in the reply metadata.
ROLE IN CODEBASE: RuntimeRegistry (vidbyte/lib/registries/runtimes.py) resolves AgentRuntimeType.INFINITE_MEMORY to this class, and BaseAgent._runtime builds one per run with the settings, workspace, and resuming journal from InfiniteMemoryAgent._runtime_extension_kwargs (agent.py). It builds InfiniteAgentMemory (memory.py) and InfiniteLaunchTool (launch.py) for the root, both holding the run's InfiniteEvents.
ARCHITECTURE NOTE: A subclass of AgentRuntime that adds per-run setup around super().arun and one _after_tool_iteration hook, as JevRuntime does; the loop itself is unchanged. The runtime refuses to exist without its agent's settings and workspace, because the enum is selectable by string. The map lives on a run-local copy of the context manager, so the agent's own manager is never changed. The hook also announces, through the root's launch tool's events, the launches a middleware denied since the last iteration, a change in workspace usage or in the map's cut, and every tenth iteration's progress; after the loop returns, arun catches up the denials of the final turn, which skips the hook.
FUNCTION INVENTORY: __init__ refuses construction outside InfiniteMemoryAgent; arun is the narrated main function, which also announces run_started or run_resumed, run_finished, and run_stopped; _after_tool_iteration renders the map again after each tool iteration and announces new denials, usage changes, and progress; _announce_denials announces each denied launch once, from the call records not yet read; _map builds the map context item.
COMMON MODIFICATION PATTERNS: Per-run setup goes in arun before super().arun; per-iteration work goes in _after_tool_iteration. A new run-bound tool adds its name to INFINITE_RESERVED_TOOL_NAMES and to the clash check in arun.
WHAT NOT TO DO IN THIS FILE: 1. Do not write a journal record before the clash check passes. 2. Do not change the agent's own context manager; copy it. 3. Do not keep earlier runs' history or tool calls in the context. 4. Do not override the caller's explicit system option (spec D-27).
KNOWN EDGE CASES: A caller's explicit system option replaces the root prompt and the map for that run (D-27). Extras are read when the run starts, so a tool attached during the run cannot be named in a task card until the next run. run_finished is written only when the loop returns, so a cancelled or failed run stays resumable. No event is announced before the clash check passes. A run that raises after its journal opened announces run_stopped (failed for an Exception, cancelled for any other BaseException) and re-raises the same error, so its journal stays resumable and the caller sees what it saw before. A root denial in a turn that skips the hook (an accepted finish, a refused finish, or a contract rejection) is announced by the next hook call or by the catch-up after the loop returns, once and before run_finished (derived-events EC-6); a run that raises before the catch-up leaves its last turn's denials unannounced (EC-7).
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 6.1 INV-3, INV-7, INV-22, INV-25, INV-39, and 8.2); docs/spec/infinite-memory-events/spec.md (sections 6.1 and 9.1); docs/spec/infinite-memory-derived-events/spec.md (sections 6.1 and 8.5, D-4); vidbyte/agents/infinite/README.md; vidbyte/agents/jev/runtime.py (the pattern this follows)
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py, tests/features/infinite_memory_agent/test_infinite_memory_context.py, tests/features/infinite_memory_agent/test_infinite_memory_resume.py, tests/features/infinite_memory_agent/test_infinite_memory_events_stream.py, tests/features/infinite_memory_agent/test_infinite_memory_events_lifecycle.py, and tests/features/infinite_memory_agent/test_infinite_memory_derived_run.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.agents.infinite.events import InfiniteEvents
from vidbyte.agents.infinite.journal import InfiniteRunJournal
from vidbyte.agents.infinite.launch import InfiniteLaunchTool
from vidbyte.agents.infinite.memory import InfiniteAgentMemory
from vidbyte.agents.infinite.settings import InfiniteMemoryAgentSettings
from vidbyte.agents.infinite.workspace import InfiniteWorkspace
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import TextContextItem
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.constants.infinite import (
    INFINITE_CALL_RECORDS_METADATA_KEY,
    INFINITE_MAP_PRIMITIVE_ID,
    INFINITE_MAP_TITLE,
    INFINITE_MIN_COUNT,
    INFINITE_RESERVED_TOOL_NAMES,
    INFINITE_ROOT_DEPTH,
    INFINITE_ROOT_KEY,
    INFINITE_RUN_BOUND_TOOL_NAMES,
    INFINITE_RUN_ID_METADATA_KEY,
    INFINITE_STOP_REASON_METADATA_KEY,
)
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.infinite import InfiniteAgentRole
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext


class InfiniteMemoryRuntime(AgentRuntime):
    """The linear loop of an InfiniteMemoryAgent run, with its journal, run-bound tools, and workspace map."""

    def __init__(self, *, settings: InfiniteMemoryAgentSettings | None = None, workspace: InfiniteWorkspace | None = None, resuming: InfiniteRunJournal | None = None, **kwargs: Any) -> None:
        # @intent infinite-runtime-needs-its-agent
        # AgentRuntimeType.INFINITE_MEMORY is selectable by string, so a
        # plain BaseAgent or a fork can reach this class without its
        # settings; refusing here names the agent to use instead.
        if not isinstance(settings, InfiniteMemoryAgentSettings) or not isinstance(workspace, InfiniteWorkspace) or (resuming is not None and not isinstance(resuming, InfiniteRunJournal)):
            raise ConfigurationError(
                "The 'infinite_memory' runtime is only available through InfiniteMemoryAgent; construct InfiniteMemoryAgent(InfiniteMemoryAgentSettings(...)) instead of BaseAgent(runtime='infinite_memory').",
                details={"received_settings": type(settings).__name__, "received_workspace": type(workspace).__name__, "received_resuming": type(resuming).__name__},
            )
        self.settings = settings
        self.workspace = workspace
        self.resuming = resuming
        # The root's launch tool once the run builds it, and how many
        # of the loop's call records were already read for denied
        # launches, so each denial is announced once.
        self._launch: InfiniteLaunchTool | None = None
        self._announced = INFINITE_MIN_COUNT
        super().__init__(**kwargs)

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        """Open or continue the run's journal, announce the run, add the run-bound tools and the map, run the loop, and record and announce how it ended."""
        # @intent run-bound-names-belong-to-the-run
        # A developer or MCP tool named like a run-bound tool would make
        # the catalog refuse it mid-run, so refuse the run before any
        # journal record is written. Every other non-internal tool the
        # root holds now is an extra it may hand on to a pair.
        clash = [name for name in self.tools.names() if name in INFINITE_RUN_BOUND_TOOL_NAMES]
        if clash:
            raise ConfigurationError(f"The tool {clash[0]!r} uses a name InfiniteMemoryAgent reserves for its own tools; rename it. Reserved: {', '.join(INFINITE_RESERVED_TOOL_NAMES)}.", details={"tool": clash[0], "reserved": list(INFINITE_RESERVED_TOOL_NAMES)})
        extras = tuple(tool for tool in self.tools.all() if tool.spec().name not in INFINITE_RESERVED_TOOL_NAMES and not self._tool_name_is_internal(tool.spec().name))

        # @intent every-run-is-journaled
        # A new run starts its journal with the task; a resumed run
        # continues the journal it was found in.
        journal = self.resuming or InfiniteRunJournal.start(self.workspace.root, message)

        # Announce the run to the developer's sink, if there is one: a
        # resumed run with what it reuses and re-runs, a new one with
        # its task, limits, and extra tools.
        events = InfiniteEvents(self.settings.on_event, journal.run_id)
        if self.resuming is not None:
            events.run_resumed(journal)
        else:
            events.run_started(self.settings, message, tuple(tool.spec().name for tool in extras))

        # @intent a-stopped-run-is-announced-and-re-raised
        # From here on any error or cancellation is announced as
        # run_stopped and raised again unchanged; run_finished is never
        # written, so the run stays resumable.
        try:
            # Give the root its memory tools and launch_subagent for
            # this run, and start from a clean context: nothing from an
            # earlier run of this agent object reaches the model.
            memory = InfiniteAgentMemory(self.workspace, key=INFINITE_ROOT_KEY, role=InfiniteAgentRole.ROOT, run_id=journal.run_id, depth=INFINITE_ROOT_DEPTH, events=events)
            launch = InfiniteLaunchTool(self.settings, self.workspace, journal, key=INFINITE_ROOT_KEY, depth=INFINITE_ROOT_DEPTH, extras=extras, events=events)
            self._launch = launch
            self.tools = self.tools.extend((launch, *memory.tools()))
            context = replace(context, tools=self.tools.specs(), tool_calls=(), history=())
            run_options = dict(options or {})
            run_options.pop("tools", None)

            # Put the workspace map at the top of a run-local copy of
            # the context, so the agent's own context manager stays
            # unchanged.
            self.context_manager = self.context_manager.copy() if self.context_manager is not None else ContextManager()
            self.context_manager.upsert(self._map(), placement=ContextWindowPlacement.TOP_OF_CONTEXT)

            # Run the inherited loop; the root's history trim came from
            # InfiniteMemoryAgent's middleware.
            result = await super().arun(message, handle=handle, context=context, metadata=metadata, options=run_options, trace_context=trace_context)
            # The loop's last turn skips the per-iteration hook, so the
            # launches a middleware denied in it are announced here.
            self._announce_denials(launch, result.metadata.get(INFINITE_CALL_RECORDS_METADATA_KEY, ()))

            # The loop returned, so record the run as finished, with
            # the root's answer and the notes it wrote for the handoff.
            journal.finish(str(result.metadata.get(INFINITE_STOP_REASON_METADATA_KEY, "")), result.output, tuple(memory.files_written))
        except BaseException as exc:
            events.run_stopped(exc)
            raise

        # Announce the finished run, and return the journal's run id
        # with the reply, so the caller can find the run again.
        events.run_finished(journal, result, self.workspace)
        return replace(result, metadata={**dict(result.metadata), INFINITE_RUN_ID_METADATA_KEY: journal.run_id})

    async def _after_tool_iteration(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Render the workspace map again after each tool iteration, so the root's next call sees what changed; with a sink, also announce new delegation denials, a change in workspace usage, and every tenth iteration's progress."""
        # @intent the-roots-map-follows-the-disk
        # Tools, bash, and finished pairs change the workspace between
        # calls, and the map is the root's only view of it.
        item = self._map()
        if self.context_manager is not None:
            self.context_manager.upsert(item, placement=ContextWindowPlacement.TOP_OF_CONTEXT)
        # Announce the launches a middleware denied since the last
        # iteration, the workspace's usage when its level or the
        # map's cut changed, and the root's progress every tenth
        # iteration; the events skip all of it when nobody listens.
        if self._launch is not None:
            self._announce_denials(self._launch, state.call_contexts)
            self._launch.events.workspace_usage(self.workspace, item.content)
            self._launch.events.agent_progress(self.settings, state)

    def _announce_denials(self, launch: InfiniteLaunchTool, calls: Sequence[object]) -> None:
        # @intent each-denial-is-announced-once
        # The loop's call records only grow, so only those after the
        # ones already read are checked, and each launch a middleware
        # denied is announced exactly once.
        for denial in InfiniteLaunchTool.denials(calls[self._announced :]):
            launch.events.batch_rejected(launch, denial)
        self._announced = len(calls)

    def _map(self) -> TextContextItem:
        # The workspace map as one context item with a fixed id, so each
        # upsert replaces the previous map.
        return TextContextItem(title=INFINITE_MAP_TITLE, content=self.workspace.map_text(), primitive_id=INFINITE_MAP_PRIMITIVE_ID)


__all__ = ["InfiniteMemoryRuntime"]
