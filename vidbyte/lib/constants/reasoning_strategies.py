"""FILE: vidbyte/lib/constants/reasoning_strategies.py

PURPOSE: Owns the required-field lists shared by the 25 batch-2 reasoning-strategy builtin tools. This module stores stable validation data only; it does not validate arguments, construct tool specifications, or render context. Closed-vocabulary categorical values live in vidbyte/lib/enums/reasoning_strategies.py, not here.
ROLE IN CODEBASE: Each module under vidbyte/tools/builtins/reasoning/ imports its required-field tuple(s) from here and passes them to ReasoningToolInput.missing_required().
ARCHITECTURE NOTE: Centralizing these tuples under vidbyte.lib keeps the public SDK contract independent from the builtins implementation, matching the existing vidbyte/lib/constants/cot_events.py precedent for the deep chain-of-thought tools.
COMMON MODIFICATION PATTERNS: Add or edit a tool's required fields here, then update that tool's ToolParameter descriptions and its design-doc requirement so the model-facing schema and the validation constants stay synchronized.
WHAT NOT TO DO: Do not add validation logic or model-facing prose here; those belong to the owning tool module. Do not add a categorical value set here; that belongs in vidbyte/lib/enums/reasoning_strategies.py. Do not duplicate a tuple that already exists for another tool.
KNOWN EDGE CASES: Field order in each *_REQUIRED_FIELDS tuple is the order surfaced in ReasoningToolInput.missing_required() error messages, so preserve it when editing.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
"""

from __future__ import annotations

ABSENCE_EVIDENCE_REQUIRED_FIELDS = (
    "hypothesis",
    "expected_evidence_if_true",
    "search_conducted",
    "search_adequacy",
    "significance",
    "conclusion",
)
BURDEN_OF_PROOF_REQUIRED_FIELDS = (
    "claim",
    "default_presumption",
    "burden_holder",
    "verdict",
    "decision",
)
BURDEN_OF_PROOF_REQUIRED_PRESENT_FIELDS = ("supporting_evidence", "opposing_evidence")
CIRCULARITY_REQUIRED_FIELDS = (
    "argument",
    "premises",
    "conclusion",
    "dependency_map",
    "circle_found",
    "fix",
    "verdict",
)
COMPOSITION_DIVISION_REQUIRED_FIELDS = (
    "parts",
    "whole",
    "property",
    "aggregation_claim",
    "validity",
    "counterexample",
)
CONSISTENCY_REQUIRED_FIELDS = ("claims", "consistency_status", "resolution")
CONSISTENCY_REQUIRED_PRESENT_FIELDS = ("pairwise_conflicts",)
COUNTEREXAMPLE_REQUIRED_FIELDS = (
    "claim",
    "intended_scope",
    "constructed_case",
    "violated_condition",
    "generalizes",
    "refined_claim",
)
DEFEASIBLE_REQUIRED_FIELDS = (
    "default_rule",
    "case",
    "rule_applies",
    "defeaters",
    "final_conclusion",
    "retraction_note",
)
DIALECTIC_REQUIRED_FIELDS = (
    "thesis",
    "antithesis",
    "synthesis",
    "preserved_insight",
    "discarded_insight",
    "synthesis_stability",
)
DILEMMA_REQUIRED_FIELDS = ("case_reasoning", "conclusion", "exhaustiveness")
EQUIVOCATION_REQUIRED_FIELDS = (
    "term",
    "senses",
    "occurrences",
    "drift",
    "corrected_argument",
    "fallacy_present",
)
IDENTITY_REQUIRED_FIELDS = (
    "entity_a",
    "entity_b",
    "shared_properties",
    "distinguishing_property",
    "grounds",
    "verdict",
)
INSTANTIATE_REQUIRED_FIELDS = (
    "general_rule",
    "case",
    "applicability_conditions",
    "conditions_met",
    "derived_conclusion",
    "scope_check",
)
MODAL_REQUIRED_FIELDS = (
    "claim",
    "modal_status",
    "possible_world_evidence",
    "actuality",
    "reasoning",
)
NECESSARY_SUFFICIENT_REQUIRED_FIELDS = (
    "condition",
    "target",
    "necessity_direction",
    "sufficiency_direction",
    "verdict",
    "implications",
)
PARADOX_REQUIRED_FIELDS = (
    "paradox",
    "premises",
    "hidden_assumption",
    "premise_to_drop",
    "resolution",
    "what_it_reveals",
)
PARTITION_REQUIRED_FIELDS = ("membership_rules", "coverage", "overlap", "verdict")
PREDICT_REQUIRED_FIELDS = (
    "theory",
    "initial_conditions",
    "derived_prediction",
    "observed_outcome",
    "match",
    "revision",
)
QUANTIFIER_REQUIRED_FIELDS = (
    "claim",
    "quantifier",
    "instance_checked",
    "counterexample",
    "scope_restriction",
    "verdict",
)
REGRESS_REQUIRED_FIELDS = (
    "claim",
    "justification_chain",
    "terminates_at",
    "style",
    "adequacy",
)
SOCRATIC_REQUIRED_FIELDS = (
    "claim",
    "probing_question",
    "assumption_surfaced",
    "contradiction_found",
    "revised_claim",
    "depth_reached",
)
STATISTICAL_SYLLOGISM_REQUIRED_FIELDS = (
    "population_claim",
    "frequency",
    "individual",
    "membership",
    "defeater",
    "probable_conclusion",
)
STRAWMAN_REQUIRED_FIELDS = (
    "original_argument",
    "restated_argument",
    "distortion",
    "fair_restatement",
    "criticism_applies",
    "residual_critique",
)
TESTIMONY_REQUIRED_FIELDS = (
    "source",
    "claim",
    "reliability_factors",
    "trust_verdict",
    "residual_uncertainty",
)
TESTIMONY_REQUIRED_PRESENT_FIELDS = ("corroboration", "conflicts")
THOUGHT_EXPERIMENT_REQUIRED_FIELDS = (
    "setup",
    "manipulation",
    "predicted_outcome",
    "insight",
    "limits",
)
TRANSITIVITY_REQUIRED_FIELDS = (
    "pairwise_links",
    "derived_chain",
    "cycle_detected",
    "consistency",
)

