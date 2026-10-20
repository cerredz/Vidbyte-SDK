# Test plan: An optional USD spend cap that every agent's own loop enforces

Spec: `docs/spec/loop-spend-cap/spec.md` r3 · Framework: pytest 8.3.5 on CPython 3.11 (`py -3.11`) · Prior art copied: `tests/features/sdk_model_usage/test_nested_usage_bill.py` (the `HttpTransport.request` seam, patched with a callable instance), `tests/agent_test_support.py` (`bind_test_runner`, `OfflineTestAgent`), `tests/test_jev_usage_ledger.py` (the `TypeSafeProvider.run_decision` seam and `_answer`), `tests/test_multi_provider_agentic_grader.py` (the `ModalityDetector.create_runner` seam), `tests/features/infinite_memory_agent/infinite_memory_fixtures.py` (the `BaseAgent._runner_for_model` seam), `tests/test_pdj_stage_model_provenance.py` (`_ALLEGATIONS`, `_DEFENSES`, `_DECISIONS`)

All new tests are in `tests/features/loop_spend_cap/`. In the table, `<x>.py` means `tests/features/loop_spend_cap/test_loop_spend_cap_<x>.py`. Levels: **unit** = one record or policy class; **integration** = a real agent or runtime, the real `UsageTracker`, and the real ledger scope in `generate_reply`, with only the model wire scripted; **acceptance** = the §4 snippet through the root import and the gateway transport; **doc** = a check of a tracked text file. Every dollar figure is computed at test time from the live pricebook by `reference_cost` (it records the same scripted responses into a fresh `UsageTracker`), so a rate change never turns a test red, and exact-boundary tests compare identical floats.

