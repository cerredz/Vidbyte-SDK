# byok-api-keys: test plan (S2)

Spec: `docs/spec/byok-api-keys/spec.md` r4 (approved). Branch `feat/byok-api-keys`, base `52aab816`.
New pack: `tests/features/sdk_provider_keys/` (117 tests, 11 files plus fixtures, FEATURE.md, README.md).
Superseded updates: `tests/features/sdk_managed_text/` and 30 module test files (spec §13).

Every test that builds a runner or an agent clears the environment (`patch.dict(os.environ, …, clear=True)` or `RecordingEnviron`) and scripts the inner HTTP transport. Only the transport, the retry wait, and the environment are faked. `ProviderKeyMatcher`, `ProviderKeys`, `credentials()`, `ProviderModelRegistry`, the adapters, and `VidbyteGatewayTransport` run for real. Every feature symbol is imported inside the test, so the pack collects while it is red.

## 1. Coverage map

Files are abbreviated: `acc` = `test_provider_keys_acceptance.py`, `match` = `…_matching.py`, `prop` = `…_property.py`, `agents` = `…_agents.py`, `sess` = `…_sessions.py`, `modes` = `…_modes.py`, `wire` = `…_wire_contract.py`, `fail` = `…_failures.py`, `sec` = `…_security.py`, `contract` = `…_contract.py`; all under `tests/features/sdk_provider_keys/`. Levels: A = acceptance (public API, end to end through the real runner and a scripted transport), I = integration (several real components), U = unit (one class or function), S = static (source or signature inspection).

### Acceptance criteria

