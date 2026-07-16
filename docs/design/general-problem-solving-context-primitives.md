# Design Doc: General Problem-Solving Context Primitives

**Status:** Approved
**Author:** Codex
**Created:** 2026-07-16
**Last Updated:** 2026-07-16

---

## 1. Overview

Add a domain-neutral family of nineteen structured context primitives for adversarial and reflective problem solving. The primitives make problem framing, unresolved objectives, assumptions, evidence quality, competing models, alternatives, tradeoffs, constraints, intervention risks, feedback gaps, stalled work, premature completion, and unresolved risk explicit in an agent's context window. They will follow the existing `ContextItem` contract as frozen, slotted dataclasses with stable `kind` values, optional managed `primitive_id` values, deterministic bounded `to_context_text()` rendering, and public exports from `vidbyte.context.primitives`, `vidbyte.context`, and `vidbyte`. The feature is intentionally primitive-only: it supplies structured state that callers, agents, future tools, and future context-window algorithms can use without introducing a software-engineering-only ontology or changing runtime behavior.

---

## 2. Goals & Non-Goals

### Goals

- Add all nineteen general problem-solving primitive types agreed in the design conversation.
- Describe reasoning and action in domain-neutral terms that work for research, strategy, diagnosis, planning, negotiation, policy analysis, creative work, everyday decision making, and software engineering.
- Group primitives by conceptual responsibility under `vidbyte/context/primitives/` rather than creating one oversized module.
- Follow the existing immutable `ContextItem` convention: `@dataclass(frozen=True, slots=True)`, `kind`, `title`, `metadata`, `primitive_id`, `primitive_frozen`, and `to_context_text()`.
- Give every new primitive consistent lifecycle fields: `status`, `severity`, `raised_by`, `owner`, and `resolution_condition`.
- Bound every rendered primitive with the existing `_truncate_text()` helper and a conservative default `max_chars=2000`.
- Preserve the distinction between domain content and window placement: callers continue to choose unmanaged `ContextManager.add()` or managed `ContextManager.upsert()`/`place_*()` behavior.
- Export every primitive from the three current public context surfaces.
- Document the new catalog and its intended general problem-solving semantics.
- Keep the implementation additive and free of new runtime or external dependencies.

### Non-Goals

- Do not add or modify context-window algorithms, including `ProblemSpaceSearchAlgorithm` and `ErrorCorrectionAlgorithm`.
- Do not add model-callable raise, respond, resolve, list, or upsert tools for these new types.
- Do not modify `ContextUpsertTool` to accept the new primitive kinds.
- Do not add an adversarial-agent orchestration flow or modify the separate untracked `docs/design/adversarial-agent.md` proposal.
- Do not add middleware that blocks actions or final answers when a primitive is open or blocking.
- Do not change `ContextManager` registry, placement, removal, freezing, rendering, or lifecycle semantics.
- Do not treat `primitive_frozen=True` as deletion protection; the current manager behavior remains unchanged.
- Do not add persistence, cross-run serialization, indexing, deduplication, eviction, or token-budget policy.
- Do not introduce enums or runtime validation for lifecycle strings, confidence values, repetition counts, or other content fields.
- Do not replace or deprecate existing `TaskContextItem`, `PlanContextItem`, `ProblemSpaceSearchContextItem`, `ErrorCorrectionContextItem`, `ReflexionContextItem`, or `TrajectoryCheckpointContextItem`.
- Do not add new automated tests or verification scripts under the no-tests workflow selected for this change.
- Do not modify the legacy `vidbyte.lib.dataclasses.context_items` compatibility shim; newer algorithm-specific primitives are already not uniformly exported there.

---

## 3. Background & Context

The SDK is a Python 3.11+ setuptools package with Pydantic 2 and `httpx` as its only runtime dependencies. Context primitives are plain Python dataclasses under `vidbyte/context/primitives/`. The structural `ContextItem` protocol requires `kind`, `title`, `metadata`, and `to_context_text()`. Concrete primitives additionally carry optional managed-registry fields and are rendered by `ContextManager` either as one-shot context items or as addressable, window-resident managed primitives.

The current primitive catalog is strong at representing inputs and runtime records: text, files, documents, environment state, memory, tasks, plans, progress, responses, tool calls, artifacts, checkpoints, broad problem-space exploration, and correction notices. It does not provide target-specific records for unresolved assumptions, evidence disputes, competing causal models, decisions, alternatives, tradeoffs, protected invariants, intervention risks, or completion gates. Today those concepts must be placed into a generic `TextContextItem`, losing stable field semantics and making later tools or algorithms rely on prose parsing.

The existing `ProblemSpaceSearchContextItem` and `ErrorCorrectionContextItem` remain complementary. Problem-space search is an algorithm-authored periodic summary of blind spots; the proposed primitives are individually addressable problem-solving records. Error correction is an authoritative aggregate notice; the proposed assumption, evidence, model, and invariant items represent the underlying unresolved concerns separately. `TaskContextItem` and `PlanContextItem` continue to describe work to perform; objective and completion primitives describe whether the work is correctly framed and sufficiently demonstrated.

The repository conventions relevant to this feature are:

