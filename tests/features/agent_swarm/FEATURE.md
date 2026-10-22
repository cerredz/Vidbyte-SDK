# Feature: AgentSwarm — agents with one shared prompt that run their tools, message each other freely, and compact their own histories

## High-Level Feature Description

A developer names two or more agents, each with only a name, a provider and a model. The developer points them at one shared folder, optionally picks one web-search provider with its key, and calls `await AgentSwarm(settings).arun(goal)`. Every agent receives the same sectioned system prompt and the same goal, and works with `bash`, `grep`, `read_lines`, `write_text`, `patch_file`, `message`, `compact`, the selected search tool, and the loop's `isDone`. An agent can `message` any agent, itself included, without waiting. A message reaches a busy agent between its tool calls as a new user message and wakes an idle agent. An agent compacts its own history when it calls `compact`, or automatically when the provider reports a prompt at or above the trigger. The swarm ends once no agent is working (QUIET, MAX_TURNS, FAILED), when the swarm-wide token budget is reached (MAX_TOKENS), or at the time limit (TIMEOUT). It returns the full ordered tuple of events, twenty-four kinds in all.

Under the hood, each agent runs one long-lived ordinary SDK loop for the whole swarm. One `AgentSwarmRuntime` per run coordinates the agents through its entry points (`post_message`, `collect_messages`, `end_turn`, `record_tool_call`, `record_tool_outcome`, `record_model_call`, `record_model_error`, `record_history_trim`, `request_compaction`, `record_compaction`). Three middleware sit in every member, in this order: the provider-boundary trim, the turn middleware, and the observer that records model calls, model errors and tool outcomes and refuses every model call once the swarm is stopping. A compaction rewrites the member's live history only in `AgentSwarmMemberRuntime._after_tool_iteration`, through the SDK's own `ContextCompactionEngine` with a summarizer that calls the member's own runner.

The feature is a mailbox protocol with a budget and a history rewrite, so its regressions look like the classic ones of distributed systems and of context management:
- a lost wake-up, which leaves a message sitting with an idle agent while the swarm ends QUIET;
- a message that is neither delivered nor marked undelivered, or both;
- a stop decision that lets one more paid model call through, or that leaves a parked agent waiting forever;
- a compaction that cuts a tool call from its result, lands after the inbox message, loses the goal, or silently drops the history when the summary call fails;
- a budget that never counts the compaction side call;
- an event stream with gaps or repeats, fields set on the wrong kind, or deliveries to the callback out of order or twice at once.

Each of these makes the swarm's data untrustworthy without any visible error. The tests here exist to make each one loud.

## Contract

- **Imports.**
  - `from vidbyte import AgentSwarm, AgentSwarmMember, AgentSwarmSettings, AgentSwarmEventKind, AgentSwarmStopReason, AgentSwarmWebSearch` works.
  - `AgentSwarmSettings` is one class, defined in `vidbyte.lib.dataclasses.agent_swarm` and re-exported by `vidbyte`, `vidbyte.agents` and `vidbyte.agents.agent_swarm` (AC-21).
  - `vidbyte.lib.enums` exports `AgentSwarmWebSearch`, `AgentSwarmCompactionTrigger`, `AgentSwarmAgentState` and `AgentSwarmFolderState`.
  - `vidbyte.tools.toolsets.AgentSwarmTools.search_tool_for(web_search, api_key)` builds the selected provider's search tool with the key inside its client.
  - `AgentRuntimeType.AGENT_SWARM_MEMBER` resolves to `AgentSwarmMemberRuntime`, which refuses to build outside a swarm.
- **Settings and the goal.**
  - `AgentSwarmMember(name, provider, model_name)` has no prompt of its own.
  - `AgentSwarmSettings` validates every field when built: 2 to 500 members with distinct names, a workplace that is not a file, `max_turns` of at least the number of members, `max_tokens` of at least one, `timeout_seconds` in (0, 2,592,000], a `web_search` that is an `AgentSwarmWebSearch` value with its key (and no key without it), a callable `on_event`, and model keys that match the members' providers (AC-19, AC-20, INV-18).
  - A refusal is a `ConfigurationError` whose message and `details["field"]` name `AgentSwarmSettings.<field>`, never quote a key, and come before any folder is created.
  - `AgentSwarm.arun` and `AgentSwarmRuntime.arun` refuse a blank or non-text goal the same way (INV-40).
