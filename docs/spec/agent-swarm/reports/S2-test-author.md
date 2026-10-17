# S2 test author report: agent-swarm

Spec: `docs/spec/agent-swarm/spec.md` r3. Base commit: 97f7d2f9. My commits:

- `ecfbac79` adds the feature pack and `test-plan.md`.
- `cf403857` fills the §6.2 Proof column.

I wrote no production code. No stub, placeholder or prototype of the swarm exists anywhere. Every probe ran existing repository code from the scratchpad with `PYTHONPATH=<worktree>`.

## Inventory

`tests/features/agent_swarm/` holds 51 test functions, which expand to 161 cases through parametrisation.

| Module | Functions | Cases | Level | Covers |
|---|---|---|---|---|
| `test_agent_swarm_acceptance.py` | 3 | 8 | acceptance | AC-1 (the §4 snippet, byte for byte), AC-4, INV-1–3 |
| `test_agent_swarm_messaging.py` | 8 | 14 | integration, component | AC-2, AC-3, AC-9, AC-20, EC-1, EC-2, EC-4, EC-27 |
| `test_agent_swarm_lifecycle.py` | 15 | 18 | integration, component | AC-5–8, AC-10, AC-15, AC-19, EC-13, EC-15, EC-16 (b, c), EC-19, EC-23, D-6, INV-19 |
| `test_agent_swarm_workplace.py` | 7 | 14 | integration, component | AC-13 (path half), AC-16, AC-18, EC-28, EC-29, EC-31, D-11 |
| `test_agent_swarm_contract.py` | 15 | 71 | contract | AC-11, AC-12, AC-13 (tools), AC-14, AC-17, AC-21, §8.4, §8.5, §9.1–9.3, INV-22, INV-28, NFR-2–5 |
| `test_agent_swarm_property.py` | 3 | 36 | property | INV-1–17 and NFR-1 over 36 seeded random swarms (default budget, tight budget, one failing agent) |

The other files in the pack:

- `FEATURE.md` was written first. It holds the contract, invariants, failure modes mapped to tests, and the selected and omitted strategies.
- `README.md` holds the scope, File Index, Run and Logs.
- `agent_swarm_fixtures.py` is the harness.

`docs/spec/agent-swarm/test-plan.md` holds the coverage map, the tests not written, the red run and the implementer notes. Every AC-1 to AC-21 row in spec §6.2 now names its test or tests.

## Fixtures added

`agent_swarm_fixtures.py` is the only fixtures module, and it is new. No existing test or fixture file was edited.

**Scripted runner and steps**

- `ScriptedSwarm` patches only `BaseAgent._runner_for_model`. It routes each model call by agent name, either to that agent's step list (one continuous list across all its turns) or to a behaviour callable.
- For each call it records the prompt, system string, history, tool names, schemas and descriptions.
- `assert_complete` fails on unscripted calls, on guard failures, and on unused steps.
- Step builders: `tool_call`, `reply`, `finish` (`isDone`), `send` (`message`), `fail`, `observe`, `after`, and `provider_error`.

**Ordering without sleeps**

- `Gate` and `Signal` are asyncio events with a 20 s failure-only guard.
- `EventLog` is a sync or async `on_event`. It records what it receives, sets Signals on (kind, agent, nth), runs hooks, can raise `CallbackBoom`, and tracks overlap in `max_active`.
- `yield_to_loop` is `asyncio.sleep(0)`.
- The search tools are `SearchTool` (optionally raising) and `BlockingSearchTool` (`entered` and `release` Signals).

**Hang guards**

- `run_swarm` bounds every `arun` at 60 s and turns a hang into an `AssertionError`.
- `guard_asyncio_run` does the same for the §4 snippet's `asyncio.run`.
- `assert_no_stray_tasks` checks that no task was left behind.

**Readers**

- `tool_results`, `tool_result`, `is_error`, `user_messages`, `message_tool_calls` and `seen_text` read transcripts.
- `prompt_text` reads from the real catalog.
- `template_regex` and `renderings` match rendered templates without hard-coding wording.
- `snapshot`, `error_text`, `of_kind`, `only`, `seq_of` and `describe` are small helpers.

**The oracle**

