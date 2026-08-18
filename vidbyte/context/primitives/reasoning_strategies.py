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
