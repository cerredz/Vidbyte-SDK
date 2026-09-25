"""FILE: vidbyte/agents/jev/preflight/__init__.py

PURPOSE: Exposes the JevAgent preflight gate (JevPreflight) and the steps its cases trigger (JevPreflightTools and JevClarificationAgent).
ROLE IN CODEBASE: JevAgent builds JevPreflight at construction and JevRuntime calls its pass_() gate; tests import the steps to pin them in isolation.
ARCHITECTURE NOTE: This folder is where the preflight logic lives; question text, flags, and records stay in vidbyte/lib/jev/, vidbyte/lib/enums/jev.py, and vidbyte/lib/dataclasses/jev.py.
COMMON MODIFICATION PATTERNS: Put the step a new preset triggers in its own module here, and add its case to JevPreflight.pass_.
KNOWN EDGE CASES: Importing this package performs no Jev call and needs no TypeSafe credential.
RELATED DOCS: docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, and scripts/test-jev-preflight.py.
"""

from vidbyte.agents.jev.preflight.clarification import JevClarificationAgent
from vidbyte.agents.jev.preflight.preflight import JevPreflight
from vidbyte.agents.jev.preflight.tools import JevPreflightTools

__all__ = ["JevClarificationAgent", "JevPreflight", "JevPreflightTools"]
