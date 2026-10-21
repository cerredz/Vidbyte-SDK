# AgentSwarm

## Folder Description / Intent

This folder holds the feature tests for `AgentSwarm`. In a swarm, two to five hundred agents share one goal, one workplace folder, and one sectioned system prompt. They run their file tools and `bash`, message any agent (themselves included) without waiting, compact their own histories, go idle when a turn ends, wake when a message arrives, and stop together when nobody is working or a turn, token or time limit is reached. Every runtime decision and every hook-derived fact is one ordered event of 24 kinds. The tests are offline. The only fakes are the model runner, patched at `BaseAgent._runner_for_model` so it reaches every member agent and every compaction side call, and the Tavily HTTP call. The agent loop, the middleware pipeline, the compaction engine, the prompt catalog, the file tools, `bash`, the filesystem under `tmp_path`, `asyncio`, and the settings validation all run for real. The fixtures order concurrent agents with asyncio events and the swarm's own `on_event` signals, never with timed sleeps. Each wait has a guard that turns a hang into a failure.

The pack covers AC-1 to AC-25 of `docs/spec/agent-swarm-v2/spec.md`, and `docs/spec/agent-swarm-v2/test-plan.md` maps each test to the spec IDs it proves. Every run is checked by one oracle, `assert_event_invariants`, which replays `result.events` as the spec's state machine. The property module also reconciles those events with what each agent's model actually received.

## File Index

- `README.md` describes the scope and how to run the pack.
- `FEATURE.md` defines the contract, the invariants, the known failure modes with the test that catches each, and the strategies left out on purpose.
- `agent_swarm_fixtures.py` provides:
  - the scripted runner routed by agent name, stamped with each member's provider and answering in that provider's own response shape (OpenAI, Anthropic or Gemini);
  - the `on_event` recorder that turns events into Signals;
  - a recording, blocking or raising fake for the Tavily call;
  - a one-shot model retry seam;
  - settings builders;
  - hang guards;
  - transcript and event readers;
  - the event oracle for all 24 kinds.
- `test_agent_swarm_acceptance.py` runs:
  - the spec's section 4 snippet as written;
  - members created, then started, in order, with the web-search tool before `isDone`;
  - first-turn QUIET endings after a reply, an `isDone` or an empty reply;
  - the goal as every call's prompt in one append-only conversation.
- `test_agent_swarm_messaging.py` covers:
  - delivery to a working agent between its tool calls, and to an idle agent by waking it;
  - continuing at once with mail waiting;
  - several messages in one delivery;
  - mutual sends without deadlock, and the send/idle race;
  - messages to oneself;
  - the two refusals and their `message_refused` events;
  - long texts.
- `test_agent_swarm_lifecycle.py` covers:
  - the turn budget and `wake_refused`;
  - the time limit, its `agent_cancelled` labels, and a limit that fires during the start flush or after the end was decided;
  - provider errors, all agents failing, the last worker failing, and mail left for a failed agent;
  - sends to a stopped agent;
  - an unrequested `CancelledError` from a tool or from `on_event`, while working or idle;
  - tool exceptions, and a model-made tool name with a newline;
  - a turn-middleware fault that exits one agent;
  - concurrent and repeated `arun`, and cancellation;
  - a raising, slow or cancelled `on_event`;
  - concurrent flushes, and where the event clock starts;
  - `tool_called` events.
- `test_agent_swarm_stop.py` covers `model_called` token counts, `model_error` before a test-installed retry, the token budget stop, calls and sends in flight at the stop, no `history_trimmed` for a call refused after the stop, and missing usage.
- `test_agent_swarm_observer.py` covers `history_trimmed`, `tool_result_truncated`, `file_changed` and `command_failed`.
- `test_agent_swarm_compaction.py` covers the `compact` tool, automatic compaction at the trigger (OpenAI and Anthropic usage, a Gemini `parts` history, and an OpenAI history of write calls only), the wait for target-sized growth before a repeat automatic compaction, the summary side call, failed and blank summaries, and a side call that reaches the budget.
- `test_agent_swarm_settings.py` covers the lib settings record: one class under every import path, members without prompts, web-search settings, the limits, key secrecy, and the layering rule.
- `test_agent_swarm_workplace.py` covers:
  - creating the workplace and keeping its files across runs;
  - `workplace_prepared` with `created` or `existed`;
  - no folder at construction;
  - a file at the workplace path, and a workplace that cannot be created;
  - file-tool refusals outside the workplace;
  - goal validation.
- `test_agent_swarm_contract.py` covers:
  - exports, record shapes and enum values;
  - the prompt family and its text rules;
  - the runtime refusal outside a swarm;
  - the exact tools, the message schema, and the shared system prompt each agent is offered;
  - settings validation and defaults, and key secrecy;
  - the tool-result cap and the history trim;
  - the event and result record rules;
  - the complexity budget and the entry-point type checks.
- `test_agent_swarm_property.py` runs seeded random swarms: with the default budget, under a tight turn budget, and with one agent failing. It checks the oracle and reconciles events with transcripts on every one.

## Run

From the repository root: `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q`. One file: `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_messaging.py -q`. The `bash` cases in `test_agent_swarm_observer.py` need a POSIX bash, or Git for Windows bash on Windows hosts.

## Logs

- 2026-10-16 - Pack added red, ahead of the implementation, from spec r3 (S2 test author).
- 2026-10-17 - S4 gap tests (mutants M2, M7, M21, M22) and spec r4 regression tests (EC-39, R-2, R-11, R-8) added; the r4 ones stay red until S5.
- 2026-10-20 - Pack rewritten red for agent-swarm-v2 spec r3 (S2 test author): four new modules (settings, stop, observer, compaction), 268 cases.
