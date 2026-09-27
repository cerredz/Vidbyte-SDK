"""FILE: vidbyte/agents/jev/done/__init__.py

PURPOSE: Exposes the JevAgent done gate (JevDoneGate) and the run report it writes (JevRunReport).
ROLE IN CODEBASE: JevAgent builds JevDoneGate at construction and JevRuntime calls its start() and review(); callers read JevRunReport on JevAgent.response.run_report.
ARCHITECTURE NOTE: This folder is where the done-check logic lives, the finish-time counterpart of vidbyte/agents/jev/gate/: run_state.py holds the records and the JevRunSection contract, builders.py the two generative builders, event_log.py the numbered log, and one module per done check (required_sequence.py).
COMMON MODIFICATION PATTERNS: Put a new done check in its own JevRunSection module here, and return it from JevDoneGate.enabled_sections.
KNOWN EDGE CASES: Importing this package performs no model or Jev call and needs no TypeSafe credential.
RELATED DOCS: docs/design/jev-required-sequence.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_required_sequence.py.
"""

from vidbyte.agents.jev.done.gate import JevDoneGate
from vidbyte.agents.jev.done.run_state import JevRunReport

__all__ = ["JevDoneGate", "JevRunReport"]
