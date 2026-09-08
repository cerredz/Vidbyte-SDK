# Design Doc: Codex Output Contracts

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

`OutputContract` is the SDK's declarative "the agent may not stop until this holds" mechanism — thirteen floor types reading a shared `counters` mapping, covering tool calls, tokens, elapsed time, output size, compactions, and named-tool usage. `CodexHarnessAgent` honors none of them: `AgentLoopSettings.output_contracts` never reaches it, and the only output guarantee it has is `output_schema` validation. This change builds the same `counters` mapping from a completed Codex turn, evaluates the caller's contracts against it, and reports the outcome. Ten of the thirteen contract types are genuinely satisfiable from native turn items; the three that read a Vidbyte-owned loop counter are rejected at construction rather than silently reported as met.

---

## 2. Goals & Non-Goals

### Goals

- Accept `AgentLoopSettings` on `CodexHarnessAgentSettings` and read its `output_contracts` and `max_contract_rejections`.
- Build the same thirteen-key `counters` mapping the direct runtime builds, from `CodexRunResult` items, usage, and duration.
- Derive tool counts from the pinned SDK's real item shapes: `commandExecution`, `mcpToolCall`, and `dynamicToolCall`, each with its own success rule.
- Evaluate every configured contract after the turn and publish the result on `AgentMessage.metadata`.
- Reject at construction any contract whose counter Codex cannot observe, naming the contract.
- Reject at construction any `AgentLoopSettings` field the adapter cannot honor, naming each.
- Raise a classified failure when a contract is unmet, rather than returning a reply that silently failed its own stated requirement.

### Non-Goals

- A corrective re-prompt loop. In the direct runtime an unmet contract drives up to `max_contract_rejections` more model calls. For Codex each retry is a whole new native turn with new tokens and new file edits, so this change evaluates and reports; §13 records the re-prompt loop as a separate opt-in.
- Contract-driven model fallback. Whether an unmet contract should advance the fallback chain from PR 1 is a policy question that needs the re-prompt decision settled first.
- `iteration_count` and `model_call_count`. Codex owns its internal loop and reports neither; inventing "1 turn = 1 iteration" would put a plausible number under a name that means something else.
- Enforcing the `AgentLoopSettings` ceilings (`max_iterations`, `max_tool_calls`, `max_tokens`, `timeout_seconds`). Those need a live turn handle to interrupt; this change reads only the floors and rejects the ceilings it cannot enforce.

---

## 3. Background & Context

`OutputContract` (`vidbyte/agents/contracts/__init__.py:27`) is a small declarative base: each subclass declares a `key` naming the counter it reads, an optional `ceiling_key` naming the paired `AgentLoopSettings` bound, a `unit` for corrective text, and inherits `satisfied(counters)` / `error(counters)` / `observed(counters)`. `AgentLoopSettings` carries them as `output_contracts: Sequence[OutputContract]` with `max_contract_rejections: int = 3`.

The direct runtime builds the counters in `AgentRuntime._contract_counters` (`vidbyte/agents/runtime.py:1765`) — thirteen keys, with internal tools filtered out so effort floors count only developer-facing work. That method is the contract this design mirrors, because two different counter shapes for one contract vocabulary would mean `MinToolCalls(3)` means different things depending on which agent runs it.

The Codex side is richer than I expected. Inspecting the pinned `openai-codex==0.147.0` generated models, each tool-shaped `ThreadItem` variant carries its own outcome fields:

| Item | Fields that matter |
|---|---|
| `CommandExecutionThreadItem` | `command`, `status`, `exit_code`, `duration_ms` |
| `McpToolCallThreadItem` | `tool`, `server`, `status`, `error`, `duration_ms` |
| `DynamicToolCallThreadItem` | `tool`, `namespace`, `status`, `success` |
| `ContextCompactionThreadItem` | `id`, `type` only |

with `CommandExecutionStatus` ∈ `{inProgress, completed, failed, declined}` and both tool-call statuses ∈ `{inProgress, completed, failed}`. `CodexResultSerializer._item` already copies every one of those into `CodexItem.fields` via `model_dump(mode="json", by_alias=True)`, so the data is present today and simply unread.

