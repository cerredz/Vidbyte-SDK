# Design Doc: Agent Behavior Efficiency Predicates

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-24
**Last Updated:** 2026-06-24

---

## 1. Overview

This feature adds `agent.behavior.efficiency`, a new post-run behavior category for detecting redundant tool use, excessive loop length, repeated arguments/results, budget stops, and tool-failure thrashing. The implementation stays inside the existing behavior facade under `vidbyte/evals/behavior/`, reads only `RunProbe` data already produced by completed agent runs, and intentionally avoids changing agent runtime loop logic.

---

## 2. Goals & Non-Goals

### Goals

- Add an `EfficiencyBehavior` category exposed as `agent.behavior.efficiency`.
- Implement as many deterministic efficiency predicates as possible using existing `RunProbe` fields: `tool_calls`, `tool_call_count`, `iteration_count`, `tokens_used`, and `stop_reason`.
- Support exact duplicate detection for tool names, tool argument mappings, `(tool_name, arguments)` pairs, consecutive calls, and repeated tool result outputs.
- Support budget and completion predicates that combine existing stop, iteration, token, and tool-call counts.
- Support failure-thrash predicates using existing `ToolCallState` values.
- Keep all predicates read-only and side-effect free.
- Preserve existing `agent.behavior.tool`, `agent.behavior.tool_args`, `agent.behavior.stop`, and `agent.behavior.handoff` behavior.
- Add unit coverage and script verification for every new predicate.
- Update SDK and usage skill docs so future agents know where the category belongs and how to extend it.

### Non-Goals

- No changes to `AgentRuntime`, tool execution, middleware behavior, loop stopping logic, provider adapters, or tracing.
- No semantic or fuzzy duplicate detection, such as "similar search query" or "subsumed query"; v1 only checks exact deterministic values.
- No latency or wall-clock efficiency metrics, because current `RunProbe` does not expose duration or per-tool timestamps.
- No per-iteration model-call predicates, because the runtime does not expose per-iteration grouping in `reply.metadata`.
- No persistence, eval registry schema changes, or hosted scoring.
- No breaking changes to `RunProbe` construction or existing behavior category APIs.

---

## 3. Background & Context

The existing behavior facade is implemented under `vidbyte/evals/behavior/` with one category file per group: `tool.py`, `tool_arguments.py`, `stop.py`, and `handoff.py`. `BaseAgent.behavior` lazily creates a `Behavior` facade, and `Behavior.probe` lazily builds a frozen `RunProbe` from `agent.last_reply.metadata`.

The direct agent runtime already stores the relevant loop summary in `reply.metadata` through `AgentRuntime._runtime_metadata`: `stop_reason`, `iteration_count`, `tokens_used`, `tool_call_count`, `tool_call_states`, and `tool_calls`. Each `ToolCallContext` exposes `tool_name`, `arguments`, `state`, and `result`. That is enough for exact loop-efficiency checks without touching runtime logic.

The user asked to add all functions that do not require agent runtime changes, and allowed `RunProbe` changes if useful. This design does not require new runtime metadata. A future follow-up may add optional `RunProbe` convenience fields, but the v1 efficiency category can be implemented using the current probe contract.

---

## 4. Requirements

### Functional Requirements

