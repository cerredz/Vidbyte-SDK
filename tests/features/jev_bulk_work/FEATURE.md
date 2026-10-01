# Feature: Jev bulk work

## High-Level Feature Description

JevAgent can opt in to bounded fan-out for a clearly named set of independent items that all receive the same requested operation. Three separate fixed Jev questions recognize multiple items, shared operation, and independence. A tool-free planner generates a complete structured plan; the coordinator rejects the entire plan if invalid or oversized, then runs fresh BaseAgent workers through a bounded queue. The main agent receives ordered worker records as untrusted context data and produces the final response.

## Contract

- Public configuration is `JevAgentSettings.bulk_work: JevBulkSettings`; its four positive integer limits are validated at construction.
- Runtime opt-in is `JevPreflightPreset.BULK_WORK`. Its three fixed questions are batched with any other fixed gate questions and each must pass; missing answers and gate outages leave fan-out disabled.
- Specialist routing wins before tool selection and bulk planning. Normal tool selection runs before the coordinator reads tools.
- Planner input is the exact original request. The planner has its own prompt, no user tools, no implicit internal agent tools, and bounded planner loops/tokens.
- A plan must contain at least two unique, nonblank items and no more than `max_items`. Invalid, absent, or oversized output is rejected whole; no worker starts and the ordinary loop receives the unchanged request.
- Workers are fresh BaseAgent instances with isolated histories, effective owner prompt, model and permission policy, and exactly the tools left by normal selection. Agent-bound tools are cloned through `clone_for_fork()` before binding.
- A fixed number of worker coroutines consume a bounded queue. Results retain plan order even when completion order differs. An ordinary worker exception becomes a stable typed failure category; siblings finish. Cancellation propagates after sibling cleanup.
- `JevAgent.response.bulk_work` is the sole public result record. Planner and worker rollups stay owned by those agents and are included once in the result record, not flattened into owner usage or result metadata.
- The original request is unchanged for the inherited main loop. Valid bulk results enter a copied context artifact; trusted synthesis instructions tell the main agent to report each failed item honestly. Caller context is not mutated.
- With the preset disabled, no planner or worker call occurs. Bulk code contains no preset checks; `JevPreflightGate` owns the run-local outcome and resets it each pass.

## Invariants

- Jev recognizes eligibility; only the generative planner makes the item list. The coordinator validates the whole plan and never truncates requested work.
- Workers cannot recurse into JevAgent, run another preflight, acquire discarded tools, or gain permissions beyond the owner.
- Worker output and artifacts are untrusted data. They cannot suppress failures or expand task scope.
- A successful worker loop is not evidence that each item succeeded. Failure status remains visible to both the public response and main synthesis context.
- Cancellation is never recorded as item success or failure.

## Known Failure Modes

- One fixed question is missing, malformed, uncertain, or vetoed but the gate accidentally preserves an earlier bulk flag.
- Planner output omits, merges, invents, duplicates, blanks, or exceeds the requested item set; accepting a partial list silently loses work.
- Planner or worker context inherits the owner system prompt or conversation snapshots in place of its own scoped prompt and clean history.
- An unbounded task-per-item implementation ignores `max_parallel_agents`, or results are returned by completion order.
- One worker exception escapes the queue and cancels successful siblings, exposes exception text, or is omitted from synthesis.
- Cancellation strands worker tasks or is swallowed as an ordinary error.
- A worker receives a selector-discarded tool or binds the original AgentTool to itself.
- Runtime selection mutates the owner's tool catalog after the run, or an invalid plan prevents serial fallback.
- Child raw usage is double-recorded in the owner rollup or written to result metadata.
- Worker prompt injection is followed by the main agent, or shared caller context is mutated while artifacts are added.

## Test Suite Map

- `tests/features/jev_bulk_work/test_jev_bulk_work.py` covers configuration, fixed questions, gate outcomes, planner boundaries, actual BaseAgent context building, queue concurrency/order/failures/cancellation, tool isolation, usage, synthesis context, selector/specialist precedence, serial fallback, opt-in behavior, and repeated runs.
- Run `python scripts/test-jev-bulk-work.py` for the complete offline feature pack.

## Omitted Testing Strategies

- Live TypeSafe and model-provider calls are omitted; deterministic transports and runners keep the suite offline.
- Long-running load and throughput benchmarks are omitted; the queue's maximum active workers is asserted directly.
- Persisted-session migration tests are omitted because bulk outcomes add no persistence schema.