- Primitive modules group related dataclasses and re-export public types from `vidbyte/context/primitives/__init__.py`.
- Public context types are also exported from `vidbyte/context/__init__.py` and the root `vidbyte/__init__.py`.
- Primitive dataclasses use `@dataclass(frozen=True, slots=True)` and plain string lifecycle/status fields rather than a mandatory enum hierarchy.
- Tuple fields express repeated structured text and render as deterministic bullet lists.
- `_truncate_text()` in `vidbyte/context/primitives/base.py` bounds model-visible text without mutating the stored value.
- The context layer owns structured meaning while `ContextManager` owns collection, placement, and compatibility conversion.
- The current checkout is a dirty `feat/context-minimal-fanout-trace` branch with unrelated untracked user documents and nested worktrees. Phase 2 creates only this design document. After approval, implementation must begin from updated `main` in a new isolated worktree and must not clean, modify, or reuse unrelated untracked files.

---

## 4. Requirements

### Functional Requirements

1. Create nineteen new public `ContextItem` dataclasses:
   1. `ProblemFrameContextItem`
   2. `ObjectiveGapContextItem`
   3. `ObjectiveConflictContextItem`
   4. `BoundaryContextItem`
   5. `AmbiguityContextItem`
   6. `PerspectiveGapContextItem`
   7. `AssumptionChallengeContextItem`
   8. `ModelChallengeContextItem`
   9. `EvidenceChallengeContextItem`
   10. `DecisionChallengeContextItem`
   11. `AlternativeChallengeContextItem`
   12. `TradeoffContextItem`
   13. `InvariantContextItem`
   14. `DependencyContextItem`
   15. `InterventionRiskContextItem`
   16. `FeedbackGapContextItem`
   17. `ProcessStallContextItem`
   18. `CompletionGateContextItem`
   19. `RiskEscalationContextItem`.
2. Every new type must be a frozen, slotted dataclass satisfying the existing structural `ContextItem` protocol.
3. Every new type must include `status: str = "open"`, `severity: str = "concern"`, `raised_by: str | None = None`, `owner: str | None = None`, and `resolution_condition: str | None = None`.
4. Every new type must include `title`, `max_chars=2000`, `metadata`, a stable snake-case `kind`, `primitive_id`, and `primitive_frozen` fields following current field-order conventions.
5. Every `to_context_text()` signature must remain on one line and be followed immediately by a concise comment explaining its rendering responsibility.
6. Every rendering must begin with status and severity, include raised-by and owner lines only when present, render domain-specific fields in deterministic order, render repeated values as bullets, include the resolution condition when present, and call `_truncate_text()` once on the complete rendered text.
7. Empty optional strings and empty tuples must omit their optional section instead of rendering placeholder prose, except required primary subject fields, which must always render.
8. `ProblemFrameContextItem` must represent a current framing, underlying need, affected parties, a suspected proxy, and alternative framings.
9. `ObjectiveGapContextItem` must represent an objective, desired outcome, unresolved parts, completion condition, and next evidence needed.
10. `ObjectiveConflictContextItem` must represent multiple objectives, the conflict among them, affected parties, and the decision needed to resolve precedence.
11. `BoundaryContextItem` must represent a boundary type, the boundary itself, a challenged action, non-goals, required authority, and escalation path.
12. `AmbiguityContextItem` must represent an ambiguous term or concept, its context, plausible interpretations, their consequences, and the clarification needed.
13. `PerspectiveGapContextItem` must represent a subject, missing perspectives, affected parties, likely blind spots, and value judgments that may be presented as facts.
14. `AssumptionChallengeContextItem` must represent an assumption, its basis, optional numeric confidence, current evidence, a falsifier, and a validation method.
15. `ModelChallengeContextItem` must represent a current mental or causal model, questionable relationships, competing models, and distinguishing observations.
16. `EvidenceChallengeContextItem` must represent a claim, supporting evidence, counterevidence, provenance issues, freshness concerns, bias risks, missing evidence, and an observation-versus-inference gap.
17. `DecisionChallengeContextItem` must represent a decision, rationale, uncertainties, optional numeric confidence, failure modes, and a condition for reopening the decision.
18. `AlternativeChallengeContextItem` must represent a target decision, a competitive alternative, its mechanism, why it is competitive, the current rejection rationale, and a counterexample.
19. `TradeoffContextItem` must represent a choice, benefits, costs, affected parties, externalities, opportunity costs, and second-order effects.
20. `InvariantContextItem` must represent a protected invariant, its scope, observed state, violation evidence, consequence, and check method.
21. `DependencyContextItem` must represent an objective or plan, a dependency, required condition, dependency owner, fragility, and fallback.
22. `InterventionRiskContextItem` must represent an intervention, intended effect, reversible effects, irreversible effects, uncertainties, containment, and recovery.
23. `FeedbackGapContextItem` must represent an intervention, expected outcome, observable signals, measurement method, observation cadence, and response threshold.
24. `ProcessStallContextItem` must represent an activity, repeated pattern, repetition count, last new information, observed drift, and escape action.
25. `CompletionGateContextItem` must represent a claimed result, desired outcome, completion condition, current evidence, and missing validation.
26. `RiskEscalationContextItem` must represent a risk, impact, mitigations, authorized acceptor, expiration/review point, and escalation trigger; the shared `owner` field is the risk owner.
27. Confidence values must render with two decimal places when present and omit the confidence line when absent. This feature does not clamp or validate their range.
28. Repetition counts must render as provided. This feature does not reject zero or negative values.
29. All nineteen types must be importable from `vidbyte.context.primitives`, `vidbyte.context`, and `vidbyte`.
30. `ContextManager.add()`, `ContextManager.upsert()`, `place_after_system_prompt()`, and `place_after_tools()` must accept the new dataclasses without manager-specific branches because they satisfy the structural protocol.
31. `ContextManager.to_context()` must continue to convert an unmanaged new primitive through its existing generic fallback into a `ContextArtifact` using the primitive's `title`, rendered text, `kind`, and `metadata`.
32. Managed new primitives must render through the existing `render_primitives_zone()` path without special handling.
33. Update the context README with a domain-neutral example showing at least one epistemic primitive and one completion primitive.
34. Update the context-primitives contributor skill with the new module layout, import examples, and the distinction between general problem-solving primitives and algorithm-authored reasoning primitives.

