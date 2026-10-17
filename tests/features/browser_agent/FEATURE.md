# Feature: BrowserAgent — episodes, a pinned goal card, and fresh-context rechecks

## High-Level Feature Description

A developer hands one long browser task to `BrowserAgent` and names their browser MCP servers by role: ACTION servers drive the browser, SEARCH and FETCH servers read the web. The orchestrator never holds an ACTION tool. It hands each page-level job to a fresh worker through `run_episode`, and gets back one capped result card. Every worker of a run shares the same ACTION server process, so the browser session survives between episodes. Each episode is bounded by an action cap, a per-tool screenshot cap, a per-tool observation window, and a history trim. The original goal and its `done_when` criteria sit on a goal card at the top of every orchestrator call. The orchestrator can change only `plan`, `blockers`, and the append-only `progress`. A finish is accepted only after a recheck agent, which sees only the goal, the criteria, and the progress, agrees. A run whose rechecks keep finding no new progress stops as `goal_stalled`. Once the orchestrator's stored history passes its cap, it is rebuilt to the newest call group. Events, one usage ledger, and the `agent.response` record let the developer watch and measure the run.

If this feature regresses, the failure is usually silent. Screenshots and page dumps flood the orchestrator. The goal drifts or is overwritten. A run declares victory without meeting `done_when`, or loops until `max_iterations`. One page burns the whole budget. A worker submits a form on its own. A key leaks into a log. A crashed worker takes the whole run down. The tests here make each of those failures loud.

## Contract

- `from vidbyte import BrowserAgent, BrowserAgentSettings, BrowserServerSettings, BrowserEvent` works. `BrowserAgentRuntime` also imports from `vidbyte.agents` and `vidbyte.agents.browser`. The agent is built only from a validated `BrowserAgentSettings`, and every server from a validated `BrowserServerSettings`.
- A preset server's required keys must be non-blank in its own `env`. `os.environ` never satisfies the check. No key text appears in a settings `repr`, a settings error, `repr(agent.tools)`, an event, `agent.response`, or a model call.
- Every orchestrator call offers the developer's tools, the SEARCH and FETCH tools, `run_episode`, `patch_goal`, and `isDone`, and never an ACTION tool. Every worker call offers only the ACTION tools (plus the loop's internal `isDone`).
- Every `run_episode` call that is not cancelled returns one card text and records one `BrowserEpisodeResult`. A cap stop, a schema miss, or a worker error gives a `stuck` card. A cap stop or schema miss carries the exact action count and the newest successful observation as evidence. Cancellation propagates and records no card.
- `patch_goal` replaces `plan` and `blockers` and appends one `progress` item per non-blank line. Any other section, an over-cap text, or a progress line that no longer fits is refused with a model-visible error, and the card is unchanged.
- A finish by final text or by `isDone` is accepted only on a `done` recheck, or when the recheck is unavailable (fail open). Otherwise one gap message is appended, the card shows the verdict and the gap, and the loop continues. Reaching `max_stalls` stops the run before its next model call with stop reason `goal_stalled` and the rendered card as output.
- Each run emits `run_started` first and exactly one of `run_finished` or `run_stopped` last, with sequence numbers 1..n. A sink `Exception` is recorded on `agent.response.event_errors`. A `BaseException` propagates.
- After a run that returns, `result.metadata["usage_rollup"]`, `agent.response.usage`, and `agent.get_usage()` are one roll-up of every agent's calls. An unpriced call raises `UsageAccountingError`.
- `BaseAgent(runtime="browser")`, a fork, and `Session` cannot run the agent.

## Actors / Callers

SDK callers that build `BrowserAgent` and call `run`, `arun`, `get_usage`, and read `agent.response`. The orchestrator model, which calls `run_episode`, `patch_goal`, the SEARCH and FETCH tools, and `isDone`. The episode workers' model, which calls the ACTION tools and returns a `BrowserEpisodePayload`. The recheck and done-when agents' model. The developer's `on_event` sink. The browser MCP server processes. `vidbyte.sessions.Session`, which must refuse the agent.

