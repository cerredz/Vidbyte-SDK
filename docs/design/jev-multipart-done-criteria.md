# Design Doc: Jev Multipart Done Criteria

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-24
**Last Updated:** 2026-09-24

---

## 1. Overview

Add an opt-in multipart done-criteria preset to `JevAgent`. When enabled, one generative sub-agent turns the original request into a stable structured run state before the main loop; at each normal finish attempt, another generative sub-agent maps the run's observed progress to the requested deliverables. The Jev runtime asks one narrow recognition question per deliverable and continues the same agent loop with concrete gaps when any part is not confidently complete. The default agent path remains unchanged when the preset is absent.

---

## 2. Goals & Non-Goals

### Goals

- Expose the named opt-in as `JevAgent(settings, done_criteria=JevPresets.MultiPart)` and through `sdk.agents.jev(...)`.
- Generate one structured state object per run, containing `goal`, `objective`, `mission`, `what_not_to_do`, and named `sections`; the multipart preset adds a `multi_part` section describing the requested deliverables and their observable completion signals.
- Build a strict structured handoff at every normal finish attempt from the original request, initial state, iteration outputs, tool call records, and candidate final output.
- Validate that the handoff contains every generated deliverable exactly once and no unknown IDs before asking Jev.
- Ask Jev one binary question per deliverable using a state containing that deliverable's criterion and its corresponding handoff entry.
- Continue the existing loop with an explicit list of incomplete deliverables; return only after all clear the fixed probability threshold.
- Keep orchestration run-local, keep Jev provider payloads in existing decision records/adapters, and expose decision outcomes in final result metadata.
- Keep the feature disabled by default and preserve ordinary `BaseAgent` behavior.

### Non-Goals

- Do not generate or store a global list of obligations for every Jev run; the deliverable list exists only inside the opt-in multipart state section.
- Do not ask Jev to infer request scope, count items, identify missing items, summarize a transcript, or otherwise reason. Generative builders and deterministic runtime code do those jobs.
- Do not add per-tool intent prompts, turn-level evidence classification, or a persistent evidence index in this change.
- Do not expose arbitrary Jev questions, thresholds, callbacks, runtime hooks, or custom preset registration.
- Do not use private chain-of-thought as state or handoff content.
- Do not change non-Jev runtimes, session persistence, or the public decision provider wire contract.

---

## 3. Background & Context

`JevAgent` currently wraps one immutable `JevAgentSettings` object and fixes the runtime to `AgentRuntimeType.JEV`. `JevRuntime` inherits the direct runtime loop unchanged. The TypeSafe `DecisionModelRunner` accepts structured `JevDecisionRequest` records and returns calibrated `JevAnswer` records; the Jev scaffold does not yet call it from the agent runtime.

Multipart completion cannot be established by a single artifact or tool call. The accepted design builds a run-level state once from the user request, then builds an end-of-attempt handoff that explains what the run did in relation to that state. Jev only recognizes each explicitly described deliverable against its corresponding handoff entry. Missing work is fed back to the main generative agent while the original runtime loop is still active.

The ordinary runtime has two normal completion boundaries: an unstructured final response and the `isDone` tool. A protected finish-attempt hook in `AgentRuntime` is required at those boundaries; `after_run` runs after the loop and cannot continue it. Existing `HandoffAgent` is not reused because it intentionally degrades invalid structured output to prose, while this capability must reject incomplete or mismatched handoff records.

---

## 4. Requirements

### Functional Requirements

1. `JevAgent` accepts `done_criteria: JevPresets | None` as a named keyword-only capability; `None` leaves current execution unchanged.
2. With `JevPresets.MultiPart`, the runtime invokes a dedicated state-builder subclass exactly once before the main generative loop, using the original request and a strict schema.
3. The generated state has stable top-level `goal`, `objective`, `mission`, `what_not_to_do`, and `sections` fields. The multipart section contains zero or more uniquely identified deliverables with a plain description and an observable completion signal.
4. At each normal finish attempt, a dedicated handoff-builder subclass receives the original request, generated state, accumulated iteration outputs, recorded tool-call contexts, candidate final output, and stable evidence-source IDs; it returns one structured entry for every deliverable.
5. Each handoff evidence excerpt cites a source ID and copies an exact substring from that source. Runtime validation rejects missing, duplicate, or unknown handoff IDs, unknown evidence sources, invented excerpts, and malformed required content; prose fallback does not satisfy the handoff contract.
6. The done-criteria policy sends exactly one `NOUL` question per deliverable, with only that deliverable's description, completion signal, and handoff entry in the Jev state. The question defines completion in observable terms and asks whether the handoff explicitly shows that condition.
7. Each deliverable passes only when `P(true)` is at least the named fixed multipart threshold. A missing/low-confidence item yields concrete continuation feedback naming that item and the evidence gap.
8. Incomplete attempts continue inside the same `AgentRuntime` loop, preserving existing counters, tool history, middleware lifecycle, context handling, and run-local state.
9. Once all deliverables pass, the runtime returns the candidate final result with a `done_criteria` metadata record containing the preset, deliverable IDs, probabilities, and attempt count.
10. State-builder, handoff-builder, malformed-result, and TypeSafe failures are explicit failures; they must never silently turn into an accepted completion.
11. Calls to `JevAgent` without the preset, ordinary `BaseAgent` construction, and standard runtime resolution retain current behavior.

