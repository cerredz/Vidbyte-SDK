# Test plan: AgentSwarm

Spec: `docs/spec/agent-swarm/spec.md` r3 (approved). Pack: `tests/features/agent_swarm/` with 51 test functions and 161 test cases. All of them are red before the implementation.

The only fake is the model runner, patched at `BaseAgent._runner_for_model` (spec §13). The agent loop, the middleware pipeline, the prompt catalog, the file tools, `bash`, the filesystem (under `tmp_path`), `asyncio` and the settings validation run for real.

Every test that runs a swarm checks two independent views of the run:

- **The event oracle.** `assert_event_invariants` replays `result.events` as the §6.1 state machine.
- **The transcripts.** These are what each model call actually carried, as recorded by the scripted runner.

Levels used below:

- **acceptance**: a full `arun` through the public entry point.
- **integration**: a full `arun` focused on one rule.
- **component**: `AgentSwarmEvents`, `AgentSwarmWorkplace` or `AgentSwarmRuntime` driven directly.
- **contract**: static surface, records and validation.
- **property**: seeded random swarms.

Module prefixes: `acc` is `test_agent_swarm_acceptance.py`, `msg` is `_messaging`, `life` is `_lifecycle`, `work` is `_workplace`, `con` is `_contract`, and `prop` is `_property`.

## Coverage map

### Acceptance criteria

