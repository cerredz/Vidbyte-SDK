"""Context Protocol Header

Description:
    Defines the public OutputContract abstraction and its immutable payloads.
Purpose:
    Lets developers gate when an agent is allowed to stop by supplying contracts
    the runtime evaluates at each termination boundary.
Architecture:
    - TerminationContext: Read-only snapshot of runtime counters at a boundary.
    - ContractVerdict: Outcome of evaluating one contract.
    - OutputContract: Async-evaluated base class for a single stop condition.
Relations:
    Implemented by vidbyte.agents.contracts.floors. Consumed by
    vidbyte.agents.contracts.gate and vidbyte.agents.contracts.validation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TerminationContext:
    """Read-only snapshot of runtime counters at a termination boundary."""

    output: str
    iteration_count: int
    model_call_count: int
    tool_call_count: int
    tokens_used: int | None
    elapsed_seconds: float
    rejection_count: int
    run_state: Mapping[Any, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContractVerdict:
    """Outcome of evaluating one contract against a TerminationContext."""

    satisfied: bool
    feedback: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


class OutputContract(ABC):
    """Base class for a condition that must hold before an agent may stop."""

    name: str = ""

    @property
    def contract_name(self) -> str:
        # Returns a stable display name used in metadata and feedback messages.
        return self.name or self.__class__.__name__

    @abstractmethod
    async def evaluate(self, ctx: TerminationContext) -> ContractVerdict:
        # Returns a verdict describing whether this contract permits stopping.
        ...


__all__ = ["ContractVerdict", "OutputContract", "TerminationContext"]
