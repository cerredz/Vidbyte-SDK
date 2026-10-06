# Design Doc: Failure Pattern Repair Prompts

**Status:** Draft
**Author:** Codex
**Created:** 2026-08-30
**Last Updated:** 2026-08-30

---

## 1. Overview

Add a catalog-backed `failure_pattern_repair` prompt family containing exactly five in-depth, independently usable prompts that turn repeated agent failures into process-level repairs. Each prompt approaches the same core idea through a different mechanism—rulebook learning, dependency-shape analysis, workflow-stage gates, evaluator red-teaming, or selective regeneration—while requiring expected behavior, failure detection, and an independent check before work may advance. The family is designed to prevent fluent completion claims or brittle green checks from standing in for demonstrated correctness.

---

## 2. Goals & Non-Goals

### Goals

- Ship exactly five substantial Markdown prompts under one discoverable prompt family.
- Give each prompt a distinct, self-contained implementation strategy for pattern-level repair.
- Require failures to be clustered by missing rule, dependency shape, or workflow stage instead of handled only as isolated tickets.
- Require an explicit expected-behavior contract, a concrete failure detector, and independent verification before advancement.
- Treat evaluator weakness as a first-class risk and require negative controls, counterexamples, or mutation-style checks where applicable.
- Register all five prompts in the JSON catalog, `Prompt` enum, generated direct-import surface, and human-readable prompt catalog.
- Preserve packaging compatibility so all Markdown assets load from an installed wheel.

### Non-Goals

- Add a new runtime algorithm, agent class, orchestration primitive, CLI command, or hosted service.
- Add prompt-specific Python logic or alter how `Prompts` discovers and exports assets.
- Add new test files; the existing catalog, source, and package gates are sufficient for this asset-only feature.
- Prescribe one migration language, repository structure, model provider, or CI vendor.
- Automatically execute repairs, mutate a repository, or decide that a caller's external workflow has passed.

---

## 3. Background & Context

The current prompt catalog stores Markdown-backed prompt families beside a JSON descriptor, maps every flattened `family.prompt` identifier to a `Prompt` enum member, and dynamically exposes direct imports from those identifiers. Existing catalog tests verify enum-to-asset synchronization and export availability, while the package gate proves non-Python assets survive wheel installation.

The requested idea comes from a process-oriented migration practice: when the same problem recurs, the useful intervention is to repair the rule or loop that keeps producing it, then re-run the affected work. That practice depends on a trustworthy referee. A check that only accepts expected output, shares assumptions with the producer, or can be gamed by completion text can remain green while behavior is wrong. The new prompt family therefore makes advancement conditional on three explicit artifacts: an expected-behavior contract, a failure detector, and an independent check whose ability to reject known-bad work has itself been demonstrated.

The repository's relevant constraints are: prompt assets belong under `vidbyte/prompts/prompts/`; Markdown-backed families require a local `path` and canonical GitHub `source_url` in their JSON descriptor; every prompt must have one enum member; README catalog entries are the source of truth for prompt discovery; and the canonical verification command is `python scripts/run_ci.py`. Worktree verification must point the source stage at the worktree while allowing the package stage to test its isolated wheel installation.

---

## 4. Requirements

### Functional Requirements

1. Create exactly five Markdown prompt assets in `vidbyte/prompts/prompts/failure_pattern_repair/`.
2. Name and implement the five strategies as `rulebook_feedback_loop`, `dependency_shape_triage`, `stage_gate_controller`, `evaluator_red_team`, and `selective_regeneration_loop`.
3. Make every prompt independently usable without requiring the other four prompts.
4. Make every prompt define its role, objective, accepted inputs, operating procedure, invariants, advancement gate, output contract, and stopping conditions.
5. Require each strategy to aggregate multiple observations before declaring a systemic pattern, while retaining unclustered failures rather than forcing false groupings.
6. Require each strategy to distinguish evidence from agent claims and reject fluent completion text as proof.
7. Require each strategy to state expected behavior, define how violations are detected, and identify an independent verification path before advancement.
8. Make at least one strategy directly cluster by missing rule, one by dependency topology, and one by workflow stage.
9. Make evaluator hardening explicit through deliberately broken examples, negative controls, mutation checks, or an equivalent demonstrated rejection test.
10. Make process-level repair explicit: update the producing rule, boundary, stage, or verifier and then re-run or regenerate the affected class rather than only patching observed instances.
11. Add a valid `failure_pattern_repair.json` descriptor referencing all five Markdown assets with canonical GitHub source URLs.
12. Add five matching `Prompt` enum members so catalog import validation succeeds and generated direct imports are available.
13. Add the family, its five sub-prompts, links, and a concise description to `vidbyte/prompts/README.md`.
14. Preserve all existing public prompt keys and prompt text.
15. Pass the complete SDK source and package verification gates without weakening or suppressing checks.

