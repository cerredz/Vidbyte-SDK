# AgentSwarm

## Folder Description / Intent

This folder holds the feature tests for `AgentSwarm`. In a swarm, two to a hundred developer-defined agents share one goal and one workplace folder. They run their file tools and `bash`, message each other without waiting, go idle when a turn ends, wake when a message arrives, and stop together when nobody is working or a turn or time limit is reached. Every state change is reported as one ordered event. The tests are offline. The only fake is the model runner, patched at `BaseAgent._runner_for_model` so it reaches every member agent the swarm builds inside `arun`. The agent loop, the middleware pipeline, the prompt catalog, the file tools, `bash`, the filesystem under `tmp_path`, `asyncio`, and the settings validation all run for real. The fixtures order concurrent agents with asyncio events and the swarm's own `on_event` signals, never with timed sleeps. Each wait has a guard that turns a hang into a failure.

The pack covers every acceptance criterion from AC-1 to AC-21, and `docs/spec/agent-swarm/test-plan.md` maps each test to the spec IDs it proves. Every run is checked by one oracle, `assert_event_invariants`, which replays `result.events` as the spec's state machine. The property module also reconciles those events with what each agent's model actually received.

## File Index

- `README.md` describes the scope and how to run the pack.
- `FEATURE.md` defines the contract, the invariants, the known failure modes with the test that catches each, and the strategies left out on purpose.
- `agent_swarm_fixtures.py` provides:
  - the scripted runner routed by agent name;
  - the `on_event` recorder that turns events into Signals;
  - plain, blocking and raising search tools;
  - settings builders;
  - hang guards;
  - transcript and event readers;
  - the event oracle.
- `test_agent_swarm_acceptance.py` runs:
  - the spec's section 4 snippet as written;
  - first-turn QUIET endings after a reply, an `isDone` or an empty reply;
  - the goal as every call's prompt in one append-only conversation.
- `test_agent_swarm_messaging.py` covers:
  - delivery to a working agent between its tool calls, and to an idle agent by waking it;
  - continuing at once with mail waiting;
  - several messages in one delivery;
  - mutual sends without deadlock;
  - the send/idle race;
  - refused messages;
  - long texts.
- `test_agent_swarm_lifecycle.py` covers:
  - the turn budget and the time limit;
  - provider errors, all agents failing, and the last worker failing;
  - tool exceptions;
  - the fail-closed turn middleware;
  - concurrent and repeated `arun`;
  - cancellation;
  - a raising, slow or cancelled `on_event`;
  - concurrent flushes;
  - `TOOL_CALLED` events.
- `test_agent_swarm_workplace.py` covers:
  - creating the workplace and keeping its files across runs;
  - no folder at construction;
  - a file at the workplace path, and a workplace that cannot be created;
  - file-tool refusals outside the workplace;
  - goal validation.
- `test_agent_swarm_contract.py` covers:
  - exports, record shapes and enum values;
  - the prompt family and its text rules;
  - the runtime refusal outside a swarm;
  - the exact tools and message schema each agent is offered, and system prompt order;
  - settings validation and defaults, and key secrecy;
  - the event and result record rules;
  - the complexity budget and the entry-point type checks.
- `test_agent_swarm_property.py` runs seeded random swarms: with the default budget, under a tight turn budget, and with one agent failing. It checks the oracle and reconciles events with transcripts on every one.

## Run

From the repository root: `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q`. One file: `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_messaging.py -q`. The one `bash` case needs a POSIX bash, or Git for Windows bash on Windows hosts.

## Logs

- 2026-10-16 - Pack added red, ahead of the implementation, from spec r3 (S2 test author).
