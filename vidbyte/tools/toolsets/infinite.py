"""FILE: vidbyte/tools/toolsets/infinite.py

PURPOSE: Defines InfiniteMemoryAgentTools, the catalog of the four ordinary tools every agent in an InfiniteMemory tree holds: bash over the project folder, and grep, read_lines, and search_memory over the memory workspace.
ROLE IN CODEBASE: Built by vidbyte/agents/infinite/agent.py for the root agent; get_tools is called by vidbyte/agents/infinite/launch.py for every generator and verifier, and by vidbyte/agents/infinite/recall.py for every retriever, which keeps grep, read_lines, and search_memory but not bash; exported by vidbyte/tools/toolsets/__init__.py. Composes vidbyte/tools/builtins/bash.py, vidbyte/tools/builtins/code_search/grep.py, vidbyte/tools/filesystem/read_lines.py, and vidbyte/tools/builtins/code_search/search_memory.py.
ARCHITECTURE NOTE: A Tools subclass that holds only the four tools; the run-bound memory and launch tools live in vidbyte/agents/infinite/ because they need the workspace and the journal, and this layer may not import vidbyte.agents. Grep skips the run journals and the superseded entries, so a search finds only live memory, and its file-size cap is derived from the workspace token cap, so no file the workspace allows is too large to search. Grep is smart-case and shows matching lines only, and read_lines returns at most max_read_lines lines per call with a footer naming the next start line, so no single read floods an agent's context. search_memory searches the full-text index the caller passes, the one InfiniteWorkspace.full_text every agent of a tree shares, with grep's byte cap.
FUNCTION INVENTORY: InfiniteMemoryAgentTools.__init__ is the narrated main function; get_tools returns bash, grep, read_lines, and search_memory in that order.
COMMON MODIFICATION PATTERNS: A tool every agent should hold is added to get_tools, to INFINITE_RESERVED_TOOL_NAMES in vidbyte/lib/constants/infinite.py, and to the folder README's tool table together.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents; the memory and launch tools stay in the agent package. 2. Do not give read_lines write access; the memory tools are the only writers. 3. Do not point grep or search_memory at the project folder; they search the memory workspace. 4. Do not build a FullTextIndex here; every agent of a tree must share the workspace's one index.
KNOWN EDGE CASES: Bash is not confined to either folder, so a command can still write into the workspace; the workspace recounts its caps from disk before every tool write. read_lines can read the run journals and the superseded entries by path, although grep and search_memory skip them.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5 and 9.2); docs/spec/infinite-memory-context-economy/spec.md (FR-1.3, FR-3.2); vidbyte/agents/infinite/README.md; vidbyte/tools/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py, tests/features/infinite_memory_agent/test_infinite_memory_workspace.py, tests/features/infinite_memory_agent/test_infinite_memory_economy.py, tests/features/infinite_memory_agent/test_infinite_memory_search.py, and tests/features/infinite_memory_agent/test_infinite_memory_recall.py
"""

from __future__ import annotations

from pathlib import Path

from vidbyte.lib.constants.infinite import (
    INFINITE_GREP_CONTEXT_LINES,
    INFINITE_RUNS_DIRNAME,
    INFINITE_SUPERSEDED_FILE,
    INFINITE_UTF8_MAX_BYTES_PER_CHAR,
)
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.util.fulltext import FullTextIndex
from vidbyte.lib.util.text import TOKEN_ESTIMATE_CHARS_PER_TOKEN
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.bash import BashTool
from vidbyte.tools.builtins.code_search.grep import GrepTool
from vidbyte.tools.builtins.code_search.search_memory import InfiniteSearchMemoryTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.filesystem.read_lines import ReadLinesTool


class InfiniteMemoryAgentTools(Tools):
    """Catalog of bash over the project folder plus grep, read_lines, and search_memory over the memory workspace."""

    def __init__(self, root_dir: Path, workspace_root: Path, max_tokens: int, max_read_lines: int, index: FullTextIndex) -> None:
        # Put bash over the project folder first, then the three
        # read-only tools over the memory workspace.
        super().__init__(self.get_tools(root_dir, workspace_root, max_tokens, max_read_lines, index))

    @staticmethod
    def get_tools(root_dir: Path, workspace_root: Path, max_tokens: int, max_read_lines: int, index: FullTextIndex) -> tuple[BaseTool, ...]:
        """Return bash over root_dir, then grep, read_lines (at most max_read_lines lines per call), and search_memory on index over workspace_root."""
        # @intent grep-sees-only-live-memory
        # Grep skips the run journals and the superseded entries, so a
        # search never returns an entry that was replaced. Its byte cap
        # is the largest file the token cap allows, so a large
        # entries.jsonl is still searched.
        largest_file_bytes = max_tokens * TOKEN_ESTIMATE_CHARS_PER_TOKEN * INFINITE_UTF8_MAX_BYTES_PER_CHAR
        # @intent workspace-reads-stay-small
        # A lowercase pattern matches any case, and a match shows its
        # line alone, because read_lines shows the rest; read_lines
        # returns one window per call and names where to read on.
        grep = GrepTool(workspace_root, ignore_patterns=(INFINITE_RUNS_DIRNAME, INFINITE_SUPERSEDED_FILE), max_file_bytes=largest_file_bytes, smart_case=True, context_lines=INFINITE_GREP_CONTEXT_LINES)
        search = InfiniteSearchMemoryTool(workspace_root, index=index, max_file_bytes=largest_file_bytes)
        return (BashTool(root_dir), grep, ReadLinesTool(FileSystemToolConfig(root=workspace_root, max_read_lines=max_read_lines)), search)


__all__ = ["InfiniteMemoryAgentTools"]