- **One run.**
  - Each `arun` prepares the workplace folder (`AgentSwarmWorkplace.prepare()` returns whether it created it), builds one fresh `AgentSwarmRuntime(settings, root, workplace_created=...)`, and returns an `AgentSwarmResult(stop_reason, events, replies, event_error_types)`.
  - A second concurrent `arun` on one `AgentSwarm` is refused. An `AgentSwarmRuntime` runs only once.
- **What each agent sees.**
  - Its model sees the goal as the prompt of every call, never in `messages`.
  - Its tools are exactly `bash`, `grep`, `read_lines`, `write_text`, `patch_file`, `message`, `compact`, the selected search tool when any, and `isDone`, in that order (INV-38, AC-2).
  - Its system prompt is the nine section leaves (web search only when selected) joined by blank lines, then the loop's agentic-loop prompt. Every member gets the same template; only its own name, its peers, the workplace and the search tool name are substituted (INV-1).
- **Messages.**
  - `message(to, text)` returns as soon as the message is queued. Its `to` schema has no `enum`; its description names every member.
  - Exactly two inputs are refused, as tool errors with one `message_refused` event: a name that is not a member (any non-string included) and blank text (INV-5, AC-4, EC-1).
  - A message to oneself is queued like any other (AC-3, EC-2, EC-3).
  - A message to a failed or exited member, or sent after the stop is decided, is a successful call recorded as `message_sent` then `message_undelivered` (INV-6, AC-5, EC-4).
  - Every `message_sent` gets exactly one later `message_delivered` or `message_undelivered` (INV-7, AC-7).
- **Ending.**
  - The stop reason is decided once, in one block that records `swarm_stopping`, marks every still-queued message undelivered, and releases every parked agent (INV-12).
  - QUIET, MAX_TURNS and FAILED are decided when nobody works; MAX_TOKENS in the block that records the `model_called` crossing the budget; TIMEOUT after the task group ends on the time limit, after `agent_cancelled` for every member still working.
  - After the decision no model call starts: the observer refuses `before_model_call` (INV-13, AC-9).
  - Every agent ends with exactly one of `agent_released`, `agent_cancelled`, `agent_failed`, `agent_exited` (INV-14).
  - `replies` holds each released agent's reply in member order.
- **Events.**
  - `workplace_prepared` is first, then `agent_created` per member, then `agent_started` per member (INV-17, INV-28, AC-2).
  - Events are numbered 1..N with no gap or repeat; exactly one `swarm_stopping` with the result's reason precedes the one last `swarm_ended` (INV-16).
  - Each kind sets exactly its own fields (INV-21, the twenty-four-row `_KIND_FIELDS` table).
  - Model calls (`model_called`, `model_error`), trims (`history_trimmed`), tool outcomes (`tool_result_truncated`, `file_changed`, `command_failed`) and compactions (`compaction`) are recorded per agent (INV-22…INV-27).
  - `on_event` (sync or async) is called once per event, in order, never twice at once; callback exceptions are contained and listed.
- **Compaction.**
  - `compact(focus?)` records a request and returns at once. The next `_after_tool_iteration` summarizes everything older than the kept newest groups through one side call on the member's runner, before any mail is appended (INV-30…INV-35, AC-16).
  - The automatic trigger is the member's last reported `total_prompt_tokens` at or above `AGENT_SWARM_COMPACTION_TRIGGER_TOKENS` (AC-17).
  - A failed summary call records `model_error`, keeps the history, and never fails the member (AC-18).

## Actors / Callers

- SDK callers who build `AgentSwarm(AgentSwarmSettings(...))` and await `arun(goal)`, optionally with an `on_event` callback.
- The model inside every member agent, which calls the swarm's tools.
- The member-side callers of `AgentSwarmRuntime`: the member loop (`collect_messages`, compaction), the turn middleware (`end_turn`, `record_tool_call`), the observer and trim middleware, and the `message` and `compact` tools.
- A plain `BaseAgent` or a fork that asks for `runtime="agent_swarm_member"`, and must be refused.

