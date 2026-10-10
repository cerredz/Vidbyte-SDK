"""FILE: vidbyte/agents/jev/done/__init__.py

PURPOSE: Exposes JevAgent's done-check machinery: JevRunState, which writes the run state and runs the enabled done checks, JevReviewer, the strict reviewer the self-review check runs first, and JevHandoff, which compiles the evidence those checks judge.
ROLE IN CODEBASE: JevAgent builds one JevRunState at construction when JevRuntimeSettings.continual enables a done check, and JevRuntime calls its begin() before the main loop and check() at every finish attempt; tests import both agents to pin them in isolation.
ARCHITECTURE NOTE: This folder is where the done-check logic lives; question text, the check vocabulary, thresholds, and records stay in vidbyte/lib/jev/done/, vidbyte/lib/enums/jev.py, vidbyte/lib/constants/jev.py, and vidbyte/lib/dataclasses/jev.py.
COMMON MODIFICATION PATTERNS: Add a done check's run-state section and evidence section to the _SECTIONS maps of JevRunState and JevHandoff, and its commented case to JevRunState._section and JevRunState._judge; what the main agent reads when it fails goes in JevDoneContinuation._explain (vidbyte/agents/jev/continuation/).
KNOWN EDGE CASES: Importing this package performs no model or Jev call and needs no TypeSafe credential.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-can-simplify-done-criteria.md, skills/jev-agent/SKILL.md, and skills/jev-continuation/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from vidbyte.agents.jev.done.handoff import JevHandoff
from vidbyte.agents.jev.done.relation import JevRunStateRelation
from vidbyte.agents.jev.done.reviewer import JevReviewer
from vidbyte.agents.jev.done.run_state import JevRunState

__all__ = ["JevHandoff", "JevReviewer", "JevRunState", "JevRunStateRelation"]
