"""FILE: vidbyte/agents/jev/__init__.py

PURPOSE: Exposes the Jev agent, validated settings, dedicated runtime, and named completion-criteria API.
ROLE IN CODEBASE: This is the public package boundary imported by vidbyte.agents, root vidbyte, and application code.
ARCHITECTURE NOTE: Completion criteria are public policy types; decision records and provider transport remain in their lower-level packages.
COMMON MODIFICATION PATTERNS: Export supported criterion and preset types here, then mirror them through vidbyte.agents and root vidbyte.
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

__all__ = ["JevAgent", "JevAgentSettings", "JevDoneCriteria", "JevDoneCriterion", "JevPreset", "JevRuntime", "MinimumTime"]
