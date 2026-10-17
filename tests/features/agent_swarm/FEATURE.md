# Feature: AgentSwarm — user-defined agents that run their tools and message each other

## High-Level Feature Description

A developer defines two or more agents, each with a name, a model and a system prompt. The developer points them at one shared folder and calls `await AgentSwarm(settings).arun(goal)`. Every agent gets the same goal and works with `bash`, `grep`, `read_lines`, `write_text` and `patch_file` in that folder. An agent can `message` any other agent without waiting. A message reaches a busy agent between its tool calls as a new user message, and it wakes an idle agent. The swarm ends once no agent is working, as QUIET, MAX_TURNS (the turn budget is spent and a message is still waiting) or FAILED, or at the time limit. It returns the full ordered tuple of events.

Under the hood, each agent runs one long-lived ordinary SDK loop for the whole swarm. One `AgentSwarmRuntime` per run coordinates the agents through four entry points: `post_message`, `collect_messages`, `end_turn` and `record_tool_call`. All coordination state changes inside synchronous blocks on one event loop.

The feature is a mailbox protocol, so its regressions look like the classic ones of distributed systems:
- a lost wake-up, which leaves a message sitting with an idle agent while the swarm ends QUIET;
- a send that blocks on its recipient, which deadlocks two agents that message each other;
- a double or misrouted delivery;
- a "delivered" event recorded before its "sent";
- an end check that misses an agent which returned early, so the swarm never ends;
- an event stream with gaps or repeats, or one that reaches the callback out of order or twice at once.

Each of these makes the swarm's data untrustworthy without any visible error. The tests here exist to make each one loud.

## Contract

- **Imports.**
  - `from vidbyte import AgentSwarm, AgentSwarmMember, AgentSwarmSettings, AgentSwarmEventKind, AgentSwarmStopReason` works.
  - `vidbyte.agents.agent_swarm` and `vidbyte.agents` export `AgentSwarm`, `AgentSwarmSettings`, `AgentSwarmRuntime`, `AgentSwarmEvents`, `AgentSwarmWorkplace` and `AgentSwarmMemberRuntime`.
  - `vidbyte.tools.toolsets` exports `AgentSwarmTools`.
  - The records live in `vidbyte.lib.dataclasses.agent_swarm`.
  - `AgentRuntimeType.AGENT_SWARM_MEMBER` resolves to `AgentSwarmMemberRuntime` (spec AC-17, §8.5).
- **Settings and the goal.**
  - `AgentSwarmMember` and `AgentSwarmSettings` validate every field when they are built.
  - A refusal is a `ConfigurationError` whose `details["field"]` names the field, raised before any folder is created.
  - `AgentSwarm.arun` and `AgentSwarmRuntime.arun` refuse a blank or non-text goal the same way (AC-11, AC-18, INV-18).
- **One run.**
  - Each `arun` prepares the workplace folder, creating it with its parents but never deleting anything.
  - It builds one fresh `AgentSwarmRuntime`, which builds fresh agents.
  - It returns an `AgentSwarmResult(stop_reason, events, replies, event_error_types)`.
  - A second concurrent `arun` on one `AgentSwarm` is refused. An `AgentSwarmRuntime` runs only once (AC-15, AC-16, INV-19, INV-20).
- **What each agent sees.**
  - Its model sees the goal as the prompt of every call.
  - It holds exactly `bash`, `grep`, `read_lines`, `write_text`, `patch_file`, `message` and `isDone`, plus the developer's search tool when one is given.
  - Its system prompt is its own prompt, then the swarm prompt, then the loop's agentic-loop prompt (AC-13, AC-14, INV-1, INV-21).
- **Messages.**
  - `message(to, text)` returns as soon as the message is queued.
  - A message reaches a working recipient after its next tool iteration, or at its turn end. At that point every waiting message is delivered as one user message labeled with each sender, in acceptance order.
  - A message wakes an idle recipient when the turn budget allows.
  - Blank text, self, unknown and failed recipients are refused as tool errors (AC-2, AC-3, AC-9, AC-20, INV-4…INV-8).
