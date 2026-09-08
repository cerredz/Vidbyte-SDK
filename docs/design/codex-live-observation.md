# Design Doc: Codex Live Observation

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-08
**Last Updated:** 2026-09-08

## 1. Overview

Expose live, typed Codex observations and route native tool lifecycle events through existing Vidbyte tracers. This is the first sequential change; continual artifacts, tool execution, checkpoint enforcement, result acceptance, context feedback, and dataset capture follow separately.

## 2. Goals & Non-Goals

### Goals
- Deterministic awaited observation delivery, optional provider tracing, and safe streamed result collection.
- Preserve absent usage, final-answer phase selection, failure and cancellation semantics.
### Non-Goals
- No fabricated model-call spans, internal iteration interception, durable replay, or native action blocking.

## 3. Background & Context

The current facade has context translation, usage accounting, and outer middleware. Transport calls AsyncThread.run and receives only the final result. Installed openai-codex 0.147.0 exposes AsyncThread.turn and AsyncTurnHandle.stream. Its collector is private; implement a small typed collector against public generated models instead of importing private functions. Field-guide constraints require concrete native contracts, separate translators, validated configuration, and preservation of missing usage and private-reasoning exclusion.

## 4. Requirements

### Functional Requirements
1. Add validated CodexObservationSettings with a TracerBase and awaited observer callbacks; accept it on agent construction and fork overrides.
2. Opted-in runs consume one native stream, preserve event order, and deliver safe observations before processing the next event.
3. Exclude private reasoning content before serialization. Unknown notifications expose only their method and run identity.
4. Emit agent.run and tool.call spans for observed lifecycle events, closing outstanding spans on failure/cancellation. Provider failures remain fail-open; observer failure aborts the run.
5. Validate native thread/turn identity and terminal completion. Preserve completed-item order, final-answer phase preference, timing, missing usage, and failed-turn behavior.
6. Keep the existing unobserved path compatible. Forks inherit observation settings unless explicitly replaced.

### Non-Functional Requirements
- Lazy Codex imports; bounded observation payloads are limited to reviewed item variants.
- Do not accumulate a second full event log in the agent; callbacks own storage.
- Never expose native exception text to tracing. Tracing is best effort; collection requirements can be enforced by observers.

## 5. High-Level Design

Agent settings carry observation configuration to transport. An enabled transport creates a turn handle and delegates its single stream to CodexStreamRunner. CodexEventTranslator produces Vidbyte records; CodexTraceBridge emits existing tracer calls. The runner reconstructs the public TurnResult then uses the existing result serializer.

## 6. Detailed Design

### 6.1 Configuration and records
**Files:** lib/dataclasses/codex.py, lib/enums/codex.py
**Type:** Modified
#### What it does
Defines CodexObservation (sequence, method, thread/turn identity, optional reviewed item) and CodexObservationSettings (tracer and tuple of async callbacks). Records stay in the shared substrate. Add observation settings to harness, fork, and transport records.
#### Interface / API
`CodexObservationSettings(tracer=NullTracer(), observers=())`
`CodexHarnessAgentSettings(..., observation=CodexObservationSettings())`
#### Logic / Algorithm
Validate concrete tracer and tuple/callable shapes at construction; validate callback awaitability when invoked. Default configuration retains the original run path.
#### Edge Cases & Error Handling
Reject malformed settings before native execution; invalid observer return fails the run. Fork None means inherit, an empty settings instance disables.

### 6.2 Stream execution and tracing
**Files:** agents/codex/observation.py, agents/codex/stream.py, agents/codex/transport.py
**Type:** New and modified
#### What it does
Translates reviewed events, records tool lifecycles, and builds the native result from one stream.
#### Interface / API
`CodexStreamRunner.run(thread, request)` is async and returns CodexRunResult.
`CodexEventTranslator.translate(event, identity)` produces CodexObservation.
`CodexTraceBridge.observe(observation)` records lifecycle without raw payload export.
#### Logic / Algorithm
Start native turn; open trace; consume events once; validate routed identities; await each observer; collect completed items and usage; require terminal event; reject failed turns; construct TurnResult and serialize. Close stream and trace in finally. No second stream consumer.
#### Edge Cases & Error Handling
Ignore payloads of unknown events. Exclude reasoning content before any observer. Duplicate starts do not leak spans; unmatched completions do not invent start times. Cancellation unwinds native client. Observer failure propagates through existing CodexAgentError classification.

