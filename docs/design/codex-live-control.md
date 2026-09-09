# Design Doc: Codex Live Control

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-09
**Last Updated:** 2026-09-09

## 1. Overview
Expose a per-turn control handle for injecting text feedback and requesting interruption while Codex runs. Both operations call the actual native SDK, preserving its thread/turn identity and acknowledgment semantics.

## 2. Goals & Non-Goals
### Goals
- Provide awaited native steering and interruption for ordinary and tool-enabled runs.
- Publish the handle when a turn starts and deactivate it on completion, failure, or cancellation.
- Reject stale handles and invalid steering input; bound command waits.
### Non-Goals
- Replace arbitrary native context, promise exact next-action timing, undo effects, or force tool calls.
- Add multimodal steering; initial run inputs retain their existing modalities.

## 3. Background & Context
The pinned AsyncTurnHandle exposes steer(input) and interrupt(). Public CodexClient provides equivalent turn_steer(thread_id, expected_turn_id, input_items) and turn_interrupt(thread_id, turn_id). Observation alone cannot affect native execution; these operations send real native requests. The existing collector provides one native stream and cleanup boundary. Control callbacks must return after registering or issuing immediate commands, rather than await the whole turn.

## 4. Requirements
### Functional Requirements
1. Add optional CodexControlSettings(on_ready, timeout_seconds=60) to harness and transport records; forks inherit or replace it.
2. Deliver one CodexRunControl handle after native turn creation. It exposes thread_id, turn_id, active, async steer(text), and async interrupt().
3. Steering calls native steer with text and validates the acknowledged turn ID. Interruption calls native interrupt; acknowledgment means a request was accepted, not that effects were undone.
4. Serialize concurrent control commands and bound each SDK wait. Reject blank/nonstring feedback, closed handles, native errors, mismatched acknowledgment, and timeout with a dedicated code.
5. Enable streaming when control alone is configured. Deactivate before delivering the terminal observation and in all failure/cancellation paths.
6. Support the ordinary high-level SDK and the public low-level tool transport without private SDK calls.
7. Await on_ready; callback errors abort the run and deactivate the handle. Apply its timeout to avoid an indefinitely blocked collector.
### Non-Functional Requirements
Opt-in preserves existing unobserved run behavior. Cancellation retains asyncio semantics. No raw provider errors or feedback text appear in control errors. Control commands cannot replace native context. A tool callback must not issue requests on its own blocking native connection.

## 5. High-Level Design
CodexStreamRunner binds CodexRunControl around the actual turn handle, invokes on_ready, and then collects notifications. The existing low-level native stream adapter gains public steer and interrupt methods. A shared controller serializes commands, checks lifecycle and acknowledgment, and reports bounded native failures. The facade passes settings; fork construction resolves inherited policy.

## 6. Detailed Design
### 6.1 Configuration and facade
**Files:** lib/dataclasses/codex.py, config.py, agent.py, fork.py, transport.py, vidbyte/__init__.py
**Type:** Modified
#### What it does
Carries and validates optional control settings before native resources are created.
#### Interface / API
`CodexControlSettings(on_ready: Callable[[CodexRunControl], Awaitable[None]], timeout_seconds: float = 60.0)`
Harness/transport `control: CodexControlSettings | None`; fork override None inherits.
#### Logic / Algorithm
Validate callback and finite positive timeout; forward settings; select stream when configured.
#### Edge Cases & Error Handling
Invalid collaborators reject before startup. Every run creates a separate handle, so concurrent agents cannot share control identity.

### 6.2 Controller
**Files:** agents/codex/control.py, lib/enums/failure.py
**Type:** New and modified
#### What it does
Owns one native turn's command and lifecycle boundary.
#### Interface / API
`CodexRunControl(thread_id, turn_id, native, timeout_seconds)`
`async steer(text: str) -> None`; `async interrupt() -> None`; `close() -> None`; `active: bool`.
#### Logic / Algorithm
Validate text, acquire the SDK AsyncCapacityLimiter, check active state, await the corresponding native method with a timeout, and verify steering response turn_id equals the expected ID. Recheck active after acknowledgment so a late response cannot look like live-turn success. close invalidates new and late command results.
#### Edge Cases & Error Handling
Raise CODEX_CONTROL_FAILED with operation/error_type only. Cancellation propagates. Pending commands are bounded; close does not cancel unrelated application tasks that issued them. Native completion can race a command and is reported as a control error rather than silently retargeting another turn.

### 6.3 Stream lifetime and low-level SDK
**Files:** stream.py, native_tools.py
**Type:** Modified
#### What it does
Creates/invalidates controller at actual native turn boundaries and retains one event consumer.
#### Interface / API
Collector accepts a native handle supporting stream, steer, and interrupt when control is configured. Low-level adapter translates text through CodexClient.turn_steer and forwards exact thread/turn IDs for interrupt.
#### Logic / Algorithm
Before collecting, invoke on_ready once with bounded wait. On terminal event invalidate before observers run. Finally invalidate again and close the stream, including readiness failure. Low-level native transport delegates this same collector path.
#### Edge Cases & Error Handling
Readiness callbacks must not wait for collector completion. A stale handle never controls a resumed/forked turn. Terminal interruption remains subject to final acceptance settings.

