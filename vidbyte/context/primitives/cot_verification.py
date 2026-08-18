"""Context Protocol Header

Description:
    Defines the self-verification monitoring primitives.
Purpose:
    Gives the cot_verification tools typed, bounded context units tracking
    active checks on the agent's own claims and outputs: single-claim
    verification, pre-completion self tests, independent re-derivations, and
    re-reads of earlier records.
Architecture:
    - VerifyContextItem, SelfTestContextItem, IndependentlyDerivedContextItem,
      ReadBackContextItem: frozen, slotted dataclasses with deterministic
      renderers bounded by max_chars.
Relations:
    Written by vidbyte.tools.builtins.cot_verification and re-exported
    through vidbyte.context.primitives.
Similar Files:
    - `vidbyte/context/primitives/cot_events.py`
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _truncate_text

_DEFAULT_MAX_CHARS = 2000


@dataclass(frozen=True, slots=True)
class VerifyContextItem:
    """Records one actively executed check on a single claim."""

    claim: str
    method: str
    verdict: str
    evidence: str
    severity_if_wrong: str | None = None
    fixed: str | None = None
    title: str = "Verification"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "verify"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the claim, method, verdict, and evidence, bounded by max_chars.
        lines = [
            f"Method: {self.method}",
            f"Verdict: {self.verdict}",
            f"Claim: {self.claim}",
            f"Evidence: {self.evidence}",
        ]
        if self.severity_if_wrong:
            lines.append(f"Severity If Wrong: {self.severity_if_wrong}")
        if self.fixed:
            lines.append(f"Fixed: {self.fixed}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class SelfTestContextItem:
    """Records the test that would fail if the agent is wrong, and whether it ran."""

    test: str
    ran: str
    result: str | None = None
    if_skipped_why: str | None = None
    coverage: str | None = None
    title: str = "Self Test"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "self_test"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the test, whether it ran, and its outcome, bounded by max_chars.
        lines = [
            f"Test: {self.test}",
            f"Ran: {self.ran}",
        ]
        if self.result:
            lines.append(f"Result: {self.result}")
        if self.coverage:
            lines.append(f"Coverage: {self.coverage}")
        if self.if_skipped_why:
            lines.append(f"If Skipped Why: {self.if_skipped_why}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class IndependentlyDerivedContextItem:
    """Records reaching one conclusion through two independent paths."""

    conclusion: str
    path_a: str
    path_b: str
    agree: str
    if_disagree: str | None = None
    title: str = "Independently Derived"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "independently_derived"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders both derivation paths and their agreement, bounded by max_chars.
        lines = [
            f"Agree: {self.agree}",
            f"Conclusion: {self.conclusion}",
            "### Path A",
            self.path_a,
            "",
            "### Path B",
            self.path_b,
        ]
        if self.if_disagree:
            lines.extend(("", f"If Disagree: {self.if_disagree}"))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class ReadBackContextItem:
    """Records re-reading an earlier output and whether it matches memory."""

    record: str
    matches_memory: str
    drift_detail: str | None = None
    corrective_action: str | None = None
    title: str = "Read Back"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "read_back"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the re-read record and any drift found, bounded by max_chars.
        lines = [
            f"Record: {self.record}",
            f"Matches Memory: {self.matches_memory}",
        ]
        if self.drift_detail:
            lines.append(f"Drift Detail: {self.drift_detail}")
        if self.corrective_action:
            lines.append(f"Corrective Action: {self.corrective_action}")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "IndependentlyDerivedContextItem",
    "ReadBackContextItem",
    "SelfTestContextItem",
    "VerifyContextItem",
]
