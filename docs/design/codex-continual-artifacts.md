# Design Doc: Codex Continual Artifacts

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-08
**Last Updated:** 2026-09-08

## 1. Overview

Maintain a custom Vidbyte trace artifact from Codex completed-item observations using a separate, bounded native Codex update turn. This change depends on feat/codex-live-observation (#422).

---

## 2. Goals & Non-Goals

### Goals
Reuse TraceSchema and UpdateTraceTool validation/merge semantics, schedule every N completed items and at successful run end, expose artifacts and diagnostics.
### Non-Goals
No internal iteration parity, native action barrier, or implicit trace injection into main context.

---

## 3. Background & Context

The existing ContinualTraceAgent requires a BaseAgent runner. Codex owns a different execution boundary. A Codex updater will request schema-constrained JSON from a separate native thread, then apply it through the existing UpdateTraceTool. Current merge behavior appends/deduplicates top-level arrays, shallow-merges objects, and replaces scalars. No generic updater refactor is required.

---

## 4. Requirements

### Functional Requirements
1. Validated CodexContinualTraceSettings carries TraceSchema, positive every_n_completed_items, bounded max_update_attempts, bounded observation window, and finite timeout_seconds.
2. Dedicated update requests reuse native model/client settings; use read-only sandbox, deny approvals, and disabled subagents. No observation recursion.
3. Update output must be a trace object accepted by UpdateTraceTool before committing artifact state.
4. Schedule unique completed items, skip duplicate item completions, and perform one final update unless the current completed-item boundary was already successfully updated.
5. Fail-open updater diagnostics are exposed; cancellation propagates. Keep trace outside main context and publish metadata[trace], metadata[trace_metadata], and agent.last_trace.
6. Forks inherit or explicitly replace/disable continual settings.
### Non-Functional Requirements
Bound memory and updater duration; never leak raw errors into diagnostic metadata; retain actual SDK schema behavior and lazy optional imports.

---

## 5. High-Level Design

CodexHarnessAgent creates a fresh CodexContinualTraceBridge for each invocation. It appends its observe callback to the native observation settings, receives reviewed completed items, and asks CodexTraceUpdater for schema-shaped JSON. UpdateTraceTool owns validation and accumulation. The updater has an isolated thread and no observation configuration, preventing recursion. The returned AgentMessage includes the artifact and update/error counters.

---

## 6. Detailed Design

### 6.1 Continual contracts
**Files:** vidbyte/lib/dataclasses/codex.py, vidbyte/lib/constants/codex.py
**Type:** Modified
#### What it does
Validated immutable configuration with explicit completed-item scheduling, typed run settings and optional disabled sentinel.
#### Interface / API
`CodexContinualTraceSettings(schema, every_n_completed_items=5, max_update_attempts=3, max_observations=100, timeout_seconds=60.0)`; `CodexHarnessAgentSettings(..., continual_trace=None)`.
#### Logic / Algorithm
Reject booleans and nonfinite/nonpositive bounds; keep None for disabled, fork None for inherit with clear_continual_trace to disable.
#### Edge Cases & Error Handling
Invalid fork configuration fails before native creation.
### 6.2 Native updater and scheduler
**Files:** vidbyte/agents/codex/continual.py, prompt enum/assets, agent.py, fork.py, __init__.py, README.md
**Type:** New and modified
#### What it does
Builds native output-schema requests and applies validated trace patches.
#### Interface / API
`CodexTraceUpdater.update(request)` and `CodexContinualTraceBridge.observe(event)` are async; `finalize()` makes a final attempt when required.
#### Logic / Algorithm
Deduplicate completed item IDs, retain a bounded observation window, count item boundaries, retry invalid updates within the attempt cap, and serialize the previous artifact plus reviewed window. Read-only restrictions are applied at thread and turn boundaries. Publish a copied artifact after the main run and include update-failure bookkeeping.
#### Edge Cases & Error Handling
Invalid JSON, malformed trace shape, timeout, and native failure preserve previous artifact and record the error class. Cancellation is never converted to success. Explicitly mark observation truncation.

---

## 7. Data Model Changes

### 7.1 Continual trace settings
**Change type:** Additive optional agent/fork fields and shared settings/request dataclasses.
**Migration strategy:** No persistent migration; disable by omission or revert feature commits.

---

## 8. API Changes

Python-only additive API described above. No HTTP endpoints. Root exports include CodexContinualTraceSettings.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|---|---|---|
| CREATE | docs/design/codex-continual-artifacts.md | Design |
| CREATE | vidbyte/agents/codex/continual.py | Native updater and scheduler |
| CREATE | tests/codex_continual/FEATURE.md | Contract |
| CREATE | tests/codex_continual/test_continual.py | Acceptance |
| CREATE | scripts/test-codex-continual-artifacts.py | Script verification |
| CREATE | vidbyte/prompts/prompts/continual_trace/codex_system.md | Native JSON update prompt |
| MODIFY | vidbyte/prompts/prompts/continual_trace/continual_trace.json | Prompt registration |
| MODIFY | vidbyte/lib/enums/prompts.py | Prompt key |
| MODIFY | vidbyte/lib/dataclasses/codex.py | Settings and update requests |
| MODIFY | vidbyte/lib/constants/codex.py | Default bounds |
| MODIFY | vidbyte/agents/codex/agent.py | Run scheduling and artifact publication |
| MODIFY | vidbyte/agents/codex/fork.py | Inherit/replace/clear |
| MODIFY | vidbyte/__init__.py | Public configuration |
| MODIFY | vidbyte/agents/codex/README.md | Document cadence and limits |

---

## 10. Testing Plan

### Unit Tests
- [Edge Case] Reject zero, negative, boolean, and nonfinite settings.
- [Silent Failure] Reuse actual UpdateTraceTool array dedupe, shallow object merge, scalar replacement, nested shape validation.
- [Hidden Failure] Invalid output/native exception/timeout preserve state and report sanitized failure class.
- [Hidden Assumption] Cancellation propagates instead of failing open.
### Integration Tests
- [Edge Case] Empty run finalizes once; exact interval does not duplicate successful final update.
- [Silent Failure] Duplicate completed IDs do not advance cadence; window truncation is explicit.
- [Hidden Assumption] Updater requests inherit credentials/model while overriding sandbox/approvals/subagents and disabling observers.
- [Hidden Failure] Real agent arun publishes isolated artifacts, resets each run, and retains normal output/middleware behavior.
- [Hidden Assumption] Forks inherit, replace, and clear settings.
### Manual / QA Test Cases
Execute all named cases through the script, then source and full CI. Native calls are faked offline; no live-model accuracy claim.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|---|---|---|---|
| openai-codex | 0.147.x | Separate structured update turns | Additional model cost and latency |
| UpdateTraceTool | Existing SDK | Schema enforcement | Existing shallow-object semantics |

---

## 12. Rollout & Deployment

Opt in through continual_trace. No migration. Later acceptance-policy PR can make artifacts mandatory; this PR preserves the SDK fail-open default. Roll back by disabling the setting. PR depends on #422 and targets main with that dependency explicitly recorded.

---

## 13. Open Questions

No blocker. Default observation window is bounded and may lose early detail; artifact accumulation and explicit truncation counters make this visible. Read-only filesystem sandbox is not a general guarantee that every configured external tool is side-effect-free; updater prompt requests no tools and documentation must not claim stronger isolation.

---

## 14. Alternatives Considered

### Alternative 1: Reuse BaseAgent runner
Rejected as default because it would require separate provider credentials rather than existing Codex authentication.
### Alternative 2: Ask main model to update traces
Rejected because the model may skip it; deterministic observer scheduling is the intended contract.
