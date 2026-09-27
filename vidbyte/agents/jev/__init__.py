"""FILE: vidbyte/agents/jev/__init__.py

PURPOSE: Exposes JevAgent, its validated settings and runtime, completion-criteria types, preflight flags, and response records.
ROLE IN CODEBASE: This is the public Jev package boundary imported by vidbyte.agents, root vidbyte, and application code.
ARCHITECTURE NOTE: Completion criteria and supported public Jev response types are re-exported; gate internals and provider transport remain in lower-level packages.
COMMON MODIFICATION PATTERNS: Export supported Jev settings, criterion, preset, and response types here, then mirror them through vidbyte.agents and root vidbyte.
KNOWN EDGE CASES: Importing this package must not resolve credentials or construct a TypeSafe decision runner.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from vidbyte.agents.jev.agent import JevAgent
from vidbyte.agents.jev.done_criteria import (
    JevDoneCriteria,
    JevDoneCriterion,
    JevPreset,
    MinimumTime,
)
from vidbyte.agents.jev.runtime import JevRuntime
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.lib.dataclasses.jev import (
    JevAgentResponse,
    JevClarification,
    JevClarifyingQuestion,
    JevPresetResult,
)
from vidbyte.lib.enums.jev import JevPreflightPreset

__all__ = [
    "JevAgent",
    "JevAgentResponse",
    "JevAgentSettings",
    "JevClarification",
    "JevClarifyingQuestion",
    "JevDoneCriteria",
    "JevDoneCriterion",
    "JevPreflightPreset",
    "JevPreset",
    "JevPresetResult",
    "JevRuntime",
    "MinimumTime",
]
