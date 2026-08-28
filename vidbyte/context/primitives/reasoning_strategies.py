"""FILE: vidbyte/context/primitives/reasoning_strategies.py

PURPOSE:
    Defines typed, bounded records for deduction, induction, abduction, analogy,
    causal chains, Bayesian updates, differential diagnosis, Fermi estimates,
    steelmanning, and falsification.
ROLE IN CODEBASE:
    Reasoning tools write these records, ContextManager renders them, and
    vidbyte.context.primitives re-exports the public strategy-specific classes.
ARCHITECTURE NOTE:
    Each frozen slotted dataclass owns its strategy's output shape; shared helpers
    format tuple sections and apply the managed-context size boundary.
FUNCTION INVENTORY:
    Ten strategy-specific ContextItem classes each render one reasoning record.
    _render_object_bullets() formats bounded mapping-based hypothesis sections.
COMMON MODIFICATION PATTERNS:
    Keep strategy fields in semantic order, preserve four-sentence prefaces, and
    update the corresponding reasoning tool when a record shape changes.
WHAT NOT TO DO IN THIS FILE:
    Do not execute reasoning strategies, score truth, or choose a model's next
    action; those responsibilities belong to the built-in tools and callers.
KNOWN EDGE CASES:
    Mapping fields may omit optional keys, tuple sections may be empty, and
    probability or confidence values are rendered as supplied by the caller.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/tree/main/vidbyte/context/primitives
TESTS:
    Existing reasoning-tool tests plus source compilation and package smoke gates
    cover imports, bounded rendering, and strategy record integration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _extend_section, _truncate_text

_HYPOTHESIS_KEYS = ("hypothesis", "explains", "simplicity", "assumptions_required")
_RULED_OUT_KEYS = ("candidate", "ruled_out_by")


def _render_object_bullets(
    items: tuple[Mapping[str, Any], ...], keys: tuple[str, ...]
) -> tuple[str, ...]:
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
        lines: list[str] = [
            "This note records a deductive chain for the model to inspect later. The premises and named inference rule show how the conclusion was derived. Use the soundness caveat to separate logical validity from confidence in the premises. Keep the conclusion tied to the stated premises rather than to later context.",
            "",
        ]
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
        lines: list[str] = [
            "This note records an inductive generalization from specific observations. The observations and pattern show what was seen before the broader claim was formed. Use the confidence, bias risk, and falsifying case to judge how far the claim can be trusted. Treat the generalization as provisional until its evidence survives that check.",
            "",
        ]
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
        lines: list[str] = [
            "This note records a comparison of competing explanations for observed evidence. The evidence and hypothesis summaries show why one explanation was selected over its rivals. Use the discriminating test to identify what could resolve any remaining ambiguity. The selected explanation remains a hypothesis until the test separates it from alternatives.",
            "",
        ]
        _extend_section(lines, "Evidence", self.evidence)
        _extend_section(
            lines,
            "Hypotheses",
            _render_object_bullets(self.hypotheses, _HYPOTHESIS_KEYS),
        )
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
            "This note records a transfer of structure from a familiar domain to a target domain. The mapped relations show what the comparison explains and where the two domains align. Use the breakdown point and weight classification before treating the analogy as decision evidence. This record marks comparison boundaries so similarity is not mistaken for identity.",
            "",
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
        lines = [
            "This note records a proposed cause-and-effect relationship with its explanatory mechanism. The mechanism and confounders show why the relationship may be causal or merely correlational. Use the intervention test to identify what observation could distinguish those possibilities. Keep correlation and causation distinct until the proposed test provides support.",
            "",
            f"Cause: {self.cause}",
        ]
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
            "This note records how evidence changes a stated belief. The prior, likelihoods, and posterior make the direction and size of the update explicit. Use the shift explanation to connect the numbers to the reasoning behind the belief revision. Read the probabilities as a recorded update, not as certainty beyond the supplied evidence.",
            "",
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
        lines: list[str] = [
            "This note records a candidate set narrowed by evidence and elimination. The ruled-out and remaining sections show which explanations still deserve attention. Use the next discriminator to choose the check that most efficiently separates the survivors. This keeps the search state explicit without declaring the surviving candidates correct.",
            "",
        ]
        _extend_section(lines, "Candidate Set", self.candidate_set)
        _extend_section(
            lines, "Ruled Out", _render_object_bullets(self.ruled_out, _RULED_OUT_KEYS)
        )
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
        lines = [
            "This note records an order-of-magnitude estimate built from smaller assumptions. The decomposition and arithmetic show how the point estimate was produced. Use the sanity band and anchor-risk note to judge whether the estimate is independently plausible. The result is a scale estimate, not a precise measurement.",
            "",
            f"Quantity: {self.quantity}",
        ]
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
        lines = [
            "This note records a position tested against its strongest credible opposition. The opposition and verdict show whether the original position still stands. Use the revision to carry any qualification or change into the next decision. This makes the revision traceable rather than silently changing the original position.",
            "",
            "### My Position",
            self.my_position,
        ]
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
        lines = [
            "This note records a claim together with a test designed to expose when it fails. The test design and riskiest prediction show what evidence would put the claim at risk. Use the status to distinguish a claim that survived a real test from one that is still untested. A surviving test raises confidence but does not prove the claim universally.",
            "",
            "### Claim",
            self.claim,
        ]
        lines.extend(("", "### Test Design", self.test_design))
        lines.extend(("", "### Riskiest Prediction", self.riskiest_prediction))
        lines.extend(("", f"Status: {self.status}"))
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "AbductionContextItem",
    "AnalogyContextItem",
    "BayesianUpdateContextItem",
    "CausalChainContextItem",
    "DeductionContextItem",
    "DifferentialDiagnosisContextItem",
    "FalsifyContextItem",
    "FermiEstimateContextItem",
    "InductionContextItem",
    "SteelmanContextItem",
]
