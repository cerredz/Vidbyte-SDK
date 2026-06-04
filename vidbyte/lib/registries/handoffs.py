"""Context Protocol Header

Description:
    Handoff registry for discovering, constructing, and describing every prebuilt
    handoff structure the SDK offers.
Purpose:
    Gives developers one place to list all prebuilt handoffs, inspect their section
    structures, construct them by name, register custom ones, and build a HandoffAgent
    from a named handoff.
Architecture:
    - HandoffRegistry: Instance-based catalog prefilled with all prebuilt Handoff classes.
Key Functions:
    - get / create: Resolve and construct a handoff by slug.
    - list / all / describe: Discovery helpers over the catalog.
    - register: Add or override a custom handoff.
    - build_agent: Construct a HandoffAgent configured with a named handoff.
Relations:
    Located in vidbyte/lib/registries/handoffs.py. References prebuilt classes from
    vidbyte.context.handoffs and lazily builds vidbyte.agents.handoff.HandoffAgent.
Similar Files:
    - vidbyte/lib/registries/actors.py: Prebuilt actor class registry.
    - vidbyte/lib/registries/agents.py: Agent discovery registry.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from vidbyte.context.handoffs import (
    APIDesignHandoff,
    ArchitectureDecisionHandoff,
    BacktrackingHandoff,
    BudgetBoundedHandoff,
    BugFixHandoff,
    CICDPipelineHandoff,
    CodeReviewHandoff,
    CodebaseOnboardingHandoff,
    ConstraintSatisfactionHandoff,
    CoverageHandoff,
    DecompositionHandoff,
    DependencyUpgradeHandoff,
    EngineeringHandoff,
    GoalStackHandoff,
    Handoff,
    IncidentResponseHandoff,
    IntegrationHandoff,
    MigrationHandoff,
    MinimalHandoff,
    PerformanceOptimizationHandoff,
    RefactorHandoff,
    RefinementLoopHandoff,
    ReleaseHandoff,
    ResearchHandoff,
    SchemaMigrationHandoff,
    SecurityRemediationHandoff,
    TestAuthoringHandoff,
    TradeoffHandoff,
    TreeSearchHandoff,
)
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.handoff import HandoffAgent


_DEFAULT_HANDOFFS: dict[str, type[Handoff]] = {
    # General prebuilts.
    "engineering": EngineeringHandoff,
    "research": ResearchHandoff,
    "minimal": MinimalHandoff,
    # Process-shape prebuilts.
    "tree_search": TreeSearchHandoff,
    "decomposition": DecompositionHandoff,
    "refinement_loop": RefinementLoopHandoff,
    "constraint_satisfaction": ConstraintSatisfactionHandoff,
    "backtracking": BacktrackingHandoff,
    "tradeoff": TradeoffHandoff,
    "goal_stack": GoalStackHandoff,
    "coverage": CoverageHandoff,
    "budget_bounded": BudgetBoundedHandoff,
    "migration": MigrationHandoff,
    # Software-engineering prebuilts.
    "code_review": CodeReviewHandoff,
    "bug_fix": BugFixHandoff,
    "refactor": RefactorHandoff,
    "performance_optimization": PerformanceOptimizationHandoff,
    "test_authoring": TestAuthoringHandoff,
    "api_design": APIDesignHandoff,
    "schema_migration": SchemaMigrationHandoff,
    "dependency_upgrade": DependencyUpgradeHandoff,
    "incident_response": IncidentResponseHandoff,
    "architecture_decision": ArchitectureDecisionHandoff,
    "codebase_onboarding": CodebaseOnboardingHandoff,
    "cicd_pipeline": CICDPipelineHandoff,
    "integration": IntegrationHandoff,
    "security_remediation": SecurityRemediationHandoff,
    "release": ReleaseHandoff,
}


class HandoffRegistry:
    """Discoverable catalog of every prebuilt handoff structure the SDK offers."""

    def __init__(self) -> None:
        # Prefill this registry instance with all SDK-provided prebuilt handoffs.
        self._handoffs: dict[str, type[Handoff]] = dict(_DEFAULT_HANDOFFS)

    def register(self, name: str, handoff_cls: type[Handoff]) -> None:
        # Add or override a handoff under a normalized slug.
        self._handoffs[self._normalize(name)] = handoff_cls

    def get(self, name: str) -> type[Handoff]:
        # Return the handoff class for a slug, raising ConfigurationError if unknown.
        key = self._normalize(name)
        if key not in self._handoffs:
            raise ConfigurationError(f"Handoff '{name}' is not registered. Available: {self.list()}")
        return self._handoffs[key]

    def create(self, name: str, **kwargs: Any) -> Handoff:
        # Construct a handoff instance by slug, forwarding kwargs to its constructor.
        return self.get(name)(**kwargs)

    def list(self) -> list[str]:
        # Return a sorted list of all registered handoff slugs.
        return sorted(self._handoffs.keys())

    def all(self) -> dict[str, type[Handoff]]:
        # Return a copy of the slug-to-class catalog.
        return dict(self._handoffs)

    def describe(self) -> dict[str, dict[str, Any]]:
        # Return each handoff's class name, title, and full section map for browsing.
        return {name: self._describe_one(handoff_cls) for name, handoff_cls in self._handoffs.items()}

    def build_agent(self, name: str, **agent_kwargs: Any) -> "HandoffAgent":
        # Build a HandoffAgent configured with the named handoff spec.
        from vidbyte.agents.handoff import HandoffAgent
        return HandoffAgent(self.create(name), **agent_kwargs)

    def _describe_one(self, handoff_cls: type[Handoff]) -> dict[str, Any]:
        # Instantiate one handoff to capture its title and default section map.
        instance = handoff_cls()
        return {"class": handoff_cls.__name__, "title": instance.title, "sections": dict(instance.sections)}

    @staticmethod
    def _normalize(name: str) -> str:
        # Normalize a handoff name to its lowercase, trimmed slug form.
        return name.strip().lower()


__all__ = ["HandoffRegistry"]
