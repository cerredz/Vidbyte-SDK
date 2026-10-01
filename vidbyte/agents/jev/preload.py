"""FILE: vidbyte/agents/jev/preload.py

PURPOSE: Defines the narrow Jev context-preload contract used by request-time capabilities that transform an immutable BaseAgentContext before the main loop.
ROLE IN CODEBASE: JevRuntime runs this contract after gate and alignment passes; JevSkillsPreload is its current implementation and returns a replacement context without changing the tool catalog.
FUNCTION INVENTORY:
    JevPreload.run(message, context) -> BaseAgentContext: asynchronously returns the effective context for one run.
COMMON MODIFICATION PATTERNS: Keep this contract limited to context input and output. Put feature questions, scoring, response records, and fail-open policy in the named preload implementation.
WHAT NOT TO DO:
    1. Do not return or mutate a Tools catalog; JevPreflight already owns that boundary.
    2. Do not mutate the caller's context; implementations should return an immutable replacement.
    3. Do not run the main model or manage done-check state from this contract.
KNOWN EDGE CASES: Gate closure and specialist delegation happen before a preload is invoked. The caller must preserve runtime state and invoke this only within the main agent run.
RELATED DOCS: `docs/design/jev-skills-preload.md` and `vidbyte/agents/jev/preflight.py`.
TESTS: `tests/test_jev_skill_preload.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from vidbyte.lib.dataclasses.context import BaseAgentContext


class JevPreload(ABC):
    """A request-local transform that returns the context the main agent will read."""

    @abstractmethod
    async def run(self, message: str, context: BaseAgentContext) -> BaseAgentContext:
        # @intent preload-is-context-transform-only
        # Implementations may add request-local context but the runtime continues to own tools, run state, and the main agent loop.
        """Return a context replacement for this request without mutating caller state."""


__all__ = ["JevPreload"]
