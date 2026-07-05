"""Context Protocol Header

Description:
    Bridges AgentLoopSettings and OutputContracts to reject conflicting configs.
Purpose:
    Guarantees at agent-construction time that a deterministic effort floor can
    never be configured below a loop-settings ceiling that would stop the run first.
Architecture:
    - ContractConfigurationError: Semantic error for contract/settings conflicts.
    - ContractSettingsValidator: Constructor-level, stateless conflict checker.
Relations:
    Invoked by vidbyte.agents.base during BaseAgent construction. Inspects
    vidbyte.agents.contracts.floors.EffortFloor and vidbyte.agents.settings.AgentLoopSettings.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.agents.contracts.base import OutputContract
from vidbyte.agents.contracts.floors import EffortFloor
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.errors import ConfigurationError


class ContractConfigurationError(ConfigurationError):
    """Raised when an output contract conflicts with the agent's loop settings."""


class ContractSettingsValidator:
    """Bridges AgentLoopSettings and OutputContracts to reject conflicting configurations."""

    _CEILING_FIELD = {
        "tokens": "max_tokens",
        "tool_calls": "max_tool_calls",
        "iterations": "max_iterations",
        "elapsed_seconds": "timeout_seconds",
    }

    def __init__(self, settings: AgentLoopSettings, contracts: Sequence[OutputContract]) -> None:
        # Captures the settings and contracts to reconcile; performs no checks yet.
        self._settings = settings
        self._contracts = tuple(contracts)

    def validate(self) -> None:
        # Raises ContractConfigurationError if any contract conflicts with the loop settings.
        self._validate_effort_floor_ceilings()

    def _validate_effort_floor_ceilings(self) -> None:
        # Ensures every effort floor sits strictly below its paired loop-settings ceiling.
        for floor in self._effort_floors():
            self._check_floor_against_ceiling(floor)

    def _effort_floors(self) -> tuple[EffortFloor, ...]:
        # Returns only the statically checkable EffortFloor contracts, skipping opaque ones.
        return tuple(c for c in self._contracts if isinstance(c, EffortFloor))

    def _check_floor_against_ceiling(self, floor: EffortFloor) -> None:
        # Raises when a floor minimum meets or exceeds its paired ceiling value.
        ceiling = self._ceiling_value(floor.dimension)
        if ceiling is not None and floor.minimum >= ceiling:
            raise ContractConfigurationError(self._conflict_message(floor, ceiling))

    def _ceiling_value(self, dimension: str) -> float | None:
        # Returns the loop-settings ceiling paired with a floor dimension, or None when unset.
        field_name = self._CEILING_FIELD.get(dimension)
        if field_name is None:
            return None
        return getattr(self._settings, field_name, None)

    def _conflict_message(self, floor: EffortFloor, ceiling: float) -> str:
        # Builds a semantic error message naming the floor, its minimum, and the ceiling.
        field_name = self._CEILING_FIELD[floor.dimension]
        return (
            f"{floor.contract_name} requires {floor.dimension} >= {floor.minimum}, but "
            f"AgentLoopSettings.{field_name}={ceiling} stops the run first. The floor is "
            f"unreachable — lower the floor or raise {field_name}."
        )


__all__ = ["ContractConfigurationError", "ContractSettingsValidator"]