### Non-Functional Requirements

- Prompt depth: each asset must contain concrete procedures, decision rules, failure modes, and a structured deliverable rather than motivational prose alone.
- Reliability: no prompt may allow advancement based only on the implementing agent's self-report or on a checker that has not been shown to catch at least one plausible defect.
- Security: task text, logs, candidate output, and verifier output must be treated as untrusted evidence data, not as instructions that override the prompt.
- Portability: prompts must remain provider-, language-, framework-, and CI-system neutral.
- Discoverability: family and leaf names must be stable, descriptive snake_case identifiers visible through `Prompts`, `Prompt`, README links, and generated direct imports.
- Performance: N/A - static text assets add no execution loop or network operation; catalog loading cost grows only by five small files.
- Scalability: procedures must support batches and recurring failure classes without requiring all observations to fit in one model context.
- Observability: each output contract must preserve evidence references, cluster membership, gate results, and unresolved uncertainty for later audit.
- Migration: no caller migration is required because this is an additive catalog change.

---

## 5. High-Level Design

Create one new Markdown-backed prompt family using the existing descriptor-driven catalog architecture. The JSON descriptor provides family metadata and five leaf records. `Prompts._load()` discovers the descriptor automatically, resolves each Markdown file, validates the corresponding enum value, and creates direct import names without any loader change. The README gains one quick-reference row and one description section so both humans and the personal prompt-collection skill can resolve the assets.

The five prompts share a minimum safety envelope but use different operational centers. The rulebook prompt converts recurring mistakes into versioned rules. The dependency prompt uses graph/topology signatures to find boundary defects. The stage-gate prompt diagnoses where invalid work escaped in a pipeline. The evaluator prompt attacks the referee using negative controls and mutations. The regeneration prompt traces a repaired rule to its blast radius and replaces all affected outputs. They are alternatives, not sequential phases, so a caller can select the mechanism matching the observed failure shape.

```text
[Failure evidence batch]
          |
          v
[Choose one pattern lens]
  | rule | dependency | stage | evaluator | regeneration |
          |
          v
[Expected behavior + detector + independent checker]
          |
          v
[Repair producing process] -> [Re-run affected class] -> [Gate evidence]
```

The gate design deliberately separates producer claims from evidence. A strategy may report `advance` only when its required artifacts exist, the primary detector passes, an independent checker agrees on observable behavior, and the checker has rejected a relevant known-bad case. Otherwise the output remains `hold`, `repair`, or `uncertain` with explicit missing evidence.

---

## 6. Detailed Design

### 6.1 Rulebook Feedback Loop Prompt

**File(s):** `vidbyte/prompts/prompts/failure_pattern_repair/rulebook_feedback_loop.md`
**Type:** New file

#### What it does

Guides an agent to cluster repeated failures by the absent, ambiguous, or incorrect rule that allowed them, amend the rulebook, identify the outputs produced under the old rule, and prove the revised rule changes the next batch's behavior.

#### Interface / API

```text
Inputs: objective, current rulebook, failure observations, produced artifacts, available detectors, independent-check options
Output: rule-gap clusters, rule amendments, affected-output ledger, regeneration plan, gate verdict
```

#### Logic / Algorithm

1. Normalize observations into evidence records without trusting completion claims.
2. Group only observations supported by a shared rule-level causal hypothesis.
3. Write a falsifiable expected behavior and primary detector for each cluster.
4. Amend the smallest upstream rule capable of preventing the class.
5. identify every output created under the superseded rule.
6. Re-run representative and affected work, then independently check behavior.
7. Permit advancement only after the detector and independent checker catch a known-bad case and accept repaired work.

#### Edge Cases & Error Handling

- Singletons remain in an unclustered queue until evidence supports a class.
- Conflicting clusters are marked uncertain rather than merged for convenience.
- A rule change with an unknown blast radius blocks advancement.
- A checker that cannot reject a deliberately broken case is treated as failed.

### 6.2 Dependency Shape Triage Prompt

**File(s):** `vidbyte/prompts/prompts/failure_pattern_repair/dependency_shape_triage.md`
**Type:** New file

#### What it does

