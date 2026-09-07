# Design Doc: Codex Usage Tracking

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

`CodexHarnessAgent` already receives complete token counts from every Codex turn and stores them on `AgentMessage.codex.usage`, but that data dead-ends there: the agent has no `get_usage()`, no `get_cost_usd()`, and does not publish `metadata["usage_rollup"]` the way every other agent in the SDK does. A Codex turn is therefore invisible to Vidbyte's cost accounting. This change translates the native `CodexUsage` snapshot into the SDK's existing `UsageTracker`, so a Codex agent reports its own token usage and an honestly-labelled cost estimate through the same API surface as `BaseAgent`.

---

## 2. Goals & Non-Goals

### Goals

- Record each completed Codex turn's token usage into a `UsageTracker` owned by the agent.
- Expose `CodexHarnessAgent.get_usage()` and `.get_cost_usd()` with the same semantics `BaseAgent` documents for them.
- Publish `AgentMessage.metadata["usage_rollup"]`, matching what `vidbyte/agents/runtime.py:1762` publishes for direct-runtime agents.
- Record the **per-turn** token delta, never the thread-cumulative snapshot, so a multi-turn thread cannot double count.
- Report cost only where it can be honestly resolved, leaving `UsageRollup.cost_complete` false otherwise.
- Preserve `cache_write_input_tokens`, which the OpenAI usage parser has no field for, in the record's raw payload.

### Non-Goals

- Speed and latency tracking. `AgentSpeedTracker` is a separate abstraction with different caveats — most importantly that no time-to-first-token exists without streaming — and is the next PR in this sequence.
- Adding `ModelProvider.CODEX`. See §14 Alternative 1 for why the record is filed under `ModelProvider.OPENAI` instead.
- Enforcing a token or dollar budget. Budget admission is roadmap task B02 and needs a middleware decision point, which is PR 4 in this sequence.
- Authoritative billing. Codex runs on ChatGPT subscription credits as well as API billing, and the SDK has no way to tell which. Every dollar figure produced here is an estimate from the local pricing table.
- Operation-axis usage (`UsageTracker.record_operation`). Codex reports no priced search/fetch operations.

---

## 3. Background & Context

`CodexResultSerializer._usage` (`vidbyte/agents/codex/result.py`) already copies every field the provider reports:

```python
return CodexUsage(
    input_tokens=value.input_tokens,
    cached_input_tokens=value.cached_input_tokens,
    cache_write_input_tokens=value.cache_write_input_tokens or 0,
    output_tokens=value.output_tokens,
    reasoning_output_tokens=value.reasoning_output_tokens,
    total_tokens=value.total_tokens,
    model_context_window=context_window or 0,
)
```

It calls this twice and keeps the results apart: `CodexRunResult.usage` holds `result.usage.total`, which is **cumulative for the thread**, and `CodexRunResult.last_usage` holds `result.usage.last`, which is **this turn's delta**. `usage_available` records whether the provider reported usage at all, so absent is distinguishable from zero.

None of it reaches `UsageTracker`. `BaseAgent` owns one at `vidbyte/agents/base.py:230`, resets it at the start of every run (line 602), and exposes it through `get_usage()` (line 747) and `get_cost_usd()` (line 751). `CodexHarnessAgent` has none of that.

