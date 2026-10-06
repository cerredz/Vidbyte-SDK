---
name: output-contracts
description: >-
  Explains OutputContract effort floors owned by AgentLoopSettings — when an
  agent MAY stop — and the process for adding new deterministic floors.
  Use when adding floors, wiring counters in AgentRuntime, or reviewing
  output-contract PRs.
---

<!-- Context Protocol Header
Description:
    Contributor guide for output contracts (deterministic effort floors).
Purpose:
    Documents the floors-vs-ceilings model, ownership split, counter snapshot,
    enforcement boundaries, and the checklist for adding a new floor.
Architecture:
    SDK Skill Guide (contributor process).
Relations:
    Located in skills/output-contracts/SKILL.md.
    Implementation: vidbyte/agents/contracts/, contract.py, settings/loop.py, runtime.py.
    Design: docs/design/output-contracts-loop-settings.md,
            docs/design/output-contract-skill-and-extended-floors.md.
Similar Files:
    - skills/tool-settings/SKILL.md
    - skills/agentic-loop-settings/SKILL.md
-->

# Output Contracts Skill Guide

Use this skill when you need to **understand, add, or review** output contracts
(deterministic **effort floors**) in the Vidbyte SDK.

Related:

- Loop ceilings catalog: `skills/agentic-loop-settings/SKILL.md`
- Framework design: `docs/design/output-contracts-loop-settings.md`
- Extended floors design: `docs/design/output-contract-skill-and-extended-floors.md`
- Skill update matrix: `skills/sdk/update-skill-files.md`

---

## 1. When to Use This Skill

**Use it when:**

- Adding a new `OutputContract` floor
- Changing counter snapshot keys in `AgentRuntime._contract_counters`
- Wiring contract evaluation at finalization boundaries
- Reviewing a PR that touches `vidbyte/agents/contracts/`, `contract.py`, or
  contract-related runtime/settings code

**Do not use it for:**

| Concern | Put it here instead |
|---------|---------------------|
| Loop budgets that force stop (`max_iterations`, `max_tokens`, `max_tool_calls`) | Flat `AgentLoopSettings` fields — `skills/agentic-loop-settings/SKILL.md` |
| Universal tool deny / thrash budgets | `ToolSettings` — `skills/tool-settings/SKILL.md` |
| Cost *ceilings* that abort the run | `CostBudgetMiddleware` |
| LLM-as-judge quality checks after a run | Evals / graders |
| Semantic / schema contracts | Deferred — not shipped |

---

## 2. Mental Model

```
Ceilings (AgentLoopSettings)  →  when the agent MUST stop
Floors   (output contracts)   →  when the agent MAY stop
```

An agent that calls `isDone` (or returns a final response with no tool calls)
before floors are met does **not** finish. The runtime injects corrective
feedback and continues the loop until either:

1. All floors are satisfied → normal stop (`is_done` / `final_response`), or
2. `max_contract_rejections` is exhausted → `contract_unsatisfied`, or
3. A ceiling / middleware abort fires first (ceiling wins).

### Ownership split

```
AgentLoopSettings(output_contracts=[...], max_contract_rejections=3)
        │  constructs + validates floor < ceiling
        ▼
AgentLoopSettings.output_contract  : AgentLoopSettingsOutputContract
        │  linear runtime only (base._runtime)
        ▼
AgentRuntime.output_contract
        │  at isDone / no-tool-calls boundaries:
        │    counters = _contract_counters(...)
        │    unmet = output_contract.unmet(counters)
        ▼
  unmet + budget remaining → inject feedback + continue
  unmet + budget exhausted → stop(CONTRACT_UNSATISFIED)
  all satisfied            → finalize normally
```

| Concern | Owner |
|---------|--------|
| Floor declarations (`key`, `minimum`, `satisfied`) | `OutputContract` subclasses |
| Floor-vs-ceiling validation | `AgentLoopSettings` |
| `active` / `unmet` / `exhausted` / `feedback` / `report` | `AgentLoopSettingsOutputContract` |
| Counters snapshot + injection envelopes + `break`/`continue` | `AgentRuntime` |
| Per-run rejection count | Local in `_arun_once` (not on owner) |

**Concurrency rule:** never store per-run counters on shared contract or
settings instances. Compaction count and rejections are loop-locals.

---

## 3. Configuration (developer-facing)

