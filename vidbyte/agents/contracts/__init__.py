"""Context Protocol Header

Description:
    Defines the OutputContract base and exposes the prebuilt deterministic effort floors.
Purpose:
    Output contracts gate when an agent is *allowed* to stop. A contract declares which
    runtime counter it reads (key), the paired loop-settings ceiling (ceiling_key), and a
    human unit, and the base supplies the satisfied/error logic.
Architecture:
    - OutputContract: Declarative base with satisfied()/error() over a counters mapping.
    - floors.py: MinToolCalls / MinTokens / MinIterations / MinElapsedSeconds.
Relations:
    Owned at runtime by vidbyte.agents.contract.AgentOutputContract; passed to Agent via
    the output_contracts= parameter.
Similar Files:
    - vidbyte/agents/settings/loop.py: AgentLoopSettings defines the ceilings these floors pair with.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.errors import ConfigurationError


class OutputContract:
    """Declarative base for a condition that must hold before an agent may stop."""

    key: str = ""                    # counters[key]: the runtime counter this contract reads
    ceiling_key: str | None = None   # paired AgentLoopSettings field, or None when unbounded
    unit: str = ""                   # human unit used in the corrective message ("tool calls")
    category: str = "deterministic"

    def __init__(self, minimum: int | float) -> None:
        # Stores the required minimum, rejecting non-positive values at construction.
        if minimum <= 0:
            raise ConfigurationError(f"{self.name}: minimum must be greater than zero, got {minimum}.")
        self.minimum = minimum

    @property
    def name(self) -> str:
        # Stable display name used in corrective feedback and result metadata.
        return type(self).__name__

    def satisfied(self, counters: Mapping[str, Any]) -> bool:
        # Returns whether the observed counter has reached this contract's minimum.
        return (counters.get(self.key) or 0) >= self.minimum

    def error(self, counters: Mapping[str, Any]) -> str:
        # Builds the corrective feedback shown to the model when this contract is unmet.
        observed = counters.get(self.key) or 0
        return f"Only {observed} {self.unit} so far; at least {self.minimum} are required before finishing. Keep working."


from vidbyte.agents.contracts.floors import MinElapsedSeconds, MinIterations, MinTokens, MinToolCalls

__all__ = [
    "OutputContract",
    "MinToolCalls",
    "MinTokens",
    "MinIterations",
    "MinElapsedSeconds",
]
