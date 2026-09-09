# Design Doc: Codex Final Acceptance

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-09
**Last Updated:** 2026-09-09

## 1. Overview
Make successful Vidbyte return conditional on required artifacts and application checks, even when Codex reports a completed native turn. This gives applications a deterministic acceptance boundary independent of model compliance and optional hooks.

## 2. Goals & Non-Goals
### Goals
- Reject noncompleted native turns, stale/missing required traces, invalid final trace schemas, and failed application checks.
- Publish success only after every configured check finishes.
- Keep native identity and usage for diagnostics without adding rejected replies to history.
### Non-Goals
- Undo prior tools, retry the model, force hidden reasoning, or guarantee hooks cover every action.
- Durable capture is a later integration; applications can already require their own capture check here.

## 3. Background & Context
Observation, continual artifacts, and native tools are implemented in preceding PRs. Continual tracing deliberately fails open and may retain an old partial artifact. Native completion therefore does not establish application success. Existing OutputSchemaFormatter validates shared output contracts; use it for final artifact validation too. Hook documentation explicitly notes skipped untrusted hooks and uncovered tool paths, making this application boundary necessary.

## 4. Requirements
### Functional Requirements
1. Add optional CodexAcceptanceSettings with require_completed, require_trace, trace_schema, checks, and timeout_seconds.
2. Validate settings before native startup; requiring trace or a trace schema requires continual_trace configuration.
3. A required trace must have a successful update for the final observed item boundary. Earlier successful updates cannot satisfy a failed final update.
4. Validate optional final trace schema through existing OutputSchemaFormatter. A custom check receives an isolated CodexAcceptanceRequest snapshot and must return exactly True; False, None, exceptions, or timeout reject.
5. Run checks after final trace generation and before appending history or publishing last_reply. Publish a deterministic acceptance receipt after all checks pass.
6. Preserve cancellation. Errors use a dedicated failure code and include native thread/turn identity without model content or raw check exceptions.
7. Forks inherit acceptance settings unless explicitly replaced. Empty settings permit callers to disable requirements; clearing continual_trace while inherited acceptance requires it rejects before native fork.
### Non-Functional Requirements
Opt-in preserves existing behavior. Each check has a finite positive timeout; checks run sequentially. Snapshots prevent one check mutating another or the reply. Validation cannot undo native effects, and cooperative callbacks must not block their event loop.

## 5. High-Level Design
CodexHarnessAgent finalizes its continual bridge, then invokes CodexAcceptanceGate with candidate reply and actual bridge artifacts/metadata. The gate verifies native status and final trace freshness, validates a requested schema, awaits isolated application checks, and returns a new reply with an acceptance receipt. Only then does the facade commit history and last_reply.

## 6. Detailed Design
### 6.1 Contracts and construction
**Files:** lib/dataclasses/codex.py, agents/codex/config.py, fork.py, vidbyte/__init__.py
**Type:** Modified
#### What it does
Defines frozen settings and candidate snapshot records; validates cross-setting dependencies and fork inheritance.
#### Interface / API
`CodexAcceptanceSettings(require_completed: bool = True, require_trace: bool = False, trace_schema: type | Mapping[str, Any] | None = None, checks: tuple[Callable[[CodexAcceptanceRequest], Awaitable[bool]], ...] = (), timeout_seconds: float = 60.0)`
`CodexAcceptanceRequest(reply: AgentMessage, trace: Mapping[str, Any] | None, trace_metadata: Mapping[str, Any])`
#### Logic / Algorithm
Validate booleans, callback tuple, finite positive timeout, and schema via shared formatter. Harness acceptance defaults None; fork override defaults None to inherit.
#### Edge Cases & Error Handling
Reject invalid callbacks/types or trace dependency mismatch before starting or forking native resources.

### 6.2 Acceptance gate
**Files:** agents/codex/acceptance.py, agent.py, continual.py, lib/enums/failure.py
**Type:** New and modified
#### What it does
Checks actual final boundary state and application requirements before successful publication.
#### Interface / API
`CodexAcceptanceGate.accept(request: CodexAcceptanceRequest) -> AgentMessage`
#### Logic / Algorithm
Reject noncompleted status when required. Required trace needs nonempty artifact plus final_update_complete=True from the actual bridge. Validate trace_schema with OutputSchemaFormatter. Await each callback with asyncio.wait_for on a deep snapshot; only bool True passes. Return a replacement reply with receipt containing accepted and check_count. Continual bridge metadata adds final_update_complete, computed from finalized and last_updated_count matching unique completed item count.
#### Edge Cases & Error Handling
Fail closed with CODEX_ACCEPTANCE_FAILED on failed requirements, timeout, or check errors. Preserve CancelledError. Keep thread identity and cost tracking after native execution so callers can inspect incurred work; do not append rejected replies or overwrite last_reply.