Guides an agent to map failures onto dependency motifs such as cycles, fan-in hubs, fan-out drift, layering inversions, shared adapter mismatches, or ordering constraints and then repair the shared boundary rather than each symptom.

#### Interface / API

```text
Inputs: objective, dependency evidence, failure observations, affected nodes/edges, build or runtime evidence, checker options
Output: topology clusters, shared-boundary hypotheses, structural repair plan, affected-node set, gate verdict
```

#### Logic / Algorithm

1. Build or validate a dependency view from authoritative artifacts.
2. Attach each failure to nodes, edges, stage order, and observable symptoms.
3. Cluster by recurring topology signature rather than text similarity alone.
4. Define the allowed dependency invariant and a mechanical violation detector.
5. Repair the narrowest shared boundary or ordering rule.
6. Re-check every incident edge and independently validate representative consumers.
7. Advance only when structural and behavioral evidence agree.

#### Edge Cases & Error Handling

- Incomplete dependency evidence is reported as an acquisition gap, not guessed.
- Similar error messages with different graph positions stay separate.
- Cycles introduced by the proposed fix block the gate.
- A clean graph check cannot substitute for behavior checks at affected consumers.

### 6.3 Stage Gate Controller Prompt

**File(s):** `vidbyte/prompts/prompts/failure_pattern_repair/stage_gate_controller.md`
**Type:** New file

#### What it does

Guides an agent to classify failures by the workflow stage that should have prevented, detected, contained, or escalated them, then install explicit entry, exit, and independent-check gates before downstream advancement.

#### Interface / API

```text
Inputs: objective, workflow stages, stage artifacts, failure observations, current gates, available independent checks
Output: escape-stage clusters, stage contracts, gate specifications, replay plan, advancement ledger
```

#### Logic / Algorithm

1. Reconstruct the workflow and authoritative artifacts at each transition.
2. Identify the earliest stage with enough information to catch each failure.
3. Cluster failures by common escape stage and missing gate capability.
4. Specify expected inputs, outputs, detector, evidence, and ownership for each gate.
5. Add an independent transition check that does not rely on producer self-attestation.
6. Replay affected transitions and downstream consequences.
7. Advance only from evidence-backed stage verdicts.

#### Edge Cases & Error Handling

- Missing stage artifacts produce `hold`, not inferred success.
- A downstream test may confirm containment but does not excuse a missing upstream prevention gate.
- Nondeterministic checks require repeat policy and uncertainty bounds.
- Manual overrides must be explicit, attributable, and non-green.

### 6.4 Evaluator Red-Team Prompt

**File(s):** `vidbyte/prompts/prompts/failure_pattern_repair/evaluator_red_team.md`
**Type:** New file

#### What it does

Guides an independent evaluator auditor to test whether the current judge can be fooled, shares blind spots with the producer, checks only surface form, or passes broken work, then harden it before its green result can authorize progress.

#### Interface / API

```text
Inputs: expected behavior, evaluator implementation or rubric, known failures, candidate artifacts, independent oracle options
Output: threat model, negative-control suite, surviving blind spots, evaluator repairs, calibrated gate verdict
```

#### Logic / Algorithm

1. Translate the expected behavior into observable claims and prohibited false positives.
2. Enumerate evaluator threat classes, including tautological checks and shared assumptions.
3. Create safe negative controls or mutations representing plausible broken behavior.
4. Run the evaluator against good, bad, ambiguous, and adversarial cases.
5. Cluster surviving bad cases by evaluator weakness.
6. Repair the evaluator and repeat until the required kill/rejection evidence exists.
7. Keep the production workflow blocked when independence or sensitivity remains unproven.

#### Edge Cases & Error Handling

- When destructive mutation is unsafe, use copies, fixtures, simulations, or counterfactual artifacts.
- A checker that rejects everything is invalid despite catching bad cases.
- Reviewer agreement is not independence when both consume the same flawed oracle.
- Unknown ground truth yields `uncertain`, never an automatic pass.

### 6.5 Selective Regeneration Loop Prompt

**File(s):** `vidbyte/prompts/prompts/failure_pattern_repair/selective_regeneration_loop.md`
**Type:** New file

#### What it does

Guides an agent to convert a confirmed systemic defect into a provenance-backed blast-radius query, repair the upstream producer, regenerate only outputs touched by that producer version, and compare the new batch against independent acceptance evidence.

#### Interface / API