| Spec ID | Test | Level | Failure caught (input + state → wrong output) | Why it cannot pass vacuously |
|---|---|---|---|---|
| AC-1 | `acc::test_section_4_snippet_prints_one_line_per_event_then_quiet_true_swarm_ended_and_one_reply_per_agent` | acceptance | The §4 snippet, run byte for byte (cwd = `tmp_path`, models scripted), where builder writes `c2f.py` and messages tester. Caught: a show line out of sequence order, a missing or extra event, a stop reason other than `quiet`, a last event that is not `swarm_ended`, replies out of member order, or the agents' file missing. | The printed lines are compared in full with the lines rebuilt from `result.events`, plus fixed first lines `1 agent_started builder` and `2 agent_started tester`. `c2f.py` must hold the exact bytes builder wrote. |
| AC-2 | `msg::test_a_message_to_a_working_agent_arrives_after_its_tool_result_without_blocking_the_sender[budget-left, budget-spent]` | integration | Tester is held inside a blocking `web_search` while builder sends. Caught: the send blocks until tester is free, the message lands in the system prompt or before the tool result, it waits for tester's turn end, or it is dropped when the budget is spent. | Tester's second call must hold exactly `[assistant, tool(web_search), user]`, with an inbox rendering from builder. Builder's call 2 must precede tester's call 2, and tester's search can only end after builder's call 2. The events must order SENT < TOOL_CALLED < DELIVERED < IDLE, with no WOKE. |
| AC-3 | `msg::test_a_message_wakes_an_idle_agent_into_a_new_turn_after_its_previous_reply[reply, isdone]` | integration | Tester has ended its turn (plain reply or `isDone`) and is idle; builder sends. Caught: no wake, a wake recorded late, the message placed before tester's previous reply, or a new conversation. | `woke == sent + 1`, IDLE < SENT < WOKE < DELIVERED. The second call's history extends the first's, and its last two entries are the previous reply (or `isDone`'s finish-not-accepted result) and then the inbox. |
| AC-4 | `acc::test_agents_that_end_their_first_turn_without_messages_end_quiet_with_one_reply_each[reply, isdone, empty-reply × default-budget, budget-equals-agents]` | acceptance | No agent sends anything. Caught: the swarm hangs, ends with a reason other than QUIET, returns replies in another order, drops an empty reply, or records TOOL_CALLED for `isDone`. | There are exactly five events, each IDLE text equals the scripted reply (empty included), and replies hold `(name, text)` in member order. |
| AC-5 | `life::test_a_spent_turn_budget_stops_wakes_and_ends_max_turns_with_the_message_undelivered` | integration | `max_turns=2` with two agents; builder sends to an idle tester. Caught: the send is refused, tester is woken past the budget, or the swarm ends QUIET with mail waiting. | The send's tool result is the `message_sent` rendering. There is no WOKE or DELIVERED, tester makes exactly one call, the stop reason is MAX_TURNS, and both replies are returned. |
| AC-6 | `life::test_the_time_limit_cancels_every_agent_and_returns_timeout` | integration | builder's model call never answers; `timeout_seconds=0.5`. Caught: `arun` raises, waits for the call, returns a reason other than TIMEOUT, returns replies, or leaves tasks pending. | The events are exactly `[STARTED b, STARTED t, IDLE t, ENDED]`. No stray task remains, and `arun` returns well before the 20 s guard on the stuck call. |
| AC-7 | `life::test_a_provider_error_fails_only_that_agent_names_its_cause_and_stops_its_mail` | integration | reviewer's model raises `ProviderRequestError`; builder messages reviewer after the failure. Caught: the whole swarm fails, the failure text shows BaseAgent's generic wrapper, or the later send is queued. | AGENT_FAILED text starts with `ProviderRequestError`, holds the cause text and not "failed to generate a reply". The send returns the `message_stopped_recipient` rendering, with no SENT. The run ends QUIET with builder's and tester's replies. |
| AC-8 | `life::test_every_agent_failing_ends_failed_with_no_replies` | integration | Every model raises. Caught: the stop reason is QUIET, failures are missing, or replies are returned. | FAILED, one AGENT_FAILED per agent naming that agent's own cause, exactly five events, no replies, no stray task. |
| AC-9 | `msg::test_a_refused_message_is_a_tool_error_queues_nothing_and_the_loop_continues[to-itself, to-an-unknown-name, to-all-is-not-a-broadcast, blank-text, empty-text]` | integration | Builder sends to itself, to `deployer`, to `all`, or with blank or empty text. Caught: the message is accepted, sent as a broadcast, queued silently, or kills the loop. | The tool result is an error holding the catalog rendering (with the given recipient, plus `tester` named as the valid recipient). There is no SENT, WOKE or DELIVERED. TOOL_CALLED is `(message, error)`, builder makes a second call, and tester is never called again. |
| AC-10 | `life::test_a_raising_on_event_callback_never_stops_the_swarm[sync, async × message_sent, swarm_ended]` | integration | `on_event` raises on MESSAGE_SENT or SWARM_ENDED. Caught: the swarm stops, an event is skipped, the error reaches the sender's tool result, or `event_error_types` does not list it. | `event_error_types == ("CallbackBoom",)`. The oracle demands `log.received == result.events` and never two callbacks at once. The send's tool result is not an error. |
| AC-11 | `con::test_invalid_settings_are_refused_naming_the_field_and_creating_nothing[26 cases]` | contract | Covers every invalid input AC-11 lists, plus the name, prompt, provider, model and timeout edges of §9.1 and §9.3. Caught: a refusal that is missing, of the wrong type, names no field, or creates something on disk. | `details["field"]` must start with the exact `Record.field`, the same text must appear in the message, and the `tmp_path` listing must be unchanged. |
| AC-12 | `con::test_runtime_type_refuses_outside_a_swarm_without_calling_a_model` | contract | A plain `BaseAgent(runtime="agent_swarm_member")`. Caught: the runtime is built without a swarm, the refusal text or details are wrong, the error escapes unwrapped from `arun`, or a model is called. | The exact message prefix, the `AgentSwarm(AgentSwarmSettings(` and `arun(` hints, and `details == {"received_swarm_runtime": "NoneType"}`. The `__cause__` type must be ConfigurationError, and the scripted runner must record zero calls. |
| AC-13 | `con::test_each_agent_holds_exactly_the_swarm_tools_and_a_message_schema_of_its_peers[no-search-tool, with-search-tool]`; `work::test_file_tools_refuse_paths_outside_the_workplace_and_change_nothing_there` | contract / integration | Three agents, with and without a search tool. Caught: a missing, extra or duplicated tool; `to` not limited to the peers; extra schema keys; descriptions not taken from the catalog; file tools reaching outside the root. | Tool names are compared as an exact sorted list. For the schema, the `to` enum must equal the agent's peers, `required` must be `{to, text}`, and `additionalProperties` must be False. Six relative and absolute escapes must all be tool errors with status error, the outside file must keep its bytes, and its text must never reach the model. |
| AC-14 | `con::test_each_system_prompt_is_own_prompt_then_swarm_prompt_then_agentic_loop_prompt` | contract | Three agents, one of whose own prompts holds `{"ok": true}` and `{name}`. Caught: the order is wrong, the own prompt is formatted (braces lost), the swarm prompt is missing or doubled, it differs between agents beyond names, or it holds digits. | The segment between the own prompt and the loop prompt must fully match the `system_prompt` template with the agent's name, every peer must appear in it, and the segments must be identical once names are masked. |
| AC-15 | `life::test_a_second_concurrent_arun_is_refused_and_a_later_arun_starts_fresh` | integration | `arun` is called while a run is held mid-call, then again after it finishes. Caught: the concurrent call is accepted, or the refused call disturbs the first run, or the third run reuses agents, history or numbering. | `pytest.raises(ConfigurationError)` with the model call count unchanged. `log.received` must equal the first run's events plus the third run's. The third run's first calls must have empty histories and the new goal. |
| AC-16 | `work::test_a_missing_workplace_is_created_with_its_parents_and_the_agents_files_stay` | integration | The workplace is three folders deep and does not exist yet. Caught: no folder is created, a folder is created at construction, or files are lost or extra. | The folder must not exist before `arun`. Afterwards the snapshot must be exactly `notes/plan.md` (the written bytes) and `test-log.txt` (written by bash). |
| AC-17 | `con::test_public_names_import_from_every_documented_path` | contract | Caught: an import path that is missing or duplicated, a sixth `AgentSwarm*` root export, enums not in `vidbyte.lib.enums.__all__`, the registry not mapping the runtime, the runtime missing from the linear-loop set, or a contract file that was not regenerated. | Object identity across the paths, `__all__` equality for the package, and the root `AgentSwarm*` set equal to the five names. The contract JSON must contain the five names. |
| AC-18 | `work::test_a_blank_or_non_text_goal_is_refused_before_any_side_effect[empty, blank, none, a-number × AgentSwarm, AgentSwarmRuntime]` | integration | A bad goal on either entry point. Caught: the goal is accepted, the refusal names the wrong field, a folder is created, a model is called, or the object is spent by the refusal. | `details["field"] == "goal"`, zero model calls, no folder (AgentSwarm), and the same object must then run a valid goal to QUIET. |
| AC-19 | `life::test_tool_called_events_carry_name_and_status_and_skip_isdone` | integration | Tester runs `bash`, then a missing-file `read_lines`, then `isDone`. Caught: TOOL_CALLED is missing, recorded for `isDone`, or has the wrong status; bash does not run in the workplace. | Exactly `[("bash", SUCCESS), ("read_lines", ERROR)]`, `bash-note.txt` in the workplace holding `hello`, and an IDLE text equal to the `final_answer`. |
| AC-20 | `msg::test_an_agent_that_ends_its_turn_with_mail_waiting_continues_at_once` | integration | A message is accepted while tester's model call is in flight; the call is a plain reply. Caught: tester goes idle and waits for another send (a lost wake-up), or the message is delivered twice. | `woke == idle + 1`, `delivered == idle + 2`. The second call's history is exactly `[assistant "First pass done.", user inbox]`. |
| AC-21 | `con::test_api_keys_never_appear_in_reprs_events_model_calls_or_errors` | contract | `api_keys` holds a key-shaped fake. Caught: key text in the repr or str of settings, swarm or runtime, in an event, in anything a model call carried, or in a refusal; a mixed-provider swarm without the second key accepted. | A substring search for `SwarmFakeKey` across every surface, after a real run with a message exchange. The mixed-provider refusal must name exactly `AgentSwarmSettings.api_keys`. |

