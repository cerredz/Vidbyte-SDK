"""FILE: vidbyte/agents/infinite/recall.py

PURPOSE: Defines InfiniteRecallTool, the recall tool the root and every generator hold under InfiniteRecallMode.DELEGATED: it hands one memory question to a fresh, read-only retriever agent and returns a capped card whose found section holds only entries and line ranges the code copied from disk, plus what was not found, the citations it refused, and the searches that ran.
ROLE IN CODEBASE: Built by InfiniteAgentMemory.tools (memory.py) when InfiniteMemoryToolRegistry (vidbyte/lib/registries/infinite.py) grants recall to the agent's role under the workspace's recall mode. Reads the agent's memory for the tree's settings, the workspace, and the recall count; builds the retriever's tools with InfiniteMemoryAgentTools.get_tools (vidbyte/tools/toolsets/infinite.py) over the workspace's one full-text index; parses the reply with InfiniteRecallCitation.parse (vidbyte/lib/dataclasses/infinite.py).
ARCHITECTURE NOTE: The retriever is a plain BaseAgent with no role and no memory tools, built like a pair's child in launch.py: the developer's prompt plus the retriever_system_prompt leaf, a map drawn when it starts, grep, read_lines, and search_memory but never bash, the masking and history trim every agent has, and a loop of INFINITE_RECALL_MAX_ITERATIONS. It is no pair, so it never counts toward max_agents and writes no journal record, while its model usage reaches the run through the usage ledger as a pair's does. The retriever only points at places; the code checks each citation and copies entries through InfiniteWorkspace.entries and ranges through the same windowed read_lines the retriever read with, so no text the retriever wrote reaches the found section. The tool is internal, so the loop's tool timeout and result cap do not apply; the retriever's loop cap and the card cap bound it instead. InfiniteAgentMemory is imported only for type checking, so at run time the import edge runs one way, memory to recall.
FUNCTION INVENTORY: spec declares the tool from the five recall leaves; execute is the narrated main function, which checks the request and the quota, pre-searches the terms, runs the retriever, checks and copies each citation, and renders and caps the card; _retriever builds the retriever agent; _searches lists the retriever's own searches; _sort reads the reply line by line; _copy checks one citation and copies its text from disk.
COMMON MODIFICATION PATTERNS: A new request field is one property in spec, one leaf for its description, one field on InfiniteRecallRequest, and its place in the retriever_task_prompt leaf. A new citation rule is one more check in _copy that raises ToolExecutionError with the reason the card lists. A new card section is one placeholder in the recall_card leaf, before {found}.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the retriever's words in the found section; copy every found text from disk. 2. Do not give the retriever bash, a memory tool, launch_subagent, or recall. 3. Do not count a call refused for its arguments or its quota, and do not start an agent for one. 4. Do not catch CancelledError or BaseException; cancelling the run must stop the retriever. 5. Do not add module-level constants here; they live in vidbyte/lib/constants/infinite.py. 6. Do not import InfiniteAgentMemory at run time; memory.py imports this module.
KNOWN EDGE CASES: A retriever stopped by its loop cap still has its reply's citations checked, usually none, so the card lists only its searches. A reply line in a citation form whose numbers the record refuses is listed as "reply line n" with the record's reason, counted from 1. A range that ends past the file's last line, is longer than the read window, leaves the workspace, or touches a bookkeeping name in any part of its resolved path, compared case-insensitively, is rejected. A card over its cap is cut at its end, so the found blocks are cut first and the earlier sections only when they alone pass the cap.
RELATED DOCS: docs/spec/infinite-memory-context-economy/spec.md (sections 6.1 INV-10.1 to INV-10.10, 8.5, and 9.2, D-14 to D-18); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_recall.py
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import TextContextItem
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.constants.infinite import (
    INFINITE_BOOKKEEPING_NAMES,
    INFINITE_HISTORY_LOW_WATERMARK_TOKENS,
    INFINITE_HISTORY_MAX_TOKENS,
    INFINITE_MAP_PRIMITIVE_ID,
    INFINITE_MAP_TITLE,
    INFINITE_MASK_KEEP_RECENT,
    INFINITE_MASKED_TOOL_NAMES,
    INFINITE_RECALL_CARD_MAX_TOKENS,
    INFINITE_RECALL_MAX_ITERATIONS,
    INFINITE_RECALL_MAX_TERMS,
    INFINITE_RECALL_TOOL_NAME,
    INFINITE_RECALLS_PER_AGENT,
    INFINITE_TRUNCATION_MARKER,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.dataclasses.infinite import (
    InfiniteRecallCitation,
    InfiniteRecallRequest,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError, VidbyteSdkError
from vidbyte.lib.tools.filesystem.permissions import FileSystemPermissions
from vidbyte.lib.util import TokenEstimate
from vidbyte.middleware import MessageHistoryCompactionMiddleware
from vidbyte.middleware.compaction import CompactionMode
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.toolsets import InfiniteMemoryAgentTools
from vidbyte.tools.types import (
    ToolCall,
    ToolPermission,
    ToolResult,
    ToolSpec,
    ToolStatus,
)

if TYPE_CHECKING:
    from vidbyte.agents.infinite.memory import InfiniteAgentMemory


class InfiniteRecallTool(BaseTool):
    """The recall tool: a fresh retriever searches memory for one question, and the card holds only text the code copied from disk."""

    def __init__(self, memory: InfiniteAgentMemory) -> None:
        self.memory = memory

    def spec(self) -> ToolSpec:
        """Return the read-only recall declaration, with every description from the prompt family."""
        prompts = Prompts()
        properties = {
            "question": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_RECALL_QUESTION_DESCRIPTION)},
            "purpose": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_RECALL_PURPOSE_DESCRIPTION)},
            "known": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_RECALL_KNOWN_DESCRIPTION)},
            "terms": {"type": "array", "items": {"type": "string"}, "maxItems": INFINITE_RECALL_MAX_TERMS, "description": prompts.get(Prompt.INFINITE_MEMORY_RECALL_TERMS_DESCRIPTION)},
        }
        return ToolSpec(
            name=INFINITE_RECALL_TOOL_NAME,
            description=prompts.get(Prompt.INFINITE_MEMORY_RECALL_TOOL_DESCRIPTION),
            permission=ToolPermission.READ,
            input_schema={"type": "object", "properties": properties, "required": ["question", "purpose"], "additionalProperties": False},
            # @intent a-recall-is-never-cut-by-tool-limits
            # A recall lasts as long as its retriever, which its own loop
            # cap bounds, and returns a capped card, so the loop's tool
            # timeout and result cap must not apply.
            metadata={"internal": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Check the request and the quota, pre-search the terms, run a fresh retriever, and return a capped card of what it cited, copied from disk."""
        memory, prompts = self.memory, Prompts()
        # @intent a-refused-recall-costs-nothing
        # Check the request, then this agent's allowance, before anything
        # starts, so a refused call starts no retriever and costs no
        # recall. The model sends terms as a JSON list, and the record
        # takes a tuple.
        terms = self._optional_argument(call, "terms", default=())
        try:
            request = InfiniteRecallRequest(question=call.arguments.get("question", ""), purpose=call.arguments.get("purpose", ""), known=self._optional_argument(call, "known", default=""), terms=tuple(terms) if isinstance(terms, list) else terms)
        except ConfigurationError as exc:
            return ToolResult.error(INFINITE_RECALL_TOOL_NAME, memory.refusal(str(exc)))
        if memory.recalled >= INFINITE_RECALLS_PER_AGENT:
            return ToolResult.error(INFINITE_RECALL_TOOL_NAME, memory.refusal(f"You have used all {INFINITE_RECALLS_PER_AGENT} of your recalls; search with search_memory and read_lines yourself."))
        memory.recalled += 1

        # Give the retriever the workspace's read-only tools, without
        # bash, over the tree's one search index, and search each term
        # on its own, in the order given, before it starts.
        workspace = memory.workspace
        _, grep, read, search = InfiniteMemoryAgentTools.get_tools(Path(memory.settings.root_dir), workspace.root, workspace.settings.max_tokens, workspace.settings.max_read_lines, workspace.full_text)
        hits = [f"{search.name}: {term}\n{(await search.execute(ToolCall(search.name, {'query': term}))).output}" for term in request.terms]

        # Run the fresh retriever on the request and the pre-search hits.
        # An error ends this recall, which still counts; cancelling the
        # run is not caught, so it stops the retriever too.
        task = prompts.get(Prompt.INFINITE_MEMORY_RETRIEVER_TASK_PROMPT).format(question=request.question, purpose=request.purpose, known=request.known or "-", hits="\n\n".join(hits) or "-")
        try:
            reply = await self._retriever((grep, read, search)).arun(task)
        except (VidbyteSdkError, OSError, ValueError) as exc:
            return ToolResult.error(INFINITE_RECALL_TOOL_NAME, f"This recall used one of your recalls and failed with {type(exc).__name__}: {str(exc.__cause__ or exc).strip()}")

        # Sort the reply's lines into what was not found, the citations
        # to check, and citation lines whose numbers were refused.
        not_found, rejected, citations = self._sort(reply.content)

        # @intent found-text-comes-from-disk
        # Copy each accepted citation's text from disk under a label the
        # code builds, and list each refused one by its place and reason,
        # so the retriever's own words never reach the found section.
        found: list[str] = []
        for citation in citations:
            try:
                found.append(await self._copy(citation, read))
            except (VidbyteSdkError, OSError, ValueError) as exc:
                place = f"#{citation.entry_id}" if citation.entry_id is not None else f"{citation.path}:{citation.start}-{citation.end}"
                rejected.append(f"- {place}: {exc}")

        # Render the card with the found blocks last, list the
        # pre-searches before the retriever's own searches, and cap it
        # with room for the cut marker, so a cut removes copied text
        # first and the whole card stays within its cap.
        searches = [*(f"- {search.name}: {term}" for term in request.terms), *self._searches(reply, (grep.name, search.name))]
        card = prompts.get(Prompt.INFINITE_MEMORY_RECALL_CARD).format(question=request.question, not_found="\n".join(not_found) or "-", rejected="\n".join(rejected) or "-", searches="\n".join(searches) or "-", found="\n\n".join(found) or "-")
        return ToolResult.success(INFINITE_RECALL_TOOL_NAME, TokenEstimate.cap(card, INFINITE_RECALL_CARD_MAX_TOKENS - TokenEstimate.count(INFINITE_TRUNCATION_MARKER), INFINITE_TRUNCATION_MARKER))

    def _retriever(self, tools: tuple[BaseTool, ...]) -> BaseAgent:
        # @intent the-retriever-only-reads
        # A fresh agent with the developer's prompt and the retriever's
        # rules, a map drawn now, only the read-only workspace tools, the
        # masking and history trim every agent has, and a short loop. It
        # has no role and no memory tools, so it is no pair: it never
        # counts toward max_agents and writes no journal record.
        memory, settings = self.memory, self.memory.settings
        context = ContextManager()
        context.upsert(TextContextItem(title=INFINITE_MAP_TITLE, content=memory.workspace.map_text(), primitive_id=INFINITE_MAP_PRIMITIVE_ID), placement=ContextWindowPlacement.TOP_OF_CONTEXT)
        return BaseAgent(
            name=f"{settings.name}/{memory.key}/{INFINITE_RECALL_TOOL_NAME}",
            system_prompt=f"{settings.system_prompt}\n\n{Prompts().get(Prompt.INFINITE_MEMORY_RETRIEVER_SYSTEM_PROMPT)}",
            provider=settings.provider,
            model_name=settings.model_name,
            api_keys=settings.api_keys,
            model_mode=settings.model_mode,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            tools=tools,
            permission_policy=settings.permission_policy,
            agent_loop_settings=AgentLoopSettings(max_iterations=INFINITE_RECALL_MAX_ITERATIONS, tool_settings=settings.loop.tool_settings),
            context_manager=context,
            middleware=(
                MessageHistoryCompactionMiddleware.tool_output_sliding_window(INFINITE_MASK_KEEP_RECENT, CompactionMode.STRIP_TOOL_RESULT_BODIES, placeholder=Prompts().get(Prompt.INFINITE_MEMORY_MASKED_OUTPUT), tools=INFINITE_MASKED_TOOL_NAMES),
                MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS, low_watermark_tokens=INFINITE_HISTORY_LOW_WATERMARK_TOKENS),
            ),
        )

    @staticmethod
    def _searches(reply: AgentMessage, names: tuple[str, ...]) -> list[str]:
        # One line per search the retriever ran, naming the tool and the
        # pattern or query it searched for.
        calls = reply.metadata.get("tool_calls", ())
        return [f"- {context.tool_name}: {context.arguments.get('query', context.arguments.get('pattern', ''))}" for context in calls if context.tool_name in names]

    @staticmethod
    def _sort(reply: str) -> tuple[list[str], list[str], list[InfiniteRecallCitation]]:
        # @intent every-reply-line-is-read-on-its-own
        # A NOT FOUND line becomes a not-found line, a FOUND line a
        # citation to check, and a FOUND line whose numbers the citation
        # record refuses a rejected line named by its number, so one bad
        # line never fails the recall; every other line is ignored.
        not_found: list[str] = []
        rejected: list[str] = []
        citations: list[InfiniteRecallCitation] = []
        for number, line in enumerate(reply.splitlines(), start=1):
            try:
                citation = InfiniteRecallCitation.parse(line)
            except (ConfigurationError, ValueError) as exc:
                rejected.append(f"- reply line {number}: {exc}")
                continue
            if citation is None:
                continue
            if citation.entry_id is None and citation.path is None:
                not_found.append(f"- {citation.why}")
            else:
                citations.append(citation)
        return not_found, rejected, citations

    async def _copy(self, citation: InfiniteRecallCitation, read: BaseTool) -> str:
        # Copy one citation's text from disk under its code-built label,
        # or raise ToolExecutionError with the reason it is refused. An
        # entry must be live, and only its id, kind, and text are copied.
        workspace = self.memory.workspace
        if citation.entry_id is not None:
            (entry,) = workspace.entries((citation.entry_id,))
            return f"#{entry.id} {entry.draft.kind.value}: {entry.draft.text}"

        # @intent ranges-come-only-from-notes
        # A range must fit one read window and lie inside the workspace,
        # and no part of its resolved path may be a bookkeeping name, so
        # superseded memory, raw entry lines, and run journals are never
        # copied. The record guarantees a range has its path and ends.
        start, end = cast(int, citation.start), cast(int, citation.end)
        window = workspace.settings.max_read_lines
        if end - start + 1 > window:
            raise ToolExecutionError(f"The range is longer than one read window of {window} lines; cite a shorter range.")
        scope = FileSystemToolConfig(root=workspace.root)
        relative = FileSystemPermissions.resolve_scoped_path(scope, cast(str, citation.path)).relative_to(scope.resolved_root())
        bookkeeping = {name.casefold() for name in INFINITE_BOOKKEEPING_NAMES}
        if any(part.casefold() in bookkeeping for part in relative.parts):
            raise ToolExecutionError("The path is a bookkeeping file or a run journal, not a note; cite a memory entry by its id instead.")

        # Read the range through the same windowed read_lines the
        # retriever read with, so it is scoped and numbered the same way,
        # and refuse a range that ends past the file's last line.
        result = await read.execute(ToolCall(read.name, {"path": relative.as_posix(), "start": start, "end": end}))
        if result.status is ToolStatus.ERROR:
            raise ToolExecutionError(result.output)
        total = result.metadata["total_lines"]
        if end > total:
            raise ToolExecutionError(f"The range ends past the file's last line, {total}.")
        return f"{relative.as_posix()}:{start}-{end}\n{result.output}"


__all__ = ["InfiniteRecallTool"]