### Non-Functional Requirements

- Extra generative calls are bounded to one state build per enabled run and one handoff build per finish attempt; no state regeneration occurs during continuation.
- Each Jev request contains one deliverable and its corresponding source-linked evidence to avoid requiring Jev to search or combine a large run transcript.
- The handoff builder receives the complete captured run snapshot. Oversized input fails through the configured generative provider; runtime does not silently truncate observations or accept a partial handoff.
- Reuse the source agent's runner cache/configuration for internal generative subclasses; keep main-agent usage and speed tracking semantics intact.
- Merge internal generative builder usage records into the source JevAgent's run-owned usage rollup exactly once.
- Do not pass Jev provider configuration or API keys into generated state, handoff, logs, or result metadata. User request and tool output text remain model supplied content.
- Runtime and intermediate records are scoped to one `arun` invocation to prevent cross-run contamination.
- Provider failures propagate with their existing typed error behavior; no implicit fail-open completion.

---

## 5. High-Level Design

`JevPresets` is a closed public enum with `MultiPart`; `JevAgent` accepts it as a keyword-only `done_criteria` choice and passes it with its validated settings through the existing runtime-extension seam. When absent, `JevRuntime` delegates directly to the existing runtime. When selected, the runtime creates `MultiPartStateBuilderAgent`, a `BaseAgent` subclass that uses the source agent's runner cache and strict output schema to produce the structured state once from the original request.

At each normal finish attempt, `MultiPartHandoffBuilderAgent` receives the complete captured run snapshot and emits a handoff keyed to the generated deliverable IDs. Its evidence entries cite stable IDs for iteration output, tool-call records, or the candidate final answer. The runtime verifies each cited excerpt occurs exactly in that run snapshot before Jev sees it. The policy then constructs one `JevDecisionRequest` per deliverable and classifies only its associated evidence. A low or missing probability adds precise gap feedback to the current messages and tells the parent loop to continue; complete answers return through normal result finalization. The direct runtime gains a protected default no-op hook invoked only at its two normal completion boundaries.

```text
JevAgent(settings, done_criteria=MultiPart)
    -> JevRuntime.arun
       -> MultiPartStateBuilderAgent (once, original request)
       -> AgentRuntime loop
          -> normal finish attempt
             -> MultiPartHandoffBuilderAgent (request + state + run snapshot)
             -> one Jev NOUL question per deliverable
             -> complete: normal finalization
             -> gaps: append feedback, continue same loop
```

---

## 6. Detailed Design

### 6.1 Preset and public agent configuration

**File(s):** `vidbyte/agents/jev/presets.py`, `vidbyte/agents/jev/agent.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `vidbyte/agents/client.py`
**Type:** [New file | Modified]

#### What it does

Adds the named `JevPresets.MultiPart` API and passes the choice into each runtime instance. The existing `JevAgentSettings` continues to own generative and decision model configuration; the new constructor keyword represents a capability choice, not a replacement settings object.

#### Interface / API

```python
class JevPresets(str, Enum):
    MultiPart = "multi_part"

class JevAgent(BaseAgent):
    def __init__(self, settings: JevAgentSettings, *, done_criteria: JevPresets | None = None) -> None: ...