## Inputs and Preconditions

- Two to `AGENT_SWARM_MAX_AGENTS` members with distinct names that match `AGENT_SWARM_NAME_PATTERN`.
- A workplace path that is not a file.
- A model each member's provider can run, and `api_keys` that the providers accept.
- Optionally `web_search` with `web_search_api_key`, an `on_event` callable, `max_turns` of at least the number of agents, `max_tokens` of at least one, and `timeout_seconds` in (0, 2,592,000].
- The tests use `tmp_path` for every folder, a scripted model runner, a recording fake in place of the Tavily HTTP call, the real filesystem and real `asyncio`.
- `bash` cases need a POSIX bash (Linux CI) or Git for Windows bash locally.

## Observable Outcomes

- **What each agent's model was sent:** `prompt`, `system`, `messages`, the offered tool names, schemas and descriptions; a compaction's side call is one more recorded call whose `system` is the summarizer prompt, whose `prompt` is the transcript, and which offers no tools.
- **Tool results:** they arrive as tool messages in the next call.
- **The result:** `result.stop_reason`, `result.events`, `result.replies` and `result.event_error_types`.
- **Callback output:** the sequence of events the `on_event` callback received.
- **The disk:** the files under the workplace.
- **Errors raised:** `ConfigurationError` (with `details["field"]`), `AgentExecutionError` (with `__cause__`) and `asyncio.CancelledError`.

## State Transitions

**Per agent** (spec §9.1): `created → started (working) → (idle ⇄ working)* → released | cancelled | failed | exited`.
- `working → idle`: records `agent_idle`.
- `idle → working`: a message is accepted with budget left, or the turn ended with mail waiting and budget left; records `agent_woke`. With the budget spent it records `wake_refused` instead and stays idle.
- `working | idle → released`: the run returned after the stop was decided; records `agent_released`.
- `working | idle → cancelled`: the swarm's own cancel (the time limit); records `agent_cancelled` with `agent_state`.
- `working | idle → failed`: an SDK error or a stray cancel; records `agent_failed` and marks its inbox undelivered.
- `working → exited`: the run returned on its own before the swarm decided (for example `middleware_abort` from a raising recording hook); records `agent_exited` and marks its inbox undelivered.

**Per swarm:** `prepared → running → stopping(reason) → ended(reason)`. An `AgentSwarmRuntime` goes `New → Running → Ended` and is never reused.

**Per message:** `refused` (never queued), or `sent → delivered once`, or `sent → undelivered once` (recipient failed or exited, or the stop was decided before delivery).

**Per member history:** `growing → compacted (summary + kept newest groups)`, only between a tool iteration's results and its mail.

## Invariants

These are checked on every run by `assert_event_invariants` in `agent_swarm_fixtures.py`, the pack's oracle, and on random schedules by `test_agent_swarm_property.py`.

**Sequence and start**
- `sequence` runs 1..N in order; `elapsed_ms` is a whole number that never decreases.
- The run starts `workplace_prepared`, then `agent_created` per member in member order, then `agent_started` per member in member order.
- Exactly one `swarm_stopping` exists, with the result's stop reason; exactly one `swarm_ended`, last, with the same reason. Their agent and `workplace_prepared`'s agent are `""`; every other event names a member.
- Every field the `_KIND_FIELDS` table does not list for a kind keeps its default.

**Lifecycle**
- Each agent goes `created → working → (idle ⇄ working)* → one terminal event`. Tool calls, model calls, sends, refusals, deliveries, trims and compactions happen only while it is working. Only `message_undelivered` for it may follow its terminal event.
- `agent_released` comes only after `swarm_stopping`; `agent_exited` only before it.
- After `swarm_stopping` nobody wakes, nothing is delivered, and no wake is refused.