`assert_event_invariants` replays `result.events` against the §6.1 and §9.1 rules:

- sequence numbering, and SWARM_ENDED as the one last event;
- member-order starts, `elapsed_ms` as an int that never decreases, and per-kind default fields;
- the lifecycle state machine;
- SENT immediately followed by WOKE when the recipient is idle and the budget allows, and the same rule for IDLE with mail;
- acceptance-order delivery;
- the end rule for each stop reason;
- replies as each running agent's last IDLE text;
- `event_error_types`;
- the callback log: never more than one active, and equal to the events (or a cut prefix plus SWARM_ENDED on TIMEOUT).

I checked the oracle in the scratchpad against hand-written AC-3 and AC-5 event sequences. It accepts both valid sequences and rejects all five mutations: no wake, replies in the wrong order, MAX_TURNS claimed without mail, a missed wake with budget left, and QUIET claimed with mail waiting.

**A harness bug found and fixed before the commit**

`SearchTool` assigned `self.name`, but `BaseTool.name` is a read-only property over `spec().name`. That broke collection of the contract module, and it would have failed every search-tool test for the wrong reason. The fixed tool keeps the name privately and serves it from `spec()`. I checked it against the real `BaseTool` and `ToolCall`.

## Existing behaviour probed (no swarm code)

Each fact below was checked on existing code. The tests rely on it:

- **Finish review.** At a plain-reply finish, `review_finish` sees `ctx.tool_result` as None, and the last `ITERATION_OUTPUTS` entry is the reply. At an `isDone` finish, `ctx.tool_result.output` is the `final_answer`. The accepted run's content equals that text, empty included, so the IDLE text equals the reply.
- **Continuation shapes.** A plain-reply CONTINUE appends the assistant reply, then the user feedback. An `isDone` CONTINUE appends the tool call, then the `finish_not_accepted` tool error, then the feedback. Histories stay strict prefixes, including under the 90,000-token trim middleware. The first call has `messages == []`, and the goal is always the call's `prompt`.
- **Tool calls.** `after_tool_call` sees `ctx.tool_call.tool_name` and `ctx.tool_result.status`. A raising tool becomes `[tool_error kind=execution_error]` with `ToolStatus.ERROR`. The loop does not enforce a schema `enum` before `execute`. `isDone` is in the runner's tool list.
- **Fail-closed abort.** A raising `after_tool_call` ends the run normally, with `stop_reason == "middleware_abort"`, after one model call.
- **Provider errors.** A `ProviderRequestError` costs one runner call (no retry at this seam) and is wrapped in `AgentExecutionError` with itself as `__cause__`.
- **Owner-refusing runtime.** Probed with `infinite_memory`: `_runtime()` raises `ConfigurationError`, and `arun` wraps it as `__cause__` with no model call.
- **Validators.** The behaviour of `require_text`, `require_int` (refuses 1.5, True and -1), `require_number`, `require_enum` (refuses value strings), `to_tuple` and `to_folder`; key matcher refusals that name `AgentSwarmSettings.api_keys` without quoting the key; model-pair validation.
- **File tools.** Relative and absolute escapes are refused, and nothing outside changes. `bash` writes inside its root (Git bash on Windows). `mkdir` under a file raises an `OSError`.
- **Runner input.** The runner receives tool descriptions and input schemas verbatim.
- **Clean shutdown.** No task is left pending after an agent run inside a pytest-asyncio test.

## What was pruned and why

| Pruned | Why |
|---|---|
| EC-38 tests | Python 3.11 `TaskGroup` behaviour. The in-progress flag's `finally` is already driven by the EC-19 test. |
| EC-16 (a) test | The same containment branch as AC-7. Reaching it would need a second fault injection into the feature. |
| EC-18 test | Needs wall-clock timing between two awaits, which would be flaky. |
| EC-20, EC-24, EC-25, EC-32 | Stated limitations with nothing to assert. |
| EC-26 | Existing trim middleware with its own tests. The constant is pinned. |
| EC-37 | No cap (Q-8 default). |
| Member-fork test | A fork is a plain `BaseAgent` with the same runtime type, which the AC-12 test drives. |
| INV-25, INV-26, INV-28 (catalog loading) | Neighbour suites, which pass. S4 reviews the diff. |
| `hypothesis` | Not a dependency. Seeded `random.Random` is used instead. |
| Bash in the property tests | A subprocess would make interleavings depend on the machine. With bash excluded, the file tools run synchronously, so each seed's interleaving is reproducible. |
| A reference prototype | Ruled out by the coordinator. A prototype copy made earlier (a pristine repo, no swarm code) was deleted by the coordinator and was not recreated. |
| A role-word list beyond the infinite_memory vocabulary | Words like "leader" or "planner" could appear legitimately ("no agent leads"). NG-10 names InfiniteMemoryAgent's biases. The test bans only words that occur in that family: generator, verifier, subagent, launch_subagent, delegat*, scarcest. |