### 6.3 Public wiring and documentation
**Files:** agents/codex/agent.py, agents/codex/fork.py, vidbyte/__init__.py, agents/codex/README.md
**Type:** Modified and new
#### What it does
Pass settings through and document the exact observation guarantee with a runnable example.
#### Interface / API
Public root imports expose CodexObservation and CodexObservationSettings.
#### Logic / Algorithm
Preserve existing middleware, metrics, and result translation ordering. Fork configuration is resolved before native creation.
#### Edge Cases & Error Handling
No settings leak into native SDK kwargs. An empty override explicitly disables inherited observation.

## 7. Data Model Changes

### 7.1 Codex observation contracts
**Change type:** New and additive fields
In-process dataclasses only; no persistent migration. Revert additive fields on rollback.

## 8. API Changes

Python APIs described in Section 6. N/A - no HTTP endpoints.

## 9. File Change Manifest

| Action | File Path | Reason |
|---|---|---|
| CREATE | docs/design/codex-live-observation.md | Design |
| CREATE | vidbyte/agents/codex/observation.py | Event translation and tracing |
| CREATE | vidbyte/agents/codex/stream.py | Single-consumer collection |
| CREATE | vidbyte/agents/codex/README.md | Usage and boundaries |
| CREATE | tests/codex_observation/FEATURE.md | Behavioral contract |
| CREATE | tests/codex_observation/test_observation.py | Acceptance and failures |
| CREATE | scripts/test-codex-live-observation.py | Named verification runner |
| MODIFY | vidbyte/lib/dataclasses/codex.py | Validated contracts |
| MODIFY | vidbyte/lib/constants/codex.py | Shared sequence increment |
| MODIFY | vidbyte/lib/enums/codex.py | Event vocabulary |
| MODIFY | vidbyte/agents/codex/agent.py | Configuration forwarding |
| MODIFY | vidbyte/agents/codex/transport.py | Native streaming path |
| MODIFY | vidbyte/agents/codex/fork.py | Inherit/replace configuration |
| MODIFY | vidbyte/__init__.py | Public imports |

## 10. Testing Plan

### Unit Tests
- [Edge Case] Invalid tracer, observer tuple, and settings types fail before running.
- [Silent Failure] Private reasoning is excluded before observer delivery; unknown event payloads are absent.
- [Silent Failure] Explicit final_answer outranks later commentary; missing usage stays absent.
- [Hidden Failure] Broken tracer does not abort; outstanding tool spans close on error.
- [Hidden Assumption] Duplicate starts and unmatched completions do not fabricate spans.
- [Hidden Assumption] Fork configuration inherits, replaces, and disables before provider creation.
### Integration Tests
- [Edge Case] Empty stream fails, interrupted text remains absent, zero usage stays available.
- [Hidden Failure] Observer error and cancellation close the stream and trace.
- [Silent Failure] Awaited callbacks receive ordered identities and completed item fields; one callback cannot mutate another callback or the native result.
- [Hidden Failure] Semantic profiles preserve explicit parentage for native tool spans.
- [Hidden Assumption] Wrong thread/turn, failed terminal event, and synchronous observer fail explicitly.
- [Hidden Assumption] Actual pinned SDK model instances prove event/result contracts; transport wiring invokes native turn only when enabled.
### Manual / QA Test Cases
Run scripts/test-codex-live-observation.py with per-case PASS/FAIL, source CI, and full CI. Live provider execution is optional and is not claimed by offline verification.

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|---|---|---|---|
| openai-codex | >=0.147.0,<0.148.0 | Native stream | Optional package and generated contract drift |

## 12. Rollout & Deployment

Opt in through observation settings. Preserve the unobserved path. Revert the feature commit to roll back; no migration. Later sequential PRs depend on this event contract and remain separately reviewable.

## 13. Open Questions

No unresolved question blocks this slice. Native event observation is not internal model-call observability. Later hook coverage requires pinned-binary validation.

## 14. Alternatives Considered

### Alternative 1: Private SDK collector
- Rejected because private functions can change independently of public result contracts.
### Alternative 2: Poll final thread history
- Rejected because it loses live scheduling and permits missing intermediate observations.

## Refinement Checklist

No unresolved gaps in this slice. The review added callback mutation isolation and semantic-parentage tests. Native streaming is opt-in, shares existing output normalization, and does not claim a native execution barrier. The manifest adds one shared-constant file modification for the sequence increment. Observer schemas carry reviewed items only; full native payload export remains outside this contract.