```text
Inputs: objective, production rules and versions, output provenance, repeated failures, available detectors, independent oracle
Output: pattern diagnosis, repaired producer specification, affected-output manifest, regeneration waves, comparison evidence, stop verdict
```

#### Logic / Algorithm

1. Confirm that multiple failures share an upstream producer or rule version.
2. Define the intended behavior and detectors before changing artifacts.
3. Patch the producer specification, not individual generated outputs.
4. Compute the affected set from provenance and dependency evidence.
5. Regenerate in bounded waves with canaries before broad fan-out.
6. Compare old and new outputs using a primary detector and independent oracle.
7. Stop when the affected set is exhausted and both checks pass, or hold with an explicit residual ledger.

#### Edge Cases & Error Handling

- Missing provenance expands uncertainty and blocks claims of complete regeneration.
- Hand-edited outputs are flagged because they can mask whether the producer improved.
- Regressions in unaffected behavior trigger rollback of the producer change.
- Cost or time limits produce a resumable incomplete state, not a false completion.

### 6.6 Prompt Family Descriptor

**File(s):** `vidbyte/prompts/prompts/failure_pattern_repair/failure_pattern_repair.json`
**Type:** New file

#### What it does

Registers the family name, description, five stable leaf keys, Markdown paths, and canonical source URLs for automatic catalog discovery.

#### Interface / API

```json
{
  "name": "Failure Pattern Repair",
  "description": "...",
  "key": "failure_pattern_repair",
  "prompts": {
    "rulebook_feedback_loop": {"path": "rulebook_feedback_loop.md", "source_url": "..."},
    "dependency_shape_triage": {"path": "dependency_shape_triage.md", "source_url": "..."},
    "stage_gate_controller": {"path": "stage_gate_controller.md", "source_url": "..."},
    "evaluator_red_team": {"path": "evaluator_red_team.md", "source_url": "..."},
    "selective_regeneration_loop": {"path": "selective_regeneration_loop.md", "source_url": "..."}
  }
}
```

#### Logic / Algorithm

1. Use the existing descriptor schema.
2. Point every record at a same-directory Markdown file.
3. Use stable `main` branch GitHub links consistent with every existing family.
4. Allow `Prompts._load()` to discover and validate the family without loader changes.

#### Edge Cases & Error Handling

- Missing, empty, or non-Markdown paths fail during catalog loading.
- Descriptor keys without enum values fail fast during import.
- Duplicate leaf keys are impossible within the JSON object and duplicate flattened enum values are rejected by the loader.

### 6.7 Prompt Enum Registration

**File(s):** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### What it does

Adds five typed identifiers and updates the header's prompt/family counts from 59/21 to 64/22.

#### Interface / API

```python
FAILURE_PATTERN_REPAIR_RULEBOOK_FEEDBACK_LOOP = "failure_pattern_repair.rulebook_feedback_loop"
FAILURE_PATTERN_REPAIR_DEPENDENCY_SHAPE_TRIAGE = "failure_pattern_repair.dependency_shape_triage"
FAILURE_PATTERN_REPAIR_STAGE_GATE_CONTROLLER = "failure_pattern_repair.stage_gate_controller"
FAILURE_PATTERN_REPAIR_EVALUATOR_RED_TEAM = "failure_pattern_repair.evaluator_red_team"
FAILURE_PATTERN_REPAIR_SELECTIVE_REGENERATION_LOOP = "failure_pattern_repair.selective_regeneration_loop"
```

#### Logic / Algorithm

1. Add one enum member per descriptor leaf.
2. Preserve existing enum values and public names.
3. Rely on current catalog validation and dynamic export generation.

#### Edge Cases & Error Handling

- Any spelling mismatch between enum and descriptor fails import-time validation.
- No aliases are added, avoiding duplicate-value ambiguity.

### 6.8 Human-Readable Prompt Catalog

**File(s):** `vidbyte/prompts/README.md`
**Type:** Modified

#### What it does

Adds a quick-reference row listing all five sub-prompts and a description explaining their shared purpose, distinct strategies, direct leaf links, and family link.

#### Interface / API

```text
Prompt: Failure Pattern Repair
Key: failure_pattern_repair
Sub-prompts: rulebook_feedback_loop, dependency_shape_triage, stage_gate_controller, evaluator_red_team, selective_regeneration_loop
```

#### Logic / Algorithm

1. Add one quick-reference row using the existing GitHub link convention.
2. Add one description section near related prompt families.
3. Add a direct canonical Markdown link for every leaf so the personal prompt-collection skill can install a specific sub-prompt without guessing a path.
4. Describe the family without duplicating full prompt bodies.