| Spec ID | Test (file → name) | Level | Failure it catches | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | acc → `test_section_4_snippet_relays_grok_with_only_the_xai_key_and_builds_the_offline_agent_without_reading_the_vidbyte_key` | A | The §4 snippet does not run as written, the grok call is not relayed, the Anthropic key rides along, or the DIRECT agent reads `VIDBYTE_API_KEY` | A patched transport that is never reached: the test asserts exactly one POST to the gateway URL with the exact bearer and relay header, and the printed reply comes from the scripted answer. `RecordingEnviron` records actual reads, so "reads nothing" is observed, not assumed |
| AC-2 | acc → `test_auto_relays_exactly_when_the_provider_has_a_key_and_otherwise_sends_base_commits_three_headers`; wire → `test_the_relay_envelope_body_is_the_direct_body_with_the_gateway_cap`; managed `test_managed_text_acceptance.py` → `test_provider_key_relays_in_auto_and_keeps_its_byok_request_byte_identical_in_direct` | A | A provider key beside a Vidbyte key goes vendor-direct (base behavior) or is not relayed | Comparing a relay body with itself: the oracle is a separate DIRECT run of the same adapter, asserted to go to the vendor URL |
| AC-3 | acc (same test as AC-2); wire → `test_a_call_without_a_provider_key_sends_exactly_the_three_base_commit_headers` | A | A paid call gains a fourth (empty) header or a changed envelope | Checking only that the relay header is absent: the test asserts the exact header-name set `{authorization, content-type, idempotency-key}` |
| AC-4 | acc → `test_auto_without_a_vidbyte_key_refuses_the_runner_before_any_request_and_names_both_ways_out` | A | `AUTO` with only `OPENAI_API_KEY` silently goes vendor-direct | An error raised for another reason: the test binds M-9's facts (`vidbyte_api_key`, `VIDBYTE_API_KEY`, `TextModelMode.DIRECT`) and `error_kind`, and asserts the transport saw no request |
| AC-5 | acc → `test_direct_sends_base_commits_byok_request_and_ignores_a_malformed_vidbyte_key_in_the_environment` | A | `DIRECT` reads `VIDBYTE_API_KEY` and fails on a malformed value, or changes the vendor request | A golden recomputed from code: the expected request is a literal recorded at base_commit |
| AC-6 | modes → `test_streaming_refuses_every_gateway_mode_before_reading_any_key`, `test_direct_streams_straight_from_the_provider_with_the_provider_key`; managed selection → `test_streaming_refuses_managed_state_but_still_streams_byok_beside_a_vidbyte_key` | I | `AUTO` streaming bypasses the gateway, or the refusal reads keys first | A refusal caused by a missing key: the environment is empty in one case and full in the other, and both must give M-15 with `details["mode"]` |
| AC-7 | agents → `test_list_order_changes_neither_the_match_nor_any_request`; prop → `test_matching_ignores_list_order_and_the_environment_and_has_exactly_two_outcomes` | A, U | Order-dependent matching | Comparing two empty records: `key_view` must hold both keys, and each provider's request must carry only its key (spec defect 1: "equal" is read as order-free equality) |
| AC-8 | match → `test_a_string_bytes_mapping_or_number_is_refused_naming_the_field_and_never_its_characters`; prop → `test_a_bare_string_is_never_iterated_into_characters` | U | A bare string iterated into characters | Any exception passing: the test binds M-1 to M-3 facts and `details`, and that the message holds no key characters |
| AC-9 | agents → `test_a_key_no_configured_provider_can_take_is_refused_naming_its_index_length_and_the_providers`, `test_an_entry_with_a_space_or_line_break_is_refused_before_anything_else` | I | An unusable entry dropped silently, or named by its characters | The refusal must name index, length, and providers (M-6) and carry no key text |
| AC-10 | match → `test_two_different_proven_keys_for_one_provider_are_refused_and_the_same_key_twice_is_one_key`, `test_two_unproven_keys_with_one_possible_owner_are_refused` | U | Last-key-wins for one provider | The "same key twice" half proves the refusal is about different keys, not duplicates |
| AC-11 | acc → `test_a_vidbyte_entry_in_api_keys_is_only_the_bearer_and_a_second_vidbyte_key_is_refused`, `test_a_vidbyte_key_in_a_provider_variable_is_refused_in_auto_and_in_direct` | A | A Vidbyte key relayed as a provider key | The request is inspected for the relay header's exact value (the OpenAI key) and for the Vidbyte key appearing only as the bearer |
| AC-12 | acc → `test_unserved_providers_and_custom_endpoints_need_direct_and_then_reach_the_vendor_or_proxy_as_at_base_commit`, `test_unserved_provider_in_direct_uses_its_environment_key_as_at_base_commit`; modes → `test_every_unserved_provider_and_any_endpoint_is_refused_at_construction_in_both_gateway_modes` | A | The Vidbyte bearer follows a caller URL, or an unserved provider is refused only late | Construction is inside `assertRaises`, so a later refusal fails the test; the DIRECT half proves the same config works |
| AC-13 | acc → `test_vidbyte_managed_never_sends_or_reads_a_provider_key` | A | `VIDBYTE_MANAGED` relays or reads `OPENAI_API_KEY` | `RecordingEnviron` proves the variable was never read, not just unused |
| AC-14 | fail → `test_a_relayed_provider_refusal_names_the_provider_and_status_and_is_never_re_sent` | I | A relayed 401/402/403 blames Vidbyte, is re-sent, or leaks the provider message | Four providers × three statuses, each asserting "your own", withheld, not billed, exactly one POST, and no key or canary |
| AC-15 | fail → `test_each_gateway_status_states_the_facts_for_a_paid_call_and_for_a_relay_call` | I | Relay calls get paid-call wording ("Vidbyte's own account", "daily") or vice versa | Ten statuses × two modes with both required and forbidden facts; the prefix "Vidbyte gateway {provider} request failed:" is exact |
| AC-16 | agents → `test_a_relayed_401_falls_back_and_each_call_carries_only_its_own_providers_key` | A | A fallback call carries the primary's key | Both POSTs are inspected, each for its own key and the absence of the other |
| AC-17 | agents → `test_a_backup_without_a_matched_key_goes_vidbyte_paid_once_the_primary_holds_its_key` | A | The backup refuses (INV-24) or borrows the primary's key | The backup's POST is asserted to carry exactly three headers |
| AC-18 | agents → `test_forks_handoff_and_continual_trace_agents_carry_the_parents_record_and_direct_mode`, `test_a_jev_agent_its_clone_and_its_brief_writer_carry_the_settings_record_and_mode`, `test_an_aggregates_children_carry_its_record_and_each_direct_call_carries_its_own_key` | I | A child re-matches the list or drops the mode | Record equality alone could hold for two empty records; the tests also assert K_u at deepseek and K_o at openai and each child's DIRECT call key |
| AC-19 | sess → `test_every_restore_path_keeps_direct_and_rebuilds_the_roots_record_without_storing_a_key` | I | A restore path loses `DIRECT` or stores a key | Every checkpoint file is read back and searched for each key |
| AC-20 | sec → `test_no_record_listed_in_inv_4_shows_a_key_in_its_repr` | U | A repr shows a key | Each record is built holding the keys; `AgentFallbackSettings` is skipped because it can no longer hold a key (D-26) |
| AC-21 | sec → `test_relay_refusal_retry_and_agent_failure_paths_print_no_key`; fail → `test_a_relay_call_with_no_response_names_no_key` | I | A key in a log line, message, `details`, or traceback | Root-logger capture plus `traceback.format_exception` text, for eight scenarios that each must actually fail or log |
| AC-22 | sec → `test_the_credential_key_policies_classify_the_plural_names_and_still_the_old_ones`, `test_the_agent_descriptor_guard_rejects_api_keys_in_metadata_and_tool_options`, `test_the_harness_redactor_removes_every_key_in_a_list_or_tuple_value` | U | The guards miss `api_keys`, or the redactor removes only the first key | Both keys of each list and tuple form must be gone (spec defect 4: these cases live here, not in `test_harness_redaction.py`) |
| AC-23 | agents → `test_image_and_audio_runners_get_their_providers_matched_key_or_none` | I | A non-text runner gets the whole list, a Vidbyte key, or another provider's key | The runner's own `api_key` is asserted equal to the matched key, and `None` when the list holds none |
| AC-24 | contract → `test_the_old_keyword_raises_a_type_error_naming_it`, `test_create_runner_refuses_api_key_for_a_text_model_naming_api_keys` | S | `api_key=` silently accepted | The `TypeError` must name `'api_key'`; `create_runner` must raise M-17 with `details["model"]` (spec defect 2) |
| AC-25 | agents → `test_model_mode_must_be_the_enum`; contract → `test_agent_runner_config_refuses_a_raw_list_and_a_string_mode` | U | `"direct"` accepted as a string | The M-16 message names the owner field |
| AC-26 | agents → `test_an_agent_without_any_vidbyte_key_builds_and_its_first_run_raises_the_missing_key_error_before_any_request` | A | The agent refuses at construction, or its first run reaches the network | Construction must succeed and the first run must raise M-9 with no request |
| AC-27 | acc → `test_readme_managed_section_documents_api_keys_vidbyte_api_key_relay_matching_and_direct` | S | The README is not rewritten | The section is found by the managed-section heading and checked for each fact; the base README lacks `api_keys` |
| AC-28 | none in pytest (gate) | — | — | Proven by `python lint/run.py` and `scripts/run_ci.py` (§11), not by a test |
| AC-29 | match → `test_each_table_f_sample_proves_its_provider_and_every_unsourced_shape_is_unproven`, `test_accepts_unproven_follows_table_a_and_the_reserved_prefixes`, `test_an_entry_with_a_space_line_break_or_non_ascii_character_is_refused_by_normalize` | U | A wrong or missing prefix rule | One sample per table F rule, built at runtime (the `AIza` + 35, `sk-ant-api03-…AA`, and `T3BlbkFJ` shapes only here, by concatenation), plus near-misses that must be unproven |
| AC-30 | contract → `test_the_manual_scripts_compile_and_build_text_configs_with_api_keys` | S | A manual script still passes `api_key=` to a text config | AST scan of all three scripts; the test fails today on `scripts/test-new-runners.py:315` |
| AC-31 | agents → `test_an_unproven_key_reaches_only_the_backup_it_was_bound_to_in_either_order` | A | An unproven key sent to the anthropic primary | Both orders, and the anthropic POST is searched for K_u |
| AC-32 | agents → `test_two_unproven_keys_two_providers_could_take_are_refused_and_a_lone_one_binds_to_the_primary` | I | Two unproven keys bound by position | The refusal must name both candidates and their variables (M-19) |
| AC-33 | agents → `test_a_list_without_the_agents_own_providers_key_is_refused_while_an_empty_or_vidbyte_only_list_goes_vidbyte_paid` | I | A list without the primary's key accepted | The paid half proves the refusal is about the missing key, not the list |
| AC-34 | agents → `test_a_fork_to_a_provider_without_a_key_goes_vidbyte_paid_and_never_receives_the_unproven_key` | A | The kimi fork receives K_u | The kimi POST must have exactly three headers and no K_u |
| AC-35 | match → `test_a_malformed_explicit_vidbyte_key_is_refused_at_construction_without_reading_the_environment` | U | A malformed key accepted until the first call | Construction is inside `assertRaises` with `RecordingEnviron` showing no read |
| AC-36 | acc (AC-12 test, mistral DIRECT row) | A | A DIRECT mistral call refused or sent with the wrong key | The exact vendor URL and bearer are asserted |
| AC-37 | agents → `test_an_aggregate_needs_every_spec_built_models_key_unless_its_list_holds_none`, `test_an_aggregate_with_no_provider_keys_sends_every_child_call_vidbyte_paid`; match → `test_several_primaries_each_need_a_key_and_the_first_without_one_is_named` | I | A missing proposer key accepted | The first keyless primary must be named; prebuilt children add no primary |
| AC-38 | agents → `test_a_lone_unproven_key_binds_to_the_agents_own_provider_and_its_openai_backup_goes_vidbyte_paid`, `test_two_unproven_sk_keys_for_a_deepseek_agent_with_an_openai_backup_are_refused_as_ambiguous` | A | The D-29 lone-key rule missing or over-applied | The backup POST must carry no K_ds |
| AC-39 | match → `test_a_hand_built_record_whose_key_does_not_fit_its_provider_is_refused_at_construction` | U | A hand-built record trusted blindly | Four bad records, each must raise M-20 naming provider and index; a valid record without the primary's key is accepted |
| AC-40 | modes → `test_an_environment_key_with_an_inner_space_is_refused_in_auto_and_direct`, `test_a_relayed_key_longer_than_512_characters_needs_direct`, `test_a_key_of_exactly_512_characters_still_relays` | I | An unsendable key reaches the HTTP layer | The boundary (512 relays, 513 refused) and the DIRECT escape are both asserted |
| AC-41 | sess → `test_a_restored_openai_child_rebuilds_its_roots_record_and_accepts_only_its_own_key`, `test_a_restored_kimi_child_keeps_the_unproven_key_on_deepseek_and_goes_vidbyte_paid` | I | A restored child re-matches against its own provider (M-6) or moves K_u | The restored record is compared to the root's, and the kimi POST is searched for K_u |
| AC-42 | match → `test_an_unproven_sk_key_beside_a_proven_openai_key_is_refused_in_both_orders`, `test_a_key_no_configured_provider_can_take_names_the_configured_providers` | U | An `sk-` key silently dropped beside a proven OpenAI key | Both orders; M-7 must name both indexes |