```

#### Logic / Algorithm

1. Validate the existing settings object as today.
2. Validate `done_criteria` as `None` or `JevPresets`; reject strings and unknown values.
3. Retain the capability selection on `JevAgent` and pass it in `_runtime_extension_kwargs()` with the settings.
4. Update `AgentClient.jev` and exports to preserve the same capability surface.

#### Edge Cases & Error Handling

- `None` does not invoke state generation or Jev.
- Unsupported raw strings fail at construction with `ConfigurationError`.
- The decision key remains lazily resolved until an enabled capability actually classifies.

### 6.2 Typed multipart run state and handoff

**File(s):** `vidbyte/agents/jev/run_state.py`
**Type:** [New file]

#### What it does

Defines immutable run-local records and deterministic schema/validation helpers for the state builder and handoff builder. This is capability-owned application data, so it stays under `vidbyte/agents/jev/` rather than changing provider wire records.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class JevDeliverable: ...
@dataclass(frozen=True, slots=True)
class JevRunState: ...
@dataclass(frozen=True, slots=True)
class JevDeliverableHandoff: ...
@dataclass(frozen=True, slots=True)
class JevRunHandoff: ...
```

#### Logic / Algorithm

1. Parse structured state output and validate required top-level fields and string content.
2. Validate multipart deliverable IDs as non-empty, unique identifiers; allow an empty tuple when the original request has no distinct deliverables.
3. Build a handoff JSON schema with required properties for the known IDs and source-reference fields.
4. Validate the returned handoff's ID set exactly matches state IDs and every evidence excerpt matches a registered snapshot source verbatim.

#### Edge Cases & Error Handling

- Empty multipart requests pass vacuously without making Jev requests.
- Duplicate/missing/extra IDs or invented source citations raise `OutputSchemaViolationError` before classification.
- Model output that has the right outer JSON but blank content is rejected.

### 6.3 Role-specific generative builder subclasses

**File(s):** `vidbyte/agents/jev/builders.py`, `vidbyte/prompts/prompts/jev/jev.json`, `vidbyte/prompts/prompts/jev/state_builder.md`, `vidbyte/prompts/prompts/jev/handoff_builder.md`, `vidbyte/lib/enums/prompts.py`, `vidbyte/prompts/README.md`
**Type:** [New file | Modified]

#### What it does

Defines `MultiPartStateBuilderAgent(BaseAgent)` and `MultiPartHandoffBuilderAgent(BaseAgent)`. Each has one role and a strict output schema. Both reuse the configured generative runner by copying the source agent's runner cache and preserve standard provider/model configuration.

#### Interface / API

```python
class MultiPartStateBuilderAgent(BaseAgent):
    def __init__(self, *, source_agent: BaseAgent, settings: JevAgentSettings) -> None: ...
    async def build_state(self, request: str) -> JevRunState: ...

class MultiPartHandoffBuilderAgent(BaseAgent):
    def __init__(self, *, source_agent: BaseAgent, settings: JevAgentSettings, state: JevRunState) -> None: ...
    async def build_handoff(self, snapshot: JevRunSnapshot) -> JevRunHandoff: ...
```

#### Logic / Algorithm

1. The state builder receives the original request, names the overall goal/objective/mission, what not to do, useful sections, and (when requested) a multipart deliverables section with observable criteria.
2. State-builder instructions forbid hidden chain-of-thought and require preserving distinct requested outputs rather than collapsing them into one headline.
3. The handoff builder receives the original request, the frozen state object, all captured iteration outputs, tool call names/arguments/results/states, candidate final answer, and deterministic evidence-source IDs.
4. Its instructions require one entry per state deliverable, exact source-linked excerpts for evidence, and a clear remaining-work field; it may not invent evidence or silently omit deliverables.
5. Structured output and record validation are mandatory; unlike `HandoffAgent`, no prose fallback is allowed.

#### Edge Cases & Error Handling

- Zero deliverables skips handoff generation and Jev classification.
- Schema violation, unknown source ID, or excerpt absent from the cited source propagates; no partial handoff is accepted.
- The internal builder agent has no tools and cannot recursively create its own Jev state.

### 6.4 Runtime loop finish-attempt extension

**File(s):** `vidbyte/agents/runtime.py`
**Type:** [Modified]

#### What it does

Adds a protected no-op finish-attempt hook to `AgentRuntime`, called at normal final-response and `isDone` boundaries after existing output-contract checks. The direct runtime remains behaviorally identical by default; `JevRuntime` overrides the hook to classify multipart completion and request another iteration when gaps remain.

#### Interface / API

```python
async def _continue_finish_attempt(self, result: AgentResult, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> bool: ...
```

#### Logic / Algorithm

1. Call the hook immediately before normal finalization at each standard completion boundary.
2. If false, retain current `_finish_result` behavior.
3. If true, the subclass has appended feedback to `messages`; continue the existing `while` loop with its current run-local counters, contexts, middleware, and context manager.
4. Leave budget stops, middleware aborts, tool failures, and output-contract exhaustion on their current terminal paths.