That makes ten of the thirteen counters real:

| Counter | Codex source |
|---|---|
| `tool_call_count` | command + mcp + dynamic items |
| `successful_tool_call_count` | per-item success rule (see §6.2) |
| `distinct_tool_count`, `tool_calls_by_name` | per-item tool name |
| `tokens_used` | `last_usage.total_tokens` |
| `final_output_tokens` | `last_usage.output_tokens` — a real count, better than the runtime's character approximation |
| `final_output_chars` | `len(final_response)` |
| `elapsed_seconds` | `duration_ms / 1000` |
| `cost_spent_usd` | the merged usage rollup's `cost_usd` |
| `compaction_count` | `contextCompaction` items |
| `iteration_count`, `model_call_count` | **unavailable** |

The roadmap tracks this as **U05** ("Extend output contracts"), whose stated caveat is the one this design turns into a rule: "A valid JSON object does not prove required tools ran. Rejection/retry is a new native turn and consumes work."

Two field-guide constraints bind the work. *Class-Bound Helpers → "Audit every surface of a shared abstraction"* (PR #412) requires §9a's audit of `AgentLoopSettings`. *Class-Bound Helpers → "Give each translated surface its own function"* requires one function per counter group that actually transforms something, rather than one large builder with inline branches.

---

## 4. Requirements

### Functional Requirements

1. `CodexHarnessAgentSettings` accepts `loop: AgentLoopSettings | None`, defaulting to `None`.
2. Construction raises `ConfigurationError` naming each unsupported field when `loop` sets any of `max_iterations`, `max_tool_calls`, `max_tokens`, `max_retries`, `max_parallel_tool_calls`, `timeout_seconds`, `context_window_budget`, `compaction_trigger_tokens`, `compaction_target_tokens`, `allowed_tools`, `tool_error_policy`, or `tool_settings` — none of which this adapter can enforce.
3. Construction raises `ConfigurationError` naming the contract when `output_contracts` contains one whose `key` is `iteration_count` or `model_call_count`.
4. A new `CodexContractTranslator` builds a `counters` mapping with the same thirteen keys `AgentRuntime._contract_counters` produces.
5. `tool_call_count` counts `commandExecution`, `mcpToolCall`, and `dynamicToolCall` items, and excludes `webSearch`, `fileChange`, `imageView`, and every non-tool item type.
6. `successful_tool_call_count` counts a command item when `status == "completed"` **and** `exit_code == 0`; an MCP item when `status == "completed"` and `error` is absent; and a dynamic item when `success` is true.
7. A tool item still `inProgress` counts toward `tool_call_count` but never toward `successful_tool_call_count`.
8. `tool_calls_by_name` names a command item by the first whitespace-separated token of its `command`, and an MCP or dynamic item by its `tool` field.
9. `distinct_tool_count` is the number of distinct names in `tool_calls_by_name`.
10. `tokens_used` and `final_output_tokens` come from `last_usage` when `usage_available` is true, and are `0` otherwise — matching the runtime's `tokens_used or 0`.
11. `elapsed_seconds` is `duration_ms / 1000` when the provider reported a duration, and `0` otherwise.
12. `cost_spent_usd` is the usage rollup's `cost_usd` when priced, and `0` otherwise.
13. `compaction_count` counts `contextCompaction` items.
14. `iteration_count` and `model_call_count` are present in the mapping with value `0`, because a contract rejected at construction can never read them and an absent key would break any caller iterating the shape.
15. Every configured contract is evaluated after result translation; the outcome records the contract name, whether it was satisfied, its observed value, and its minimum.
16. An unmet contract raises `CodexAgentError` with `CODEX_CONTRACT_UNMET`, whose message carries the first unmet contract's own `error(counters)` text, and whose details name every unmet contract. Each `CodexContractResult` carries that text too, so a caller reading the published outcome sees the same corrective detail — `MinToolCallsById` names the specific tool it wanted, which a generic observed-vs-required message would lose.
17. `AgentMessage.metadata` carries the contract evaluation under one key when contracts are configured, and omits the key entirely otherwise.
18. An agent with `loop=None` behaves exactly as before this change.

### Non-Functional Requirements

- **Performance:** one pass over the turn's items plus one evaluation per contract. Item counts are bounded by what one turn produced.
- **Scalability:** no retained state; counters are built per turn and discarded.
- **Security:** counters carry integers, a float, and tool names. Command items contribute only their first argv token, so a full command line — which routinely contains paths and occasionally secrets — never reaches the counters or the metadata.
- **Observability:** the evaluation is published on the reply, so a caller can see which contract failed and by how much without re-deriving it.
- **Reliability:** an unmet contract fails the turn loudly. The turn already ran and its side effects are real; §13 records that this is a report, not a rollback.

---

## 5. High-Level Design

One new collaborator plus one settings field.

`CodexContractTranslator` (`vidbyte/agents/codex/contracts.py`) has two jobs kept deliberately separate. `counters(request)` converts a `CodexRunResult` into the shared mapping, and `evaluate(contracts, counters)` runs the caller's contracts against it. Splitting them means the counter shape is testable without any contract, and a contract is testable against a hand-built mapping — which matters because the counters are where the real work is and the evaluation is three lines.

The counter builder is one function per group that genuinely transforms something, per the field guide: `_tool_counters` walks the items once and returns the four tool-shaped counters together (because they share one pass and one filter), `_usage_counters` reads the turn delta, and `_output_counters` reads the final response. A single large builder with inline branches would hide which item types are counted where — and this design's whole value is that the answer is inspectable.

The **success rule** is the part worth getting right, because each item type reports its outcome differently. A command is successful only when it both completed and exited zero — `status == "completed"` alone would count a command that ran and returned exit code 1 as a success, which is exactly the silent wrong answer `MinSuccessfulToolCalls` exists to catch. An MCP call reports `status` plus a separate `error` field, so both must be clean. A dynamic tool call carries an explicit `success` boolean, which is authoritative and needs no inference.

The **rejection surface** is the other half. `AgentLoopSettings` has eighteen fields and this adapter can honor three of them; the other fifteen describe a Vidbyte-owned loop with iterations, a local tool executor, and a compaction budget. Accepting them silently would be the same failure PR #415's middleware validator exists to prevent, so `translate_agent` names every unsupported field it was handed.

```
CodexHarnessAgent.__init__
   |
   |-- CodexVidbyteTranslator.translate_agent()
   |       |-- CodexContractValidator.validate(loop)   <- NEW
   |             rejects 12 unenforceable fields + iteration/model-call contracts
   v
CodexHarnessAgent.arun()
   |
   v  CodexTransport.run() -> CodexRunResult (items, last_usage, duration_ms)
   |
   |-- CodexResultTranslator.translate() -> AgentMessage
   |
   |-- CodexContractTranslator.counters(result, rollup)   <- one pass over items
   |        {tool_call_count, successful_tool_call_count, distinct_tool_count,
   |         tool_calls_by_name, tokens_used, elapsed_seconds, final_output_chars,
   |         final_output_tokens, cost_spent_usd, compaction_count, ...}
   v
   CodexContractTranslator.evaluate(contracts, counters)
   |        all satisfied -> publish evaluation on metadata -> return reply
   |        any unmet     -> raise CODEX_CONTRACT_UNMET with the contract's own text
```

---

## 6. Detailed Design

### 6.1 Loop settings validation

**File(s):** `vidbyte/agents/codex/contracts.py`, `vidbyte/agents/codex/config.py`
**Type:** New file, then modified

#### What it does

Rejects, at construction, every `AgentLoopSettings` field and every contract this adapter cannot honor.

#### Interface / API

```python
class CodexContractValidator:
    """Rejects loop settings and contracts Codex has no way to honor."""

    @classmethod
    def validate(cls, loop: AgentLoopSettings | None) -> None: ...

    @staticmethod
    def _unsupported_fields(loop: AgentLoopSettings) -> tuple[str, ...]: ...

    @staticmethod
    def _unsupported_contracts(loop: AgentLoopSettings) -> tuple[str, ...]: ...
```

`CODEX_UNSUPPORTED_LOOP_FIELDS` and `CODEX_UNOBSERVABLE_COUNTER_KEYS` live in the constants module so both sets are data.

#### Logic / Algorithm

1. Return immediately when `loop` is `None`.
2. Collect every unsupported field whose value is not its default, and raise naming all of them at once — so fixing one and re-running does not reveal the next.
3. Collect every contract whose `key` is in the unobservable set, and raise naming the contract classes.

#### Edge Cases & Error Handling

- **A field set to its own default.** Not a finding. Passing `max_iterations=None` is indistinguishable from not passing it, and rejecting it would fail a caller who built one `AgentLoopSettings` for several agents.
- **A custom `OutputContract` subclass with a novel key.** Accepted, and its counter reads as absent — `OutputContract.satisfied` uses `counters.get(self.key) or 0`, so an unknown key evaluates as `0` and the contract simply fails. §13 records whether that should instead be rejected.

### 6.2 Counter construction

**File(s):** `vidbyte/agents/codex/contracts.py`
**Type:** New file

#### Interface / API

```python
class CodexContractTranslator:
    """Builds the shared contract counters from one completed Codex turn."""

    @classmethod
    def counters(cls, request: CodexContractRequest) -> dict[str, Any]: ...

    @classmethod
    def evaluate(cls, request: CodexContractEvaluation) -> CodexContractOutcome: ...

    @staticmethod
    def _tool_counters(items: tuple[CodexItem, ...]) -> dict[str, Any]: ...
    @staticmethod
    def _tool_name(item: CodexItem) -> str: ...
    @staticmethod
    def _tool_succeeded(item: CodexItem) -> bool: ...
    @staticmethod
    def _usage_counters(result: CodexRunResult, cost_usd: float | None) -> dict[str, Any]: ...
    @staticmethod
    def _output_counters(result: CodexRunResult) -> dict[str, Any]: ...
```

#### Logic / Algorithm

`_tool_counters` walks the items once:
1. Skip any item whose type is not in `CODEX_TOOL_ITEM_TYPES`.
2. Name it through `_tool_name`, and increment its histogram entry.
3. Ask `_tool_succeeded` and increment the success counter when true.
4. Return `tool_call_count`, `successful_tool_call_count`, `distinct_tool_count`, and `tool_calls_by_name`.

`_tool_name` returns `fields["tool"]` for MCP and dynamic items, and for a command item the first whitespace-separated token of `fields["command"]`, falling back to the item type when the field is absent.

`_tool_succeeded` applies the per-type rule from requirement 6.

#### Edge Cases & Error Handling

- **An empty `command`.** Falls back to the item type as the name, so the call is still counted rather than silently dropped from the histogram.
- **A missing `status`.** Treated as not successful. Absent evidence of success is not success.
- **`exit_code` absent on a completed command.** Not successful, for the same reason.
- **No items at all.** Every tool counter is `0` and the histogram is empty, which is the correct reading of a turn that answered without acting.

### 6.3 Evaluation and reporting

**File(s):** `vidbyte/agents/codex/contracts.py`, `vidbyte/agents/codex/agent.py`, `vidbyte/agents/codex/result.py`
**Type:** New file, then modified

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class CodexContractResult:
    """One contract's verdict against one turn's counters."""

    name: str
    satisfied: bool
    observed: Any
    minimum: float
    error: str = ""   # the contract's own corrective text, empty when satisfied


@dataclass(frozen=True, slots=True)
class CodexContractOutcome:
    """Every contract's verdict plus the counters they were judged against."""

    results: tuple[CodexContractResult, ...]
    counters: Mapping[str, Any]

    @property
    def unmet(self) -> tuple[CodexContractResult, ...]: ...
```

#### Logic / Algorithm

1. `arun` builds the counters after result translation, when the usage rollup is already available.
2. `evaluate` produces one `CodexContractResult` per contract.
3. When any is unmet, `arun` raises `CodexAgentError` with `CODEX_CONTRACT_UNMET`, the first unmet contract's `error(counters)` text as the message, and the unmet names in `details`.
4. When all are met, the outcome is published on the reply metadata.

#### Edge Cases & Error Handling

- **The turn already ran.** An unmet contract does not undo the turn's file edits. The error says which contract failed; it does not claim the work was prevented.
- **No contracts configured.** No counters are built, no key is published, and the hot path is unchanged.

---

## 7. Data Model Changes

N/A - no persisted records, no database, no migration. Four in-memory dataclasses are added (`CodexContractRequest`, `CodexContractEvaluation`, `CodexContractResult`, `CodexContractOutcome`) and one settings field. Nothing is serialized.

---

## 8. API Changes

N/A - no HTTP endpoints. The public surface gains one settings field, four dataclasses, one `FailureCode` member, and one metadata key, all additive.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-output-contracts.md` | This design document |
| CREATE | `vidbyte/agents/codex/contracts.py` | `CodexContractValidator`, `CodexContractTranslator` |
| MODIFY | `vidbyte/lib/constants/codex.py` | Tool item types, unsupported loop fields, unobservable keys, metadata key (A007) |
| MODIFY | `vidbyte/lib/dataclasses/codex.py` | Four contract records and the `loop` settings field |
| MODIFY | `vidbyte/lib/enums/failure.py` | `CODEX_CONTRACT_UNMET` |
| MODIFY | `vidbyte/agents/codex/config.py` | Validate loop settings in `translate_agent` |
| MODIFY | `vidbyte/agents/codex/agent.py` | Build counters, evaluate, raise or publish |
| MODIFY | `vidbyte/agents/codex/result.py` | Publish the contract evaluation |
| MODIFY | `vidbyte/agents/codex/__init__.py` | Export the contract records |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export on the agents facade |
| MODIFY | `vidbyte/__init__.py` | Re-export for public-export integrity (S015) |
| CREATE | `tests/test_codex_output_contracts.py` | Feature tests for the Testing Plan below |
| CREATE | `scripts/test-codex-output-contracts.py` | Phase 5 verification script |

Totals: 4 create, 9 modify, 0 delete.

---

## 9a. Abstraction Surface Audit

Required by the field guide's *audit every surface* entry. `AgentLoopSettings` has eighteen constructor fields:

| Surface | Disposition |
|---|---|
| `output_contracts` | **Translated** — evaluated against native counters |
| `max_contract_rejections` | **Read but unused** — no re-prompt loop exists yet; §13 |
| `max_queued_prompts` | Not applicable — governs a Vidbyte prompt queue Codex has no equivalent of; ignored without rejection because it cannot conflict with anything |
| `max_iterations`, `max_tool_calls`, `max_tokens`, `max_retries`, `max_parallel_tool_calls` | **Rejected** — inner-loop ceilings Codex owns |
| `timeout_seconds` | **Rejected** — needs a live turn handle to interrupt (roadmap B01) |
| `context_window_budget`, `compaction_trigger_tokens`, `compaction_target_tokens` | **Rejected** — describe a Vidbyte-managed context window |
| `allowed_tools`, `tool_error_policy`, `tool_settings` | **Rejected** — describe a local tool executor Codex does not use |

`OutputContract` has four class attributes and three methods: `key` (**translated** — the counter lookup), `unit` and `name` (**translated** — carried into the error text and the result record), `ceiling_key` (**not a translation** — names an `AgentLoopSettings` bound this adapter rejects anyway), `satisfied`/`error`/`observed` (**not translations** — called, not converted).

`CodexRunResult` surfaces read: `items`, `last_usage`, `usage_available`, `duration_ms`, `final_response`. Deliberately unread: `status` (the result translator already gates on it), `thread_id`/`turn_id` (identity, not effort), `error` (a failed turn raises before contracts are evaluated).

---

## 10. Testing Plan

All tests run offline against a fake transport, with `CodexItem` payloads shaped exactly like the pinned SDK's `model_dump` output.

### Unit Tests

- `_tool_counters` -> `counts command, mcp, and dynamic items` — [Edge Case]
- `_tool_counters` -> `excludes webSearch, fileChange, and agentMessage items` — [Silent Failure] — counting a web search as a tool call inflates every effort floor by an amount that varies with the prompt.
- `_tool_counters` -> `returns zeros for a turn with no items` — [Edge Case]
- `_tool_succeeded` -> `rejects a completed command with a nonzero exit code` — [Silent Failure] — the headline defect: `status == "completed"` alone counts a command that failed as a success, which is precisely what `MinSuccessfulToolCalls` exists to catch.
- `_tool_succeeded` -> `accepts a completed command with exit code zero` — [Edge Case]
- `_tool_succeeded` -> `rejects a completed MCP call carrying an error` — [Silent Failure]
- `_tool_succeeded` -> `honors the dynamic tool call's explicit success flag over its status` — [Hidden Assumption]
- `_tool_succeeded` -> `rejects an inProgress item` — [Edge Case]
- `_tool_succeeded` -> `rejects an item with no status field` — [Hidden Assumption] — absent evidence of success is not success.
- `_tool_succeeded` -> `rejects a completed command with no exit_code` — [Hidden Assumption]
- `_tool_name` -> `names a command by its first argv token` — [Silent Failure] — naming it by the whole command line would make `MinToolCallsById("git")` never match and would leak paths into metadata.
- `_tool_name` -> `names an mcp item by its tool field` — [Edge Case]
- `_tool_name` -> `falls back to the item type for an empty command` — [Edge Case] — the call must still be counted.
- `counters` -> `reads tokens from the per-turn delta, not the thread cumulative` — [Silent Failure] — the same defect PR #413 guarded against, in a second consumer.
- `counters` -> `reports zero tokens when usage is unavailable` — [Edge Case]
- `counters` -> `converts duration_ms to elapsed seconds` — [Silent Failure] — reporting milliseconds as seconds would satisfy every `MinElapsedSeconds` by a factor of 1000.
- `counters` -> `reports zero elapsed when the provider reported no duration` — [Edge Case]
- `counters` -> `includes iteration_count and model_call_count as zero` — [Hidden Assumption] — a caller iterating the shape must not hit a missing key.
- `counters` -> `produces exactly the keys the direct runtime produces` — [Hidden Failure] — asserts the key set against `AgentRuntime._contract_counters`'s literal keys, so the two shapes cannot drift and make one contract mean two things.
- `CodexContractValidator` -> `accepts loop=None` — [Edge Case]
- `CodexContractValidator` -> `accepts a loop carrying only output_contracts` — [Edge Case]
- `CodexContractValidator` -> `rejects every field CODEX_UNSUPPORTED_LOOP_FIELDS lists, naming it` — [Hidden Failure] — the test asserts its own case set equals the constant, so a field added to the constant without a probe fails the test rather than going untested.
- `CodexContractValidator` -> `names every unsupported field at once` — [Silent Failure] — fixing one and re-running should not reveal a second.
- `CodexContractValidator` -> `rejects MinIterations, naming the contract` — [Hidden Failure] — a contract on a counter Codex cannot observe would evaluate against `0` and always fail, which reads as a broken agent rather than a rejected configuration.
- `CodexContractValidator` -> `accepts a field left at its default` — [Hidden Assumption] — one `AgentLoopSettings` reused across agents must not fail on defaults it never set.
- `evaluate` -> `reports satisfied and observed per contract` — [Edge Case]
- `evaluate` -> `carries each unmet contract's own corrective text` — [Silent Failure] — a generic message loses the tool name `MinToolCallsById` computes, which is the only actionable part.
- `evaluate` -> `leaves a satisfied contract's error empty` — [Edge Case]
- `evaluate` -> `reports unmet contracts in declaration order` — [Silent Failure]

### Integration Tests

The flow to prove is a real turn producing real counters. Only the transport is faked; the real `OutputContract` subclasses, the real `AgentLoopSettings`, and the merged `UsageTracker` all run.

- A turn with two successful commands satisfies `MinToolCalls(2)` and returns the reply. [Edge Case]
- A turn with one successful and one failed command satisfies `MinToolCalls(2)` but fails `MinSuccessfulToolCalls(2)`. [Silent Failure] — proves the two counters genuinely differ, which a shared implementation would hide.
- An unmet contract raises `CODEX_CONTRACT_UNMET` whose message is the contract's own corrective text. [Hidden Failure] — a generic message would lose the observed-vs-required numbers the contract computes.
- An unmet contract's error details name every unmet contract, not just the first. [Silent Failure]
- A satisfied run publishes the evaluation on `metadata`, including the counters. [Edge Case]
- `MinToolCallsById("git", 2)` is satisfied by two `git` commands and not by one `git` and one `ls`. [Silent Failure] — the histogram is the only counter with per-name resolution, so a naming bug shows up here and nowhere else.
- An agent with `loop=None` publishes no contract key and runs unchanged. [Hidden Assumption]
- A turn whose contracts are all met still publishes the counters, so a caller can see the margin. [Edge Case]

### Manual / QA Test Cases

1. Given an agent with `MinToolCalls(1)` and a turn that answers without running anything, when it completes, then the caller sees `codex.contract_unmet` naming `MinToolCalls` with observed 0. — [Hidden Failure]
2. Given an agent whose loop sets `timeout_seconds=30`, when it is constructed, then construction fails naming `timeout_seconds` as unenforceable. — [Hidden Assumption]
3. Given a turn that ran `git status` and `git diff`, when `MinDistinctTools(2)` is configured, then it fails — both calls name the same tool. — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` | 0.147.0, optional extra | Its `ThreadItem` variants define the field names the counters read | A future item-shape change would silently zero a counter; requirement 5's explicit type set and the name-fallback limit the blast radius |

No dependency additions. The counters read `CodexItem.fields`, which `result.py` already populates, so no new SDK import is introduced.

---

## 12. Rollout & Deployment

No feature flag. The default is `loop=None`, so an existing agent is untouched; the metadata key is omitted when no contracts are configured.

This branches from `origin/main` at `6b7d848d`, which includes the merged usage tracking (#413). It is PR 2 of three and should merge after PR 1 (`feat/codex-failure-recovery`): both add a collaborator to `__init__` and a step to `arun`, in adjacent lines, and PR 1's classification is what a future contract-driven fallback would consult.

Rollback is a revert of this branch.

---

## 13. Open Questions

- [ ] Should an unmet contract drive a corrective re-prompt, honoring `max_contract_rejections`? Each rejection is a full native turn with new tokens and new file edits, so the cost is much higher than in the direct runtime. Reporting first, looping later, keeps the expensive behavior opt-in.
- [ ] Should an unmet contract advance PR 1's fallback chain? It is a plausible trigger, but only after the re-prompt question is settled — otherwise a contract failure would switch models before it had retried once.
- [ ] A custom `OutputContract` with an unknown key currently evaluates against `0` and always fails. Should the validator reject unknown keys instead, at the cost of refusing a contract a caller wrote deliberately against a key they populate themselves?
- [ ] `successful_tool_call_count` treats a `declined` command as unsuccessful, which is right, but declined and failed are different operator situations. Should the counters distinguish them?

---

## 14. Alternatives Considered

### Alternative 1: Reuse `AgentRuntime._contract_counters`

- What: Call the direct runtime's builder instead of writing a Codex one.
- Why rejected: It takes `Sequence[ToolCallContext]`, `iteration_count`, `model_call_count`, and a `started_at` from the runtime's own clock — every argument is a Vidbyte-loop concept a Codex turn does not have. Constructing fake `ToolCallContext` objects to satisfy it would be more code than building the mapping, and it would invent the two counters this design deliberately refuses to fabricate.

### Alternative 2: Count `status == "completed"` uniformly across item types

- What: One success rule for all three tool item types.
- Why rejected: A command that completed with exit code 1 ran and failed. Counting it as a successful tool call is exactly the silent wrong answer `MinSuccessfulToolCalls` exists to detect, and the pinned SDK gives each item type its own outcome fields precisely because they differ.

### Alternative 3: Accept unsupported `AgentLoopSettings` fields and ignore them

- What: Take the whole settings object and honor the three fields that map.
- Why rejected: `timeout_seconds=30` that never times out is worse than a construction error, because the caller believes a bound exists. This is the same rule PR #415 applied to inner-loop middleware hooks.

### Alternative 4: Evaluate contracts inside `CodexResultTranslator`

- What: Fold the evaluation into the class that already builds the `AgentMessage`.
- Why rejected: That class is called on the fork and error paths too, and it currently has no side effects beyond validation. Giving it the power to raise a contract failure would make a message-construction helper into a policy gate, and would evaluate contracts in paths where no turn ran.
