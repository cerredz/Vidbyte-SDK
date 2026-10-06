# Design Doc: Output-Contract Skill + Extended Effort Floors

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-08
**Last Updated:** 2026-07-08
**Base:** `origin/main` @ `d92be50` (includes #261 Output Contracts + #262 ToolSettings budgets)
**Repo:** `vidbyte-sdk` (local main worktree updated before this design)

---

## 1. Overview

PR #261 shipped the **output-contract framework** and four deterministic effort floors owned by `AgentLoopSettings`. This change does two things on top of that foundation:

1. **Create a contributor skill** (`skills/output-contracts/SKILL.md`) that documents the full mental model, ownership split, counter snapshot, enforcement boundaries, process for adding a new floor, and invariants — modeled after `skills/tool-settings/SKILL.md`.
2. **Add the next set of deterministic floors**, implemented one at a time with explicit counter wiring for each:
   - `MinCompactions`
   - `MinSuccessfulToolCalls`
   - `MinDistinctTools`
   - `MinFinalOutputChars` / `MinFinalOutputTokens`
   - `MinToolCallsById`
   - `MinTimeTaken` (alias of existing `MinElapsedSeconds`)
   - `MinCostSpent`

Framing remains unchanged:

> **`AgentLoopSettings` ceilings say when the agent MUST stop. Output contracts say when the agent MAY stop.**

---

## 2. Goals & Non-Goals

### Goals
- Ship a durable **output-contracts skill** that explains the existing #261 system end-to-end and the process for adding floors.
- Extend `_contract_counters` (and, where needed, runtime/middleware telemetry) so every new floor has a real, documented counter.
- Add the listed floors with sequential, carefully reasoned logic (not one bulk dump of unreviewed classes).
- Keep the #261 ownership model: contracts live on `AgentLoopSettings`; evaluation is owned by `AgentLoopSettingsOutputContract`; the linear runtime owns control flow and injection envelopes.
- Keep linear-only enforcement; inactive contracts remain a pure no-op.
- Re-export new public floor classes from `vidbyte.agents` (and `vidbyte` root when appropriate).
- Cross-link from `skills/agentic-loop-settings/SKILL.md` and the skill-update matrix.

### Non-Goals
- **No new stop reasons** — still `CONTRACT_UNSATISFIED` on rejection-budget exhaustion.
- **No tests / verification scripts** (per `/design-doc-no-tests`).
- **No LLM-judged / schema / predicate contracts** — still deterministic only.
- **No non-linear runtime support.**
- **No `Agent(output_contracts=)` top-level param** — still only via `AgentLoopSettings`.
- **No rewriting of the #261 owner class API** beyond optional, backward-compatible report enrichment.
- **No new `max_compactions` / `max_cost` loop ceilings** in this PR (floors with `ceiling_key=None` are unbounded by settings validation; existing ceilings / middleware still terminate the run).
- **Not counting tool-result body compaction** (truncate/strip/hide per tool output) as a "context-window compaction event" for `MinCompactions` — only **provider message-history** compaction that actually mutates history.

---

## 3. Background & Context

### What already exists (main @ #261)

| Piece | Path | Role |
|-------|------|------|
| `OutputContract` base | `vidbyte/agents/contracts/__init__.py` | Declarative `key` / `ceiling_key` / `unit` / `category` + `satisfied()` / `error()` |
| Floors | `vidbyte/agents/contracts/floors.py` | `MinToolCalls`, `MinTokens`, `MinIterations`, `MinElapsedSeconds` |
| Owner | `vidbyte/agents/contract.py` | `AgentLoopSettingsOutputContract` — `active/unmet/exhausted/feedback/report` |
| Settings home | `vidbyte/agents/settings/loop.py` | `output_contracts=`, `max_contract_rejections=`, floor-vs-ceiling validation |
| Runtime enforcement | `vidbyte/agents/runtime.py` | Two boundaries: no-tool-calls + `isDone`; `_contract_counters`; rejections local |
| Stop reason | `AgentStopReason.CONTRACT_UNSATISFIED` | Exhausted reject budget |
| Design doc | `docs/design/output-contracts-loop-settings.md` | Architecture of the framework |
| Loop-settings skill | `skills/agentic-loop-settings/SKILL.md` | Ceilings catalog; **does not yet document floors deeply** |

Current counters snapshot (`_contract_counters`):

```python
{
  "iteration_count": int,
  "model_call_count": int,
  "tool_call_count": int,      # excludes internal tools (isDone)
  "tokens_used": int,
  "elapsed_seconds": float,    # middleware.clock() - started_at
}
```

### Why this extension now

The four v1 floors only cover "how much loop work." Product use cases need floors on **window survival** (compactions), **quality of tool work** (success / diversity / by-id), **non-empty finals**, **wall-clock presence**, and **research budget spend**. The deferred `MinCompactions` item from the original design is unblocked by adding a small runtime compaction counter.

### Relevant existing machinery (audit findings)

| Need | Existing source |
|------|-----------------|
| Successful tool outcomes | `ToolCallContext.state == ToolCallState.SUCCEEDED` (set in runtime when `ToolResult.status == success`) |
| Failures / denials | `FAILED` / `DENIED` (permission denials, tool settings denials, execution errors) |
| Distinct tool names | `ToolCallContext.tool_name` on `call_contexts` |
| Elapsed time | Already in counters as `elapsed_seconds` (`MinElapsedSeconds`) |
| Final assistant text | `last_assistant_output` (no-tool-calls path) / `result.output` (`isDone` path) — not yet in counters |
| Compaction events | Middleware transform metadata `{"compaction": mode, "before_count", "after_count"}` from `MessageHistoryCompactionMiddleware` / summary / trace replacement — **no counter today** |
| Cost estimate | `CostBudgetMiddleware` accumulates `_estimated_spend_usd` via `tokens / 1e6 * cost_per_million_tokens` — instance state, not yet in counters |
| Token≈chars heuristic | Compaction code uses `max(1, ceil(len(text)/4)) if text else 0` |

---

## 4. Requirements

### Functional Requirements

1. Create `skills/output-contracts/SKILL.md` covering: mental model, ownership, existing floors, counter keys, enforcement boundaries, process to add a floor, invariants, anti-patterns, related files.
2. Update `skills/agentic-loop-settings/SKILL.md` with a pointer section to output contracts + `max_contract_rejections` / stop reason.
3. Update `skills/sdk/update-skill-files.md` with an "Add or Change Output Contracts" matrix row.
4. Extend `_contract_counters` (and call sites) to include all keys needed by new floors (see §6.2).
5. Implement floors in **this order** (each depends only on prior counter work or is independent):

| Order | Floor | Depends on new telemetry? |
|------:|-------|---------------------------|
| 1 | `MinTimeTaken` alias | No (rename/export only) |
| 2 | `MinSuccessfulToolCalls` | Counter derived from `call_contexts` |
| 3 | `MinDistinctTools` | Counter derived from `call_contexts` |
| 4 | `MinToolCallsById` | Per-name map from `call_contexts` + custom `satisfied` |
| 5 | `MinFinalOutputChars` / `MinFinalOutputTokens` | Pass final text into counters |
| 6 | `MinCostSpent` | Cost estimate from middleware and/or explicit rate |
| 7 | `MinCompactions` | Runtime compaction counter |

6. Each floor must:
   - Reject non-positive `minimum` via existing base / subclass validation (`ConfigurationError`).
   - Participate in floor-vs-ceiling validation when `ceiling_key` is set.
   - Produce a clear `error()` string naming observed vs required.
   - Appear in `contract_evaluations` metadata via existing `report()`.
7. `MinCompactions` counts only **history-level** compaction events that **mutate** provider messages (`before_count != after_count` when both present; otherwise count when a `provider_messages` transform carries a `compaction` mode and replaces messages).
8. `MinSuccessfulToolCalls` counts non-internal contexts with `state is SUCCEEDED` only (excludes `FAILED`, `DENIED`, `REQUESTED`).
9. `MinDistinctTools` counts unique non-internal tool names that appear in `call_contexts` (any state — diversity of *attempted surface*, not only successes).
10. `MinToolCallsById(tool_name, minimum)` counts non-internal calls whose `tool_name` matches exactly; excludes internal tools.
11. `MinFinalOutputChars` / `MinFinalOutputTokens` measure the **candidate final assistant text at the evaluation boundary** (the text that would become the run output if contracts pass).
12. `MinTimeTaken` is a public alias of `MinElapsedSeconds` (same class object or thin subclass with identical key/ceiling/unit). Document both names; prefer documenting `MinElapsedSeconds` as canonical and `MinTimeTaken` as synonym.
13. `MinCostSpent` floors estimated USD spend. Prefer live `CostBudgetMiddleware` estimate when that middleware is on the pipeline; otherwise compute `tokens_used / 1e6 * cost_per_million_tokens` when the contract carries an explicit rate. Without either source, observed spend is `0` (floor stays unmet until rejection budget or other stop).
14. Empty `output_contracts` remains byte-for-byte inert.
15. No behavior change for existing four floors beyond additional counter keys in the snapshot (extra keys must not break existing `satisfied()` which only reads its own key).

### Non-Functional Requirements
- **Performance:** counter snapshot stays O(tool_calls) for context scans; compaction counter is O(1) increment per model-call hook; no extra LLM calls.
- **Concurrency:** do not store per-run counters on shared settings / contract instances. Compaction counter is a **local** in `_arun_once` (or run_state entry under a private key), not on middleware instances if that would leak across concurrent runs of shared middleware objects.
- **Reliability:** three-layer termination still holds (construction validation, ceilings / middleware aborts, `max_contract_rejections`).
- **Style:** class-first where non-trivial; one-line signatures; mandatory 1–2 line comment under every method; Context Protocol Header on new modules/skills.
- **Observability:** `contract_evaluations` continues to list each contract; optional enrichment with `observed` is allowed if cheap.

---

## 5. High-Level Design

```
skills/output-contracts/SKILL.md          << NEW contributor skill
skills/agentic-loop-settings/SKILL.md     << pointer + max_contract_rejections / stop reason
skills/sdk/update-skill-files.md          << matrix row

vidbyte/agents/contracts/floors.py        << new floor classes (+ MinTimeTaken alias)
vidbyte/agents/contracts/__init__.py      << re-exports
vidbyte/agents/__init__.py                << public re-exports
vidbyte/__init__.py                       << root re-exports if other floors are root-exported
                                          (today floors are agents-package exports only —
                                           keep that pattern unless root already exports them)

vidbyte/agents/runtime.py
  - extend _contract_counters(...)
  - pass final_output + compaction_count + cost estimate
  - increment compaction_count after before_model_call transform (history mutation)
  - optional: publish cost_spent_usd from CostBudgetMiddleware

vidbyte/middleware/builtins/cost_budget.py  (light touch, optional but preferred)
  - expose read-only estimated_spend_usd property
  - optionally publish to run_state["__result_metadata__"]["estimated_spend_usd"]

vidbyte/agents/settings/loop.py
  - no new settings fields required for these floors
  - existing _validate_output_contracts handles ceiling_key floors only
```

Data flow (unchanged control plane, richer counters):

```
AgentLoopSettings(output_contracts=[...new floors...])
        │
        ▼
AgentLoopSettingsOutputContract.unmet(counters)
        ▲
        │  counters from AgentRuntime._contract_counters(...)
        │    + successful_tool_call_count
        │    + distinct_tool_count
        │    + tool_calls_by_name: dict[str,int]
        │    + final_output_chars / final_output_tokens
        │    + cost_spent_usd
        │    + compaction_count
        │
AgentRuntime finalization boundaries (isDone / no-tool-calls)
```

**Key decisions**
1. **Prefer derived counters from `call_contexts`** when the data already exists — zero middleware changes for success/distinct/by-id.
2. **`MinCompactions` needs runtime-owned state** — middleware already emits transform metadata; the runtime is the correct place to count events without mutating shared middleware instances.
3. **`MinToolCallsById` and `MinCostSpent` override `satisfied`/`error`** — they are still `OutputContract` subclasses, just not pure three-attribute declarations.
4. **`MinFinalOutput*` requires threading final text into the snapshot** at both evaluation call sites.
5. **Sequential implementation commits** — one floor family per commit after skill + counter scaffolding, so review can reason about each floor’s semantics.

---

## 6. Detailed Design

### 6.1 Skill: `skills/output-contracts/SKILL.md`

**File(s):** `skills/output-contracts/SKILL.md`  
**Type:** New file

#### What it does
Canonical contributor guide for output contracts (analogous to `skills/tool-settings/SKILL.md`).

#### Skill outline (required sections)
1. **When to use** / when not to (vs loop ceilings, tool settings, middleware, evals).
2. **Mental model** — floors vs ceilings; decision vs action split; linear-only.
3. **Ownership map** — settings → owner → runtime boundaries; ASCII diagram.
4. **Existing surface** — table of all floors (v1 + this PR) with `key`, `ceiling_key`, unit, notes.
5. **Counter snapshot contract** — every key `_contract_counters` must emit, with source of truth.
6. **Enforcement algorithm** — isDone tool-result envelope; no-tool-calls user message; rejection budget; `CONTRACT_UNSATISFIED`.
7. **Process: add a new floor** (checklist):
   - Declare class in `floors.py` (or override methods if needed)
   - Export from `contracts/__init__.py` + `agents/__init__.py`
   - Add counter key to `_contract_counters` (and any producers)
   - Set `ceiling_key` only if an `AgentLoopSettings` field is a true paired ceiling
   - Update this skill + agentic-loop-settings pointer + update-skill-files matrix
8. **Invariants** (must not break).
9. **What NOT to do**.
10. **Related files** table.

#### Edge cases documented in skill
- Provider never reports tokens → `MinTokens` / cost floors stuck at 0.
- `isDone` excluded from tool effort counters.
- Ceiling trip beats contract exhaustion (stop reason is `MAX_*` / middleware abort, not `contract_unsatisfied`).
- Compaction middleware absent → `compaction_count` stays 0.
- Cost middleware absent and no rate on contract → `cost_spent_usd` stays 0.

---

### 6.2 Runtime counter snapshot extensions

**File(s):** `vidbyte/agents/runtime.py`  
**Type:** Modified

#### Interface / API
```python
def _contract_counters(
    self,
    *,
    iteration_count: int,
    model_call_count: int,
    call_contexts: Sequence[ToolCallContext],
    tokens_used: int | None,
    started_at: float,
    final_output: str | None = None,
    compaction_count: int = 0,
) -> dict[str, Any]:
    # Packages live runtime counters for output-contract evaluation.
```

#### Full snapshot keys after this PR
| Key | Type | Source |
|-----|------|--------|
| `iteration_count` | int | loop local |
| `model_call_count` | int | loop local |
| `tool_call_count` | int | non-internal contexts (existing) |
| `successful_tool_call_count` | int | non-internal + `SUCCEEDED` |
| `distinct_tool_count` | int | unique non-internal tool names |
| `tool_calls_by_name` | `dict[str, int]` | non-internal name histogram |
| `tokens_used` | int | provider cumulative (or 0) |
| `elapsed_seconds` | float | `clock() - started_at` |
| `final_output_chars` | int | `len(final_output or "")` |
| `final_output_tokens` | int | approx tokens of final output |
| `cost_spent_usd` | float | middleware estimate or 0 (rate-bearing contracts may recompute) |
| `compaction_count` | int | runtime-owned event counter |

#### Logic / Algorithm
1. Keep existing keys for backward compatibility.
2. Add helpers (private methods, class-first style):
   - `_count_non_internal_tool_contexts(call_contexts)`
   - `_successful_tool_call_count(call_contexts)`
   - `_distinct_tool_count(call_contexts)`
   - `_tool_calls_by_name(call_contexts)`
   - `_approx_output_tokens(text: str) -> int` using `max(1, math.ceil(len(text) / 4)) if text else 0`
   - `_cost_spent_usd(tokens_used) -> float` (see §6.9)
   - `_compaction_event_delta(decision: MiddlewareDecision) -> int` (see §6.8)
3. Both finalization call sites pass `final_output=...` and the live `compaction_count` local.
4. In `_arun_once`, introduce `compaction_count = 0` next to `rejections = 0`.
5. After every successful `before_model_call` decision that continues, `compaction_count += self._compaction_event_delta(decision)`.

#### Edge Cases & Error Handling
- Missing final output → chars/tokens = 0.
- Empty `call_contexts` → all tool-derived counters 0 / empty map.
- Concurrent runs: compaction counter is loop-local only.

---

### 6.3 `MinTimeTaken` (alias)

**File(s):** `vidbyte/agents/contracts/floors.py`, exports  
**Type:** Modified

#### What it does
Public synonym for `MinElapsedSeconds` so API language matches product language ("time taken").

#### Interface / API
```python
class MinElapsedSeconds(OutputContract):
    key = "elapsed_seconds"
    ceiling_key = "timeout_seconds"
    unit = "seconds"

MinTimeTaken = MinElapsedSeconds  # public alias
```

#### Logic / Algorithm
1. Prefer alias assignment (same class, `name` property stays `MinElapsedSeconds` via `type(self).__name__`).
2. **Problem:** `name` would remain `MinElapsedSeconds` even when constructed as `MinTimeTaken(30)` if alias points to same class.
3. **Decision:** use a thin subclass instead so metadata/report names distinguish cleanly:

```python
class MinTimeTaken(MinElapsedSeconds):
    """Alias floor: require minimum wall-clock seconds before stop (same counters as MinElapsedSeconds)."""
    # inherits key/ceiling_key/unit; name becomes MinTimeTaken
```

#### Edge Cases
- Same ceiling validation as `MinElapsedSeconds` (`timeout_seconds`).
- `timeout_seconds` still not enforced as a runtime `_budget_stop` on main (documented limitation remains).

---

### 6.4 `MinSuccessfulToolCalls`

**File(s):** `floors.py`  
**Type:** Modified (new class)

```python
class MinSuccessfulToolCalls(OutputContract):
    """Require at least `minimum` non-internal tools that finished with SUCCEEDED state."""

    key = "successful_tool_call_count"
    ceiling_key = "max_tool_calls"  # cannot require more successes than total call ceiling
    unit = "successful tool calls"
```

#### Logic
1. Pure declaration; base `satisfied` compares counters.
2. Runtime counter: `sum(1 for c in call_contexts if not internal and c.state is ToolCallState.SUCCEEDED)`.
3. Permission denials (`DENIED`) and failures do **not** count — anti-gaming intent.

#### Edge Cases
- Denied-then-retry success later: each context is one attempt; only SUCCEEDED rows count.
- Internal tools never count.

---

### 6.5 `MinDistinctTools`

```python
class MinDistinctTools(OutputContract):
    """Require at least `minimum` unique non-internal tool names used in the run."""

    key = "distinct_tool_count"
    ceiling_key = None  # no settings ceiling for distinct tools
    unit = "distinct tools"
```

#### Logic
1. Counter: `len({c.tool_name for c in call_contexts if not internal})`.
2. Counts attempts of any state (spam of one tool fails the floor; diversifying surface satisfies it).
3. **Why any state, not only success:** the floor is about action-surface diversity, not outcome quality (`MinSuccessfulToolCalls` covers quality).

#### Edge Cases
- Same tool failed 10 times → distinct = 1.
- No tools → 0.

---

### 6.6 `MinToolCallsById`

```python
class MinToolCallsById(OutputContract):
    """Require at least `minimum` non-internal calls to one named tool."""

    key = "tool_calls_by_name"
    ceiling_key = None
    unit = "calls"

    def __init__(self, tool_name: str, minimum: int) -> None:
        # Validates tool_name and minimum; stores the target tool identity.
        ...

    def satisfied(self, counters: Mapping[str, Any]) -> bool:
        # Returns whether the named tool's call count meets the minimum.
        ...

    def error(self, counters: Mapping[str, Any]) -> str:
        # Builds corrective text including the tool name and observed count.
        ...
```

#### Logic / Algorithm
1. Normalize `tool_name = tool_name.strip()`; reject empty with `ConfigurationError`.
2. `minimum` via `super().__init__(minimum)` (rejects `<= 0`).
3. Identification: **tool name string** (matches `ToolCall.tool_name` / `ToolSpec.name`). There is no separate opaque tool id in the SDK tool call path today — name is the public identity.
4. `satisfied`: `(counters.get("tool_calls_by_name") or {}).get(self.tool_name, 0) >= self.minimum`.
5. `error`: `"Only {n} calls to '{tool}' so far; at least {minimum} are required before finishing. Keep working."`
6. Optional enhancement to `AgentLoopSettingsOutputContract.report`: include `"tool_name"` when `getattr(contract, "tool_name", None)`.

#### Ceiling validation (optional stretch)
If `AgentLoopSettings.tool_settings` is set and `max_calls_per_tool[tool_name]` exists, validate `minimum < max_calls_per_tool[tool_name]` inside `AgentLoopSettings._validate_output_contracts` via a dedicated branch for `MinToolCallsById`. **Include this** — it matches the floor-vs-ceiling spirit without inventing a new settings field.

#### Edge Cases
- Tool never attached but name required → floor never met until budget exhaustion (correct: configuration/runtime responsibility).
- Case-sensitive name match (consistent with tool registry / ToolSettings deny lists).

---

### 6.7 `MinFinalOutputChars` / `MinFinalOutputTokens`

```python
class MinFinalOutputChars(OutputContract):
    key = "final_output_chars"
    ceiling_key = None
    unit = "final output characters"

class MinFinalOutputTokens(OutputContract):
    key = "final_output_tokens"
    ceiling_key = None
    unit = "final output tokens"
```

#### Logic
1. At evaluation, runtime passes the candidate final string into `_contract_counters`.
2. Chars: `len(text)`.
3. Tokens: approximate with shared helper (chars/4 ceiling) — **deterministic, no tokenizer dependency**. Document that this is an estimate, not provider tokenizer truth.
4. Empty / whitespace-only text still has length 0 for empty string; whitespace counts as characters (crude anti-empty, not anti-whitespace). **Decision:** do **not** strip — keep fully deterministic `len(text)`.

#### Edge Cases
- Structured `output_schema` JSON finals still measure the serialized assistant text the runtime would return.
- Rejection path: after inject-and-continue, next finalization re-measures the new candidate.

---

### 6.8 `MinCompactions`

```python
class MinCompactions(OutputContract):
    """Require at least `minimum` successful context-history compaction events before stop."""

    key = "compaction_count"
    ceiling_key = None  # no max_compactions on AgentLoopSettings today
    unit = "compactions"
```

#### Runtime counting algorithm
1. Local `compaction_count = 0` in `_arun_once`.
2. In `_invoke_with_middleware`, after `before_model_call` returns `CONTINUE`, compute delta:

```python
def _compaction_event_delta(self, decision: MiddlewareDecision) -> int:
    # Returns 1 when a history compaction transform actually mutated provider messages.
    transform = decision.transform
    if transform is None or transform.provider_messages is None:
        return 0
    meta = dict(transform.metadata or {})
    if "compaction" not in meta:
        return 0
    before = meta.get("before_count")
    after = meta.get("after_count")
    if before is not None and after is not None:
        return 1 if int(before) != int(after) else 0
    # Compaction transform present without counts → count conservatively as one event.
    return 1
```

3. Pass `compaction_count` into `_contract_counters`.
4. **Do not** count `ToolResultCompactionMiddleware` (after_tool_call model-visible truncation) — not a window-survival event.
5. **Do not** require a new middleware class for v1.

#### Why not store the counter on middleware?
Shared middleware instances across concurrent agent runs would race. Loop-local counter is consistent with `rejections`.

#### Edge Cases
- Compaction middleware runs every iteration but often no-ops (same before/after counts) → no increment.
- No compaction middleware → count stays 0 → floor unmet (developer must attach compaction middleware for this floor to be reachable).
- Agent-invoked compaction **tools** are tool calls, not automatic compaction events (they may still help distinct/success floors).

#### Optional follow-up (not this PR)
- `max_compactions` ceiling on settings.
- Counting agent tool-driven compaction if product wants unified "window edits".

---

### 6.9 `MinCostSpent`

```python
class MinCostSpent(OutputContract):
    """Require estimated USD spend to reach `minimum` before stop."""

    key = "cost_spent_usd"
    ceiling_key = None
    unit = "USD"

    def __init__(self, minimum: float, *, cost_per_million_tokens: float | None = None) -> None:
        # Validates minimum and optional rate used when cost middleware is absent.
        ...

    def satisfied(self, counters: Mapping[str, Any]) -> bool:
        # Compares estimated spend (middleware counter or local rate × tokens) to minimum.
        ...

    def error(self, counters: Mapping[str, Any]) -> str:
        # Corrective message with observed USD vs required.
        ...
```

#### Spend resolution order (in contract `satisfied` / shared helper)
1. If `counters["cost_spent_usd"] > 0` or middleware published a value (including 0 after reset mid-run once tokens exist), prefer counters.
2. Runtime `_cost_spent_usd`:
   - Scan `self.middleware.middleware` for `CostBudgetMiddleware` instances; if found, read a **public property** `estimated_spend_usd` (add property wrapping `_estimated_spend_usd` — no new private access from runtime without a property).
   - Else return `0.0`.
3. Contract override: if runtime counter is 0 and `self.cost_per_million_tokens` is set, compute `(counters.get("tokens_used") or 0) / 1_000_000 * self.cost_per_million_tokens`.
4. Formula must match `CostBudgetMiddleware` exactly: `tokens / 1e6 * rate`.

#### CostBudgetMiddleware light change
```python
@property
def estimated_spend_usd(self) -> float:
    # Returns the current estimated USD spend for this middleware instance.
    return self._estimated_spend_usd
```

Document concurrency caveat: CostBudgetMiddleware already uses instance fields (pre-existing pattern); this PR does not rework it to run_state, but notes the known limitation.

#### Edge Cases
- Floor without middleware and without rate → always 0 → unreachable without rejection budget / other stop. Construction **warn?** No — no logging framework requirement; skill documents configuration.
- Rate required when? **Optional.** Prefer middleware. Skill shows both patterns.
- `minimum` is float (USD); base currently accepts `int | float` — good.

#### Validation
- Reject `cost_per_million_tokens is not None and cost_per_million_tokens <= 0`.
- No `AgentLoopSettings` ceiling pairing (cost ceiling is middleware `max_spend_usd`, cross-object). **Optional stretch:** if middleware is present at agent construction we cannot easily validate floor < ceiling without scanning middleware on settings construction (settings don't hold middleware). **Skip cross-validation** in this PR; document that floors + cost ceilings are configured together by the developer.

---

### 6.10 Owner `report` enrichment (small, optional)

**File(s):** `vidbyte/agents/contract.py`  
**Type:** Modified (optional)

```python
{"name": ..., "satisfied": ..., "minimum": ..., "observed": <scalar if available>}
```

For map-backed `MinToolCallsById`, `observed` is the per-tool count; include `"tool_name"`. Keep backward compatible (additive keys only).

---

### 6.11 Exports

| Module | Export additions |
|--------|------------------|
| `vidbyte/agents/contracts/floors.py` | all new classes + alias subclass |
| `vidbyte/agents/contracts/__init__.py` | re-export + `__all__` |
| `vidbyte/agents/__init__.py` | re-export + `__all__` |
| `vidbyte/__init__.py` | only if other contract symbols are already root-exported (today: **no** — keep agents-package exports only) |

---

### 6.12 Skill + docs cross-links

| File | Change |
|------|--------|
| `skills/output-contracts/SKILL.md` | **CREATE** full skill |
| `skills/agentic-loop-settings/SKILL.md` | Add § Output Contracts: floors vs ceilings, `output_contracts`, `max_contract_rejections`, `contract_unsatisfied`, link to skill |
| `skills/sdk/update-skill-files.md` | New matrix: Add or Change Output Contracts |
| `docs/design/output-contract-skill-and-extended-floors.md` | This design doc |

---

## 7. Data Model Changes

N/A — no database or persisted schema.

In-memory / API-level type surface:

### 7.1 Counters mapping (extended)

```python
ContractCounters = Mapping[str, Any]
# documented keys listed in §6.2
```

### 7.2 `CostBudgetMiddleware.estimated_spend_usd`

**Change type:** Modified (public read-only property)

No migration.

---

## 8. API Changes

N/A — no HTTP endpoints.

### 8.1 Public Python API (additive)

```python
from vidbyte.agents import (
    OutputContract,
    MinToolCalls,
    MinTokens,
    MinIterations,
    MinElapsedSeconds,
    MinTimeTaken,              # NEW
    MinSuccessfulToolCalls,    # NEW
    MinDistinctTools,          # NEW
    MinFinalOutputChars,       # NEW
    MinFinalOutputTokens,      # NEW
    MinToolCallsById,          # NEW
    MinCompactions,            # NEW
    MinCostSpent,              # NEW
    AgentLoopSettings,
)

settings = AgentLoopSettings(
    max_tool_calls=40,
    max_tokens=200_000,
    timeout_seconds=600,
    max_contract_rejections=5,
    output_contracts=[
        MinTimeTaken(30),
        MinSuccessfulToolCalls(8),
        MinDistinctTools(3),
        MinToolCallsById("web_search", 4),
        MinFinalOutputChars(500),
        MinFinalOutputTokens(120),
        MinCompactions(1),
        MinCostSpent(0.02, cost_per_million_tokens=3.0),
    ],
    tool_settings=ToolSettings(max_calls_per_tool={"web_search": 10}),
)
```

**Error cases (construction):**

| Condition | Error |
|-----------|-------|
| `minimum <= 0` | `ConfigurationError` |
| floor `>=` paired ceiling | `ConfigurationError` |
| `MinToolCallsById` empty tool name | `ConfigurationError` |
| `MinToolCallsById.minimum >= tool_settings.max_calls_per_tool[name]` when set | `ConfigurationError` |
| `MinCostSpent` rate `<= 0` when provided | `ConfigurationError` |
| Active contracts + non-linear runtime | `ConfigurationError` (existing) |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/output-contract-skill-and-extended-floors.md` | This design doc |
| CREATE | `skills/output-contracts/SKILL.md` | Contributor skill for output contracts |
| MODIFY | `skills/agentic-loop-settings/SKILL.md` | Point to output contracts; document floors params |
| MODIFY | `skills/sdk/update-skill-files.md` | Matrix entry for output-contract changes |
| MODIFY | `vidbyte/agents/contracts/floors.py` | All new floors + `MinTimeTaken` |
| MODIFY | `vidbyte/agents/contracts/__init__.py` | Re-exports + `__all__` |
| MODIFY | `vidbyte/agents/__init__.py` | Public re-exports |
| MODIFY | `vidbyte/agents/runtime.py` | Counter extensions, compaction local, final_output pass-through, cost read |
| MODIFY | `vidbyte/agents/settings/loop.py` | Optional `MinToolCallsById` vs `max_calls_per_tool` validation |
| MODIFY | `vidbyte/agents/contract.py` | Optional report enrichment (`observed` / `tool_name`) |
| MODIFY | `vidbyte/middleware/builtins/cost_budget.py` | Public `estimated_spend_usd` property |

**Summary:** **2 created, 9 modified, 0 deleted.**

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| (none new) | — | Uses existing middleware, tool call contexts, stdlib `math` | Low |

No new third-party packages.

---

## 11. Rollout & Deployment

- **Feature flags:** none — inert unless floors are configured.
- **Breaking change:** no. Additive counters and classes; existing floors unchanged in semantics.
- **Migration:** none.
- **Deployment:** single library PR.
- **Rollback:** revert PR.
- **Implementation sequencing after approval** (Phase 4):
  1. Commit design doc.
  2. Skill + cross-links (docs-first so implementers follow the process).
  3. Runtime counter scaffolding (all keys, compaction local, final_output arg) as one commit.
  4. Floors in order §4 table — one commit per floor (or per tightly-coupled pair `MinFinalOutputChars`+`Tokens`).
  5. Exports + settings validation for by-id.
  6. Self-critique refinement pass.

---

## 12. Open Questions

- [x] **Tool identity for `MinToolCallsById`:** tool **name** string (only stable public id on `ToolCall` / `ToolCallContext`). No separate tool UUID.
- [x] **`MinDistinctTools` counts failed attempts:** yes — diversity of action surface.
- [x] **`MinCompactions` counts only mutating history compaction:** yes.
- [x] **`MinTimeTaken` thin subclass vs alias:** thin subclass for stable `name` in metadata.
- [ ] **`MinCostSpent` without middleware or rate:** leave unreachable (documented) vs raise at settings construction if neither can ever produce spend? **Assumption for this design:** allow construction; skill documents that developers must attach `CostBudgetMiddleware` and/or pass `cost_per_million_tokens`. Confirm if you want fail-fast construction when rate is omitted.
- [ ] **Should `report()` always include `observed`?** **Assumption:** yes, additive enrichment — cheap and improves debugging.
- [ ] **Root package export of new floors?** **Assumption:** keep `vidbyte.agents` exports only (matches #261).

---

## 13. Alternatives Considered

### Alternative 1: Count tool-result truncations as compactions
- What: Increment on `ToolResultCompactionMiddleware` after_tool_call transforms.
- Why rejected: User intent is long-horizon **window pressure survival**, not per-result truncation. Truncation fires far more often and is gameable.

### Alternative 2: Dedicated `CompactionCounterMiddleware`
- What: New middleware that only increments a counter.
- Why rejected: Extra composition burden; transform metadata already exists; runtime can observe it without a new type.

### Alternative 3: Store compaction_count on middleware instances
- What: Each compaction middleware tracks `self.events`.
- Why rejected: Shared middleware + concurrent runs race; violates the "no per-run state on shared objects" invariant used by ToolSettings / contracts.

### Alternative 4: `MinCostSpent` only via CostBudgetMiddleware (no rate param)
- What: Floor unusable without attaching cost middleware.
- Why rejected: Cost middleware is a *ceiling* tool; forcing it for a floor couples unrelated concerns. Optional rate keeps the floor usable alone while still preferring middleware counters when present.

### Alternative 5: Provider tokenizer for `MinFinalOutputTokens`
- What: Call provider/tiktoken for exact counts.
- Why rejected: Non-deterministic across environments, new deps, slower; product ask is "cheap and fully deterministic."

### Alternative 6: Broaden `OutputContract` base with pluggable extractors
- What: Register counter extractors per key.
- Why rejected: Over-architecture for a fixed set of deterministic floors; keep base simple and put special cases on subclasses.

---

## Implementation notes for Phase 4 (after approval)

Worktree branch: `feat/output-contract-skill-and-extended-floors` from updated `main`.

Commit plan:
1. `docs: add design doc for output-contract skill and extended floors`
2. `docs(skills): add output-contracts skill and cross-links`
3. `feat(runtime): extend contract counter snapshot for new floors`
4. `feat(contracts): add MinTimeTaken alias floor`
5. `feat(contracts): add MinSuccessfulToolCalls`
6. `feat(contracts): add MinDistinctTools`
7. `feat(contracts): add MinToolCallsById + settings validation`
8. `feat(contracts): add MinFinalOutputChars and MinFinalOutputTokens`
9. `feat(contracts): add MinCostSpent + cost middleware property`
10. `feat(contracts): add MinCompactions`
11. refinement commits as needed

No tests (skill constraint). Manual smoke is optional and out of scope unless requested.

---

END OF DESIGN DOC