1. `Behavior` must expose a new `.efficiency` property returning an `EfficiencyBehavior` instance.
2. `EfficiencyBehavior` must live in `vidbyte/evals/behavior/efficiency.py` and read `self._behavior.probe`.
3. `EfficiencyBehavior` must not mutate the agent, probe, tool call contexts, reply metadata, or any result objects.
4. `EfficiencyBehavior.max_tool_repetitions(name, max_count)` must return whether calls to `name` are `<= max_count`.
5. `EfficiencyBehavior.max_any_tool_repetitions(max_count)` must return whether every individual tool name appears `<= max_count` times.
6. `EfficiencyBehavior.completed_within_iterations(max_iterations)` must return whether `probe.iteration_count <= max_iterations`.
7. `EfficiencyBehavior.completed_within_tool_calls(max_calls)` must return whether `probe.tool_call_count <= max_calls`.
8. `EfficiencyBehavior.tool_calls_between(minimum, maximum)` must return whether `minimum <= probe.tool_call_count <= maximum`.
9. `EfficiencyBehavior.no_duplicate_tool_args(name)` must return whether no two calls to `name` have exactly equal argument mappings.
10. `EfficiencyBehavior.no_duplicate_tool_calls()` must return whether no `(tool_name, arguments)` pair repeats.
11. `EfficiencyBehavior.duplicate_tool_arg_count(name)` must count repeated argument mappings for calls to `name`, counting each duplicate occurrence after the first.
12. `EfficiencyBehavior.duplicate_tool_call_count()` must count repeated `(tool_name, arguments)` occurrences after the first.
13. `EfficiencyBehavior.unique_tool_call_count()` must return the number of unique `(tool_name, arguments)` pairs.
14. `EfficiencyBehavior.unique_tool_ratio_at_least(min_ratio)` must return whether `unique_tool_call_count / tool_call_count >= min_ratio`, with zero tool calls treated as ratio `1.0`.
15. `EfficiencyBehavior.no_consecutive_identical_calls()` must return whether adjacent calls never repeat the same tool name and exact arguments.
16. `EfficiencyBehavior.no_consecutive_same_tool()` must return whether adjacent calls never use the same tool name.
17. `EfficiencyBehavior.consecutive_identical_call_count()` must count adjacent repeated `(tool_name, arguments)` pairs.
18. `EfficiencyBehavior.consecutive_same_tool_count()` must count adjacent repeated tool names regardless of arguments.
19. `EfficiencyBehavior.max_consecutive_tool_calls(name, max_count)` must return whether the longest adjacent run of calls to `name` is `<= max_count`.
20. `EfficiencyBehavior.max_any_consecutive_tool_repetitions(max_count)` must return whether every adjacent same-tool run is `<= max_count`.
21. `EfficiencyBehavior.repeated_tool_names()` must return ordered unique tool names that appear more than once.
22. `EfficiencyBehavior.no_repeated_tool_results(name=None)` must return whether no non-`None` result output repeats, optionally scoped to a tool name.
23. `EfficiencyBehavior.repeated_tool_result_count(name=None)` must count repeated non-`None` result outputs after the first, optionally scoped to a tool name.
24. `EfficiencyBehavior.max_result_repetitions(max_count, name=None)` must return whether every non-`None` result output appears `<= max_count`, optionally scoped to a tool name.
25. `EfficiencyBehavior.failed_tool_calls_at_most(max_count)` must return whether calls with state `FAILED` are `<= max_count`.
26. `EfficiencyBehavior.denied_tool_calls_at_most(max_count)` must return whether calls with state `DENIED` are `<= max_count`.
27. `EfficiencyBehavior.unsuccessful_tool_calls_at_most(max_count)` must return whether calls with state `FAILED` or `DENIED` are `<= max_count`.
28. `EfficiencyBehavior.successful_tool_call_ratio_at_least(min_ratio)` must return whether succeeded calls divided by total tool calls is at least `min_ratio`, with zero tool calls treated as ratio `1.0`.
29. `EfficiencyBehavior.no_failed_tool_retries(name=None)` must return whether no failed or denied `(tool_name, arguments)` pair is repeated later, optionally scoped to a tool name.
30. `EfficiencyBehavior.failed_tool_retry_count(name=None)` must count repeated failed or denied `(tool_name, arguments)` attempts after the first, optionally scoped to a tool name.
31. `EfficiencyBehavior.did_not_stop_on_budget()` must return whether `stop_reason` is not `max_iterations`, `max_tool_calls`, or `max_tokens`.
32. `EfficiencyBehavior.stopped_normally_within_iterations(max_iterations)` must require normal final-response stop and `iteration_count <= max_iterations`.
33. `EfficiencyBehavior.stopped_normally_within_tool_calls(max_calls)` must require normal final-response stop and `tool_call_count <= max_calls`.
34. `EfficiencyBehavior.tokens_per_tool_call()` must return `tokens_used / tool_call_count` as `float`, or `None` when tokens are unknown or there were zero tool calls.
35. `EfficiencyBehavior.tokens_per_tool_call_at_most(max_tokens)` must return `True` when tokens per tool call is unknown, otherwise compare `<= max_tokens`.
36. `EfficiencyBehavior.tokens_per_iteration()` must return `tokens_used / iteration_count` as `float`, or `None` when tokens are unknown or there were zero iterations.
37. `EfficiencyBehavior.tokens_per_iteration_at_most(max_tokens)` must return `True` when tokens per iteration is unknown, otherwise compare `<= max_tokens`.
38. The behavior package `__init__.py` must export `EfficiencyBehavior`.
39. Existing behavior tests and verification script helpers must initialize the new category when constructing `Behavior` from a prebuilt `RunProbe`.
40. Skill docs must include the new function catalog and extension rules.