**Messages**
- A `message_sent` has `message_id == sequence`, names any member (the sender included), and carries non-blank text.
- Every `message_sent` has exactly one later `message_delivered` or `message_undelivered` with the same id, sender and recipient swapped. Deliveries to one recipient follow acceptance order.
- A send to a failed or exited recipient, or after the stop, is followed at once by its `message_undelivered`.
- A send to an idle recipient before the stop is followed at once by `agent_woke` (budget left) or `wake_refused` (budget spent). A turn end with mail waiting is followed at once by `agent_woke` (budget left) or by one `wake_refused` per waiting message.
- `swarm_stopping` is followed at once by one `message_undelivered` per message still queued for a running agent, in member order.

**Derived events**
- `tool_result_truncated`, `file_changed` and `command_failed` follow their agent's own `tool_called` for the matching tool; `file_changed` names an absolute path and the previous different writer of that path.
- `model_called` counts never go negative and the loop's model call count never decreases per agent; `compaction` follows its agent's own `model_called` for the side call.

**Turns, stop reasons and replies**
- Turns started (`agent_started` + `agent_woke`) never pass `max_turns`.
- QUIET, MAX_TURNS, FAILED: nobody is working at `swarm_stopping`. QUIET leaves nothing undelivered at the stop; MAX_TURNS spends the budget exactly and every message undelivered at the stop had its `wake_refused`; FAILED holds exactly when every agent failed or exited first.
- MAX_TOKENS: `swarm_stopping` directly follows the `model_called` that crossed the budget. TIMEOUT: every agent's terminal event precedes `swarm_stopping`.
- `replies` holds exactly the released agents, in member order; on QUIET and MAX_TURNS each reply is that agent's last `agent_idle` text.

**The callback**
- Except on TIMEOUT, the `on_event` callback received exactly `result.events`; on TIMEOUT an increasing subsequence that ends with `swarm_ended`. Never two deliveries at once.

## External Dependencies

- The local filesystem (real, under `tmp_path`).
- `bash` (a real subprocess); the timeout case lowers the bash tool's module-level timeout and runs a busy loop, so nothing waits on a timer.
- The model runner: the only model fake, patched at `BaseAgent._runner_for_model` so it reaches every member built inside `arun`, and the compaction side call through `AgentSwarmMemberAgent.call_model`. It stamps each response with the member's own provider and model and answers in that provider's own shape (OpenAI Responses items, Anthropic `tool_use` blocks, Gemini candidate `parts` with `usageMetadata`), so the loop builds each provider's real history and each provider's own parser reads the usage.
- Web search: `TavilyClient.search` (the HTTP boundary) is replaced by a recording fake; the swarm, the toolset and `TavilySearchTool` are real.
- The prompt catalog, the compaction engine, the middleware pipeline and `AgentSwarmEvents` (all real).
- `asyncio` (real). Ordering is controlled with `Gate`, `Signal` and events the `on_event` callback observes, never with timed sleeps. The one timed wait is in `test_event_time_counts_from_arun_not_from_building_the_runtime`, where the time between building the runtime and calling `arun` is itself under test.

## Known Failure Modes

Each line is *input + state → wrong output if unguarded*, with the test that catches it.

**The shared prompt and the tools**
- A member still gets a per-agent prompt, two members get different templates, the web-search section appears without a provider, a placeholder is left unformatted, or the loop prompt is not last (`test_every_member_gets_the_same_sectioned_system_prompt_then_the_agentic_loop_prompt`, `test_the_section_4_snippet_runs_as_written`).
- A leaf states a number, has fewer sentences than the spec asks, misses a thoroughness heading, or has a stray format field (`test_prompt_family_has_exactly_the_twenty_three_documented_leaves_with_their_fields`, `test_prompt_leaves_hold_no_digits_roles_or_examples`, `test_the_thoroughness_section_has_the_eight_headings_each_six_to_eight_sentences`).
- An agent misses `compact` or the search tool, holds them in the wrong order, or the `to` schema still declares an `enum` (`test_each_agent_holds_exactly_the_swarm_tools_and_a_message_schema_naming_every_agent`, `test_three_members_are_created_then_started_in_order_with_the_search_tool_before_isdone`).

