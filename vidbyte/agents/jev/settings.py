"""FILE: vidbyte/agents/jev/settings.py

PURPOSE: Validates the agent-profile catalog separately from Jev's runtime-wide decision and preflight controls.
ROLE IN CODEBASE: `Jev` consumes `JevAgentSettings` to choose a configured profile and `JevRuntimeSettings` to build the gate and tool selector; profile record validation lives in `vidbyte/lib/dataclasses/jev.py`.
ARCHITECTURE NOTE: The profile catalog is the only content in JevAgentSettings; named runtime controls stay in a separate typed object so developer-defined agent configuration is not mixed with Jev policy.
FUNCTION INVENTORY: `JevAgentSettings.__post_init__` freezes and validates candidate profiles; `JevRuntimeSettings.__post_init__` validates decision, preflight, and tool-selector configuration. Both raise `ConfigurationError` for invalid public input.
COMMON MODIFICATION PATTERNS: Add profile identity or catalog bounds to the `JevAgent`/`JevAgentCatalog` records; add a global policy control to `JevRuntimeSettings` and pass it to its owning capability.
WHAT NOT TO DO IN THIS FILE: 1. Do not put agent execution policy in `JevRuntime`; `Jev` and its capability classes own it. 2. Do not add provider request JSON; `vidbyte/providers/typesafe.py` owns wire serialization.
KNOWN EDGE CASES: Empty profiles are rejected because a coordinator needs a profile to initialize from; the TypeSafe decision key is resolved only when a run actually requests a decision.
RELATED DOCS: `docs/design/jev-agent-profile-routing.md`, `skills/jev-agent/SKILL.md`, and `skills/asking-jev-questions/SKILL.md`.
TESTS: `tests/test_jev_agent.py`, `tests/test_jev_preflight.py`, and `tests/test_jev_tool_selector.py`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from vidbyte.lib.constants.jev import (
    JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD,
    JEV_TOOL_SELECTOR_MAX_THRESHOLD,
    JEV_TOOL_SELECTOR_MIN_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import JevAgent, JevAgentCatalog
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums.jev import JevPreflightPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev import JevPreflightRegistry


@dataclass(frozen=True, slots=True)
class JevAgentSettings:
    """Validated catalog of candidate agents available to one Jev coordinator."""

    agents: Sequence[JevAgent]

    def __post_init__(self) -> None:
        # Freezes sequence input once so profile order remains the deterministic tie-break.
        if isinstance(self.agents, (str, bytes)) or not isinstance(self.agents, Sequence):
            raise ConfigurationError("JevAgentSettings.agents must be a sequence of JevAgent profiles.")
        catalog = JevAgentCatalog(agents=tuple(self.agents))
        object.__setattr__(self, "agents", catalog.agents)


@dataclass(frozen=True, slots=True)
class JevRuntimeSettings:
    """Validated runtime-wide decision and preflight policy, separate from agent profiles."""

    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig, repr=False)
    preflight: Sequence[JevPreflightPreset | str] = ()
    tool_selector_threshold: float = JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD

    def __post_init__(self) -> None:
        # Normalizes the existing preflight surface and validates the tool selector probability.
        if not isinstance(self.decision, DecisionModelConfig):
            raise ConfigurationError("JevRuntimeSettings.decision must be a DecisionModelConfig instance.")
        object.__setattr__(self, "preflight", JevPreflightRegistry.validate(self.preflight))
        self._validate_tool_selector_threshold()

    def _validate_tool_selector_threshold(self) -> None:
        # Keeps existing tool selection semantics on a finite, inclusive probability range.
        value = self.tool_selector_threshold
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not JEV_TOOL_SELECTOR_MIN_THRESHOLD <= value <= JEV_TOOL_SELECTOR_MAX_THRESHOLD:
            raise ConfigurationError("JevRuntimeSettings.tool_selector_threshold must be a finite probability between 0 and 1 inclusive.")
        object.__setattr__(self, "tool_selector_threshold", float(value))


__all__ = ["JevAgentSettings", "JevRuntimeSettings"]
