"""Context Protocol Header

Description:
    Defines the inter-agent delegation epistemics monitoring primitives.
Purpose:
    Gives the cot_delegation tools typed, bounded context units tracking what
    was delegated with which assumptions, what came back and how it was
    trusted, why work crossed an agent boundary, brief completeness,
    subagent failure attribution, and current blocking dependencies.
Architecture:
    - DelegationBriefContextItem, DelegationReceiptContextItem,
      HandoffWhyContextItem, HandoffCompletenessContextItem,
      SubagentFailuresContextItem, BlockedOnContextItem: frozen, slotted
      dataclasses with deterministic renderers bounded by max_chars.
Relations:
    Written by vidbyte.tools.builtins.cot.delegation and re-exported
    through vidbyte.context.primitives.
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
class DelegationBriefContextItem:
    """Records what was sent to a subagent, the success criteria, and passed assumptions.

    A brief carries far more than its literal task statement: it silently
    embeds assumptions in its phrasing that a receiver cannot see or
    question. This primitive makes that invisible cargo auditable by naming
    the assumptions passed along, what was deliberately withheld, how much
    supporting context traveled with the task, and the fallback if the
    delegated work fails outright, so that a later reader can trace a bad
    result back to the brief itself rather than only to the receiver.
    """

    task: str
    success_criteria: str
    assumptions_passed: tuple[str, ...] = ()
    withheld: str | None = None
    context_attached: str | None = None
    fallback_on_failure: str | None = None
    title: str = "Delegation Brief"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "delegation_brief"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the brief, its success criteria, and passed assumptions, bounded by max_chars.
        lines = [
            f"Task: {self.task}",
            f"Success Criteria: {self.success_criteria}",
        ]
        if self.context_attached:
            lines.append(f"Context Attached: {self.context_attached}")
        _extend_section(lines, "Assumptions Passed", self.assumptions_passed)
        if self.withheld:
            lines.append(f"Withheld: {self.withheld}")
        if self.fallback_on_failure:
            lines.append(f"Fallback On Failure: {self.fallback_on_failure}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class DelegationReceiptContextItem:
    """Records what came back from a subagent and how much it was trusted.

    Trust transferred across an agent boundary without verification is how
    errors compound silently in multi-agent systems, so this primitive makes
    that trust level an explicit, visible field rather than an implicit
    default. It records the result, how thoroughly it was checked, its
    standing against the originating brief's success criteria, and whether
    the receipt itself calls for a follow-up before the result is relied on
    further.
    """

    result_summary: str
    trust: str
    criteria_met: str
    discrepancies: str | None = None
    recheck_cost: str | None = None
    follow_up_needed: str | None = None
    title: str = "Delegation Receipt"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "delegation_receipt"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the result, trust level, and criteria verdict, bounded by max_chars.
        lines = [
            f"Trust: {self.trust}",
            f"Criteria Met: {self.criteria_met}",
            f"Result: {self.result_summary}",
        ]
        if self.discrepancies:
            lines.append(f"Discrepancies: {self.discrepancies}")
        if self.recheck_cost:
            lines.append(f"Recheck Cost: {self.recheck_cost}")
        if self.follow_up_needed:
            lines.append(f"Follow Up Needed: {self.follow_up_needed}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class HandoffWhyContextItem:
    """Records why a unit of work left this agent for another.

    A handoff is often a load-bearing decision wearing the costume of mere
    logistics: work can leave because context is polluted, because the
    receiver genuinely knows better, or simply because it was convenient, and
    those carry very different risk profiles. This primitive records the
    stated reason, the receiver's actual readiness to take the work on, the
    expected duration before a result is due back, and the condition under
    which the work would be reclaimed.
    """

    work: str
    reason: str
    rationale: str
    receiver_ready: str | None = None
    take_back_trigger: str | None = None
    expected_duration: str | None = None
    title: str = "Handoff Why"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "handoff_why"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the handoff reason and its take-back trigger, bounded by max_chars.
        lines = [
            f"Work: {self.work}",
            f"Reason: {self.reason}",
            f"Rationale: {self.rationale}",
        ]
        if self.receiver_ready:
            lines.append(f"Receiver Ready: {self.receiver_ready}")
        if self.expected_duration:
            lines.append(f"Expected Duration: {self.expected_duration}")
        if self.take_back_trigger:
            lines.append(f"Take Back Trigger: {self.take_back_trigger}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class HandoffCompletenessContextItem:
    """Records an audit of whether a handoff brief contained everything the receiver needs.

    The classic delegation failure is a structurally sound brief that omits
    exactly the one thing the receiver had no way to know on their own. This
    primitive records the audit's verdict on which category was missing, if
    any, whether the gap was fixed, who actually performed the audit, whether
    a follow-up correction was sent, and the risk carried forward if the gap
    is left unaddressed.
    """

    brief: str
    missing: str
    fix_applied: str | None = None
    risk_if_unfixed: str | None = None
    reviewed_by: str | None = None
    follow_up_sent: str | None = None
    title: str = "Handoff Completeness"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "handoff_completeness"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the completeness audit and risk if unfixed, bounded by max_chars.
        lines = [
            f"Missing: {self.missing}",
            f"Brief: {self.brief}",
        ]
        if self.reviewed_by:
            lines.append(f"Reviewed By: {self.reviewed_by}")
        if self.fix_applied:
            lines.append(f"Fix Applied: {self.fix_applied}")
        if self.follow_up_sent:
            lines.append(f"Follow Up Sent: {self.follow_up_sent}")
        if self.risk_if_unfixed:
            lines.append(f"Risk If Unfixed: {self.risk_if_unfixed}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class SubagentFailuresContextItem:
    """Records a subagent failure and whose failure it actually was.

    Honest attribution changes the fix that follows it: a brief failure
    means the instructions need rewriting, a capability failure means who or
    how work is delegated needs to change, a context failure means the
    receiver was missing something only the delegator could supply, and luck
    means a plain retry is appropriate. This primitive records the failure,
    its attributed owner, the evidence for that attribution, whether the
    situation is recoverable, whether the pattern has shown up before, and
    what will be done differently on retry.
    """

    failure: str
    owner: str
    analysis: str
    recoverable: str | None = None
    retry_differently: str | None = None
    pattern_seen_before: str | None = None
    title: str = "Subagent Failure"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "subagent_failures"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the failure, its attributed owner, and the analysis, bounded by max_chars.
        lines = [
            f"Owner: {self.owner}",
            f"Failure: {self.failure}",
            f"Analysis: {self.analysis}",
        ]
        if self.recoverable:
            lines.append(f"Recoverable: {self.recoverable}")
        if self.pattern_seen_before:
            lines.append(f"Pattern Seen Before: {self.pattern_seen_before}")
        if self.retry_differently:
            lines.append(f"Retry Differently: {self.retry_differently}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class BlockedOnContextItem:
    """Records a current blocking dependency and the chosen response.

    Blocking silently is one of the most expensive things a run can do,
    since every idle step is wasted and the waste stays invisible unless it
    is declared. This primitive is a ledger entry keyed by the blocker's
    statement so repeated updates converge on one record: it names what is
    being waited on, the response chosen, the condition that ends the block,
    the escalation path available if the block persists, and whether
    productive alternative work exists in the meantime.
    """

    blocked_on: str
    response: str
    unblock_condition: str
    blocking_since_step: int | None = None
    steps_wasted: int | None = None
    escalation_path: str | None = None
    alternative_work_available: str | None = None
    title: str = "Blocked On"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "blocked_on"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the blocker, the response, and the unblock condition, bounded by max_chars.
        lines = [
            f"Blocked On: {self.blocked_on}",
            f"Response: {self.response}",
            f"Unblock Condition: {self.unblock_condition}",
        ]
        if self.blocking_since_step is not None:
            lines.append(f"Blocking Since Step: {self.blocking_since_step}")
        if self.steps_wasted is not None:
            lines.append(f"Steps Wasted: {self.steps_wasted}")
        if self.alternative_work_available:
            lines.append(f"Alternative Work Available: {self.alternative_work_available}")
        if self.escalation_path:
            lines.append(f"Escalation Path: {self.escalation_path}")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "BlockedOnContextItem",
    "DelegationBriefContextItem",
    "DelegationReceiptContextItem",
    "HandoffCompletenessContextItem",
    "HandoffWhyContextItem",
    "SubagentFailuresContextItem",
]
