"""Context Protocol Header

Description:
    Defines AgentOutputContract, the per-agent owner of output contracts.
Purpose:
    Validates floor-vs-ceiling conflicts once at agent construction (fail fast) and exposes
    the one-line methods the linear runtime calls at each termination boundary. Immutable and
    stateless across runs — the reject-and-continue counter lives in the runtime loop.
Architecture:
    - AgentOutputContract: validate() in __init__; active/unmet/exhausted/feedback/report at runtime.
Relations:
    Constructed by vidbyte.agents.base.BaseAgent and threaded into the linear AgentRuntime,
    which consults it at the IS_DONE and no-tool-calls finalization boundaries.
Similar Files:
    - vidbyte/agents/runtime.py: AgentRuntime, the peer loop-owner that consults this class.
    - vidbyte/agents/contracts/__init__.py: OutputContract base these are built from.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.contracts import OutputContract
from vidbyte.agents.settings.loop import AgentLoopSettings
from vidbyte.lib.errors import ConfigurationError


class AgentOutputContract:
    """Owns an agent's output contracts: validates config at construction, evaluates at termination boundaries."""

    _CEILING_LABEL = "AgentLoopSettings"

    def __init__(self, contracts: Sequence[OutputContract], loop_settings: AgentLoopSettings, *, max_rejections: int = 3) -> None:
        # Captures contracts + settings and validates every floor-vs-ceiling conflict immediately.
        self._contracts = tuple(contracts)
        self._loop_settings = loop_settings
        self._max_rejections = max_rejections
        self._validate()

    def _validate(self) -> None:
        # Raises ConfigurationError when any floor's minimum meets or exceeds its paired ceiling.
        for contract in self._contracts:
            self._validate_ceiling(contract)

    def _validate_ceiling(self, contract: OutputContract) -> None:
        # Enforces the strict floor < ceiling invariant for one contract that declares a ceiling_key.
        if not contract.ceiling_key:
            return
        ceiling = getattr(self._loop_settings, contract.ceiling_key, None)
        if ceiling is not None and contract.minimum >= ceiling:
            raise ConfigurationError(
                f"{contract.name}(minimum={contract.minimum}) conflicts with "
                f"{self._CEILING_LABEL}.{contract.ceiling_key}={ceiling}: the floor is unreachable "
                "(require minimum < ceiling)."
            )

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
