"""FILE: vidbyte/tools/toolsets/agent_swarm.py

PURPOSE: Defines AgentSwarmTools, the catalog of the five file and shell tools every agent of an AgentSwarm holds over the one shared workplace folder: bash, grep, read_lines, write_text, and patch_file.
ROLE IN CODEBASE: Built by AgentSwarmRuntime (vidbyte/agents/agent_swarm/runtime.py) for every member agent of a run; exported by vidbyte/tools/toolsets/__init__.py. Composes vidbyte/tools/builtins/bash.py, vidbyte/tools/builtins/code_search/grep.py, vidbyte/tools/filesystem/read_lines.py, vidbyte/tools/filesystem/write_text.py, and vidbyte/tools/builtins/editing/patch.py.
ARCHITECTURE NOTE: A Tools subclass that holds only the five tools. The run-bound message tool lives in vidbyte/agents/agent_swarm/ because it needs the running swarm, and this layer may not import vidbyte.agents; the swarm runtime appends it and the developer's optional search tool after these five. read_lines and write_text share one configuration that allows writing, so both see the same root folder.
FUNCTION INVENTORY: AgentSwarmTools.__init__ is the narrated main function; get_tools returns bash, grep, read_lines, write_text, and patch_file in that order.
COMMON MODIFICATION PATTERNS: A tool every swarm agent should hold is added to get_tools, to AGENT_SWARM_RESERVED_TOOL_NAMES in vidbyte/lib/constants/agent_swarm.py, and to the package README together.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents; the message tool stays in the agent package. 2. Do not add a search or fetch tool here; web search is the developer's opt-in search_tool. 3. Do not root two tools at different folders; every agent shares the one workplace.
KNOWN EDGE CASES: The file tools refuse a path outside the root, but bash is not confined and runs with the inherited environment. Two agents writing one file at the same time is not guarded; the last write wins.
RELATED DOCS: docs/spec/agent-swarm/spec.md (sections 8.5 and 9.2); vidbyte/agents/agent_swarm/README.md; vidbyte/tools/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py and tests/features/agent_swarm/test_agent_swarm_workplace.py
"""

from __future__ import annotations

from pathlib import Path

from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.bash import BashTool
from vidbyte.tools.builtins.code_search.grep import GrepTool
from vidbyte.tools.builtins.editing.patch import PatchTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.filesystem.read_lines import ReadLinesTool
from vidbyte.tools.filesystem.write_text import WriteTextTool


class AgentSwarmTools(Tools):
    """Catalog of bash, grep, read_lines, write_text, and patch_file over one shared workplace folder."""

    def __init__(self, root: Path) -> None:
        # Give every agent the same five tools over the shared folder:
        # the shell first, then search, read, write, and patch.
        super().__init__(self.get_tools(root))

    @staticmethod
    def get_tools(root: Path) -> tuple[BaseTool, ...]:
        """Return bash, grep, read_lines, write_text, and patch_file over root."""
        # Reading and writing share one configuration that allows
        # writing, so both resolve paths against the same folder and
        # refuse any path outside it.
        file_config = FileSystemToolConfig(root=root, allow_write=True)
        return (BashTool(root), GrepTool(root), ReadLinesTool(file_config), WriteTextTool(file_config), PatchTool(root))


__all__ = ["AgentSwarmTools"]
