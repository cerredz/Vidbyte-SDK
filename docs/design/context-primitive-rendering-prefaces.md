# Design Doc: Context Primitive Rendering Prefaces

**Status:** Draft
**Author:** Codex
**Created:** 2026-08-28
**Last Updated:** 2026-08-28

---

## 1. Overview

Add a unique, four-sentence preface to the rendered text of every concrete context-window primitive in `vidbyte/context/primitives`. Each preface will tell the next model iteration what kind of typed context follows before the primitive's fields are rendered, making heterogeneous context windows easier to interpret without changing primitive schemas, placement, trust boundaries, or truncation behavior.

---

## 2. Goals & Non-Goals

### Goals

- Add one unique four-sentence semantic preface to each of the 52 concrete `*ContextItem` renderers under `vidbyte/context/primitives`.
- Place each preface at the beginning of the renderer's local `lines`/rendering sequence, before the primitive-specific fields.
- Describe the specific context type and the meaning of the fields that follow for every primitive.
- Preserve the shared managed-context introduction, untrusted-data tags, deterministic field order, optional-field behavior, and existing character bounds.
- Keep the change dependency-free and compatible with the existing public primitive APIs.

### Non-Goals

- Do not change dataclass fields, constructor signatures, primitive IDs, registry behavior, or context placement.
- Do not alter the shared three-line `CONTEXT_INTRODUCTION_LINES` boundary.
- Do not change trust classification or remove `<untrusted_data>` wrappers from multi-agent records.
- Do not add a new rendering abstraction, lint rule, or feature-test directory.
- Do not modify context algorithms, tools, handoff models, or non-primitive `lines` arrays.

---

## 3. Background & Context

- The SDK represents model-visible runtime state as immutable, typed context primitives whose `to_context_text()` output is inserted into later context-window iterations.
- The current shared introduction says that a record is managed SDK context, but it does not identify whether the following body is a task, artifact, causal analysis, worker report, risk concern, or another specific record type.
- The primitive package already owns deterministic renderers and the shared `_with_context_intro()`/`_truncate_text()` helpers. The smallest safe extension is therefore local preface text in each concrete renderer.
- The repository's `scripts/check_context_primitive_introductions.py` check must continue to see every renderer using `_with_context_intro()` or `_truncate_text()`, and `scripts/run_ci.py` remains the canonical SDK gate.

---

## 4. Requirements

### Functional Requirements

1. Every concrete class ending in `ContextItem` under `vidbyte/context/primitives/*.py`, except the structural `ContextItem` protocol, must render a preface before its primitive-specific body.
2. Each preface must be a single string entry in the renderer's local rendering sequence and contain four complete sentences.
3. Each preface must be unique to its primitive and explain the type of context represented by the fields that follow.
4. Renderers that currently build a `lines` list must start that list with the new preface and a blank separator before existing field output.
5. Renderers that currently return a direct string or build a tuple must be adjusted to use an equivalent ordered sequence without changing their observable field content.
6. The shared managed-context introduction must still be emitted before every primitive body through `_with_context_intro()` or `_truncate_text()`.
7. Existing output safety behavior must remain unchanged: multi-agent trust tags remain intact, optional fields remain conditional, and `max_chars` continues to bound the complete rendered text.
8. The final implementation must cover exactly 52 concrete renderers across 13 primitive modules, with no primitive module omitted.

### Non-Functional Requirements

- Performance: Prefaces are static literals; rendering adds only the cost of joining a few short strings.
- Determinism: Identical primitive values must produce identical output, including preface order and wording.
- Compatibility: No public import, constructor, dataclass field, or return type changes.
- Reliability: Existing source, import/render, package, and full CI gates must pass.
- Security: Existing untrusted-data wrappers and serialization boundaries must remain unchanged.

---

## 5. High-Level Design

The implementation will update only the concrete primitive renderer methods. For list-based renderers, the first local list element will be a four-sentence paragraph describing that primitive, followed by an empty string and the existing fields. For direct-string renderers, the body will be assembled as a local list before passing through the existing shared helper. For tuple-based checkpoint output, the sequence will be converted to the same ordered string-list pattern so the preface remains clearly first.

The shared rendering boundary remains the outer layer: `_with_context_intro()` continues to add the generic managed-context warning for renderers that use it, and `_truncate_text()` continues to add that warning and enforce `max_chars`. Multi-agent renderers will place their semantic preface outside the existing tagged payload while leaving all tags, serialized values, and trust classifications unchanged.