### Invariants, decisions, and edge cases not already named above

| Spec ID | Test (file → name) | Level | Failure it catches | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| INV-2, FR-7 | wire → `test_each_served_provider_relays_its_own_key_in_the_header_and_nowhere_else`, `test_the_header_carries_the_stripped_key_from_the_list_or_the_environment` | I | The key also in the body or another header | The whole request (`flat`) is searched; the header occurs once |
| INV-3 | wire → `test_a_key_for_another_provider_is_never_sent_with_this_call` | I | A neighbour's key relayed | The list holds both keys; only one may appear |
| INV-4, D-8, EC-37 | wire → `test_an_adapter_called_directly_in_auto_sees_only_the_placeholder`; managed selection adapter test | I | A relay key reaches an adapter called directly | The adapter's own auth header is asserted to equal the placeholder |
| INV-5, INV-6, D-7 | modes → `test_credentials_follow_table_r_and_read_only_what_each_mode_needs` | U | A mode reads a variable it must not | `RecordingEnviron` reads per row |
| INV-7, M-9 | modes → `test_gateway_modes_without_a_vidbyte_key_raise_the_tagged_error_from_validate_credentials_and_the_runner` | U | One of the three entry points does not refuse | All three are asserted |
| INV-8, D-23 | modes → `test_every_unserved_provider_and_any_endpoint_is_refused_at_construction_in_both_gateway_modes` | U | Refusal only at the runner | Construction inside `assertRaises`, and no `*_API_KEY` read |
| INV-9, INV-10 | prop → both tests | U | Order or environment dependence; a dropped entry | Exhaustive permutations of seeded lists in two environments; both outcomes must each be more than 1/8 of cases |
| INV-12 | modes → `test_a_relay_runner_keeps_its_keys_after_the_environment_changes`; managed selection pinning test | I | Per-call environment reads | The environment is changed after construction and the old keys must be sent |
| INV-14, D-30 | sess → `test_export_records_the_mode_and_the_matched_names_and_no_key`, `test_a_restored_root_still_needs_its_own_providers_key`, `test_a_checkpoint_written_before_this_change_restores_auto_and_is_matched_as_a_root` | I | Keys in checkpoints; wrong `key_providers` | Serialized checkpoints are searched for each key |
| INV-16 | wire → `test_a_call_without_a_provider_key_sends_exactly_the_three_base_commit_headers` and the managed pack | I | A paid call changes | Exact header set and envelope |
| INV-17 | fail → `FailureAssertions.assert_credential_safe` (every failure test) | I | Excerpt, `__cause__`, `__context__`, or body text | Each is asserted on every raised error |
| INV-18, D-14 | modes → `test_decision_keeps_its_own_missing_key_message_while_text_names_the_new_ways_out`; managed selection Decision test | U | Decision's message changed | Exact string for Decision |
| INV-20 | wire → `RelayCapAndFloorTests` (two tests); managed wire floor test | I | A relay call loses the cap or the 630 s floor | Exact cap values 100, 40,000, and default 32,768; floor and NaN |
| INV-21, EC-27, EC-28 | wire → `RelayResendTests` (two tests) | I | A re-send drops or changes the key | Every attempt's headers compared; 502 sent three times |
| INV-23 | agents → `test_building_an_agent_reads_no_api_key_variable` | U | Construction reads the environment | `RecordingEnviron` |
| INV-24, M-18 | match → `ConfiguredPrimaryTests` (five tests) | U | Missing primary key accepted | Positive and negative halves |
| INV-25, D-2, D-29 | match → `test_unique_assignment_binds_each_unproven_key_to_its_one_possible_owner`, `test_a_lone_unproven_key_binds_to_the_one_keyless_primary_that_takes_it` | U | Guessed binding | Binding asserted per provider |
| INV-26, M-10, M-11 | match → `VidbyteEntryTests`; managed selection credential test | U | Malformed key accepted until a call | Construction inside `assertRaises` |
| D-13 | match → `test_a_matched_record_passes_through_unchanged_with_no_primary_check` | U | A record re-matched | Equality and no INV-24 check |
| D-25, M-5 | match → `test_two_different_vidbyte_keys_are_refused_naming_their_indexes` | U | Two Vidbyte keys accepted | Both indexes named |
| D-26 | contract → `test_the_old_keyword_raises_a_type_error_naming_it` (FallbackModel half); settings validation `test_explicit_fallback_model_is_kept_as_given_and_takes_no_key_of_its_own` | S | `FallbackModel` keeps a key field | `TypeError` required |
| D-32 | modes → `test_a_key_of_exactly_512_characters_still_relays` | I | Off-by-one at the cap | 512 must relay |
| EC-13, M-14 | acc and modes → `test_find_provider_api_key_reads_the_record_then_the_variable_and_refuses_a_vidbyte_value` | U | A Vidbyte value in a provider variable relayed | Refusal names the variable and `VIDBYTE_API_KEY` |
| EC-14 | wire → `test_a_provider_variable_is_trusted_by_its_name` | I | An env key format-checked like a list entry | An xai-shaped key in the variable relays |
| EC-21 | modes → `test_direct_with_an_explicit_vidbyte_key_never_sends_it` | I | DIRECT sends the Vidbyte key | Request search plus no `VIDBYTE_API_KEY` read |
| EC-38 | wire → `ConcurrentRelayTests` | I | Concurrent calls swap keys | Per-call gateway records each call's headers |
| FR-1, FR-3, FR-5, FR-6, D-20, names | contract → `NamesAndConstantsTests`, `RecordLayoutTests`, `SignatureTests` | S | Wrong names, field orders, exports, or defaults | Exact lists and values from §8.5 and §12.3 |

