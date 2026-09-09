# Design Doc: Codex Trajectory Capture

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-09
**Last Updated:** 2026-09-09

## 1. Overview
Export reviewed native Codex trajectories through the existing Vidbyte TrajectoryRecord and TrajectorySink interfaces. Capture is opt-in, includes visible inputs/items/final artifacts, and can be required before the harness publishes a successful reply.

## 2. Goals & Non-Goals
### Goals
- Reuse existing file/memory/custom trajectory sinks for distillation-ready observed records.
- Record success, failure, cancellation, actual native identities, trace artifacts, and bounded observation windows.
- Apply existing credential-key redaction plus common free-text credential-assignment redaction before export.
- Await required export before history publication and expose explicit capture receipts.
### Non-Goals
- Export hidden reasoning, reconstruct unseen native prompts or model iterations, invent rewards, or train models.
- Pretend Codex observations are a resumable Vidbyte Session snapshot. Native thread storage remains authoritative; Session persistence stays unsupported.
- Guarantee complete PII/secret detection or recover events after process crashes.

## 3. Background & Context
Existing harness distillation joins Session checkpoints into TrajectoryRecord and writes an opted-in TrajectorySink. Codex owns its context and cannot provide the required resumable RunState. Its reviewed event stream can still populate the same export record contract with explicit capture_scope and missing-data limits. Reuse the sink and redaction APIs rather than inventing another dataset format or fabricating Session state. Existing HarnessRedactor drops credential-like keys but leaves ordinary strings unchanged; its public safe_error_message method handles common free-text credential assignments and is applied without truncating normal strings.

## 4. Requirements
### Functional Requirements
1. Add optional CodexCaptureSettings(sink, required=True, max_observations=100, timeout_seconds=60, redactor=None). Configuring capture is explicit opt-in export consent; no export occurs when omitted.
2. Validate sink contract, booleans, positive observation bound, callback, and finite timeout before native execution.
3. Capture only reviewed CodexObservation snapshots from the existing stream, bounded by max_observations with a visible dropped-event count.
4. Export one TrajectoryRecord per invocation, including a unique run ID, actual translated prompt when available, reviewed native events, candidate output, final trace, selected nonsecret behavior settings, and status. reward is None; label scope as observed native events, not full internal model context.
5. Exclude native process env/config/credentials from the specification. Apply mandatory baseline key redaction and free-text assignment scrubbing to every exported section. Apply optional tenant redaction before the baseline.
6. Await sink.write with a bounded timeout. Required export failure raises CODEX_CAPTURE_FAILED and does not append history or publish last_reply; optional failure returns an explicit failed capture receipt.
7. Failure/cancellation recording is best effort and cannot replace the primary exception. Never perform a second write when a success-record write fails ambiguously; consumers deduplicate by run ID if retrying storage outside this adapter.
8. Forks inherit or explicitly replace capture settings; each invocation gets separate IDs/windows. Omission preserves existing behavior.
### Non-Functional Requirements
No native private data or invented model-step records. The native provider remains execution authority. Cooperative sink cancellation does not guarantee a timed-out physical write was undone; receipt accurately reports lack of acknowledgment. Dataset completeness is bounded and explicit.

## 5. High-Level Design
The facade arun wrapper creates a per-invocation CodexTrajectoryCapture, invokes the existing candidate pipeline, awaits final export, then commits history/last_reply. The candidate pipeline adds the capture observer alongside tracing, provides translated prompt and final candidate evidence, and retains existing acceptance logic. Capture formats a shared TrajectoryRecord and writes through the caller's existing TrajectorySink. A separate translator owns specification projection and recursive redaction.

## 6. Detailed Design
### 6.1 Settings and facade lifetime
**Files:** lib/dataclasses/codex.py, agents/codex/config.py, agent.py, fork.py, vidbyte/__init__.py
**Type:** Modified
#### What it does
Defines capture settings, validates collaborators, forwards actual prompt/candidate evidence, and moves successful history publication after required export.
#### Interface / API
`CodexCaptureSettings(sink: TrajectorySink, required: bool = True, max_observations: int = 100, timeout_seconds: float = 60.0, redactor: Callable[[Any], Any] | None = None)`
Harness/fork `capture: CodexCaptureSettings | None`; fork None inherits.
#### Logic / Algorithm
Create capture per arun. A candidate helper returns reply and translated prompt text; capture receives prompt after context translation and candidate before acceptance. Await final sink receipt, then update history/last_reply/last_prompt. Catch failures around candidate work only so ambiguous sink failure never triggers a duplicate failure write.
#### Edge Cases & Error Handling
Pre-native failures can produce diagnostic records with no native identity. Rejected acceptance candidates are labeled failed. Caller cancellation is re-raised after best-effort bounded recording. Existing native identity and usage accounting remain available after capture rejection.

### 6.2 Capture and shared sink
**Files:** agents/codex/capture.py, lib/enums/failure.py
**Type:** New and modified
#### What it does
Maintains bounded reviewed observations and writes one final shared export unit.
#### Interface / API
`CodexTrajectoryCapture.observe(event)`; `set_prompt(prompt)`; `set_candidate(reply)`; `finish(reply) -> AgentMessage`; `failed(error) -> None`.
#### Logic / Algorithm
Assign UUID once; retain the latest bounded events and count discarded events. Build a record with actual status and no reward. Write once per invocation with wait_for. Return metadata.capture containing run_id, saved, observed_event_count, dropped_event_count, and optional error_type. Required failure raises safe CodexAgentError; failure-path recording remains best effort.
#### Edge Cases & Error Handling
Snapshot nested values to prevent callback mutation. Truncated windows explicitly report incompleteness. Never infer unavailable model prompts, private reasoning, hidden tool deltas, or full native context. Sink timeout is unacknowledged export, not proof that storage rolled back.