- **Ending.**
  - The swarm ends exactly when no agent is working.
  - The stop reason is FAILED when every agent failed; otherwise MAX_TURNS when an idle running agent still holds mail; otherwise QUIET.
  - TIMEOUT is a hard stop that overrides the others.
  - `replies` holds each released agent's last reply in member order, and is empty on TIMEOUT and FAILED (AC-4…AC-8, INV-9…INV-12).
- **Events.**
  - Events are numbered 1..N with no gap or repeat, in true causal order, ending with the one `SWARM_ENDED`.
  - `on_event` (sync or async) is called once per event, in order, never twice at once.
  - Callback exceptions are contained and their type names are listed (AC-10, AC-19, INV-13…INV-16).
- **Failures.** One agent's contained failure becomes one `AGENT_FAILED` event that names the root cause, and the others continue. A tool exception is a tool error, not a failure (AC-7, AC-8, INV-17, EC-12…EC-16).

## Actors / Callers

- SDK callers who build `AgentSwarm(AgentSwarmSettings(...))` and await `arun(goal)`, optionally with an `on_event` callback.
- The model inside every member agent, which calls the swarm's tools.
- `AgentSwarmRuntime`'s three member-side callers: the member loop (`collect_messages`), the turn middleware (`end_turn`, `record_tool_call`) and the `message` tool (`post_message`).
- A plain `BaseAgent` or a fork that asks for `runtime="agent_swarm_member"`, and must be refused.

## Inputs and Preconditions

- Two to `AGENT_SWARM_MAX_AGENTS` members with distinct names that match `AGENT_SWARM_NAME_PATTERN`.
- A workplace path that is not a file.
- A model each member's provider can run.
- Optionally `api_keys`, one search `BaseTool`, an `on_event` callable, `max_turns` of at least the number of agents, and `timeout_seconds` in (0, 604800].
- The tests use `tmp_path` for every folder, a scripted model runner, the real filesystem and real `asyncio`.
- `bash` cases need a POSIX bash (Linux CI) or Git for Windows bash locally.

## Observable Outcomes

- **What each agent's model was sent:** `prompt`, `system`, `messages`, the offered tool names, schemas and descriptions.
- **Tool results:** they arrive as tool messages in the next call.
- **The result:** `result.stop_reason`, `result.events`, `result.replies` (`AgentMessage.sender` / `.content`) and `result.event_error_types`.
- **Callback output:** the sequence of events the `on_event` callback received.
- **The disk:** the files under the workplace.
- **Errors raised:** `ConfigurationError` (with `details["field"]`), `AgentExecutionError` (with `__cause__`) and `asyncio.CancelledError`.

## State Transitions

**Per agent** (spec §9.1):
- `Working → Working`: the turn ends with mail waiting and budget left; it records `AGENT_IDLE` then `AGENT_WOKE`.
- `Working → Idle`: records `AGENT_IDLE`.
- `Idle → Working`: a message is accepted and budget is left; it records `AGENT_WOKE`.
- `Idle → Done`: the swarm ends QUIET, MAX_TURNS or FAILED, and the agent is released.
- `Working → Failed`: records `AGENT_FAILED`.
- `Idle → Failed`: an unrequested `CancelledError` is raised while the agent's own `AGENT_IDLE` is delivered (EC-39, r4); records `AGENT_FAILED`.
- `Working/Idle → Cancelled`: the time limit is reached.

**Per swarm:** `Ready → Running → Ready`. An `AgentSwarmRuntime` goes `New → Running → Ended` and is never reused.

**Per message:** `accepted (MESSAGE_SENT) → delivered once (MESSAGE_DELIVERED)`, or left undelivered only when the recipient failed or the swarm ended MAX_TURNS or TIMEOUT.

## Invariants