## 2. Tests deliberately not written

- **AC-28 (lint, C017, full gate):** a gate, not a pytest test. `python lint/run.py` passes on the red pack (`SDK-LINT: PASS`); `run_ci.py` belongs to the implementer.
- **`credential_mismatch`, Q-3 to Q-6 (all "no"), NG-1 to NG-19:** rejected or out of scope. No test asserts the backend relay, fee-only billing, the Sentry scrub, the vidbyte-cli rename, or a live call (NG-15).
- **`hypothesis` property tests:** not installed and NFR-6 forbids new dependencies. `prop` uses a seeded `random.Random` and `itertools.permutations` instead.
- **`tests/test_harness_redaction.py` changes:** it is on the §13 "Not superseded" list. The AC-22 list and tuple cases live in `sec` (spec defect 4).
- **A Decision-mode relay:** INV-18 says Decision is unchanged; covered only by message equality.
- **A repr case for `AgentFallbackSettings`:** after D-26 it holds no key, so a repr test could not fail.
- **Network-level checks of the gateway's own behaviour on `X-Vidbyte-Provider-Key`:** owned by the companion run `byok-fee-relay`.
- **A test of the exact wording of table M and table G beyond the facts columns:** the spec says the wording is the implementer's; tests bind the facts only.

## 3. Red run

