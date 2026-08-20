"""Context Protocol Header

Description:
    Defines context primitives for named scientific-reasoning strategies:
    deduction, induction, abduction, analogy, causal-chain reasoning, Bayesian
    updating, differential diagnosis, Fermi estimation, steelmanning, and
    falsification.
Purpose:
    Gives each reasoning-strategy tool a typed, bounded ContextItem that renders
    the strategy's characteristic output shape into the context window.
Architecture:
    - DeductionContextItem: Premises, named inference rule, conclusion, caveat.
    - InductionContextItem: Observations, pattern, generalization, falsifier.
    - AbductionContextItem: Evidence, scored competing hypotheses, best pick.
    - AnalogyContextItem: Source/target domains, mapped relations, breakdown point.
    - CausalChainContextItem: Cause, mechanism, effect, confounders, test.
    - BayesianUpdateContextItem: Prior/posterior probabilities and likelihoods.
    - DifferentialDiagnosisContextItem: Candidate set, eliminations, next check.
    - FermiEstimateContextItem: Decomposed quantity estimate with sanity band.
    - SteelmanContextItem: A position against its strongest opposition.
    - FalsifyContextItem: A claim against its designed falsification test.
    Batch 2 (tools 11-35) — formal logic, epistemology, argumentation:
    - CounterexampleContextItem: Formal disproof by constructed case.
    - ConsistencyContextItem: Contradiction audit of a belief set.
    - DilemmaContextItem: Proof by exhaustive cases.
    - QuantifierContextItem: Scope analysis of quantified claims.
    - TransitivityContextItem: Ordered relational chains and cycles.
    - IdentityContextItem: Leibniz's-law sameness check.
    - PartitionContextItem: Exhaustive and disjoint classification check.
    - ModalContextItem: Necessity/possibility analysis.
    - EquivocationContextItem: Term-consistency audit across an argument.
    - NecessarySufficientContextItem: Condition-direction analysis.
    - CompositionDivisionContextItem: Part-whole inference check.
    - CircularityContextItem: Begging-the-question detection.
    - RegressContextItem: Justification-chain structure.
    - BurdenOfProofContextItem: Presumption and evidence burden.
    - TestimonyContextItem: Source reliability evaluation.
    - AbsenceEvidenceContextItem: Absence-of-evidence inference.
    - DefeasibleContextItem: Default reasoning with defeaters.
    - StatisticalSyllogismContextItem: Frequency-to-individual transfer.
    - SocraticContextItem: Elenchus by probing question.
    - DialecticContextItem: Thesis, antithesis, synthesis.
    - ParadoxContextItem: Hidden-assumption dissection.
    - StrawmanContextItem: Fair-restatement audit.
    - PredictContextItem: Deductive-nomological prediction.
    - ThoughtExperimentContextItem: Gedankenexperiment analysis.
    - InstantiateContextItem: Universal instantiation with scope check.
Relations:
    Written by the tools in vidbyte.tools.builtins.reasoning and re-exported
    through vidbyte.context.primitives.
Similar Files:
    - `vidbyte/context/primitives/checkpoints.py`
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _extend_section, _truncate_text

_HYPOTHESIS_KEYS = ("hypothesis", "explains", "simplicity", "assumptions_required")
_RULED_OUT_KEYS = ("candidate", "ruled_out_by")
_CONFLICT_KEYS = ("claim_a", "claim_b", "conflict")
_CASE_REASONING_KEYS = ("case", "leads_to")
_PAIRWISE_LINK_KEYS = ("from", "to", "holds")
_MEMBERSHIP_RULE_KEYS = ("category", "rule")
_OCCURRENCE_KEYS = ("context", "sense_used")
_DEPENDENCY_KEYS = ("premise", "depends_on")
_RELIABILITY_FACTOR_KEYS = ("factor", "assessment")
_DEFEATER_KEYS = ("defeater", "applies")
_CONDITION_MET_KEYS = ("condition", "satisfied")


def _render_object_bullets(items: tuple[Mapping[str, Any], ...], keys: tuple[str, ...]) -> tuple[str, ...]:
    # Flattens each mapping into one "key: value; key: value" bullet, skipping absent keys.
    bullets = []
    for item in items:
        parts = [f"{key}: {item[key]}" for key in keys if item.get(key)]
        if parts:
            bullets.append("; ".join(parts))
    return tuple(bullets)


@dataclass(frozen=True, slots=True)
class DeductionContextItem:
    """A deductive chain: stated premises, the named rule, and the conclusion they force."""

    primitive_id: str
    premises: tuple[str, ...]
    inference_rule: str
    conclusion: str
    soundness_caveat: str
    title: str = "Deductive Chain"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "deduction"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders premises, the named rule, the conclusion, and the soundness caveat.
        lines: list[str] = []
        _extend_section(lines, "Premises", self.premises)
        lines.append(f"Inference Rule: {self.inference_rule}")
        lines.extend(("", "### Conclusion", self.conclusion))
        lines.extend(("", "### Soundness Caveat", self.soundness_caveat))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class InductionContextItem:
    """An inductive generalization projected from specific observations."""

    primitive_id: str
    observations: tuple[str, ...]
    pattern: str
    generalization: str
    sample_bias_risk: str
    falsifying_case: str
    confidence: float | None = None
    title: str = "Inductive Generalization"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "induction"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders observations, the noticed pattern, the generalization, and its risks.
        confidence_text = "N/A" if self.confidence is None else f"{self.confidence:.2f}"
        lines: list[str] = []
        _extend_section(lines, "Observations", self.observations)
        lines.extend(("", "### Pattern", self.pattern))
        lines.extend(("", "### Generalization", self.generalization))
        lines.append(f"Confidence: {confidence_text}")
        lines.extend(("", "### Sample Bias Risk", self.sample_bias_risk))
        lines.extend(("", "### Falsifying Case", self.falsifying_case))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class AbductionContextItem:
    """Inference to the best explanation among scored competing hypotheses."""

    primitive_id: str
    evidence: tuple[str, ...]
    hypotheses: tuple[Mapping[str, Any], ...]
    best: str
    discriminating_test: str
    runner_up: str | None = None
    title: str = "Abductive Inference"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "abduction"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders evidence, each scored hypothesis, the winner, and the discriminating test.
        lines: list[str] = []
        _extend_section(lines, "Evidence", self.evidence)
        _extend_section(lines, "Hypotheses", _render_object_bullets(self.hypotheses, _HYPOTHESIS_KEYS))
        lines.extend(("", "### Best Explanation", self.best))
        if self.runner_up:
            lines.extend(("", "### Runner-Up", self.runner_up))
        lines.extend(("", "### Discriminating Test", self.discriminating_test))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class AnalogyContextItem:
    """An analogical transfer with its mapped relations and where it breaks down."""

    primitive_id: str
    source_domain: str
    target_domain: str
    mapped_relations: tuple[str, ...]
    breaks_down_at: str
    carries_weight: str
    title: str = "Analogical Transfer"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "analogy"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the source/target domains, mapped relations, breakdown point, and weight.
        lines = [
            f"Source Domain: {self.source_domain}",
            f"Target Domain: {self.target_domain}",
        ]
        _extend_section(lines, "Mapped Relations", self.mapped_relations)
        lines.extend(("", "### Breaks Down At", self.breaks_down_at))
        lines.append(f"Carries Weight: {self.carries_weight}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class CausalChainContextItem:
    """A causal claim anchored to an explicit mechanism, not bare correlation."""

    primitive_id: str
    cause: str
    mechanism: str
    effect: str
    confounders: tuple[str, ...]
    intervention_test: str
    title: str = "Causal Chain"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "causal_chain"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders cause, mechanism, effect, confounders, and the intervention test.
        lines = [f"Cause: {self.cause}"]
        lines.extend(("", "### Mechanism", self.mechanism))
        lines.extend(("", "### Effect", self.effect))
        _extend_section(lines, "Confounders", self.confounders)
        lines.extend(("", "### Intervention Test", self.intervention_test))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class BayesianUpdateContextItem:
    """An explicit prior-to-posterior belief revision over a stated hypothesis."""

    primitive_id: str
    hypothesis: str
    prior: float
    evidence: str
    likelihood_if_true: float
    likelihood_if_false: float
    posterior: float
    shift_explanation: str
    title: str = "Bayesian Update"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "bayesian_update"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the hypothesis, prior, evidence, both likelihoods, posterior, and explanation.
        lines = [
            f"Hypothesis: {self.hypothesis}",
            f"Prior: {self.prior:.3f}",
        ]
        lines.extend(("", "### Evidence", self.evidence))
        lines.append(f"Likelihood if True: {self.likelihood_if_true:.3f}")
        lines.append(f"Likelihood if False: {self.likelihood_if_false:.3f}")
        lines.append(f"Posterior: {self.posterior:.3f}")
        lines.extend(("", "### Shift Explanation", self.shift_explanation))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class DifferentialDiagnosisContextItem:
    """A candidate set narrowed by elimination toward the next discriminating check."""

    primitive_id: str
    candidate_set: tuple[str, ...]
    remaining: tuple[str, ...]
    next_discriminator: str
    ruled_out: tuple[Mapping[str, Any], ...] = ()
    title: str = "Differential Diagnosis"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "differential_diagnosis"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the full candidate set, eliminations, survivors, and the next check.
        lines: list[str] = []
        _extend_section(lines, "Candidate Set", self.candidate_set)
        _extend_section(lines, "Ruled Out", _render_object_bullets(self.ruled_out, _RULED_OUT_KEYS))
        _extend_section(lines, "Remaining", self.remaining)
        lines.extend(("", "### Next Discriminator", self.next_discriminator))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class FermiEstimateContextItem:
    """A Fermi estimate: a quantity decomposed into checkable sub-estimates."""

    primitive_id: str
    quantity: str
    decomposition: tuple[str, ...]
    arithmetic: str
    estimate: str
    sanity_band: str
    anchor_risk: str
    title: str = "Fermi Estimate"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "fermi_estimate"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the quantity, its decomposition, the arithmetic, and the resulting estimate.
        lines = [f"Quantity: {self.quantity}"]
        _extend_section(lines, "Decomposition", self.decomposition)
        lines.extend(("", "### Arithmetic", self.arithmetic))
        lines.append(f"Estimate: {self.estimate}")
        lines.append(f"Sanity Band: {self.sanity_band}")
        lines.append(f"Anchor Risk: {self.anchor_risk}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class SteelmanContextItem:
    """A position tested against the strongest available opposition."""

    primitive_id: str
    my_position: str
    strongest_opposition: str
    survives: str
    revision: str = ""
    title: str = "Steelman"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "steelman"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the position, its strongest opposition, the verdict, and any revision.
        lines = ["### My Position", self.my_position]
        lines.extend(("", "### Strongest Opposition", self.strongest_opposition))
        lines.extend(("", f"Survives: {self.survives}"))
        if self.revision:
            lines.extend(("", "### Revision", self.revision))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class FalsifyContextItem:
    """A claim paired with the test designed to refute it and its current status."""

    primitive_id: str
    claim: str
    test_design: str
    riskiest_prediction: str
    status: str
    title: str = "Falsification Test"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "falsify"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the claim, its test design, the riskiest prediction, and current status.
        lines = ["### Claim", self.claim]
        lines.extend(("", "### Test Design", self.test_design))
        lines.extend(("", "### Riskiest Prediction", self.riskiest_prediction))
        lines.extend(("", f"Status: {self.status}"))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class CounterexampleContextItem:
    """A formal disproof: a constructed case that violates a general claim."""

    primitive_id: str
    claim: str
    intended_scope: str
    constructed_case: str
    violated_condition: str
    generalizes: str
    refined_claim: str
    title: str = "Counterexample"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "counterexample"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the claim, scope, the violating case, and the refined claim.
        lines = ["### Claim", self.claim]
        lines.extend(("", "### Intended Scope", self.intended_scope))
        lines.extend(("", "### Constructed Case", self.constructed_case))
        lines.extend(("", "### Violated Condition", self.violated_condition))
        lines.extend(("", "### Generalizes", self.generalizes))
        lines.extend(("", "### Refined Claim", self.refined_claim))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class ConsistencyContextItem:
    """A belief set audited for pairwise contradictions."""

    primitive_id: str
    claims: tuple[str, ...]
    pairwise_conflicts: tuple[Mapping[str, Any], ...]
    consistency_status: str
    resolution: str
    title: str = "Consistency Audit"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "consistency"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the claims, concrete conflicts, status, and resolution.
        lines: list[str] = []
        _extend_section(lines, "Claims", self.claims)
        _extend_section(lines, "Pairwise Conflicts", _render_object_bullets(self.pairwise_conflicts, _CONFLICT_KEYS))
        lines.extend(("", f"Status: {self.consistency_status}"))
        lines.extend(("", "### Resolution", self.resolution))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class DilemmaContextItem:
    """A proof by exhaustive cases: every branch leads to the conclusion."""

    primitive_id: str
    alternatives: tuple[str, ...]
    case_reasoning: tuple[Mapping[str, Any], ...]
    conclusion: str
    exhaustiveness: str
    title: str = "Proof by Cases"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "dilemma"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the branches, per-case reasoning, conclusion, and exclusion argument.
        lines: list[str] = []
        _extend_section(lines, "Alternatives", self.alternatives)
        _extend_section(lines, "Case Reasoning", _render_object_bullets(self.case_reasoning, _CASE_REASONING_KEYS))
        lines.extend(("", "### Conclusion", self.conclusion))
        lines.extend(("", "### Exhaustiveness", self.exhaustiveness))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class QuantifierContextItem:
    """A quantified claim checked against a concrete instance."""

    primitive_id: str
    claim: str
    quantifier: str
    instance_checked: str
    counterexample: str
    scope_restriction: str
    verdict: str
    title: str = "Quantifier Analysis"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "quantifier"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the claim, its quantifier, the checked instance, and the verdict.
        lines = ["### Claim", self.claim]
        lines.append(f"Quantifier: {self.quantifier}")
        lines.extend(("", "### Instance Checked", self.instance_checked))
        lines.extend(("", "### Counterexample", self.counterexample))
        lines.extend(("", "### Scope Restriction", self.scope_restriction))
        lines.extend(("", f"Verdict: {self.verdict}"))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class TransitivityContextItem:
    """A relational chain: known links, forced conclusions, and any cycle."""

    primitive_id: str
    entities: tuple[str, ...]
    relation: str
    pairwise_links: tuple[Mapping[str, Any], ...]
    derived_chain: tuple[str, ...]
    cycle_detected: str
    consistency: str
    title: str = "Transitive Chain"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "transitivity"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the entities, relation, checked links, derived chain, cycles, and consistency.
        lines = [f"Relation: {self.relation}"]
        _extend_section(lines, "Entities", self.entities)
        _extend_section(lines, "Pairwise Links", _render_object_bullets(self.pairwise_links, _PAIRWISE_LINK_KEYS))
        _extend_section(lines, "Derived Chain", self.derived_chain)
        lines.extend(("", "### Cycle Detected", self.cycle_detected))
        lines.extend(("", f"Consistency: {self.consistency}"))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class IdentityContextItem:
    """A Leibniz's-law check on whether two entities are the same."""

    primitive_id: str
    entity_a: str
    entity_b: str
    shared_properties: tuple[str, ...]
    distinguishing_property: str
    grounds: str
    verdict: str
    title: str = "Identity Check"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "identity"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the two entities, shared properties, the deciding property, and verdict.
        lines = [f"Entity A: {self.entity_a}", f"Entity B: {self.entity_b}"]
        _extend_section(lines, "Shared Properties", self.shared_properties)
        lines.extend(("", "### Distinguishing Property", self.distinguishing_property))
        lines.extend(("", "### Grounds", self.grounds))
        lines.extend(("", f"Verdict: {self.verdict}"))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class PartitionContextItem:
    """A classification checked for gaps and overlaps."""

    primitive_id: str
    items: tuple[str, ...]
    categories: tuple[str, ...]
    membership_rules: tuple[Mapping[str, Any], ...]
    coverage: str
    overlap: str
    verdict: str
    title: str = "Partition Check"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "partition"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the items, categories, membership rules, gaps, overlaps, and verdict.
        lines: list[str] = []
        _extend_section(lines, "Items", self.items)
        _extend_section(lines, "Categories", self.categories)
        _extend_section(lines, "Membership Rules", _render_object_bullets(self.membership_rules, _MEMBERSHIP_RULE_KEYS))
        lines.extend(("", "### Coverage", self.coverage))
        lines.extend(("", "### Overlap", self.overlap))
        lines.extend(("", f"Verdict: {self.verdict}"))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class ModalContextItem:
    """A claim's modal status supported by possible-world evidence."""

    primitive_id: str
    claim: str
    modal_status: str
    possible_world_evidence: str
    actuality: str
    reasoning: str
    title: str = "Modal Analysis"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "modal"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the claim, its modal status, world evidence, actuality, and argument.
        lines = ["### Claim", self.claim]
        lines.append(f"Modal Status: {self.modal_status}")
        lines.extend(("", "### Possible World Evidence", self.possible_world_evidence))
        lines.extend(("", "### Actuality", self.actuality))
        lines.extend(("", "### Reasoning", self.reasoning))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class EquivocationContextItem:
    """An audit of a term used with shifting meanings across an argument."""

    primitive_id: str
    term: str
    senses: tuple[str, ...]
    occurrences: tuple[Mapping[str, Any], ...]
    drift: str
    corrected_argument: str
    fallacy_present: str
    title: str = "Equivocation Audit"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "equivocation"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the term, its senses, each occurrence, the drift, and the correction.
        lines = [f"Term: {self.term}"]
        _extend_section(lines, "Senses", self.senses)
        _extend_section(lines, "Occurrences", _render_object_bullets(self.occurrences, _OCCURRENCE_KEYS))
        lines.extend(("", "### Drift", self.drift))
        lines.extend(("", "### Corrected Argument", self.corrected_argument))
        lines.append(f"Fallacy Present: {self.fallacy_present}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class NecessarySufficientContextItem:
    """A condition's necessity and sufficiency tested in both directions."""

    primitive_id: str
    condition: str
    target: str
    necessity_direction: str
    sufficiency_direction: str
    verdict: str
    implications: str
    title: str = "Condition Analysis"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "necessary_sufficient"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the condition, both direction tests, the verdict, and implications.
        lines = [f"Condition: {self.condition}", f"Target: {self.target}"]
        lines.extend(("", "### Necessity Direction", self.necessity_direction))
        lines.extend(("", "### Sufficiency Direction", self.sufficiency_direction))
        lines.extend(("", f"Verdict: {self.verdict}"))
        lines.extend(("", "### Implications", self.implications))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class CompositionDivisionContextItem:
    """A part-whole property transfer checked for composition/division fallacies."""

    primitive_id: str
    parts: tuple[str, ...]
    whole: str
    property: str
    aggregation_claim: str
    validity: str
    counterexample: str
    title: str = "Part-Whole Check"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "composition_division"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the parts, whole, property, transfer claim, verdict, and counterexample.
        lines: list[str] = []
        _extend_section(lines, "Parts", self.parts)
        lines.append(f"Whole: {self.whole}")
        lines.append(f"Property: {self.property}")
        lines.extend(("", "### Aggregation Claim", self.aggregation_claim))
        lines.extend(("", f"Validity: {self.validity}"))
        lines.extend(("", "### Counterexample", self.counterexample))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class CircularityContextItem:
    """An argument audited for premises that presuppose the conclusion."""

    primitive_id: str
    argument: str
    premises: tuple[str, ...]
    conclusion: str
    dependency_map: tuple[Mapping[str, Any], ...]
    circle_found: str
    fix: str
    verdict: str
    title: str = "Circularity Audit"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "circularity"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the argument, premises, dependencies, the circle, and its fix.
        lines = ["### Argument", self.argument]
        _extend_section(lines, "Premises", self.premises)
        lines.extend(("", "### Conclusion", self.conclusion))
        _extend_section(lines, "Dependency Map", _render_object_bullets(self.dependency_map, _DEPENDENCY_KEYS))
        lines.extend(("", "### Circle Found", self.circle_found))
        lines.extend(("", "### Fix", self.fix))
        lines.extend(("", f"Verdict: {self.verdict}"))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class RegressContextItem:
    """A justification chain analyzed for where and how it terminates."""

    primitive_id: str
    claim: str
    justification_chain: tuple[str, ...]
    terminates_at: str
    style: str
    adequacy: str
    title: str = "Justification Regress"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "regress"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the claim, the chain, its termination point, style, and adequacy.
        lines = ["### Claim", self.claim]
        _extend_section(lines, "Justification Chain", self.justification_chain)
        lines.extend(("", "### Terminates At", self.terminates_at))
        lines.extend(("", f"Style: {self.style}"))
        lines.extend(("", "### Adequacy", self.adequacy))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class BurdenOfProofContextItem:
    """A claim's evidence burden, presumption, and standing verdict."""

    primitive_id: str
    claim: str
    default_presumption: str
    supporting_evidence: tuple[str, ...]
    opposing_evidence: tuple[str, ...]
    burden_holder: str
    verdict: str
    decision: str
    title: str = "Burden of Proof"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "burden_of_proof"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the claim, presumption, both evidence sides, burden, verdict, and decision.
        lines = ["### Claim", self.claim]
        lines.extend(("", "### Default Presumption", self.default_presumption))
        _extend_section(lines, "Supporting Evidence", self.supporting_evidence)
        _extend_section(lines, "Opposing Evidence", self.opposing_evidence)
        lines.extend(("", "### Burden Holder", self.burden_holder))
        lines.extend(("", f"Verdict: {self.verdict}"))
        lines.extend(("", "### Decision", self.decision))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class TestimonyContextItem:
    """A testimony evaluated for source reliability and corroboration."""

    primitive_id: str
    source: str
    claim: str
    reliability_factors: tuple[Mapping[str, Any], ...]
    corroboration: tuple[str, ...]
    conflicts: tuple[str, ...]
    trust_verdict: str
    residual_uncertainty: str
    title: str = "Testimony Evaluation"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "testimony"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the source, claim, reliability factors, corroboration, conflicts, and verdict.
        lines = [f"Source: {self.source}", "### Claim", self.claim]
        _extend_section(lines, "Reliability Factors", _render_object_bullets(self.reliability_factors, _RELIABILITY_FACTOR_KEYS))
        _extend_section(lines, "Corroboration", self.corroboration)
        _extend_section(lines, "Conflicts", self.conflicts)
        lines.append(f"Trust Verdict: {self.trust_verdict}")
        lines.extend(("", "### Residual Uncertainty", self.residual_uncertainty))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class AbsenceEvidenceContextItem:
    """An absence-of-evidence inference weighed against search adequacy."""

    primitive_id: str
    hypothesis: str
    expected_evidence_if_true: str
    search_conducted: str
    search_adequacy: str
    significance: str
    conclusion: str
    title: str = "Absence of Evidence"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "absence_evidence"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the hypothesis, expected evidence, the search, adequacy, and significance.
        lines = ["### Hypothesis", self.hypothesis]
        lines.extend(("", "### Expected Evidence if True", self.expected_evidence_if_true))
        lines.extend(("", "### Search Conducted", self.search_conducted))
        lines.extend(("", "### Search Adequacy", self.search_adequacy))
        lines.extend(("", f"Significance: {self.significance}"))
        lines.extend(("", "### Conclusion", self.conclusion))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class DefeasibleContextItem:
    """A default rule applied to a case with its defeaters and retraction."""

    primitive_id: str
    default_rule: str
    case: str
    rule_applies: str
    defeaters: tuple[Mapping[str, Any], ...]
    final_conclusion: str
    retraction_note: str
    title: str = "Defeasible Reasoning"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "defeasible"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the default rule, case, applicability, defeaters, and final conclusion.
        lines = ["### Default Rule", self.default_rule]
        lines.extend(("", "### Case", self.case))
        lines.extend(("", f"Rule Applies: {self.rule_applies}"))
        _extend_section(lines, "Defeaters", _render_object_bullets(self.defeaters, _DEFEATER_KEYS))
        lines.extend(("", "### Final Conclusion", self.final_conclusion))
        lines.extend(("", "### Retraction Note", self.retraction_note))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class StatisticalSyllogismContextItem:
    """A frequency-to-individual probability transfer with its defeater."""

    primitive_id: str
    population_claim: str
    frequency: float
    individual: str
    membership: str
    defeater: str
    probable_conclusion: str
    confidence: float | None = None
    title: str = "Statistical Syllogism"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "statistical_syllogism"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the population claim, frequency, individual, membership, and conclusion.
        confidence_text = "N/A" if self.confidence is None else f"{self.confidence:.2f}"
        lines = ["### Population Claim", self.population_claim]
        lines.append(f"Frequency: {self.frequency:.3f}")
        lines.extend(("", "### Individual", self.individual))
        lines.extend(("", "### Membership", self.membership))
        lines.extend(("", "### Defeater", self.defeater))
        lines.extend(("", "### Probable Conclusion", self.probable_conclusion))
        lines.append(f"Confidence: {confidence_text}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class SocraticContextItem:
    """A claim interrogated by a probing question that surfaces a hidden assumption."""

    primitive_id: str
    claim: str
    probing_question: str
    assumption_surfaced: str
    contradiction_found: str
    revised_claim: str
    depth_reached: str
    title: str = "Socratic Elenchus"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "socratic"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the claim, the probing question, the surfaced assumption, and the revision.
        lines = ["### Claim", self.claim]
        lines.extend(("", "### Probing Question", self.probing_question))
        lines.extend(("", "### Assumption Surfaced", self.assumption_surfaced))
        lines.extend(("", "### Contradiction Found", self.contradiction_found))
        lines.extend(("", "### Revised Claim", self.revised_claim))
        lines.extend(("", "### Depth Reached", self.depth_reached))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class DialecticContextItem:
    """A thesis and its strongest antithesis resolved into a synthesis."""

    primitive_id: str
    thesis: str
    antithesis: str
    synthesis: str
    preserved_insight: str
    discarded_insight: str
    synthesis_stability: str
    title: str = "Dialectic"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "dialectic"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the thesis, antithesis, synthesis, and what each side gave up and kept.
        lines = ["### Thesis", self.thesis]
        lines.extend(("", "### Antithesis", self.antithesis))
        lines.extend(("", "### Synthesis", self.synthesis))
        lines.extend(("", "### Preserved Insight", self.preserved_insight))
        lines.extend(("", "### Discarded Insight", self.discarded_insight))
        lines.extend(("", "### Synthesis Stability", self.synthesis_stability))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class ParadoxContextItem:
    """A paradox dissected into premises, a hidden assumption, and a dropped premise."""

    primitive_id: str
    paradox: str
    premises: tuple[str, ...]
    hidden_assumption: str
    premise_to_drop: str
    resolution: str
    what_it_reveals: str
    title: str = "Paradox Dissection"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "paradox"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the paradox, its premises, the hidden assumption, and the resolution.
        lines = ["### Paradox", self.paradox]
        _extend_section(lines, "Premises", self.premises)
        lines.extend(("", "### Hidden Assumption", self.hidden_assumption))
        lines.extend(("", f"Premise to Drop: {self.premise_to_drop}"))
        lines.extend(("", "### Resolution", self.resolution))
        lines.extend(("", "### What It Reveals", self.what_it_reveals))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class StrawmanContextItem:
    """An argument audited against the critic's restatement of it."""

    primitive_id: str
    original_argument: str
    restated_argument: str
    distortion: str
    fair_restatement: str
    criticism_applies: str
    residual_critique: str
    title: str = "Strawman Audit"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "strawman"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the original, the restatement, the distortion, and the fair version.
        lines = ["### Original Argument", self.original_argument]
        lines.extend(("", "### Restated Argument", self.restated_argument))
        lines.extend(("", "### Distortion", self.distortion))
        lines.extend(("", "### Fair Restatement", self.fair_restatement))
        lines.extend(("", f"Criticism Applies: {self.criticism_applies}"))
        lines.extend(("", "### Residual Critique", self.residual_critique))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class PredictContextItem:
    """A theory's derived prediction checked against the observed outcome."""

    primitive_id: str
    theory: str
    initial_conditions: tuple[str, ...]
    derived_prediction: str
    observed_outcome: str
    match: str
    revision: str
    title: str = "Deductive-Nomological Prediction"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "predict"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the theory, conditions, prediction, observation, match, and revision.
        lines = ["### Theory", self.theory]
        _extend_section(lines, "Initial Conditions", self.initial_conditions)
        lines.extend(("", "### Derived Prediction", self.derived_prediction))
        lines.extend(("", "### Observed Outcome", self.observed_outcome))
        lines.extend(("", f"Match: {self.match}"))
        lines.extend(("", "### Revision", self.revision))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class ThoughtExperimentContextItem:
    """A gedankenexperiment: an imagined world, a manipulation, and the insight."""

    primitive_id: str
    setup: str
    manipulation: str
    predicted_outcome: str
    insight: str
    limits: str
    title: str = "Thought Experiment"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "thought_experiment"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the setup, manipulation, predicted outcome, insight, and limits.
        lines = ["### Setup", self.setup]
        lines.extend(("", "### Manipulation", self.manipulation))
        lines.extend(("", "### Predicted Outcome", self.predicted_outcome))
        lines.extend(("", "### Insight", self.insight))
        lines.extend(("", "### Limits", self.limits))
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class InstantiateContextItem:
    """A general rule applied to a case after verifying its applicability conditions."""

    primitive_id: str
    general_rule: str
    case: str
    applicability_conditions: tuple[str, ...]
    conditions_met: tuple[Mapping[str, Any], ...]
    derived_conclusion: str
    scope_check: str
    title: str = "Instantiation"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "instantiate"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the rule, case, applicability checks, conclusion, and scope justification.
        lines = ["### General Rule", self.general_rule]
        lines.extend(("", "### Case", self.case))
        _extend_section(lines, "Applicability Conditions", self.applicability_conditions)
        _extend_section(lines, "Conditions Met", _render_object_bullets(self.conditions_met, _CONDITION_MET_KEYS))
        lines.extend(("", "### Derived Conclusion", self.derived_conclusion))
        lines.extend(("", "### Scope Check", self.scope_check))
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "AbductionContextItem",
    "AbsenceEvidenceContextItem",
    "AnalogyContextItem",
    "BayesianUpdateContextItem",
    "BurdenOfProofContextItem",
    "CausalChainContextItem",
    "CircularityContextItem",
    "CompositionDivisionContextItem",
    "ConsistencyContextItem",
    "CounterexampleContextItem",
    "DeductionContextItem",
    "DefeasibleContextItem",
    "DialecticContextItem",
    "DifferentialDiagnosisContextItem",
    "DilemmaContextItem",
    "EquivocationContextItem",
    "FalsifyContextItem",
    "FermiEstimateContextItem",
    "IdentityContextItem",
    "InductionContextItem",
    "InstantiateContextItem",
    "ModalContextItem",
    "NecessarySufficientContextItem",
    "ParadoxContextItem",
    "PartitionContextItem",
    "PredictContextItem",
    "QuantifierContextItem",
    "RegressContextItem",
    "SocraticContextItem",
    "StatisticalSyllogismContextItem",
    "SteelmanContextItem",
    "StrawmanContextItem",
    "TestimonyContextItem",
    "ThoughtExperimentContextItem",
    "TransitivityContextItem",
]
