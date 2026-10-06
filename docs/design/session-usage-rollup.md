# Design Doc: `session.usage()` — cost/usage rollups

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

---

## 1. Overview

Add `session.usage()` to the durable `Session` facade: a near-free aggregation that folds the per-turn usage numbers the agent runtime *already records* into a single rollup — `{tokens, cost, latency, tool_calls}` — broken down per agent that participated in the session. It reads existing data (each assistant message's `metadata`, persisted verbatim in every checkpoint) rather than capturing anything new. This is the seam every eval-related workflow hangs off of.

---

## 2. Original User Prompts

The user's own words, verbatim and in order, across the conversation that produced all four session design docs.

**Prompt 1 (via `/talk`):**
```
- i want to add the following features to our session objectin the vidbyte-sdk/ repo:
  - want to add a batch_fork method to the session object, also make this a tool
  - want to add a session.usage object:   - Usage/cost rollups. You store traces per checkpoint but expose no aggregate. session.usage() -> {tokens, cost, latency,
  tool_calls} folded across the head chain. Near-free, and it's the
  seam for everything eval-related. Should be able to track the usage of all agents in the session. 
  - i want to be able to resume/fork by name and not just uuid, maybe like a session.tag() function to do this. 
  -  export() / import() — a portable session bundle (checkpoints +
  traces) to move between stores, attach to a bug report, or ship a
  repro. FileSessionStore already has the on-disk shape; this is
  mostly a zip.
. Can you kind of just scope out the session skill and see how we would implement this, and explain how we would do it?
```

**Prompt 2:**
```
1) the batch_fork should attempt to do the same thing the fork function does, just multiple of. If a few fail its fine, just keep running the others that dont. 2) I simply want the session.usage() function to use the already existing logic in the agent class's and calculate this for all agents in the session 3) go more into depth and explain to me how we would implement this 4) also explain this more. Using these answers, show me some implementation surfaces
```

**Prompt 3:**
```
great, can you create 4 design docs for this feature
```

---

## 3. Structured Conversation Notes

### Key Decisions
- **Reuse the agent's existing usage logic — do not add new capture** (Prompt 2, item 2: "use the already existing logic in the agent class's"). The agent runtime already computes and attaches per-turn usage to every reply's `metadata`.
- **The exact existing seam (verified in code):** `AgentRuntime._runtime_metadata` (`vidbyte/agents/runtime.py:1447`) returns:
  ```python
  {"stop_reason", "iteration_count", "tokens_used", "tool_call_count",
   "tool_call_states", "tool_calls"}
  ```
  `tokens_used` is already summed across every model call in that turn via `_add_token_usage` (`runtime.py:1461`) + `token_usage_from_response` (`vidbyte/lib/token_usage.py`). This metadata flows into the final `AgentMessage` at `vidbyte/agents/base.py:596-608`, is appended to `history`, and is persisted **unscrubbed** in `Checkpoint.run_state.history` (the serializer's `_scrub_metadata` only drops credential-like keys; `tokens_used`/`tool_call_count` survive).
- **"All agents in the session" == group history messages by `sender`** (Prompt 2). Each assistant message carries `sender` = the producing agent's name. Handoff sub-agents append their own messages with their own `tokens_used`, so grouping by `sender` yields a per-agent breakdown for free.
- **Fold over the HEAD checkpoint's history, not a parent-chain walk.** `run_state.history` is *cumulative* — the head checkpoint already contains every turn from every agent in the thread. Summing per-checkpoint totals along the chain would massively double-count. This corrects the user's original "folded across the head chain" phrasing (Prompt 1): the correct, near-free implementation reads head once.
- **Return a structured `UsageRollup`** with a `per_agent` breakdown, not a bare dict, so eval code has typed access. Fields: `tokens`, `tool_calls`, `turns`, `latency`, `cost`, `per_agent: tuple[AgentUsage, ...]`.
- **Cost stays honest.** There is no pricing table in the SDK. `cost` is `None` by default; callers who care pass a `prices` map (`{model_name: price_per_token}`) to `usage(prices=...)`. This avoids shipping a pricing table that rots.

### Rejected Alternatives
- **Walk the parent chain summing each checkpoint's `tokens_used`.** Rejected — double-counts because history is cumulative. (This is the subtle trap; the implementer must read head only.)
- **Add a new per-turn capture path for usage.** Rejected — the user explicitly wants the *existing* agent logic reused; the numbers are already in `metadata`.
- **Bundle a hardcoded provider pricing table for `cost`.** Rejected — stale-data liability; use an optional injected `prices` map instead.
- **Return a plain dict `{tokens, cost, latency, tool_calls}`.** Softly rejected in favor of a typed dataclass with a `per_agent` breakdown (the "all agents" requirement needs structure); the top-level scalar fields are preserved on the dataclass for the shape the user asked for.

### Constraints & Assumptions
- **Latency is NOT currently in the persisted per-turn metadata.** `elapsed_seconds` exists only on `MiddlewareContext` (`runtime.py:900`); it is *not* in `_runtime_metadata`'s dict. Two options (see Open Questions): (a) derive session latency from checkpoint `created_at` timestamp deltas (near-free, already stored), or (b) add `"elapsed_seconds"` to `_runtime_metadata` for precise per-turn latency. Recommended: ship (a) now.
- `tokens_used` may be `None` for a turn (provider didn't report usage); treat as 0 in the sum.
- No `SESSION_SCHEMA_VERSION` bump on the recommended path (pure read-side aggregation). Option (b) for latency would touch runtime metadata but still needs no session schema change.

### Clarifications & Answers
- **Q: How sophisticated should usage be?** A (Prompt 2): "simply … use the already existing logic in the agent class's and calculate this for all agents in the session." → aggregate `tokens_used` + `tool_call_count` from history metadata, grouped by `sender`.

### Terminology / Glossary
- **`tokens_used`:** per-turn total tokens, already summed across model calls by the runtime; lives in each reply's `metadata`.
- **`tool_call_count`:** per-turn count of tool calls; `len(contexts)` in `_runtime_metadata`.
- **Head checkpoint:** the current tip of the session (`store.head(session_id)`); its `run_state.history` is the full cumulative transcript.
- **`per_agent`:** breakdown keyed by message `sender` (agent name) — the "all agents in the session" view.
- **Rollup:** a single aggregate record folded from many turns.

### Implementation Hints for the Downstream Model
- **New file:** `vidbyte/sessions/usage.py` holding `AgentUsage` and `UsageRollup` frozen dataclasses plus small helpers (`_price`, `_sum_or_none`). Keep dataclasses `slots=True`.
- **Method** `usage(self, *, prices: Mapping[str, float] | None = None) -> UsageRollup` goes in `vidbyte/sessions/session.py`. Get head via `self._store.head(self._session_id)`; return an empty rollup when head is `None`.
- **Iterate `head.run_state.history`** (a `list[dict]`, each item shaped by `SessionSerializer.message_to_dict`: keys `sender`, `recipient`, `content`, `message_type`, `metadata`). Skip items whose `metadata` has neither `tokens_used` nor `tool_call_count` (user/tool messages).
- **Per-agent accumulation:** `dict[sender] -> {tokens, tool_calls, turns}`, then materialize into `AgentUsage` tuples; top-level fields are sums over the per-agent entries.
- **Latency (recommended path a):** add a private `_session_latency()` reading `self._store.history(session_id)` and computing `last.created_at - first.created_at` (parse the ISO-8601 strings written by `_now()`), returning seconds as float or `None` when <2 checkpoints.
- **Model name for pricing:** available at `head.run_state.model_name`; per-agent pricing is coarse (one model per session in the common case). If mixed models matter later, thread model name per message — out of scope now.
- **Re-export** `UsageRollup`/`AgentUsage` from `vidbyte/sessions/__init__.py` `__all__` so eval code can import them.
- **Do NOT** modify the serializer's scrub logic — `tokens_used`/`tool_call_count` already survive it. Verify with a quick check that no `_SECRET_TOKENS` substring matches those keys (it doesn't).

### Open Questions
- **Latency source:** ship timestamp-delta (a) now, or also add `elapsed_seconds` to `_runtime_metadata` (b) for per-turn precision in the same PR? Recommended: (a) now, (b) as a fast-follow if evals need per-turn latency.
- Should `usage()` optionally cover a **fork tree** (parent + child sessions sharing a `parent_session_id` root) via a separate `usage_tree()`? Deferred — single-session rollup ships first.
- Should there be a read-only **`UsageTool`** so an agent can introspect its own spend? Not requested; leave out unless asked.

---

## 4. Goals & Non-Goals

### Goals
- Add `Session.usage(*, prices=None) -> UsageRollup` folding existing per-turn metadata from the head checkpoint's cumulative history.
- Aggregate `tokens` and `tool_calls` across all agents, with a `per_agent` breakdown keyed by `sender`.
- Provide `latency` (session wall-clock from checkpoint timestamps) and `cost` (only when a `prices` map is supplied, else `None`).
- Reuse the agent runtime's existing usage numbers with zero new capture code.

### Non-Goals
- Adding a new usage-capture path or changing how the runtime computes `tokens_used`.
- Bundling a provider pricing table.
- Cross-session / fork-tree aggregation (`usage_tree()`).
- Precise per-turn latency (unless the optional runtime-metadata addition is approved).

---

## 5. Background & Context

Sessions persist rich per-checkpoint trace data but expose no aggregate — there's no one-call answer to "how many tokens/tool-calls did this session cost, across every agent that ran in it?" Evals, budgeting, and regression comparisons all need that number. Because the agent runtime already computes per-turn `tokens_used` and `tool_call_count` and those values are already persisted in every checkpoint's history, the aggregate is a pure read-side fold — "near-free," as the user put it. This doc pins down the correct fold (head-only, grouped by `sender`) and the honest handling of `cost` and `latency`, which are the two fields not directly present in the existing metadata.

---

## 6. Requirements

1. `Session.usage(*, prices=None)` returns a `UsageRollup` with `tokens`, `tool_calls`, `turns`, `latency`, `cost`, and `per_agent`.
2. `tokens` = sum of `metadata["tokens_used"]` (treating `None` as 0) over all assistant turns in the head checkpoint's history.
3. `tool_calls` = sum of `metadata["tool_call_count"]` over the same turns.
4. `per_agent` groups the above by message `sender`, one `AgentUsage(agent_name, tokens, tool_calls, turns, cost)` per agent.
5. The fold reads the head checkpoint once; it must NOT walk the parent chain (avoids double-counting cumulative history).
6. `cost` is `None` unless a `prices` map is provided, in which case it is `tokens * price` per agent, summed.
7. `latency` is derived from checkpoint `created_at` deltas (or `None` when fewer than two checkpoints exist).
8. An empty session (no head) returns a zeroed `UsageRollup` with empty `per_agent`, not an error.

---

## 7. Non-Functional Requirements

- **Performance:** O(len(history)) over a single checkpoint read plus one `history()` call for latency; no model calls, no network. Genuinely "near-free."
- **Correctness:** Must not double-count (head-only fold). Must tolerate missing `tokens_used`.
- **Security:** Reads already-scrubbed persisted metadata; introduces no new data capture.
- **Observability:** This *is* the observability seam; the rollup should be stable and typed for downstream eval tooling.
- **Reliability:** Never raises on a normal session; degrades to zeros/`None` for empty or partial data.

---

## 8. High-Level Design

`usage()` reads the session's head checkpoint (`store.head(session_id)`) and folds its `run_state.history`. Because that history is cumulative, the head alone holds every turn from every agent — no chain walk. It iterates the persisted message dicts, skips non-agent messages (those without `tokens_used`/`tool_call_count` in `metadata`), and accumulates `tokens`, `tool_calls`, and `turns` into a per-`sender` map. That map materializes into `AgentUsage` entries (the "all agents" breakdown), and the top-level `UsageRollup` scalar fields are sums across them. `cost` is computed only if the caller passes a `prices` map; otherwise `None`. `latency` is the wall-clock span between the first and last checkpoint's `created_at` timestamps.

The only genuinely new data is `latency` and `cost`, and both are handled without new persistence: latency from timestamps already stored, cost from an injected price map. Everything else is a fold over data the agent runtime already produced (`runtime.py:1447`) and the serializer already persisted.

```
store.head(session_id).run_state.history   (cumulative: all turns, all agents)
        |
        v  fold, grouping by message.sender, skip non-agent msgs
   { "planner":  {tokens, tool_calls, turns},
     "coder":    {tokens, tool_calls, turns},
     "reviewer": {tokens, tool_calls, turns} }        <- per_agent (AgentUsage[])
        |
        v  sum scalars; latency from store.history() timestamps; cost from prices map
   UsageRollup(tokens, tool_calls, turns, latency, cost, per_agent)
```

Components:
- **Created:** `vidbyte/sessions/usage.py` (`AgentUsage`, `UsageRollup`, `_price`, `_sum_or_none`).
- **Modified:** `vidbyte/sessions/session.py` (add `usage()` + `_session_latency()`), `vidbyte/sessions/__init__.py` (`__all__`). Optional (deferred): `vidbyte/agents/runtime.py` `_runtime_metadata` to add `elapsed_seconds` for precise latency.
- **Deleted:** none.

---
