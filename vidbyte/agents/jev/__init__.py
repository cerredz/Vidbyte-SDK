"""FILE: vidbyte/agents/jev/__init__.py

PURPOSE: Exposes JevAgent, its settings, its runtime, the preflight flags, and the records a caller reads on JevAgent.response.
ROLE IN CODEBASE: This is the public package boundary imported by vidbyte.agents and application code.
ARCHITECTURE NOTE: The agent types plus the preflight flag enum and result records are public; they are re-exported from vidbyte.lib, while preflight questions, JevPreflight, decision records, and provider transport stay in their lower-level packages.
COMMON MODIFICATION PATTERNS: Export a named capability settings type only when it becomes part of the supported JevAgent API.
KNOWN EDGE CASES: Importing this package must not resolve credentials or construct a TypeSafe decision runner.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from vidbyte.agents.jev.agent import JevAgent
from vidbyte.agents.jev.runtime import JevRuntime
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.lib.dataclasses.jev import (
    JevAgentResponse,
    JevClarification,
    JevPresetResult,
    JevToolSelection,
)
from vidbyte.lib.enums.jev import JevPreflightPreset

__all__ = [
    "JevAgent",
    "JevAgentResponse",
    "JevAgentSettings",
    "JevClarification",
    "JevPreflightPreset",
    "JevPresetResult",
    "JevRuntime",
    "JevToolSelection",
]
