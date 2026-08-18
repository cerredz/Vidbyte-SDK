"""Context Protocol Header

Description:
    Defines the context-window awareness monitoring primitives.
Purpose:
    Gives the cot_context tools typed, bounded context units tracking what
    occupies the window, whether load-bearing facts remain visible, memory
    recall accuracy, and deliberate forgetting.
Architecture:
    - ContextLoadContextItem, AttentionCheckContextItem, RecallTestContextItem,
      ForgetDecisionContextItem: frozen, slotted dataclasses with deterministic
      renderers bounded by max_chars.
Relations:
    Written by vidbyte.tools.builtins.cot_context and re-exported through
    vidbyte.context.primitives.
Similar Files:
    - `vidbyte/context/primitives/cot_events.py`
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _extend_section, _truncate_text

_DEFAULT_MAX_CHARS = 2000


@dataclass(frozen=True, slots=True)
class ContextLoadContextItem:
    """Snapshot of what occupies the context window and whether it is crowded."""

    occupying: tuple[str, ...]
    crowded: str
    what_to_forget: str
    oldest_unreferenced: str | None = None
    imbalance: str = "none"
    compaction_recommended: str = "no"
    title: str = "Context Load"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "context_load"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the load snapshot in deterministic order, bounded by max_chars.
        lines = [
            f"Crowded: {self.crowded}",
            f"Imbalance: {self.imbalance}",
            f"Compaction Recommended: {self.compaction_recommended}",
        ]
        _extend_section(lines, "Top Consumers", self.occupying)
        if self.oldest_unreferenced:
            lines.append(f"Oldest Unreferenced: {self.oldest_unreferenced}")
        lines.append(f"What To Forget: {self.what_to_forget}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class AttentionCheckContextItem:
    """Records whether the fact the next step depends on is still visible in window."""

    next_step: str
    depends_on: str
    still_visible: str
    if_no_recover_how: str | None = None
    could_state_from_memory: float | None = None
    title: str = "Attention Check"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "attention_check"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the dependency visibility check, bounded by max_chars.
        lines = [
            f"Next Step: {self.next_step}",
            f"Depends On: {self.depends_on}",
            f"Still Visible: {self.still_visible}",
        ]
        if self.could_state_from_memory is not None:
            lines.append(f"Could State From Memory: {self.could_state_from_memory:.2f}")
        if self.if_no_recover_how:
            lines.append(f"Recovery If Not: {self.if_no_recover_how}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class RecallTestContextItem:
    """Records one from-memory recall attempt and whether it matched the source."""

    claimed_fact: str
    confidence: float
    verified_now: str = "no"
    matches: str | None = None
    source_step: str | None = None
    title: str = "Recall Test"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "recall_test"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the recall claim, its confidence, and verification outcome, bounded by max_chars.
        lines = [
            f"Confidence In Memory: {self.confidence:.2f}",
            f"Claimed Fact: {self.claimed_fact}",
            f"Verified Now: {self.verified_now}",
        ]
        if self.matches:
            lines.append(f"Matches: {self.matches}")
        if self.source_step:
            lines.append(f"Source: {self.source_step}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class ForgetDecisionContextItem:
    """Records the deliberate drop of information from active consideration."""

    what: str
    why: str
    recoverable: str
    reload_cost: str = "moderate"
    what_still_depends_on_it: str = ""
    title: str = "Forget Decision"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "forget_decision"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the forgetting decision and its dependencies, bounded by max_chars.
        lines = [
            f"Forgotten: {self.what}",
            f"Why: {self.why}",
            f"Recoverable: {self.recoverable}",
            f"Reload Cost: {self.reload_cost}",
            f"Still Depends On It: {self.what_still_depends_on_it or 'nothing recorded'}",
        ]
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "AttentionCheckContextItem",
    "ContextLoadContextItem",
    "ForgetDecisionContextItem",
    "RecallTestContextItem",
]
