"""Context Protocol Header

Description:
    Static configuration for the SDK's prebuilt handoff catalog.
Purpose:
    Keeps the default handoff slug-to-class mapping in config so registries can
    stay focused on lookup, mutation, and construction behavior.
Architecture:
    - DEFAULT_HANDOFFS: Canonical mapping from stable handoff slugs to Handoff classes.
Relations:
    Imported by vidbyte.lib.registries.handoffs to prefill HandoffRegistry instances.
Similar Files:
    - vidbyte/lib/config/mcp_presets.py: Static SDK catalog data.
    - vidbyte/lib/registries/handoffs.py: Runtime registry wrapper around this config.
"""

from __future__ import annotations

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

DEFAULT_HANDOFFS: dict[str, type[Handoff]] = {
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

__all__ = ["DEFAULT_HANDOFFS"]
