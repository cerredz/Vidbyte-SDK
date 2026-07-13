"""FILE: vidbyte/workflows/approval.py
PURPOSE: Defines deterministic transition confirmation gates and run-level risk policies.
ROLE IN CODEBASE: graph.py stores gates; machine.py evaluates them after guards pass.

ARCHITECTURE NOTE:
    Required edge approval and optional risk confirmation are separate decisions.
    Policies only answer whether to suspend; they cannot choose graph destinations.

PUBLIC API INVENTORY:
    RiskLevel: Ordered transition/action risk classification.
    ApprovalGate: Edge-owned required confirmation and rejection outcome.
    ApprovalContext: Bounded facts visible to a confirmation policy.
    ConfirmationPolicy / NeverConfirm / AlwaysConfirm / ConfirmRisky: Run policy surface.

COMMON MODIFICATION PATTERNS:
    Add a policy as a pure requires_confirmation implementation; persistence and
    resume remain owned by machine.py and contracts.py.

WHAT NOT TO DO IN THIS FILE:
    1. Do not block waiting for human input.
    2. Do not execute callbacks during policy evaluation.
    3. Do not allow optional policy to bypass a required gate.

KNOWN EDGE CASES:
    NeverConfirm applies only to optional risk checks. A required ApprovalGate always
    suspends after guards pass, even when the run uses NeverConfirm.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke covers all three policies.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


class RiskLevel(IntEnum):
    """Ordered risk attached to a declared transition or action."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True, slots=True)
class ApprovalGate:
    """Transition-owned approval requirement and deterministic rejection outcome."""

    required: bool = False
    reason: str = ""
    rejection_outcome: str = "approval_denied"

    def __post_init__(self) -> None:
        # Normalizes human-facing reason and the semantic rejection route outcome.
        if not isinstance(self.required, bool):
            raise TypeError("ApprovalGate.required must be a boolean.")
        if not isinstance(self.reason, str):
            raise TypeError("ApprovalGate.reason must be a string.")
        object.__setattr__(self, "reason", self.reason.strip())
        outcome = str(self.rejection_outcome).strip()
        if not outcome:
            raise ValueError("ApprovalGate.rejection_outcome cannot be empty.")
        object.__setattr__(self, "rejection_outcome", outcome)


@dataclass(frozen=True, slots=True)
class ApprovalContext:
    """Bounded transition facts supplied to an optional confirmation policy."""

    run_id: str
    stage: str
    target: str
    outcome: str
    risk: RiskLevel
    gate: ApprovalGate | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Protects policy inputs from mutation and normalizes risk classification.
        risk = self.risk if isinstance(self.risk, RiskLevel) else RiskLevel(self.risk)
        object.__setattr__(self, "risk", risk)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@runtime_checkable
class ConfirmationPolicy(Protocol):
    """Pure run-level policy deciding whether an otherwise-valid edge suspends."""

    def requires_confirmation(self, context: ApprovalContext) -> bool:
        # Returns True only to suspend; the compiled edge still owns the target.
        ...


class NeverConfirm:
    """Automatically continues optional risk checks while preserving required gates."""

    def requires_confirmation(self, context: ApprovalContext) -> bool:
        # Declines optional confirmation for every risk classification.
        return False


class AlwaysConfirm:
    """Suspends before every otherwise-valid confirmation-capable transition."""

    def requires_confirmation(self, context: ApprovalContext) -> bool:
        # Requires confirmation independently of risk while preserving declared rejection.
        return context.gate is not None


@dataclass(frozen=True, slots=True)
class ConfirmRisky:
    """Suspends optional confirmation at or above a configured risk threshold."""

    minimum_risk: RiskLevel = RiskLevel.HIGH

    def __post_init__(self) -> None:
        # Normalizes the ordered threshold once for deterministic comparisons.
        level = self.minimum_risk if isinstance(self.minimum_risk, RiskLevel) else RiskLevel(self.minimum_risk)
        object.__setattr__(self, "minimum_risk", level)

    def requires_confirmation(self, context: ApprovalContext) -> bool:
        # Compares declared edge risk without inspecting mutable workflow state.
        return context.gate is not None and context.risk >= self.minimum_risk


__all__ = [
    "AlwaysConfirm",
    "ApprovalContext",
    "ApprovalGate",
    "ConfirmationPolicy",
    "ConfirmRisky",
    "NeverConfirm",
    "RiskLevel",
]
