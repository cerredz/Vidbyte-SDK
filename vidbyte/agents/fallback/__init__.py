"""Context Protocol Header

Description:
    Public exports for the vidbyte.agents.fallback sub-package.
Purpose:
    Exposes the fallback chain, its developer-facing settings object, and the
    per-hop policy classes from one package, replacing the former single-file
    vidbyte/agents/fallback.py and vidbyte/agents/settings/fallback.py.
Architecture:
    - chain.py: AgentFallback, the ordered model chain and its transforms.
    - settings.py: AgentFallbackSettings, the validated developer-facing config.
    - policies.py: LatencyPolicy and CostBudgetPolicy, the per-hop trigger conditions.
Relations:
    Re-exported from vidbyte.agents.__init__ and vidbyte.agents.settings.__init__.
"""

from vidbyte.agents.fallback.chain import AgentFallback, DEFAULT_FALLBACK_ERRORS
from vidbyte.agents.fallback.policies import CostBudgetPolicy, LatencyPolicy
from vidbyte.agents.fallback.settings import AgentFallbackSettings
from vidbyte.lib.dataclasses.agents import FallbackTransform

__all__ = [
    "AgentFallback",
    "AgentFallbackSettings",
    "CostBudgetPolicy",
    "DEFAULT_FALLBACK_ERRORS",
    "FallbackTransform",
    "LatencyPolicy",
]