### Non-Functional Requirements

- **Performance:** Each primitive render must be linear in the number and size of its own fields. No registry scans, network calls, filesystem access, model calls, or global state are allowed.
- **Context size:** Every new primitive defaults to a maximum 2,000-character rendered representation through `_truncate_text()`; callers may override `max_chars` consistently with existing primitives.
- **Scalability:** The feature adds independent value objects only. It must not introduce shared mutable state or per-class registries.
- **Security:** Renderers treat all content as opaque text. They must not execute, interpret, load, or follow instructions contained in primitive fields.
- **Reliability:** Rendering must remain deterministic for a fixed dataclass value and must not fail merely because optional fields are empty.
- **Compatibility:** The change is additive. Existing constructors, imports, manager behavior, algorithms, tools, and serialized application data remain unchanged.
- **Observability:** N/A - value objects do not emit logs, metrics, or traces. Their `metadata` field remains available for caller-owned provenance and iteration data.
- **Validation:** N/A - the existing primitive layer generally accepts content as supplied. Lifecycle strings and numeric fields remain descriptive rather than runtime-enforced.
- **Dependencies:** No new package or service dependency is permitted.
- **Code style:** New modules must include the repository's context protocol header. Every method signature must be one line with the required immediate intent comment.

---

## 5. High-Level Design

The feature adds five primitive modules organized around a general problem-solving lifecycle. `framing.py` describes what problem is being solved and for whom. `epistemics.py` records assumptions, models, and evidence challenges. `decisions.py` records decisions, alternatives, and tradeoffs. `execution.py` records invariants, dependencies, intervention risks, and feedback gaps. `closure.py` records stalled processes, completion gates, and unresolved risk escalation. This preserves the package's one-module-per-conceptual-group convention and avoids mixing caller-authored problem records into the existing algorithm-specific `reasoning.py` module.

Each dataclass owns only structured content and deterministic text rendering. It does not know whether it was created by a developer, a primary worker, an adversarial reviewer, a future tool, or a future runtime algorithm. It can be supplied as an unmanaged `context_item` or stored as a managed primitive with an addressable ID and caller-selected placement. Existing `ContextManager` behavior performs both paths without modification.

All types repeat the small lifecycle envelope rather than introducing inheritance or a nested state object. Repetition keeps construction flat and consistent with existing primitive APIs, avoids frozen/slotted dataclass inheritance complexity, and lets each type remain independently understandable. Status and severity use strings, matching current flexible context records; documented conventional values are advisory rather than validated.

```text
General problem-solving concern
              |
              v
  frozen ContextItem dataclass
              |
       to_context_text()
              |
       _truncate_text(...)
              |
     +--------+---------+
     |                  |
ContextManager.add   ContextManager.upsert/place_*
     |                  |
BaseContext artifact   managed primitives zone
     |                  |
     +--------+---------+
              |
        model-visible context
```

No algorithm or tool is automatically attached. This is deliberate: primitives are the shared structured currency, while trigger, authorship, authority, and enforcement require separate future designs.

---

## 6. Detailed Design

### 6.1 Shared Primitive Contract And Rendering Rules

**File(s):** `vidbyte/context/primitives/framing.py`, `vidbyte/context/primitives/epistemics.py`, `vidbyte/context/primitives/decisions.py`, `vidbyte/context/primitives/execution.py`, `vidbyte/context/primitives/closure.py`
**Type:** New files

#### What it does

Defines a consistent lifecycle and rendering contract repeated by all nineteen primitives without adding a base dataclass or changing the structural `ContextItem` protocol.

#### Interface / API

Every concrete class appends this common field tail after its domain-specific fields:

```python
status: str = "open"
severity: str = "concern"
raised_by: str | None = None
owner: str | None = None
resolution_condition: str | None = None
title: str = "<type-specific title>"
max_chars: int = 2000
metadata: Mapping[str, Any] = field(default_factory=dict)
kind: str = "<stable snake-case kind>"
primitive_id: str | None = None
primitive_frozen: bool = False

def to_context_text(self) -> str:
    # Renders this problem-solving record in deterministic order, bounded by max_chars.
    ...
```

Documented conventional lifecycle values:

```text
status: open | acknowledged | investigating | resolved | invalidated | accepted_risk
severity: observation | concern | blocking | critical
```

These remain plain strings and are not rejected when applications use domain-specific extensions.

#### Logic / Algorithm

1. Start a local `lines` list with `Status: <status>` and `Severity: <severity>`.
2. Append `Raised by:` and `Owner:` only when their values are not `None` or empty.
3. Append required domain-specific subject lines or sections in the order specified for the concrete type.
4. Append optional scalar sections only when present.
5. Render tuple fields as titled bullet sections using `_extend_section()`.
6. Append `Resolution Condition` only when present.
7. Join with newline separators.
8. Return `_truncate_text(rendered, self.max_chars)`.

#### Edge Cases & Error Handling