```text
[shared managed-context introduction]
        |
        v
[unique primitive preface]
        |
        v
[existing primitive-specific fields and trust tags]
        |
        v
[existing truncation bound]
```

The change is intentionally local to rendering content. No new helper is introduced because a shared formatter would make the descriptions less explicit and could make it easier for two semantically different primitives to acquire the same preface.

---

## 6. Detailed Design

### 6.1 Concrete Primitive Renderers

**File(s):** `vidbyte/context/primitives/checkpoints.py`, `closure.py`, `decisions.py`, `documents.py`, `epistemics.py`, `execution.py`, `framing.py`, `multi_agent.py`, `reasoning.py`, `reasoning_strategies.py`, `reasoning_traces.py`, `records.py`, `tasks.py`
**Type:** Modified

#### What it does

Each renderer will introduce the following context-specific subject before its existing body. The table is the source-of-truth inventory for the required unique prefaces.

| Primitive | Preface subject |
|---|---|
| `TrajectoryCheckpointContextItem` | A bounded runtime checkpoint, including iteration, trajectory, output, score, and feedback. |
| `ReflexionContextItem` | A self-critique and correction plan describing a failed or uncertain reasoning attempt. |
| `ProcessStallContextItem` | A process-stall diagnosis covering repetition, missing novelty, drift, and an escape action. |
| `CompletionGateContextItem` | A completion claim compared with desired outcomes, evidence, and missing validation. |
| `RiskEscalationContextItem` | An unresolved risk record covering impact, mitigations, acceptance, review, and escalation. |
| `DecisionChallengeContextItem` | A decision under scrutiny through rationale, uncertainty, failure modes, and reopening criteria. |
| `AlternativeChallengeContextItem` | A competitive alternative assessed against a target decision, mechanism, rejection rationale, and counterexample. |
| `TradeoffContextItem` | The benefits, costs, affected parties, externalities, opportunity costs, and second-order effects of a choice. |
| `TextContextItem` | Free-form text with its title, optional source, and body content. |
| `FileContextItem` | A file snapshot with path metadata, language information, and content or excerpt. |
| `GitDiffContextItem` | A repository change set with branch/range metadata, changed files, and raw diff. |
| `DocumentContextItem` | A sourced document identified by title and optional ID, followed by its content. |
| `EnvironmentContextItem` | Execution-environment details such as operating system, working directory, and shell. |
| `MemoryContextItem` | A retained memory summary with optional source attribution. |
| `AssumptionChallengeContextItem` | An assumption examined through its basis, confidence, evidence, falsifier, and validation method. |
| `ModelChallengeContextItem` | A model or causal representation challenged through competing models and distinguishing observations. |
| `EvidenceChallengeContextItem` | A claim audited for support, counterevidence, provenance, freshness, bias, and missing evidence. |
| `InvariantContextItem` | An invariant check describing scope, observed state, violation evidence, consequence, and check method. |
| `DependencyContextItem` | A dependency required by an objective or plan, including fragility, ownership, and fallback. |
| `InterventionRiskContextItem` | An intervention risk split into intended, reversible, irreversible, uncertain, contained, and recoverable effects. |
| `FeedbackGapContextItem` | The feedback design needed to observe an intervention's expected outcome and response threshold. |
| `ProblemFrameContextItem` | A challenge to the current problem frame, underlying need, affected parties, and alternative frames. |
| `ObjectiveGapContextItem` | The unresolved gap between an objective and desired outcome, including next evidence and completion criteria. |
| `ObjectiveConflictContextItem` | Objectives that cannot currently be satisfied together, with affected parties and a decision needed. |
| `BoundaryContextItem` | A scope, authority, policy, ethical, or other boundary around a challenged action. |
| `AmbiguityContextItem` | Competing interpretations of a term or context and the consequences of leaving it unclear. |
| `PerspectiveGapContextItem` | Missing viewpoints, affected parties, likely blind spots, and value judgments around a subject. |
| `MultiAgentRequestContextItem` | The user request supplied to orchestration phases, explicitly treated as untrusted input. |
| `MultiAgentTeamContextItem` | Trusted team instructions and bounded capability cards for worker agents. |
| `MultiAgentLedgerContextItem` | An untrusted orchestration ledger snapshot containing current tasks, facts, blockers, and next action. |
| `MultiAgentReportContextItem` | An untrusted latest worker report containing result, evidence, blockers, and next action. |
| `MultiAgentLimitsContextItem` | Finite orchestration budgets, current counters, and timeout limits that constrain manager authority. |
| `MultiAgentTerminalContextItem` | Terminal synthesis state, candidate answer, and finish decision, all with existing trust treatment. |
| `ProblemSpaceSearchContextItem` | A bounded exploration note showing what was not considered, current blind spots, and next directions. |
| `ErrorCorrectionContextItem` | An authoritative correction notice identifying context that contradicts the original system prompt. |
| `DeductionContextItem` | A deductive argument with premises, inference rule, conclusion, and soundness caveat. |
| `InductionContextItem` | An inductive generalization built from observations, a pattern, confidence, bias risk, and falsifier. |
| `AbductionContextItem` | A comparison of competing explanations against evidence, with a best explanation and discriminating test. |
| `AnalogyContextItem` | A structural analogy mapping relations from a source domain to a target domain and marking its limits. |
| `CausalChainContextItem` | A proposed cause-and-effect chain with mechanism, effect, confounders, and intervention test. |
| `BayesianUpdateContextItem` | A belief revision showing hypothesis, prior, likelihoods, posterior, and shift explanation. |
| `DifferentialDiagnosisContextItem` | A candidate set narrowed by eliminations toward the next discriminating check. |
| `FermiEstimateContextItem` | An order-of-magnitude estimate decomposed into assumptions, arithmetic, sanity band, and anchor risk. |
| `SteelmanContextItem` | A position tested against its strongest opposition, with a survival verdict and possible revision. |
| `FalsifyContextItem` | A claim paired with a test and riskiest prediction that could expose its failure. |
| `ReasoningTraceContextItem` | A strategy-specific reasoning checkpoint whose strategy-owned fields or fallback fields follow. |
| `ArtifactContextItem` | A named deliverable with an artifact type and body content for later context consumers. |
| `ResponseContextItem` | A response record with optional sender attribution and response content. |
| `ToolCallContextItem` | A tool invocation record showing the tool name, arguments, and resulting output. |
| `TaskContextItem` | A goal-tracking record with status, progress, completed work, next steps, and checks. |
| `ProgressContextItem` | A compact run journal of completed tasks, touched files, decisions, errors, and next steps. |
| `PlanContextItem` | An ordered multi-step plan whose status and active step guide execution. |

