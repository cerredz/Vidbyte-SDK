"""FILE: vidbyte/agents/jev/gate/__init__.py

PURPOSE: Exposes the JevAgent preflight gate (JevPreflightGate) and the step its clarity case triggers (JevClarificationAgent).
ROLE IN CODEBASE: JevAgent builds JevPreflightGate at construction and JevRuntime calls its pass_() gate; tests import the clarification agent to pin it in isolation.
ARCHITECTURE NOTE: This folder is where the fixed-question preflight logic lives; question text, flags, and records stay in vidbyte/lib/jev/, vidbyte/lib/enums/jev.py, and vidbyte/lib/dataclasses/jev.py. The tool selector keeps its own module, vidbyte/agents/jev/preflight.py.
COMMON MODIFICATION PATTERNS: Put the step a new preset triggers in its own module here, and add its case to JevPreflightGate.pass_.
KNOWN EDGE CASES: Importing this package performs no Jev call and needs no TypeSafe credential.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from vidbyte.agents.jev.gate.clarification import JevClarificationAgent
from vidbyte.agents.jev.gate.gate import JevPreflightGate

__all__ = ["JevClarificationAgent", "JevPreflightGate"]