- `max_chars <= 0` preserves the existing `_truncate_text()` pass-through behavior.
- Empty tuple fields are omitted by `_extend_section()`.
- Required strings are rendered exactly as supplied, including empty strings; the primitive layer does not introduce construction-time validation.
- Metadata remains an arbitrary `Mapping[str, Any>` and is not rendered automatically.
- Frozen dataclasses prevent attribute assignment but do not guarantee recursive immutability of caller-supplied mapping values.
- `primitive_frozen` retains its current manager meaning: an existing frozen primitive cannot be overwritten, but this feature does not change removal behavior.

### 6.2 Framing And Objective Primitives

**File(s):** `vidbyte/context/primitives/framing.py`
**Type:** New file

#### What it does

Defines six primitives for challenging the framing, objectives, boundaries, interpretations, and represented perspectives of a problem.

#### Interface / API

All classes include the common field tail from Section 6.1.

```python
@dataclass(frozen=True, slots=True)
class ProblemFrameContextItem:
    current_frame: str
    underlying_need: str
    affected_parties: tuple[str, ...] = ()
    suspected_proxy: str | None = None
    alternative_frames: tuple[str, ...] = ()
    # common tail; title="Problem Frame", kind="problem_frame"

@dataclass(frozen=True, slots=True)
class ObjectiveGapContextItem:
    objective: str
    desired_outcome: str
    unresolved_parts: tuple[str, ...] = ()
    completion_condition: str | None = None
    next_evidence: tuple[str, ...] = ()
    # common tail; title="Objective Gap", kind="objective_gap"

@dataclass(frozen=True, slots=True)
class ObjectiveConflictContextItem:
    objectives: tuple[str, ...]
    conflict: str
    affected_parties: tuple[str, ...] = ()
    decision_needed: str | None = None
    # common tail; title="Objective Conflict", kind="objective_conflict"

@dataclass(frozen=True, slots=True)
class BoundaryContextItem:
    boundary_type: str
    boundary: str
    challenged_action: str | None = None
    non_goals: tuple[str, ...] = ()
    authority_required: str | None = None
    escalation_path: str | None = None
    # common tail; title="Boundary", kind="boundary"

@dataclass(frozen=True, slots=True)
class AmbiguityContextItem:
    term: str
    context: str
    interpretations: tuple[str, ...] = ()
    consequences: tuple[str, ...] = ()
    clarification_needed: str | None = None
    # common tail; title="Ambiguity", kind="ambiguity"

@dataclass(frozen=True, slots=True)
class PerspectiveGapContextItem:
    subject: str
    missing_perspectives: tuple[str, ...] = ()
    affected_parties: tuple[str, ...] = ()
    likely_blind_spots: tuple[str, ...] = ()
    value_judgments: tuple[str, ...] = ()
    # common tail; title="Perspective Gap", kind="perspective_gap"
```

#### Logic / Algorithm

1. Render the shared lifecycle header.
2. Render each primitive's primary frame, objective, conflict, boundary, ambiguous term, or subject first.
3. Render the underlying need, desired outcome, contextual explanation, or conflict immediately after the primary subject.
4. Render parties, alternatives, unresolved parts, interpretations, consequences, non-goals, blind spots, and value judgments as named bullet sections.
5. Render proxy, completion, authority, clarification, decision-needed, and escalation scalars only when supplied.
6. Append the common resolution condition and truncate.

#### Edge Cases & Error Handling

- An empty `objectives` tuple renders an empty Objectives section; no minimum count is enforced.
- A `BoundaryContextItem` does not itself enforce scope or authority.
- A `PerspectiveGapContextItem` records potentially missing perspectives without claiming those perspectives are correct.
- Objective completion conditions are descriptive; they do not invoke validators or automatically change status.

### 6.3 Epistemic Primitives

**File(s):** `vidbyte/context/primitives/epistemics.py`
**Type:** New file

#### What it does

Defines three primitives for challenging assumptions, mental or causal models, and the evidence supporting a claim.

#### Interface / API

All classes include the common field tail from Section 6.1.

```python
@dataclass(frozen=True, slots=True)
class AssumptionChallengeContextItem:
    assumption: str
    basis: str | None = None
    confidence: float | None = None
    evidence: tuple[str, ...] = ()
    falsifier: str | None = None
    validation_method: str | None = None
    # common tail; title="Assumption Challenge", kind="assumption_challenge"

@dataclass(frozen=True, slots=True)
class ModelChallengeContextItem:
    model: str
    questionable_relationships: tuple[str, ...] = ()
    competing_models: tuple[str, ...] = ()
    distinguishing_observations: tuple[str, ...] = ()
    # common tail; title="Model Challenge", kind="model_challenge"

@dataclass(frozen=True, slots=True)
class EvidenceChallengeContextItem:
    claim: str
    supporting_evidence: tuple[str, ...] = ()
    counterevidence: tuple[str, ...] = ()
    provenance_issues: tuple[str, ...] = ()
    freshness_concerns: tuple[str, ...] = ()
    bias_risks: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    observation_inference_gap: str | None = None
    # common tail; title="Evidence Challenge", kind="evidence_challenge"
```

#### Logic / Algorithm

1. Render the shared lifecycle header.
2. Render the assumption, model, or claim as the primary subject.
3. For assumptions, render basis, confidence, evidence, falsifier, and validation method.
4. For models, render questionable relationships, competing models, and observations that distinguish them.
5. For evidence challenges, render supporting and counterevidence before provenance, freshness, bias, and missing-evidence sections so the epistemic dispute remains balanced.
6. Render observation-versus-inference text only when present.
7. Append the common resolution condition and truncate.

