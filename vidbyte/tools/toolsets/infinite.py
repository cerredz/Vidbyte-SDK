"""FILE: vidbyte/tools/toolsets/infinite.py

PURPOSE: Defines InfiniteMemoryAgentTools, the catalog of the three ordinary tools every agent in an InfiniteMemory tree holds: bash over the project folder, and grep and read_lines over the memory workspace.
ROLE IN CODEBASE: Built by vidbyte/agents/infinite/agent.py for the root agent, and get_tools is called by vidbyte/agents/infinite/launch.py for every generator and verifier; exported by vidbyte/tools/toolsets/__init__.py. Composes vidbyte/tools/builtins/bash.py, vidbyte/tools/builtins/code_search/grep.py, and vidbyte/tools/filesystem/read_lines.py.
ARCHITECTURE NOTE: A Tools subclass that holds only the three tools; the run-bound memory and launch tools live in vidbyte/agents/infinite/ because they need the workspace and the journal, and this layer may not import vidbyte.agents. Grep skips the run journals and the superseded entries, so a search finds only live memory, and its file-size cap is derived from the workspace token cap, so no file the workspace allows is too large to search.
FUNCTION INVENTORY: InfiniteMemoryAgentTools.__init__ is the narrated main function; get_tools returns bash, grep, and read_lines in that order.
COMMON MODIFICATION PATTERNS: A tool every agent should hold is added to get_tools, to INFINITE_RESERVED_TOOL_NAMES in vidbyte/lib/constants/infinite.py, and to the folder README's tool table together.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents; the memory and launch tools stay in the agent package. 2. Do not give read_lines write access; the memory tools are the only writers. 3. Do not point grep at the project folder; it searches the memory workspace.
KNOWN EDGE CASES: Bash is not confined to either folder, so a command can still write into the workspace; the workspace recounts its caps from disk before every tool write. read_lines can read the run journals and the superseded entries by path, although grep skips them.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5 and 9.2); vidbyte/agents/infinite/README.md; vidbyte/tools/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py and tests/features/infinite_memory_agent/test_infinite_memory_workspace.py
"""

from __future__ import annotations

from pathlib import Path

from vidbyte.lib.constants.infinite import (
    INFINITE_RUNS_DIRNAME,
    INFINITE_SUPERSEDED_FILE,
    INFINITE_UTF8_MAX_BYTES_PER_CHAR,
)
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.util.text import TOKEN_ESTIMATE_CHARS_PER_TOKEN
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.bash import BashTool
from vidbyte.tools.builtins.code_search.grep import GrepTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.filesystem.read_lines import ReadLinesTool


class InfiniteMemoryAgentTools(Tools):
    """Catalog of bash over the project folder plus grep and read_lines over the memory workspace."""

    def __init__(self, root_dir: Path, workspace_root: Path, max_tokens: int) -> None:
        # Put bash over the project folder first, then the two read-only
        # tools over the memory workspace.
        super().__init__(self.get_tools(root_dir, workspace_root, max_tokens))

    @staticmethod
    def get_tools(root_dir: Path, workspace_root: Path, max_tokens: int) -> tuple[BaseTool, ...]:
        """Return bash over root_dir, then grep and read_lines over workspace_root."""
        # @intent grep-sees-only-live-memory
        # Grep skips the run journals and the superseded entries, so a
        # search never returns an entry that was replaced. Its byte cap
        # is the largest file the token cap allows, so a large
        # entries.jsonl is still searched.
        largest_file_bytes = max_tokens * TOKEN_ESTIMATE_CHARS_PER_TOKEN * INFINITE_UTF8_MAX_BYTES_PER_CHAR
        grep = GrepTool(workspace_root, ignore_patterns=(INFINITE_RUNS_DIRNAME, INFINITE_SUPERSEDED_FILE), max_file_bytes=largest_file_bytes)
        return (BashTool(root_dir), grep, ReadLinesTool(FileSystemToolConfig(root=workspace_root)))


__all__ = ["InfiniteMemoryAgentTools"]