#### Edge Cases & Error Handling

- All displayed leaf names must match the descriptor exactly.
- Leaf links must target their Markdown assets and the family link must target its directory on the `main` branch.

---

## 7. Data Model Changes

N/A - This feature adds static prompt assets and enum identifiers; it does not change persisted schemas, database records, wire models, or migrations.

---

## 8. API Changes

N/A - No HTTP or RPC endpoint changes are introduced. The existing additive Python prompt-catalog surface automatically exposes five new enum keys and direct imports.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/failure-pattern-repair-prompts.md` | Record requirements, architecture, risks, and verification before implementation |
| CREATE | `vidbyte/prompts/prompts/failure_pattern_repair/rulebook_feedback_loop.md` | Implement rule-gap clustering and rulebook feedback strategy |
| CREATE | `vidbyte/prompts/prompts/failure_pattern_repair/dependency_shape_triage.md` | Implement dependency-topology clustering and boundary repair strategy |
| CREATE | `vidbyte/prompts/prompts/failure_pattern_repair/stage_gate_controller.md` | Implement workflow-stage escape analysis and transition gates |
| CREATE | `vidbyte/prompts/prompts/failure_pattern_repair/evaluator_red_team.md` | Implement adversarial evaluator validation and hardening |
| CREATE | `vidbyte/prompts/prompts/failure_pattern_repair/selective_regeneration_loop.md` | Implement provenance-based blast-radius regeneration strategy |
| CREATE | `vidbyte/prompts/prompts/failure_pattern_repair/failure_pattern_repair.json` | Register the five Markdown assets as one catalog family |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add five typed catalog keys and update catalog counts |
| MODIFY | `vidbyte/prompts/README.md` | Make the family and direct prompt links discoverable |

Summary: 7 files created, 2 files modified, 0 files deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing `Prompts` catalog | Repository implementation | Discover, validate, and export the new family | Descriptor/enum drift causes import failure, which existing gates detect |
| Python package data | Existing `pyproject.toml` patterns | Include nested JSON and Markdown assets in distributions | Source-only checks could miss packaging errors, so the package stage is mandatory |
| Anthropic migration article | `https://claude.com/blog/ai-code-migration` | Source inspiration for process-level repair, adversarial review, and mechanical verification | The prompts must remain self-contained and must not depend on future page availability |

No new runtime dependency or external service call is added.

---

## 11. Rollout & Deployment

- No feature flag is required; the change is additive static package content.
- Existing users retain every current key and import unchanged.
- The five new keys become available when the next SDK build containing the assets is installed.
- Deployment order is the normal package release flow because descriptor, files, enum keys, and documentation ship atomically.
- Before push, install development gates once and run the worktree-aware source stage, package stage, and complete canonical gate.
- Rollback consists of reverting the feature commits, which removes the new descriptor/assets and their enum/README entries without data migration.

---

## 12. Open Questions

N/A - No unresolved decision requires user input. The family structure, names, integration surface, and exact count follow the existing prompt-catalog conventions and the user's five-prompt stopping condition.

---

## 13. Alternatives Considered

### Alternative 1: Five inline strings in one JSON file

- What: Store all prompt bodies directly in a single descriptor.
- Why rejected: In-depth prompt text would be harder to review, link, diff, and elect individually through the prompt collection. The repository prefers Markdown assets for substantial prompts.

### Alternative 2: Five unrelated top-level families

- What: Give each strategy a separate family and descriptor.
- Why rejected: All five implement the same user-facing concept and should be discoverable together. Separate families would add catalog noise and obscure that callers are choosing among alternative lenses.

### Alternative 3: One universal prompt with five optional modes

- What: Put all strategies in one long prompt selected by a mode argument.
- Why rejected: The user explicitly requested five prompts, and a mode-based prompt would make independent selection, direct linking, and focused context loading less clear.

### Alternative 4: Add a Python runtime orchestrator

- What: Implement clustering, gate execution, and regeneration as SDK classes.
- Why rejected: The request is for reusable prompts that introduce the implementation idea in different ways. Runtime automation would materially expand scope and require additional contracts and feature tests.

### Alternative 5: Add five new test files

- What: Write prompt-specific unit tests for wording and sections.
- Why rejected: Text-shape tests would be brittle and easy to game. Existing catalog synchronization, dynamic export, full source, and installed-package gates verify the relevant executable contract; prompt depth and distinctness are better checked through structured review and direct content audit.