#### Edge Cases & Error Handling

- `confidence` is rendered to two decimal places but is not clamped to `[0.0, 1.0]`.
- Evidence entries are opaque strings and may contain document references, measurements, calculations, interviews, observations, tool results, or other domain evidence.
- An empty counterevidence tuple means no counterevidence was recorded, not that none exists.
- The renderer does not decide which source is authoritative or whether a model is true.

### 6.4 Decision Primitives

**File(s):** `vidbyte/context/primitives/decisions.py`
**Type:** New file

#### What it does

Defines three primitives for challenging a chosen decision, preserving a competitive alternative, and making tradeoffs and downstream effects explicit.

#### Interface / API

All classes include the common field tail from Section 6.1.

```python
@dataclass(frozen=True, slots=True)
class DecisionChallengeContextItem:
    decision: str
    rationale: str | None = None
    uncertainties: tuple[str, ...] = ()
    confidence: float | None = None
    failure_modes: tuple[str, ...] = ()
    reopen_condition: str | None = None
    # common tail; title="Decision Challenge", kind="decision_challenge"

@dataclass(frozen=True, slots=True)
class AlternativeChallengeContextItem:
    target_decision: str
    alternative: str
    mechanism: str | None = None
    why_competitive: str | None = None
    rejection_rationale: str | None = None
    counterexample: str | None = None
    # common tail; title="Alternative Challenge", kind="alternative_challenge"

@dataclass(frozen=True, slots=True)
class TradeoffContextItem:
    choice: str
    benefits: tuple[str, ...] = ()
    costs: tuple[str, ...] = ()
    affected_parties: tuple[str, ...] = ()
    externalities: tuple[str, ...] = ()
    opportunity_costs: tuple[str, ...] = ()
    second_order_effects: tuple[str, ...] = ()
    # common tail; title="Tradeoff", kind="tradeoff"
```

#### Logic / Algorithm

1. Render the shared lifecycle header.
2. Render the decision, target decision plus alternative, or choice first.
3. Render rationale and confidence before uncertainty and failure-mode bullets.
4. Render alternative mechanism, competitiveness, rejection rationale, and counterexample in that order.
5. Render tradeoff benefits and costs before affected parties, externalities, opportunity costs, and second-order effects.
6. Render reopen and resolution conditions independently when both are present; reopening describes the decision, while resolution describes the challenge record.
7. Truncate the complete text.

#### Edge Cases & Error Handling

- Confidence has the same descriptive, non-validating behavior as the assumption primitive.
- A missing rejection rationale remains visibly absent rather than being synthesized.
- `TradeoffContextItem` does not require benefits and costs to be balanced or quantified.
- A counterexample is recorded as a proposed falsifier and is not automatically executed or evaluated.

### 6.5 Execution And Feedback Primitives

**File(s):** `vidbyte/context/primitives/execution.py`
**Type:** New file

#### What it does

Defines four primitives for protected constraints, fragile dependencies, potentially harmful interventions, and missing feedback loops.

#### Interface / API

All classes include the common field tail from Section 6.1.

```python
@dataclass(frozen=True, slots=True)
class InvariantContextItem:
    invariant: str
    scope: str | None = None
    observed_state: str | None = None
    violation_evidence: tuple[str, ...] = ()
    consequence: str | None = None
    check_method: str | None = None
    # common tail; title="Invariant", kind="invariant"

@dataclass(frozen=True, slots=True)
class DependencyContextItem:
    objective_or_plan: str
    dependency: str
    required_condition: str | None = None
    dependency_owner: str | None = None
    fragility: str | None = None
    fallback: str | None = None
    # common tail; title="Dependency", kind="dependency"

@dataclass(frozen=True, slots=True)
class InterventionRiskContextItem:
    intervention: str
    intended_effect: str | None = None
    reversible_effects: tuple[str, ...] = ()
    irreversible_effects: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    containment: str | None = None
    recovery: str | None = None
    # common tail; title="Intervention Risk", kind="intervention_risk"

@dataclass(frozen=True, slots=True)
class FeedbackGapContextItem:
    intervention: str
    expected_outcome: str
    observable_signals: tuple[str, ...] = ()
    measurement_method: str | None = None
    observation_cadence: str | None = None
    response_threshold: str | None = None
    # common tail; title="Feedback Gap", kind="feedback_gap"
```

#### Logic / Algorithm

1. Render the shared lifecycle header.
2. Render the invariant, objective/plan plus dependency, or intervention first.
3. Keep observed state distinct from violation evidence so observation is not silently promoted into a conclusion.
4. Render reversible and irreversible intervention effects in separate sections.
5. Render feedback signals before measurement method, cadence, and response threshold.
6. Append the common resolution condition and truncate.

#### Edge Cases & Error Handling

- `InvariantContextItem` is model-visible information and does not enforce the invariant.
- Shared `owner` identifies who owns resolving the primitive; `dependency_owner` identifies who or what owns the dependency itself.
- Recovery and fallback are descriptive and are not invoked by the context layer.
- The feature does not interpret units, deadlines, probabilities, or thresholds.

### 6.6 Closure And Escalation Primitives

**File(s):** `vidbyte/context/primitives/closure.py`
**Type:** New file

#### What it does

Defines three primitives for detecting unproductive repetition or goal drift, gating premature completion, and making unresolved risk ownership and escalation explicit.

#### Interface / API

All classes include the common field tail from Section 6.1.