These are checked on every run by `assert_event_invariants` in `agent_swarm_fixtures.py`, the pack's oracle. They are also checked on random schedules by `test_agent_swarm_property.py`.

**Sequence and ending**
- `sequence` runs 1..N in order. Exactly one `SWARM_ENDED` exists; it is last, its agent is `""`, and its stop reason equals the result's.
- The first events are one `AGENT_STARTED` per member, in member order.

**Lifecycle**
- Each agent's lifecycle events read `STARTED (IDLE WOKE)* [IDLE | FAILED]`. The oracle lets an agent fail only while working; spec r4's EC-39 idle variant fails an idle agent (`IDLE` then `FAILED`, which INV-14 allows), so that one test checks its events directly instead of calling the oracle.
- An agent's `TOOL_CALLED`, `MESSAGE_SENT` and `MESSAGE_DELIVERED` events happen only while it is working.
- Nothing follows its `AGENT_FAILED`.

**Messages**
- A `MESSAGE_SENT` has `message_id == sequence`.
- Every `MESSAGE_DELIVERED` names an earlier `MESSAGE_SENT` with sender and recipient swapped.
- No message is delivered twice.
- Deliveries to one recipient follow acceptance order.

**Turns and stop reasons**
- Turns started (`STARTED` + `WOKE`) are at most `max_turns`.
- QUIET or FAILED: every message to a non-failed agent was delivered.
- MAX_TURNS: some message to a non-failed agent was not delivered, and the budget is exactly spent.
- FAILED holds exactly when every agent failed.

**Replies and fields**
- On QUIET or MAX_TURNS, `replies` holds one reply per non-failed agent, in member order, whose content is that agent's last `AGENT_IDLE` text. On TIMEOUT and FAILED it is empty. The one exception is EC-18 (r4): when the time limit fires after the end was decided, `replies` may miss the agent it cut, so that test checks a subset and the `AGENT_IDLE` texts instead of calling the oracle.
- `elapsed_ms` is a whole number that never decreases.
- Every field the §9.1 table does not list for a kind keeps its default.

**The callback**
- On QUIET, MAX_TURNS or FAILED, the `on_event` callback received exactly `result.events`.
- On TIMEOUT it received an increasing subsequence that ends with `SWARM_ENDED`.

## External Dependencies

- The local filesystem (real, under `tmp_path`).
- `bash` (a real subprocess).
- The model runner: the only fake, patched at `BaseAgent._runner_for_model` so it reaches every member built inside `arun`.
- The prompt catalog (real).
- `asyncio` (real). Ordering is controlled with `Gate`, `Signal` and events the `on_event` callback observes, never with timed sleeps. The one timed wait is in `test_event_time_counts_from_arun_not_from_building_the_runtime`, where the time between building the runtime and calling `arun` is itself under test (D-16).

## Known Failure Modes

Each line is *input + state → wrong output if unguarded*, with the test that catches it.

**Messaging and wake-ups**
- A message sent while the recipient is between its inbox check and becoming idle is queued without a wake. The swarm then ends with mail undelivered, or never ends (`test_a_message_accepted_while_the_recipient_is_going_idle_is_never_lost`).
- `message` waits for the recipient: the sender stalls behind a long tool call (`test_a_message_to_a_working_agent_arrives_after_its_tool_result_without_blocking_the_sender`), and two agents messaging each other deadlock (`test_two_agents_messaging_each_other_mid_turn_never_deadlock`).
- A message to a busy agent is delivered only at its turn end, or is put into the system prompt instead of after the tool result (`test_a_message_to_a_working_agent_arrives_after_its_tool_result_without_blocking_the_sender`).
- Messages that waited together are delivered as separate user messages, in completion order, or without sender labels (`test_messages_queued_before_one_delivery_point_arrive_together_in_acceptance_order`).
- An idle agent is not woken, or is woken by a new `arun`, which loses its history. The wake message lands before the agent's previous reply. After an `isDone` finish the agent is not woken at all (`test_a_message_wakes_an_idle_agent_into_a_new_turn_after_its_previous_reply`).
- An agent that ends its turn with mail waiting goes idle and waits for another send (`test_an_agent_that_ends_its_turn_with_mail_waiting_continues_at_once`).
- Self, unknown, `"all"` or blank sends are queued, recorded as sent, or crash the loop (`test_a_refused_message_is_a_tool_error_queues_nothing_and_the_loop_continues`).
- Message text is passed through `str.format`, cut, or stripped: braces raise or get substituted, and long or unicode text arrives changed (`test_message_text_reaches_the_recipient_whole_and_unformatted`).