Command: `env -u DEEPSEEK_API_KEY PYTHONPATH=C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-byok-api-keys python -m pytest -q -p no:cacheprovider`, at HEAD `661fe8bf` plus these test changes (no production code changed).

- Baseline before S2 (same command, base tests): **3912 passed, 13 skipped**.
- Red run: **295 failed, 3727 passed, 13 skipped, 7 errors in 39.47s** (4,042 tests = 3,925 + 117 new).
- New pack: **117 failed, 0 passed**.
- Superseded tests: **178 failed + 7 setup errors**, all in the files listed in §5. No failure is in an untouched file, so none is pre-existing (the base run had none).

Failure reasons, grouped (every one is the feature being absent, never a bad import or a typo):

| Count | Reason |
|---|---|
| 113 | `AttributeError: DIRECT` (106 in a test, 7 in `setUp`): `TextModelMode.DIRECT` does not exist yet |
| 38 + 2 | `JevAgentSettings` / `JevRunBriefSettings` reject `api_keys` |
| 30 + 6 + 3 | `BaseAgent` rejects `api_keys`, `vidbyte_api_key`, `model_mode` |
| 28 | `TextModelConfig` rejects `api_keys` / `vidbyte_api_key` |
| 29 | `vidbyte.lib.registries.provider_keys` does not exist |
| 6 + 6 | `AggregateAgent` / `AgentRoleSettings` reject `api_keys` |
| 5 + 3 + 1 | `ProviderKeys`, `TextCredentials`, `VIDBYTE_PROVIDER_KEY_HEADER` cannot be imported |
| 32 | Behaviour assertions: refusal not raised at construction (8), `TypeError` not raised for an old keyword (2), call went vendor-direct instead of relaying (2), base wording ("Missing API key … Pass api_key", "Vidbyte managed openai request failed: …", the old streaming message), base field orders and signatures, the manual script still using `api_key=` (`scripts/test-new-runners.py:315`), no relay header, the harness redactor leaving the second key, the guards not classifying `api_keys`, `FallbackModel(api_key=)` still accepted |