## Inputs and Preconditions

A `BrowserAgentSettings` with at least one ACTION server, keys in each server's `env`, and caps within the bounds in spec §9.3. The tests use fake keys (`fc-test-only-…`, `sk-test-BROWSER-SECRET-…`) that exist only to be searched for, scripted model runners, and a fake transport factory. The settings and the fake replies use the snippet's priced `gpt-5.4-mini` (spec r4); a model with no pricebook row would make every run raise `UsageAccountingError`.

## Observable Outcomes

The model calls each agent receives (its `prompt`, `system`, `messages`, offered tool names and schemas), tool results as the next call's tool messages, the requests each fake server received and the env and timeout it was built with, `reply.content` and `reply.metadata["stop_reason"]`, `agent.response` (goal card, episodes, rechecks, rebuilds, usage, event errors), the events the sink received in order, `agent.get_usage()`, and the raised `ConfigurationError`, `UsageAccountingError`, `ToolRegistrationError`, `OutputSchemaViolationError`, or `CancelledError`.

## State Transitions

Goal card: built at run start (with `done_when` given or derived) → patched (`plan`, `blockers` replaced; `progress` grown) → re-rendered with each recheck verdict and gap. Stall count: 0 → +1 on a `stalled` verdict or a `continue` with unchanged progress → reset by any other recheck → stop at `max_stalls`. Orchestrator history: grows → rebuilt to the newest group when over `BROWSER_HISTORY_MAX_TOKENS` and older messages exist. Servers: queued at construction → started by the first run → closed after each sync run, or kept across `arun` calls on one loop.

## Invariants

- The orchestrator never holds an ACTION tool and never receives a screenshot. Episode output reaches it only as the capped card text.
- A worker never makes more than `max_actions` browser calls, never executes one screenshot tool more than `max_screenshots` times, and never sends more than `keep_observations` full results per tool.
- Every non-cancelled episode yields exactly one card and one record.
- `card.goal` and `card.done_when` never change during a run, and `progress` only grows.
- The card appears exactly once in every orchestrator call, as it stands after the latest patch, episode, recheck, and refusal.
- A recheck sees only the goal, the criteria, and the progress, with no orchestrator history and no tools beyond the loop's `isDone`.
- No code path submits, sends, or pays. `ready_to_submit` is recorded only.
- Building the runtime has no side effects. Each run starts from a clean conversation and a fresh record, and an earlier record never changes.
- No prompt leaf states a number.

## External Dependencies

The model runner (fake, at `BaseAgent._runner_for_model`); the MCP stdio transport (fake, at `vidbyte.tools.mcp.attach.McpStdioTransport`); everything else is real: `BaseAgent`, the linear loop, `McpAttachableMixin`, `attach_mcp_server`, `McpClient`, `McpToolBridge`, `MessageHistoryCompactionMiddleware`, `ContextCompactionEngine`, `ToolSettings`, the prompt catalog, the pricebook, and the usage tracker. Ordering checks yield with `asyncio.sleep(0)` only.

## Known Failure Modes

Each line is *input + state → wrong output if unguarded*, with the test that catches it.