**Turns and limits**
- Turn-budget exhaustion still wakes agents, ends QUIET with mail waiting, or cancels working agents (`test_a_spent_turn_budget_stops_wakes_and_ends_max_turns_with_the_message_undelivered`). A budget check also wrongly blocks mid-turn delivery (`test_a_message_to_a_working_agent_arrives_after_its_tool_result_without_blocking_the_sender[budget-spent]`).
- The time limit waits for a model call that never answers, raises instead of returning, or leaves member tasks running (`test_the_time_limit_cancels_every_agent_and_returns_timeout`).
- The time limit cuts the task delivering an event, and that event is then repeated or `SWARM_ENDED` is never delivered (`test_the_time_limit_cuts_a_slow_callback_once_and_still_delivers_swarm_ended`, `test_a_flush_cancelled_mid_callback_never_repeats_that_event`).
- The time limit fires after the end was already decided and overwrites the decided stop reason with TIMEOUT (`test_the_time_limit_firing_after_the_end_was_decided_keeps_the_decided_stop_reason`).
- Event time counts from building the runtime instead of from `arun`, so a delay before the run leaks into every `elapsed_ms` (`test_event_time_counts_from_arun_not_from_building_the_runtime`).
- A huge tool result reaches the model uncut, or a long conversation is sent untrimmed and outgrows the model's context (`test_tool_results_are_cut_and_a_long_history_is_trimmed_before_each_model_call`).