The managed pack's `test_managed_text_failures.py:126-146` (the §13 "must stay green" test) passes.

## 4. Notes for the implementer

- **Seams the tests use.** `RUNNER_TRANSPORT_TARGET` (`vidbyte.lib.runners.text.HttpTransport`) for agents that build their own runner; the gateway's retry wait is patched where `vidbyte.lib.http.vidbyte_gateway` looks up `asyncio`. Keep both lookups where they are.
- **Private seams read by tests:** `TextModelRunner._config` (via `AgentFallback.build_runner(i)._config.credentials()`), as `test_agent_settings_validation.py` already did at base, and `BaseAgent._runner_for_model()` plus the non-text runner's `_config.api_key` (AC-23). Keep both where they are.
- **`AgentFallbackSettings.resolved_models(primary=…)`** is still called (with a keyless `FallbackModel`) by `FallbackApiKeyInheritanceTests`; the spec keeps it (row 18).
- **Provider strings with spaces.** `test_aggregate_agent.py` keeps `ProposerSpec(" DeepSeek ", …)` as a primary; the matcher must normalise it as deepseek, as the base runner already does.
- **Error types.** An impossible `TextCredentials` combination is asserted as `ConfigurationError` (the spec does not name one). `create_runner`/`create_runner_for_modality` with `api_key` for a text model must raise `ConfigurationError` (M-17), not `TypeError` (spec defect 2).
- **Repr list.** `AgentFallback` is checked by repr; at base its repr already omits keys, so keep `__repr__` credential-free (row 18 says unchanged).
- **Order of checks in `AUTO`** with `OPENAI_API_KEY=vb_live_…` and no `VIDBYTE_API_KEY`: the tests assert only `error_kind`, so either M-9 or M-14 may win.
- **Fakes.** Every fake is built by concatenation; anything with `vb_live_` reuses `VIDBYTE_KEY` or `VIDBYTE_API_KEY_PREFIX`. Do not "simplify" them into literals (C020, push protection).
- **Run the pack** with `DEEPSEEK_API_KEY` unset; this machine exports a real one.

## 5. Superseded tests updated

All rows are from spec §13. Protective intent is kept in every case; no assertion was loosened beyond what the cited spec ID requires. "Rename" = `api_key=` → `api_keys=[<fake that matches the provider per table F/A>]`, plus `mode`/`model_mode=TextModelMode.DIRECT` where the test expects vendor-direct traffic.