#### Interface / API

No public interface changes. Every affected class retains its existing `to_context_text() -> str` signature and existing dataclass contract. The only output change is the added primitive-specific preface before the already-rendered body.

#### Logic / Algorithm

1. Identify each concrete `*ContextItem` renderer in the 13 listed modules.
2. Add one four-sentence literal as the first local rendering item, followed by a blank separator.
3. Preserve all existing field additions, conditional sections, serializer calls, tags, and field order after the separator.
4. Preserve the existing final call to `_with_context_intro()` or `_truncate_text()` exactly as the renderer's boundary mechanism.
5. Review the resulting output inventory to confirm all 52 concrete renderers have distinct four-sentence prefaces.

#### Edge Cases & Error Handling

- Existing `max_chars` bounds remain authoritative; a long preface may cause more of the body to be truncated, which is expected for this model-context clarification.
- Empty optional fields and empty tuple sections retain their current omission behavior after the preface.
- `MultiAgentContextSerializer` continues to bound opaque values and preserve untrusted tags; the preface does not make payload data trusted.
- `ReasoningTraceContextItem` continues to render dynamic strategy fields when present and fallback fields otherwise; its preface describes both paths.
- No new exceptions or error handling paths are introduced.

### 6.2 Existing Verification Surface

**File(s):** `scripts/check_context_primitive_introductions.py`, `scripts/test_context_window_primitives.py`, `tests/test_context_primitives_registry.py`, `scripts/run_ci.py`
**Type:** Existing files, used without modification

#### What it does

The existing introduction checker confirms every concrete primitive renderer uses the shared context boundary. The focused primitive script and pytest suite verify importability, registry rendering, placement, and compatibility behavior. The canonical source and package stages provide the final repository gate.

#### Interface / API

```text
PYTHONPATH=<worktree> python scripts/run_ci.py --stage source
python scripts/run_ci.py --stage package
python scripts/run_ci.py
```

#### Logic / Algorithm

1. Run the focused primitive smoke script after implementation.
2. Run the source gate with `PYTHONPATH` pointing at the worktree so imports resolve to the changed code.
3. Run the package gate without `PYTHONPATH` so the freshly built wheel is installed and tested.
4. Run the complete `python scripts/run_ci.py` command without `PYTHONPATH` as the final local gate.

#### Edge Cases & Error Handling