The project field guide entry *Runtime Boundaries → "Keep model usage accounting agent-owned"* (PR #285 comment 3635839045) requires the agent's own `UsageTracker` to be the single source, with each raw model response recorded exactly once, and requires that the metadata rollup and the agent usage API expose the same rollup without duplicate records. The *Class-Bound Helpers* entry's "Normalize the concrete SDK contract before validating the Vidbyte result" rule adds the specific warning that applies here: cumulative and last counters are not automatically per-turn usage.

The roadmap tracks this as **O02** ("Normalize usage accurately") and **O03** ("Report cost honestly"), whose stated completion evidence is that one native operation creates one accounting record.

---

## 4. Requirements

### Functional Requirements

1. `CodexHarnessAgent` owns one `UsageTracker` instance, created at construction.
2. The tracker is reset at the start of every `arun()` call, matching `BaseAgent`'s per-run lifecycle, so `get_usage()` describes the most recent turn.
3. A completed turn whose provider reported usage produces exactly one `UsageRecord`.
4. That record's token counts come from `CodexRunResult.last_usage` (the turn delta), never from `CodexRunResult.usage` (the thread cumulative).
5. A turn where `usage_available` is false produces zero records, and the resulting rollup reports `model_call_count == 0` rather than a record of zeros.
6. The record is filed under `ModelProvider.OPENAI` with the effective model name, resolved as `turn.model` first and `thread.model` second.
7. When `CodexThreadSettings.model_provider` is non-empty — Codex pointed at a non-OpenAI backend — no record is created, because neither the usage parser nor the pricing table can be trusted for an unknown backend.
8. `cached_input_tokens` maps to `input_tokens_details.cached_tokens` and `reasoning_output_tokens` maps to `output_tokens_details.reasoning_tokens`, matching what `OpenAIUsage.from_usage_payload` reads.
9. `cache_write_input_tokens` is preserved in the payload handed to the parser, so it survives on `OpenAIUsage.raw` despite having no typed field.
10. `CodexHarnessAgent.get_usage()` returns the tracker's `UsageRollup`; `get_cost_usd()` returns that rollup's `cost_usd`, which is `None` when nothing was priced.
11. `AgentMessage.metadata["usage_rollup"]` and `get_usage()` report identical values, because both fold the same single ledger. `UsageTracker.rollup()` builds a fresh `UsageRollup` per call, so they are equal rather than identical objects; what must hold is that no second recording pass exists between them.
12. Recording never fails a turn. `OpenAIUsage.from_usage_payload` reads every field through the total `coerce_int`/`nested_int` helpers, so an unparseable snapshot yields no `UsageRecord` and leaves `recording_integrity` `INTACT` rather than raising after Codex has already done the work.

### Non-Functional Requirements

- **Performance:** one dict construction and one tracker append per turn. No I/O, no retained history beyond the single-turn ledger the reset clears.
- **Scalability:** the ledger holds at most one record per turn and is reset each turn, so it cannot grow across a long-lived thread.
- **Security:** token counts only. No prompt text, no reasoning content, and no credentials enter the record or the rollup.
- **Observability:** this change *is* the observability work — it makes Codex turns visible to the same rollup surface as every other agent. `UsageRollup.cost_complete` distinguishes a priced run from an unpriced one, and `recording_integrity` distinguishes a clean ledger from a corrupted one.
- **Reliability:** recording is fail-open. A metering failure degrades the rollup, never the turn.

---

## 5. High-Level Design

One new collaborator, `CodexMetricsTranslator` in `vidbyte/agents/codex/metrics.py`, owns the conversion from a `CodexRunResult` into a `UsageTracker` record. It is a peer of the existing `CodexContextTranslator` and `CodexResultTranslator`: one file, one concern, one class, matching the package's established shape.

The translator's job is deliberately narrow. It decides whether this turn is recordable, builds the OpenAI-shaped usage payload, wraps it in a small typed response shim, and hands that to `UsageTracker.record_call()`. It does not own the tracker, does not compute cost itself, and does not touch the `AgentMessage`. Cost arithmetic stays where it already lives, in `UsageTracker` and the pricing registry, which satisfies the C005 cost-arithmetic-site-parity lint rule and keeps one pricing implementation in the SDK.

The shim exists because `UsageTracker.record_call()` duck-types its argument, reading `response.provider`, `response.model`, and `response.usage` (`vidbyte/agents/pricing/tracker.py:69-72`). Every existing caller passes a provider SDK response object. Codex has no such object — its result is already normalized into `CodexRunResult` — so the adapter constructs `CodexUsageResponse`, a frozen three-field dataclass carrying exactly the attributes the tracker reads. This is the smallest thing that satisfies the existing contract without widening `record_call`'s signature for one caller.

`CodexHarnessAgent` gains the tracker, the reset at the top of `arun`, one recording call after the result is normalized, and the two public accessors. The rollup travels to `AgentMessage.metadata` through a new optional field on `CodexResultTranslationRequest`, so the result translator publishes the same object the agent API returns rather than recomputing it. That field is annotated under `TYPE_CHECKING` because `vidbyte/lib/dataclasses/` is a lower layer than `vidbyte/agents/` in the A006 dependency graph and may not import `UsageRollup` at runtime.

```
CodexHarnessAgent.arun()
   |
   |-- self._usage.reset()                        <- per-turn lifecycle, mirrors BaseAgent
   v
CodexTransport.run() -> CodexRunResult
   |                       (.usage = thread cumulative, .last_usage = turn delta)
   v
CodexMetricsTranslator.record_usage()             <- NEW
   |     model_provider set?      -> record nothing
   |     usage_available false?   -> record nothing
   |     else CodexUsageResponse(provider=openai, model=..., usage={...})
   v
UsageTracker.record_call()  ->  UsageRecord (cost from the pricing registry)
   |
   v
CodexResultTranslator.translate(usage_rollup=...)  -> AgentMessage.metadata["usage_rollup"]
   |
   v
CodexHarnessAgent.get_usage() / .get_cost_usd()    <- same rollup, no second recording
```

---

## 6. Detailed Design

### 6.1 Codex usage response shim

**File(s):** `vidbyte/lib/dataclasses/codex.py`
**Type:** Modified

#### What it does

Carries the three attributes `UsageTracker.record_call()` reads, so a normalized Codex result can enter the existing tracker without changing the tracker's contract.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class CodexUsageResponse:
    """Presents one Codex turn to UsageTracker in the shape it duck-types."""

    provider: str
    model: str
    usage: Mapping[str, Any]
```

`CodexResultTranslationRequest` gains one optional field:

```python
usage_rollup: UsageRollup | None = None
```

annotated through the module's existing `TYPE_CHECKING` block.

#### Logic / Algorithm

1. `__post_init__` validates `provider` as required text, `model` as optional text (an empty model is legal and simply prices to `None`), and `usage` as a mapping with non-empty string keys.

#### Edge Cases & Error Handling

- **Empty model.** Allowed. Codex resolves the model itself when neither `turn.model` nor `thread.model` is set, and the adapter must not invent a name; the record carries `""` and the pricing registry returns no cost.
- **Non-mapping usage.** Rejected at construction, so a malformed payload cannot reach the tracker's parser.

### 6.2 CodexMetricsTranslator

**File(s):** `vidbyte/agents/codex/metrics.py`
**Type:** New file

#### What it does

Decides whether a completed turn is recordable, converts its per-turn token delta into an OpenAI-shaped usage payload, and records it once into the caller's tracker.

#### Interface / API

```python
class CodexMetricsTranslator:
    """Records one native turn's usage into Vidbyte's shared accounting."""

    @classmethod
    def record_usage(cls, request: CodexUsageTranslationRequest) -> UsageRecord | None: ...

    @staticmethod
    def _recordable_usage(request: CodexUsageTranslationRequest) -> CodexUsage | None: ...

    @staticmethod
    def _model_name(settings: CodexAgentSettings) -> str: ...

    @staticmethod
    def _usage_payload(usage: CodexUsage) -> dict[str, Any]: ...
```

`CodexUsageTranslationRequest` is a frozen slots dataclass in `vidbyte/lib/dataclasses/codex.py` holding `result: CodexRunResult`, `settings: CodexAgentSettings`, and `tracker: object` — the tracker is loosely typed for the same A006 reason as the rollup, and is exercised through its `record_call` method only.

#### Logic / Algorithm

1. Ask `_recordable_usage` for the turn delta, and return `None` when it declines. It returns the usage only when `settings.thread.model_provider` is empty, `usage_available` is true, and `last_usage` is present. It returns the snapshot rather than a boolean so the caller needs no second `None` narrowing.
2. Resolve the model as `settings.turn.model or settings.thread.model`.
3. Build the payload from `result.last_usage`, nesting cached and reasoning counts where `OpenAIUsage.from_usage_payload` reads them and keeping `cache_write_input_tokens` as a top-level key so it survives on `OpenAIUsage.raw`.
4. Construct `CodexUsageResponse` and call `tracker.record_call(response)`, returning whatever the tracker returns.

#### Edge Cases & Error Handling

- **Interrupted or failed turn.** `usage_available` is false in that case, so nothing is recorded and the rollup reports no calls. An interrupted turn that *did* report usage still records, because the tokens were genuinely spent.
- **All-zero usage.** Recorded. Zero reported tokens is a fact, distinct from usage being absent; requirement 5 covers the absent case separately.
- **Malformed payload.** `UsageTracker.record_call` returns `None` when the parser finds no usable token field, and `ProviderUsage.coerce_int`/`nested_int` are total functions that cannot raise, so no record is written and metering integrity stays `INTACT`. The translator adds no second guard, because duplicating that policy would let the two copies drift.
- **Custom `model_provider`.** No record at all. Recording tokens under `ModelProvider.OPENAI` for an unknown backend would let the pricing table produce a dollar figure for a model the account is not billed for.

### 6.3 CodexHarnessAgent usage surface

**File(s):** `vidbyte/agents/codex/agent.py`
**Type:** Modified

#### What it does

Owns the tracker, drives its per-turn lifecycle, and exposes the two public accessors.

#### Interface / API

```python
class CodexHarnessAgent:
    def get_usage(self) -> UsageRollup: ...
    def get_cost_usd(self) -> float | None: ...
```

#### Logic / Algorithm

1. `__init__` creates `self._usage = UsageTracker()`.
2. `arun` calls `self._usage.reset()` immediately before the transport call and after context translation, mirroring `BaseAgent.generate_reply`'s reset at `vidbyte/agents/base.py:602`. Resetting last, rather than at the top of the method, means a turn rejected during translation leaves the previous turn's rollup readable.
3. After `self._transport.run(...)` returns, `arun` calls `CodexMetricsTranslator.record_usage(...)` with the result, the settings, and the tracker.
4. The rollup is read once and passed into `CodexResultTranslationRequest`, so the metadata and the accessor return the same object.
5. `get_usage()` returns `self._usage.rollup()`; `get_cost_usd()` returns `self.get_usage().cost_usd`.

#### Edge Cases & Error Handling

- **Transport failure.** The recording call is never reached, and the tracker keeps the reset state — an empty rollup, not a stale one from the previous turn. This is why the reset happens before the transport call rather than after it.
- **Fork.** A forked child constructs its own agent and therefore its own tracker. Usage is not inherited, which is correct: the child has not spent anything yet.
- **Reset timing.** Because the reset is the last step before the transport call, any translation failure leaves the previous turn's rollup intact rather than clearing it for a turn that never ran. This ordering also stays correct once PR 1's input bridge adds an earlier translation step ahead of it.

### 6.4 Result metadata

**File(s):** `vidbyte/agents/codex/result.py`
**Type:** Modified

#### What it does

Publishes the rollup on the outgoing message under the same key the direct runtime uses.

#### Logic / Algorithm

1. `CodexResultTranslator.translate` adds `"usage_rollup": request.usage_rollup` to the metadata dict when the field is present.
2. The key is omitted entirely when no rollup was supplied, so a caller can distinguish "not tracked" from "tracked and empty."

#### Edge Cases & Error Handling

- **Metadata collision.** `usage_rollup` is set after the caller's `input_metadata` is merged, matching how `provider` and `provider_item_count` already win, so a caller cannot spoof the rollup.

---

## 7. Data Model Changes

N/A - no persisted records, no database, no migration. Three in-memory dataclasses are added to `vidbyte/lib/dataclasses/codex.py` (`CodexUsageResponse`, `CodexUsageTranslationRequest`) and one optional field is added to an existing one (`CodexResultTranslationRequest.usage_rollup`). None is serialized.

---

## 8. API Changes

N/A - no HTTP endpoints in this package. The public Python surface gains two methods on `CodexHarnessAgent` (`get_usage`, `get_cost_usd`) and one metadata key on returned messages. Both are additive; no existing signature changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-usage-tracking.md` | This design document |
| CREATE | `vidbyte/agents/codex/metrics.py` | `CodexMetricsTranslator` |
| MODIFY | `vidbyte/lib/dataclasses/codex.py` | `CodexUsageResponse`, `CodexUsageTranslationRequest`, `CodexResultTranslationRequest.usage_rollup` |
| MODIFY | `vidbyte/lib/constants/codex.py` | `CODEX_USAGE_PROVIDER` and `CODEX_USAGE_ROLLUP_KEY`, so neither string is inline (A007) |
| MODIFY | `vidbyte/agents/codex/agent.py` | Own the tracker, drive its lifecycle, add `get_usage`/`get_cost_usd` |
| MODIFY | `vidbyte/agents/codex/result.py` | Publish `metadata["usage_rollup"]` |
| MODIFY | `vidbyte/agents/codex/__init__.py` | Export the new dataclasses |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export on the agents facade |
| MODIFY | `vidbyte/__init__.py` | Re-export for public-export integrity (S015) |
| CREATE | `tests/test_codex_usage_tracking.py` | Feature tests for the Testing Plan below |
| CREATE | `scripts/test-codex-usage-tracking.py` | Phase 5 verification script |

Totals: 4 create, 7 modify, 0 delete.

---

## 10. Testing Plan

All tests run offline against a fake transport; no Codex process and no `openai-codex` import.

### Unit Tests

- `CodexMetricsTranslator` -> `records the per-turn delta, not the thread cumulative` — [Silent Failure] — the single most dangerous defect here: recording `result.usage` produces a plausible, monotonically rising number that is wrong by a growing factor. Builds a result whose `usage` totals 900 and whose `last_usage` totals 300, then asserts the record's total is 300.
- `CodexMetricsTranslator` -> `records nothing when usage_available is false` — [Edge Case]
- `CodexMetricsTranslator` -> `records a genuine all-zero usage snapshot` — [Silent Failure] — proves zero is not conflated with absent, the inverse of the test above.
- `CodexMetricsTranslator` -> `records nothing when model_provider names a custom backend` — [Hidden Assumption] — the implementation must not assume Codex always runs OpenAI models.
- `CodexMetricsTranslator` -> `prefers the turn model over the thread model` — [Silent Failure] — the wrong model name silently prices at another model's rate.
- `CodexMetricsTranslator` -> `records an empty model name when neither layer sets one` — [Edge Case]
- `CodexMetricsTranslator` -> `maps cached tokens into input_tokens_details` — [Silent Failure] — a mis-nested key parses as `None`, which understates nothing but silently loses the cache discount in the cost.
- `CodexMetricsTranslator` -> `maps reasoning tokens into output_tokens_details` — [Silent Failure]
- `CodexMetricsTranslator` -> `preserves cache_write_input_tokens on the parsed raw payload` — [Silent Failure] — the field has no typed counterpart and would vanish without an explicit assertion.
- `CodexMetricsTranslator` -> `records nothing for a usage payload whose counts are non-numeric` — [Hidden Failure] — proves the fail-open path is the tracker's parser returning None, not a swallowed exception in the translator, and that integrity is not falsely reported as corrupted.
- `CodexUsageResponse` -> `rejects a non-mapping usage payload` — [Hidden Assumption]
- `CodexUsageResponse` -> `accepts an empty model name` — [Edge Case]

### Integration Tests

The flow to prove end to end is: one `arun()` produces exactly one accounting record, reachable identically from `get_usage()` and from `AgentMessage.metadata`. Only `CodexTransport` is faked; `CodexMetricsTranslator`, `CodexResultTranslator`, and the real `UsageTracker` all run, because the defect this guards against — double recording — only appears when the real components are wired together.

- One `arun()` produces `get_usage().model_call_count == 1`. [Silent Failure] — a record written in both the translator and the result path would read 2.
- `AgentMessage.metadata["usage_rollup"] is agent.get_usage()`-equivalent: same call count and same totals, proving no second recording pass.
- Three sequential `arun()` calls against a thread whose cumulative usage rises each turn leave `get_usage().total_tokens` equal to the third turn's delta, not the running total. [Silent Failure] — this is the multi-turn double-count that unit tests cannot surface, because it needs the reset and the delta selection to both be right.
- A turn that raises from the transport leaves `get_usage().model_call_count == 0` rather than the previous turn's record. [Hidden Failure] — proves the reset precedes the transport call.
- `get_cost_usd()` returns `None` and `cost_complete` is false for an unpriced model name. [Hidden Assumption] — the implementation must not assume every model is in the pricing table.

### Manual / QA Test Cases

1. Given a Codex agent with no model configured at either layer, when a turn completes with usage, then `get_usage().model_call_count` is 1 and `get_cost_usd()` is `None` — tokens tracked, cost honestly absent. — [Edge Case]
2. Given a Codex agent whose thread sets `model_provider="my-gateway"`, when a turn completes with usage, then no record exists and no dollar figure is produced. — [Hidden Assumption]
3. Given two sequential turns, when the second completes, then `AgentMessage.codex.usage` shows the rising thread cumulative while `metadata["usage_rollup"]` shows only the second turn — the two surfaces are deliberately different and both correct. — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` | 0.147.0, optional extra | Source of the usage snapshot, already normalized upstream of this change | None added — no new SDK surface is read |
| Existing pricing registry | `vidbyte/agents/pricing/` | Resolves an OpenAI model rate to a USD estimate | A model missing from the table yields `None`, which is the designed behavior |

No dependency additions.

---

## 12. Rollout & Deployment

No feature flag. The change is additive: existing callers see two new methods and one new metadata key, and nothing that previously worked changes shape. There is no service, no ordering constraint, and no data to migrate; rollback is a revert of this branch.

This is PR 2 of five independent Codex-translation PRs, each branched from `origin/main`. It should be merged after PR 1 (`feat/codex-agent-input-bridge`) to keep the conflicts in `vidbyte/agents/codex/agent.py` trivial.

---

## 13. Open Questions

- [ ] Should a future change let a caller opt into thread-cumulative accounting, given the provider snapshot already exposes it on `AgentMessage.codex.usage`? Recorded here as a deliberate two-surface split rather than a gap.
- [ ] Should `ModelProvider` eventually gain a `CODEX` member with its own pricing registry, if Codex begins reporting resolved model names that diverge from the OpenAI catalogue? Not needed today; see §14.

---

## 14. Alternatives Considered

### Alternative 1: Add `ModelProvider.CODEX` with its own usage class and pricing registry

- What: A new enum member, a `CodexProviderUsage(ProviderUsage)` parser, and Codex rates in the operation pricebook.
- Why rejected: Codex runs OpenAI models, and `OpenAIUsage.from_usage_payload` already reads exactly the field shape Codex reports. A `CODEX` member would mean maintaining a second copy of OpenAI's rate table for the same models, which the field guide's *Operation Pricebook Rates* entry treats as a change requiring separate justification. The condition that would flip this: Codex reporting a resolved model name outside the OpenAI catalogue.

### Alternative 2: Widen `UsageTracker.record_call()` to accept a typed usage record directly

- What: Add an overload or a second method taking `(provider, model, ProviderUsage)` instead of a duck-typed response.
- Why rejected: It changes a shared abstraction used by every provider to accommodate one caller. The shim is three fields and lives entirely inside the Codex package, so the blast radius stays where the new requirement is.

### Alternative 3: Record usage inside `CodexResultTranslator`

- What: Let the existing result translator do the recording while it builds the `AgentMessage`.
- Why rejected: That class's stated job is producing the Vidbyte message and validating structured output; giving it a side effect on a mutable tracker makes it non-idempotent, and the field guide's "one native operation creates one accounting record" evidence bar becomes much harder to prove for a class that also runs on every fork and error path.

### Alternative 4: Never reset the tracker, reporting thread-cumulative usage

- What: Let the rollup accumulate across every turn of a thread.
- Why rejected: It diverges from `BaseAgent.get_usage()`, which documents "the current or most recent run" and resets each run. Two agents in one pipeline would then report usage on incompatible bases. The thread cumulative remains available on `AgentMessage.codex.usage`, so nothing is lost.
