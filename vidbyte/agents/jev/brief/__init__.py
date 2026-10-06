"""FILE: vidbyte/agents/jev/brief/__init__.py

PURPOSE: Exposes the JEV brief keeper and its tool-free structured note writer.
ROLE IN CODEBASE: JEV agent integrations import the public brief components from this package.
ARCHITECTURE NOTE: The keeper owns cadence and state; the writer builds windows, verifies notes, and performs model calls.
COMMON MODIFICATION PATTERNS: Keep the package exports aligned with the brief implementation modules.
KNOWN EDGE CASES: A successful empty note delta still advances the keeper's event pointer.
RELATED DOCS: skills/jev-agent/SKILL.md and vidbyte/agents/jev/README.md.
TESTS: tests/test_jev_run_brief.py.
"""

from vidbyte.agents.jev.brief.keeper import JevRunBriefKeeper
from vidbyte.agents.jev.brief.writer import JevRunBriefWriter

__all__ = ["JevRunBriefKeeper", "JevRunBriefWriter"]