- The source stage must use the worktree import path; otherwise an editable install can test the canonical checkout instead.
- The package stage must not inherit `PYTHONPATH`; otherwise it can bypass the wheel installation.
- No new tests are added because this is a bounded, content-only rendering change covered by existing primitive and full SDK gates under the requested no-tests workflow.

---

## 7. Data Model Changes

N/A - This change adds static rendering text only; no dataclass fields, schemas, persisted records, or migrations change.

---

## 8. API Changes

N/A - Public constructors, imports, methods, and serialized data contracts remain unchanged. The model-visible text returned by `to_context_text()` gains a descriptive preface by design.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-primitive-rendering-prefaces.md` | Document the complete rendering-preface inventory and implementation contract. |
| MODIFY | `vidbyte/context/primitives/checkpoints.py` | Add unique prefaces to trajectory checkpoint and reflexion renderers. |
| MODIFY | `vidbyte/context/primitives/closure.py` | Add unique prefaces to process-stall, completion-gate, and risk-escalation renderers. |
| MODIFY | `vidbyte/context/primitives/decisions.py` | Add unique prefaces to decision, alternative, and tradeoff renderers. |
| MODIFY | `vidbyte/context/primitives/documents.py` | Add unique prefaces to text, file, diff, document, environment, and memory renderers. |
| MODIFY | `vidbyte/context/primitives/epistemics.py` | Add unique prefaces to assumption, model, and evidence challenge renderers. |
| MODIFY | `vidbyte/context/primitives/execution.py` | Add unique prefaces to invariant, dependency, intervention-risk, and feedback-gap renderers. |
| MODIFY | `vidbyte/context/primitives/framing.py` | Add unique prefaces to problem-frame, objective, boundary, ambiguity, and perspective renderers. |
| MODIFY | `vidbyte/context/primitives/multi_agent.py` | Add unique prefaces while preserving orchestration serialization and trust tags. |
| MODIFY | `vidbyte/context/primitives/reasoning.py` | Add unique prefaces to problem-space search and error-correction renderers. |
| MODIFY | `vidbyte/context/primitives/reasoning_strategies.py` | Ensure all ten strategy renderers have distinct four-sentence prefaces. |
| MODIFY | `vidbyte/context/primitives/reasoning_traces.py` | Add a strategy-trace preface before dynamic or fallback fields. |
| MODIFY | `vidbyte/context/primitives/records.py` | Add unique prefaces to artifact, response, and tool-call renderers. |
| MODIFY | `vidbyte/context/primitives/tasks.py` | Add unique prefaces to task, progress, and plan renderers. |
| DELETE | N/A | No files are deleted. |

**Manifest totals:** 1 file created, 13 files modified, 0 files deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | Existing project runtime `>=3.11` | String-list assembly and existing renderer helpers. | None beyond normal source syntax errors, covered by compile and source gates. |
| Existing SDK CI tooling | `scripts/run_ci.py` | Verify source and installed-package behavior. | Worktree import-path mistakes can test stale code; follow the field-guide command sequence. |

No new external service, package, network call, or dependency is introduced.

---

## 11. Rollout & Deployment

- No feature flag or migration is involved.
- This is backward-compatible for Python callers and changes only model-visible rendering text.
- Rollout occurs with the normal SDK source distribution and wheel release.
- Rollback is a revert of the implementation commit(s), restoring the prior renderer sequences; no data repair is required.

---

## 12. Open Questions

N/A - The request specifies the target package, ordering, uniqueness, and sentence-level description requirements.

---

## 13. Alternatives Considered

### Alternative 1: One shared generic preface for every primitive

- What: Add a single helper-generated description such as “The following record contains context fields.”
- Why rejected: It would not satisfy the requirement for descriptions unique to each primitive or explain the specific body that follows.

### Alternative 2: Add descriptions only to renderers that already use a `lines` list

- What: Leave direct-string and tuple-based renderers unchanged.
- Why rejected: It would omit concrete primitives and violate the requirement that every primitive receive a preface.

### Alternative 3: Add a new base-class field or renderer abstraction

- What: Store a description on each dataclass and centralize preface assembly in the base protocol/helper.
- Why rejected: It changes the data model and adds abstraction to a content-only request; local literals keep each primitive's meaning visible beside its existing field layout.

### Alternative 4: Add new feature-specific tests

- What: Create a new test pack asserting exact preface text for all primitives.
- Why rejected: The requested `design-doc-no-tests` workflow treats this as a low-risk, content-only rendering update; existing primitive smoke, source, package, and full CI gates are sufficient without pinning prose snapshots.
