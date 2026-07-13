"""Context Protocol Header

PURPOSE:
    Defines AgentLoopSettingsOutputContract, the runtime-facing owner of an
    agent's output contracts. It holds the configured contracts and the
    reject-and-continue budget and exposes the one-line methods the linear runtime
    calls at each termination boundary. Immutable and stateless across runs — the
    rejection counter lives in the runtime loop, and floor-vs-ceiling validation is
    performed by AgentLoopSettings (which owns the ceilings), not here.
ROLE IN CODEBASE:
    Constructed by vidbyte.agents.settings.loop.AgentLoopSettings and threaded
    into the linear AgentRuntime, which consults it at the IS_DONE and
    no-tool-calls finalization boundaries. Built from the OutputContract base in
    vidbyte/agents/contracts/__init__.py.
ARCHITECTURE:
    - AgentLoopSettingsOutputContract: active/unmet/exhausted/feedback/report
      queries over a runtime-owned counters mapping.
FUNCTION INVENTORY:
    - active(): whether any contract is configured.
    - unmet(...)/exhausted(...): termination-boundary checks against the budget.
    - feedback(...)/report(...): model-visible feedback and terminal report.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.contracts import OutputContract


class AgentLoopSettingsOutputContract:
    """Owns an agent's output contracts and evaluates them at the runtime's termination boundaries."""

    def __init__(self, contracts: Sequence[OutputContract], *, max_rejections: int = 3) -> None:
        # Captures the configured contracts and the reject-and-continue budget.
        self._contracts = tuple(contracts)
        self._max_rejections = max_rejections

    def active(self) -> bool:
        # Returns whether any contract is configured for this agent.
        return bool(self._contracts)

    def unmet(self, counters: Mapping[str, Any]) -> list[OutputContract]:
        # Returns the contracts not yet satisfied by the current counters snapshot.
        return [contract for contract in self._contracts if not contract.satisfied(counters)]

    def exhausted(self, rejections: int) -> bool:
        # Returns whether the reject-and-continue budget has been spent.
        return rejections >= self._max_rejections

    def feedback(self, unmet: Sequence[OutputContract], counters: Mapping[str, Any]) -> str:
        # Builds the aggregated corrective message injected when contracts are unmet.
        lines = "\n".join(f"- {contract.error(counters)}" for contract in unmet)
        return f"You cannot finish yet:\n{lines}"

    def report(self, counters: Mapping[str, Any]) -> list[dict[str, Any]]:
        # Builds the per-contract records surfaced in AgentResult.metadata["contract_evaluations"].
        return [
            {"name": contract.name, "satisfied": contract.satisfied(counters), "minimum": contract.minimum}
            for contract in self._contracts
        ]