**Messaging and wake-ups**
- A self-message is refused, or never delivered (`test_a_message_to_oneself_is_accepted_and_delivered_at_the_next_tool_iteration`, `test_a_self_message_sent_with_isdone_wakes_the_sender_at_once`).
- An unknown name or blank text is queued, recorded as sent, or records no `message_refused` (`test_a_refused_message_is_a_tool_error_queues_nothing_and_the_loop_continues`).
- A message to a failed peer is a tool error, or is queued and never resolved (`test_a_provider_error_fails_only_that_agent_names_its_cause_and_stops_its_mail`).
- A send to an idle peer with the budget spent records no `wake_refused`, or its message is never marked undelivered (`test_a_spent_turn_budget_stops_wakes_and_ends_max_turns_with_the_message_undelivered`).
- The lost wake-up, the blocking send, the misordered batch and the formatted text of r5 (`test_a_message_accepted_while_the_recipient_is_going_idle_is_never_lost`, `test_two_agents_messaging_each_other_mid_turn_never_deadlock`, `test_messages_queued_before_one_delivery_point_arrive_together_in_acceptance_order`, `test_message_text_reaches_the_recipient_whole_and_unformatted`).

**The budget and the stop path**
- A model call's usage is not recorded, or recorded with the wrong counts (`test_a_model_response_records_its_tokens_and_the_budget_grows_by_the_reported_total`).
- The budget stop lets another member make one more paid call, leaves a parked agent waiting, or records the stop late (`test_the_response_that_crosses_max_tokens_stops_the_swarm_in_its_own_block_and_runs_nothing_more`, `test_the_first_response_crossing_the_budget_leaves_no_further_paid_call`).
- A member in the middle of a long tool call when the stop is decided makes another model call, or is cancelled instead of released (`test_a_member_inside_a_long_tool_call_finishes_it_and_is_released_before_its_next_model_call`).
- A send whose response was in flight when the stop was decided is lost or delivered (`test_a_message_sent_after_the_stop_is_recorded_sent_then_undelivered`).
- A compact request still pending when the stop is decided makes a paid summary call after `swarm_stopping` (`test_a_compact_request_pending_at_the_stop_makes_no_summary_call_and_records_no_compaction`).
- The trim records `history_trimmed` for a model call that the observer then refuses after the stop, so the record shows work on a call that was never sent (`test_a_model_call_refused_after_the_stop_records_no_history_trimmed`).
- A model error that a retry middleware retries is not recorded, or the observer's hook changes the retry decision; AgentSwarm installs no retry, so the test appends one (`test_a_retried_model_error_records_model_error_and_the_agent_keeps_working`).
- A provider that reports no usage crashes the observer or trips the budget (`test_a_provider_that_reports_no_usage_records_zeros_and_never_spends_the_budget`).
- The time limit leaves an agent with no ending, fails it, or labels a parked agent as working (`test_the_time_limit_cancels_every_agent_and_returns_timeout`, `test_the_time_limit_labels_working_and_idle_agents_cancelled_and_fails_none`).
- A recording bug fails the agent instead of exiting it, or leaves its inbox unresolved (`test_a_turn_middleware_recording_bug_exits_only_that_agent_naming_the_middleware_abort`).

**Tool outcomes and the trim**
- A long history is sent untrimmed, or the trim records the wrong count (`test_each_model_call_the_trim_changes_records_history_trimmed_with_its_exact_drop`).
- A result over the cap reaches the model uncut, or its truncation is unrecorded or off by one at the cap (`test_a_tool_result_over_the_cap_records_its_exact_omitted_count_and_one_at_the_cap_records_none`).
- Two agents writing one file are not reported as a collision, or a relative `patch_file` path is a different key (`test_two_agents_writing_one_file_record_file_changed_naming_the_previous_writer`); an agent rewriting its own file names itself as the peer (`test_one_agent_writing_one_file_twice_records_file_changed_with_no_peer_both_times`); a refused write still reports a change (`test_a_refused_write_records_no_file_changed`).
- A non-zero exit or a bash timeout is silent, or a zero exit is reported (`test_bash_records_command_failed_for_a_non_zero_exit_and_none_for_zero`, `test_a_bash_command_that_runs_out_of_time_records_command_failed_timeout`).