### Non-Functional Requirements

- **Backward compatible:** all additions are additive. Existing behavior properties and exports remain valid.
- **No runtime impact:** no changes to agent execution, tool execution, middleware, providers, or loop budgets.
- **Deterministic:** no LLM judging, no semantic similarity, no remote calls, no nondeterministic ordering.
- **Performance:** all predicates are O(n) or O(n squared) over tool calls, where n is bounded by agent loop budgets. Equality scans will avoid requiring tool argument mappings to be hashable.
- **Security:** predicates only inspect in-memory data already exposed through behavior probes; no new I/O or secret handling.
- **Reliability:** unknown token usage returns `None` for raw ratios and vacuously passes `*_at_most` checks, matching existing `did_not_exceed_tokens` behavior where unknown usage is not treated as failure.

---

## 5. High-Level Design

The feature follows the existing category pattern. A new `EfficiencyBehavior` class is created under `vidbyte/evals/behavior/efficiency.py`. `Behavior.__init__` constructs `self._efficiency = EfficiencyBehavior(self)`, and a new `Behavior.efficiency` property returns it. The category methods inspect the same `RunProbe` that existing categories use.

Data flow remains unchanged:

```text
AgentRuntime -> reply.metadata["tool_calls", "tool_call_count", "iteration_count", ...]
BaseAgent.last_reply -> RunProbe.from_agent(agent)
Behavior.probe -> EfficiencyBehavior predicates
User/Eval -> agent.behavior.efficiency.no_duplicate_tool_calls()
```

The design intentionally keeps efficiency as a separate category rather than adding these methods to `ToolBehavior`. Tool behavior answers "what tools were called and what happened"; efficiency answers "did the run avoid waste, loops, and redundant work." The separation preserves category cohesion and matches the requested `agent.behavior.efficiency.*` public API.

The implementation will use small internal helper methods inside `EfficiencyBehavior` for repeated mechanics: filtered calls, exact argument equality, exact call equality, duplicate counting, longest consecutive runs, result-output extraction, and numeric threshold checks. Helpers stay private and deterministic.

---

## 6. Detailed Design

### 6.1 EfficiencyBehavior

**File(s):** `vidbyte/evals/behavior/efficiency.py`
**Type:** New file

#### What it does

Provides read-only predicates and small metrics for loop efficiency, redundant tool calls, duplicate arguments/results, budget stops, failed retry thrash, and token density.

#### Interface / API

