"""FILE: vidbyte/agents/infinite/runtime.py

PURPOSE: Defines InfiniteMemoryRuntime, the INFINITE_MEMORY runtime: for each run of an InfiniteMemoryAgent it opens or continues the run's journal, adds the root's run-bound tools (launch_subagent and the memory tools), clears what earlier runs of the same agent left in the context, draws the workspace map once at the top of the root's context, keeps the root's system string the same on every call, tells the root after each tool iteration what changed in the workspace, runs the inherited linear loop, and records how the run ended.
ROLE IN CODEBASE: RuntimeRegistry (vidbyte/lib/registries/runtimes.py) resolves AgentRuntimeType.INFINITE_MEMORY to this class, and BaseAgent._runtime builds one per run with the settings, workspace, and resuming journal from InfiniteMemoryAgent._runtime_extension_kwargs (agent.py). It builds InfiniteAgentMemory (memory.py) and InfiniteLaunchTool (launch.py) for the root.
ARCHITECTURE NOTE: A subclass of AgentRuntime that adds per-run setup around super().arun and one _after_tool_iteration hook, as JevRuntime does; the loop itself is unchanged. The runtime refuses to exist without its agent's settings and workspace, because the enum is selectable by string. The map lives on a run-local copy of the context manager, so the agent's own manager is never changed. The root's system string holds neither a redrawn map nor the loop-settings block, whose counters change every call, so a provider's prompt cache can serve the whole prefix; both reach the root instead as one user status message appended to its history after each tool iteration.
FUNCTION INVENTORY: __init__ refuses construction outside InfiniteMemoryAgent; arun is the narrated main function; _build_system_string drops the loop-settings block from the root's system string; _after_tool_iteration is the narrated hook that diffs the workspace map against the last report and appends the status message; _map builds the map context item.
COMMON MODIFICATION PATTERNS: Per-run setup goes in arun before super().arun; per-iteration work goes in _after_tool_iteration. A new run-bound tool adds its name to INFINITE_RESERVED_TOOL_NAMES and to the clash check in arun.
WHAT NOT TO DO IN THIS FILE: 1. Do not write a journal record before the clash check passes. 2. Do not change the agent's own context manager; copy it. 3. Do not keep earlier runs' history or tool calls in the context. 4. Do not override the caller's explicit system option (spec D-27). 5. Do not upsert the map again during a run or put anything that changes per call into the system string; changes go in the status message. 6. Do not append more than one status message per tool iteration.
KNOWN EDGE CASES: A caller's explicit system option replaces the root prompt and the map for that run (D-27); status messages still arrive. The root's first call has no status message, and the first report diffs against the snapshot taken when the map was drawn. A report whose change lines were cut still becomes the new baseline, so lines left out are not repeated. With no loop budget configured the block is empty, so a quiet iteration appends nothing. Extras are read when the run starts, so a tool attached during the run cannot be named in a task card until the next run. run_finished is written only when the loop returns, so a cancelled or failed run stays resumable.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 6.1 INV-3, INV-7, INV-22, INV-25, INV-39, and 8.2); docs/spec/infinite-memory-context-economy/spec.md (INV-7.1 to INV-7.6); vidbyte/agents/infinite/README.md; vidbyte/agents/jev/runtime.py (the pattern this follows)
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py, tests/features/infinite_memory_agent/test_infinite_memory_context.py, tests/features/infinite_memory_agent/test_infinite_memory_resume.py, and tests/features/infinite_memory_agent/test_infinite_memory_stable_prefix.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

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
    INFINITE_MAP_PRIMITIVE_ID,
    INFINITE_MAP_REMOVED_LINE,
    INFINITE_MAP_TITLE,
    INFINITE_RESERVED_TOOL_NAMES,
    INFINITE_ROOT_DEPTH,
    INFINITE_ROOT_KEY,
    INFINITE_RUN_BOUND_TOOL_NAMES,
)
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.infinite import InfiniteMapSnapshot
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.infinite import InfiniteAgentRole
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext
from vidbyte.prompts.catalog import Prompts


class InfiniteMemoryRuntime(AgentRuntime):
    """The linear loop of an InfiniteMemoryAgent run, with its journal, run-bound tools, and workspace map."""

    # The workspace map as last reported to the root: the snapshot taken
    # when arun drew the map, then the one behind each status message.
    _reported: InfiniteMapSnapshot

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
        super().__init__(**kwargs)

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        """Open or continue the run's journal, add the run-bound tools and the map, run the loop, and record how it ended."""
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

        # Give the root its memory tools and launch_subagent for this
        # run, and start from a clean context: nothing from an earlier
        # run of this agent object reaches the model.
        memory = InfiniteAgentMemory(self.workspace, key=INFINITE_ROOT_KEY, role=InfiniteAgentRole.ROOT, run_id=journal.run_id, settings=self.settings)
        launch = InfiniteLaunchTool(self.settings, self.workspace, journal, key=INFINITE_ROOT_KEY, depth=INFINITE_ROOT_DEPTH, extras=extras)
        self.tools = self.tools.extend((launch, *memory.tools()))
        context = replace(context, tools=self.tools.specs(), tool_calls=(), history=())
        run_options = dict(options or {})
        run_options.pop("tools", None)

        # Draw the workspace map once, at the top of a run-local copy of
        # the context, so the agent's own context manager stays
        # unchanged. The snapshot is taken first and is what the first
        # status message diffs against, so no change slips between them.
        self._reported = self.workspace.map_snapshot()
        self.context_manager = self.context_manager.copy() if self.context_manager is not None else ContextManager()
        self.context_manager.upsert(self._map(), placement=ContextWindowPlacement.TOP_OF_CONTEXT)

        # Run the inherited loop; the root's history trim came from
        # InfiniteMemoryAgent's middleware.
        result = await super().arun(message, handle=handle, context=context, metadata=metadata, options=run_options, trace_context=trace_context)

        # The loop returned, so record the run as finished; a cancelled
        # or failed run never gets here and stays resumable.
        journal.finish(str(result.metadata.get("stop_reason", "")))
        return result

    def _build_system_string(self, context: BaseAgentContext, *, loop_settings_block: str = "") -> str:
        """Build the root's system string without the loop-settings block, which each status message carries instead."""
        # @intent the-roots-prefix-never-changes
        # The block's counters change on every call, so leaving it out
        # keeps the root's system string byte-identical for the whole run
        # and lets a provider serve the prefix from its prompt cache.
        return super()._build_system_string(context)

    async def _after_tool_iteration(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Append one status message after each tool iteration: what changed in the workspace since the last report, then the loop-settings block."""
        # @intent the-root-hears-what-changed-without-a-new-prefix
        # Tools, bash, and finished pairs change the workspace between
        # calls, and redrawing the map would change the system string,
        # so the root is told only the map lines that changed, in one
        # message appended after the tool results, with the loop
        # counters the system string no longer carries.
        # Recount the workspace in a worker thread, so the event loop
        # keeps serving the other agents of the tree meanwhile.
        current = await asyncio.to_thread(self.workspace.map_snapshot)

        # Compare with the last report: every added or changed map line
        # in map order, then one removed line per file that is gone.
        before = dict(self._reported.lines)
        after = dict(current.lines)
        changes = [line for path, line in current.lines if before.get(path) != line]
        changes += [INFINITE_MAP_REMOVED_LINE.format(path=path) for path in before if path not in after]

        # This snapshot is the next report's baseline even when the
        # change lines are cut below, so lines left out never repeat.
        self._reported = current

        # Render the loop-settings block with the live counters, counting
        # tool calls as the base system-string path does.
        block = self._render_loop_settings_block(iteration_count=state.iteration_count, tokens_used=state.tokens_used, tool_call_count=len(self._non_internal_tool_contexts(state.call_contexts)))

        # Changes go in the map_update text, cut by the map's own rule,
        # followed by the block; with no change the block stands alone,
        # and with neither nothing is appended.
        parts = [block] if block else []
        if changes:
            update = Prompts().get(Prompt.INFINITE_MEMORY_MAP_UPDATE).format(header=current.header, changes="\n".join(InfiniteWorkspace.fit_map_lines(current.header, changes)))
            parts.insert(0, update)
        if parts:
            messages.append({"role": "user", "content": "\n\n".join(parts)})

    def _map(self) -> TextContextItem:
        # The workspace map as one context item with a fixed id, drawn
        # once per run.
        return TextContextItem(title=INFINITE_MAP_TITLE, content=self.workspace.map_text(), primitive_id=INFINITE_MAP_PRIMITIVE_ID)


__all__ = ["InfiniteMemoryRuntime"]
