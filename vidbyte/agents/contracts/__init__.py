"""Context Protocol Header

Description:
    Public exports for the vidbyte.agents.contracts sub-package.
Purpose:
    Exposes the OutputContract abstraction, deterministic effort floors, the
    constructor-level validator, and the runtime gate.
Architecture:
    - Base primitives: OutputContract, ContractVerdict, TerminationContext.
    - Effort floors: MinTokens, MinToolCalls, MinIterations, MinElapsedSeconds.
    - Validation: ContractSettingsValidator, ContractConfigurationError.
    - Enforcement: OutputContractGate, ContractReport.
Relations:
    Re-exported from vidbyte.agents. Consumed by vidbyte.agents.base and runtime.
"""

from vidbyte.agents.contracts.base import ContractVerdict, OutputContract, TerminationContext
from vidbyte.agents.contracts.floors import (
    EffortFloor,
    MinElapsedSeconds,
    MinIterations,
    MinTokens,
    MinToolCalls,
)
from vidbyte.agents.contracts.gate import ContractReport, OutputContractGate
from vidbyte.agents.contracts.validation import ContractConfigurationError, ContractSettingsValidator

__all__ = [
    "ContractConfigurationError",
    "ContractReport",
    "ContractSettingsValidator",
    "ContractVerdict",
    "EffortFloor",
    "MinElapsedSeconds",
    "MinIterations",
    "MinTokens",
    "MinToolCalls",
    "OutputContract",
    "OutputContractGate",
    "TerminationContext",
]