```python
class EfficiencyBehavior:
    def __init__(self, behavior: Behavior) -> None: ...
    def max_tool_repetitions(self, name: str, max_count: int) -> bool: ...
    def max_any_tool_repetitions(self, max_count: int) -> bool: ...
    def completed_within_iterations(self, max_iterations: int) -> bool: ...
    def completed_within_tool_calls(self, max_calls: int) -> bool: ...
    def tool_calls_between(self, minimum: int, maximum: int) -> bool: ...
    def no_duplicate_tool_args(self, name: str) -> bool: ...
    def no_duplicate_tool_calls(self) -> bool: ...
    def duplicate_tool_arg_count(self, name: str) -> int: ...
    def duplicate_tool_call_count(self) -> int: ...
    def unique_tool_call_count(self) -> int: ...
    def unique_tool_ratio_at_least(self, min_ratio: float) -> bool: ...
    def no_consecutive_identical_calls(self) -> bool: ...
    def no_consecutive_same_tool(self) -> bool: ...
    def consecutive_identical_call_count(self) -> int: ...
    def consecutive_same_tool_count(self) -> int: ...
    def max_consecutive_tool_calls(self, name: str, max_count: int) -> bool: ...
    def max_any_consecutive_tool_repetitions(self, max_count: int) -> bool: ...
    def repeated_tool_names(self) -> tuple[str, ...]: ...
    def no_repeated_tool_results(self, name: str | None = None) -> bool: ...
    def repeated_tool_result_count(self, name: str | None = None) -> int: ...
    def max_result_repetitions(self, max_count: int, name: str | None = None) -> bool: ...
    def failed_tool_calls_at_most(self, max_count: int) -> bool: ...
    def denied_tool_calls_at_most(self, max_count: int) -> bool: ...
    def unsuccessful_tool_calls_at_most(self, max_count: int) -> bool: ...
    def successful_tool_call_ratio_at_least(self, min_ratio: float) -> bool: ...
    def no_failed_tool_retries(self, name: str | None = None) -> bool: ...
    def failed_tool_retry_count(self, name: str | None = None) -> int: ...
    def did_not_stop_on_budget(self) -> bool: ...
    def stopped_normally_within_iterations(self, max_iterations: int) -> bool: ...
    def stopped_normally_within_tool_calls(self, max_calls: int) -> bool: ...
    def tokens_per_tool_call(self) -> float | None: ...
    def tokens_per_tool_call_at_most(self, max_tokens: float) -> bool: ...
    def tokens_per_iteration(self) -> float | None: ...
    def tokens_per_iteration_at_most(self, max_tokens: float) -> bool: ...
```

#### Logic / Algorithm

1. `_calls` returns `self._behavior.probe.tool_calls`.
2. Count predicates iterate over `_calls` and compare `tool_name` or `state`.
3. Duplicate call detection uses pairwise equality rather than hashes:
   - arguments are equal when `dict(left.arguments) == dict(right.arguments)`.
   - calls are equal when `tool_name` and argument dicts match.
   - each duplicate occurrence after the first increments the count.
4. Consecutive detection zips adjacent calls and compares tool names and/or arguments.
5. Longest-run detection walks calls once, tracking the current same-tool run and the maximum run.
6. Repeated result detection skips calls with `result is None`; it compares exact `result.output` strings.
7. Failure-thrash detection considers `ToolCallState.FAILED` and `ToolCallState.DENIED` as unsuccessful retry states.
8. Budget-stop detection compares `probe.stop_reason` to `AgentStopReason.MAX_ITERATIONS.value`, `MAX_TOOL_CALLS.value`, and `MAX_TOKENS.value`.
9. Normal-completion combined predicates compare `probe.stop_reason` to `AgentStopReason.FINAL_RESPONSE.value` and also check the requested count limit.
10. Token-density metrics return `None` when `tokens_used is None`, `tool_call_count == 0`, or `iteration_count == 0`.

#### Edge Cases & Error Handling

- Empty tool calls pass duplicate and consecutive checks.
- Zero tool calls produce a unique-tool-call ratio of `1.0`.
- Missing token usage returns `None` for raw token-density metrics and `True` for threshold checks.
- Calls with `result is None` are ignored for repeated-result checks.
- Nested unhashable argument values are supported because equality comparison does not hash mappings.
- Invalid numeric thresholds are not specially validated in v1; the comparison result follows normal Python numeric comparisons, consistent with existing behavior predicates such as `did_not_exceed_tokens`.

---

### 6.2 Behavior Facade Wiring

**File(s):** `vidbyte/evals/behavior/behavior.py`
**Type:** Modified

#### What it does

Composes the new efficiency category into the existing `Behavior` facade.

#### Interface / API

