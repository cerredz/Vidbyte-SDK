"""FILE: vidbyte/lib/integrations_budget.py

PURPOSE: Fits loaded source content to caller token budgets with explicit truncation accounting.
ROLE IN CODEBASE: SourceContext admits document items and reports how much content was retained.
ARCHITECTURE NOTE: ContextAdmission owns estimation and clipping; no module-level budget helpers exist.
COMMON MODIFICATION PATTERNS: Change the estimator or marker policy in ContextAdmission and update the budget tests.
KNOWN EDGE CASES: Zero budgets admit nothing, empty content costs nothing, and one boundary item may be clipped.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from vidbyte.lib.constants.integrations import (
    SOURCES_CHARS_PER_TOKEN,
    SOURCES_MIN_TOKEN_COST,
    SOURCES_MIN_TOKENS,
    SOURCES_TRUNCATION_MARKER,
)


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """Items admitted under one budget and the resulting accounting."""

    items: tuple[Any, ...]
    tokens_admitted: int
    tokens_original: int
    truncated: bool
    skipped: bool


class ContextAdmission:
    """Admits source items in order until an approximate token ceiling is reached."""

    def __init__(self, *, max_tokens: int) -> None:
        """Store one nonnegative budget for a single admission operation."""
        self.validate_budget(max_tokens)
        self._remaining = max_tokens

    @staticmethod
    def validate_budget(max_tokens: int) -> None:
        """Validate one nonnegative integer token budget."""
        if type(max_tokens) is not int or max_tokens < SOURCES_MIN_TOKENS:
            raise ValueError("ContextAdmission.max_tokens must be a nonnegative integer.")

    @property
    def remaining_tokens(self) -> int:
        """Return the approximate tokens still available."""
        return self._remaining

    def admit(self, items: tuple[Any, ...]) -> AdmissionResult:
        """Admit whole items, clip one boundary item, and skip the remainder."""
        admitted: list[Any] = []
        clipped_any = False
        for item in items:
            verdict = self._admit_one(item)
            if verdict is None:
                break
            admitted.append(verdict)
            clipped_any = clipped_any or bool(verdict.metadata.get("truncated", False))
        original = sum(self.estimate_tokens(item.content) for item in items)
        cost = sum(self.estimate_tokens(item.content) for item in admitted)
        return AdmissionResult(
            items=tuple(admitted),
            tokens_admitted=cost,
            tokens_original=original,
            truncated=clipped_any,
            skipped=len(admitted) < len(items),
        )

    def _admit_one(self, item: Any) -> Any | None:
        """Admit one item whole, clip it to the remaining budget, or skip it."""
        cost = self.estimate_tokens(item.content)
        if cost <= self._remaining:
            self._remaining -= cost
            return item
        if self._remaining <= SOURCES_MIN_TOKENS:
            return None
        clipped = self._clip_to_tokens(item.content, self._remaining)
        self._remaining -= self.estimate_tokens(clipped)
        metadata = dict(item.metadata)
        metadata["truncated"] = True
        return replace(item, content=clipped, metadata=metadata)

    @staticmethod
    def estimate_tokens(content: str) -> int:
        """Approximate text cost with the documented shared character ratio."""
        if not content:
            return SOURCES_MIN_TOKENS
        return max(SOURCES_MIN_TOKEN_COST, len(content) // SOURCES_CHARS_PER_TOKEN)

    @classmethod
    def _clip_to_tokens(cls, content: str, budget: int) -> str:
        """Clip text to an approximate token budget with the marker counted."""
        room_chars = budget * SOURCES_CHARS_PER_TOKEN - len(SOURCES_TRUNCATION_MARKER)
        if room_chars <= SOURCES_MIN_TOKENS:
            return SOURCES_TRUNCATION_MARKER[: max(SOURCES_MIN_TOKENS, budget * SOURCES_CHARS_PER_TOKEN)]
        return f"{content[:room_chars]}{SOURCES_TRUNCATION_MARKER}"


__all__ = ["AdmissionResult", "ContextAdmission"]
