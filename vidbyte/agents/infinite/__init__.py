"""FILE: vidbyte/agents/infinite/__init__.py

PURPOSE: Exposes InfiniteMemoryAgent, its two settings objects (InfiniteMemoryAgentSettings and InfiniteWorkspaceSettings), and InfiniteMemoryRuntime, the runtime that AgentRuntimeType.INFINITE_MEMORY resolves to.
ROLE IN CODEBASE: This is the public package boundary imported by vidbyte.agents, by the runtime registry's lazy import, and by application code.
ARCHITECTURE NOTE: The workspace, journal, memory tools, and launch tool stay internal to the package; their records and enums are public from vidbyte.lib.dataclasses.infinite and vidbyte.lib.enums, and the preset toolset from vidbyte.tools.toolsets.
FUNCTION INVENTORY: None; this module only re-exports the four public names.
COMMON MODIFICATION PATTERNS: Export a new name here only when it becomes part of the supported InfiniteMemoryAgent API, and mirror it in vidbyte/agents/__init__.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not export the workspace, journal, memory, or launch classes; they are internal. 2. Do not add logic here.
KNOWN EDGE CASES: Importing this package builds nothing and touches no folder; the workspace is created when an InfiniteMemoryAgent is built.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (section 8.5); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py
"""

from vidbyte.agents.infinite.agent import InfiniteMemoryAgent
from vidbyte.agents.infinite.runtime import InfiniteMemoryRuntime
from vidbyte.agents.infinite.settings import (
    InfiniteMemoryAgentSettings,
    InfiniteWorkspaceSettings,
)

__all__ = [
    "InfiniteMemoryAgent",
    "InfiniteMemoryAgentSettings",
    "InfiniteMemoryRuntime",
    "InfiniteWorkspaceSettings",
]