### 6.4 Shared capacity boundary
**Files:** lib/util/concurrency.py, lib/util/__init__.py, lib/util/README.md
**Type:** New and modified
#### What it does
Owns SDK asynchronous concurrency admission without the prohibited asyncio.Lock API.
#### Interface / API
`AsyncCapacityLimiter(capacity: int = 1)` is an async context manager backed by asyncio.BoundedSemaphore.
#### Logic / Algorithm
Validate positive nonboolean integer capacity; await admission on entry and return one permit on exit. Codex uses capacity one to serialize commands.
#### Edge Cases & Error Handling
Cancelled waiters must not release a permit they never acquired. Exceptions inside an admitted operation release its permit. Tests cover both.

## 7. Data Model Changes
### 7.1 Control settings
**Change type:** New
Frozen settings and optional harness/fork/transport fields. No persistent schema or migration. Controller is an ephemeral runtime collaborator, never serialized.

## 8. API Changes
### 8.1 Native live control
**Change type:** New
on_ready receives the handle; steer adds feedback to the active native turn, interrupt requests interruption. Operations raise codex.control_failed on invalid state or native failure. Native output remains authoritative; no synthetic interrupted result is created.

## 9. File Change Manifest
| Action | File Path | Reason |
|---|---|---|
| CREATE | docs/design/codex-live-control.md | Design |
| CREATE | vidbyte/agents/codex/control.py | Live native control |
| CREATE | vidbyte/lib/util/concurrency.py | Shared SDK async capacity boundary |
| CREATE | vidbyte/lib/util/README.md | Shared helper File Index |
| MODIFY | vidbyte/lib/util/__init__.py | Export shared capacity limiter |
| CREATE | tests/codex_control/FEATURE.md | Feature contract |
| CREATE | tests/codex_control/test_control.py | Acceptance cases |
| CREATE | scripts/test-codex-live-control.py | Verification script |
| MODIFY | vidbyte/lib/dataclasses/codex.py | Settings |
| MODIFY | vidbyte/lib/enums/failure.py | Dedicated error |
| MODIFY | vidbyte/agents/codex/config.py | Configuration validation |
| MODIFY | vidbyte/agents/codex/agent.py | Forward settings |
| MODIFY | vidbyte/agents/codex/fork.py | Inherit/replace |
| MODIFY | vidbyte/agents/codex/transport.py | Control enables streaming |
| MODIFY | vidbyte/agents/codex/stream.py | Handle lifecycle |
| MODIFY | vidbyte/agents/codex/native_tools.py | Public SDK control calls |
| MODIFY | vidbyte/agents/codex/README.md | API and File Index |
| MODIFY | vidbyte/__init__.py | Public exports |

## 10. Testing Plan
### Unit Tests
- [Edge Case] Invalid callback and zero/boolean/nonfinite timeout reject.
- [Edge Case] Empty/blank/nonstring steering input rejects before native calls.
- [Silent Failure] Real native response model with correct ID acknowledges steer and preserves exact feedback.
- [Hidden Failure] Wrong turn acknowledgment, SDK exceptions, timeout, and cancellation cannot report success.
- [Hidden Assumption] Closed handles and commands completing after close cannot operate successfully.
- [Hidden Failure] Concurrent controls execute serially without retargeting.
- [Hidden Failure] SDK capacity limiter retains exact capacity after waiting-task cancellation and an admitted operation exception.
### Integration Tests
- [Silent Failure] Control-only configuration chooses streaming and on_ready can issue native steering/interruption.
- [Hidden Failure] Readiness exception or timeout closes the handle and stream.
- [Hidden Assumption] Terminal observers see an inactive handle, and collector failures invalidate it.
- [Silent Failure] Low-level native adapter forwards exact thread/turn identities and feedback to public SDK methods.
- [Hidden Assumption] Fork inheritance/replacement and facade forwarding retain the control policy.
### Manual / QA Test Cases
Run every case through the feature script, then lint/source/full package gates. No paid model calls: native request methods and actual acknowledgment models are exercised offline.

## 11. Dependencies & External Services
| Dependency | Version / Endpoint | Purpose | Risk |
|---|---|---|---|
| openai-codex | >=0.147.0,<0.148.0 | Native steer/interrupt | Native timing is asynchronous |
| asyncio | Standard library | Capacity limiting and bounded waits | Cooperative callbacks |

## 12. Rollout & Deployment
Opt-in control settings; merge after #426. Removing the setting restores prior path. Existing native output and final acceptance rules remain authoritative.

## 13. Open Questions
No unresolved implementation decisions. Exact next-action timing and native context replacement are not offered by these SDK operations.

## 14. Alternatives Considered
Observer-only feedback stays outside the model. Editing local ContextManager state does not replace Codex-owned context. The actual steer request provides the supported supplemental-input behavior, with explicit acknowledgment and lifecycle limits.

## Refinement Checklist

- [x] [Notable] **SDK concurrency ownership**
  Expected: concurrency belongs to the SDK shared boundary. The repository bans asyncio.Lock but this checkout had no replacement helper. Added AsyncCapacityLimiter under lib/util, using bounded permit admission with cancellation/exception tests, and used capacity one for native commands. The policy and baseline remain unchanged.
- [x] [Notable] **Readiness failure before stream opening**
  Expected: no leaked capability or native resource when on_ready fails. Readiness runs before the stream opens, so the outer transport closes the native client and its registered queues. An integration case now verifies client exit in addition to handle deactivation; no unopened generator is represented as having run cleanup.

Feature verification passed 12/12; repository lint passed; source CI passed 1775 tests with one existing optional skip. The updated manifest includes the shared utility owner and folder index.
Full local CI also passed, including wheel/sdist validation and isolated installed-package smoke checks.
