"""Context Protocol Header

Description:
    Defines VerifierRuntimeSettings.
Purpose:
    The single value a developer attaches to AgentLoopSettings — composes
    every pillar into one object. Pure configuration; no behavior.
Architecture note:
    - VerifierRuntimeSettings: thin wrapper exposing active().
    VerifierRuntimeSettingsParams (validated dataclass: one field per pillar;
    no __post_init__ of its own since every field's own class already
    validated itself at construction) lives in
    vidbyte.lib.dataclasses.verifier, not here, per review feedback on
    PR #349.
Relations:
    Attached to vidbyte.agents.settings.loop.AgentLoopSettings.verifier_runtime.
    Consumed by vidbyte.agents.runtimes.verifier.runtime.AgentVerifierRuntime.
Similar Files:
    - vidbyte/agents/contract.py: AgentLoopSettingsOutputContract, the
      nearest existing "settings-facing owner with an active() check" shape.
Role in codebase:
    Attaches validated verifier configuration to AgentLoopSettings.
Common modification patterns:
    Add configuration fields to the lib dataclass params and keep this wrapper
    behavior-free.
Known edge cases:
    Omitting mode selects FinalizationGateMode for backward compatibility.
Related docs:
    docs/design/verifier-runtime.md; docs/design/verifier-runtime-algorithms.md
Tests:
    Covered by settings construction and package tests.
"""

from __future__ import annotations

from vidbyte.agents.runtimes.verifier.algorithms.finalization_gate import FinalizationGateMode
from vidbyte.lib.dataclasses.verifier import VerifierRuntimeSettingsParams


class VerifierRuntimeSettings:
    """The value a developer attaches to AgentLoopSettings.verifier_runtime."""

    def __init__(self, params: VerifierRuntimeSettingsParams) -> None:
        # Stores the composed, already-validated pillar configuration.
        self.params = params
        self.mode = params.mode or FinalizationGateMode()

    def active(self) -> bool:
        """Returns whether at least one verifier is configured to run."""
        return bool(self.params.collection.params.verifiers)


__all__ = ["VerifierRuntimeSettings", "VerifierRuntimeSettingsParams"]