__all__ = [
    "ABSENCE_EVIDENCE_REQUIRED_FIELDS",
    "BURDEN_OF_PROOF_REQUIRED_FIELDS",
    "BURDEN_OF_PROOF_REQUIRED_PRESENT_FIELDS",
    "CIRCULARITY_REQUIRED_FIELDS",
    "COMPOSITION_DIVISION_REQUIRED_FIELDS",
    "CONSISTENCY_REQUIRED_FIELDS",
    "CONSISTENCY_REQUIRED_PRESENT_FIELDS",
    "COUNTEREXAMPLE_REQUIRED_FIELDS",
    "DEFEASIBLE_REQUIRED_FIELDS",
    "DIALECTIC_REQUIRED_FIELDS",
    "DILEMMA_REQUIRED_FIELDS",
    "EQUIVOCATION_REQUIRED_FIELDS",
    "IDENTITY_REQUIRED_FIELDS",
    "INSTANTIATE_REQUIRED_FIELDS",
    "MODAL_REQUIRED_FIELDS",
    "NECESSARY_SUFFICIENT_REQUIRED_FIELDS",
    "PARADOX_REQUIRED_FIELDS",
    "PARTITION_REQUIRED_FIELDS",
    "PREDICT_REQUIRED_FIELDS",
    "QUANTIFIER_REQUIRED_FIELDS",
    "REGRESS_REQUIRED_FIELDS",
    "SOCRATIC_REQUIRED_FIELDS",
    "STATISTICAL_SYLLOGISM_REQUIRED_FIELDS",
    "STRAWMAN_REQUIRED_FIELDS",
    "TESTIMONY_REQUIRED_FIELDS",
    "TESTIMONY_REQUIRED_PRESENT_FIELDS",
    "THOUGHT_EXPERIMENT_REQUIRED_FIELDS",
    "TRANSITIVITY_REQUIRED_FIELDS",
]