```python
class Behavior:
    @property
    def efficiency(self) -> EfficiencyBehavior: ...
```

#### Logic / Algorithm

1. Import `EfficiencyBehavior`.
2. Initialize `self._efficiency = EfficiencyBehavior(self)` in `__init__`.
3. Return `self._efficiency` from the `efficiency` property.
4. Leave `probe`, `tool`, `tool_args`, `stop`, and `handoff` unchanged.

#### Edge Cases & Error Handling

- Accessing `agent.behavior.efficiency` before any run uses the default empty `RunProbe`, matching other categories.
- Repeated access returns the same `EfficiencyBehavior` instance for the cached `Behavior`.

---

### 6.3 Behavior Package Exports

**File(s):** `vidbyte/evals/behavior/__init__.py`
**Type:** Modified

#### What it does

Exports `EfficiencyBehavior` from the behavior package namespace.

#### Interface / API

```python
from vidbyte.evals.behavior.efficiency import EfficiencyBehavior

__all__ = [
    "Behavior",
    "EfficiencyBehavior",
    ...
]
```

#### Logic / Algorithm

1. Import `EfficiencyBehavior`.
2. Add it to `__all__`.
3. Do not add root-level `vidbyte.EfficiencyBehavior` unless later requested; existing category classes are exported from `vidbyte.evals.behavior`, not root.

#### Edge Cases & Error Handling

- Import order must avoid circular imports. The category only imports `Behavior` under `TYPE_CHECKING`, matching existing category files.

---

### 6.4 Tests

**File(s):** `tests/test_agent_behavior.py`
**Type:** Modified

#### What it does

Adds unit tests for every new efficiency predicate and updates the test helper that creates a `Behavior` from a prebuilt `RunProbe`.

#### Interface / API

```python
def behavior_from_probe(probe: RunProbe) -> Behavior: ...
```

#### Logic / Algorithm

1. Import `EfficiencyBehavior`.
2. Update `behavior_from_probe` to set `b._efficiency`.
3. Add tests grouped under `# --- EfficiencyBehavior ---`.
4. Use existing `make_call` helper for states, arguments, and result outputs.
5. Add a small helper only if needed for constructing failed or denied calls.

#### Edge Cases & Error Handling

- Tests must cover empty runs, one-call runs, duplicate mappings, nested unhashable arguments, repeated outputs, failed/denied states, normal stop reasons, and token-unknown cases.

---

### 6.5 Verification Script

**File(s):** `scripts/test-agent-behavior.py`
**Type:** Modified

#### What it does

Runs every new Section 10 test case and prints PASS/FAIL with a final summary.

#### Interface / API

```python
def main() -> int: ...
```

#### Logic / Algorithm

1. Mirror the unit test helper changes.
2. Add one script test function for each efficiency test in Section 10.
3. Register each test with `TestRunner.run(...)`.
4. Exit non-zero if any test fails, preserving existing script behavior.

#### Edge Cases & Error Handling

- The script must cover all efficiency tests from this design doc, not only the unit-test happy path.

---

### 6.6 Skill and Usage Docs

**File(s):** `skills/vidbyte-sdk/agent-behavior.md`, `skills/usage/agent-behavior.md`
**Type:** Modified

#### What it does

Documents the new category, function catalog, examples, invariants, and verification command.

#### Interface / API

```python
agent.behavior.efficiency.max_tool_repetitions("search", 2)
agent.behavior.efficiency.no_duplicate_tool_calls()
agent.behavior.efficiency.did_not_stop_on_budget()
```

#### Logic / Algorithm

1. Update architecture references from four category classes to five.
2. Add an `agent.behavior.efficiency` section to the function catalog.
3. Add user-facing examples for loop and duplicate checks.
4. Preserve existing extension instructions: one category file per group and `Behavior` facade composition.

#### Edge Cases & Error Handling

- Docs must explicitly state v1 uses exact deterministic matching, not semantic similarity.

---

### 6.7 Existing Agent Behavior Design Doc

**File(s):** `docs/design/agent-behavior.md`
**Type:** Modified

#### What it does