#### Edge Cases & Error Handling

- `BaseAgent` and unrelated runtime subclasses use the default `False` path.
- Hook provider failures propagate through the existing `arun` exception path; the runtime does not return a false success.
- The output-contract retry logic remains earlier in the finish sequence and keeps its existing accounting.

### 6.5 Multipart policy and JevRuntime orchestration

**File(s):** `vidbyte/agents/jev/runtime.py`, `vidbyte/agents/jev/run_state.py`, `vidbyte/lib/constants/jev.py`
**Type:** [Modified]

#### What it does

Uses `JevRuntime` as lifecycle coordinator and a `MultiPartDoneCriteriaPolicy` class for snapshot rendering, request creation, result interpretation, continuation feedback, and metadata. `JevRuntime.arun` creates the initial state once and owns it for the attempt; its finish hook delegates to the policy.

#### Interface / API

```python
class MultiPartDoneCriteriaPolicy:
    async def evaluate(self, source_agent: BaseAgent, state: JevRunState, snapshot: JevRunSnapshot) -> JevDoneCriteriaDecision: ...

class JevRuntime(AgentRuntime):
    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult: ...
```

#### Logic / Algorithm

1. With no preset, delegate directly to `AgentRuntime.arun`.
2. With `MultiPart`, build state once from `message` using the source model runner.
3. At a finish attempt, render the complete run snapshot from original message, immutable state, `iteration_outputs`, recorded tool contexts, and candidate result.
4. Generate and strictly validate the handoff; for each deliverable, create one `JevDecisionRequest` containing only that deliverable's state and handoff record.
5. Construct `DecisionModelRunner` from `JevAgentSettings.decision`, classify, and compare `answer.noul` to `JEV_MULTIPART_DONE_THRESHOLD = 0.8`. Missing source-linked evidence cannot pass even when Jev's probability is high.
6. Save per-deliverable probabilities and attempt count to the runtime's result-metadata channel.
7. If any item is below threshold, append the candidate answer where necessary and user feedback naming each incomplete deliverable and its reported gap, then return `True` to continue.
8. If all items meet threshold, return `False` and allow ordinary finalization.

#### Edge Cases & Error Handling

- No deliverables are treated as complete without creating a decision request.
- A decision answer missing its named `noul` value is a malformed provider response and cannot pass.
- A TypeSafe configuration/key/network failure propagates; it does not count as a complete result.
- Fallback/middleware/iteration budgets remain owned by existing runtime behavior; if a budget ends before a passing finish attempt, the ordinary stop result is returned with the latest evaluation metadata where available.

### 6.6 Nested generative usage accounting

**File(s):** `vidbyte/agents/pricing/tracker.py`
**Type:** [Modified]

#### What it does

Adds an explicit rollup merge operation so the source JevAgent remains the owner of all generative usage from its state and handoff builder subclasses.

#### Interface / API

```python
def merge(self, rollup: UsageRollup) -> None: ...
```

#### Logic / Algorithm

1. Validate the nested value is a `UsageRollup`.
2. Append its priced model and operation records with new sequential indices.
3. Preserve provider-reported usage and cost values without re-parsing or charging the same response twice.
4. Propagate a corrupted nested recording-integrity state.

#### Edge Cases & Error Handling

- Empty rollups leave the owner unchanged.
- An object of another type is rejected immediately.
- Nested call indices are rebased after any prior calls in the owner.

---

## 7. Data Model Changes

### 7.1 JevRunState and multipart section

**Change type:** [New]

```python
{
    "goal": "...",
    "objective": "...",
    "mission": "...",
    "what_not_to_do": ["..."],
    "sections": {"constraints": ["..."], "approach": ["..."]},
    "multi_part": {
        "deliverables": [
            {"id": "documentation", "description": "...", "completion_signal": "..."}
        ]
    }
}
```

No database migration applies. Records are immutable and live only during one `arun` call.

### 7.2 JevRunHandoff

**Change type:** [New]

```python
{
    "deliverables": [
    {"id": "documentation", "status": "...", "evidence": [{"source_id": "final_answer", "excerpt": "..."}], "remaining": "..."}
    ]
}
```

The runtime verifies a bijection between generated deliverable IDs and handoff IDs before sending any question.

---

## 8. API Changes

### 8.1 Python constructor

**Change type:** [Modified]

