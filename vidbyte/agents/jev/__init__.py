"""FILE: vidbyte/agents/jev/__init__.py

PURPOSE: Exposes the opinionated Jev agent facade, immutable settings, dedicated runtime, and the named preflight vocabulary callers configure and read.
ROLE IN CODEBASE: This is the public package boundary imported by vidbyte.agents and application code.
ARCHITECTURE NOTE: Preset, action, category, and result types are re-exported from `vidbyte.lib`; question text, decision records, and provider transport remain in their lower-level packages.
COMMON MODIFICATION PATTERNS: Export a named capability settings type only when it becomes part of the supported JevAgent API.
KNOWN EDGE CASES: Importing this package must not resolve credentials or construct a TypeSafe decision runner.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from vidbyte.agents.jev.agent import JevAgent
from vidbyte.agents.jev.runtime import JevRuntime
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.lib.dataclasses.jev import JevSecurityResult
from vidbyte.lib.enums.jev import (
    JevPreflightPreset,
    JevSecurityAction,
    JevSecurityCategory,
)

__all__ = [
    "JevAgent",
    "JevAgentSettings",
    "JevPreflightPreset",
    "JevRuntime",
    "JevSecurityAction",
    "JevSecurityCategory",
    "JevSecurityResult",
]