## Coverage map

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | `acceptance.py` → `test_the_developer_snippet_prints_the_line_that_matches_the_run[cap, blind, finished]` | acceptance | The §4 snippet, run as written: spend ≥ $0.50 → it prints "finished", or a blind call prints the cap line, or more than one line prints | It could pass if the snippet were edited to fit. `SECTION_4_SNIPPET` is byte-identical to the spec's first python block (checked while writing). The wire must be called exactly once, and the cap case asserts the priced spend really is ≥ 0.5 |
| AC-2, EC-1, EC-2, EC-3, T-1 | `contract.py` → `test_settings_reject_each_invalid_cap_and_name_the_field[True, nan, inf, -inf, 0, -1, 5]`, `test_settings_accept_valid_caps_unchanged[1, 0.25, None, 5e-324, max float]` | unit | `nan` or `inf` is accepted → silently uncapped; `True` → $1; `"5"` → a raw `TypeError` mid-run | It could pass if any `ConfigurationError` were raised. The test matches the field name and `details["field"]`, and the accept cases prove the guard does not reject everything |
| AC-2, T-3 | `contract.py` → `test_cap_error_never_echoes_a_long_value` | unit | A 400-character string cap → the error message echoes it | It could pass if no error were raised at all; `pytest.raises` requires the error first |
| AC-3 | `contract.py` → `test_runtime_config_carries_the_cap_and_repr_shows_it`, `test_runtime_config_rejects_each_invalid_cap[7 values]` | unit | `to_runtime_config()` drops the cap, `repr` hides it, or `AgentRuntimeConfig` built directly accepts `nan` | The direct construction bypasses `AgentLoopSettings`, so only the config's own `__post_init__` can raise |
| AC-4, EC-25 | `runtime.py` → `test_a_tool_turn_that_reaches_the_cap_runs_none_of_its_tools` | integration | Call 2 brings spend to exactly C and asks for a lookup → the lookup runs (`>` instead of `>=`, or no CP3) and call 3 is sent | The cap equals the computed spend of calls 1 and 2, so it is not reached until call 2. The lookup from call 1 must run (`executed == [first]`) |
| AC-5, EC-12, INV-8 (CP2) | `runtime.py` → `test_a_plain_text_answer_that_reaches_the_cap_is_replaced_before_any_finish_work[finish, max_tokens_tie]` | integration | A plain-text answer reaches C → `review_finish`, `after_iteration` or a finish attempt still runs, or the tie reports `max_tokens` | Uncapped controls prove that the hooks do run (`["review_finish","after_iteration"]`, 1 finish attempt) and that the tie case does stop on `max_tokens` |
| AC-6, EC-13, D-11 | `runtime.py` → `test_a_finish_or_internal_tool_requested_after_the_cap_never_executes[isDone, launch_helpers]` | integration | Spend ≥ C when the model calls isDone or an internal launch tool → the tool runs (it skips the budget checks), or `before_tool_call` runs first | `LaunchLikeTool` carries `internal_agent_tool` metadata, so it takes the exempt path. The test asserts no hooks, no tool iteration and the model's text in `iteration_outputs` |
| AC-7, INV-8 (CP3) | `runtime.py` → `test_a_priced_operation_that_crosses_the_cap_stops_the_next_tool_in_its_turn[free_turn, max_tool_calls_tie]` | integration | A priced search's own operation cost reaches C → the next tool in the same turn runs, or the tie reports `max_tool_calls` | Without the operation cost, call spend alone is below C (C = call + operation). An uncapped control proves the lookup normally runs and the tie normally stops on `max_tool_calls` |
| AC-7, EC-15 (CP4) | `runtime.py` → `test_a_last_tool_that_crosses_the_cap_stops_before_the_after_tool_iteration_hook` | integration | The last tool in a turn crosses C → `_after_tool_iteration` (the compute checkpoint) still starts | The control shows one tool iteration and two calls. Capped, `after_iteration` must run and `_after_tool_iteration` must not (it is counted by a subclass that calls the real method) |
| AC-7, AC-15, INV-12 | `children.py` → `test_a_sub_agent_tool_that_spends_past_the_cap_stops_the_next_tool` | integration | A sub-agent run through `as_tool()` spends past C → its spend is invisible to the parent, so the next tool runs | The cap equals the parent's turn plus the helper's answer, so only the merged child spend reaches it. The bill must hold exactly two model calls, and `cost_usd == cap` |
| AC-15, INV-12, EC-14 | `children.py` → `test_concurrent_capped_children_each_keep_their_own_cap_and_the_parent_stops_on_their_total` | integration | Two capped children run at the same time (an `asyncio.Event` barrier, no sleeps) → a child reads its sibling's spend and stops, or the parent misses their total | Each child cap is 1.5 × one child's cost, so a shared ledger would stop the second child. Both children must end `final_response`, the parent must stop on `max_spend` and the lookup must not run |
| AC-8, EC-6 | `runtime.py` → `test_a_response_without_usage_stops_the_run_blind` | integration | A response with no usage → `cost_usd` looks like $0 and the run continues under a $1 cap | The uncapped control continues and runs the lookup. Capped, the exact unmeasured text, `unaccounted_call_count == 1` and `cost_measured is False` are all required |
| AC-9, EC-5 (run time) | `runtime.py` → `test_a_response_naming_an_unpriced_model_stops_the_run_and_names_it` | integration | Call 2 names a model the pricebook lacks → it is summed as free and the run continues | `assert_price_preconditions` fails loudly if the probe model ever gains a price. `cost_usd` must equal call 1's cost alone |
| AC-9, EC-8, EC-9 | `runtime.py` → `test_openrouter_spend_is_enforced_from_its_reported_cost[reported_cost_reaches_cap, no_reported_cost]` | integration | OpenRouter with a reported cost is not enforced, or OpenRouter without one is treated as measured | The two cases need opposite `cost_measured` values and different stop texts |
| EC-7, INV-4(b) | `runtime.py` → `test_a_failed_operation_recording_stops_the_run_blind` | integration | A tool's cost report raises → the ledger is CORRUPTED but the run continues | The uncapped control runs the lookup. Capped, the stop text must name "usage recording failed" |
| AC-10, INV-8, INV-17 | `runtime.py` → `test_a_cap_the_run_never_reaches_changes_nothing[final_response, is_done, max_iterations, max_tool_calls, max_tokens]` | integration (metamorphic) | A cap one float step above all spend changes the content, the stop reason, `iteration_outputs`, counters, tool states, model calls or cost | The control is asserted to end on each named stop, and the cap is `nextafter(total, inf)`, the tightest cap that must not stop. The rest of AC-10 is the unchanged existing suite (see Red run) |
| AC-11 | `refusals.py` → `test_a_capped_non_linear_runtime_is_refused[mcts_search, actor_model, actor_model_p2p, actor_model_broadcast]` | integration | A capped MCTS or actor runtime is accepted, and the cap is never checked | The exact message is asserted, and the same agent without the cap must construct |
| AC-12, EC-32 | `refusals.py` → `test_a_capped_non_text_model_is_refused_naming_its_runner_type` | integration | A capped image model is accepted | The runner type in the expected message is derived at test time, and the uncapped agent must construct |
| AC-13, EC-18 | `jev.py` → `test_a_capped_jev_agent_refuses_a_specialist_that_could_outspend_it[uncapped_specialist, one_step_above]`, `test_a_capped_jev_agent_accepts_specialists_capped_no_higher_than_it[equal, lower]` | integration | A specialist with no cap, or a cap one float step above JevAgent's, is accepted (or one equal to it is refused) | The boundary cases sit on both sides of `>`. The exact message and the three detail keys are asserted |
| AC-14, EC-17 | `jev.py` → `test_preflight_decision_spend_alone_stops_the_run_before_any_generative_call` | integration | Jev's preflight decision spend reaches C → the first generative call still happens | The cap equals the decision's computed cost. The decision runner must have run once and the generative runner zero times |
| AC-16, INV-15 | `copy_paths.py` → `test_a_checkpoint_carries_the_cap_and_an_uncapped_one_omits_it`, `test_a_yaml_loop_cap_reaches_the_built_agent`, `test_a_fork_with_a_max_iterations_override_keeps_the_cap`, `test_a_fork_tool_loop_override_keeps_the_parents_cap` | integration | A copy path rebuilds `AgentLoopSettings` field by field and drops the cap | Each test reads the cap from the resulting agent's runtime config, not from the input. The fork tool runs for real against a recording parent |
| AC-16, EC-28, T-2 | `copy_paths.py` → `test_the_fork_tool_refuses_any_model_supplied_cap[raise, lower, clear]` | integration | The model raises, lowers or clears its own cap through `fork_conversation` | The exact tool error text is asserted, and the schema must not list the field |
| EC-4, T-1 | `copy_paths.py` → `test_a_yaml_loop_cap_is_validated_like_the_keyword[.nan, .inf, 0, -1, "5", true]` | integration | A YAML cap of `.nan` or `"5"` loads | It matches `AgentLoopSettings\.max_spend_usd`. Today's loader raises "unsupported field", which does not match |
| AC-17, INV-10 | `failure_routing.py` → `test_a_cap_stop_routes_as_one_exhausted_resource_failure` | integration | A `max_spend` reply falls through to `runtime.error`, or records extra details | The reply comes from a real capped run, not a hand-built dict. Exactly one Failure, with exact code, status, disposition, phase, source and details |
| AC-18, INV-10 | `failure_routing.py` → `test_a_cap_stop_counts_as_a_budget_stop` | integration | The efficiency eval reports a cap stop as "did not stop on budget" | A non-budget control must report True |
| AC-19, INV-2 | `contract.py` → `test_cost_measured_follows_inv2_for_every_combination[16 cases]`, `test_empty_rollup_is_measured_although_cost_is_not_complete`, `test_cost_measured_is_derived_and_read_only` | unit | Any one of the four conditions is ignored; an empty rollup reads as blind; the flag is a stored field that can drift | All 16 combinations are built through the real tracker, not hand-made rollups. The read-only check also asserts it is not a dataclass field |
| AC-20 | `jev.py` → `test_a_continuation_budget_extension_never_lifts_the_cap` | integration | A Jev continuation's budget extension drops or replaces the cap | The uncapped control proves the extension really grants `max_iterations: 1` and reaches "final". Capped, the run stops on `max_spend` with both outputs |
| AC-21, INV-16, D-14 | `acceptance.py` → `test_the_cap_never_reaches_the_model` | acceptance | The rendered system prompt or request mentions `max_spend` or the cap value | The cap 0.4321 is distinctive, and the capped request's instructions must equal the uncapped ones exactly |
| AC-22, EC-16, EC-24, INV-8 (CP1) | `runtime.py` → `test_spend_after_the_last_tool_check_is_caught_at_the_next_iteration_before_max_iterations` | integration | The cap and `max_iterations` are both exhausted at CP1 → the stop reports `max_iterations` | The control stops on `max_iterations`. The spend that reaches C is recorded inside `_after_tool_iteration`, so only CP1 can catch it. The metadata key set equals that of the control's budget stop |
| AC-23, EC-21 | `run_ending.py` → `test_reflexion_never_reflects_on_an_attempt_the_cap_stopped`, `test_a_reflection_that_reaches_the_cap_stops_the_next_attempt_before_its_first_call` | integration | Reflexion reflects on a capped attempt, or starts a second attempt after a reflection reached C | The uncapped control makes 3 calls and is "fixed". Capped (ii) needs exactly 2 calls and 1 reflection |
| AC-24, INV-21 | not written here (see the omitted list) | — | — | — |
| AC-25, INV-20, EC-19 | `jev.py` → `test_an_unpriced_call_still_fails_closed_after_the_cap_stops_the_loop` | integration | The cap stop hides Jev's fail-closed `UsageAccountingError` | The control raises too, but only after running the lookup. Capped, it must raise with `details["unpriced"]` naming the model, with the lookup never run and one call |
| AC-26, FR-10 | `docs.py` → `test_the_agents_readme_has_a_spend_cap_section_naming_what_a_caller_reads`, `test_each_named_doc_mentions_the_cap[5 docs]` | doc | The docs never name the cap, its stop reason or its failure code | Names are checked inside the Spend Cap section, not anywhere in the README. The vocabulary check requires one line with both names |
| AC-27, EC-39 | `refusals.py` → `test_codex_refuses_a_capped_loop_through_its_existing_field_list` | integration | A capped `CodexHarnessAgent` is accepted | Checks the error type, `failure_code`, the `__cause__` type and the field name; the uncapped loop is unaffected |
| AC-28, EC-22 | `run_ending.py` → `test_a_capped_producer_is_returned_unreviewed[independent_critic, prosecutor_defender_judge]` | integration | The critic or PDJ reviews a capped producer and spends again | The uncapped control is reviewed. Capped, there is 1 call and no review metadata key |
| AC-28, EC-23 | `run_ending.py` → `test_the_grader_returns_a_capped_trial_without_grading` | integration | The grader grades a capped trial, or replaces its stop text | The uncapped control grades exactly once. Capped, the grader is called zero times and the output is the reached text |
| AC-29 (i), EC-33 | `run_ending.py` → `test_a_capped_worker_blocks_its_task_without_retry` | integration | A capped worker reply parses as done or as a retryable failure | The exact `TaskBlocker` is asserted, including `retryable=False` |
| AC-29 (ii), EC-42 | `run_ending.py` → `test_a_capped_manager_phase_is_not_retried_as_a_parse_failure` | integration | A capped manager phase is re-sent as a parse retry on a fresh fork | The exact message and details are asserted, with `attempts == 1`, one plan call and one phase agent created |
| AC-29 (iii) | `run_ending.py` → `test_a_capped_infinite_memory_generator_is_failed_and_never_verified` | integration | InfiniteMemory verifies a capped generator's partial answer | The uncapped control calls the verifier once; capped, it is called zero times |
| AC-30 (i), (ii), INV-13 | `refusals.py` → `test_a_capped_agent_with_an_unpriced_configured_model_is_refused_naming_each_one[unpriced_primary, unpriced_fallbacks_in_chain_order]`, `test_a_capped_parent_cannot_fork_a_child_onto_an_unpriced_model` | integration | An unpriced primary or fallback is accepted, or is named out of chain order, or a fork escapes the check | The fallback chain mixes unpriced and priced models in a non-sorted order, so the exact message pins chain order |
| AC-30 (iii) | `refusals.py` → `test_a_capped_agent_whose_whole_chain_is_measurable_constructs[priced_primary, priced_fallback, openrouter_primary, openrouter_fallback]` | integration | A priced chain or OpenRouter is refused | Paired with the refusal tests above, so a guard that refuses everything fails here |
| AC-31 (i), EC-20 | `run_ending.py` → `test_a_capped_reply_runs_no_queued_prompt` | integration | Prompts queued by `enqueue_prompts` or by the model's `run_prompts_sequentially` run after a cap stop | `queued_prompts_truncated == 2` requires the drain to see and drop them; one model call only |
| AC-31 (ii), INV-11 | `run_ending.py` → `test_a_drained_reply_that_hits_the_cap_ends_the_drain` | integration | A drained reply stops on the cap and the drain continues | The uncapped control runs all 3 queued prompts |
| AC-32, EC-40 | `run_ending.py` → `test_a_capped_reply_with_an_output_schema_raises_with_the_cap_stop` | integration | A cap stop with an output schema returns a reply, or the error hides the stop reason, or the queued prompt runs | The scripted second response is valid JSON for the schema, so a run that continued would satisfy it |
| INV-4, INV-9 | `contract.py` → `test_stop_output_is_reached_at_exactly_the_cap_and_not_one_step_below`, `test_stop_output_reports_reached_before_blind`, `test_stop_output_names_every_blind_cause_in_spec_order`, `test_stop_output_names_a_lone_cause_without_separators[corrupted, operation]` | unit | `>` instead of `>=`; a blind check before the reached check; causes out of order or unsorted; separators around a lone cause | The boundary uses `nextafter(cap, 0)`. The order test uses a rollup whose model names sort differently from the order they were recorded in |
| D-16, FR-5 | `contract.py` → `test_spend_cap_policy_is_exported_from_its_own_module_only`, `test_max_spend_stop_reason_is_not_a_deliverable_answer` | unit | `AgentSpendCap` leaks into a package `__all__` (a new root name); `max_spend` counts as a deliverable answer | Both negative checks are paired with a positive one (`spend_cap.__all__`, the enum value) |

