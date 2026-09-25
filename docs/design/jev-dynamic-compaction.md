# Jev dynamic compaction

## What and why

Every existing compaction strategy picks *when* to compact by size (a token budget or a message count) and *what* to compact by recency (the oldest N messages). Recency is a weak stand-in for relevance. The best time to fold context away is when a piece of work has finished, because the raw steps of finished work are the part of the history the agent is least likely to need again.

This change adds dynamic compaction to `JevAgent` as a named capability. Jev watches each step of the run and recognizes when the agent has moved on to a new unit of work. Code tracks those units, and once enough finished work has piled up to be worth one cache miss, it replaces each finished unit's messages with a short written record.

There are several ways to find a point where context can be folded: a finished unit of work, a topic change in a long chat, a phase change, a user milestone. Each is a separate *trigger* that the user can enable. This PR ships the first trigger, `unit_of_work`. The trigger contract is shaped so that later triggers plug in without changing the ledger, the compaction policy, or the record writer.

Run state (#448, #450, #452) is out of scope. Units are found from the steps themselves, not from a plan built at run start.

## Public surface

```python
JevAgentSettings(
    ...,
    dynamic_compaction=JevDynamicCompactionSettings(unit_of_work=True),
)
```

- `JevDynamicCompactionSettings` is frozen and validated. It has one boolean flag per trigger (only `unit_of_work` for now) and one bound: `min_reclaim_tokens` (default 8,000), the smallest estimated saving that justifies rewriting the history.
- `JevAgentSettings.dynamic_compaction` defaults to `None`. `None`, or settings with every flag off, leaves the ordinary loop unchanged.
- `JevDynamicCompaction` is the class `JevAgent` uses. It is a tool-free `BaseAgent` subclass, following `JevAgentAlignment` (#445). It holds the settings, asks Jev, applies the compaction policy, and writes unit records using the main agent's model. `JevAgent` builds one instance when the capability is enabled and passes it to each run's `JevRuntime`.

## How it works

1. **Runtime seam.** `AgentRuntime.prepare_iteration_history(state, messages)` is a new no-op hook. The loop calls it at the top of every pass, before the model call. A `before_model_call` middleware cannot do this job, because its `provider_messages` transform only changes the options of one call: the canonical `messages` list keeps every message, so a middleware summary would be rebuilt on every call and would never shrink the history. The seam rewrites the canonical list once. `JevRuntime` overrides it.
2. **Ledger** (`JevUnitLedger`, one per run). On each pass it records how many messages the last iteration added, so every iteration maps to one contiguous run of messages. Each run holds one assistant tool-call message and all of its tool results, so removing whole iterations never splits a call from its result. The ledger groups iterations into units: the open unit, closed units, and compacted units. If the list changes in a way the ledger did not cause, for example a model fallback that rebuilds the history, the ledger disables compaction for the rest of the run.
3. **Boundary question.** When the open unit already has at least one step before the latest one, every enabled trigger adds its state fields and questions to **one** batched Jev request. For `unit_of_work` the state is `{open_unit, latest_step}`. Each step is rendered as the agent's text plus tool names, arguments, and status. Tool outputs are left out because they are large and say little about the agent's goal.

   The question is a `choice` with the options `continues`, `starts_new`, and `unclear`. It follows the asking-jev-questions skill: a unit is defined in the text, the boundary between continuing and starting is spelled out with examples, and Jev judges only what the steps say. It asks what the latest step *does*, not whether the old unit is "done" (that would be a forecast). If P(`starts_new`) ≥ 0.8, code closes the open unit just before the latest step and opens a new unit at it. The 0.8 threshold is untuned.
4. **Compaction policy (code).** Closed units that are not yet compacted become eligible, except the most recent one. The next unit often builds directly on the one before it, so that one stays raw. The policy estimates the tokens eligible units hold, at about four characters per token. When that estimate reaches `min_reclaim_tokens`, it compacts every eligible unit in one rewrite, so one cache miss pays for all of them. The system prompt, earlier history passed in as messages, the open unit, and the latest closed unit are never compacted.
5. **Unit record.** For each unit, `JevDynamicCompaction` runs itself as a tool-free writer. It gets the task and that unit's steps, with outputs clipped per call, and writes a record with fixed sections: Goal, Done, Found, Changed, Open. A fixed header then wraps the record in one `user` message. The header says which steps were removed and that tools can be re-run for exact outputs. If the writer fails or returns nothing, a deterministic record is used instead: each step's text and tool calls without outputs. Both the writer prompt and the header are prompt assets (`jev_compaction` family).
6. **Report.** `result.metadata["jev_dynamic_compaction"]` holds a frozen `JevCompactionReport`. It lists the enabled triggers, each detected boundary (iteration, trigger, and probability), and each compaction (unit, steps, messages removed, estimated tokens removed, and whether the record came from the writer or the fallback). It also records the number of Jev calls, Jev usage, failures, and why compaction was disabled, if it was. The writer shares the main agent's usage tracker, so its model calls show up in `JevAgent.get_usage()` and in cost.

## Failure behavior

| Situation | Behavior |
|---|---|
| Capability off | Unchanged loop; the seam returns at once |
| No TypeSafe key | Disabled for the run, reason `jev_unavailable` |
| Jev request error | No boundary for that step; stop asking after 3 consecutive errors |
| Writer error or empty record | Deterministic fallback record |
| History changed outside the ledger (fallback, other rewriter) | Disabled for the rest of the run, reason recorded |

The seam never raises into the loop for these expected failures.

## Files

- `vidbyte/agents/runtime.py`: the `prepare_iteration_history` seam and its one call site.
- `vidbyte/agents/jev/settings.py`: `JevDynamicCompactionSettings` and the `dynamic_compaction` field.
- `vidbyte/agents/jev/agent.py`, `runtime.py`, `__init__.py`, `README.md`: build, pass, and override the seam, then export.
- `vidbyte/agents/jev/compaction/` (new): `agent.py` (`JevDynamicCompaction`), `ledger.py`, `steps.py` (step rendering), `triggers.py` (`JevCompactionTrigger` ABC plus `JevUnitOfWorkTrigger`), `report.py`, `README.md`, `__init__.py`.
- `vidbyte/lib/enums/jev_compaction.py`, `vidbyte/lib/constants/jev_compaction.py` (new); `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/enums/prompts.py`.
- `vidbyte/prompts/prompts/jev_compaction/` (new family: writer system prompt, record header); `vidbyte/prompts/README.md`.
- `vidbyte/__init__.py`, `vidbyte/agents/__init__.py`: export the settings type.
- `skills/jev-agent/SKILL.md`: a short note on the capability.
- `tests/test_jev_dynamic_compaction.py` (new).

## Risks and open questions

- Asking Jev once per iteration adds one short request of latency to each step. Batching all triggers into one request keeps it at one.
- The 0.8 threshold, the 8,000-token default, and the question wording are untuned. They need a labeled set of boundaries from real traces.
- A unit the agent returns to after it was compacted is only available through the record. A good signal for compacting too early is the agent re-reading something from a compacted unit; that is left for evaluation work.
- #443, #445, #450, and #452 also edit `JevRuntime` and `JevAgentSettings`. Whichever PR lands later needs a small rebase.

## Verification

- Offline tests with a scripted generative runner and a scripted TypeSafe transport:
  - capability off;
  - no boundary;
  - a boundary with too little to reclaim;
  - a compaction that rewrites exactly the finished unit;
  - writer fallback;
  - no Jev key;
  - repeated Jev errors;
  - a fallback-rebuilt history that disables the ledger;
  - settings validation;
  - the batched request shape.
- `python lint/run.py`, `python scripts/run_ci.py --stage source`, and `python scripts/run_ci.py`.
