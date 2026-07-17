"""Context Protocol Header

FILE:
    vidbyte/agents/adversarial/__init__.py is the public surface of the
    adversarial-review package.
PURPOSE:
    Re-exports the runnerless AdversarialAgent connector and its data contracts so
    existing `from vidbyte.agents.adversarial import ...` imports keep working after
    the single module was split into a package.
ARCHITECTURE:
    - agent.py     -> AdversarialAgent: thin BaseAgent connector.
    - context.py   -> AdversarialContext: owns the context-window mechanics.
    - runtime.py   -> _AdversarialRunController: the deterministic run loop.
    - The data contracts (AdversarialSettings + review/round/result records) live
      in vidbyte/lib/dataclasses/adversarial.py and are surfaced here for callers.
RELATIONS:
    Consumed by vidbyte.agents, vidbyte (root exports), and AgentClient.adversarial().
"""

from __future__ import annotations

from vidbyte.agents.adversarial.agent import AdversarialAgent
from vidbyte.lib.dataclasses.adversarial import AdversarialResult, AdversarialReview, AdversarialRoundResult, AdversarialSettings

__all__ = [
    "AdversarialAgent",
    "AdversarialResult",
    "AdversarialReview",
    "AdversarialRoundResult",
    "AdversarialSettings",
]