- The §4 snippet stops working as printed (`test_section_4_snippet_prints_events_answer_stop_reason_and_progress`).
- A dict or a string is accepted in place of `BrowserAgentSettings` (`test_a_non_settings_object_is_refused_naming_its_type`).
- `BaseAgent(runtime="browser")`, a fork, or a `Session` runs the agent without its settings and collaborators (`test_runtime_type_resolves_and_refuses_outside_its_agent`; `test_session_refuses_the_agent`).
- A public name, enum value, constant, default, or prompt leaf drifts from the spec, or a leaf states a number (`test_public_names_import_from_every_documented_path`; `test_enum_values_and_added_members_are_the_documented_strings`; `test_fixed_string_constants_are_the_documented_values`; `test_defaults_are_the_named_constants`; `test_prompt_family_has_exactly_the_nineteen_leaves_with_their_placeholders_and_no_digits`).
- A preset name is stored as a string instead of the registered definition, or `env` can be changed after validation (`test_a_preset_is_stored_as_its_registered_definition_and_env_is_read_only`).
- The runtime overrides more of the loop than NFR-3 allows, or the package outgrows its budget (`test_runtime_overrides_exactly_the_five_documented_methods`; `test_new_package_stays_inside_the_complexity_budget`).
- `run_episode` counts against the orchestrator's `max_tool_calls` → a small tool budget stops the run after one episode (`test_run_episode_is_internal_so_it_does_not_spend_the_orchestrators_tool_budget`).
- Servers start under generic names, out of role order, with another server's env, or with the default timeout (`test_named_servers_names_every_server_by_role_in_role_order`; `test_servers_start_under_their_role_names_with_their_own_env_and_timeout`).
- A required key present only in `os.environ` is accepted → the server starts unauthenticated, because the child-env allowlist never passes it (`test_a_required_server_key_is_refused_unless_it_is_in_env_even_when_os_environ_has_it`).
- A blank key is accepted, or the refusal quotes a value (`test_a_blank_required_key_is_refused_without_quoting_any_value`).
- A developer-built preset definition that differs from the registered one is accepted → the registered preset of that name runs instead, silently (`test_each_invalid_server_setting_is_refused_naming_its_field`).
- No ACTION server, one preset or command in two roles, an `async def` sink, a reserved tool name in `settings.tools`, or an unknown model accepted at construction (`test_each_invalid_agent_setting_is_refused_naming_its_field`).
- A key in a settings `repr`, a settings error, `repr(agent.tools)`, an event, `agent.response`, or a model call (`test_keys_never_appear_in_a_settings_repr_or_a_settings_error`; `test_keys_never_reach_tools_events_the_response_or_any_model_call`).
- An ACTION tool offered to the orchestrator, or SEARCH, FETCH, or orchestrator tools offered to a worker; worker and orchestrator rules swapped (`test_orchestrator_never_holds_action_tools_and_workers_hold_only_them`; `test_each_role_is_enforced_by_the_catalog_not_by_the_prompt`).
- Each episode starts its own browser process → logins, cookies, and tabs lost between episodes (`test_every_episode_of_one_run_uses_the_same_action_server_process`; `test_sync_runs_get_their_own_servers_and_async_runs_on_one_loop_share_them`).
- The action cap is not applied, or a fourth call in the same turn still runs (`test_action_cap_stops_the_worker_and_returns_a_stuck_card_with_evidence`; `test_a_call_past_the_action_cap_in_the_same_turn_is_not_executed`).
- A cap-stopped worker's card is built with no evidence or a guessed action count → the orchestrator cannot tell what page state the worker reached (`test_action_cap_stops_the_worker_and_returns_a_stuck_card_with_evidence`).
- A second screenshot ends the episode instead of being denied in context; the marker is compared case-sensitively; a denied call does not count as an action (`test_a_second_screenshot_is_denied_in_context_and_the_worker_finishes_its_card`; `test_screenshot_cap_counts_each_screenshot_tool_case_insensitively_and_spares_other_tools`).
- Older observations are sent whole, or the newest one is cut (`test_older_observations_are_cut_and_the_newest_is_whole`).
- The worker history is not trimmed, or the trim splits a call from its result → the worker's calls grow without bound or fail at the provider (`test_worker_history_stays_within_its_token_cap_with_whole_call_groups`).
- A worker's free-text reply or provider error kills the run instead of becoming a `stuck` card (`test_a_free_text_worker_reply_becomes_a_stuck_card_with_evidence`; `test_a_worker_provider_error_becomes_a_stuck_card_and_the_run_continues`).
- Cancellation during an episode is swallowed into a card (`test_cancelling_during_an_episode_propagates_and_records_no_card`).
- `ready_to_submit` triggers an action, or a `submit` setting or argument exists (`test_ready_to_submit_is_recorded_and_nothing_acts_on_it`; `test_run_episode_and_patch_goal_schemas_follow_the_documented_contract`).
- A recipe includes denied or failed calls, or an event carries a typed password (`test_a_done_card_records_the_recipe_of_successful_calls_and_the_event_names_only_the_count`; `test_a_failed_browser_call_counts_as_an_action_but_not_a_recipe_step`).
- An oversized worker card reaches the record or the orchestrator uncapped (`test_an_oversized_worker_card_is_capped_on_the_record_and_in_the_orchestrator_view`).
- Two `run_episode` calls in one turn run concurrently on one browser (`test_two_episodes_in_one_turn_run_one_after_the_other_in_call_order`).
- Worker transcripts or tool output reach the orchestrator beside the card (`test_only_the_card_text_reaches_the_orchestrator`).
- Workers bypass the developer's `permission_policy` (`test_the_developer_permission_policy_binds_every_worker`).
- `patch_goal` rewrites `goal` or `done_when`, replaces `progress`, or the card in the next call is stale or duplicated (`test_patch_goal_changes_only_plan_progress_and_blockers_and_every_call_shows_the_latest_card`; `test_patch_matches_a_reference_model_over_random_sequences`).
- An over-cap patch is partly applied, or a full progress section accepts a line silently (`test_an_over_cap_patch_is_refused_with_the_patch_refused_leaf_and_changes_nothing`; `test_a_progress_line_that_no_longer_fits_returns_progress_full_and_changes_nothing`).
- User text with `{braces}` goes through `str.format` → a `KeyError` or a changed goal (`test_user_text_is_rendered_verbatim_even_when_it_looks_like_a_format_string`).
- A recheck sees the orchestrator's history or tools → it grades the transcript, not the goal (`test_a_recheck_sees_only_the_goal_done_when_and_progress`).
- A `continue` verdict ends the run, or appends no gap, or the next call's card lacks the verdict (`test_a_refused_finish_appends_one_gap_message_and_the_next_call_shows_the_verdict`).
- Periodic rechecks run at the wrong count or end the run (`test_periodic_rechecks_follow_recheck_every_and_never_end_the_run`).
- A run whose finishes keep failing with no new progress loops until `max_iterations`; a stall stop makes one more model call (`test_stalls_stop_the_run_before_another_model_call_with_the_card_as_output`; `test_stall_count_matches_the_d14_rule_over_random_recheck_sequences`).
- `done_when` is derived even when given, after the first orchestrator call, or a failed derivation starts browsing anyway (`test_done_when_is_derived_once_before_the_first_orchestrator_call_only_when_not_given`; `test_a_failing_done_when_call_stops_the_run_before_any_browser_action`).
- A failed recheck blocks the finish (`test_a_failing_or_off_schema_recheck_fails_open`).
- The orchestrator history is never rebuilt, is rebuilt to the wrong group, loses the card or the task, or a no-op check is counted (`test_history_over_the_cap_after_a_tool_iteration_is_rebuilt_to_the_last_exchange`; `test_history_over_the_cap_at_a_refused_is_done_keeps_that_turn_and_the_gap`; `test_a_single_group_over_the_cap_is_kept_whole_and_not_counted`).
- A raising sink breaks the run, or cancellation from the sink is swallowed (`test_a_raising_sink_is_recorded_and_never_breaks_the_run`; `test_a_base_exception_from_the_sink_propagates`).
- A `max_iterations` stop ends without `run_stopped`, or event details span lines (`test_a_max_iterations_stop_ends_with_run_stopped`; `test_event_details_are_one_line_within_their_cap`).
- Worker, recheck, or done-when usage is missing from the roll-up, or an unpriced call returns quietly (`test_usage_is_one_rollup_that_counts_every_agent`; `test_an_unpriced_call_raises_usage_accounting_error`).
- An MCP tool named `patch_goal`, an ACTION server with no tools, or two servers with one tool name reach a model call (`test_a_reserved_name_on_an_mcp_tool_is_refused_before_any_model_call`; `test_an_action_server_without_tools_is_refused_before_any_model_call`; `test_duplicate_tool_names_across_servers_fail_the_attach_all_or_nothing`).
- Building the runtime starts a process or emits an event, or a second run changes the first run's record (`test_building_the_runtime_has_no_side_effects`; `test_each_run_starts_clean_and_never_changes_an_earlier_record`).

