# Design Doc: Sequential Prompt Execution

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-19
**Last Updated:** 2026-06-19

---

## 1. Overview

Adds `run_sequentially()` and `arun_sequentially()` methods to `BaseAgent` that accept a list of prompts and execute them one after another using the agent's existing `run()`/`arun()` flow — while deliberately preserving `self.history` across every call so that each prompt sees the full prior conversation. This enables multi-turn batch workflows without forcing callers to manually loop and manage state.

---

## 2. Goals & Non-Goals

### Goals
- Add `run_sequentially(prompts, **options)` — synchronous entry point matching the `run()` pattern
- Add `arun_sequentially(prompts, **options)` — async entry point matching the `arun()` pattern
- Preserve `self.history` across all prompts in the sequence (no context window reset)
- Accept `Sequence[str | AgentInput]` as input to match what `generate_reply` already accepts
- Return `list[AgentMessage]` — one reply per prompt, in order
- Forward `**options` to each underlying `generate_reply` call unchanged
- Raise immediately if any prompt fails (consistent with `run()`/`arun()` error semantics)

### Non-Goals
- Parallel execution of prompts (that would reset or conflict with shared `self.history`)
- Batching at the provider level
- Streaming replies per-prompt
- Per-prompt option overrides (all options are shared across the sequence)
- Modifying how history is accumulated (existing `generate_reply` already appends to `self.history`)

---

## 3. Background & Context

`BaseAgent` currently exposes `run(message)` and `arun(message)` for single-turn execution. Users who want to feed multiple prompts in sequence must loop manually:

```python
replies = []
for prompt in prompts:
    replies.append(agent.run(prompt))
```

This works but is verbose and, more importantly, unclear — the contract that `self.history` persists between calls is implicit and undiscovered unless you read the source. `run_sequentially` makes the multi-turn batch pattern first-class and self-documenting.

The key insight from reading the code: `generate_reply` already appends each reply to `self.history` (line 492 of `base.py`), and `_build_context` passes `agent_history=self.history` into the runtime on every call. So "no context reset" is already the natural behavior; this feature merely wraps it with a clean API.

---

## 4. Requirements

### Functional Requirements
1. `run_sequentially(prompts, **options)` must accept `Sequence[str | AgentInput]` and return `list[AgentMessage]`
2. `arun_sequentially(prompts, **options)` must accept `Sequence[str | AgentInput]` and return `list[AgentMessage]`
3. Prompts must be executed in list order, one at a time (sequential, not concurrent)
4. `self.history` must not be cleared or reset between prompt executions
5. Each reply must be appended to `self.history` before the next prompt is sent, so later prompts see earlier replies as context
6. If any prompt raises, the method must re-raise immediately without executing remaining prompts
7. Passing an empty list must return an empty list without error
8. `**options` forwarded to each `generate_reply` call must be the same for every prompt in the sequence
9. `run_sequentially()` must raise `AgentExecutionError` if called from an active event loop (matching `run()` behavior)

### Non-Functional Requirements
- No additional dependencies
- No new I/O or network calls beyond what `generate_reply` already does
- Zero overhead when `prompts` has length 1 (reduce to a single `generate_reply` call)

---

## 5. High-Level Design

`run_sequentially` and `arun_sequentially` are thin wrappers over the existing `generate_reply` machinery. The async version iterates the prompt list and `await`s `generate_reply` for each; the sync version mirrors `run()` by using `asyncio.run()` when no event loop is active.

```
caller
  │
  ├─ run_sequentially(prompts)
  │     └─ asyncio.run(arun_sequentially(prompts))
  │
  └─ arun_sequentially(prompts)
        for prompt in prompts:
            reply = await generate_reply(prompt, **options)
            results.append(reply)
        return results
```

Because `generate_reply` already appends each reply to `self.history` (and `_build_context` feeds `self.history` to the runtime as `agent_history`), there is nothing extra to do to preserve context — the existing mechanism does it automatically.

No new state is added to `BaseAgent`. The feature is a pure behavior extension.

---

## 6. Detailed Design

### 6.1 `BaseAgent.arun_sequentially`

**File:** `vidbyte/agents/base.py`
**Type:** Modified (new method added)

#### What it does
Iterates a list of prompts, awaits `generate_reply` for each, and returns all replies in order.

#### Interface / API
```python
async def arun_sequentially(self, prompts: Sequence[str | AgentInput], **options: Any) -> list[AgentMessage]:
```

#### Logic / Algorithm
1. If `prompts` is empty, return `[]` immediately.
2. Initialize `results: list[AgentMessage] = []`.
3. For each `prompt` in `prompts`, await `self.generate_reply(prompt, **options)` and append the reply to `results`. (`generate_reply` already appends the reply to `self.history` before returning, so context is preserved automatically.)
4. Return `results`.

#### Edge Cases & Error Handling
- Empty list → return `[]` immediately (no calls to `generate_reply`)
- Single-element list → exactly one `generate_reply` call (no special path needed)
- `generate_reply` raises on prompt N → exception propagates out; prompts N+1..end are never called; `self.history` reflects all replies up to but not including the failed prompt
- `options` may not include keys that conflict across calls; that is the caller's responsibility (no validation added — consistent with `generate_reply`'s own behavior)

---

### 6.2 `BaseAgent.run_sequentially`

**File:** `vidbyte/agents/base.py`
**Type:** Modified (new method added)

#### What it does
Synchronous entry point for sequential prompt execution. Mirrors `run()` in its event-loop detection guard.