```python
from vidbyte.agents import (
    Agent,
    AgentLoopSettings,
    MinToolCalls,
    MinSuccessfulToolCalls,
    MinDistinctTools,
    MinToolCallsById,
    MinFinalOutputChars,
    MinElapsedSeconds,
    MinTimeTaken,
    MinCompactions,
    MinCostSpent,
)

agent = Agent(
    name="researcher",
    system_prompt="Research thoroughly before finishing.",
    runner=my_runner,
    tools=[search, browse, write_notes],
    agent_loop_settings=AgentLoopSettings(
        max_tool_calls=40,
        max_tokens=200_000,
        timeout_seconds=600,
        max_contract_rejections=5,
        output_contracts=[
            MinToolCalls(5),
            MinSuccessfulToolCalls(4),
            MinDistinctTools(2),
            MinToolCallsById("search", 3),
            MinFinalOutputChars(400),
            MinTimeTaken(30),  # alias of MinElapsedSeconds
            MinCompactions(1),
            MinCostSpent(0.02, cost_per_million_tokens=3.0),
        ],
    ),
)
```

Public imports:

```python
from vidbyte.agents import OutputContract, MinToolCalls, MinCompactions, ...
from vidbyte.agents.contracts import MinCostSpent, MinToolCallsById
```

There is **no** `Agent(output_contracts=...)` parameter. Contracts only live on
`AgentLoopSettings`.

Linear runtime only. Non-linear runtimes raise `ConfigurationError` when
`output_contract.active()` is true.

---

## 4. Floor Catalog

| Floor | Counter key | Ceiling key | Notes |
|-------|-------------|-------------|-------|
| `MinToolCalls` | `tool_call_count` | `max_tool_calls` | Excludes internal tools (`isDone`) |
| `MinSuccessfulToolCalls` | `successful_tool_call_count` | `max_tool_calls` | `ToolCallState.SUCCEEDED` only |
| `MinDistinctTools` | `distinct_tool_count` | — | Unique non-internal names (any state) |
| `MinToolCallsById(name, n)` | `tool_calls_by_name[name]` | `ToolSettings.max_calls_per_tool[name]` when set | Tool **name** is the identity |
| `MinTokens` | `tokens_used` | `max_tokens` | Provider-reported cumulative tokens |
| `MinIterations` | `iteration_count` | `max_iterations` | Loop iterations |
| `MinElapsedSeconds` / `MinTimeTaken` | `elapsed_seconds` | `timeout_seconds` | Wall clock; same counters |
| `MinFinalOutputChars` | `final_output_chars` | — | `len(candidate final text)` |
| `MinFinalOutputTokens` | `final_output_tokens` | — | Deterministic ≈ `ceil(chars/4)` |
| `MinCompactions` | `compaction_count` | — | Mutating **history** compaction only |
| `MinCostSpent` | `cost_spent_usd` (+ optional rate×tokens) | — | Prefer `CostBudgetMiddleware` |

---

## 5. Counter Snapshot Contract

Built by `AgentRuntime._contract_counters(...)` at each finalization attempt:

| Key | Source |
|-----|--------|
| `iteration_count` | Loop local |
| `model_call_count` | Loop local |
| `tool_call_count` | Non-internal contexts |
| `successful_tool_call_count` | Non-internal + `SUCCEEDED` |
| `distinct_tool_count` | Unique non-internal names |
| `tool_calls_by_name` | Histogram of non-internal names |
| `tokens_used` | Provider cumulative (or 0) |
| `elapsed_seconds` | `middleware.clock() - started_at` |
| `final_output_chars` | Length of candidate final assistant text |
| `final_output_tokens` | Approx tokens of that text |
| `cost_spent_usd` | `CostBudgetMiddleware.estimated_spend_usd` or 0 |
| `compaction_count` | Loop-local count of mutating history compactions |

Internal tools (`isDone`, tools with `metadata["internal"]`) never count toward
tool effort floors.

---

## 6. Enforcement Algorithm

### Boundaries

1. **No-tool-calls / final response** — evaluate before `FINAL_RESPONSE`.
   Unmet → append **user** message with feedback → `continue`.
2. **`isDone` tool** — evaluate before `IS_DONE`.
   Unmet → append **error tool-result** for the `isDone` call → continue loop.
   (Keeps the provider transcript valid: every tool call gets a result.)

### Rejection budget

- `AgentLoopSettings.max_contract_rejections` (default `3`, must be `> 0`).
- Each unmet finalization attempt increments a run-local `rejections` counter.
- When `rejections >= max_contract_rejections`, stop with
  `AgentStopReason.CONTRACT_UNSATISFIED` (`"contract_unsatisfied"`).

### Metadata

`AgentResult.metadata["contract_evaluations"]` is a list of:

```python
{"name": str, "satisfied": bool, "minimum": number, "observed": Any, "tool_name"?: str}
```

---

## 7. Compaction Counting (`MinCompactions`)

After each `before_model_call` that continues, the runtime inspects the
middleware transform:

- Must include `provider_messages` and metadata key `"compaction"`.
- If `before_count` / `after_count` present → count only when they differ.
- Else → count 1 conservatively.

**Does not count:** `ToolResultCompactionMiddleware` (per-tool output truncate/strip/hide).

**Requires:** history compaction middleware (e.g. `MessageHistoryCompactionMiddleware`)
on the agent, or the counter stays 0 and the floor is unreachable until rejection budget.

