"""FILE: vidbyte/agents/jev/continuation/base.py

PURPOSE: Defines JevContinuation, the contract JevRuntime calls at every finish attempt of JevAgent's main agent: should_continue() decides whether the run keeps going, and continue_() shapes what the main agent reads when it does.
ROLE IN CODEBASE: JevAgent builds one continuation at construction and passes it to JevRuntime, whose _continue_finish_attempt hook asks should_continue() and, on True, calls continue_() with the loop's own messages; JevDoneContinuation (done.py) is the first subclass.
ARCHITECTURE NOTE: The runtime holds no continuation logic, so each continuation feature is its own subclass with its own reason to continue and its own message, and adding one never adds a branch to JevRuntime.
COMMON MODIFICATION PATTERNS: Subclass JevContinuation in a new module in this folder, build it in JevAgent.__init__, and keep its message text in a vidbyte/prompts asset.
KNOWN EDGE CASES: continue_() is called only after should_continue() returned True on the same finish attempt, so a subclass may keep what it decided between the two calls; like the JevAgent that owns it, one instance serves one run at a time.
RELATED DOCS: skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from vidbyte.context.manager import ContextManager
from vidbyte.lib.dataclasses.jev import JevContinuationEvidence
from vidbyte.tools.types import ToolCallContext


# Load skills/jev-continuation/SKILL.md before adding a continuation feature: a new done check extends
# JevDoneContinuation and JevRunState, and that skill says when a new subclass of this contract is warranted instead.
class JevContinuation(ABC):
    """Decides at every finish attempt whether JevAgent's main agent goes back to work, and what it reads when it does."""

    @abstractmethod
    async def should_continue(
        self,
        final_answer: str,
        responses: Sequence[str],
        calls: Sequence[ToolCallContext],
        context_manager: ContextManager,
    ) -> bool:
        """Return True when the main agent must keep working instead of finishing with `final_answer`."""

    def budget_extension(self) -> tuple[int, int, int]:
        """Return extra iteration, token, and tool-call limits for this continuation, defaulting to none."""
        return 0, 0, 0

    @abstractmethod
    def continue_(self, messages: list[dict[str, Any]], context_manager: ContextManager) -> JevContinuationEvidence | None:
        """Append the continuation and optionally return its evidence segment after should_continue() returned True."""


__all__ = ["JevContinuation"]