```python
@dataclass(frozen=True, slots=True)
class ProcessStallContextItem:
    activity: str
    repeated_pattern: str
    repetition_count: int = 0
    last_new_information: str | None = None
    observed_drift: str | None = None
    escape_action: str | None = None
    # common tail; title="Process Stall", kind="process_stall"

@dataclass(frozen=True, slots=True)
class CompletionGateContextItem:
    claimed_result: str
    desired_outcome: str
    completion_condition: str | None = None
    current_evidence: tuple[str, ...] = ()
    missing_validation: tuple[str, ...] = ()
    # common tail; title="Completion Gate", kind="completion_gate"

@dataclass(frozen=True, slots=True)
class RiskEscalationContextItem:
    risk: str
    impact: str | None = None
    mitigations: tuple[str, ...] = ()
    authorized_acceptor: str | None = None
    expires_or_review: str | None = None
    escalation_trigger: str | None = None
    # common tail; title="Risk Escalation", kind="risk_escalation"
```

#### Logic / Algorithm

1. Render the shared lifecycle header.
2. Render activity and repeated pattern before count, last new information, drift, and escape action.
3. Render claimed result and desired outcome next to each other before completion condition, current evidence, and missing validation.
4. Render risk and impact before mitigations, owner, authorized acceptor, review point, and escalation trigger.
5. Render accepted risk through the shared `status="accepted_risk"` convention; do not infer acceptance merely because an acceptor is named.
6. Append the common resolution condition and truncate.

#### Edge Cases & Error Handling

- Repetition count is descriptive and may be zero or negative; no numeric validation is added.
- A completion gate does not block `isDone`, final responses, or agent termination without a separate future enforcement design.
- An authorized acceptor is a recorded assertion, not authenticated authority.
- Expiration and review points are strings so domains may use iterations, dates, milestones, observations, or other review triggers.

### 6.7 Primitive Package Exports

**File(s):** `vidbyte/context/primitives/__init__.py`
**Type:** Modified

#### What it does

Imports all nineteen classes from their five modules and adds them to `__all__` so callers can use the canonical primitive package.

#### Interface / API

```python
from vidbyte.context.primitives import (
    AlternativeChallengeContextItem,
    AmbiguityContextItem,
    AssumptionChallengeContextItem,
    BoundaryContextItem,
    CompletionGateContextItem,
    DecisionChallengeContextItem,
    DependencyContextItem,
    EvidenceChallengeContextItem,
    FeedbackGapContextItem,
    InterventionRiskContextItem,
    InvariantContextItem,
    ModelChallengeContextItem,
    ObjectiveConflictContextItem,
    ObjectiveGapContextItem,
    PerspectiveGapContextItem,
    ProblemFrameContextItem,
    ProcessStallContextItem,
    RiskEscalationContextItem,
    TradeoffContextItem,
)
```

#### Logic / Algorithm

1. Import each class from the module that owns it.
2. Add every name to the alphabetized public `__all__` list.
3. Update the module protocol header to name the five new groups.

#### Edge Cases & Error Handling

- Import order must not create cycles; new modules depend only on standard-library types and primitive base helpers.
- Existing exports remain unchanged.

### 6.8 Context And Root Public Exports

**File(s):** `vidbyte/context/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Re-exports all nineteen classes from the public context namespace and SDK root, matching the current public treatment of core context primitive types.

#### Interface / API

```python
from vidbyte import AssumptionChallengeContextItem, CompletionGateContextItem
from vidbyte.context import ProblemFrameContextItem, EvidenceChallengeContextItem
```

#### Logic / Algorithm

1. Add all new names to the existing grouped import from `vidbyte.context.primitives` in `vidbyte/context/__init__.py`.
2. Add all new names to `vidbyte.context.__all__`.
3. Add all new names to the existing grouped import from `vidbyte.context` in `vidbyte/__init__.py`.
4. Add all new names to the root `__all__` list.
5. Preserve existing names and ordering conventions.

#### Edge Cases & Error Handling

- Root namespace growth is deliberate because the request is for first-class SDK primitives.
- The legacy `vidbyte.lib.dataclasses.context_items` shim remains unchanged and is not presented as the canonical import path.

### 6.9 Documentation And Contributor Guidance

**File(s):** `vidbyte/context/README.md`, `vidbyte/context/primitives/README.md`, `skills/vidbyte-sdk/context-primitives.md`
**Type:** Modified

#### What it does

Documents the catalog as general problem-solving state rather than coding-specific review records and updates the contributor module map.

#### Interface / API

The context README will include a compact example equivalent to:

```python
from vidbyte import AssumptionChallengeContextItem, CompletionGateContextItem, ContextManager