### Invariants, edge cases, requirements and decisions

| Spec ID | Test | Level | Failure caught (input + state → wrong output) | Why it cannot pass vacuously |
|---|---|---|---|---|
| INV-1, INV-2, INV-3, FR-2 | `acc::test_every_agent_gets_the_goal_verbatim_as_the_prompt_of_every_call_in_one_conversation`; property tests | acceptance / property | A goal with braces, unicode and edge whitespace, over three calls per agent. Caught: a goal that is stripped, formatted or repeated as a message, a history that is edited or restarted, or a system string that changes. | Every call's prompt equals the goal byte for byte; histories are strict prefixes of the next call's; one system string per agent. |
| INV-4, EC-2 | `msg::test_two_agents_messaging_each_other_mid_turn_never_deadlock` | integration | Two agents send to each other from overlapping calls (`Gate(2)`). Caught: a send that waits for the recipient, which deadlocks here (turned into a failure by the guards), or a delivery that needs a wake. | Each agent makes exactly three calls, holds the other's message once, and has one DELIVERED; there is no WOKE. |
| INV-5, INV-6, EC-4 | `msg::test_messages_queued_before_one_delivery_point_arrive_together_in_acceptance_order` | integration | Two senders queue for one held recipient. Caught: two user messages instead of one, the wrong order, or unlabeled messages. | One inbox rendering with both labeled renderings in acceptance order, and two back-to-back DELIVERED events with increasing ids. |
| INV-7, D-4, EC-1 | `msg::test_a_message_accepted_while_the_recipient_is_going_idle_is_never_lost` | component | `AgentSwarmRuntime.post_message` is started inside the very `on_event` call that reports tester's AGENT_IDLE. Caught: a send decided against a stale "working" state, leaving tester idle with mail (QUIET with undelivered mail, or a hang). | The send's result is `message_sent`, the events order IDLE < SENT < WOKE < DELIVERED, tester's second call holds the inbox, and the oracle checks no undelivered mail on QUIET. |
| INV-8, EC-6 | AC-9 test | integration | See AC-9. | See AC-9. |
| INV-9, INV-10, EC-8, EC-9 | AC-5 test; AC-4 `budget-equals-agents`; `prop::test_random_schedules_under_a_tight_turn_budget_end_quiet_or_max_turns_by_the_rules[16..27]` | integration / property | A budget of n to n+2 turns over random message schedules. Caught: a wake past the budget, QUIET with mail waiting, or MAX_TURNS without it. | The oracle replays the turn count and the end rule on every event; 12 seeds. |
| INV-11, INV-12 | AC-4, AC-6, AC-8 tests | integration | Caught: tasks left pending after `arun`, or replies on TIMEOUT or FAILED. | `assert_no_stray_tasks` and the oracle's replies rule. |
| INV-13, INV-14, NFR-1 | Every swarm test (oracle); `prop::test_random_schedules_keep_every_event_invariant_and_end_quiet[0..15]` | property | Random schedules of valid and refused sends, failing reads, writes, both turn endings, and scheduler yields in model calls and in sync or async callbacks. Caught: gaps or repeats, more than one SWARM_ENDED, events out of causal order, and DELIVERED without a matching SENT. | The oracle checks every event. Reconciliation then requires that successful `message` results equal the SENT events, that TOOL_CALLED equals the transcript's non-`isDone` tool results with status, that IDLE count equals the turns the model ended, and that every delivered text appears once, labeled, in order, and never in a third agent's view. |
| INV-15, INV-16, D-6 | AC-10 test; `life::test_the_event_outbox_delivers_each_event_once_in_order_even_with_concurrent_flushes`; `life::test_a_flush_cancelled_mid_callback_never_repeats_that_event`; `life::test_the_time_limit_cuts_a_slow_callback_once_and_still_delivers_swarm_ended` (EC-23) | component / integration | Overlapping flushes; a flush cancelled inside a callback; a callback stuck until the time limit. Caught: double delivery, out-of-order delivery, overlapping callbacks, swallowed cancellation, a repeated cut event, or SWARM_ENDED not delivered on TIMEOUT. | Exact `log.received` lists, `max_active == 1`, `flushing.cancelled()`, and on TIMEOUT `log.received == [S, S, I, ENDED]`. |
| INV-17, EC-12, EC-13 | AC-7, AC-8 tests; `life::test_the_last_working_agent_failing_ends_the_swarm_without_a_hang`; `prop::test_random_schedules_with_one_failing_agent_contain_the_failure[28..35]` | integration / property | A failure while the others are idle or working, at a random point in a forced first turn. Caught: the end check is not run on failure (a hang, turned into a failure by the guard), the failure is not contained, or later sends to the failed agent are queued. | The exact failure text prefix, QUIET with the survivors' replies, and refused sends matching `message_stopped_recipient`. |
| EC-16 (b) | `life::test_an_exception_inside_a_tool_is_a_tool_error_not_a_failure` | integration | The search tool raises `RuntimeError`. Caught: the tester fails, or TOOL_CALLED has status success. | There is no AGENT_FAILED, TOOL_CALLED is `(web_search, ERROR)`, the tool result is an error, and both replies are returned. |
| EC-15, EC-16 (c) | `life::test_a_turn_middleware_recording_bug_fails_only_that_agent_naming_the_middleware_abort` | integration (one fault injection) | `record_tool_call` raises for tester. Caught: the middleware not failing closed (a TOOL_CALLED silently dropped while tester runs on), the early return not treated as a failure, or the failure naming the bug's type. | AGENT_FAILED text matches `middleware.abort` and not `RuntimeError`. Tester makes one call and has no TOOL_CALLED. Builder's TOOL_CALLED is intact, and the run ends QUIET. |
| EC-19 | `life::test_cancelling_arun_propagates_and_the_swarm_can_run_again` | integration | The caller cancels `arun` mid-call. Caught: swallowed cancellation, tasks left behind, or an in-progress flag that is never cleared. | `task.cancelled()` and no stray tasks; the next `arun` runs fresh to QUIET. |
| EC-27 | `msg::test_message_text_reaches_the_recipient_whole_and_unformatted` | integration | Text with format fields, braces, unicode, newlines and 20,000 extra characters. Caught: `str.format` applied to the text, truncation, or escaping. | The SENT text equals the input, and the delivered message contains it exactly once inside a labeled rendering. |
| EC-28, EC-29, INV-18, INV-20 | `work::test_a_file_that_appears_at_the_workplace_path_is_refused_before_any_model_call`; `work::test_a_workplace_that_cannot_be_created_is_refused_with_the_os_error_as_cause`; `work::test_constructing_the_swarm_or_its_runtime_creates_no_folder`; `work::test_a_second_run_on_the_same_workplace_sees_earlier_files_and_user_files_stay_byte_identical` (EC-31) | integration / component | A file at the path; a parent that is a file; construction alone; a second run over user files with CRLF bytes. Caught: a refusal that is missing or unchained; a side effect at construction; a deleted or rewritten user file; a later run that cannot see earlier files. | The path must be named in the message or details, `__cause__` must be an `OSError`, there must be zero model calls, the snapshot must be byte-identical, and the read results must show the earlier text. |
| INV-19 | AC-15 test; `life::test_a_swarm_runtime_runs_only_once` | integration | A second `arun` on one runtime. Caught: it is accepted. | `ConfigurationError` with no new model call. |
| INV-21, FR-3, D-13 | AC-13 tests | contract | See AC-13. | See AC-13. |
| INV-22, NFR-4, NG-10 | `con::test_prompt_leaves_hold_no_digits_roles_or_examples` | contract | Caught: a leaf with a digit, a word from the infinite_memory family's role and workflow vocabulary (generator, verifier, subagent, launch_subagent, delegat*, scarcest), or examples; a description leaf outside 4–5 sentences; a swarm prompt missing what AC-14 requires. | It reads the real catalog family; before the feature exists the family is missing, which is the red failure. |
| INV-24, EC-35 | AC-12 test | contract | See AC-12. | See AC-12. |
| INV-28, W-2 | `con::test_prompt_family_has_exactly_the_ten_documented_leaves_with_their_fields` | contract | Caught: a missing or extra key, a leaf with the wrong `str.format` fields, or a blank leaf. | `Prompt` members must equal the ten documented ones, and `string.Formatter().parse` field sets must equal the documented ones. |
| FR-1, §9.3 | `con::test_boundary_settings_are_accepted_with_documented_defaults` | contract | Caught: defaults, boundary values (100 agents, a 64-character name, one week), provider conversion, path resolution, or the constants' values differing from the spec. | Exact equality on every default and constant. |
| §8.5, NFR-5 | `con::test_records_and_settings_are_frozen_slotted_dataclasses_with_the_documented_fields`; `con::test_enum_values_are_the_documented_lowercase_strings` | contract | Caught: a record that is not frozen or slotted, field order or names differing from §8.5, `api_keys` shown in the repr, or wrong enum values. | Field lists are compared exactly, and the set of `repr=False` fields must be `{api_keys}`. |
| §9.1 | `con::test_event_records_enforce_the_per_kind_field_table[22 cases]`; `con::test_result_records_enforce_one_ordered_sequence_ending_in_swarm_ended[10 cases]` | contract | Caught: an event that sets a field its kind does not list, misses a required field, has a bad number, or passes its kind as a raw string; a result with gaps, without a final SWARM_ENDED or with two, with a mismatched stop reason, with non-`AgentMessage` replies, or with blank or multi-line error types. | Every documented valid shape must build with its fields kept. Each invalid case must name `AgentSwarmEvent.<field>` or `AgentSwarmResult.<field>` exactly. |
| §9.2 | `con::test_entry_points_refuse_anything_but_their_documented_types` | contract | Caught: `AgentSwarm` accepting a dict or None; `AgentSwarmRuntime` accepting a str root. | `ConfigurationError` each time, with nothing on disk. |
| NFR-2, NFR-3, §8.4 | `con::test_new_modules_stay_inside_the_complexity_budget_and_never_sleep` | contract | Caught: an eighth package module, any of the eleven modules over 400 lines after its header, or any `sleep` call in the package or toolset. | An AST scan of the real files; red today because the package folder does not exist. |
| NFR-9 | AC-6 test | integration | See AC-6. The wall-clock bound is loose on purpose (limit + 10 s). | The stuck call's own guard is 20 s, so a time limit that does not cancel fails the bound. |
| FR-14 | AC-17 test | contract | See AC-17. | See AC-17. |
| FR-15 | Oracle replies rule; §9.1 result test | integration / contract | Caught: replies that are not each released agent's last IDLE text in member order, or replies on TIMEOUT or FAILED. | Exact `(sender, content)` lists. |

