"""FILE: vidbyte/agents/infinite/__init__.py

PURPOSE: Exposes InfiniteMemoryAgent, its two settings objects (InfiniteMemoryAgentSettings and InfiniteWorkspaceSettings), InfiniteMemoryRuntime, the runtime that AgentRuntimeType.INFINITE_MEMORY resolves to, and the run's event and handoff types: InfiniteEvent, InfiniteEventKind, and InfiniteHandoff.
ROLE IN CODEBASE: This is the public package boundary imported by vidbyte.agents, by the runtime registry's lazy import, and by application code.
ARCHITECTURE NOTE: The workspace, journal, memory tools, launch tool, and event writer stay internal to the package; their records and enums are public from vidbyte.lib.dataclasses.infinite and vidbyte.lib.enums, and the preset toolset from vidbyte.tools.toolsets. InfiniteEvent and InfiniteEventKind are re-exported here from lib, and InfiniteHandoff from vidbyte.context.handoff.infinite, because a developer's on_event sink and run_handoff caller need them; the details records stay in lib only.
FUNCTION INVENTORY: None; this module only re-exports the seven public names, mirrored in vidbyte/agents/__init__.py.
COMMON MODIFICATION PATTERNS: Export a new name here only when it becomes part of the supported InfiniteMemoryAgent API, and mirror it in vidbyte/agents/__init__.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not export the workspace, journal, memory, launch, or events classes; they are internal. 2. Do not export the event details records; they stay in vidbyte.lib.dataclasses.infinite. 3. Do not add logic here.
KNOWN EDGE CASES: Importing this package builds nothing and touches no folder; the workspace is created when an InfiniteMemoryAgent is built.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (section 8.5); docs/spec/infinite-memory-events/spec.md (section 9.2); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py and tests/features/infinite_memory_agent/test_infinite_memory_events_records.py
"""

from vidbyte.agents.infinite.agent import InfiniteMemoryAgent
from vidbyte.agents.infinite.runtime import InfiniteMemoryRuntime
from vidbyte.agents.infinite.settings import (
    InfiniteMemoryAgentSettings,
    InfiniteWorkspaceSettings,
)
from vidbyte.context.handoff.infinite import InfiniteHandoff
from vidbyte.lib.dataclasses.infinite import InfiniteEvent
from vidbyte.lib.enums.infinite import InfiniteEventKind

__all__ = [
    "InfiniteEvent",
    "InfiniteEventKind",
    "InfiniteHandoff",
    "InfiniteMemoryAgent",
    "InfiniteMemoryAgentSettings",
    "InfiniteMemoryRuntime",
    "InfiniteWorkspaceSettings",
]
