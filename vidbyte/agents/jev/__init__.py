"""FILE: vidbyte/agents/jev/__init__.py

PURPOSE: Exposes the opinionated Jev agent facade, immutable settings, done-criteria presets, and dedicated runtime.
ROLE IN CODEBASE: This is the public package boundary imported by vidbyte.agents and application code.
ARCHITECTURE NOTE: Only the facade, settings, presets, and runtime are public; preset internals (motivating_case/), decision records, and provider transport stay private or lower-level.
COMMON MODIFICATION PATTERNS: Export a named capability settings type only when it becomes part of the supported JevAgent API.
KNOWN EDGE CASES: Importing this package must not resolve credentials or construct a TypeSafe decision runner.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from vidbyte.agents.jev.agent import JevAgent
from vidbyte.agents.jev.presets import JevPresets
from vidbyte.agents.jev.runtime import JevRuntime
from vidbyte.agents.jev.settings import JevAgentSettings

__all__ = ["JevAgent", "JevAgentSettings", "JevPresets", "JevRuntime"]