## Tests deliberately not written

| Spec ID | Why not |
|---|---|
| EC-38 | `KeyboardInterrupt`, `SystemExit` and uncontained `Exception`s propagate through Python 3.11's `TaskGroup`, which the spec does not change. The in-progress flag's `finally` is the one EC-19's test drives. |
| EC-16 (a) | An exception in `collect_messages` or `end_turn` takes the same `VidbyteSdkError` containment branch as the AC-7 provider error. Forcing it would need a second fault injection into the feature. |
| EC-18 | The time limit hitting after the end was decided lies between two awaits of member unwinding. Reaching it needs wall-clock timing, which would be flaky. |
| EC-20, EC-24, EC-25, EC-32 | Stated limitations with no control to test. |
| EC-26 | The trim is the existing `MessageHistoryCompactionMiddleware`, covered by its own tests. Its constant (90,000) is pinned in the boundary test. |
| EC-37 | No cap exists (Q-8 default), so there is nothing to assert beyond the property runs. |
| INV-25, INV-26, INV-28 (catalog load) | Covered by the neighbour suites, which pass: `tests/features/infinite_memory_agent`, `tests/test_agent_tool_loop.py`, `tests/test_jev_compute.py`, `tests/multi_agent`, `tests/test_prompts_interface.py`. S4 checks that the diff leaves those files untouched. |
| A fork of a member (INV-24) | A fork builds a plain `BaseAgent` with the same runtime type, which the AC-12 test drives directly. |
| `hypothesis` | Not a dependency. Seeded `random.Random` schedules stand in for it. |