context = ContextManager()
context.place_after_tools(
    AssumptionChallengeContextItem(
        assumption="Demand will remain constant during the pilot.",
        falsifier="Observed demand changes materially during the pilot.",
        validation_method="Compare weekly demand measurements.",
        resolution_condition="Two stable measurement periods are observed.",
    )
)
context.place_after_system_prompt(
    CompletionGateContextItem(
        claimed_result="The intervention worked.",
        desired_outcome="Wait times decreased without reducing service quality.",
        missing_validation=("Compare against baseline", "Review quality measures"),
        severity="blocking",
    )
)
```

#### Logic / Algorithm

1. Explain that the new primitives describe problem-solving structures across domains.
2. State that a primitive records a concern but does not automatically enforce, investigate, or resolve it.
3. Explain how managed IDs and placement can make a concern persistent and prominent.
4. Add the five new modules and all nineteen types to the contributor skill's package map.
5. Distinguish caller/worker-authored problem-solving primitives from algorithm-authored `ProblemSpaceSearchContextItem` and `ErrorCorrectionContextItem`.
6. Add the five new modules to the primitives folder README's file index, which is present on the current `main` branch.

#### Edge Cases & Error Handling

- Documentation must not imply that status transitions are automatic.
- Documentation must not claim that `blocking` severity deterministically blocks an agent.
- Examples must remain domain-neutral and must not require a provider or network call.

### 6.10 Existing Verification Without New Tests

**File(s):** N/A - no verification script or test file will be created.
**Type:** N/A - command-only verification

#### What it does

Uses compilation plus direct import, rendering, structural-protocol, unmanaged-conversion, and managed-rendering smoke checks to verify the additive value-object change under the selected no-tests workflow.

#### Interface / API

```powershell
python -m compileall vidbyte
python -c "from vidbyte import AssumptionChallengeContextItem, CompletionGateContextItem, ContextManager; from vidbyte.context.primitives import ContextItem; a=AssumptionChallengeContextItem(assumption='A', primitive_id='assumption:a'); g=CompletionGateContextItem(claimed_result='R', desired_outcome='O'); m=ContextManager([g]); m.upsert(a); assert isinstance(a, ContextItem); assert 'Assumption' in m.render_primitives_zone(); assert any(x.artifact_type == 'completion_gate' for x in m.to_context().artifacts)"
```

#### Logic / Algorithm

1. Compile the complete package.
2. Import representative types from the root and primitive package.
3. Confirm structural `ContextItem` compatibility.
4. Confirm a managed primitive renders through the registry zone.
5. Confirm an unmanaged primitive converts through the generic `ContextArtifact` fallback with its `kind` as `artifact_type`.
6. During implementation self-review, instantiate and render all nineteen classes once to catch missing required arguments or import/export omissions.

#### Edge Cases & Error Handling

- No claim will be made that automated tests passed because no new test coverage is included in this workflow.
- If compilation or the smoke command fails, implementation is incomplete and must not proceed to PR creation.
- `ruff` and `mypy` are not configured in `pyproject.toml`; they are not claimed as gates.

---

## 7. Data Model Changes

### 7.1 General Problem-Solving Context Types

**Change type:** New

The feature adds nineteen in-memory Python dataclasses with the exact domain fields in Sections 6.2 through 6.6 and the repeated lifecycle tail in Section 6.1. They implement the existing structural `ContextItem` protocol and introduce no database, wire, session, or persistent schema.

```python
ProblemFrameContextItem
ObjectiveGapContextItem
ObjectiveConflictContextItem
BoundaryContextItem
AmbiguityContextItem
PerspectiveGapContextItem
AssumptionChallengeContextItem
ModelChallengeContextItem
EvidenceChallengeContextItem
DecisionChallengeContextItem
AlternativeChallengeContextItem
TradeoffContextItem
InvariantContextItem
DependencyContextItem
InterventionRiskContextItem
FeedbackGapContextItem
ProcessStallContextItem
CompletionGateContextItem
RiskEscalationContextItem
```

**Migration strategy:**

- Forward migration: N/A - the dataclasses and exports are additive. Applications opt in by constructing them.
- Rollback plan: remove the new modules, exports, and documentation. Existing persisted data is unaffected because no serializer or store is changed.

### 7.2 Existing Context Types And Manager State

**Change type:** N/A - unchanged

`ContextItem`, `ContextManager`, `BaseContext`, `_registry`, `_placements`, and existing primitives retain their current fields and behavior.

**Migration strategy:**

- Forward migration: N/A.
- Rollback plan: N/A.

---

## 8. API Changes

### 8.1 Python Primitive Imports

**Change type:** New

The API adds nineteen importable Python classes at three surfaces:

```python
from vidbyte.context.primitives import ProblemFrameContextItem
from vidbyte.context import EvidenceChallengeContextItem
from vidbyte import CompletionGateContextItem
```

Construction uses the dataclass fields documented in Section 6. No new client, registry, endpoint, or factory is introduced.

**Error cases:**

| Error | Condition |
|-------|-----------|
| `TypeError` | A required dataclass field is omitted or an unknown keyword is supplied. |
| `ValueError` from `ContextManager.upsert()` | A managed item has no non-empty `primitive_id` or attempts to overwrite an existing frozen primitive. |

### 8.2 HTTP Or External Service Endpoints

**Change type:** N/A - the SDK feature exposes Python value objects only.

**Request:**

N/A - no endpoint.

**Response:**

N/A - no endpoint.

**Error cases:**

N/A - no endpoint.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/general-problem-solving-context-primitives.md` | Approved source-of-truth design document |
| CREATE | `vidbyte/context/primitives/framing.py` | Problem framing, objectives, boundaries, ambiguity, and perspective primitives |
| CREATE | `vidbyte/context/primitives/epistemics.py` | Assumption, model, and evidence challenge primitives |
| CREATE | `vidbyte/context/primitives/decisions.py` | Decision, alternative, and tradeoff primitives |
| CREATE | `vidbyte/context/primitives/execution.py` | Invariant, dependency, intervention-risk, and feedback-gap primitives |
| CREATE | `vidbyte/context/primitives/closure.py` | Process-stall, completion-gate, and risk-escalation primitives |
| MODIFY | `vidbyte/context/primitives/__init__.py` | Export all nineteen primitives from the canonical package |
| MODIFY | `vidbyte/context/__init__.py` | Export all nineteen primitives from the context namespace |
| MODIFY | `vidbyte/__init__.py` | Export all nineteen primitives from the SDK root |
| MODIFY | `vidbyte/context/README.md` | Document domain-neutral problem-solving usage and limitations |
| MODIFY | `vidbyte/context/primitives/README.md` | Keep the primitives folder file index synchronized with the five new modules |
| MODIFY | `skills/vidbyte-sdk/context-primitives.md` | Update contributor module map and primitive guidance |

