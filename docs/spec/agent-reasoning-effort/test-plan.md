# Test plan: A reasoning effort for an agent's generative model

Spec: `docs/spec/agent-reasoning-effort/spec.md` r3 (S2), extended for r4 (S2b, after the S4 review) · Framework: pytest 8.3.5 (plain functions with `pytest.mark.parametrize`; Hypothesis is not installed, so each algebraic invariant runs as an exhaustive sweep over the §9.2 table) · Prior art copied: `tests/features/loop_spend_cap/test_loop_spend_cap_refusals.py`, `tests/features/loop_spend_cap/test_loop_spend_cap_copy_paths.py:103-176`, `tests/features/loop_spend_cap/test_loop_spend_cap_acceptance.py:78-123` (`GatewayWire` on `HttpTransport.request`), `tests/features/sdk_managed_text/test_managed_text_wire_contract.py:81-109`, `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py`

Pack: `tests/features/agent_reasoning_effort/` has 9 test files. At S2 it collected 655 cases; after the S2b additions it has 77 test functions, which give 700 collected cases (the S2 image-only non-text test was replaced by its 8-case parametrization). File names below are shortened to their aspect: `wire` means `test_agent_reasoning_effort_wire.py`, and so on.

**The central oracle.** It is a metamorphic identity, checked in the same test: `body(effort) == deep_merge(body(unset), fragment(provider, value))`, and the method, URL and headers are unchanged. Both bodies come through the real adapter, captured at `HttpTransport.request`. `fragment` and the cell lists are written into `agent_reasoning_effort_fixtures.py` from the spec's §9.2 text, never imported from the production table, so a production row that drifts from the spec fails a test instead of moving the oracle with it. `unset` tests prove that `body(unset)` holds none of the fragment's keys, so the identity cannot hold by accident.