## Red run

Bootstrap: none needed — global Python 3.11.0 with pytest 8.3.5 / pytest-asyncio 1.3.0; PYTHONPATH=$(pwd).

Command: `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q`. Result: `161 failed in 2.31s`. Per file: acceptance `8 failed`, messaging `14 failed`, lifecycle `18 failed`, workplace `14 failed`, contract `71 failed`, property `36 failed`. Every failure is the feature being absent:

| Count | Reason |
|---|---|
| 85 | `ImportError: cannot import name 'AgentSwarmStopReason' from 'vidbyte'` |
| 33 | `ModuleNotFoundError: No module named 'vidbyte.agents.agent_swarm'` |
| 25 | `ImportError: cannot import name 'AgentSwarmEventKind' from 'vidbyte'` |
| 11 | `ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.agent_swarm'` |
| 2 | `ImportError: cannot import name 'AgentSwarm' from 'vidbyte'` |
| 1 | `ImportError: cannot import name 'AgentSwarmMember' from 'vidbyte'` |
| 1 | `ImportError: cannot import name 'agent_swarm' from 'vidbyte.lib.constants'` |
| 1 | `ConfigurationError: Prompt family does not exist: 'agent_swarm'` |
| 1 | `AssertionError: assert {} == {'AGENT_SWARM...` (no `Prompt.AGENT_SWARM_*` members) |
| 1 | `AssertionError: vidbyte/agents/agent_swarm does not exist` (budget test) |

