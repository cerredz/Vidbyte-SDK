"""FILE: vidbyte/lib/constants/reasoning_strategies.py

PURPOSE: Owns the required-field lists and closed-vocabulary value sets shared by the 25 batch-2 reasoning-strategy builtin tools. This module stores stable validation data only; it does not validate arguments, construct tool specifications, or render context.
ROLE IN CODEBASE: Each module under vidbyte/tools/builtins/reasoning/ imports its required-field tuple and closed-vocabulary tuples from here and passes them to ReasoningToolInput.missing_required() and ReasoningToolInput.enum_error().
ARCHITECTURE NOTE: Centralizing these tuples under vidbyte.lib keeps the public SDK contract independent from the builtins implementation, matching the existing vidbyte/lib/constants/cot_events.py precedent for the deep chain-of-thought tools.
COMMON MODIFICATION PATTERNS: Add or edit a tool's required fields or vocabulary here, then update that tool's ToolParameter descriptions and its design-doc requirement so the model-facing schema and the validation constants stay synchronized.
WHAT NOT TO DO: Do not add validation logic or model-facing prose here; those belong to the owning tool module. Do not duplicate a tuple that already exists for another tool.
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
ABSENCE_EVIDENCE_SIGNIFICANCE_VALUES = ("evidence_against", "neutral", "evidence_for")
BURDEN_OF_PROOF_REQUIRED_FIELDS = (
    "claim",
    "default_presumption",
    "burden_holder",
    "verdict",
    "decision",
)
BURDEN_OF_PROOF_REQUIRED_PRESENT_FIELDS = ("supporting_evidence", "opposing_evidence")
BURDEN_OF_PROOF_VERDICT_VALUES = ("established", "not_established", "contested")
CIRCULARITY_REQUIRED_FIELDS = (
    "argument",
    "premises",
    "conclusion",
    "dependency_map",
    "circle_found",
    "fix",
    "verdict",
)
CIRCULARITY_VERDICT_VALUES = ("circular", "not_circular", "partially")
COMPOSITION_DIVISION_REQUIRED_FIELDS = (
    "parts",
    "whole",
    "property",
    "aggregation_claim",
    "validity",
    "counterexample",
)
COMPOSITION_DIVISION_VALIDITY_VALUES = (
    "valid",
    "fallacy_of_composition",
    "fallacy_of_division",
    "unknown",
)
CONSISTENCY_REQUIRED_FIELDS = ("claims", "consistency_status", "resolution")
CONSISTENCY_REQUIRED_PRESENT_FIELDS = ("pairwise_conflicts",)
CONSISTENCY_STATUS_VALUES = ("consistent", "contradictory", "unresolved")
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
DEFEASIBLE_RULE_APPLIES_VALUES = ("yes", "no", "borderline")
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
EQUIVOCATION_FALLACY_VALUES = ("yes", "no", "uncertain")
IDENTITY_REQUIRED_FIELDS = (
    "entity_a",
    "entity_b",
    "shared_properties",
    "distinguishing_property",
    "grounds",
    "verdict",
)
IDENTITY_VERDICT_VALUES = ("same", "different", "indeterminate")
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
MODAL_STATUS_VALUES = ("necessary", "possible", "contingent", "impossible")
NECESSARY_SUFFICIENT_REQUIRED_FIELDS = (
    "condition",
    "target",
    "necessity_direction",
    "sufficiency_direction",
    "verdict",
    "implications",
)
NECESSARY_SUFFICIENT_VERDICT_VALUES = (
    "necessary_only",
    "sufficient_only",
    "both",
    "neither",
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
PARTITION_VERDICT_VALUES = ("exhaustive_disjoint", "gaps", "overlaps")
PREDICT_REQUIRED_FIELDS = (
    "theory",
    "initial_conditions",
    "derived_prediction",
    "observed_outcome",
    "match",
    "revision",
)
PREDICT_MATCH_VALUES = ("yes", "no", "partial")
QUANTIFIER_REQUIRED_FIELDS = (
    "claim",
    "quantifier",
    "instance_checked",
    "counterexample",
    "scope_restriction",
    "verdict",
)
QUANTIFIER_KIND_VALUES = ("all", "some", "none", "most")
QUANTIFIER_VERDICT_VALUES = ("holds", "fails", "unverifiable")
REGRESS_REQUIRED_FIELDS = (
    "claim",
    "justification_chain",
    "terminates_at",
    "style",
    "adequacy",
)
REGRESS_STYLE_VALUES = ("foundational", "circular", "infinite")
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
STRAWMAN_CRITICISM_VALUES = ("yes", "no", "partially")
TESTIMONY_REQUIRED_FIELDS = (
    "source",
    "claim",
    "reliability_factors",
    "trust_verdict",
    "residual_uncertainty",
)
TESTIMONY_REQUIRED_PRESENT_FIELDS = ("corroboration", "conflicts")
TESTIMONY_TRUST_VALUES = ("high", "moderate", "low", "withheld")
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
TRANSITIVITY_CONSISTENCY_VALUES = ("consistent", "cyclic", "intransitive")

__all__ = [
    "ABSENCE_EVIDENCE_REQUIRED_FIELDS",
    "ABSENCE_EVIDENCE_SIGNIFICANCE_VALUES",
    "BURDEN_OF_PROOF_REQUIRED_FIELDS",
    "BURDEN_OF_PROOF_REQUIRED_PRESENT_FIELDS",
    "BURDEN_OF_PROOF_VERDICT_VALUES",
    "CIRCULARITY_REQUIRED_FIELDS",
    "CIRCULARITY_VERDICT_VALUES",
    "COMPOSITION_DIVISION_REQUIRED_FIELDS",
    "COMPOSITION_DIVISION_VALIDITY_VALUES",
    "CONSISTENCY_REQUIRED_FIELDS",
    "CONSISTENCY_REQUIRED_PRESENT_FIELDS",
    "CONSISTENCY_STATUS_VALUES",
    "COUNTEREXAMPLE_REQUIRED_FIELDS",
    "DEFEASIBLE_REQUIRED_FIELDS",
    "DEFEASIBLE_RULE_APPLIES_VALUES",
    "DIALECTIC_REQUIRED_FIELDS",
    "DILEMMA_REQUIRED_FIELDS",
    "EQUIVOCATION_FALLACY_VALUES",
    "EQUIVOCATION_REQUIRED_FIELDS",
    "IDENTITY_REQUIRED_FIELDS",
    "IDENTITY_VERDICT_VALUES",
    "INSTANTIATE_REQUIRED_FIELDS",
    "MODAL_REQUIRED_FIELDS",
    "MODAL_STATUS_VALUES",
    "NECESSARY_SUFFICIENT_REQUIRED_FIELDS",
    "NECESSARY_SUFFICIENT_VERDICT_VALUES",
    "PARADOX_REQUIRED_FIELDS",
    "PARTITION_REQUIRED_FIELDS",
    "PARTITION_VERDICT_VALUES",
    "PREDICT_MATCH_VALUES",
    "PREDICT_REQUIRED_FIELDS",
    "QUANTIFIER_KIND_VALUES",
    "QUANTIFIER_REQUIRED_FIELDS",
    "QUANTIFIER_VERDICT_VALUES",
    "REGRESS_REQUIRED_FIELDS",
    "REGRESS_STYLE_VALUES",
    "SOCRATIC_REQUIRED_FIELDS",
    "STATISTICAL_SYLLOGISM_REQUIRED_FIELDS",
    "STRAWMAN_CRITICISM_VALUES",
    "STRAWMAN_REQUIRED_FIELDS",
    "TESTIMONY_REQUIRED_FIELDS",
    "TESTIMONY_REQUIRED_PRESENT_FIELDS",
    "TESTIMONY_TRUST_VALUES",
    "THOUGHT_EXPERIMENT_REQUIRED_FIELDS",
    "TRANSITIVITY_CONSISTENCY_VALUES",
    "TRANSITIVITY_REQUIRED_FIELDS",
]
