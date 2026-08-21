"""Context Protocol Header

Description:
    Defines VerifierRuntimeSettingsParams and VerifierRuntimeSettings.
Purpose:
    The single value a developer attaches to AgentLoopSettings — composes
    every pillar into one object. Pure configuration; no behavior.
Architecture:
    - VerifierRuntimeSettingsParams: one field per pillar. No __post_init__
      of its own — every field's own class already validated itself at
      construction, so there is nothing left to check at composition time.
    - VerifierRuntimeSettings: thin wrapper exposing active().
Relations:
    Attached to vidbyte.agents.settings.loop.AgentLoopSettings.verifier_runtime.
    Consumed by vidbyte.agents.runtimes.verifier.runtime.AgentVerifierRuntime.
Similar Files:
    - vidbyte/agents/contract.py: AgentLoopSettingsOutputContract, the
      nearest existing "settings-facing owner with an active() check" shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.agents.runtimes.verifier.budget import VerifierRuntimeBudget
from vidbyte.agents.runtimes.verifier.collection import VerifierCollection
from vidbyte.agents.runtimes.verifier.feedback import VerifierRuntimeFeedback
from vidbyte.agents.runtimes.verifier.gate import VerifierRuntimeGate
from vidbyte.agents.runtimes.verifier.ledger import VerifierLedgerParams
from vidbyte.agents.runtimes.verifier.repair import VerifierRepairStrategy
from vidbyte.agents.runtimes.verifier.target import VerifierTargetResolver
from vidbyte.agents.runtimes.verifier.verdict import VerifierVerdictPolicy


@dataclass(frozen=True, slots=True)
class VerifierRuntimeSettingsParams:
    """Composes every verifier-runtime pillar into one configuration object."""

    target_resolver: VerifierTargetResolver
    collection: VerifierCollection
    gate: VerifierRuntimeGate
    verdict_policy: VerifierVerdictPolicy
    feedback: VerifierRuntimeFeedback
    repair_strategy: VerifierRepairStrategy
    budget: VerifierRuntimeBudget
    ledger_params: VerifierLedgerParams


class VerifierRuntimeSettings:
    """The value a developer attaches to AgentLoopSettings.verifier_runtime."""

    def __init__(self, params: VerifierRuntimeSettingsParams) -> None:
        # Stores the composed, already-validated pillar configuration.
        self.params = params

    def active(self) -> bool:
        """Returns whether at least one verifier is configured to run."""
        return bool(self.params.collection.params.verifiers)


__all__ = ["VerifierRuntimeSettings", "VerifierRuntimeSettingsParams"]