What an easy generated test would miss: a cap checked only by the model call count instead of the requests the server received; "no leak" checked on the final reply instead of on every orchestrator call; the card checked once instead of exactly once in every call; a stall rule checked without the progress-changed reset; a rebuild checked without proving the history was over the cap before it.

## Historical Regressions

None yet. The pack was written red before the implementation, from spec r3 (S2). Spec review rounds shaped several tests: r1 R-1 (the rebuild, AC-22), r1 R-2 and r2 R-2 (the stuck card with evidence, AC-7 and EC-12), r1 R-3 (the card after a refused finish, AC-13), r1 R-4 (`progress_full`, AC-32), r1 R-6 (the per-tool window and the worker trim, AC-31), and r2 R-3 (the rebuild at a refused `isDone`, AC-33).

## Test Suite Map

- `test_browser_agent_acceptance.py` — the §4 snippet as written, one browser process per run, sync and async lifetimes, a side-effect-free runtime build, and a clean record per run. Start here for a caller-visible regression.
- `test_browser_agent_contract.py` — exports, enum values, constants, the prompt family, the runtime registry and refusal, the session refusal, the overridden hooks, tool schemas, role naming, and the complexity budget.
- `test_browser_agent_settings.py` — required and blank keys, invalid server and agent settings, key secrecy in settings, the type check, defaults, and preset storage.
- `test_browser_agent_episode.py` — tool split, caps, observation window, worker trim, stuck cards, cancellation, `ready_to_submit`, recipes, card caps, order, and the permission policy.
- `test_browser_agent_goal.py` — `patch_goal`, the card in every call, refusals, the full progress section, verbatim text, and the seeded property tests.
- `test_browser_agent_recheck.py` — the fresh recheck, refused finishes, periodic rechecks, the stall stop, derived `done_when`, fail open and fail closed.
- `test_browser_agent_rebuild.py` — the orchestrator history rebuild on both paths and the single-group case.
- `test_browser_agent_observability.py` — events and the sink, usage, run-time key secrecy, server names and env, reserved MCP names, an empty ACTION server, duplicate tool names.
- `browser_agent_fixtures.py` — the scripted model, the fake servers, builders, and readers every module uses.