Adds a small historical addendum noting that the original behavior facade now has a fifth category, with this design doc as the source for efficiency-specific behavior.

#### Interface / API

N/A - documentation addendum only.

#### Logic / Algorithm

1. Avoid rewriting the original design.
2. Add a short note linking the new category and design doc.

#### Edge Cases & Error Handling

- Keep the original design doc readable as history while preventing stale "four categories only" language from misleading future agents.

---

## 7. Data Model Changes

N/A - no database, persistence, registry schema, or runtime metadata changes. `RunProbe` already exposes the data required for v1 efficiency predicates.

---

## 8. API Changes

No HTTP endpoints.

### 8.1 `agent.behavior.efficiency`

**Change type:** New

**Request:**

```json
{
  "agent_state": "completed agent run with last_reply metadata"
}
```

**Response:**

```json
{
  "efficiency": "EfficiencyBehavior category object with boolean and metric methods"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Python SDK property, no HTTP status |

### 8.2 `vidbyte.evals.behavior.EfficiencyBehavior`

**Change type:** New

**Request:**

```json
{
  "behavior": "Behavior facade"
}
```

**Response:**

```json
{
  "predicates": "methods described in Section 6.1"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Python SDK class, no HTTP status |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-behavior-efficiency.md` | Design source of truth for the feature |
| CREATE | `vidbyte/evals/behavior/efficiency.py` | New `EfficiencyBehavior` category implementation |
| MODIFY | `vidbyte/evals/behavior/behavior.py` | Compose and expose `.efficiency` |
| MODIFY | `vidbyte/evals/behavior/__init__.py` | Export `EfficiencyBehavior` |
| MODIFY | `tests/test_agent_behavior.py` | Unit coverage for all efficiency predicates |
| MODIFY | `scripts/test-agent-behavior.py` | Verification script coverage for all efficiency predicates |
| MODIFY | `skills/vidbyte-sdk/agent-behavior.md` | SDK extension docs and function catalog |
| MODIFY | `skills/usage/agent-behavior.md` | User-facing examples and function catalog |
| MODIFY | `docs/design/agent-behavior.md` | Add historical addendum pointing to the fifth behavior category |

---

## 10. Testing Plan

### Unit Tests

All unit tests will be added to `tests/test_agent_behavior.py`.

- `EfficiencyBehavior` -> `test_efficiency_max_tool_repetitions` verifies a named tool count at, below, and above the limit. [Edge Case]
- `EfficiencyBehavior` -> `test_efficiency_max_any_tool_repetitions` verifies the highest repeated tool name controls the result. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_completed_within_iterations` verifies exact boundary equality passes and one-over fails. [Edge Case]
- `EfficiencyBehavior` -> `test_efficiency_completed_within_tool_calls` verifies exact boundary equality passes and one-over fails. [Edge Case]
- `EfficiencyBehavior` -> `test_efficiency_tool_calls_between` verifies inclusive lower and upper bounds plus outside-range failures. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_no_duplicate_tool_args` verifies duplicate args for the same tool fail while same args on a different tool do not matter. [Hidden Assumption]
- `EfficiencyBehavior` -> `test_efficiency_no_duplicate_tool_calls` verifies repeated `(tool_name, arguments)` pairs fail while same tool with different args passes. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_duplicate_tool_arg_count` verifies only duplicate occurrences after the first are counted. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_duplicate_tool_call_count` verifies duplicate `(tool_name, arguments)` occurrences are counted after the first. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_unique_tool_call_count` verifies repeated exact calls do not inflate unique count. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_unique_tool_ratio_at_least_empty` verifies zero tool calls produce a passing ratio of `1.0`. [Edge Case]
- `EfficiencyBehavior` -> `test_efficiency_unique_tool_ratio_at_least_mixed` verifies the exact ratio boundary and below-boundary failure. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_no_consecutive_identical_calls` verifies adjacent repeated exact calls fail and non-adjacent duplicates do not affect this predicate. [Hidden Assumption]
- `EfficiencyBehavior` -> `test_efficiency_no_consecutive_same_tool` verifies adjacent same-tool calls fail even with different args. [Hidden Assumption]
- `EfficiencyBehavior` -> `test_efficiency_consecutive_identical_call_count` verifies adjacent duplicate exact-call count and ignores non-adjacent duplicates. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_consecutive_same_tool_count` verifies adjacent same-tool count regardless of args. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_max_consecutive_tool_calls` verifies longest run for one named tool controls the result. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_max_any_consecutive_tool_repetitions` verifies longest run across all tool names controls the result. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_repeated_tool_names_ordered` verifies repeated tool names are ordered by first occurrence. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_no_repeated_tool_results_global_and_scoped` verifies repeated result outputs globally and scoped by tool name. [Hidden Assumption]
- `EfficiencyBehavior` -> `test_efficiency_repeated_tool_result_count` verifies repeated output occurrences after the first are counted and `None` results are skipped. [Hidden Failure]
- `EfficiencyBehavior` -> `test_efficiency_max_result_repetitions` verifies output frequency threshold behavior. [Edge Case]
- `EfficiencyBehavior` -> `test_efficiency_failed_tool_calls_at_most` verifies failed call threshold behavior. [Edge Case]
- `EfficiencyBehavior` -> `test_efficiency_denied_tool_calls_at_most` verifies denied call threshold behavior. [Edge Case]
- `EfficiencyBehavior` -> `test_efficiency_unsuccessful_tool_calls_at_most` verifies failed plus denied calls are both counted. [Hidden Assumption]
- `EfficiencyBehavior` -> `test_efficiency_successful_tool_call_ratio_at_least_empty` verifies zero calls produce a ratio of `1.0`. [Edge Case]
- `EfficiencyBehavior` -> `test_efficiency_successful_tool_call_ratio_at_least_mixed` verifies succeeded-only numerator and total-call denominator. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_no_failed_tool_retries` verifies repeated failed or denied exact attempts fail, optionally scoped by tool name. [Hidden Assumption]
- `EfficiencyBehavior` -> `test_efficiency_failed_tool_retry_count` verifies repeated failed or denied attempts after the first are counted. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_did_not_stop_on_budget` verifies max-iteration, max-tool-call, and max-token stop reasons fail while final-response passes. [Hidden Assumption]
- `EfficiencyBehavior` -> `test_efficiency_stopped_normally_within_iterations` verifies both normal stop and iteration bound are required. [Hidden Failure]
- `EfficiencyBehavior` -> `test_efficiency_stopped_normally_within_tool_calls` verifies both normal stop and tool-call bound are required. [Hidden Failure]
- `EfficiencyBehavior` -> `test_efficiency_tokens_per_tool_call` verifies normal division plus `None` for missing tokens and zero calls. [Edge Case]
- `EfficiencyBehavior` -> `test_efficiency_tokens_per_tool_call_at_most` verifies unknown token usage passes and known over-limit fails. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_tokens_per_iteration` verifies normal division plus `None` for missing tokens and zero iterations. [Edge Case]
- `EfficiencyBehavior` -> `test_efficiency_tokens_per_iteration_at_most` verifies unknown token usage passes and known over-limit fails. [Silent Failure]
- `EfficiencyBehavior` -> `test_efficiency_handles_nested_unhashable_args` verifies duplicate detection works with list/dict values inside arguments. [Hidden Failure]
- `Behavior Facade` -> `test_agent_behavior_efficiency_returns_efficiency_behavior` verifies `agent.behavior.efficiency` returns `EfficiencyBehavior`. [Edge Case]
- `Behavior Facade` -> `test_behavior_from_probe_helper_initializes_efficiency` verifies tests using prebuilt probes can access the new category. [Hidden Assumption]

### Integration Tests

- End-to-end with the existing `MockAgent`: run an agent with repeated tool calls and verify `agent.behavior.efficiency.no_duplicate_tool_calls()` reflects the latest run. [Silent Failure]
- `EvalRunner` plus `PredicateGrader`: run a suite where the predicate uses `p.tool_calls` and mirrors an efficiency check, confirming the existing probe bridge still works after the category is added. [Hidden Assumption]
- Cache invalidation: run the mock agent once with duplicate calls, access `agent.behavior.efficiency`, run again with unique calls, and verify the second behavior facade reflects the second run. [Silent Failure]

### Manual / QA Test Cases

1. Given an agent that calls `search` twice with the same query, when `agent.behavior.efficiency.no_duplicate_tool_args("search")` is called, then it returns `False`. [Edge Case]
2. Given an agent that completes in four iterations, when `agent.behavior.efficiency.completed_within_iterations(4)` is called, then it returns `True`. [Edge Case]
3. Given an agent that stops with `max_iterations`, when `agent.behavior.efficiency.did_not_stop_on_budget()` is called, then it returns `False`. [Hidden Assumption]
4. Given an agent with no reported token usage, when `agent.behavior.efficiency.tokens_per_tool_call()` is called, then it returns `None`. [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | `collections`, typing, and basic comparisons | Low |
| `ToolCallContext` | Existing SDK dataclass | Tool name, arguments, state, and result access | Low |
| `ToolCallState` | Existing SDK enum | Failure, denial, and success categorization | Low |
| `AgentStopReason` | Existing SDK enum | Budget and normal-stop comparisons | Low |
| `RunProbe` | Existing SDK dataclass | Source of completed-run observable state | Low |

No external services. No new package dependencies.

---

## 12. Rollout & Deployment

- This is an additive SDK API change and needs no feature flag.
- The implementation will be done in an isolated worktree after approval, per the design-doc workflow.
- The design doc will be committed first on the feature branch.
- Rollout is normal package release or source consumption; no deployment ordering is required.
- Rollback is reverting the feature branch or PR. No migration or state cleanup is needed.

---

## 13. Open Questions

- [ ] Should invalid numeric thresholds such as negative limits or ratios outside `[0.0, 1.0]` raise `ValueError` instead of returning normal comparison results? This design keeps behavior consistent with existing simple predicates, but validation could make eval author mistakes more visible.
- [ ] Should `EfficiencyBehavior` also be exported from `vidbyte.evals` and root `vidbyte`? Existing category classes are package-level exports under `vidbyte.evals.behavior`, so this design keeps the same pattern.
- [ ] Should the older `docs/design/agent-behavior.md` be updated only with an addendum, or should its full function catalog be revised? This design chooses a short addendum to avoid rewriting historical design text.

---

## 14. Alternatives Considered

### Alternative 1: Add efficiency methods to `ToolBehavior`

- What: Put duplicate and loop-thrash methods directly on `agent.behavior.tool`.
- Why rejected: The user requested an efficiency behavior class and examples under `agent.behavior.efficiency.*`. Keeping a separate category also avoids turning `ToolBehavior` into a mixed presence/outcome/efficiency class.

### Alternative 2: Add runtime metadata for model calls and per-iteration grouping

- What: Change `AgentRuntime._runtime_metadata` to include model-call count, per-iteration snapshots, durations, and assistant outputs.
- Why rejected: The user explicitly scoped this to functions that do not require agent runtime changes. These richer metrics should be a later runtime-design PR.

### Alternative 3: Semantic duplicate detection for search queries

- What: Treat similar or subsumed search arguments as duplicates through normalization, embeddings, or LLM judging.
- Why rejected: That would add nondeterminism, dependencies, and ambiguous semantics. Exact argument equality is reliable for eval predicates.

### Alternative 4: Generic `Behavior.loops` category name

- What: Expose methods under `agent.behavior.loop`.
- Why rejected: The requested concept is broader than loops: it includes duplicate arguments, repeated outputs, token density, and budget-stop predicates. `efficiency` is the more accurate public category.

### Alternative 5: Extend `RunProbe` before adding predicates

- What: Add convenience fields such as `tool_call_names`, `unique_tool_calls`, or raw metadata to `RunProbe`.
- Why rejected: The current probe already contains sufficient source data. Adding derived probe fields would duplicate logic and expand the dataclass without enabling additional v1 predicates.