| File | Test | Spec ID | What changed |
|---|---|---|---|
| `tests/features/sdk_managed_text/test_managed_text_selection.py` | module constants, `EXPECTED_TEXT_CONFIG_FIELDS`, `run_text` | M-9, M-11, D-24, FR-15 | `MISSING_VIDBYTE_KEY`/`NON_STRING_TEXT_KEY` replaced by M-9/M-11 fact tuples and the unchanged Decision message; field list has `api_keys` third and `vidbyte_api_key` last; `run_text` takes `api_keys` and `direct=` |
| same | `test_key_fall_through_…` → `test_key_resolution_relays_provider_keys_through_the_gateway_and_sends_only_direct_calls_to_the_vendor` | INV-1, INV-2, D-25, EC-13, D-7 | 11 rows: relay header in `AUTO`, vendor only in `DIRECT`, a list Vidbyte entry is the bearer; a Vidbyte key in a provider variable is refused (M-14) |
| same | `test_without_a_selectable_key_…` → `test_without_a_usable_key_each_mode_refuses_before_any_request` | INV-7, INV-8 | openrouter/mistral in `AUTO` → M-12 naming `DIRECT`; `DIRECT` → M-8; openai `AUTO` with no Vidbyte key → M-9 |
| same | `test_explicit_managed_mode_uses_the_vidbyte_key_and_never_reads_the_provider_env_var` | INV-5, D-25 | Vidbyte key via `vidbyte_api_key` and via a list entry; no relay header |
| same | `test_managed_credential_failures_raise_tagged_configuration_errors_before_any_request` | M-9, M-11, INV-26 | Explicit malformed keys refused when the config is built; environment ones at the runner |
| same | `test_managed_state_refuses_a_custom_endpoint_while_a_byok_proxy_still_works` | INV-8, D-23, M-13, EC-17 | Every gateway mode refuses at construction naming `DIRECT`; the proxy works in `DIRECT` |
| same | `test_managed_state_refuses_every_provider_the_gateway_does_not_serve` | M-12, D-11, D-23 | `vidbyte_api_key=`; message must name `TextModelMode.DIRECT` |
| same | `test_streaming_refuses_managed_state_but_still_streams_byok_beside_a_vidbyte_key` | INV-11, D-10, M-15 | `AUTO` with a provider key now refused too; refusal names `DIRECT` and `TextModelRunner` with `details["mode"]`; BYOK stream uses `DIRECT` |
| same | `test_managed_runner_stays_managed_…` → `test_gateway_runners_keep_their_pinned_credentials_after_env_changes` | INV-12, INV-2 | Second half: an `AUTO` relay runner keeps its relayed key and Vidbyte key after the environment changes |
| same | `test_vidbyte_key_alone_manages_text_but_not_image_video_audio_or_embedding` | FR-2 | `is_vidbyte_managed()` → `credentials().uses_gateway`; non-text half unchanged |
| same | `test_text_config_appends_mode_last_…` → `test_text_config_keeps_its_field_order_and_rejects_a_mode_that_is_not_the_enum` | D-24, D-20 | Enum gains `DIRECT`; positional list → `api_keys`; positional string refused (M-1) |
| same | `test_text_config_repr_hides_the_api_key` | INV-4 | Cases for `api_keys` (Vidbyte and provider) and `vidbyte_api_key` |
| same | `test_adapters_see_only_the_placeholder_key_in_managed_state_even_when_called_directly` | FR-2, EC-37, D-25 | `vidbyte_api_key=`; new `AUTO` relay-key case must not reach the adapter |
| same | `test_decision_and_text_share_one_managed_key_resolver_with_unchanged_messages` | D-14, INV-18 | Decision keeps its exact message; text in `VIDBYTE_MANAGED` gives M-9 facts |
| `tests/features/sdk_managed_text/test_managed_text_acceptance.py` | `test_each_managed_provider_posts_its_byok_body_once_to_the_gateway_and_parses_the_answer` | FR-15, INV-16 | Oracle runs in `DIRECT` with a per-provider matching fake; three-header assertion kept |
| same | `test_provider_key_keeps_…` → `test_provider_key_relays_in_auto_and_keeps_its_byok_request_byte_identical_in_direct` | INV-2, INV-6 | Goldens in `DIRECT` (gemini with an `AQ.` fake); openai and kimi relay in `AUTO`; anthropic stays paid with no header |
| `tests/features/sdk_managed_text/test_managed_text_wire_contract.py` | `byok_body` | FR-15 | `DIRECT` oracle with matching fakes, asserted to reach the vendor |
| same | `test_each_managed_attempt_gets_the_630_second_floor_and_a_nan_timeout_resolves_to_the_floor` | INV-20, INV-6 | New relay case gets 630 s at the gateway; the 30 s case runs in `DIRECT` |
| `tests/features/sdk_managed_text/test_managed_text_deadline.py` | `test_validate_refuses_an_endpoint_when_auto_selects_the_vidbyte_key` | D-23, M-13 | Refused at construction, inside `assertRaises`; names `DIRECT` |
| same | `test_validate_refuses_an_explicit_vidbyte_key_for_a_provider_the_gateway_does_not_serve` | D-25, D-23, M-12 | `vidbyte_api_key=`; refused at construction; names `DIRECT` |
| `tests/features/sdk_managed_text/FEATURE.md`, `README.md` | contract text | G-1, INV-1, INV-2 | "BYOK must see no change at all" replaced by the relay/`DIRECT` contract; key selection, headers, pinning, invariants, failure modes, README log |
| `tests/test_text_model_runner.py` | all six tests | INV-6 | Rename, `DIRECT` |
| `tests/test_streaming_text_runner.py` | all 17 tests | INV-11 | Rename, `DIRECT` (gemini with an `AIza` fake built at runtime) |
| `tests/test_sync_runner_default_transport.py` | `test_default_streaming_runner_yields_chunks` | INV-11 | Rename, `DIRECT`; non-text tests unchanged |
| `tests/test_config_validation.py` | `test_text_config_resolves_explicit_api_key`, `…_env_api_key`, `…_rejects_bad_temperature` | FR-2 | Rename, `DIRECT` (`resolved_api_key()` returns the key only in `DIRECT`) |
| `tests/test_openrouter_provider.py` | six tests | EC-15 | Rename with an `sk-or-` fake, `DIRECT`; `:78` becomes M-4 |
| `tests/test_deepseek_provider.py` | `test_zero_argument_tool_call_returns_empty_text`, `_text`, `_agent` (8 tests) | Rename | Rename, `DIRECT` |
| `tests/test_gemini_tool_wire_format.py` | `fake_gemini`, `strict_gemini`, `_runner` (10 tests) | Rename | Rename with a runtime `AIza` fake, `DIRECT` |
| `tests/test_output_schema_provider_dialect.py` | three tests | D-2, D-28 | Rename, `DIRECT`; mistral keeps `["k"]` |
| `tests/test_prompt_opens_tool_exchange.py` | `_chat_wire`, `_anthropic_wire`, `_responses_wire`, streaming, `call` (11 tests) | INV-11 | Rename, `DIRECT` |
| `tests/test_compatible_provider_text.py` | `_text` | Rename | Rename with per-provider fakes, `DIRECT` |
| `tests/test_prompt_sits_at_run_boundary.py` | `_runner` (8 tests) | Rename | Rename with per-provider fakes, `DIRECT` |
| `tests/test_agent_tool_loop.py` | `boom` | Rename | Rename, `DIRECT` |
| `tests/test_agent_modality_routing.py` | `test_model_identity_routes_to_image_runner` | D-12 | Image config gets `api_keys.key_for(provider)` |
| `tests/features/sdk_model_usage/test_billed_unusable_replies.py` | parametrize list; `test_billed_refusal_then_fallback_bills_both_calls` | EC-37, D-26 | Rename, `DIRECT`; the fallback's key moves into the agent's `api_keys` |
| `tests/features/sdk_model_usage/test_nested_usage_bill.py` | module keywords | Rename | `api_keys=["d-mock"]`, `model_mode=DIRECT` |
| `tests/test_agent_fork_isolation.py` | six fork-key tests (two renamed) | D-13, INV-15, INV-3, EC-47 | Children carry the parent's record; per-call keys checked with `find_provider_api_key` or the child runner's `credentials()`; a glm child in `AUTO` is refused (D-23); a key bound to deepseek never reaches kimi |
| `tests/test_agent_settings_validation.py` | `test_agent_rejects_a_bare_string_fallback`; `FallbackApiKeyInheritanceTests` (one renamed); `test_fallback_runner_inherits_the_agent_timeout`; `test_provider_prefixed_primary_model_builds_a_chain` | D-13, D-26, INV-15 | `FallbackModel` has no key; each chain runner's relayed key read from its config; the timeout test runs in `DIRECT` (a gateway runner floors at 630 s) |
| `tests/test_aggregate_agent.py` | four key tests (one renamed) | D-13, D-27, INV-24, INV-25, EC-33 | Every child carries the record; the openai proposer and aggregator need their own key (M-18); a mixed panel with one unproven key is refused (M-19) |
| `tests/test_durable_sessions.py` | `test_export_captures_config_and_omits_secret`, `test_live_fork_keeps_agent_key_and_never_stores_it`, `test_cold_resume_and_continue_take_the_agent_key`, `test_file_store_resume_keeps_fallback_chain_without_keys` | INV-14, FR-11, D-30 | `model_mode`/`key_providers` in `runtime_config`; no key in the checkpoint; resume re-matches to the root's record |
| `tests/test_session_failures.py` | `test_fork_recovery_keeps_live_agent_key` | FR-11 | Recovery child carries the live record |
| `tests/test_fork_tool.py` | `test_model_chosen_provider_swap_does_not_pass_parent_api_key` | D-13, EC-47 | Child carries the record; no openai key from it |
| `tests/test_handoff_agent.py` | `test_side_agents_keep_source_fallback_chain_and_timeout` | FR-11 | Rename |
| `tests/test_context_minimal_fanout_agents.py` | `_settings` | Rename | `AgentRoleSettings(api_keys=…)` |
| `tests/test_jev_agent.py` | `test_normalizes_provider_and_redacts_both_keys` | INV-4 | Rename |
| `tests/test_jev_run_brief.py` | `_settings`, `test_defaults_and_provider_validation`, `test_uses_main_provider_by_default_and_allows_an_independent_provider` | EC-34, D-13, D-27 | Rename; the writer's own list is its own root |
| `tests/test_jev_compute.py`, `…_clone.py`, `…_situations.py`, `…_swarm.py` | `_settings` / `_agent` | Rename | `api_keys=["sk-main-key"]` (an `sk-` key the openai primary takes) |
| `tests/test_codex_failure_recovery.py` | module header | wording | Prose now names `api_keys` |
