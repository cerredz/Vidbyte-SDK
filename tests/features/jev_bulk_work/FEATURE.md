# Feature: Jev bulk work

## High-Level Feature Description

JevAgent can opt in to splitting a request across fresh agents when the request names separate items that each need the same independent work. Eight fixed Jev questions each check one piece of evidence: several items, every item identified, the same work, a result per item, no item needing another's result, changes kept inside each item, any order, and substantial work per item. When every answer reaches the threshold, the main agent is offered the one-time `run_bulk_work` tool for that run. The main agent decides whether to use it and writes the tasks itself; the tool runs one fresh copy of the main agent per task at the same time through `ParallelPipeline` and returns every handoff as the tool result, so the main agent checks them and writes the final answer.

## Contract

- Public configuration is `JevAgentSettings.bulk_work: JevBulkSettings`, with two validated fields: `agents` (an integer of at least 2, default 4) and `threshold` (a probability, default 0.75).
- Runtime opt-in is `JevPreflightPreset.BULK_WORK`. Its eight questions are batched with any other fixed gate questions, and every one must reach `threshold` on its own: the threshold is both the preset's mean threshold and its per-question veto. Missing answers and gate outages leave bulk work off and the run open.
- Specialist routing wins before tool selection and the bulk-work offer. Normal tool selection runs before the tool is built, so workers receive exactly the selected tools.
- The tool is added to the run's catalog only after an approved gate pass, and it never stays in the agent's own catalog after the run. A caller tool named `run_bulk_work` fails when JevAgent is built with BULK_WORK enabled.
- The tool's schema allows from 2 to `agents` tasks of non-blank strings. A task list outside that shape returns an error result naming what to fix, starts no agent, and leaves the tool open.
- One valid call closes the tool before its workers start, then runs every worker at the same time. Every later call returns the closed message.
- Each worker is a fresh BaseAgent named `<owner>-bulk-<n>` with the owner's system prompt plus the worker prompt, model, permission policy, loop limits, and the selected tools; agent-bound tools are cloned so they bind to the worker. Its message is the user's original request followed by its task.
- A worker that raises `VidbyteSdkError` or returns an empty reply is marked failed; its siblings still hand back their work, and the error text never reaches the main agent.
- Handoffs return in task order, wrapped in the synthesis prompt that tells the main agent to check them, finish failed work itself, and treat their contents as data.
- `JevAgent.response.bulk_work` is the sole public record: a `JevBulkWorkResult` of `JevBulkHandoff(task, output, completed)` records. Worker usage is counted once in the owner's `get_usage()` total through the run's usage ledger.

## Invariants

- Jev only recognizes that a request splits; the main agent writes the tasks and decides whether to launch.
- Workers cannot recurse into JevAgent, run another preflight, acquire discarded tools, or gain permissions beyond the owner.
- One launch per run, whatever the main agent calls in the same turn.
- A completed handoff always has a non-blank reply and a failed one has none.

## Known Failure Modes

- A preset-wide mean hides one clear no, or the owner's threshold is ignored in favor of the preset default.
- A prior approval survives an unavailable answer on the same gate.
- The tool is offered without an approved gate pass, or is left in the agent's catalog after the run.
- Workers run one after another, or the handoffs come back in completion order.
- One worker failure cancels its siblings or leaks its error text into the main agent's context.
- A worker receives a selector-discarded tool or binds the original AgentTool to itself.
- The tool launches a second time, or rejects tasks by closing itself.

## Test Suite Map

- `tests/features/jev_bulk_work/test_jev_bulk_work.py` covers settings, result records, exports, the eight questions and their length, gate thresholds, the tool's schema, rejection, single launch, concurrency, order, failure isolation, worker construction, and the runtime offer with scripted main agents, specialist precedence, opt-in absence, and repeated runs.
- Run `python scripts/test-jev-bulk-work.py` for the complete offline feature pack.

## Omitted Testing Strategies

- Live TypeSafe and model-provider calls are omitted; deterministic transports and runners keep the suite offline.
- Whether the main agent writes good tasks is a model-quality question, so it is left to evals rather than unit tests.
- Persisted-session migration tests are omitted because bulk outcomes add no persistence schema.