## 7. Data Model Changes
### 7.1 Acceptance settings/request
**Change type:** New
Frozen records; harness and fork add acceptance option. Continual metadata gains final_update_complete boolean. No persistent migration.

## 8. API Changes
### 8.1 Harness arun/run result boundary
**Change type:** Modified, opt-in
Successful replies include metadata.acceptance={accepted:true,check_count:N}. Rejection raises CodexAgentError with failure_code codex.acceptance_failed. No automatic provider retry or rollback.

## 9. File Change Manifest
| Action | File Path | Reason |
|---|---|---|
| CREATE | docs/design/codex-final-acceptance.md | Design |
| CREATE | vidbyte/agents/codex/acceptance.py | Acceptance enforcement |
| CREATE | tests/codex_acceptance/FEATURE.md | Feature contract |
| CREATE | tests/codex_acceptance/test_acceptance.py | Acceptance cases |
| CREATE | scripts/test-codex-final-acceptance.py | Verification runner |
| MODIFY | vidbyte/lib/dataclasses/codex.py | Typed contracts |
| MODIFY | vidbyte/lib/enums/failure.py | Dedicated error identity |
| MODIFY | vidbyte/agents/codex/config.py | Validate dependencies and schemas |
| MODIFY | vidbyte/agents/codex/agent.py | Gate before success publication |
| MODIFY | vidbyte/agents/codex/continual.py | Actual final boundary receipt |
| MODIFY | vidbyte/agents/codex/fork.py | Inherit/replace settings |
| MODIFY | vidbyte/agents/codex/README.md | API and File Index |
| MODIFY | vidbyte/__init__.py | Public exports |

## 10. Testing Plan
### Unit Tests
- [Edge Case] Zero, boolean, infinite timeout and nonboolean requirements reject.
- [Hidden Assumption] Invalid checks, missing trace configuration, invalid schema, and invalid settings type reject before execution.
- [Silent Failure] Interrupted native result rejects by default and passes only with explicit require_completed=False.
- [Hidden Failure] Stale final trace rejects despite earlier updates; actual completed empty-run update can pass.
- [Edge Case] Required trace fields may legitimately contain zero/False/empty arrays when schema permits them.
- [Silent Failure] Shared schema validation rejects missing or malformed final trace fields.
- [Hidden Failure] False/None check result, exception, and timeout cannot produce success; exception content is withheld.
- [Hidden Assumption] Checks mutate only their own snapshot and cannot forge acceptance for later checks.
- [Hidden Failure] Cancellation propagates without a success receipt.
### Integration Tests
- [Silent Failure] A passing candidate commits history and receipt only after check completion.
- [Hidden Failure] A rejected candidate retains native identity and usage but leaves history and last_reply unchanged.
- [Hidden Assumption] Fork inheritance and replacement preserve requirements; clearing required trace rejects before native fork.
- [Silent Failure] Actual continual bridge metadata distinguishes stale failure from successful finalization.
### Manual / QA Test Cases
Run all cases through the feature script, then lint/source/full package gates. No live model call needed because the deterministic acceptance boundary runs after a native candidate exists.

## 11. Dependencies & External Services
| Dependency | Version / Endpoint | Purpose | Risk |
|---|---|---|---|
| OutputSchemaFormatter | Existing | Final trace schema validation | Same supported constraints as shared output API |
| asyncio | Standard library | Bounded awaited checks | Cooperative cancellation |

## 12. Rollout & Deployment
Opt in with acceptance settings; merge after native tool PR #425. No change for callers omitting acceptance. Roll back by removing that option. Required capture can be supplied as an application check until durable capture integration lands.

## 13. Open Questions
Native effects cannot be rolled back after acceptance rejection. Hooks and durable distillation capture remain subsequent features; neither should be represented as completed by this PR.

## 14. Alternatives Considered
Prompt-only requirements and Stop-hook continuation cannot establish successful artifact publication. Automatically rerunning Codex could repeat effects. A deterministic application gate provides an explicit failure boundary with no hidden retry.