## Coverage map
| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | acceptance → `test_the_developer_snippet_sends_high_prints_one_refusal_and_builds_jev` | acceptance | The §4 snippet run as written (runpy, keys built at run time, wire scripted) → the `planner` body lacks `reasoning.effort=high`; the printed line differs from §4; Gemini is called; or `jev`'s Messages body lacks `output_config.effort=low` | The snippet text is copied verbatim and executed. The printed output is compared with `==`. Every Responses body and every Messages body is checked, and a URL check proves that no Gemini request was sent. An empty wire fails the "every body" checks, because the test first asserts that requests exist |
| AC-2 | wire → `test_an_agent_sends_its_own_providers_fragment_and_nothing_else` (7 providers); wire → `test_each_sent_cell_adds_exactly_its_fragment_to_the_vendor_body` | integration | An agent on provider P with value v → a body that differs from the unset body by more or less than the §9.2 fragment, or that changes URL or headers | The fragment is non-empty for every cell, and the unset body has none of its keys (unset tests). So a dropped attach breaks the `==`: the drop-attach mutants failed 33 to 82 cases each |
| AC-3 | wire → `test_each_sent_cell_adds_exactly_its_fragment_to_the_vendor_body` (198 cells); registry → `test_each_sent_value_has_the_section_9_2_wire_form` | integration + unit | A "sent" cell → a wrong key path, the wrong spelling (Gemini `HIGH` versus `high`), a remapped level, or a fragment that is shallow-merged into the payload | The cells are listed from the §9.2 text, not from the module. Each runs through the real `TextModelRunner` and adapter. Shallow-merge and alias mutants failed |
| AC-4 | refusals → `test_every_refused_cell_is_refused_on_every_carrier_before_any_request` (120); refusals → `test_an_id_with_no_row_is_refused_with_the_no_row_text` (35); registry → `test_supported_returns_each_section_9_2_line_in_enum_order`, `test_an_id_with_no_row_supports_nothing` | integration + unit | A refused cell or a no-row id → construction succeeds, a request is sent, or the message is not the §8.5 capability or no-row text | The text is compared with `==` against templates built from §8.5. `wire.requests == []` is asserted after the refusal. The no-row date is read from `REASONING_EFFORT_AS_OF`, so the test cannot pin a stale literal |
| AC-5 | refusals → `test_a_gateway_mode_is_refused_with_the_text_naming_direct` (21); `test_the_mode_reason_comes_once_and_before_any_chain_entrys_capability`; `test_text_model_config_keeps_its_earlier_refusal_for_what_the_gateway_cannot_serve`; `test_text_model_config_keeps_its_custom_endpoint_refusal_in_a_gateway_mode` | integration | AUTO by default, explicit AUTO, or VIDBYTE_MANAGED with an effort → the effort reaches the gateway, or the refusal does not name `TextModelMode.DIRECT`, or the GLM/Meta/endpoint refusal changes | The default-mode case passes no `model_mode`, so it exercises the real default. For GLM, Meta and the endpoint case, the test builds the same config without an effort in the same run and compares the two messages, so the oracle is the base behavior and not a copied string |
| AC-6 | refusals → `test_every_chain_entry_is_checked_in_either_order` (7 chains); wire → `test_a_chain_that_can_take_the_value_sends_each_hops_own_form` | integration | A bad primary before a good backup, the reverse, a bad middle hop, two bad hops, or a repeated bad hop → construction succeeds, or the reasons come out of order or repeated. A capable chain → some hop sends no fragment or the wrong provider's fragment | The chain hops are driven by HTTP 500 from the wire, so every hop really sends. Each hop's body is compared with the same hop unset. The skip-primary-hop, skip-last-hop, no-dedup and hop-drop mutants each failed |
| AC-7 | refusals → `test_effort_beside_thinking_config_or_an_overlapping_extra_body_is_refused` (9); `test_the_capability_and_mode_reasons_come_before_thinking_config`; wire → `test_a_disjoint_extra_body_is_sent_beside_the_fragment` (5) | integration | thinking_config plus an effort, or an `extra_body` that overlaps the fragment's top-level keys → accepted, and `payload.update` overwrites the fragment. A disjoint `extra_body` → refused, or one of the two is missing from the body | The texts are exact and the details are exact. The disjoint case asserts that both the extra keys and the fragment are on the wire. The no-overlap and thinking-truthy mutants failed |
| AC-8 | unset → `test_an_unset_effort_sends_the_request_the_omitted_argument_sends` (17: DIRECT × 7, AUTO and VIDBYTE_MANAGED × gateway providers); `test_an_unset_checkpoint_has_no_effort_key`; `test_a_config_whose_effort_is_replaced_by_none_is_the_never_set_config`; `test_an_explicitly_unset_jev_agent_sends_what_the_default_one_sends` | integration | An unset effort → any effort field in a body, a `"reasoning_effort"` key in `runtime_config`, or a request that differs between explicit `None` and an omitted argument | It does not compare against `base_commit`, which a test cannot read (no `git show`). Instead it asserts that no effort field sits at any fragment location, plus the explicit-None identity. The `export_none` mutant (it writes `None` into the checkpoint) failed |
| AC-9 | jev → `test_each_agent_on_jevs_model_sends_the_effort` (10 children); `test_the_run_brief_writer_keeps_its_own_settings`; `test_jev_decision_calls_never_carry_the_effort`; `test_a_specialist_runs_at_its_own_setting` (2) | integration | A JevAgent with `low` → one child (main, fresh continuation, run state, run-state relation, handoff, reviewer, clarification, bulk worker, clone, swarm) sends no effort; or the brief writer, a decision call or a specialist inherits it | Each child sends exactly one request (the wire answers 500, so it is one call), and that request is compared with the same child unset. The brief and decision bodies are compared with `==` across effort and unset, so an inherited effort shows. Each of the ten skip-child mutants and the brief-inherits mutant failed |
| AC-10 | refusals → `test_a_value_outside_the_six_is_refused_on_every_carrier` (5 values × 3 carriers); `test_a_plain_string_or_another_enums_member_is_stored_as_the_member` (3) | unit | `"max"`, `""`, `"HIGH"`, `3` or `GrokReasoningEffort.MAX` → accepted, case-folded, or a message other than `<Field> must be one of …; got <repr>.`. `"high"` or `GrokReasoningEffort.HIGH` → stored as a str or a foreign member | The stored value is checked with `is ReasoningEffort.HIGH`, so an equal str fails. The message is compared exactly, with the field name for each carrier |
| AC-11 | copy_paths → `test_a_checkpoint_carries_the_effort_and_the_restored_agent_sends_it`; `test_an_old_checkpoint_without_the_key_restores_with_no_effort`; `test_restoring_a_value_the_table_no_longer_allows_is_refused` | integration | Export, then restore → the effort is lost, stored as a member (which breaks JSON), or not sent by the restored agent. A stale value → restored silently | The test JSON round-trips the state before restoring it, and asserts the restored agent's wire body. The no-export and no-restore mutants failed |
| AC-11, D-6, review R-4 | copy_paths → `test_a_restored_chain_sends_the_kept_effort_in_each_hops_own_form` | integration | Export, then restore, of a DIRECT `openai/gpt-5.5` agent with `fallback=["anthropic/claude-sonnet-5"]` and `high` → the restored chain drops the effort (for example only when `fallback_models` is stored), or a rebuilt hop sends the wrong provider's form | OpenAI answers 500, so both hops really send. It asserts the restored effort is `HIGH`, two hops with the unset chain's URLs, `reasoning={'effort': 'high'}` then `output_config={'effort': 'high'}`, and each hop's body equals the restored unset hop's body deep-merged with that hop's fragment. It asserts only what D-6 promises: the one agent-wide value is kept and the chain is rebuilt from it; no per-hop effort exists to survive. Kills N22 |
| AC-12 | copy_paths → `test_a_plain_fork_carries_the_effort_onto_the_wire`; `test_a_fork_to_a_model_that_can_take_the_effort_sends_it`; `test_a_fork_to_a_model_that_cannot_take_the_effort_is_refused` (2); `test_the_fork_tool_turns_the_refusal_into_an_error_result_and_offers_no_effort` | integration | A plain fork → the effort is dropped. A switch to an incapable model → the fork is built anyway. The fork tool → it raises, or it sends a request | The forked child's own request is captured and compared. The fork-tool case asserts error status, an output equal to the guard text, `error_type`, zero vendor requests, and a schema with no `reasoning_effort` property. The fork-drop mutant failed |
| AC-13 | contract → `test_each_root_name_is_the_defining_object_and_listed_once`; `test_a_fresh_interpreter_imports_the_three_root_names`; `test_the_public_api_contract_lists_the_three_names_at_the_package_version`; `test_the_root_header_has_one_agent_setting_exports_bullet_naming_the_three` | contract | A root copy instead of the same object; an import that works only after other imports; a stale `contracts/sdk-public-api.json`; or two header bullets | The fresh interpreter is a subprocess with `*_API_KEY` removed from its environment. The contract check is a superset plus `set(exports) == set(__all__)`, so it never pins a count. It checks the version for equality across three sources, so it never pins a version |
| AC-14 | wire → `test_anthropic_structured_output_keeps_its_format_beside_the_effort` | integration | An Anthropic `output_schema` with an effort → `_attach_response_format` erases `output_config.effort`, or the effort erases `format` | It asserts both keys in the same `output_config` dict, and compares the whole body with the deep-merge identity |
| AC-15 | wire → `test_gemini_keeps_temperature_and_schema_beside_the_thinking_config` (2: gemini-3.5-flash low, gemini-2.5-flash none) | integration | Gemini with temperature and a schema → `generationConfig` is replaced, so `temperature` or the schema is lost | The whole `generationConfig` must equal the unset one (which holds `temperature` and the schema keys) plus `thinkingConfig`, and `temperature == 0.3` is asserted directly. `thinkingConfig` is `{"thinkingLevel": "LOW"}` or `{"thinkingBudget": 0}` |
| AC-16, AC-28, EC-9, reviews R-2, R-9 | refusals → `test_a_non_text_runner_refuses_the_effort_instead_of_dropping_it` (8: `gpt-image-2`/image, `tts-1`/audio, `text-embedding-3-small`/embedding, `sora-2`/video × the keyword and `options={"reasoning_effort": "high"}`); wire → `test_runner_build_hands_the_effort_to_the_text_config` | integration | `Runner(non-text model, effort).build()`, from either channel → builds and drops the effort; a refusal narrowed to one type (N05); or the r3 text "resolves to a image runner". A text Runner → drops the effort from the options | Each case first builds the same id with the effort unset and asserts the runner class (`ImageModelRunner`, `AudioModelRunner`, `EmbeddingModelRunner`, `VideoModelRunner`), so a drifted id cannot pass vacuously. Then the exact r4 text from §8.5, the exact `details` and zero requests. The text path is checked on the wire with xAI grok-4.7 xhigh. The S2 runner-no-refuse and runner-drop mutants failed; N05 is killed by the audio, embedding and video keyword cases |
| AC-17 | usage → `test_billed_reasoning_tokens_reach_the_usage_rollup` (7 providers) | integration | A reply that reports reasoning tokens in the vendor's usage shape → a different `output_tokens` or `cost_usd` with the effort than without it | It asserts `output_tokens` equal to the billed count derived from the shape (for example Gemini 6 + 100), and `cost_usd > 0` where the pricebook prices the model, so a rollup that reads zeros fails |
| AC-18 | registry → `test_supported_normalizes_the_prefix_the_alias_padding_and_case` (5); `test_refusal_names_the_model_as_given_but_stripped` (3); refusals → `test_a_padded_upper_case_id_is_named_as_given_but_stripped`; wire → `test_a_normalized_model_id_is_sent_with_its_rows_form` (3) | unit + integration | `openai/gpt-5.6`, `gpt-5.6`, `" GPT-5.5 "` or `anthropic/claude-sonnet-5` → looked up raw (so it has no row), or named normalized in the message | Support is checked against the normalized id's line from the fixtures. The message is checked to contain the stripped original. The wire test proves that the normalized ids really send |
| AC-19 | **not tested** (it reads `docs/design/release-0-4-0.md`) | review | — | Tests may not read under `docs/` (prompt §7). S4 review checks line 17 and line 19 |
| AC-20 | wire → `test_each_sent_cell_adds_exactly_its_fragment_to_the_vendor_body`; `test_an_agent_sends_its_own_providers_fragment_and_nothing_else`; registry → `test_refusal_gives_the_section_8_5_reason_mode_first` | integration | An effort → a body with `max`, a remapped level (DeepSeek `medium` sent as `high`), a key, or another provider's reasoning field | Whole-body `==` against the identity rules out any extra key. A key-in-body search is done on the agent path. The remap mutant failed |
| AC-21, AC-22, AC-23, EC-33, D-19, review R-1 | refusals → `test_an_algorithm_that_builds_its_own_runners_refuses_the_effort` (9: AC-21 `algorithm="multi_provider_agentic_grader"`, `ContextWindow.preset.multi_provider_agentic_grader`, `ContextWindowAlgorithm(name="my-grader")` with and without `provider_models`; AC-22 reviewer `anthropic/claude-haiku-4-5` (a refused cell for `high`) and `anthropic/claude-sonnet-5` (a sent cell); AC-23 only the prosecutor, only the defender, or only the judge on `anthropic/claude-sonnet-5`) | integration | A DIRECT `openai/gpt-5.5` agent with `high` and an algorithm that builds its own runners → constructs, and those runners send no effort; or the text names the user's `name` ("my-grader", "second-opinion", "debate") instead of the fixed key | The text and the four-key `details` are compared with `==` against the §8.5 algorithm template, and zero requests. Each named case also asserts that its `name` is absent from the message (EC-33). The configurations live in the fixtures (`OWN_RUNNER_ALGORITHMS`), shared with AC-25, so the refused and the unset sides run the same objects |
| AC-24, EC-30 | wire → `test_an_algorithm_on_the_agents_own_runner_sends_the_effort_on_every_call` (2: `independent_critic` without a reviewer, `prosecutor_defender_judge` without stage models) | integration | The guard refuses a configuration that reuses the agent's own runner, or a reviewer or stage call drops the effort | Each run completes on the Wire with a reply the algorithm accepts, and must make exactly 2 (producer + reviewer) or 4 (producer + three stages) calls. Every call's body equals the unset run's matching body deep-merged with `reasoning={'effort': 'high'}`, with the same route |
| AC-25 | unset → `test_an_unset_effort_keeps_every_algorithm_configuration_running_as_before` (11: the 9 AC-21 to AC-23 configurations and the 2 of AC-24) | integration | `refuse_algorithm_models` refuses or changes an agent whose effort is `None` | Each configuration is built with `reasoning_effort=None` and run; the preset grader gets run-time key variables so it really picks its models. It must send at least 2 vendor requests (the algorithm's own calls included), and none may carry an effort field at any §9.2 location |
| AC-26, review R-3 | wire → `test_an_options_effort_reaches_the_text_config_and_the_wire` | integration | `Runner(openai/gpt-5.5, DIRECT, options={"reasoning_effort": "high"})` → the unset keyword overwrites the option with `None`, so nothing is sent | It asserts the built config's `reasoning_effort is ReasoningEffort.HIGH` (through `TextModelRunner._config`, as `tests/features/sdk_provider_keys` reads it) and the body identity with `reasoning={'effort': 'high'}` |
| AC-27, review R-3 | refusals → `test_an_options_effort_the_text_config_cannot_send_is_refused_like_the_keyword` (3: default AUTO `high`, DIRECT `minimal` on `gpt-5.5`, DIRECT `high` on the no-row `gpt-4o`) | integration | An options effort in a gateway mode, on a refused cell, or on an id with no row → built and dropped, or sent | The `TextModelConfig` text is compared with `==` against the §8.5 mode, capability or no-row template, and must equal the keyword channel's text from the same build. `details` are exact, including `mode`; zero requests |
| AC-29 | wire → `test_the_keyword_effort_wins_over_an_options_effort` | integration | Keyword `LOW` with `options` `high` → the options value wins | The config holds `LOW`, and the body equals the unset body plus `reasoning={'effort': 'low'}` only. This pins "the keyword wins" against a repair that lets options win |
| EC-31 | refusals → `test_an_earlier_guard_reason_outranks_the_algorithm_text` | integration | The algorithm check runs before `refuse_unsupported`, so the algorithm text hides a gateway-mode or capability reason | One test proves the order: the same `multi_provider_agentic_grader` agent gives the algorithm text in DIRECT on a sent cell, the mode text in the default AUTO, and the capability text on the refused cell `minimal` |
| EC-32 | refusals → `test_a_non_linear_runtime_refuses_its_algorithm_before_either_guard_method` | integration | An effort reason replaces the existing non-linear runtime refusal | The effort is a refused cell, so either guard method would refuse if it ran first. The message must equal the same build without an effort, captured in the same run, and must not mention `reasoning_effort` |
| EC-30 | refusals → `test_a_half_set_model_pair_fails_before_any_agent_exists` (4); and the AC-24 row | unit | A reviewer or stage pair could be half set, so the guard's "reviewer set" and "stage sets both" checks would miss a runner the algorithm builds | Each half pair must raise from its own record, before any agent exists, with a text that does not mention `reasoning_effort` |
| EC-34 | **not tested** (accepted limitation) | — | — | The spec accepts that an `agent.algorithm` assigned after construction is not re-checked |
| EC-35 | wire → `test_an_options_effort_of_none_is_unset_on_every_runner_type` | integration | `options={"reasoning_effort": None}` → a reasoning field is sent, or a non-text runner is refused | The text body must equal the body built without `options`, with no `reasoning` key, and the config must hold `None`. All four non-text ids must build |
| EC-36, review R-3 | refusals → `test_an_options_effort_outside_the_six_is_refused_by_the_text_config` (2: `"max"`, `"HIGH"`) | integration | A bad options value on a text model → dropped silently | The message equals `TextModelConfig.reasoning_effort must be one of none, minimal, low, medium, high, xhigh; got 'max'.` (and `got 'HIGH'.`) exactly; zero requests |
| INV-1 | unset tests (AC-8 row); refusals → GLM/Meta/endpoint messages compared in the same run | integration | Unset → a changed body or a changed existing message | See AC-8. Existing messages are compared against the same construction without an effort |
| INV-2 | wire → sent-cell sweep, chain test, AC-14 and AC-15 tests; registry → `test_attach_deep_merges_into_keys_the_payload_already_holds` | unit + integration | Shallow merge → a nested key the adapter set is lost | Nested pre-existing keys are seeded under the fragment's own top-level key |
| INV-3 | refusals (AC-4, AC-16, AC-21 to AC-23, AC-27, AC-28 rows); wire (AC-26 row); refusals → `test_an_agent_without_both_a_provider_and_a_model_is_refused` (3) | integration | An effort that is dropped silently (by `Runner`, from either channel, or by an algorithm's own runner), or set on an agent that can never run | Exact identity text and zero requests |
| INV-4, NFR-2 | every refusal test asserts `wire.requests == []` | integration | A refusal raised after an HTTP call | The wire records every request, including gateway and decision URLs |
| INV-5 | AC-5 row | integration | — | — |
| INV-6 | AC-6 row | integration | — | — |
| INV-7 | AC-7 row | integration | — | — |
| INV-8 | AC-10 row; contract → `test_reasoning_effort_is_a_str_enum_with_the_six_values_in_order` | unit + contract | Members out of order, a seventh member, or no StrEnum | Values, names, `str()` and f-string results are all checked |
| INV-9 | wire → `_same_route` in every wire test; agent-path key search | integration | An effort that changes the URL, the headers or the key | Method, URL and headers are compared as a tuple with the unset call |
| INV-10, NFR-5 | AC-17 row | integration | — | — |
| INV-11, NFR-6 | every refusal test compares `str(error)` with `==` against the §8.5 templates; the key-in-message check in `_assert_carrier_texts` | unit | A paraphrased message, a missing supported list, or a key in the text | The templates are built from §8.5 text in the fixtures, not from production |
| INV-12 | AC-13 row | contract | — | — |
| INV-13, EC-27 | registry → `test_attach_gives_each_payload_a_private_copy_and_never_touches_the_table` | unit | Two payloads share a fragment object, or a write to one payload mutates the module table | It asserts that the two payloads share no dict ids, mutates one, then compares the table with a deepcopy taken before. The alias mutant failed |
| INV-14 | AC-11 row | integration | — | — |
| INV-15 | AC-9 row | integration | — | — |
| INV-17 | wire → `test_thinking_config_without_an_effort_is_forwarded_as_before` (4) | integration | Unset effort → Anthropic or Gemini `thinking_config` forwarding changes (truthy versus not-None) | The empty and set cases are checked for each provider |
| INV-18 | refusals → `test_the_spend_cap_refusal_still_runs_before_the_effort_guard` | integration | The guard runs first, so the spend-cap text is lost | The id is both unpriced and unlisted, so both refusals apply. The message with the effort must equal the message the same agent gives without the effort, in the same run, and must not mention `reasoning_effort`. The guard-first mutant failed |
| INV-19 | contract → `test_each_carrier_takes_the_effort_keyword_only_with_default_none` (4); `test_the_guard_is_a_keyword_only_static_method` | contract | A positional parameter, a non-None default, or a guard with different parameters | `inspect.signature` kind and default are checked. The existing pins stay as they are |
| FR-7, D-19, §8.5 | contract → `test_the_algorithm_guard_is_a_keyword_only_static_method` | contract | `refuse_algorithm_models` is missing, not a staticmethod, positional, or has other parameters; or the repair adds `algorithm` to `refuse_unsupported` instead | It pins `["agent_name", "runner_config", "algorithm"]`, all keyword-only, beside the unchanged `refuse_unsupported` pin |
| INV-20 | registry → `test_supported_returns_each_section_9_2_line_in_enum_order` (53), `test_an_id_with_no_row_supports_nothing` (44), `test_every_table_row_is_a_catalog_text_id_with_an_enum_ordered_tuple` | unit | A missing line, a reordered tuple, an empty row, or a row keyed by a non-catalog id | It checks each line, and checks structure over every row. It never checks the table's size or freezes its key set (prompt rule) |
| EC-1 to EC-5, EC-9, EC-10, EC-18 to EC-24 | the refusal, copy-path and wire rows above (EC-21 is `test_a_slug_without_a_provider_is_checked_against_the_row_the_runner_resolves`) | regression | the trigger in §6.3 → the wrong outcome named there | each is a parametrized case with an exact text |
| EC-6, EC-7, EC-8 | AC-14 and AC-7 rows | regression | — | — |
| EC-25, EC-26, EC-28 | in the sent-cell sweep (claude-opus-5 none sends `thinking.type=disabled` only; claude-opus-4-8 sends `output_config.effort` alone; gpt-5.5 medium is sent explicitly) | integration | — | It compares the whole body |
| T-1 | AC-4 and AC-20 rows | security | A careless value is sent and billed | — |
| T-2 | copy_paths → fork-tool test; wire → `_same_route` | security | A model-chosen fork sends an unsupported effort, or moves a key | Zero vendor requests; the schema offers no `reasoning_effort` |
| T-3 | `_assert_carrier_texts` asserts the key is not in `str(error)`; the agent-path key search | security | A key leaks into a refusal or a body | Keys are assembled at run time and searched for as whole strings |
| T-4 | AC-5 row | security | A gateway mode carries the effort to a shared backend | — |
| Pins | `test_managed_text_selection.py:57`, `test_provider_keys_contract.py:130,132` | contract | The field is not appended last on `TextModelConfig`, `AgentRunnerConfig` or `JevAgentSettings` | They are red now only because `reasoning_effort` is missing (Red run below) |

## Tests deliberately NOT written
| Candidate | Why it would not earn its keep |
|---|---|
| AC-19 release record (line 17 and line 19) | It lives under `docs/`, which tests may not read. It is a review check |
| INV-16 `EMITTED_KEYS` and the managed-text wire contract | `tests/features/sdk_managed_text/test_managed_text_wire_contract.py` already pins them and must pass unedited. A copy would re-prove it |
| Byte equality with `base_commit` bodies | It needs `git show` or a merge-base, which the prompt forbids. The unset tests prove the same fact (explicit None equals omitted, and there is no effort field at any fragment location) |
| Asserting the size of `REASONING_EFFORT_SUPPORT`, or freezing its key set | The prompt forbids it, and a sourced new row must not turn the pack red |
| A Hypothesis property over random payloads for deep-merge | Hypothesis is not installed. The exhaustive sweep over every sent cell, with seeded nested keys, covers the same algebra |
| NFR-3 lint ratchet, NFR-7 file sizes, NFR-4 per-cell quote IDs | These are lint or review facts, not behavior. A test would duplicate `lint/run.py` |
| EC-11 to EC-17 vendor behavior (400s, ignored temperature, tool_choice, reasoning items) | They are accepted limitations that only a live vendor shows. A scripted wire would assert the script |
| EC-29 restore by an older SDK | It needs an older SDK in the test process |
| Per-hop effort that survives restore (D-6), Q-1 to Q-10, A-4 | Excluded by the prompt |
| The effort forwarded into an algorithm's own runners (Q-11) | Q-11 is No: the agent is refused instead (D-19), so a forwarding test would pin the rejected design |
| An `agent.algorithm` assigned after construction is refused (EC-34) | An accepted limitation in the spec |
| A second acceptance run per provider | AC-2's seven-provider agent test already runs the same path |
| "Attach leaves the payload unchanged after a refusal" | Over-specification. §8.5 does not promise it, and the builder raises before the payload is used |
| A README path-string assertion | Too brittle. The sources heading and the date are checked, and the exact pointer text is inside the no-row template |

## Red run (before implementation)
Bootstrap: none. Per the briefing, nothing was installed (`pip install -e .` is forbidden). Every command runs with `PYTHONPATH=$(pwd)` inline, never exported, and with `py -3.11`.

```
$ PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort
655 errors in 4.19s
    365 ImportError: cannot import name 'REASONING_EFFORT_AS_OF' from 'vidbyte.lib.configs'
    263 ImportError: cannot import name 'ReasoningEffort' from 'vidbyte.lib.enums'
     15 ImportError: cannot import name 'ReasoningEffort' from 'vidbyte'
     12 ImportError: cannot import name 'GEMINI_THINKING_BUDGET_OFF' from 'vidbyte.lib.configs'
```
Run per file, with `PYTHONPATH=$(pwd) py -3.11 -m pytest -q <file>`:
```
test_agent_reasoning_effort_acceptance.py → 1 error in 0.87s
test_agent_reasoning_effort_contract.py → 12 errors in 0.90s
test_agent_reasoning_effort_copy_paths.py → 10 errors in 0.90s
test_agent_reasoning_effort_jev.py → 14 errors in 0.92s
test_agent_reasoning_effort_refusals.py → 214 errors in 2.11s
test_agent_reasoning_effort_registry.py → 151 errors in 1.57s
test_agent_reasoning_effort_unset.py → 21 errors in 0.94s
test_agent_reasoning_effort_usage.py → 7 errors in 0.89s
test_agent_reasoning_effort_wire.py → 225 errors in 1.93s
```
The errors are setup errors: a module-level guard holds the `ImportError`, and an autouse fixture raises it. So the pack collects, and the rest of the tree collects too (`pytest --collect-only tests` → `8360 tests collected`).

Focused area suite, with the three pin appends:
```
$ PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/sdk_managed_text tests/features/sdk_provider_keys tests/features/loop_spend_cap tests/features/jev_cli_root_exports tests/test_gemini_provider_text.py tests/test_compatible_provider_text.py tests/test_deepseek_provider.py tests/test_agent_pricing.py tests/test_jev_agent.py
FAILED tests/features/sdk_managed_text/test_managed_text_selection.py::KeySelectionTests::test_text_config_keeps_its_field_order_and_rejects_a_mode_that_is_not_the_enum
FAILED tests/features/sdk_provider_keys/test_provider_keys_contract.py::RecordLayoutTests::test_each_renamed_record_keeps_its_field_order
2 failed, 418 passed in 5.53s
```
Both failures are the expected pin reds. The first is `Second list contains 1 additional elements … 'reasoning_effort'`. The second fails on the `AgentRunnerConfig` layout for the same missing field; the `JevAgentSettings` append on line 132 is checked after it.

**Satisfiability check, outside the worktree.** A throwaway prototype of §12 was written in a scratch copy of the repository, not in this worktree and not committed: the three new modules and the call-site edits. Against it the pack ran `655 passed in 2.50s`, and the area suite with the pins ran `420 passed`. That proves the pins are red only because the field is missing. 35 seeded mutants were each run against the pack, and every one failed at least one test (failures per mutant):

| Mutant | Cases failed |
|---|---|
| drop attach in OpenAI / Anthropic / Gemini / compatible builder | 82 / 67 / 33 / 59 |
| shallow merge / alias the table / remap DeepSeek medium to high | 10 / 11 / 8 |
| guard skips the primary hop / skips the last hop / no dedup / runs before the spend cap / is removed | 2 / 4 / 2 / 1 / 194 |
| capability checked before mode | 141 |
| Runner drops the option / does not refuse a non-text runner | 32 / 1 |
| primary runner drops the effort / a fallback hop drops it | 31 / 1 |
| checkpoint not exported / `None` exported when unset / not restored | 1 / 2 / 2 |
| fork / continual trace / handoff side agent drops it | 5 / 1 / 1 |
| thinking_config refused only when truthy / no extra_body overlap check | 2 / 6 |
| Jev skips main / fresh / bulk / clone / swarm / done-handoff / reviewer / run state / clarification | 2 / 1 / 1 / 1 / 1 / 1 / 1 / 2 / 1 |
| brief writer inherits the effort | 1 |

## S2b red run (spec r4, before the S5 repair)

The code is the S3 implementation (code head ce751768, worktree HEAD 346f8c3e). Every pre-existing test still passes; the red set is exactly the tests for the broken behaviors. Each red test fails on the missing behavior, never on a fixture or import error:

```
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort tests/features/sdk_managed_text/test_managed_text_selection.py tests/features/sdk_provider_keys/test_provider_keys_contract.py tests/test_agent_modality_routing.py
25 failed, 723 passed in 3.57s
```

| Red group (cases) | Why it is red now | One failing assertion |
|---|---|---|
| AC-21 to AC-23: `test_an_algorithm_that_builds_its_own_runners_refuses_the_effort` (9) | no refusal: the agent constructs (R-1) | `refusals.py:143: Failed: DID NOT RAISE <class 'vidbyte.lib.errors.base.ConfigurationError'>` |
| EC-31: `test_an_earlier_guard_reason_outranks_the_algorithm_text` (1) | its DIRECT control gets no algorithm refusal (R-1) | `Failed: DID NOT RAISE <class 'vidbyte.lib.errors.base.ConfigurationError'>` |
| Method pin: `test_the_algorithm_guard_is_a_keyword_only_static_method` (1) | the method does not exist | `contract.py:290: AssertionError: AgentReasoningEffortGuard has no static refuse_algorithm_models` |
| AC-16, AC-28 keyword: `test_a_non_text_runner_refuses_the_effort_instead_of_dropping_it[*-keyword]` (4) | the r3 text (R-9) | `- solves to runner type 'image', which has no reasoning effort.` / `+ solves to a image runner, which has no reasoning effort.` |
| AC-28 options: `…[*-options]` (4) | the options effort is dropped, not refused (R-3) | `Failed: DID NOT RAISE <class 'vidbyte.lib.errors.base.ConfigurationError'>` |
| AC-26: `test_an_options_effort_reaches_the_text_config_and_the_wire` (1) | the options effort is overwritten with `None` (R-3) | `wire.py:355: AssertionError: assert None is <ReasoningEffort.HIGH: 'high'>` |
| AC-27: `test_an_options_effort_the_text_config_cannot_send_is_refused_like_the_keyword` (3) | the options effort is dropped before `TextModelConfig` sees it (R-3) | `Failed: DID NOT RAISE <class 'vidbyte.lib.errors.base.ConfigurationError'>` |
| EC-36: `test_an_options_effort_outside_the_six_is_refused_by_the_text_config` (2) | the same drop (R-3) | `Failed: DID NOT RAISE <class 'vidbyte.lib.errors.base.ConfigurationError'>` |

Green now, and they must stay green through the repair: AC-24 (2), AC-25 (11), AC-29, EC-30 (4), EC-32, EC-35 and the R-4 restored chain. The area suite (the pack plus `tests/features/sdk_managed_text tests/features/sdk_provider_keys tests/features/loop_spend_cap tests/features/jev_cli_root_exports tests/test_gemini_provider_text.py tests/test_compatible_provider_text.py tests/test_deepseek_provider.py tests/test_agent_pricing.py tests/test_jev_agent.py tests/test_agent_modality_routing.py`) gives `25 failed, 1114 passed`: the same 25.

The ids were confirmed at this code with the effort unset before they were pinned: `Runner(provider="openai", model_name=…).build()` builds `ImageModelRunner` for `gpt-image-2`, `AudioModelRunner` for `tts-1`, `EmbeddingModelRunner` for `text-embedding-3-small` and `VideoModelRunner` for `sora-2` (ModalityDetector agrees), so the suggested ids were kept.

## Mutation (S2b)

Run in a scratch copy of the staged tree (`git archive $(git write-tree)`), with the engineering runner restricted to N05 and N22 (`-x`, pack + pins + modality pin, every red node deselected). The archive has `contracts/`, so the two contract tests ran and passed; nothing else was deselected.

| Mutant | Change | Result | Killed by |
|---|---|---|---|
| Control | none, 25 red deselected | `723 passed, 25 deselected` (before and after) | — |
| N22 | `restore` passes `reasoning_effort=None` when `fallback_models` is stored | KILLED: `1 failed, 14 passed, 25 deselected` (`-x`); without `-x`, `1 failed, 674 passed` | copy_paths → `test_a_restored_chain_sends_the_kept_effort_in_each_hops_own_form`, the only pack test that fails |
| N05 | the non-text refusal fires only for `runner_type == "image"` | KILLED: `1 failed, 246 passed, 21 deselected` (`-x`); the four keyword cases give `3 failed, 1 passed` | refusals → `test_a_non_text_runner_refuses_the_effort_instead_of_dropping_it[audio-keyword]`, `[embedding-keyword]`, `[video-keyword]` (`[image-keyword]` passes, as N05 keeps images) |

N05's killers are red at this code only on the r3 text (R-9), so the proof first changed the single `Runner` message line in the scratch copy's `vidbyte/lib/runners/utility.py` to the r4 text. The four keyword cases then gave `4 passed`, and the pack with the other 21 red nodes deselected gave `727 passed`. N05 was applied on top of that, and both files were restored and diffed equal to the worktree (`diff --strip-trailing-cr`). That text change exists only in the scratch copy; it was never committed or applied to the worktree. After the S5 repair rewrites the refusal line, N05's exact old string no longer exists; the same cases then guard the repaired condition directly.

## Notes for the implementer
- **Names the tests bind to:**
  - `vidbyte.lib.enums.ReasoningEffort`, plus the root names `ReasoningEffort`, `DecisionModelConfig` and `DecisionModelMode`;
  - `vidbyte.lib.configs`: `REASONING_EFFORT_AS_OF`, `REASONING_EFFORT_FORMS`, `REASONING_EFFORT_SUPPORT` and `GEMINI_THINKING_BUDGET_OFF`;
  - `vidbyte.lib.registries.ReasoningEffortRegistry`, with `supported`, `refusal(provider=, model=, effort=, mode=)` and `attach(payload, provider=, model=, effort=)`;
  - the modules `vidbyte.lib.configs.reasoning_effort` and `vidbyte.lib.registries.reasoning_effort`, which are checked for identity;
  - `vidbyte.agents.reasoning_effort.AgentReasoningEffortGuard.refuse_unsupported(*, agent_name, runner_config, fallback)`, a staticmethod;
  - (r4) `AgentReasoningEffortGuard.refuse_algorithm_models(*, agent_name, runner_config, algorithm)`, a staticmethod, called by `BaseAgent.__init__` after the algorithm is resolved;
  - (r4) `Runner(options={"reasoning_effort": ...})`, which must reach `TextModelConfig` and the non-text refusal like the keyword;
  - the `reasoning_effort` keyword-only parameter with default `None` on `BaseAgent.__init__`, `Runner.__init__`, `AgentFallback.__init__` and `AgentFallbackSettings.to_fallback`;
  - the fields `TextModelConfig.reasoning_effort`, `AgentRunnerConfig.reasoning_effort` and `JevAgentSettings.reasoning_effort`, each appended last;
  - the `runtime_config["reasoning_effort"]` key, which holds a plain str and is present only when the effort is set.
- **Exact texts.** The tests compare messages character for character against §8.5, including these:
  - the no-row pointer `(see "Reasoning Effort Sources" in vidbyte/lib/registries/README.md)`;
  - a heading in that README that matches `^## Reasoning Effort Sources`;
  - the Runner text, r4: `Runner sets reasoning_effort, but model '{model_name}' resolves to runner type '{runner_type}', which has no reasoning effort.` (r3's `… resolves to a image runner …` was re-pinned at S2b, review R-9);
  - the algorithm text, r4: `Agent {agent_name} sets reasoning_effort, but its {algorithm} algorithm calls models through runners it builds itself, which never send the effort; unset reasoning_effort, or configure an algorithm that runs only on the agent's own model.`, where `{algorithm}` is `multi_provider_agentic_grader`, `independent_critic` or `prosecutor_defender_judge`.
- **Exact details.** These are compared as dicts:
  - Guard: `{"agent", "field": "reasoning_effort", "reasoning_effort"}`; the algorithm refusal adds `"algorithm"`, the fixed key.
  - TextModelConfig: `{"field": "TextModelConfig.reasoning_effort", "provider", "model", "reasoning_effort", "mode"}`, where `model` is the stripped given id.
  - Thinking and overlap: `{"field": "TextModelConfig.reasoning_effort"}`.
  - Runner: `{"provider", "model", "runner_type"}`.
  - `to_enum` keeps its own `{"field": <Carrier>.reasoning_effort}`.
- **Fixtures relied on.** The pack fakes only `HttpTransport.request`, through `Wire().install(monkeypatch)`, or a `transport=` passed to `TextModelRunner`, `StreamingTextModelRunner` or `Runner.build`. Wire answers TypeSafe decision URLs with 500, and Jev's gates fail open. Do not route the effort around `HttpTransport`.
- **What must not change:**
  - the attach point, immediately before `_attach_extra_body`;
  - deep copy plus deep merge;
  - mode checked before capability;
  - guard order: spend cap, then the guard;
  - the brief writer, decisions and specialists never receive the effort;
  - the three pins, which S2 owns.
- **Do not edit any test in this pack to make it pass.** If a test disagrees with the code, the spec decides. A test that is wrong against the spec is reported to the orchestrator.