**Compaction**
- `compact` rewrites the history mid-iteration, splits a tool call from its result, puts the inbox message before the summary, sends the summary call without the focus, or never counts the side call (`test_a_compact_call_summarizes_only_the_older_history_and_mail_follows_the_summary`).
- The automatic trigger fires below the threshold, never fires, or reads output tokens; an Anthropic prompt held in its cache buckets never triggers (`test_a_measured_context_at_the_trigger_compacts_automatically_and_one_below_does_not`, `test_anthropic_context_is_measured_as_all_three_input_buckets`).
- A request and the trigger in one iteration compact twice; two requests in one response compact twice (`test_a_pending_request_and_the_trigger_in_one_iteration_compact_once`, `test_two_compact_calls_in_one_response_compact_once_with_the_last_focus`).
- A failed summary call drops the history, fails the member, or swallows the mail (`test_a_failed_summary_keeps_the_history_delivers_mail_and_fails_nobody`).
- A blank summary aborts the compaction; nothing older still makes a paid call (`test_a_blank_summary_still_compacts_to_the_prefix`, `test_a_compact_request_with_nothing_older_changes_nothing_and_is_consumed`).
- A side call that crosses the budget loses its compaction or lets the member call the model again (`test_a_side_call_that_reaches_the_budget_completes_its_compaction_and_stops_the_swarm`).
- The summary side call's tokens never reach the member's `tokens_used` (`test_the_summary_call_tokens_are_added_to_the_members_tokens_used`).
- A size estimate that reads only `content` counts a Gemini member's `parts` history, and an OpenAI history whose text sits in `tool_calls`, as almost empty, so neither ever compacts and the trim becomes the mechanism (`test_a_gemini_member_at_the_trigger_compacts_its_parts_history_through_one_summary_call`, `test_an_openai_history_of_write_calls_only_compacts_at_the_trigger`).
- A prompt whose uncompactable part (system prompt, tools, goal) keeps the measured context at the trigger makes every tool iteration pay for another summary of the summary; or a fix makes a `compact` request wait for growth too (`test_automatic_compaction_waits_for_a_target_of_new_history_and_a_compact_request_does_not`).
- The estimate behind the trigger's fallback and the growth check reads only `content`: a Gemini member whose provider reports no usage never compacts, and one whose provider does compacts once and then leaves the 90,000-token trim to do the work (`test_a_gemini_member_compacts_again_each_time_its_parts_history_grows_by_the_target`, `test_a_gemini_member_whose_provider_reports_no_usage_compacts_when_its_estimate_reaches_the_trigger`).

**Runs, workplace, settings and events**
- The workplace's first event is missing or misreports whether the folder was created (`test_the_first_event_reports_whether_the_run_created_the_workplace`).
- A refused setting creates the folder or names no field; a web-search key leaks into a `repr`, an event, a model call or a refusal (`test_invalid_settings_are_refused_naming_the_field_and_creating_nothing`, `test_web_search_settings_without_a_key_with_a_dangling_key_or_an_unknown_provider_are_refused`, `test_web_search_key_never_appears_in_reprs_events_model_calls_or_errors`).
- An event of a new kind sets a field it does not own, or a result without its `swarm_stopping` is accepted (`test_event_records_enforce_the_per_kind_field_table`, `test_result_records_enforce_one_ordered_sequence_ending_in_swarm_ended`).
- Every r5 failure mode for concurrent runs, cancellation, the outbox and the callback keeps its r5 test in `test_agent_swarm_lifecycle.py`.

**What an easy generated test would miss:**
- concurrency "proven" by timing instead of a gate;
- a budget stop checked only by its stop reason, never by the scripted calls that were not answered;
- a compaction checked only by its event, never by the summary call's system, prompt and empty tool list, or by the next call's history;
- an Anthropic usage path that is never parsed as Anthropic because the fake stamps every response OpenAI;
- a size rule checked only on OpenAI text results, where `content` holds everything, never on Gemini `parts` or on call turns whose text sits in `tool_calls`;
- a TIMEOUT test where nothing was actually blocked;
- a failure test that only asserts `agent_failed` exists, not that it names the cause.