### 6.3 Export translator and redaction
**Files:** agents/codex/capture_format.py
**Type:** New
#### What it does
Builds a shared TrajectoryRecord with reviewed scope and one mandatory export-redaction boundary.
#### Interface / API
`CodexTrajectoryFormatter.record(...) -> TrajectoryRecord` and recursive `redact(value)`.
#### Logic / Algorithm
Project only selected public behavior: agent name/system instructions, native model/sandbox/approval values, tool declarations, and trace schema. Never serialize the client settings or arbitrary process config. Apply optional tenant redactor, then HarnessRedactor.redact, then recursively scrub string credential assignments with the shared public redaction method. Preserve empty strings and legitimate empty values.
#### Edge Cases & Error Handling
Unsupported objects use the shared dropped markers. Invalid tenant redaction/sink behavior is a capture failure, not silent raw export. Existing sink implementations determine persistence guarantees.

## 7. Data Model Changes
### 7.1 Capture settings
**Change type:** New
Frozen capture settings and harness/fork options. Export reuses TrajectoryRecord unchanged, labeling agents as native observed turns rather than stored Session checkpoints. No new database or Session schema.

## 8. API Changes
### 8.1 Harness capture receipt
**Change type:** New, opt-in
Successful reply metadata.capture reports saved and run_id. Required sink failure raises codex.capture_failed before successful publication. Original failure/cancellation remains the primary exception if diagnostic export also fails.

## 9. File Change Manifest
| Action | File Path | Reason |
|---|---|---|
| CREATE | docs/design/codex-trajectory-capture.md | Design |
| CREATE | vidbyte/agents/codex/capture.py | Per-run observation/export lifecycle |
| CREATE | vidbyte/agents/codex/capture_format.py | Shared record projection and redaction |
| CREATE | tests/codex_capture/FEATURE.md | Feature contract |
| CREATE | tests/codex_capture/test_capture.py | Capture acceptance cases |
| CREATE | scripts/test-codex-trajectory-capture.py | Verification runner |
| MODIFY | vidbyte/lib/dataclasses/codex.py | Typed settings |
| MODIFY | vidbyte/lib/enums/failure.py | Dedicated capture failure |
| MODIFY | vidbyte/agents/codex/config.py | Validate sink and settings |
| MODIFY | vidbyte/agents/codex/agent.py | Candidate/capture/publication ordering |
| MODIFY | vidbyte/agents/codex/fork.py | Inherit/replace capture |
| MODIFY | vidbyte/agents/codex/README.md | Capture API, scope, File Index |
| MODIFY | vidbyte/__init__.py | Public settings export |

## 10. Testing Plan
### Unit Tests
- [Edge Case] Invalid sink, timeout, boolean/window bounds, and redactor reject before execution.
- [Silent Failure] Export schema, native IDs, reward=None, and observed-only scope match actual evidence.
- [Edge Case] Empty events and zero/False/empty string values remain valid.
- [Hidden Failure] Bounded windows count dropped events without silently claiming complete capture.
- [Hidden Assumption] Nested caller mutations cannot alter previously captured observations.
- [Hidden Failure] Process env/config never enters export; secret keys and common text assignments are scrubbed, including custom redactor output.
- [Hidden Failure] Sink exception/timeout required versus optional behavior produces accurate receipts without duplicate writes.
### Integration Tests
- [Silent Failure] Real FileTrajectorySink writes readable JSONL using existing TrajectoryRecord.
- [Hidden Failure] Required capture finishes before history publication; failure preserves prior accepted reply.
- [Hidden Assumption] Native failure, acceptance rejection, and cancellation retain their original error if diagnostic capture also fails.
- [Silent Failure] Capture-only configuration enables streaming via its observer; no capture setting means no sink calls.
- [Hidden Assumption] Forks inherit/replace configuration but each run gets isolated IDs and windows.
### Manual / QA Test Cases
Run all design cases through the script, then repository lint/source/full package gates. Inspect one temporary JSONL record for explicit missing-data scope. No paid native model or training call is required.

## 11. Dependencies & External Services
| Dependency | Version / Endpoint | Purpose | Risk |
|---|---|---|---|
| TrajectoryRecord/TrajectorySink | Existing | Shared distillation export format/storage | Sink-specific persistence semantics |
| HarnessRedactor | Existing | Mandatory baseline redaction | Not exhaustive PII detection |

## 12. Rollout & Deployment
Opt-in capture setting. Reuse FileTrajectorySink, InMemoryTrajectorySink, or caller sink. Merge after live control. Removing capture disables export. Native Session persistence remains unsupported; records explicitly state observed-only scope.

## 13. Open Questions
Hidden native model inputs/context cannot be reconstructed from public events. No guarantee of full trajectory fidelity or exhaustive secret detection is made. Native hook enforcement remains the next feature.

## 14. Alternatives Considered
Fabricating a resumable RunState would misrepresent native context ownership. A new dataset/sink format would fragment existing tooling. Reusing the existing record and sink with explicit native observation scope supports downstream distillation without either error.
