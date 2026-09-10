"""FILE: vidbyte/integrations/budget.py

PURPOSE: Bounds both access paths — admitting loaded content against a token ceiling and confining agent exploration to a call and byte ceiling.
ROLE IN CODEBASE: The only component that decides what fits in the window, so under-delivery is always recorded rather than silent.
ARCHITECTURE NOTE: Admission returns a typed record per item, which the report renders; the budget never mutates a caller's items in place.
COMMON MODIFICATION PATTERNS: Replace the character-ratio estimator with an injected tokenizer by widening ContextAdmissionBudget's constructor, leaving admit() unchanged.
KNOWN EDGE CASES: A zero budget admits nothing without raising, an empty document costs nothing, and truncation preserves the untrusted-content fence.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: tests/test_sources_access_layer.py and scripts/test_sources_access_layer.py.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.lib.config.sources import UNTRUSTED_CONTENT_END
from vidbyte.lib.constants.integrations import (
    INTEGRATIONS_CHARS_PER_TOKEN,
    INTEGRATIONS_MIN_TRUNCATION_CHARS,
    INTEGRATIONS_TRUNCATION_MARKER,
)
from vidbyte.lib.enums.integrations import LoadOutcome


@dataclass(frozen=True, slots=True)
class BudgetAdmission:
    """The items one selection actually contributed, and what the budget did to them."""

    items: tuple[DocumentContextItem, ...]
    outcome: LoadOutcome
    tokens_admitted: int
    tokens_original: int


class ContextAdmissionBudget:
    """Admits loaded context items in order until a token ceiling is reached."""

    def __init__(self, *, max_tokens: int) -> None:
        # Remaining tokens are consumed across every admit() call for one resolution.
        self._max_tokens = max_tokens
        self._remaining = max_tokens

    @property
    def remaining_tokens(self) -> int:
        """Return how many estimated tokens are still available to admit."""
        return self._remaining

    def admit(self, items: tuple[DocumentContextItem, ...]) -> BudgetAdmission:
        """Admit as many items as fit, truncating one boundary item and skipping the rest."""
        admitted: list[DocumentContextItem] = []
        tokens_original = sum(self.estimate_tokens(item.content) for item in items)
        truncated_any = False
        for item in items:
            verdict = self._admit_one(item)
            if verdict is None:
                break
            admitted.append(verdict.item)
            truncated_any = truncated_any or verdict.truncated
        tokens_admitted = sum(self.estimate_tokens(item.content) for item in admitted)
        outcome = self._outcome(skipped=len(admitted) < len(items), truncated=truncated_any)
        return BudgetAdmission(items=tuple(admitted), outcome=outcome, tokens_admitted=tokens_admitted, tokens_original=tokens_original)

    @staticmethod
    def _outcome(*, skipped: bool, truncated: bool) -> LoadOutcome:
        """Return the single outcome that most honestly describes an admission."""
        if skipped:
            return LoadOutcome.SKIPPED
        if truncated:
            return LoadOutcome.TRUNCATED
        return LoadOutcome.LOADED

    def _admit_one(self, item: DocumentContextItem) -> "_AdmittedItem | None":
        """Admit one item whole, truncated to the remaining budget, or not at all."""
        cost = self.estimate_tokens(item.content)
        if cost <= self._remaining:
            self._remaining -= cost
            return _AdmittedItem(item=item, truncated=False)
        available_chars = self._remaining * INTEGRATIONS_CHARS_PER_TOKEN
        if available_chars < INTEGRATIONS_MIN_TRUNCATION_CHARS:
            return None
        truncated = self._truncate(item, available_chars)
        self._remaining -= self.estimate_tokens(truncated.content)
        self._remaining = max(self._remaining, 0)
        return _AdmittedItem(item=truncated, truncated=True)

    def _truncate(self, item: DocumentContextItem, available_chars: int) -> DocumentContextItem:
        """Return a copy of an item cut to the available characters, marked and re-fenced."""
        # @intent redaction
        # Slicing raw content can cut through the untrusted-content fence that keeps
        # a model from reading provider text as instruction, so the closing marker is
        # re-appended whenever the original carried one and the cut removed it.
        body = item.content[:available_chars] + INTEGRATIONS_TRUNCATION_MARKER
        if UNTRUSTED_CONTENT_END in item.content and UNTRUSTED_CONTENT_END not in body:
            body = f"{body}\n{UNTRUSTED_CONTENT_END}"
        metadata = dict(item.metadata)
        metadata["truncated"] = True
        metadata["original_chars"] = len(item.content)
        return dataclasses.replace(item, content=body, metadata=metadata)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate a text's token cost from its character count, rounding up."""
        if not text:
            return 0
        return math.ceil(len(text) / INTEGRATIONS_CHARS_PER_TOKEN)


@dataclass(frozen=True, slots=True)
class _AdmittedItem:
    """One item that cleared the budget, and whether it had to be cut to fit."""

    item: DocumentContextItem
    truncated: bool


class ToolBudget:
    """Confines an agent's provider exploration to a call count and a cumulative byte ceiling."""

    def __init__(self, *, max_calls: int, max_bytes: int) -> None:
        # One budget is shared by every scoped tool built for a single resolution.
        self._max_calls = max_calls
        self._max_bytes = max_bytes
        self._calls_used = 0
        self._bytes_used = 0
        self._exhausted = False

    def charge(self, byte_count: int) -> bool:
        """Record one tool call and its payload, returning False once a ceiling is crossed."""
        # @intent permissions
        # Exhaustion is sticky: once either ceiling is crossed the budget stays
        # closed for the rest of the run, so a refused agent cannot retry its way
        # back into an unbounded exploration.
        if self._exhausted:
            return False
        self._calls_used += 1
        self._bytes_used += max(byte_count, 0)
        if self._calls_used > self._max_calls or self._bytes_used > self._max_bytes:
            self._exhausted = True
            return False
        return True

    def would_exceed(self) -> bool:
        """Return whether this budget has already refused a call."""
        return self._exhausted

    def remaining_calls(self) -> int:
        """Return how many tool calls remain before the call ceiling is reached."""
        return max(self._max_calls - self._calls_used, 0)


__all__ = [
    "BudgetAdmission",
    "ContextAdmissionBudget",
    "ToolBudget",
]