---

## 8. Cost Floor (`MinCostSpent`)

Resolution order inside the contract:

1. Use `counters["cost_spent_usd"]` when middleware reported spend `> 0`, or when
   no fallback rate is configured.
2. Else if `cost_per_million_tokens` was passed to the contract, compute
   `tokens_used / 1e6 * rate` (same formula as `CostBudgetMiddleware`).
3. Else observed spend is `0`.

`CostBudgetMiddleware` exposes `estimated_spend_usd` for the runtime to snapshot.

---

## 9. Process: Add a New Floor

Follow every step.

### Step 1 — Declare the floor

**File:** `vidbyte/agents/contracts/floors.py`

1. Subclass `OutputContract`.
2. Set `key`, `ceiling_key` (or `None`), `unit`.
3. Override `satisfied` / `error` / `observed` only when the counter is not a
   simple scalar compare.
4. Reject invalid constructor args with `ConfigurationError`.

### Step 2 — Export

| Module | Action |
|--------|--------|
| `vidbyte/agents/contracts/__init__.py` | Import + `__all__` |
| `vidbyte/agents/__init__.py` | Re-export + `__all__` |

### Step 3 — Counter wiring

**File:** `vidbyte/agents/runtime.py`

1. Extend `_contract_counters` with the new key.
2. Add a small private helper if the derivation is non-trivial.
3. Thread any new loop-local state (like `compaction_count`) through the call
   sites that evaluate contracts — **do not** store it on shared settings.

### Step 4 — Ceiling validation (if paired)

**File:** `vidbyte/agents/settings/loop.py`

- Scalar floors with `ceiling_key` are covered by `_validate_contract_ceiling`.
- Special pairings (e.g. `MinToolCallsById` vs `max_calls_per_tool`) need an
  explicit helper in `_validate_output_contracts`.

### Step 5 — Docs / skills

| File | Update |
|------|--------|
| `skills/output-contracts/SKILL.md` | Floor table + counter keys + process notes |
| `skills/agentic-loop-settings/SKILL.md` | Pointer / stop reason if needed |
| `skills/sdk/update-skill-files.md` | Keep matrix accurate |
| `docs/design/...` | Non-trivial architecture only |

### Step 6 — Smoke checklist

- [ ] `from vidbyte.agents import NewFloor` works
- [ ] `minimum <= 0` raises `ConfigurationError`
- [ ] Floor appears in `contract_evaluations` with `observed`
- [ ] Unmet finalization continues; exhaustion → `contract_unsatisfied`
- [ ] Empty `output_contracts` still no-ops
- [ ] Non-linear + active contracts still rejected at construction

---

## 10. Invariants (Do Not Break)

1. **Settings own contracts** — no top-level `Agent(output_contracts=)`.
2. **Owner is stateless** — rejections are loop-local.
3. **Runtime owns control flow** — owner only decides unmet/exhausted/feedback.
4. **Internal tools excluded** from tool effort counters.
5. **Linear-only** enforcement today.
6. **Empty contracts inert** — `active()` false, no per-iteration cost.
7. **Ceilings still win** when they fire first.
8. **`ConfigurationError` at construction** for unreachable floors / bad minima.
9. **No per-run state on shared middleware/settings** for contract counters
   (compaction uses a loop local).
10. **Additive counters** — new keys must not change semantics of existing floors.

---

## 11. What NOT to Do

- **Do not** invent a second home for contracts on `Agent` or `AgentRuntimeConfig`.
- **Do not** put rejection counters on `AgentLoopSettingsOutputContract`.
- **Do not** count tool-result truncation as a `MinCompactions` event.
- **Do not** count `isDone` toward tool floors.
- **Do not** require provider tokenizers for final-output floors.
- **Do not** assume cost floors work without middleware **or** an explicit rate.
- **Do not** support non-linear runtimes without a dedicated design.

---

## 12. Related Files

| Path | Role |
|------|------|
| `vidbyte/agents/contracts/__init__.py` | `OutputContract` base + exports |
| `vidbyte/agents/contracts/floors.py` | Prebuilt floors |
| `vidbyte/agents/contract.py` | Runtime owner |
| `vidbyte/agents/settings/loop.py` | Config home + validation |
| `vidbyte/agents/runtime.py` | Counters + enforcement boundaries |
| `vidbyte/agents/base.py` | Linear-only wiring / non-linear guard |
| `vidbyte/middleware/builtins/cost_budget.py` | Cost ceiling middleware + `estimated_spend_usd` |
| `vidbyte/lib/dataclasses/agents.py` | `AgentStopReason.CONTRACT_UNSATISFIED` |
| `docs/design/output-contracts-loop-settings.md` | Framework design |
| `docs/design/output-contract-skill-and-extended-floors.md` | Extended floors design |