Run: `PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q` from the repository root.

## Omitted Testing Strategies

- Live providers and real MCP servers: offline by spec §13; the runner and the stdio transport are the only fakes, and the OS keyring holds live keys.
- AC-29 (the three `AgentStopReason` tests and the infinite and jev packs pass unchanged): those existing tests are the proof; a copy here would pass before the feature exists.
- Behaviors owned by the shared MCP and compaction code (INV-28: image placeholders, the client's 8,000-character cut, all-or-nothing attach, the sliding window itself): pinned by `tests/test_mcp_bridge.py` and `tests/test_mcp_attachment.py`. This pack checks only how the feature uses them.
- A server command that fails its handshake (EC-9), a server that dies mid-run (EC-10), and a browser call that times out (EC-28): shared MCP attach and client behavior, or a slow fake that would need wall-clock time. The timeout value itself is checked.
- Overlapping `arun` calls on one agent (EC-21), an explicit `system=` option (EC-24), a click on a submit button despite the rules (EC-29), and vendor-billed MCP usage (EC-30): accepted limitations with nothing to assert.
- The message order after a refused final-text finish (EC-36): a loop limitation on main shared with `JevRuntime`; the tests check the gap message and the card, not that order.
- Stress at the default caps (30 actions, 60,000-token rebuild): the caps are reached with small settings values or with the §13 recipes.
- Hypothesis-style property tests: `hypothesis` is not a dependency; the patch and stall rules are checked against a reference model over seeded `random.Random` sequences.
- Whether a finish recheck resets the `recheck_every` counter, and how whitespace inside a progress line is normalized: not specified, so not tested.