## Historical Regressions

None yet in v2. The r5 pack was written red from spec r3 of `docs/spec/agent-swarm/` and hardened by S4 mutants M2, M7, M21 and M22; those gap tests stay. This revision (spec `docs/spec/agent-swarm-v2/` r3) reverses these r5 decisions, and each test that pinned one was rewritten to the new value rather than removed:

| Reversed decision | Spec | Tests rewritten |
|---|---|---|
| Per-member `system_prompt` | FR-1, INV-1 | field lists, prompt order, §4 snippet, fixtures `member()` |
| Self and failed recipients refused | INV-5, INV-6, D-4 | `REFUSALS`, failure tests, property plans |
| `search_tool` setting, reserved names | D-17, D-18 | settings refusals, tool sets, budget-cap test |
| Caps 100 agents, 7 days, 500 turns, 1 hour | §8.5 constants | refusals, defaults |
| `prepare()` returns a `Path` | D-13 | workplace tests |
| Eight event kinds, four stop reasons | §8.5 | enum sets, event tables, exact event lists, oracle |
| Recording bug ends as `agent_failed` | INV-14, EC-12 | middleware-abort test |

The S4 review of the v2 implementation (`docs/spec/agent-swarm-v2/review.md`, spec r4) found defects the pack did not catch. Each now has a test, red until the S5 repair:

- **R-2:** the compaction size estimate read only `message["content"]`, so Gemini members and write-heavy OpenAI members never compacted. Tests: `test_a_gemini_member_at_the_trigger_compacts_its_parts_history_through_one_summary_call`, `test_an_openai_history_of_write_calls_only_compacts_at_the_trigger`.
- **R-9:** the trim recorded `history_trimmed` for a call refused after the stop. Test: `test_a_model_call_refused_after_the_stop_records_no_history_trimmed`.
- **R-6:** automatic compaction had no hysteresis, so a large goal made every iteration pay for a summary. Test: `test_automatic_compaction_waits_for_a_target_of_new_history_and_a_compact_request_does_not`.

It also found three lines the spec pins that could be deleted with the pack still passing (R-7). Each now has a test that passes on the shipped code and fails on its mutant: `compact_while_stopping` (`test_a_compact_request_pending_at_the_stop_makes_no_summary_call_and_records_no_compaction`), `self_writer_as_peer` (`test_one_agent_writing_one_file_twice_records_file_changed_with_no_peer_both_times`), and `side_call_tokens_not_added` (`test_the_summary_call_tokens_are_added_to_the_members_tokens_used`).

The S5 re-review of the repair (`review.md` R-20) found that half of the R-2 fix had no test: the estimate behind the trigger's fallback and the growth check could go back to reading only `content` (mutant `estimate_content_only`) with the pack still passing. Two tests now fail on that mutant: `test_a_gemini_member_compacts_again_each_time_its_parts_history_grows_by_the_target` and `test_a_gemini_member_whose_provider_reports_no_usage_compacts_when_its_estimate_reaches_the_trigger`.

## Test Suite Map

