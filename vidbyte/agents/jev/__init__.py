"""FILE: vidbyte/agents/jev/__init__.py

PURPOSE: Exposes the opinionated Jev agent facade, immutable settings, and dedicated runtime.
ROLE IN CODEBASE: This is the public package boundary imported by vidbyte.agents and application code.
ARCHITECTURE NOTE: The scaffold types plus the self-alignment editor and its result records are public; decision records and provider transport remain in their lower-level packages.
COMMON MODIFICATION PATTERNS: Export a named capability settings type only when it becomes part of the supported JevAgent API.
KNOWN EDGE CASES: Importing this package must not resolve credentials or construct a TypeSafe decision runner.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from vidbyte.agents.jev.agent import JevAgent
from vidbyte.agents.jev.alignment import (
    JevAgentAlignment,
    JevAlignmentResult,
    JevAlignmentStatus,
    JevResponse,
)
from vidbyte.agents.jev.presets import JevPreflightPreset
from vidbyte.agents.jev.runtime import JevRuntime
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.lib.dataclasses.jev_alignment import JevAlignmentInput

__all__ = ["JevAgent", "JevAgentAlignment", "JevAgentSettings", "JevAlignmentInput", "JevAlignmentResult", "JevAlignmentStatus", "JevPreflightPreset", "JevResponse", "JevRuntime"]