**Failures**
- A provider error stops the whole swarm, or `AGENT_FAILED` reads only the generic "failed to generate a reply" wrapper. A later message to the failed agent is queued (`test_a_provider_error_fails_only_that_agent_names_its_cause_and_stops_its_mail`).
- Every agent failing reads as QUIET, or returns replies (`test_every_agent_failing_ends_failed_with_no_replies`).
- Mail left in a failed agent's inbox is counted as undelivered work, so a swarm that should end QUIET ends MAX_TURNS (`test_mail_left_for_an_agent_that_failed_does_not_turn_quiet_into_max_turns`).
- A `CancelledError` the swarm never requested (raised by a tool, or by an async `on_event` while that agent's own event is delivered) kills the member task silently; the agent stays counted as working and the swarm waits out the whole time limit. In the idle variant a peer's message wakes a dead task (`test_a_cancelled_error_raised_by_a_tool_fails_that_agent_instead_of_waiting_for_the_time_limit`, `test_a_cancelled_error_raised_by_on_event_while_an_agent_works_fails_that_agent`, `test_a_cancelled_error_raised_by_on_event_on_an_idle_agent_fails_it_instead_of_waking_it`). The opposite mistake fails an agent the swarm already released: a cancel that arrives after the end was decided gets an AGENT_FAILED (`test_an_unrequested_cancel_after_the_end_was_decided_does_not_fail_the_released_agent`).
- The end check does not run on a failure, so a swarm whose last working agent fails hangs (`test_the_last_working_agent_failing_ends_the_swarm_without_a_hang`).
- A tool exception is treated as an agent failure (`test_an_exception_inside_a_tool_is_a_tool_error_not_a_failure`). A tool name the model invents with a newline in it fails the agent through the event record instead of coming back as a tool error (`test_a_tool_name_holding_a_newline_is_a_tool_error_not_a_failure`).
- An early return from a member run is mistaken for a normal release, so the agent never leaves the working set and the swarm hangs. Or a turn-middleware bug is swallowed (`fail_closed` turned off) and `TOOL_CALLED` events go missing silently (`test_a_turn_middleware_recording_bug_fails_only_that_agent_naming_the_middleware_abort`).

**Runs, cancellation and workplace**
- A second concurrent `arun` interleaves two event streams that each start at 1. A later `arun` reuses the previous agents' history (`test_a_second_concurrent_arun_is_refused_and_a_later_arun_starts_fresh`). An `AgentSwarmRuntime` runs twice (`test_a_swarm_runtime_runs_only_once`).
- Cancelling `arun` is swallowed, or leaves the in-progress flag set so the swarm can never run again (`test_cancelling_arun_propagates_and_the_swarm_can_run_again`).
- The workplace is created at construction, cleaned at start, or deleted at the end. An existing file there is overwritten (`test_constructing_the_swarm_or_its_runtime_creates_no_folder`, `test_a_missing_workplace_is_created_with_its_parents_and_the_agents_files_stay`, `test_a_second_run_on_the_same_workplace_sees_earlier_files_and_user_files_stay_byte_identical`).
- A file that appears at the workplace path, or a parent that is a file, crashes with a raw `OSError` after agents were built (`test_a_file_that_appears_at_the_workplace_path_is_refused_before_any_model_call`, `test_a_workplace_that_cannot_be_created_is_refused_with_the_os_error_as_cause`).
- The file tools are rooted somewhere other than the workplace, so `../` escapes are accepted (`test_file_tools_refuse_paths_outside_the_workplace_and_change_nothing_there`).

**Events and the callback**
- A raising `on_event` stops the swarm, turns the `message` call into a tool error, or skips later events. An async callback is never awaited (`test_a_raising_on_event_callback_never_stops_the_swarm`).
- Concurrent flushes deliver an event twice, out of order, or call the callback twice at once (`test_the_event_outbox_delivers_each_event_once_in_order_even_with_concurrent_flushes`, every property test).
- `TOOL_CALLED` is recorded for `isDone`, is missing the status, or is missing for failed tool calls (`test_tool_called_events_carry_name_and_status_and_skip_isdone`).
- Any scheduling-dependent ordering bug: a delivery before its send, a delivery to an idle agent, a lost or duplicated message, a non-monotonic sequence, or replies out of member order (`test_random_schedules_keep_every_event_invariant_and_end_quiet`, `test_random_schedules_under_a_tight_turn_budget_end_quiet_or_max_turns_by_the_rules`, `test_random_schedules_with_one_failing_agent_contain_the_failure`).

**Prompts, tools and settings**
- The goal is stripped, formatted, or sent only once, so later turns lose it. A turn starts a new conversation. The system prompt changes between turns (`test_every_agent_gets_the_goal_verbatim_as_the_prompt_of_every_call_in_one_conversation`).
- The member prompt is passed through `str.format`, so braces in it raise or get substituted. The swarm prompt lands before the member's own prompt or after the loop prompt (`test_each_system_prompt_is_own_prompt_then_swarm_prompt_then_agentic_loop_prompt`).
- An agent holds a tool twice, misses `message`, offers itself as a recipient, or the search tool leaks to agents when none was given (`test_each_agent_holds_exactly_the_swarm_tools_and_a_message_schema_of_its_peers`).
- A refused setting creates the folder, or names no field (`test_invalid_settings_are_refused_naming_the_field_and_creating_nothing`). A search tool named `isDone` is accepted and then silently replaced by the loop's own `isDone` (`test_a_search_tool_named_isdone_is_refused_naming_the_reserved_names`). A boundary value is refused (`test_boundary_settings_are_accepted_with_documented_defaults`).
- An API key appears in the settings `repr`, an event, a model call, or a refusal (`test_api_keys_never_appear_in_reprs_events_model_calls_or_errors`).
- The `agent_swarm_member` runtime builds without a swarm and calls the model unguarded (`test_runtime_type_refuses_outside_a_swarm_without_calling_a_model`).
- A prompt leaf states a number, a role or an example, or a leaf has a stray format field that makes `.format` raise at run time (`test_prompt_family_has_exactly_the_ten_documented_leaves_with_their_fields`, `test_prompt_leaves_hold_no_digits_roles_or_examples`).
- A polling loop (`asyncio.sleep`) is used for the end check, or the package outgrows its budget (`test_new_modules_stay_inside_the_complexity_budget_and_never_sleep`).

**What an easy generated test would miss:**
- concurrency "proven" by timing instead of a gate;
- a wake tested only when the message happens to arrive after the idle mark, never during the step that marks it;
- delivery checked by counting events instead of reading the recipient's next model call;
- "no duplicates" checked on events but not on what the model saw;
- a TIMEOUT test where nothing was actually blocked;
- a failure test that only asserts `AGENT_FAILED` exists, not that it names the cause;
- `on_event` checked only with a sync callback.

## Historical Regressions

None yet. The pack was written red, before the implementation, from spec r3 (S2 test author). These spec-review findings shaped specific tests:

| Finding | What changed in the pack |
|---|---|
| R-1 | `AGENT_FAILED` names the `__cause__` type, not the wrapper. |
| R-2 | `isDone` and the agentic-loop prompt are in every call. |
| R-6 | Gates come from `on_event` signals, not from "answered" marks. |
| R-8 | The member runtime's refusal is checked through `_runtime()` and through `arun`'s `__cause__`. |
| R-9 | A recording bug aborts the run through the fail-closed middleware. |
| R-11 | Uncontained exceptions; see the omitted strategies. |
| S4 R-2 | A search tool named `isDone` is refused (spec r4). |
| S4 R-3 | An unrequested `CancelledError` fails its agent: three EC-39 tests (spec r4). |
| S4 R-5 | Mutants M2, M7, M21 and M22 survived the pack; one gap test now kills each (EC-12/INV-10, EC-18, EC-26). |
| S4 R-8 | `TOOL_CALLED` records any non-blank tool name (spec section 9.1), so a newline in a model-made name is a tool error. |
| S4 R-11 | Event time starts in `arun` (D-16). |
| S4 R-14 | `replies` may be partial under EC-18 (spec r4); the EC-18 test checks a subset. |

## Test Suite Map

- `test_agent_swarm_acceptance.py` covers the §4 snippet as written, a swarm that ends after one turn each, and the goal reaching every call verbatim. Start here for a caller-visible regression.
- `test_agent_swarm_messaging.py` covers mid-turn delivery, batching, wakes after a reply or `isDone`, mail waiting at turn end, mutual messages, the lost-wake-up race, refused messages, and text fidelity.
- `test_agent_swarm_lifecycle.py` covers:
  - the turn budget, the time limit, and failures by provider error, tool exception and middleware abort;
  - concurrent and repeated runs, and cancellation;
  - callback containment, the event outbox, and `TOOL_CALLED` events.
- `test_agent_swarm_workplace.py` covers folder creation and preservation, a folder shared across runs, refused workplaces, path escapes, and goal checks.
- `test_agent_swarm_contract.py` covers:
  - exports, enums, the prompt family and the runtime registry and refusal;
  - the exact tools, schemas and system prompt;
  - settings validation and defaults, key secrecy, record validation, and the complexity budget.
- `test_agent_swarm_property.py` covers seeded random schedules over two to four agents, checked against the oracle and against each agent's own transcript.
- `agent_swarm_fixtures.py` holds the scripted runner, `Gate`/`Signal`, `EventLog`, blocking and raising search tools, builders, transcript readers and the event oracle.

Run: `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q` from the repository root.

## Testing Strategies Selected

- **Example-based acceptance tests**, one per AC, each driving the real loop through a scripted runner and reading both the event record and what each model was sent. These are two independent views of the same run.
- **A reusable oracle** (`assert_event_invariants`) applied to every swarm run in the pack. Every scenario test also checks the global invariants, not only its own assertion.
- **Deterministic interleaving control.** A blocking search tool holds an agent mid-turn. `Gate` makes two calls overlap. `Signal`s are set by the `on_event` callback when a state change happens inside the swarm. One test injects a send during the exact callback that reports an agent going idle (the lost-wake-up window).
- **Seeded property tests** (`random.Random(seed)`, no `hypothesis` dependency). Random plans of valid and invalid sends, file reads, `isDone` or plain finishes, and zero-delay scheduler yields run over two to four agents. Each run is reconciled against the oracle and against every agent's transcript: every successful `message` result is exactly one `MESSAGE_SENT`, every delivered text appears once in the recipient's history and never in a third party's, and histories are append-only.
- **Hang guards everywhere.** `run_swarm` bounds every `arun` with `asyncio.wait` and a timeout, cancelling the run on a hang. The §4 snippet's `asyncio.run` is wrapped the same way. Every `Gate`, `Signal` and blocking tool fails after `GUARD_SECONDS` instead of waiting forever. A hang is therefore a failure with a message, never a stuck run.
- **Contract tests** on the static surface: exports, enum values, prompt leaves and their format fields, record validation tables, and the module budget.
- **Mutation-guided gap tests.** S4 ran textual mutants of the implementation (`docs/spec/agent-swarm/review.md` R-5). Each surviving mutant got one test that is green on the real code and red under that mutant: undelivered mail of a failed agent (M2), the time limit after a decided end, held open by a callback that never returns (M7), and a huge search result over many calls, with every bound derived from the constants (M21, M22).
- **One deliberate fault injection** (`test_a_turn_middleware_recording_bug_fails_only_that_agent_naming_the_middleware_abort`). It replaces `AgentSwarmRuntime.record_tool_call` for one agent with a function that raises. EC-15 and EC-16 (c) describe behavior that only a bug in that method can trigger, and the loop defaults have no cap that would end a run early by themselves. It is the only replacement besides the model runner.

## Omitted Testing Strategies

- **Live provider calls.** Offline by NFR-7; the runner is the only fake.
- **`KeyboardInterrupt` or `SystemExit` from a member, and uncontained `Exception`s from the runtime's own code (EC-38).** The propagation is Python 3.11's `TaskGroup` behavior, which the spec does not change. The in-progress flag's `finally` is the same one the cancellation test (EC-19) drives.
- **An exception in `collect_messages` or `end_turn` (EC-16 a).** It takes the same `VidbyteSdkError` containment branch as the provider error that the AC-7 test drives. Forcing it would need a second fault injection into the feature itself.
- **Windows bash outliving a cancelled swarm (EC-20), concurrent edits to one file (EC-24), bash outside the workplace (EC-25), two swarms sharing one folder (EC-32).** These are stated limitations with no control to test.
- **A fork of a member agent asking for the member runtime.** The member agent is internal and built inside `arun`. A fork builds a plain `BaseAgent` with the same runtime type (spec INV-24), which `test_runtime_type_refuses_outside_a_swarm_without_calling_a_model` drives directly.
- **`runtime.py` and the actor runtime unchanged (INV-25, INV-26), and the catalog loading (INV-28).** The neighbour suites cover these: `tests/test_agent_tool_loop.py`, `tests/test_jev_compute.py`, `tests/multi_agent`, `tests/test_prompts_interface.py`, and the InfiniteMemory pack. S4 checks the diff.
- **Event volume at the default limits (EC-37).** There is no cap to test (Q-8 default). The property tests produce runs of tens of events.
- **`hypothesis`.** It is not a dependency; seeded `random.Random` schedules stand in for it.