Collection: 161 tests collected with no collection error.

Neighbours: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent tests/test_agent_tool_loop.py tests/test_jev_compute.py tests/multi_agent tests/test_prompts_interface.py -q` gives `197 passed in 4.94s`. The repository lint, `python lint/run.py --all --format json`, exits 0 with no finding in the pack.

## Notes for the implementer

**Routing and offers**

- The scripted runner routes model calls by the member `BaseAgent`'s `name`, so each member agent's name must be the member's `name`. Each member must reach its runner through `BaseAgent._runner_for_model`.
- The tests read tools from the runner's `tools` option.
  - Each tool description must equal its catalog leaf after `strip()`.
  - The `to` and `text` properties must each carry `type: string` and a catalog `description`.
  - `to` also carries `enum` (the peers).
- The tests never compare hand-written wording. Inbox, refusal and sent texts are matched against the catalog templates with regexes: `fullmatch` for the `inbox` user message, and `search` inside tool results. A tool-error envelope prefix around a refusal is therefore fine.

**Ordering the tests depend on (§8.5 pseudocode)**

- `end_turn` marks the agent idle and creates its wait future *before* it flushes AGENT_IDLE. The EC-1 test starts `runtime.post_message("builder", "tester", ...)` inside the callback that reports that IDLE and expects a wake.
- `AgentSwarmRuntime.arun` checks the goal *before* it marks the runtime as run. The AC-18 test expects the same runtime to run a valid goal after refusing a blank one.
- A send to an idle agent records SENT then WOKE back to back. A turn end with mail records IDLE, WOKE, then one DELIVERED per message, back to back.
- `flush` marks each event delivered before awaiting the callback, delivers under one `asyncio.Lock`, catches `Exception` into `error_types`, and lets cancellation through.

**Failures and fault injection**

- An early return's AGENT_FAILED text must contain the run's stop reason value (`middleware_abort`) and must not contain the bug's type.
- The fault-injection test replaces `AgentSwarmRuntime.record_tool_call` on the class. Call it through the runtime instance, with the agent name as the first positional argument or as `name=`.
- No TOOL_CALLED for `isDone`.

**Refusal field names**

- Settings and member refusals put the field in `details["field"]`, starting with `AgentSwarmSettings.<field>` or `AgentSwarmMember.<field>`, and repeat that text in the message.
- Event refusals name exactly `AgentSwarmEvent.<field>`. Two cross-field rules are pinned:
  - a SENT `message_id` that differs from its own `sequence` names `message_id`;
  - a DELIVERED `message_id` at or above its own `sequence` names `message_id`.
- A result whose stop reason differs from its SWARM_ENDED may name `AgentSwarmResult.events` or `AgentSwarmResult.stop_reason`.

**Existing behaviour confirmed by probes (no swarm code)**

- At a plain-reply finish, `review_finish` sees `ctx.tool_result` as None, and the last `ITERATION_OUTPUTS` entry is the reply. At an `isDone` finish, `ctx.tool_result.output` is the `final_answer`, and the accepted run's content equals that text (empty included).
- `after_tool_call` gets `ctx.tool_call.tool_name` and `ctx.tool_result.status`. A raising tool reaches it as `ToolStatus.ERROR`.
- The loop does not enforce a schema `enum` before `execute`, so `AgentSwarmMessageTool.execute` must check the recipient itself (D-13).
- A raising `after_tool_call` aborts the run with `stop_reason == "middleware_abort"` after one model call.
- A raised `ProviderRequestError` costs one runner call (no retry at this seam) and arrives as `AgentExecutionError` with the error as `__cause__`.

**Timing and replay**

- The TIMEOUT tests use `timeout_seconds=0.5`. The only wall-clock assertion is `elapsed < 10.5 s`.
- Property seeds are 0–35. A failure prints its plan and replays from its seed.
- No test sleeps. `yield_to_loop` is `asyncio.sleep(0)` in test code only. The budget test's no-sleep scan covers only the package and the toolset.
