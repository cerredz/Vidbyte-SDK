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
    Written by vidbyte.tools.builtins.cot.context and re-exported through
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
    """Snapshot of what occupies the context window and whether it is crowded.

    This primitive is the agent's self-report on its own working memory:
    which items currently dominate attention, how much headroom remains
    before load-bearing facts start getting pushed out or drowned, and what
    the agent itself would choose to drop first. It is a snapshot rather than
    a ledger — each call replaces the previous one, so a reader always sees
    the current window state rather than a history of past states. Downstream
    monitors use it to decide whether compaction is warranted before the next
    major step, and to catch crowding before it silently degrades later
    reasoning.
    """

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
    """Records whether the fact the next step depends on is still visible in window.

    Each call is a pre-flight check performed immediately before a step whose
    correctness hinges on an earlier detail: it names the dependency, states
    whether that dependency is currently visible, and — when it is not —
    records how the agent intends to recover it before acting. The
    criticality field lets a reader triage these checks at a glance, since a
    missed low-criticality dependency and a missed blocking one carry very
    different consequences. Read together, a run's attention checks form a
    trail of exactly which prior facts later steps leaned on and whether that
    lean was verified or assumed.
    """

    next_step: str
    depends_on: str
    still_visible: str
    if_no_recover_how: str | None = None
    criticality: str | None = None
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
        if self.criticality:
            lines.append(f"Criticality: {self.criticality}")
        if self.could_state_from_memory is not None:
            lines.append(f"Could State From Memory: {self.could_state_from_memory:.2f}")
        if self.if_no_recover_how:
            lines.append(f"Recovery If Not: {self.if_no_recover_how}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class RecallTestContextItem:
    """Records one from-memory recall attempt and whether it matched the source.

    Each entry captures a fact restated purely from memory before its source
    is re-checked, paired with a confidence estimate given in advance of
    verification. When the agent goes on to verify the claim in the same
    call, the record also holds the comparison outcome and, when it matters,
    how costly being wrong would have been. Read across a run, these records
    turn an agent's self-trust in its own memory into measurable data instead
    of an unexamined assumption.
    """

    claimed_fact: str
    confidence: float
    verified_now: str = "no"
    matches: str | None = None
    source_step: str | None = None
    impact_if_wrong: str | None = None
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
        if self.impact_if_wrong:
            lines.append(f"Impact If Wrong: {self.impact_if_wrong}")
        if self.source_step:
            lines.append(f"Source: {self.source_step}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class ForgetDecisionContextItem:
    """Records the deliberate drop of information from active consideration.

    Each entry documents one conscious decision to stop tracking something,
    distinguishing intentional pruning from the silent, undecided kind of
    forgetting that later causes a run to act on a gap it does not know it
    has. It names what is being dropped, why that is currently safe, what
    would have to still depend on it for the decision to be wrong, and what
    prompted the decision in the first place. Because the record states
    recoverability and reload cost up front, a later reader can judge how
    dangerous the drop actually was without re-deriving that judgment from
    scratch.
    """

    what: str
    why: str
    recoverable: str
    reload_cost: str = "moderate"
    what_still_depends_on_it: str = ""
    trigger: str | None = None
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
        if self.trigger:
            lines.append(f"Trigger: {self.trigger}")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "AttentionCheckContextItem",
    "ContextLoadContextItem",
    "ForgetDecisionContextItem",
    "RecallTestContextItem",
]