No files will be deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | Python 3.11+ | Dataclasses, mappings, and typing | None beyond the existing package baseline |
| Existing primitive helpers | Repository implementation | Bullet-section rendering and bounded text | Low; reused without modification |
| External services | N/A | No external service is used | None |

---

## 11. Rollout & Deployment

- No feature flag is required because the change is additive and inert until a caller constructs a new primitive.
- After explicit approval, create `feat/general-problem-solving-context-primitives` from updated `main` in a clean isolated worktree.
- Commit this design document first in the new branch before implementation code.
- Implement the five modules, then package exports, then documentation.
- Run compilation and the direct smoke verification from Section 6.10.
- Perform the required prosecution/defense refinement pass against the original request and this design before opening a PR.
- Push the branch and open a draft PR into `main`.
- No database, service, or deployment ordering is involved.
- Rollback consists of reverting the additive commits. Existing agents and context data remain compatible.

---

## 12. Open Questions

- [x] Approval confirmed that “add them” means the full nineteen-type revised catalog, not only the ten-type suggested initial subset.
- [x] Approval confirmed that all nineteen types should be exported from the SDK root.
- [ ] Should lifecycle strings eventually become enums with construction-time validation? Proposed answer for this change: no; retain flexible strings and consider enums only alongside lifecycle tools or enforcement.
- [ ] Should future model-callable tools support type-specific creation and resolution? Proposed answer: yes as a separate design, after the primitive API has stabilized.
- [ ] Should `primitive_frozen` eventually prevent removal or support resolver authority? Proposed answer: potentially, but only in a separate `ContextManager` lifecycle/authority design because changing removal semantics is broader and potentially breaking.
- [ ] Should the generic `ContextUpsertTool` eventually accept these kinds? Proposed answer: not directly; type-specific fields are too rich for its current single-content-string contract.

---

## 13. Alternatives Considered

### Alternative 1: Add Only The Ten Suggested Initial Types

- What: Implement only problem frame, objective gap, assumption, evidence, model, alternative, decision, invariant, intervention risk, and completion gate.
- Why rejected: The user's final instruction refers to the revised set as a whole. The omitted types capture materially distinct structures—conflicting objectives, ambiguity, perspective gaps, tradeoffs, dependencies, feedback, process stalls, and explicit risk escalation—that would otherwise immediately fall back to generic text.

### Alternative 2: One Generic `AdversarialFindingContextItem`

- What: Add one dataclass with a `finding_type` discriminator and generic subject/evidence/action fields.
- Why rejected: It would minimize source code but reproduce the current generic-text problem at a slightly higher level. Type-specific consumers would need discriminator checks and loosely interpreted payload fields, and model/tool schemas could not express which information belongs to an assumption versus a tradeoff or completion gate.

### Alternative 3: One New Module Containing All Nineteen Types

- What: Put the entire catalog in `vidbyte/context/primitives/problem_solving.py`.
- Why rejected: Nineteen dataclasses plus rendering logic would create an oversized module and conflict with the package's conceptual grouping convention. Five focused modules make the catalog easier to navigate and evolve.

### Alternative 4: Dataclass Inheritance From A Shared Adversarial Base

- What: Define a frozen/slotted base dataclass containing lifecycle and identity fields, then subclass it for each primitive.
- Why rejected: Required domain fields would interact awkwardly with inherited default fields, frozen/slotted dataclass inheritance adds complexity, and current primitives use structural conformance rather than a concrete base hierarchy. Repeating a small field tail is more explicit and consistent with the repository.

### Alternative 5: Nested Shared Lifecycle State

- What: Store status, severity, ownership, and resolution inside a `FindingState` value object used by every primitive.
- Why rejected: It would reduce repeated declarations but make common construction and later tool schemas unnecessarily nested. Flat fields are easier for developers and models to author.

### Alternative 6: Extend Existing Task And Reasoning Primitives

- What: Add all problem-solving fields to `TaskContextItem`, `ProblemSpaceSearchContextItem`, or `ErrorCorrectionContextItem`.
- Why rejected: Those types have different ownership and lifecycle semantics. Expanding them would produce large optional-field bags, break conceptual clarity, and couple caller-authored durable records to specific runtime algorithms.

### Alternative 7: Add Algorithms And Tools In The Same Change

- What: Add an adversarial audit algorithm plus model-callable raise/respond/resolve tools alongside the dataclasses.
- Why rejected: Trigger cadence, authorship, authority, lifecycle enforcement, deduplication, and composition with existing algorithms are separate architectural decisions. The user asked to add the primitives, and the selected no-tests workflow favors an additive value-object change.

### Alternative 8: Software-Engineering-Specific Primitive Names

- What: Add API-contract, regression-test, retry, migration, and rollback primitives.
- Why rejected: The user explicitly broadened the requirement to general problem solving. Those concepts remain valid domain instances of dependency, invariant, intervention risk, feedback, and completion primitives rather than defining the top-level ontology.