## Tests deliberately NOT written

| Candidate | Why it would not earn its keep |
|---|---|
| AC-24 (public API contract and `FailureCode` order) | It already passes on `base_commit`, so it cannot be red first. Lint C016, `scripts/generate-sdk-public-api.py --check` and the harness-threads pins guard it. The pack checks only that `AgentSpendCap` is not exported |
| A separate "no new spend-named `FailureCode`" test | It passes before the feature exists, and AC-17 pins the exact code the stop maps to |
| `dataclasses.replace` revalidation of the cap | It re-proves `__post_init__`, which AC-3 already exercises |
| A direct unit test of `AgentSpendCap.model_refusal` | It would re-prove the construction tests (AC-11, AC-12, AC-30) without the `BaseAgent.__init__` wiring that matters |
| EC-27 (a fallback switch reaching CP1) | The switch `continue`s to the same CP1 that AC-22 pins, and the CP1 mutant is caught there. Driving a billed failure and then a switch offline would need a fallback-chain harness this pack does not have |
| A "?" entry for a missing part in the chain message | The spec gives it no AC. `FallbackModel.__post_init__` already rejects an empty provider or model (`vidbyte/lib/dataclasses/agents.py:333-335`), so a test would have to guess at the runner's normalization to reach it |
| The 0.4.0 release record (AC-26's last clause) and "no line calls unmeasured spend capped" | The pack must not read `docs/`, and the second clause is prose. Both are left to S5 review |
| NFR-1 and NFR-2 timing | Wall-clock assertions are nondeterministic on shared machines. NFR-1 is shown by the metamorphic AC-10 test, and S4 can mutate the early return |
| `10**400` raising `OverflowError` | A quirk of the shared validator, not a promise; pinning it would block a later fix |
| EC-35, R-6, Q-14 (overlapping replies on one agent object) | A stated limitation; a test demanding a fix would be a scope change |
| Q-7 to Q-14 | Scope-adding; their default answer is No |
| EC-36 (`after_run` spend after the stop) | Accepted behavior that this change does not touch: the cap adds no logic after the stop, so a test would only pin existing `after_run` behavior |
| EC-10, EC-38 (spend the meter never sees) | Unmeasurable by design; a test could only assert that nothing happens |
| Property-based tests | Hypothesis is not installed; `cost_measured` is checked exhaustively over all 16 combinations plus the empty rollup instead |
| EC-31 (a capped checkpoint restored by an older SDK) | It needs an older SDK; the spec accepts it as forward-only |
| EC-11, EC-26 (rating differs from the bill; float accumulation) | Both are accepted limitations. The pack's reference sum uses the same order as the ledger, so the boundary tests are exact |

## Red run (before implementation)

Bootstrap: none needed. No install was run; every command uses `PYTHONPATH=$(pwd)` inline from the worktree root, on commit `643a52f6`.

```
PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/loop_spend_cap
→ 123 failed in 1.92s
```

Every failure names a missing feature. Grouped by message (`--tb=line`):

```
 65 TypeError: AgentLoopSettings.__init__() got an unexpected keyword argument 'max_spend_usd'
 20 TypeError: AgentRuntimeConfig.__init__() got an unexpected keyword argument 'max_spend_usd'
 18 AttributeError: 'UsageRollup' object has no attribute 'cost_measured'
  6 AssertionError: Regex pattern did not match.          (YAML: "'agent.loop' contains unsupported field(s): max_spend_usd.")
  5 ModuleNotFoundError: No module named 'vidbyte.agents.spend_cap'
  1 ConfigurationError: 'agent.loop' contains unsupported field(s): max_spend_usd.
  1 AttributeError: MAX_SPEND
  6 AssertionError: <doc> does not name max_spend_usd / '\n## Spend Cap\n' in <agents README>
```

```
PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/loop_spend_cap tests/features/sdk_loop_settings tests/features/sdk_model_usage tests/test_agent_runtime.py tests/test_session_failures.py tests/test_fork_tool.py tests/test_jev_usage_ledger.py tests/test_codex_output_contracts.py
→ FAILED tests/test_codex_output_contracts.py::ContractValidationTests::test_rejects_every_field_the_constant_lists
→ 124 failed, 303 passed in 2.45s
```

The only red outside the pack is the expected §12.3 row 26 entry: `AssertionError: Items in the first set but not the second: 'max_spend_usd'`. It goes green when rows 2, 25 and 26 land. `pytest --collect-only tests` collects 7690 tests with no errors. The suites the pack borrows from or touches (`tests/multi_agent`, the grader, PDJ, reflexion, critic, queued prompts, InfiniteMemory, output connectors, middleware abort) give 1099 passed.

Independent check, outside the worktree and never committed: a throwaway prototype of §12, built in a scratch copy of the tree, turns the pack green (123 passed; 427 passed for the area command above), in any file order and with each file run alone. 42 single-fault mutants of that prototype were each caught by at least one test:

- `>` for `>=`;
- each check point removed or moved;
- the blind check removed or reordered;
- the causes unsorted;
- `cost_measured` ignoring each input;
- each refusal removed;
- the fallback chain ignored or sorted;
- the OpenRouter exemption removed;
- each copy path dropping the cap;
- the router, efficiency and Codex entries removed;
- each run-ending guard removed;
- the Jev `>`, `>=` and None cases.

## Notes for the implementer

- **Names the tests bind to:**
  - `AgentLoopSettings(max_spend_usd=…)` and `.max_spend_usd`;
  - `AgentRuntimeConfig(max_spend_usd=…)`;
  - `AgentStopReason.MAX_SPEND == "max_spend"`;
  - `UsageRollup.cost_measured`, a property, not a dataclass field;
  - `vidbyte.agents.spend_cap.AgentSpendCap.stop_output(cap, rollup)`, with `__all__ == ["AgentSpendCap"]` and no re-export from `vidbyte` or `vidbyte.agents`;
  - `CODEX_UNSUPPORTED_LOOP_FIELDS` including `"max_spend_usd"`.
- **Exact strings the tests assert** (copy them from spec INV-9, INV-13 and §8.5; do not paraphrase):
  - the reached text and the blind prefix;
  - the cause texts `"{n} model calls reported no usage"`, `"no price for p:m, …"` (sorted) and `"usage recording failed"`;
  - the four refusal messages;
  - the Jev specialist message and its details `{"specialist", "max_spend_usd", "specialist_max_spend_usd"}`;
  - the worker blocker `"Worker run stopped at its spend cap."`;
  - the manager phase message `"Multi-agent manager phase stopped at its spend cap."`;
  - the fork tool error `"loop_settings does not support field 'max_spend_usd'."`.
- **Order matters:**
  - The construction refusal names unpriced models in fallback-chain order (not sorted).
  - The run-time blind text sorts them.
  - CP3 runs before the `tool_is_internal` return and before `before_tool_call`.
  - CP4 runs after `after_iteration` and before `_after_tool_iteration`.
  - CP1 runs before the `max_iterations` check.
- **Fixtures:**
  - `loop_spend_cap_fixtures.py` builds agents on `openai:gpt-5.4-mini` (the §4 model) and uses `gpt-unpriced-spend-cap-probe` as the unpriced text model. `assert_price_preconditions()` fails loudly if either assumption stops holding.
  - `ScriptedRunner` counts model calls.
  - `LaunchLikeTool` carries `internal_agent_tool` metadata.
  - `PricedSearchTool` records its cost through `record_operation`.
- **Seams the tests patch** (keep them stable):
  - `HttpTransport.request`;
  - `TypeSafeProvider.run_decision`;
  - `ModalityDetector.create_runner` in `vidbyte.agents.algorithms.multi_provider_agentic_grader`;
  - `BaseAgent._runner_for_model`;
  - `bind_test_runner`.
- **The probe subclasses** (`ProbeRuntime`, `ComputeCheckpointRuntime`) override `_continue_finish_attempt(result, state, messages)` and `_after_tool_iteration(state, messages)`, and call the real methods. AC-5 and AC-7 name these two existing methods as the observable. Keep their names and signatures.
- **A trap the prototype hit:** `BaseAgent._drain_queued_prompts` compares against `AgentStopReason.MAX_SPEND`, so `base.py` must import `AgentStopReason` where the drain runs. A missing import surfaces as `queued_prompt_error` and turns AC-31 red.
- **`_LOOP_FIELDS` in `vidbyte/lib/dataclasses/config.py` is a frozenset literal.** Add the name inside the braces.
- **Do not change** `tests/multi_agent/test_worker_stop_report.py`'s `STOPPED_REPLIES`, or the three middleware-abort tests the spec names. They must stay green unedited.
