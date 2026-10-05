"""FILE: vidbyte/agents/jev/brief/__init__.py

PURPOSE: Exports the run brief: JevRunBriefKeeper, its single entry point, and the parts it composes, the numbered event view, the facts reader, the separate writer agent, and the verifier.
ROLE IN CODEBASE: A caller builds one JevRunBriefKeeper per JevAgent and drives it between the main agent's iterations; the other exports exist for focused use and tests.
ARCHITECTURE NOTE: Each module owns one concern: events.py numbers and windows the run, facts.py counts, writer.py is the only model call, verifier.py decides what survives, and keeper.py decides when and composes the rest.
COMMON MODIFICATION PATTERNS: Add a behavior to the module that owns its concern and keep the keeper's public surface small.
KNOWN EDGE CASES: Nothing here changes a run on its own; the brief only exists where a caller drives a keeper.
RELATED DOCS: docs/design/jev-run-brief.md.
TESTS: tests/test_jev_run_brief.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.brief.events import JevRunBriefEvents
from vidbyte.agents.jev.brief.facts import JevRunFactsReader
from vidbyte.agents.jev.brief.keeper import JevRunBriefKeeper
from vidbyte.agents.jev.brief.verifier import JevRunBriefVerifier
from vidbyte.agents.jev.brief.writer import JevRunBriefWriter

__all__ = ["JevRunBriefEvents", "JevRunBriefKeeper", "JevRunBriefVerifier", "JevRunBriefWriter", "JevRunFactsReader"]
