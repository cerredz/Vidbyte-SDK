"""FILE: vidbyte/agents/jev/continuation/__init__.py

PURPOSE: Exposes JevAgent's continuations: the JevContinuation contract JevRuntime calls at every finish attempt, and JevDoneContinuation, which sends the main agent back to work when an enabled done check fails.
ROLE IN CODEBASE: JevAgent builds its continuation at construction and passes it to JevRuntime; tests import both classes to pin them in isolation.
ARCHITECTURE NOTE: One module per continuation feature over the shared base, so a new way to continue a run is a new subclass rather than a branch in JevRuntime; message text lives in vidbyte/prompts/prompts/jev_continuation/.
COMMON MODIFICATION PATTERNS: Add a JevContinuation subclass in its own module here, export it, and build it in JevAgent.__init__.
KNOWN EDGE CASES: Importing this package performs no model or Jev call and needs no TypeSafe credential.
RELATED DOCS: skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from vidbyte.agents.jev.continuation.base import JevContinuation
from vidbyte.agents.jev.continuation.done import JevDoneContinuation

__all__ = ["JevContinuation", "JevDoneContinuation"]
