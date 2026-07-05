"""Context Protocol Header

Description:
    Evaluates output contracts at agent termination boundaries.
Purpose:
    Decides whether an attempted stop is permitted, and builds the corrective
    feedback injected into context when contracts are unmet.
Architecture:
    - ContractReport: Per-contract evaluation record for feedback and metadata.
    - OutputContractGate: Runs contracts, filters unmet ones, tracks the rejection budget.
Relations:
    Constructed and consulted by vidbyte.agents.runtime.AgentRuntime at the
    IS_DONE and no-tool-calls finalization boundaries.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.contracts.base import OutputContract, TerminationContext


@dataclass(frozen=True, slots=True)
class ContractReport:
    """Per-contract evaluation record used for injected feedback and result metadata."""

    name: str
    satisfied: bool
    feedback: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


class OutputContractGate:
    """Evaluates output contracts at termination boundaries and drives reject-and-continue."""

    def __init__(self, contracts: Sequence[OutputContract], *, max_rejections: int) -> None:
        # Stores the contracts and the rejection budget that bounds reject-and-continue.
        self._contracts = tuple(contracts)
        self._max_rejections = max_rejections

    def active(self) -> bool:
        # Returns whether any contract is configured for this run.
        return bool(self._contracts)

    async def evaluate(self, ctx: TerminationContext) -> tuple[ContractReport, ...]:
        # Evaluates every contract against the snapshot and returns per-contract reports.
        return tuple([await self._evaluate_one(contract, ctx) for contract in self._contracts])

    async def _evaluate_one(self, contract: OutputContract, ctx: TerminationContext) -> ContractReport:
        # Evaluates one contract, treating any raised exception as a fail-closed rejection.
        try:
            verdict = await contract.evaluate(ctx)
        except Exception as exc:
            return ContractReport(contract.contract_name, False, feedback=str(exc), metadata={"error": type(exc).__name__})
        return ContractReport(contract.contract_name, verdict.satisfied, feedback=verdict.feedback, metadata=dict(verdict.metadata))

    def unmet(self, reports: Sequence[ContractReport]) -> tuple[ContractReport, ...]:
        # Filters reports down to the contracts that were not satisfied.
        return tuple(report for report in reports if not report.satisfied)

    def exhausted(self, rejection_count: int) -> bool:
        # Returns whether the rejection budget has been spent.
        return rejection_count >= self._max_rejections

    def rejection_message(self, unmet: Sequence[ContractReport]) -> str:
        # Builds the aggregated feedback block injected when contracts are unmet.
        lines = "\n".join(f"- {report.name}: {report.feedback}" for report in unmet)
        return f"Completion blocked — {len(unmet)} output contract(s) unmet:\n{lines}"

    @staticmethod
    def summarize(reports: Sequence[ContractReport], *, rejection_count: int) -> tuple[dict[str, Any], ...]:
        # Builds observable metadata records for AgentResult.metadata["contract_evaluations"].
        return tuple(
            {
                "name": report.name,
                "satisfied": report.satisfied,
                "feedback": report.feedback,
                "rejection_count": rejection_count,
                **dict(report.metadata),
            }
            for report in reports
        )


__all__ = ["ContractReport", "OutputContractGate"]