**Request:**

```python
agent = JevAgent(settings, done_criteria=JevPresets.MultiPart)
```

**Response:** `JevAgent` configured with the multipart done-criteria capability.

**Error cases:** `ConfigurationError` for non-`JevAgentSettings` settings, a raw/unsupported preset, or invalid structured state/handoff; existing TypeSafe errors propagate when classification cannot run.

### 8.2 Runtime result metadata

**Change type:** [Modified]

```json
{
  "done_criteria": {
    "preset": "multi_part",
    "attempts": 2,
    "deliverables": {
      "documentation": {"complete": true, "probability": 0.94}
    }
  }
}
```

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-multipart-done-criteria.md` | Source of truth for feature implementation |
| CREATE | `vidbyte/agents/jev/presets.py` | Closed public capability preset |
| CREATE | `vidbyte/agents/jev/run_state.py` | Typed structured state, handoff, snapshot, policy records and validation |
| CREATE | `vidbyte/agents/jev/builders.py` | Role-specific generative `BaseAgent` subclasses |
| MODIFY | `vidbyte/agents/jev/agent.py` | Add validated keyword-only preset and runtime wiring |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Build once, classify finish attempts, continue with gaps |
| MODIFY | `vidbyte/agents/jev/settings.py` | Clarify settings versus named runtime capabilities |
| MODIFY | `vidbyte/agents/jev/__init__.py` | Export the supported preset |
| MODIFY | `vidbyte/agents/client.py` | Expose the preset through `sdk.agents.jev` |
| MODIFY | `vidbyte/agents/__init__.py` | Export preset at agent package level |
| MODIFY | `vidbyte/__init__.py` | Export preset at root SDK level |
| MODIFY | `vidbyte/agents/runtime.py` | Add default no-op finish-attempt hook at two ordinary terminal boundaries |
| MODIFY | `vidbyte/lib/constants/jev.py` | Name and export fixed multipart threshold |
| MODIFY | `vidbyte/agents/pricing/tracker.py` | Merge nested builder usage into the main run-owned usage ledger |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add builder prompt IDs |
| CREATE | `vidbyte/prompts/prompts/jev/jev.json` | Register the prompt family |
| CREATE | `vidbyte/prompts/prompts/jev/state_builder.md` | State-builder instructions |
| CREATE | `vidbyte/prompts/prompts/jev/handoff_builder.md` | Handoff-builder instructions |
| MODIFY | `vidbyte/prompts/README.md` | Document prompt family and counts |
| MODIFY | `skills/jev-agent/SKILL.md` | Document named capability API and lifecycle invariants |
| MODIFY | `tests/test_jev_agent.py` | Unit and integration coverage for state, handoff, classification, continuation, and disabled behavior |
| MODIFY | `tests/test_agent_pricing.py` | Verify nested usage rollup merge and sequential call indexing |
| CREATE | `scripts/test-jev-multipart-done-criteria.py` | Executable feature verification script |

---

## 10. Testing Plan

Every test case is labeled by the failure category it targets.

### Unit Tests

- `[Edge Case]` Preset omitted: no builder or decision runner call and ordinary final response is preserved.
- `[Hidden Assumption]` Preset accepts only `JevPresets` and rejects strings/unknown values at construction.
- `[Edge Case]` State builder returns zero deliverables: run completes without handoff or Jev requests.
- `[Hidden Failure]` State output missing a required field, duplicate deliverable ID, or wrong structured-output shape fails before main runtime execution.
- `[Silent Failure]` Handoff entries are matched by ID rather than list position when model returns a different order.
- `[Hidden Failure]` Missing, duplicate, or unknown handoff IDs fail closed before any Jev calls.
- `[Silent Failure]` An unknown evidence source ID or excerpt absent from the cited source fails before Jev sees the handoff.
- `[Edge Case]` A single deliverable creates exactly one `NOUL` question and accepts probability exactly at the threshold.
- `[Silent Failure]` A high `P(false)` or a `P(true)` just below threshold cannot be mistaken for completion.
- `[Hidden Assumption]` Every question state contains only its matching deliverable and handoff entry, not another deliverable's evidence.
- `[Hidden Failure]` Builder, TypeSafe credential, network, and malformed answer errors do not return success metadata.
- `[Silent Failure]` Final metadata reports the final finish attempt and the correct ID-to-probability mapping.
- `[Hidden Assumption]` `UsageTracker.merge` accepts only `UsageRollup` and rebases nested model-call indices after existing calls.

### Integration Tests

- `[Hidden Failure]` Standard final-response completion builds state once, handoff once, requests Jev per item, and returns after pass.
- `[Hidden Failure]` `isDone` completion uses the same Jev check and finalization path.
- `[Hidden Failure]` A low-probability deliverable appends actionable feedback and the same runtime consumes the next scripted model response; state is not rebuilt.
- `[Silent Failure]` Runtime continuation preserves prior tool-call contexts and iteration outputs for the second handoff.
- `[Silent Failure]` A second handoff can cite an earlier tool result after the main loop continues.
- `[Silent Failure]` State and handoff builder usage appears once in the JevAgent-owned usage rollup alongside main-loop calls.
- `[Hidden Assumption]` Ordinary `BaseAgent` and `JevAgent` without the preset resolve/run without invoking any new subclass or Jev endpoint.
- `[Edge Case]` Empty multipart deliverables skip decision API setup, including TypeSafe key resolution.
- `[Hidden Failure]` Repeated incomplete result follows existing runtime iteration budgets instead of spinning outside the loop.

### Manual / QA Test Cases

1. `[Silent Failure]` Give a request for implementation plus docs and explanation; verify the generated state has three stable deliverables, the first handoff maps progress to all three, and omitting docs yields explicit continuation feedback.
2. `[Hidden Assumption]` Give a one-part request; verify the preset still works with one item and does not invent extra deliverables.
3. `[Edge Case]` Give a broad request that genuinely has no distinct deliverables; verify the generated empty list is accepted and does not make a Jev request.
4. `[Hidden Failure]` Remove the TypeSafe key or return malformed structured output; verify the run reports the provider/schema error rather than returning a completed answer.

### Executable verification script

`python scripts/test-jev-multipart-done-criteria.py` imports the production classes and runs every scenario above using existing scripted generative runners and TypeSafe transports. It prints `PASS` or `FAIL` by named case, summarizes `X/Y tests passed`, and exits non-zero when any case fails. No test uses live network credentials.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing generative runner | Configured by `JevAgentSettings` | Builds initial state and each final-attempt handoff | Extra latency and output-schema failure |
| Existing `DecisionModelRunner` / TypeSafe | Existing configured model and endpoint | One classification per deliverable | Credential, rate limit, or service errors propagate |
| JSON Schema runtime | Existing SDK output-schema path | Enforce structured builder output | Schema behavior must be verified in source and package gates |

---

## 12. Rollout & Deployment

- The feature is opt-in; no existing caller changes behavior.
- This adds a keyword-only `JevAgent` and namespace-client option without changing the required settings object.
- No migration or deployment ordering is needed.
- Rollback by reverting the feature commit; callers can remove `done_criteria` to return to current runtime behavior.
- Existing Jev scaffolding is alpha; this addition should be documented as experimental until prompt and threshold calibration is evaluated on representative tasks.

---

## 13. Open Questions

- [ ] Is `0.8` the appropriate initial P(true) completion threshold? It will be a named internal constant and can be calibrated without changing the public API.
- [ ] The model-generated state can only preserve requested parts it recognizes. Evaluation on a representative set of user prompts remains a product-quality follow-up, not a deterministic runtime guarantee.
- [ ] Handoff-builder input grows with the captured run. A future bounded evidence-selection strategy may be needed for unusually long runs; it must preserve source IDs and fail closed when it cannot represent relevant observations.

---

## 14. Alternatives Considered

### Alternative 1: A single state object generated on every iteration

- What: Re-summarize the entire run context before each Jev decision.
- Why rejected: It adds repeated generative cost and creates a moving target. This design pays for one stable state object, then adds a structured handoff only at finish attempts.

### Alternative 2: Ask Jev to compare the request with the whole transcript

- What: Pass the full run trace to one broad Jev question.
- Why rejected: Jev would have to locate, count, and compare items across unstructured context, which is reasoning. The handoff builder performs that synthesis, and deterministic code routes one deliverable at a time.

### Alternative 3: Reuse `HandoffAgent` directly

- What: Configure the generic handoff feature to emit multipart data.
- Why rejected: Its documented behavior falls back to prose on schema failure. This capability must enforce exact deliverable ID coverage before classification.

### Alternative 4: Implement continuation outside `AgentRuntime`

- What: Run the ordinary runtime once, then start a second `arun` after classification.
- Why rejected: It resets counters/middleware lifecycle and complicates conversation history. A narrow hook at the two normal finish boundaries keeps continuation in the current loop.