- `test_agent_swarm_acceptance.py` covers the §4 snippet as written, three members created and started in order with the web-search tool, a swarm that ends after one turn each, and the goal reaching every call verbatim. Start here for a caller-visible regression.
- `test_agent_swarm_messaging.py` covers mid-turn delivery, batching, wakes after a reply or `isDone`, mail waiting at turn end, mutual messages, the lost-wake-up race, self-messages, the two refusals, and text fidelity.
- `test_agent_swarm_lifecycle.py` covers the turn budget and `wake_refused`, the time limit and its labels, failures by provider error, tool exception and middleware abort, concurrent and repeated runs, cancellation, callback containment, the event outbox, and `tool_called` events.
- `test_agent_swarm_stop.py` covers `model_called`, `model_error`, the token budget stop, refused calls after the stop and the trim they no longer record, no summary call for a compact request pending at the stop, sends in flight at the stop, and missing usage.
- `test_agent_swarm_observer.py` covers `history_trimmed`, `tool_result_truncated`, `file_changed` (including one agent rewriting its own file) and `command_failed`.
- `test_agent_swarm_compaction.py` covers the `compact` tool, automatic compaction at the trigger (OpenAI and Anthropic usage, a Gemini `parts` history, an OpenAI history of write calls only), the wait for target-sized growth before a repeat automatic compaction (a Gemini `parts` history too), a Gemini member with no reported usage, the summary call and its tokens, failures and blank summaries, and a side call that crosses the budget.
- `test_agent_swarm_settings.py` covers the lib settings record: import identity, members without prompts, web-search settings, the generous limits, defaults, key secrecy and the layering rule.
- `test_agent_swarm_workplace.py` covers folder creation and preservation, `workplace_prepared`, a folder shared across runs, refused workplaces, path escapes, and goal checks.
- `test_agent_swarm_contract.py` covers exports, enums, the prompt family, the runtime registry and refusal, the exact tools, schemas and system prompt, settings validation and key secrecy, record validation for twenty-four kinds, and the complexity budget.
- `test_agent_swarm_property.py` covers seeded random schedules over two to four agents, self-messages and refusals included, checked against the oracle and against each agent's own transcript.
- `agent_swarm_fixtures.py` holds the scripted runner (provider-stamped and provider-shaped for OpenAI, Anthropic and Gemini, with multi-call steps), `Gate`/`Signal`, `EventLog`, the recording Tavily fake, a one-shot retry middleware, builders, transcript readers and the event oracle.

Run: `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q` from the repository root.

## Testing Strategies Selected

- **Example-based acceptance tests**, one or more per AC, each driving the real loop through a scripted runner and reading both the event record and what each model was sent. These are two independent views of the same run.
- **A reusable oracle** (`assert_event_invariants`) applied to every swarm run in the pack, extended to all twenty-four kinds, the four endings and the one-outcome-per-message rule.
- **Deterministic interleaving control.** A blocking Tavily fake holds an agent mid-turn. `Gate` makes two calls overlap. `Signal`s are set by the `on_event` callback when a state change happens inside the swarm.
- **Exact arithmetic from the constants.** Truncation, trim, trigger and budget cases derive every size from the spec's constants, with the value one below and at the bound, so an off-by-one fails.
- **Seeded property tests** (`random.Random(seed)`, no `hypothesis` dependency) over two to four agents, reconciled against the oracle and every agent's transcript.
- **Hang guards everywhere.** `run_swarm` bounds every `arun`; every `Gate`, `Signal` and blocking fake fails after `GUARD_SECONDS`.
- **Contract tests** on the static surface: exports, enum values, prompt leaves and their sentence counts, record validation tables, and the module budget.
- **Two deliberate seams besides the model runner.** The r5 fault injection (`AgentSwarmRuntime.record_tool_call` raising) drives AC-24. A one-shot retry middleware appended to the member's runtime middleware drives AC-10, because neither the member loop nor AgentSwarm installs a retry (spec r4 INV-23: without one, a member's first failed model call fails it); it only decides to retry and never touches the swarm.

## Omitted Testing Strategies

- **Live provider calls.** Offline by spec §13; the runner and the Tavily HTTP call are the only fakes.
- **Brave, Browserbase, Exa and Parallel at run time.** `search_tool_for` is checked for every provider statically; only Tavily runs inside a swarm, because the five tools share one construction path.
- **`max_iterations` and `tool_loop_limit` early exits (EC-13).** The member agent sets no loop guard, so no test can reach them; AC-24's `middleware_abort` drives the same `agent_exited` branch.
- **500 agents (EC-29, EC-30) and thirty-day runs (EC-31).** The bounds are checked at construction; a run at that scale adds no branch.
- **Provider acceptance of consecutive assistant messages (A-1, EC-35).** That is the provider's behaviour, not the swarm's; the test checks the shape the engine produces.
- **A stale `total_prompt_tokens` (EC-26).** Impossible by construction: every iteration starts with a model call.
- **`hypothesis`.** It is not a dependency; seeded `random.Random` schedules stand in for it.