#### Interface / API
```python
def run_sequentially(self, prompts: Sequence[str | AgentInput], **options: Any) -> list[AgentMessage]:
```

#### Logic / Algorithm
1. Call `asyncio.get_running_loop()` inside a `try/except RuntimeError`.
2. If no running loop → call `asyncio.run(self.arun_sequentially(prompts, **options))` and return the result.
3. If a running loop is detected → raise `AgentExecutionError` with a message directing the caller to use `await arun_sequentially()`.

#### Edge Cases & Error Handling
- Called from an active event loop → raises `AgentExecutionError` (identical guard to `run()`)
- All other error cases are handled inside `arun_sequentially` / `generate_reply`

---

## 7. Data Model Changes

N/A — no new fields, tables, or schema changes. `self.history` already exists on `BaseAgent` and is mutated by `generate_reply` as a side effect.

---

## 8. API Changes

N/A — this is a pure SDK Python API addition. No HTTP endpoints are created or modified.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/agents/base.py` | Add `arun_sequentially` and `run_sequentially` methods to `BaseAgent` |
| MODIFY | `tests/test_agent_base.py` | Add test cases for the new methods |
| CREATE | `scripts/test-sequential-prompts.py` | Phase 5 verification script |

---

## 10. Testing Plan

### Unit Tests

All new tests live in `tests/test_agent_base.py` inside `AgentBaseTests`.

- `test_run_sequentially_returns_all_replies` — calls `run_sequentially` with 3 prompts, asserts 3 replies returned in order — [Edge Case]
- `test_run_sequentially_empty_list_returns_empty` — calls `run_sequentially([])`, asserts `[]` returned without calling the runner — [Edge Case]
- `test_run_sequentially_single_prompt_works` — single-element list behaves identically to `run(prompt)` — [Edge Case]
- `test_arun_sequentially_preserves_history` — after `arun_sequentially`, `agent.history` contains both the user prompts and all replies in the correct interleaved order — [Silent Failure]
- `test_arun_sequentially_context_accumulates_across_prompts` — verifies that the runner receives the prior reply in context when the second prompt is sent (checks `agent.history` grows monotonically) — [Hidden Failure]
- `test_run_sequentially_raises_on_active_event_loop` — asserts `AgentExecutionError` when `run_sequentially` is called inside an already-running loop — [Hidden Assumption]
- `test_arun_sequentially_stops_on_first_failure` — first prompt succeeds, second raises; asserts only one reply was produced and the exception propagates — [Hidden Failure]
- `test_arun_sequentially_accepts_agent_input_objects` — passes `AgentInput` objects (not raw strings) and asserts they are forwarded correctly — [Hidden Assumption]
- `test_arun_sequentially_forwards_options_to_each_call` — passes a recognizable kwarg option and confirms it reached every underlying `generate_reply` invocation — [Silent Failure]

### Integration Tests

- Execute `arun_sequentially` end-to-end with a real `TextRunner`; assert `agent.history` has `2 * N` entries (N user messages interleaved with N assistant replies) after N prompts — [Hidden Failure]
- Verify that when `generate_reply` is replaced with a stub that fails on the 2nd call, only 1 reply is in the returned list and `agent.history` has exactly 1 reply — [Silent Failure]

### Manual / QA Test Cases

1. Given a `BaseAgent` with a real runner, when `run_sequentially(["Who are you?", "What did you just say?"])` is called, then the second reply should reference the content of the first reply — demonstrating real context carry-over — [Hidden Failure]
2. Given `run_sequentially` called from an async context via `asyncio.run(outer())` where `outer` calls `run_sequentially` inside a sync function, when executed, then it should complete normally without event-loop nesting errors — [Hidden Assumption]
3. Given an empty list `[]`, when `run_sequentially([])` is called, then `[]` is returned and `agent.history` is unchanged — [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `asyncio` (stdlib) | Python 3.11+ | Event-loop detection, `asyncio.run()` | None — already used in `run()` |

---

## 12. Rollout & Deployment

- No feature flag needed — additive public API, no behavior change to existing methods.
- Not a breaking change — new methods only.
- No deployment order dependency — SDK-only, no services.
- Rollback: revert the two added methods from `base.py` and the new tests.

---

## 13. Open Questions

- [ ] Should `run_sequentially` / `arun_sequentially` also be exported from `vidbyte/agents/__init__.py`'s `__all__`? (Methods on `BaseAgent` are already accessible without an `__all__` entry, so this is a documentation/discoverability choice only.)
- [ ] Should an `on_reply` callback parameter be offered so callers can inspect each reply as it arrives without waiting for the full sequence? (Not in scope for this PR — left as a follow-up.)

---

## 14. Alternatives Considered

### Alternative 1: Add to `AgentClient` instead of `BaseAgent`
- What: put `run_sequentially` on the higher-level `AgentClient` wrapper
- Why rejected: `AgentClient` is a lightweight request-level wrapper; `BaseAgent` owns `self.history` directly, so placing the method there keeps the implementation trivially thin

### Alternative 2: Reset history between prompts by default, with an `keep_history=True` flag
- What: clear `self.history` after each prompt unless opted in
- Why rejected: the user's explicit requirement is "context window should not reset"; making no-reset the opt-in default would be confusing and inconsistent with how `run()` already works (successive `run()` calls naturally accumulate history)

### Alternative 3: Return a generator/iterator instead of `list[AgentMessage]`
- What: yield each reply as it's produced rather than collecting all into a list
- Why rejected: adds complexity and a new API shape; the synchronous `run()` analogue returns a single value, so returning a list for the sequential version is the simplest consistent extension