Q-1 to Q-11 are tested at their defaults only:

- no sync `run`;
- one recipient, with `all` refused as unknown;
- no length cap (a 20,000-character message is delivered whole);
- fixed allow-all;
- no usage on the result;
- TOOL_CALLED carries name and status only;
- per-agent containment;
- the full events tuple;
- no shared-workplace guard;
- five root exports;
- a private root-cause helper (only the AGENT_FAILED text is asserted).

## Red run (exact)

Bootstrap: none needed — global Python 3.11.0 with pytest 8.3.5 / pytest-asyncio 1.3.0; PYTHONPATH=$(pwd).

```
$ PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q
161 failed in 2.31s
$ PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_<area>.py -q
acceptance: 8 failed in 0.87s
messaging: 14 failed in 0.92s
lifecycle: 18 failed in 0.98s
workplace: 14 failed in 0.95s
contract: 71 failed in 1.64s
property: 36 failed in 1.04s
$ PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent tests/test_agent_tool_loop.py tests/test_jev_compute.py tests/multi_agent tests/test_prompts_interface.py -q
197 passed in 4.94s
```

Failure reasons, taken per test case from the junit XML. All 161 come from the feature being absent:

```
 85  ImportError: cannot import name 'AgentSwarmStopReason' from 'vidbyte'
 33  ModuleNotFoundError: No module named 'vidbyte.agents.agent_swarm'
 25  ImportError: cannot import name 'AgentSwarmEventKind' from 'vidbyte'
 11  ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.agent_swarm'
  2  ImportError: cannot import name 'AgentSwarm' from 'vidbyte'
  1  ImportError: cannot import name 'AgentSwarmMember' from 'vidbyte'
  1  ImportError: cannot import name 'agent_swarm' from 'vidbyte.lib.constants'
  1  vidbyte.lib.errors.base.ConfigurationError: Prompt family does not exist: 'agent_swarm'
  1  AssertionError: assert {} == {'AGENT_SWARM...ge_sent', ...}
  1  AssertionError: vidbyte/agents/agent_swarm does not exist
```

Feature symbols are imported inside each test, and collection has no errors. `python lint/run.py --all --format json` exits 0 with no finding in the pack. The pack is not ruff-formatted, and neither is the existing infinite pack; ruff is not part of `run_ci.py`.

## Spec defects and ambiguities

1. **§9.1 does not say which field a cross-field refusal names.** Where the tests had to choose:
   - SENT `message_id` ≠ its `sequence` names `message_id`;
   - DELIVERED `message_id` ≥ its own `sequence` names `message_id`;
   - a result whose stop reason differs from its SWARM_ENDED may name either `AgentSwarmResult.events` or `AgentSwarmResult.stop_reason`, and the test accepts both.
2. **§9.2 says `AgentSwarmRuntime` "runs once, and raises ConfigurationError on a second call".** It does not say whether a call refused for a bad goal counts as the run. The §8.5 pseudocode checks the goal before "mark it as run", and the AC-18 test pins that: the same runtime runs a valid goal after a refusal.
3. **INV-1 says the goal is "the first user message".** On this loop it reaches the runner as the call's `prompt`, with `messages == []` on the first call (probed). The tests assert `prompt == goal` on every call and that the goal is never repeated as a message. This is a wording gap, not a contradiction.
4. **INV-22 and NG-10 ("no role") give no word list.** The test bans the infinite_memory family's own role and workflow words only (see Pruned).
