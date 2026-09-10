"""FILE: vidbyte/integrations/budget.py

PURPOSE: Fits loaded source content to caller budgets with explicit truncation accounting.
ROLE IN CODEBASE: SourceContext admits items against max_tokens and tools clip payloads against max_output_bytes.
ARCHITECTURE NOTE: The truncation marker always counts toward the budget it clips for, and zero budgets admit nothing.
COMMON MODIFICATION PATTERNS: Swap the character-ratio estimator for a tokenizer by changing estimate_tokens alone.
KNOWN EDGE CASES: Empty content costs nothing, one boundary item truncates while the rest skip, and markers never overflow.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py and scripts/test-source-context-tools.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.lib.constants.integrations import SOURCES_CHARS_PER_TOKEN, SOURCES_TRUNCATION_MARKER


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """Items that fit the budget, the tokens they cost, and whether anything clipped."""

    items: tuple[DocumentContextItem, ...]
    tokens_admitted: int
    tokens_original: int
    truncated: bool
    skipped: bool


class ContextAdmission:
    """Admits context items in order until an approximate token ceiling is reached."""

    def __init__(self, *, max_tokens: int) -> None:
        """Track the remaining approximate tokens for one load operation."""
        self._remaining = max(0, max_tokens)

    @property
    def remaining_tokens(self) -> int:
        """Return the approximate tokens still available to admit."""
        return self._remaining

    def admit(self, items: tuple[DocumentContextItem, ...]) -> AdmissionResult:
        """Admit items whole, truncate one boundary item, and skip the remainder."""
        admitted: list[DocumentContextItem] = []
        clipped_any = False
        for item in items:
            verdict = self._admit_one(item)
            if verdict is None:
                break
            admitted.append(verdict)
            clipped_any = clipped_any or verdict.metadata.get("truncated", False)
        original = sum(estimate_tokens(item.content) for item in items)
        cost = sum(estimate_tokens(item.content) for item in admitted)
        return AdmissionResult(items=tuple(admitted), tokens_admitted=cost, tokens_original=original, truncated=clipped_any, skipped=len(admitted) < len(items))

    def _admit_one(self, item: DocumentContextItem) -> DocumentContextItem | None:
        """Admit one item whole, truncated to the remaining budget, or not at all."""
        cost = estimate_tokens(item.content)
        if cost <= self._remaining:
            self._remaining -= cost
            return item
        if self._remaining <= 0:
            return None
        clipped = clip_to_tokens(item.content, self._remaining)
        self._remaining -= estimate_tokens(clipped)
        metadata = dict(item.metadata)
        metadata["truncated"] = True
        return DocumentContextItem(source=item.source, content=clipped, title=item.title, document_id=item.document_id, metadata=metadata, kind=item.kind, primitive_id=item.primitive_id, primitive_frozen=item.primitive_frozen)


def estimate_tokens(content: str) -> int:
    """Approximate one text's token cost with the shared character ratio."""
    if not content:
        return 0
    return max(1, len(content) // SOURCES_CHARS_PER_TOKEN)


def clip_to_tokens(content: str, budget: int) -> str:
    """Clip text to an approximate token budget with the marker counted inside."""
    room_chars = budget * SOURCES_CHARS_PER_TOKEN - len(SOURCES_TRUNCATION_MARKER)
    if room_chars <= 0:
        return SOURCES_TRUNCATION_MARKER[: max(0, budget * SOURCES_CHARS_PER_TOKEN)]
    return f"{content[:room_chars]}{SOURCES_TRUNCATION_MARKER}"


__all__ = [
    "AdmissionResult",
    "ContextAdmission",
    "clip_to_tokens",
    "estimate_tokens",
]
