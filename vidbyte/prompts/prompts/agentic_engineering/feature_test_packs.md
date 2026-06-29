# Description
Feature test packs turn testing into first-class executable feature intent. Traditional developers often treated testing as an afterthought because comprehensive suites were tedious to write, but agents can draft broad test suites quickly enough that the bottleneck has moved from typing effort to testing judgment. This principle exploits that shift: testing should become one of the most robust, secure, adversarial, and behavior-defining parts of the repository, not a thin confidence layer added after implementation. A feature test pack is a folder of tests organized around one durable behavior boundary, with a `FEATURE.md` file that defines the feature and each test file acting as a different strategy for trying to break that feature's promise. The agent's job is not to confirm that its patch runs; the agent's job is to use cheap test generation to make code safer, harder to regress, and easier for future agents to modify correctly. The best test pack becomes a second implementation of intent: it explains the feature, attacks the feature, and gives future agents executable proof of what must continue to work.

# Intent
The intent of feature test packs is to make testing first-class in the repository because agents have changed the economics of test creation. When test writing is slow, teams underinvest in deep edge cases, security checks, stress coverage, negative paths, and realistic integration behavior. When an agent can produce suites quickly, the correct move is to spend that speed on robust, secure, complex, adversarial coverage that would have been too tedious to write by hand. The test suite should then feed back into development: future agents can read the feature definition, run the pack, see the protected contracts, and make code changes with stronger guardrails than prose documentation alone can provide.

This principle closes a known agent failure mode: models can generate a large number of tests without becoming good testers. They often test only the path they just implemented, mock away the collaborator that carries the actual risk, use toy fixtures that avoid real edge cases, assert private implementation steps that should be free to change, and never try to break the code. Feature test packs make the model adopt the mindset of a hostile but constructive tester: define the feature, describe the promised behavior, search for ways to collapse the system, cover the ordinary path, cover the abusive path, and leave behind a suite that makes later coding more reliable.

# Goal
This skill file teaches you everything you need to know to write tests while coding: how to define the feature being protected, how to create a feature-owned test pack, how to think like a good tester, how to choose many complementary testing strategies, how to distinguish useful tests from easy-to-pass tests, and how to leave future agents with executable intent they can trust before changing the code.

# Definition of a Feature
* A feature is the smallest durable behavior boundary the codebase promises to preserve. It is a named capability with a trigger or caller, inputs or preconditions, observable outcomes, invariants that must remain true, meaningful failure modes, and a reason someone would care if it broke.
* A feature is not automatically a file, class, folder, endpoint, helper function, module, or package. Those are implementation containers. A feature is the behavior those containers exist to provide.
* A feature can be user-facing, API-facing, agent-facing, runtime-facing, or maintainer-facing. `checkout payment authorization`, `prompt enum/catalog synchronization`, `context compaction preserving required messages`, `tool permission enforcement`, `trace redaction`, and `retry policy for idempotent calls` are features because each names a behavior a caller relies on.
* A feature should be named without referencing implementation location. If the only name you can give it is `utils.py`, `BillingService`, `routes/`, or `parse_config()`, you have probably named a container rather than a feature.
* A right-sized feature is neither a whole subsystem nor a private implementation detail. `billing` is too broad; `format_billing_date` is usually too narrow. `billing invoice generation` or `subscription cancellation keeps access until paid period end` is the right kind of durable behavior boundary.
* A private helper deserves its own feature test pack only when it encodes a reusable invariant, domain rule, public contract, or high-risk transformation that multiple features depend on. Otherwise, test it inside the parent feature's pack.
* A feature can span multiple files. In fact, the most important features often do. If a behavior crosses an API route, service layer, data model, event publisher, and external provider, the test pack belongs to the behavior, not to any one file in that chain.
* A feature can be smaller than a product feature. `tool permission enforcement rejects disallowed tools` is a feature even if it is one part of a larger agent runtime. The boundary is durable because a caller can rely on it, a bug report could name it, and a regression would matter.
* A feature boundary must be stable through refactors. If moving code between files changes the name of the feature, the boundary was probably implementation-shaped rather than behavior-shaped.

# Feature Identification Rubric
Use this rubric before creating a feature test pack. If most answers are yes, the behavior deserves feature-level test organization.

* Can a user, API consumer, downstream agent, or maintainer describe this behavior without naming the source file that implements it?
* Could a bug report plausibly be titled after this behavior?
* Could a changelog entry mention this behavior?
* Does the behavior have acceptance criteria or a product/user expectation?
* Does it own at least one invariant that must remain true after refactors?
* Does it cross a meaningful boundary, such as UI to API, API to service, service to database, runtime to provider, model to tool, or package to consumer?
* If the behavior broke, would the fix require understanding behavior rather than just syntax?
* Would a regression test be expected after a bug in this behavior?
* Does it have failure modes that are not obvious from one source file?
* Would a future agent benefit from finding all tests for this behavior in one folder?

# Feature Test Pack Structure
A feature test pack lives under `tests/features/<feature_slug>/`. The folder should begin broad: assume the feature deserves multiple testing strategies, then prune only the strategies that do not protect a real risk. The `FEATURE.md` file explains the feature being tested, which strategies are included, which strategies are intentionally omitted, and why.

```text
tests/features/<feature_slug>/
|-- FEATURE.md
|-- test_acceptance.py
|-- test_contract.py
|-- test_unit.py
|-- test_integration.py
|-- test_component.py
|-- test_e2e.py
|-- test_browser_interaction.py
|-- test_smoke.py
|-- test_regression.py
|-- test_edge_cases.py
|-- test_negative.py
|-- test_error_behavior.py
|-- test_security.py
|-- test_policy_permissions.py
|-- test_concurrency.py
|-- test_idempotency.py
|-- test_stress.py
|-- test_performance.py
|-- test_property.py
|-- test_fuzz.py
|-- test_metamorphic.py
|-- test_snapshot_golden.py
|-- test_migration_compatibility.py
|-- test_observability.py
|-- test_chaos_failure_injection.py
|-- test_compatibility.py
|-- test_accessibility.py
|-- test_serialization_roundtrip.py
|-- test_cli_package_smoke.py
|-- fixtures.py
`-- factories.py
```

* `FEATURE.md` is mandatory. It defines the feature, its purpose, its contract, its real callers, its failure inventory, the selected testing strategies, and the omitted strategies. Without it, the folder is just a pile of tests.
* Test files are selected by risk, but the default stance is ambitious coverage. A pure transformation feature may need unit, property, metamorphic, edge-case, fuzz, and regression tests. An agent tool policy feature may need contract, integration, security, permission, error behavior, regression, observability, concurrency, and idempotency tests. A UI workflow may need acceptance, browser interaction, accessibility, smoke, snapshot, error behavior, and negative tests.
* `fixtures.py` and `factories.py` exist to make realistic setup cheap. Prefer named factories that encode domain meaning over anonymous dictionaries copied into every test.
* Existing module-based tests do not have to be moved immediately. When working in a legacy repo, create the feature pack for new or touched behavior and cross-reference existing module tests in `FEATURE.md`.
* If the codebase uses another language, preserve the concept and adapt filenames to local convention: `*.spec.ts`, `*.test.ts`, `*_test.go`, or test suites in a nested package are all acceptable if the feature pack remains discoverable.

# Feature Test Pack FEATURE.md
Every feature pack `FEATURE.md` must be short enough to read before opening test files and specific enough to route an agent to the right testing strategy. Its first job is to explain the actual feature being tested, not merely list files. A future agent should be able to read `FEATURE.md` and understand what behavior users, callers, maintainers, or other agents rely on before reading the implementation.

```markdown
# Feature: <feature name>

## High-Level Feature Description
What this feature does, why it exists, who depends on it, and what would become unsafe, broken, expensive, or confusing if it regressed. Explain the behavior in product, SDK, runtime, or caller terms before naming implementation files.

## Contract
What behavior the codebase promises to preserve. Write this in user, caller, or system terms, not implementation terms.

## Actors / Callers
Who triggers this feature: user workflow, API consumer, SDK caller, provider callback, scheduled job, agent runtime, CLI command, or internal subsystem.

## Inputs and Preconditions
Valid inputs, required state, permissions, configuration, environment, and assumptions that must hold before the feature runs.

## Observable Outcomes
Return values, persisted state, emitted events, UI state, logs, traces, metrics, files, network calls, errors, or other outputs that prove behavior.

## State Transitions
Allowed before/after states, forbidden transitions, idempotency expectations, rollback behavior, and partial failure behavior.

## Invariants
Rules that must remain true for every implementation.

## External Dependencies
Databases, providers, model APIs, browser APIs, filesystems, queues, clocks, caches, auth layers, and services that shape test boundaries.

## Known Failure Modes
Ways this feature can break, including edge cases, abuse cases, concurrency races, dependency failures, and resource limits.

## Historical Regressions
Bugs, review comments, production incidents, and footguns this pack now protects.

## Test Suite Map
Which test files exist, what each protects, and when to run them.

## Omitted Testing Strategies
Which test strategies were intentionally not added and why the omission is acceptable.
```

* The Contract section is the anchor. If a test does not protect something in the contract, invariants, outcomes, or failure modes, challenge whether it belongs.
* The High-Level Feature Description section is the orientation layer. It should let an agent understand the feature's purpose and stakes before it decides which tests to open.
* The Omitted Testing Strategies section prevents false completeness. It is acceptable to omit stress tests for a tiny pure parser; it is not acceptable to omit the rationale.
* Keep `FEATURE.md` stable through refactors. File paths can appear in the suite map, but the main contract should describe behavior that survives file movement.

# Failure Inventory Before Test Generation
Before writing tests, write the failure inventory in `FEATURE.md`. This inventory is the bridge between "I can generate tests quickly" and "I am generating the right tests." It forces the agent to name what can break before it reaches for pytest, Playwright, a fuzz harness, or a mock. The inventory should be specific enough that a future agent can look at a test and know which risk it protects.

```text
Feature:
Core contract:
Actors / callers:
Valid inputs:
Invalid inputs:
Preconditions:
Observable outcomes:
State transitions:
Invariants:
External boundaries:
Security and policy risks:
Concurrency and idempotency risks:
Historical bugs:
Resource limits:
Observability promises:
What an easy generated test would miss:
```

# Testing Philosophy
A good testing agent is not trying to prove that code is fine. It is trying to break the system in every way that matters while leaving behind clear evidence of what survived. The model should look for edges, abuse cases, stale state, invalid permissions, malformed data, concurrency races, unrealistic mocks, provider failure, secret leakage, cost explosions, and regressions that a shallow happy-path test would never see. Easy tests are not a virtue. A test that always passes because it asserts only that something returned is worse than no test because it creates false confidence.

The goal is maximum meaningful coverage, not maximum file count. A good test is not one that passes; a good test is one that would fail for the right reason if the feature promise were broken. Start by considering as many testing strategies as the feature could justify, especially negative, security, policy, regression, stress, property, fuzz, observability, and failure-injection strategies that human teams often skip because they are tedious. Then remove only the strategies that do not protect a real contract, invariant, risk, or failure mode. The correct mindset is: "How can this feature collapse, and what executable evidence would catch that collapse before users, maintainers, or future agents do?"

# Universal Strategy Rubric
Apply this rubric inside every testing strategy section. Each strategy has different tactics, but the difference between good and bad tests stays consistent.

1. Name the feature promise, not the implementation mechanism.
2. Assert observable behavior that a caller, user, system, trace, file, or downstream agent can verify.
3. Include realistic valid inputs with domain-shaped fixtures, not only tiny toy objects.
4. Include invalid, missing, duplicate, stale, unauthorized, malformed, or adversarial inputs when the strategy allows it.
5. Mock outside the feature boundary, never the behavior the strategy claims to prove.
6. Make the failure diagnostic: the name, setup, and assertion should reveal the broken promise.
7. Ensure the test would fail if a guard were deleted, a branch inverted, a policy bypassed, state skipped, or redaction removed.
8. Avoid pinning private steps unless the private protocol is itself the feature contract.
9. Control nondeterminism from time, randomness, provider output, ordering, concurrency, and generated IDs.
10. Tie regression tests to the old failure mechanism, not just the new code path.
11. Prefer multiple narrow tests over one broad test that fails with no signal.
12. Delete or strengthen tests that increase coverage while proving no meaningful behavior.

# Testing Strategy Playbook
Each section below describes one testing strategy. For every strategy you include, write tests that use the universal rubric, then document in `FEATURE.md` why that strategy belongs in the pack.

## 1. Acceptance Tests
Acceptance tests prove the feature satisfies a stakeholder-visible behavior. They belong when a product owner, SDK consumer, maintainer, or user could say the feature is complete or broken without knowing the implementation. Good acceptance tests follow the workflow language in the feature contract and assert final outcomes, not private calls. Bad acceptance tests click or call one thing, assert `not None`, and never prove the user-visible promise.

### Good Tests
* Name the acceptance behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the acceptance promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the acceptance strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat acceptance coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: prompt catalog loading. Tests: `test_user_can_fetch_agentic_engineering_feature_test_pack`, `test_catalog_lists_feature_test_pack_in_family`, `test_direct_import_returns_same_prompt_text`, `test_missing_asset_blocks_catalog_load`, `test_descriptor_key_mismatch_reports_configuration_error`, `test_readme_quick_reference_matches_family_keys`, `test_system_prompt_routes_testing_tasks_to_feature_pack`, `test_packaged_distribution_includes_markdown_asset`, `test_catalog_error_names_missing_file`, `test_feature_pack_prompt_has_goal_and_conclusion`.
* Example feature: context compaction. Tests: `test_long_trace_compacts_under_budget`, `test_required_system_message_survives_compaction`, `test_recent_user_intent_remains_visible`, `test_tool_error_context_is_not_dropped`, `test_empty_history_returns_empty_result`, `test_compaction_reports_removed_segments`, `test_compaction_preserves_message_order`, `test_budget_exact_boundary_is_allowed`, `test_oversized_required_message_returns_diagnostic_error`, `test_compacted_context_can_resume_agent_run`.
* Why this suite exists: acceptance tests define "done" from outside the code. They prevent future agents from optimizing internals while breaking the caller's real workflow.

## 2. Contract Tests
Contract tests protect stable boundaries between consumers and providers: SDK APIs, exported symbols, schemas, event payloads, prompt keys, CLI arguments, tool schemas, and provider adapters. They belong when another module, package, user, service, or agent relies on a shape or behavior remaining stable. Good contract tests exercise both sides of the contract when possible. Bad contract tests check only the producer and never prove the consumer can still use the interface.

### Good Tests
* Name the contract behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the contract promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the contract strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat contract coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: prompt enum/catalog synchronization. Tests: `test_every_prompt_enum_has_catalog_record`, `test_every_catalog_record_has_prompt_enum`, `test_direct_imports_are_exported_in_all`, `test_family_lookup_returns_registered_subprompts`, `test_missing_markdown_path_fails_fast`, `test_duplicate_prompt_value_is_rejected`, `test_source_url_is_present_for_each_record`, `test_prompt_text_is_non_empty`, `test_unknown_family_raises_configuration_error`, `test_agentic_engineering_feature_test_pack_key_is_stable`.
* Example feature: MCP tool schema. Tests: `test_tool_schema_includes_required_name`, `test_tool_schema_rejects_unknown_argument`, `test_tool_schema_accepts_optional_description`, `test_client_payload_matches_server_protocol`, `test_server_response_roundtrips_to_client_type`, `test_missing_required_field_reports_contract_error`, `test_extra_provider_field_is_ignored_or_reported`, `test_version_field_matches_supported_protocol`, `test_error_payload_preserves_request_id`, `test_schema_export_has_no_private_fields`.
* Why this suite exists: contract tests give future agents a hard boundary. If an implementation changes, the contract decides whether it was a valid refactor or a breaking change.

## 3. Unit Tests
Unit tests protect isolated decision rules, validation, parsing, formatting, normalization, reducers, scoring, and pure transformations. They belong when a feature has logic that can be proven without external systems. Good unit tests cover each branch and invariant with clear inputs and outputs. Bad unit tests test trivial getters, private plumbing, or duplicated implementation logic.

### Good Tests
* Name the unit behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the unit promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the unit strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat unit coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: retry classification. Tests: `test_timeout_is_retryable`, `test_auth_error_is_not_retryable`, `test_payment_charge_is_not_retried`, `test_idempotency_key_allows_safe_retry`, `test_retry_count_stops_at_limit`, `test_jitter_stays_inside_bounds`, `test_missing_status_code_is_non_retryable`, `test_rate_limit_reads_retry_after`, `test_provider_quota_error_is_reported`, `test_cancelled_request_is_not_retried`.
* Example feature: prompt key normalization. Tests: `test_spaces_convert_to_underscore`, `test_uppercase_converts_to_lowercase`, `test_existing_snake_case_is_stable`, `test_empty_key_is_rejected`, `test_key_with_path_separator_is_rejected`, `test_duplicate_normalized_key_is_rejected`, `test_unicode_key_reports_clear_error`, `test_dot_separator_preserves_family_boundary`, `test_private_prefix_is_rejected`, `test_roundtrip_prompt_id_is_stable`.
* Why this suite exists: unit tests make small rules cheap to verify. They should never be the whole feature pack when the feature is orchestration.

## 4. Integration Tests
Integration tests protect collaborators working together inside the codebase. They belong when the feature's risk lives in the seam between modules. Good integration tests keep real internal collaborators and replace only expensive external systems. Bad integration tests mock every collaborator until only the current file remains.

### Good Tests
* Name the integration behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the integration promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the integration strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat integration coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: tool execution policy. Tests: `test_policy_runs_before_executor`, `test_denied_tool_never_reaches_executor`, `test_allowed_tool_receives_validated_arguments`, `test_policy_error_is_returned_to_agent`, `test_audit_log_records_denial`, `test_budget_middleware_blocks_expensive_tool`, `test_sandbox_mode_is_forwarded_to_executor`, `test_tool_result_is_serialized_for_context`, `test_executor_exception_preserves_policy_metadata`, `test_parallel_tool_calls_keep_independent_policy_results`.
* Example feature: prompt loading through MCP. Tests: `test_prompts_list_reads_catalog_records`, `test_prompts_get_returns_markdown_text`, `test_unknown_prompt_name_reports_protocol_error`, `test_family_filter_uses_catalog_key`, `test_package_data_missing_surfaces_configuration_error`, `test_handler_does_not_duplicate_records`, `test_prompt_description_is_preserved`, `test_mcp_response_matches_expected_shape`, `test_catalog_cache_is_reused`, `test_handler_keeps_error_context`.
* Why this suite exists: many agent-introduced bugs happen at seams. Integration tests prevent each module from being correct alone while the feature is broken together.

## 5. Component Or Service Tests
Component or service tests protect one subsystem through its public boundary. They belong when the feature has a service-level API with internal helpers. Good component tests call the service like a real caller and assert the service contract. Bad component tests reach into private helpers and call that coverage.

### Good Tests
* Name the component or service behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the component or service promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the component or service strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat component or service coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: compaction service. Tests: `test_service_preserves_required_messages`, `test_service_reports_removed_tokens`, `test_service_rejects_impossible_budget`, `test_service_handles_empty_context`, `test_service_keeps_latest_user_request`, `test_service_records_compaction_strategy`, `test_service_is_deterministic_for_same_input`, `test_service_handles_provider_summary_failure`, `test_service_does_not_mutate_original_messages`, `test_service_exposes_diagnostic_metadata`.
* Example feature: provider client. Tests: `test_client_sends_standard_chat_payload`, `test_client_maps_provider_error_to_sdk_error`, `test_client_redacts_api_key_in_logs`, `test_client_respects_timeout`, `test_client_streams_chunks_in_order`, `test_client_handles_empty_response`, `test_client_retries_retryable_status`, `test_client_preserves_request_id`, `test_client_rejects_unsupported_model`, `test_client_records_token_usage`.
* Why this suite exists: component tests give strong confidence without the noise of full end-to-end tests.

## 6. End-To-End Tests
End-to-end tests protect a complete workflow through the highest practical boundary. They belong for critical user, CLI, API, package, or agent flows where many layers must cooperate. Good end-to-end tests assert several externally visible milestones. Bad end-to-end tests merely start the system and call that comprehensive.

### Good Tests
* Name the end-to-end behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the end-to-end promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the end-to-end strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat end-to-end coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: SDK prompt access. Tests: `test_installed_sdk_loads_prompt_family`, `test_cli_lists_agentic_engineering_prompts`, `test_python_import_exposes_direct_prompt`, `test_mcp_handler_returns_prompt_text`, `test_missing_package_data_fails_during_startup`, `test_readme_example_runs_as_written`, `test_prompt_enum_access_works_after_install`, `test_wheel_contains_markdown_assets`, `test_no_network_is_required_for_prompt_access`, `test_error_output_names_missing_asset`.
* Example feature: agent tool execution. Tests: `test_agent_selects_allowed_tool_and_gets_result`, `test_agent_denied_tool_returns_policy_error`, `test_tool_result_is_added_to_context`, `test_trace_contains_tool_call`, `test_budget_limit_stops_repeated_calls`, `test_executor_failure_reaches_final_response`, `test_parallel_tools_join_results`, `test_agent_respects_sandbox_path`, `test_audit_log_records_execution`, `test_run_finishes_without_private_secret_leak`.
* Why this suite exists: end-to-end tests prove the feature exists as a real system behavior, not only as compatible modules.

## 7. Browser Interaction And Manual Agent Tests
Browser interaction tests protect real UI behavior: clicks, typing, focus, DOM state, visual state, network behavior, screenshots, and downloadable artifacts. They belong when the feature depends on browser state or human workflow. Good browser tests exercise the real interaction and assert visible outcomes. Bad browser tests only assert that a page loaded.

### Good Tests
* Name the browser interaction and manual agent behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the browser interaction and manual agent promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the browser interaction and manual agent strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat browser interaction and manual agent coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: export dialog. Tests: `test_open_export_dialog_from_toolbar`, `test_filename_input_receives_focus`, `test_empty_filename_shows_error`, `test_export_button_disabled_while_saving`, `test_network_failure_shows_retry`, `test_success_downloads_file`, `test_cancel_closes_without_request`, `test_keyboard_escape_closes_dialog`, `test_download_name_matches_input`, `test_error_message_is_announced`.
* Example feature: trace viewer. Tests: `test_trace_list_loads_recent_runs`, `test_click_run_opens_detail_panel`, `test_filter_by_status_updates_rows`, `test_failed_step_expands_error_context`, `test_secret_value_is_redacted`, `test_copy_trace_id_writes_clipboard`, `test_empty_state_is_visible`, `test_large_trace_scrolls_without_overlap`, `test_refresh_preserves_selected_run`, `test_mobile_layout_keeps_actions_visible`.
* Why this suite exists: browser tests catch broken workflows that unit and API tests cannot see.

## 8. Smoke Tests
Smoke tests protect basic boot, import, startup, and main-path availability. They belong for packages, CLIs, servers, plugin entrypoints, prompt catalogs, and feature flags. Good smoke tests are fast and narrow. Bad smoke tests are mistaken for correctness tests.

### Good Tests
* Name the smoke behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the smoke promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the smoke strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat smoke coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: package import. Tests: `test_import_vidbyte_package`, `test_import_prompts_module`, `test_import_prompt_enum`, `test_import_mcp_server_module`, `test_import_agent_runtime`, `test_import_tool_policy`, `test_import_context_compaction`, `test_import_provider_client`, `test_import_public_all`, `test_import_has_version`.
* Example feature: CLI startup. Tests: `test_cli_help_runs`, `test_cli_version_runs`, `test_cli_prompts_help_runs`, `test_cli_lists_prompt_families`, `test_cli_reports_unknown_command`, `test_cli_loads_without_network`, `test_cli_uses_packaged_assets`, `test_cli_exit_code_zero_for_help`, `test_cli_exit_code_nonzero_for_bad_args`, `test_cli_error_has_actionable_text`.
* Why this suite exists: smoke tests are early warning lights. They do not replace acceptance, contract, or failure-mode tests.

## 9. Regression Tests
Regression tests protect a known bug's actual failure mechanism. They belong after every bug fix, review comment, incident, or recurring footgun. Good regression tests fail against the old broken behavior. Bad regression tests only cover the new happy path and would have passed before the fix.

### Good Tests
* Name the regression behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the regression promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the regression strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat regression coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: trace redaction. Tests: `test_api_key_in_error_metadata_is_redacted`, `test_nested_secret_in_tool_args_is_redacted`, `test_secret_in_provider_payload_is_redacted`, `test_redaction_preserves_nonsecret_fields`, `test_multiple_secret_values_are_all_removed`, `test_redacted_trace_still_serializes`, `test_redaction_error_does_not_emit_secret`, `test_case_insensitive_secret_key_is_redacted`, `test_secret_in_list_item_is_redacted`, `test_regression_fixture_matches_old_leak_shape`.
* Example feature: prompt asset loading. Tests: `test_missing_markdown_asset_fails_fast`, `test_bad_descriptor_does_not_cache_partial_family`, `test_enum_value_typo_reports_prompt_id`, `test_duplicate_family_key_is_rejected`, `test_direct_import_missing_from_all_is_detected`, `test_package_data_lookup_uses_resource_api`, `test_windows_path_separator_does_not_break_lookup`, `test_empty_prompt_file_is_rejected`, `test_descriptor_without_prompts_is_rejected`, `test_old_missing_asset_fixture_fails`.
* Why this suite exists: regression tests are memory. They keep future agents from stepping on the exact failure already discovered.

## 10. Edge Case Tests
Edge case tests protect weird but valid boundaries: empty, null, min, max, duplicate, ordering, timezone, encoding, pagination, limits, legacy data, and exact thresholds. They belong whenever the input space has meaningful edges. Good edge tests are specific about which boundary matters. Bad edge tests use one empty case and call the category done.

### Good Tests
* Name the edge case behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the edge case promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the edge case strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat edge case coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: token budget compaction. Tests: `test_empty_messages_returns_empty`, `test_one_message_under_budget_is_unchanged`, `test_message_exactly_at_budget_is_allowed`, `test_message_one_token_over_budget_compacts`, `test_required_message_over_budget_errors`, `test_duplicate_messages_keep_order`, `test_unicode_tokens_count_correctly`, `test_large_number_of_messages_compacts`, `test_zero_budget_is_rejected`, `test_boundary_summary_preserves_latest_user_message`.
* Example feature: pagination. Tests: `test_first_page_returns_first_items`, `test_last_page_with_partial_items`, `test_empty_collection_returns_empty_page`, `test_negative_page_is_rejected`, `test_page_size_zero_is_rejected`, `test_max_page_size_is_allowed`, `test_over_max_page_size_is_rejected`, `test_duplicate_sort_keys_keep_stable_order`, `test_cursor_after_deleted_item_recovers`, `test_unicode_filter_value_is_handled`.
* Why this suite exists: edge cases catch the bugs agents miss when they only test the obvious path.

## 11. Negative Tests
Negative tests protect rejection behavior: malformed inputs, forbidden actions, impossible states, unsupported modes, wrong permissions, and missing dependencies. They belong whenever "must reject" is part of the feature contract. Good negative tests assert the specific reason for rejection. Bad negative tests only assert that some exception occurred.

### Good Tests
* Name the negative behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the negative promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the negative strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat negative coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: tool attachment. Tests: `test_unknown_transport_is_rejected`, `test_missing_server_name_is_rejected`, `test_empty_tool_schema_is_rejected`, `test_duplicate_tool_name_is_rejected`, `test_disallowed_tool_is_rejected`, `test_invalid_json_arguments_are_rejected`, `test_tool_outside_sandbox_is_rejected`, `test_permission_prompt_denial_blocks_attach`, `test_failed_attach_does_not_mutate_catalog`, `test_error_names_invalid_field`.
* Example feature: prompt descriptor parsing. Tests: `test_missing_name_is_rejected`, `test_missing_key_is_rejected`, `test_prompts_not_object_is_rejected`, `test_prompt_without_path_is_rejected`, `test_path_outside_family_is_rejected`, `test_source_url_not_string_is_rejected`, `test_empty_markdown_file_is_rejected`, `test_duplicate_subprompt_key_is_rejected`, `test_unknown_descriptor_field_is_rejected_or_ignored`, `test_failed_descriptor_does_not_cache`.
* Why this suite exists: negative tests prove the guardrails, not just the useful path.

## 12. Error Behavior Tests
Error behavior tests protect the quality of failure output: type, message, violated invariant, expected-vs-actual detail, remediation context, redaction, chaining, and related files. They belong for important failure paths and agentic error classes. Good error tests inspect the structured context. Bad error tests check only `raises(Exception)`.

### Good Tests
* Name the error behavior behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the error behavior promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the error behavior strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat error behavior coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: configuration error. Tests: `test_error_type_is_configuration_error`, `test_error_names_missing_prompt_asset`, `test_error_includes_expected_descriptor_path`, `test_error_includes_actual_missing_path`, `test_error_includes_fix_approach`, `test_error_redacts_private_root`, `test_error_links_related_files`, `test_error_preserves_original_exception`, `test_error_message_is_stable_for_agents`, `test_error_does_not_cache_partial_catalog`.
* Example feature: provider failure. Tests: `test_timeout_error_is_retryable`, `test_auth_error_is_not_retryable`, `test_error_redacts_api_key`, `test_error_includes_provider_name`, `test_error_includes_request_id`, `test_error_preserves_status_code`, `test_error_maps_rate_limit_retry_after`, `test_error_keeps_safe_payload_excerpt`, `test_error_records_test_reference`, `test_error_does_not_drop_trace_context`.
* Why this suite exists: good error behavior turns production failures into repairable context for future agents.

## 13. Security Tests
Security tests protect authentication, authorization, injection, path traversal, confused deputy, unsafe deserialization, secret leakage, privilege escalation, and tenant boundaries. They belong whenever the feature handles identity, permissions, user input, tools, files, secrets, or external payloads. Good security tests are adversarial. Bad security tests only prove the allowed user can do the allowed action.

### Good Tests
* Name the security behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the security promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the security strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat security coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: workspace file access. Tests: `test_path_traversal_is_rejected`, `test_symlink_escape_is_rejected`, `test_absolute_path_outside_root_is_rejected`, `test_allowed_relative_path_reads_file`, `test_denied_read_does_not_emit_file_contents`, `test_error_redacts_private_path`, `test_hidden_file_policy_is_enforced`, `test_null_byte_path_is_rejected`, `test_unicode_normalization_cannot_escape_root`, `test_audit_log_records_denial`.
* Example feature: tool execution. Tests: `test_disallowed_tool_name_is_denied`, `test_tool_alias_cannot_bypass_policy`, `test_arguments_cannot_request_shell_escape`, `test_secret_arg_is_redacted_in_trace`, `test_untrusted_provider_tool_is_denied`, `test_confused_deputy_context_is_blocked`, `test_permission_denial_prevents_executor_call`, `test_policy_bypass_attempt_is_audited`, `test_budget_bypass_is_rejected`, `test_error_does_not_echo_secret`.
* Why this suite exists: security tests are where the model should most aggressively try to break the system.

## 14. Permission And Policy Tests
Permission and policy tests protect deterministic boundaries around model actions: allowed tools, sandbox modes, approvals, budgets, provider allowlists, rate limits, middleware gates, and user scopes. They belong in agent systems because the model's request must never be the final authority. Good policy tests assert the policy layer overrides unsafe model intent. Bad policy tests trust the model request.

### Good Tests
* Name the permission and policy behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the permission and policy promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the permission and policy strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat permission and policy coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: tool policy. Tests: `test_allowed_tool_executes`, `test_disallowed_tool_is_denied`, `test_unknown_tool_is_denied`, `test_case_variant_tool_name_is_denied`, `test_permission_denial_blocks_executor`, `test_budget_limit_blocks_tool`, `test_sandbox_readonly_blocks_write_tool`, `test_policy_error_reaches_agent_context`, `test_policy_denial_is_audited`, `test_policy_cache_does_not_leak_between_users`.
* Example feature: provider policy. Tests: `test_allowed_provider_runs`, `test_disallowed_provider_is_denied`, `test_missing_model_scope_is_denied`, `test_expensive_model_requires_approval`, `test_rate_limit_blocks_run`, `test_policy_denial_has_remediation`, `test_override_token_is_validated`, `test_user_scope_is_isolated`, `test_fallback_provider_respects_allowlist`, `test_denied_provider_key_is_redacted`.
* Why this suite exists: policy tests make model autonomy safe by proving deterministic code wins.

## 15. Concurrency Tests
Concurrency tests protect races, locks, duplicate requests, stale reads, ordering, simultaneous writes, async task joins, and worker coordination. They belong when multiple callers can touch the same state. Good concurrency tests create actual overlapping operations or deterministic simulations. Bad concurrency tests run two operations sequentially and call it coverage.

### Good Tests
* Name the concurrency behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the concurrency promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the concurrency strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat concurrency coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: actor inbox. Tests: `test_parallel_senders_preserve_per_sender_order`, `test_duplicate_message_id_is_ignored`, `test_concurrent_ack_only_applies_once`, `test_stale_read_does_not_drop_message`, `test_lock_release_after_exception`, `test_parallel_pollers_do_not_double_deliver`, `test_shutdown_waits_for_inflight_message`, `test_timeout_unblocks_waiter`, `test_backpressure_limit_is_enforced`, `test_audit_log_records_concurrent_conflict`.
* Example feature: prompt catalog cache. Tests: `test_parallel_loads_create_one_cache`, `test_failed_load_does_not_poison_cache`, `test_concurrent_family_reads_are_stable`, `test_cache_reset_during_read_is_safe`, `test_duplicate_descriptor_load_is_deduped`, `test_threaded_access_returns_same_text`, `test_partial_cache_is_never_visible`, `test_lock_releases_on_configuration_error`, `test_repeated_imports_are_stable`, `test_concurrent_missing_asset_errors_are_consistent`.
* Why this suite exists: concurrency tests catch bugs that are invisible to single-threaded happy paths.

## 16. Idempotency Tests
Idempotency tests protect retry safety, duplicate events, repeated requests, exactly-once or at-least-once semantics, payment operations, queue workers, and repeated agent actions. They belong whenever an operation can run more than once. Good idempotency tests assert no duplicate state and the correct response on repeats. Bad idempotency tests only assert that the second call does not crash.

### Good Tests
* Name the idempotency behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the idempotency promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the idempotency strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat idempotency coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: retrying tool result write. Tests: `test_same_tool_call_id_writes_once`, `test_retry_returns_existing_result`, `test_duplicate_event_does_not_emit_second_trace`, `test_different_tool_call_id_writes_new_result`, `test_partial_write_recovers_without_duplicate`, `test_concurrent_duplicate_calls_coalesce`, `test_failed_first_call_can_retry`, `test_idempotency_key_expiry_is_respected`, `test_replay_preserves_original_timestamp`, `test_audit_log_records_duplicate_suppression`.
* Example feature: payment charge. Tests: `test_same_idempotency_key_charges_once`, `test_retry_after_timeout_returns_original_charge`, `test_new_key_creates_new_charge`, `test_failed_validation_does_not_record_key`, `test_concurrent_charge_requests_create_one_charge`, `test_duplicate_webhook_is_ignored`, `test_partial_provider_response_is_reconciled`, `test_cancelled_charge_is_not_replayed`, `test_idempotency_conflict_reports_error`, `test_audit_log_links_retries`.
* Why this suite exists: idempotency tests prevent retries from becoming duplicate work, duplicate cost, or duplicate user-visible effects.

## 17. Stress Tests
Stress tests protect behavior under high volume, repeated calls, large payloads, many files, many users, long contexts, many tool calls, or large prompt catalogs. They belong when scale can change behavior. Good stress tests use realistic high-volume shapes and assert invariants. Bad stress tests use ten items and call that stress.

### Good Tests
* Name the stress behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the stress promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the stress strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat stress coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: prompt catalog loading. Tests: `test_loads_large_number_of_prompt_records`, `test_repeated_loads_do_not_drift`, `test_many_direct_imports_are_exported`, `test_large_markdown_asset_loads`, `test_many_family_keys_keep_order`, `test_repeated_missing_asset_errors_do_not_leak_cache`, `test_many_descriptor_files_are_discovered`, `test_catalog_keys_remain_unique_at_scale`, `test_large_readme_index_matches_records`, `test_stress_run_completes_under_memory_limit`.
* Example feature: context window. Tests: `test_compacts_thousand_message_trace`, `test_large_tool_outputs_are_summarized`, `test_many_required_messages_are_preserved_or_error`, `test_repeated_compactions_are_stable`, `test_large_unicode_content_counts_tokens`, `test_many_provider_errors_do_not_drop_recent_intent`, `test_large_trace_keeps_order`, `test_stress_budget_exact_boundary`, `test_many_parallel_compactions_do_not_share_state`, `test_stress_diagnostics_include_removed_counts`.
* Why this suite exists: stress tests reveal scale-shaped bugs before production traffic or giant agent traces do.

## 18. Load And Performance Tests
Load and performance tests protect latency, throughput, memory, query count, token usage, provider calls, render time, and cost ceilings. They belong when users or infrastructure rely on a budget. Good performance tests use stable inputs, thresholds, and measured units. Bad performance tests measure wall-clock casually on unstable environments.

### Good Tests
* Name the load and performance behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the load and performance promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the load and performance strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat load and performance coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: prompt catalog. Tests: `test_catalog_loads_under_expected_ms`, `test_cached_lookup_is_constant_time_enough`, `test_family_lookup_does_not_reload_assets`, `test_direct_import_has_no_network_call`, `test_large_family_memory_stays_under_budget`, `test_repeated_keys_lookup_has_stable_latency`, `test_descriptor_validation_does_not_scan_unrelated_dirs`, `test_error_path_fails_fast`, `test_package_asset_read_count_is_bounded`, `test_performance_failure_reports_record_count`.
* Example feature: context compaction. Tests: `test_compaction_under_token_budget_has_time_ceiling`, `test_large_trace_memory_stays_bounded`, `test_provider_summary_calls_are_limited`, `test_no_extra_token_count_passes`, `test_performance_scales_with_message_count`, `test_timeout_returns_diagnostic_error`, `test_parallel_compactions_respect_worker_limit`, `test_cost_estimate_stays_under_budget`, `test_cache_reuse_reduces_tokenization_work`, `test_performance_report_names_input_size`.
* Why this suite exists: performance tests convert "this should be cheap" into an executable budget.

## 19. Property-Based Tests
Property-based tests protect invariants across generated valid inputs. They belong for parsers, serializers, reducers, compaction, ranking, scheduling, calculations, and normalization. Good property tests generate domain-valid inputs and assert universal properties. Bad property tests generate arbitrary nonsense and then blame the code for rejecting it.

### Good Tests
* Name the property-based behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the property-based promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the property-based strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat property-based coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: context compaction. Tests: `test_required_system_prompt_is_never_dropped`, `test_output_never_exceeds_budget_when_possible`, `test_message_order_is_preserved`, `test_no_duplicate_messages_are_created`, `test_latest_user_message_survives`, `test_empty_valid_sequence_roundtrips`, `test_removed_count_matches_difference`, `test_compaction_is_deterministic`, `test_metadata_ids_remain_unique`, `test_invalid_impossible_budget_errors`.
* Example feature: key normalization. Tests: `test_normalized_key_is_lowercase`, `test_normalization_is_idempotent`, `test_valid_keys_roundtrip`, `test_normalized_keys_do_not_contain_spaces`, `test_invalid_separator_is_rejected`, `test_distinct_valid_keys_remain_distinct_or_conflict`, `test_empty_key_is_never_valid`, `test_unicode_policy_is_consistent`, `test_family_prompt_split_roundtrips`, `test_normalization_does_not_strip_required_family`.
* Why this suite exists: property tests let agents cover broad input spaces without hand-writing every example.

## 20. Fuzz Tests
Fuzz tests protect parsers and boundary handlers against malformed, adversarial, random, or corrupted input. They belong for JSON, Markdown, CLI args, model outputs, webhooks, file formats, and network payloads. Good fuzz tests assert safe failure or preserved invariants. Bad fuzz tests expect every random input to succeed.

### Good Tests
* Name the fuzz behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the fuzz promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the fuzz strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat fuzz coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: descriptor parser. Tests: `test_random_bytes_do_not_crash_parser`, `test_malformed_json_reports_configuration_error`, `test_deeply_nested_descriptor_is_rejected_safely`, `test_random_missing_fields_do_not_cache`, `test_weird_unicode_paths_are_rejected`, `test_huge_string_field_has_size_error`, `test_array_instead_of_object_is_rejected`, `test_fuzz_error_has_no_private_path`, `test_partial_records_are_not_exposed`, `test_valid_minimal_descriptor_still_loads`.
* Example feature: model tool arguments. Tests: `test_random_json_arguments_do_not_execute_tool`, `test_malformed_json_returns_validation_error`, `test_nested_command_injection_is_rejected`, `test_huge_argument_value_is_rejected`, `test_unknown_argument_is_reported`, `test_null_required_argument_is_rejected`, `test_unicode_argument_is_normalized_or_rejected`, `test_fuzz_denial_does_not_call_executor`, `test_error_redacts_argument_secrets`, `test_valid_generated_arguments_execute`.
* Why this suite exists: fuzz tests teach agents to protect boundaries where the system receives untrusted shape.

## 21. Metamorphic Tests
Metamorphic tests protect relationships that should remain true after controlled input transformations. They belong when exact expected output is hard but invariants are clear. Good metamorphic tests compare related runs. Bad metamorphic tests force one brittle golden output.

### Good Tests
* Name the metamorphic behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the metamorphic promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the metamorphic strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat metamorphic coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: context compaction. Tests: `test_adding_irrelevant_old_message_preserves_latest_intent`, `test_reordering_unrelated_old_segments_does_not_change_required_prefix`, `test_duplicate_optional_context_does_not_duplicate_output`, `test_increasing_budget_keeps_all_previous_output`, `test_removing_optional_messages_does_not_remove_required_message`, `test_equivalent_tokenization_keeps_budget_property`, `test_summary_provider_wording_changes_do_not_drop_ids`, `test_compacting_twice_is_stable`, `test_adding_metadata_preserves_content_order`, `test_transform_failure_reports_same_invariant`.
* Example feature: prompt lookup. Tests: `test_family_lookup_and_direct_lookup_return_same_text`, `test_descriptor_order_does_not_change_key_set`, `test_whitespace_in_markdown_preserves_nonempty_prompt`, `test_reloading_catalog_returns_same_records`, `test_source_url_change_does_not_change_prompt_text`, `test_key_case_policy_is_consistent`, `test_package_and_source_tree_lookup_match`, `test_json_field_order_does_not_change_records`, `test_adding_unrelated_family_does_not_change_existing_family`, `test_cache_reset_preserves_lookup_result`.
* Why this suite exists: metamorphic tests let agents verify deep relationships without overspecifying exact outputs.

## 22. Snapshot And Golden Tests
Snapshot and golden tests protect stable generated output, prompt text bundles, schemas, CLI output, rendered files, and compatibility artifacts. They belong when exact output is a public or reviewable contract. Good golden tests snapshot stable artifacts and normalize unstable fields. Bad golden tests freeze timestamps, IDs, order, or debug noise.

### Good Tests
* Name the snapshot and golden behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the snapshot and golden promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the snapshot and golden strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat snapshot and golden coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: prompt catalog docs. Tests: `test_quick_reference_matches_golden`, `test_agentic_engineering_system_prompt_matches_expected_sections`, `test_feature_pack_prompt_has_required_headers`, `test_prompt_descriptor_json_matches_golden_order`, `test_cli_prompt_list_output_matches_golden`, `test_generated_prompt_index_has_no_missing_family`, `test_snapshot_normalizes_absolute_paths`, `test_snapshot_excludes_build_timestamp`, `test_changed_prompt_requires_explicit_snapshot_update`, `test_golden_diff_names_prompt_key`.
* Example feature: API schema. Tests: `test_tool_schema_matches_golden`, `test_error_payload_schema_matches_golden`, `test_prompt_record_schema_matches_golden`, `test_openapi_fragment_matches_golden`, `test_cli_help_matches_golden`, `test_event_payload_matches_golden`, `test_redacted_trace_artifact_matches_golden`, `test_snapshot_normalizes_uuid`, `test_schema_change_requires_compat_note`, `test_golden_is_semantically_valid_json`.
* Why this suite exists: golden tests protect artifacts users or agents consume exactly.

## 23. Migration And Backward Compatibility Tests
Migration and backward compatibility tests protect old data, new data, mixed versions, rollback assumptions, serialized artifacts, caches, config, and installed packages. They belong when users may already have state. Good compatibility tests load real old fixtures. Bad compatibility tests test only the new schema.

### Good Tests
* Name the migration and backward compatibility behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the migration and backward compatibility promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the migration and backward compatibility strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat migration and backward compatibility coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: trace schema. Tests: `test_old_trace_without_tool_ids_loads`, `test_new_trace_with_tool_ids_loads`, `test_mixed_trace_versions_load`, `test_removed_field_has_default`, `test_unknown_future_field_is_ignored`, `test_old_secret_field_is_redacted`, `test_migration_preserves_run_id`, `test_failed_migration_reports_version`, `test_rollback_shape_can_be_read`, `test_old_fixture_is_not_generated_by_new_factory`.
* Example feature: prompt descriptor. Tests: `test_descriptor_without_source_url_has_compat_error_or_default`, `test_old_family_key_still_aliases`, `test_new_subprompt_does_not_break_old_family_lookup`, `test_old_package_data_layout_loads`, `test_new_package_data_layout_loads`, `test_mixed_prompt_family_versions_are_rejected_clearly`, `test_old_enum_value_remains_supported`, `test_removed_prompt_has_migration_note`, `test_rollback_descriptor_is_valid`, `test_compat_error_names_upgrade_path`.
* Why this suite exists: migration tests stop future agents from assuming only fresh state exists.

## 24. Observability Tests
Observability tests protect logs, traces, metrics, audit records, debug artifacts, and diagnostic metadata. They belong when operators, support workflows, or agents rely on emitted context. Good observability tests assert useful fields and secret absence. Bad observability tests assert that "something was logged."

### Good Tests
* Name the observability behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the observability promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the observability strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat observability coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: agent run trace. Tests: `test_trace_records_run_id`, `test_trace_records_tool_call_ids`, `test_trace_records_provider_name`, `test_trace_redacts_api_key`, `test_trace_records_policy_denial`, `test_trace_records_retry_count`, `test_trace_preserves_error_chain`, `test_trace_records_token_usage`, `test_trace_has_no_prompt_secret`, `test_trace_links_final_response`.
* Example feature: prompt catalog loading. Tests: `test_catalog_load_metric_records_family_count`, `test_configuration_error_log_names_descriptor`, `test_missing_asset_error_has_prompt_key`, `test_success_log_has_cache_hit_flag`, `test_debug_artifact_excludes_prompt_secrets`, `test_audit_records_direct_import_generation`, `test_metric_cardinality_is_bounded`, `test_trace_records_package_lookup`, `test_error_log_has_remediation`, `test_observability_is_disabled_when_configured`.
* Why this suite exists: observability tests make the system debuggable after it breaks.

## 25. Chaos And Failure Injection Tests
Chaos and failure-injection tests protect behavior under dependency timeouts, provider failures, network partitions, partial writes, retry exhaustion, filesystem errors, queue failures, and clock problems. They belong when resilience and recovery are part of the contract. Good chaos tests assert recovery, rollback, or diagnostic behavior. Bad chaos tests inject failure and never inspect aftermath.

### Good Tests
* Name the chaos and failure injection behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the chaos and failure injection promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the chaos and failure injection strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat chaos and failure injection coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: provider call. Tests: `test_timeout_returns_retryable_error`, `test_rate_limit_uses_retry_after`, `test_partial_stream_preserves_received_chunks`, `test_provider_500_triggers_retry`, `test_retry_exhaustion_returns_context_packet`, `test_auth_failure_does_not_retry`, `test_network_partition_does_not_drop_history`, `test_cancelled_request_cleans_up`, `test_provider_failure_redacts_key`, `test_fallback_provider_respects_policy`.
* Example feature: catalog load. Tests: `test_filesystem_read_failure_reports_path`, `test_json_parse_failure_does_not_cache`, `test_markdown_read_failure_names_prompt`, `test_importlib_resource_failure_is_wrapped`, `test_partial_descriptor_failure_blocks_family`, `test_cache_lock_releases_after_failure`, `test_failure_during_direct_import_generation_rolls_back`, `test_recovery_after_fixed_asset_loads`, `test_error_has_related_files`, `test_failure_metric_is_recorded`.
* Why this suite exists: chaos tests prove failure handling is real, not aspirational.

## 26. Compatibility Tests
Compatibility tests protect supported OS, Python, browser, provider, API, package, and protocol versions. They belong when the feature promises to work across environments. Good compatibility tests encode the support matrix or stable protocol shape. Bad compatibility tests assume the local runtime is the whole world.

### Good Tests
* Name the compatibility behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the compatibility promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the compatibility strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat compatibility coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: package data. Tests: `test_package_data_loads_on_windows_paths`, `test_package_data_loads_on_posix_paths`, `test_python_311_imports_package`, `test_wheel_install_in_clean_env_loads_assets`, `test_editable_install_loads_assets`, `test_zip_safe_resource_lookup_works`, `test_path_separator_does_not_affect_prompt_key`, `test_case_sensitive_lookup_is_explicit`, `test_old_supported_python_version_errors_clearly`, `test_dependency_free_import_still_works`.
* Example feature: MCP protocol. Tests: `test_prompts_list_matches_protocol_shape`, `test_prompts_get_matches_protocol_shape`, `test_unknown_prompt_error_matches_protocol`, `test_client_older_protocol_gets_compat_response`, `test_new_optional_field_is_backward_compatible`, `test_required_protocol_field_is_present`, `test_json_rpc_id_roundtrips`, `test_batch_request_behavior_is_supported_or_rejected`, `test_transport_specific_payload_is_stable`, `test_protocol_version_error_is_actionable`.
* Why this suite exists: compatibility tests prevent future agents from coding only for their local environment.

## 27. Accessibility Tests
Accessibility tests protect keyboard navigation, labels, focus order, semantic roles, contrast, screen reader names, and error announcements. They belong for UI features and browser workflows. Good accessibility tests use the interface the user experiences. Bad accessibility tests inspect pixels while ignoring whether a keyboard or screen reader can use the feature.

### Good Tests
* Name the accessibility behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the accessibility promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the accessibility strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat accessibility coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: export dialog. Tests: `test_open_button_has_accessible_name`, `test_dialog_has_role_dialog`, `test_filename_input_has_label`, `test_initial_focus_moves_to_filename`, `test_tab_order_reaches_actions`, `test_escape_closes_dialog`, `test_error_is_announced`, `test_export_button_disabled_state_is_exposed`, `test_focus_returns_to_trigger`, `test_keyboard_can_complete_export`.
* Example feature: trace viewer. Tests: `test_run_list_has_semantic_table_or_list`, `test_filter_input_has_label`, `test_failed_run_status_is_announced`, `test_expand_error_is_keyboard_accessible`, `test_focus_does_not_escape_panel`, `test_copy_button_has_accessible_name`, `test_empty_state_is_announced`, `test_color_status_has_text_label`, `test_mobile_actions_remain_reachable`, `test_error_details_are_readable_by_screen_reader`.
* Why this suite exists: accessibility tests make UI behavior robust for users and automation.

## 28. Serialization And Round-Trip Tests
Serialization and round-trip tests protect encode/decode behavior, persistence hydration, config loading, schema conversion, queue payloads, and artifact regeneration. They belong when data crosses a process, file, API, queue, or storage boundary. Good round-trip tests compare semantic equality and invariants. Bad round-trip tests serialize without deserializing.

### Good Tests
* Name the serialization and round-trip behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the serialization and round-trip promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the serialization and round-trip strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat serialization and round-trip coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: agent run record. Tests: `test_run_record_roundtrips_json`, `test_tool_calls_survive_roundtrip`, `test_error_context_survives_roundtrip`, `test_token_usage_survives_roundtrip`, `test_unknown_future_field_is_ignored`, `test_missing_optional_field_defaults`, `test_datetime_timezone_roundtrips`, `test_secret_is_redacted_before_serialization`, `test_binary_artifact_reference_roundtrips`, `test_semantic_equality_ignores_field_order`.
* Example feature: prompt descriptor. Tests: `test_descriptor_roundtrips_json`, `test_prompt_paths_survive_roundtrip`, `test_source_urls_survive_roundtrip`, `test_family_key_survives_roundtrip`, `test_unknown_field_policy_is_stable`, `test_missing_optional_description_reports_error`, `test_unicode_prompt_name_roundtrips`, `test_sorted_output_is_stable`, `test_invalid_roundtrip_is_rejected`, `test_package_manifest_regeneration_matches_descriptor`.
* Why this suite exists: round-trip tests catch silent data loss at boundaries.

## 29. CLI Package And Install Smoke Tests
CLI, package, and install smoke tests protect importability, entrypoints, package data, extras, command startup, installed-resource lookup, and example commands. They belong for SDKs, CLIs, plugins, and prompt catalogs. Good install smoke tests run from a clean environment or installed artifact. Bad install smoke tests only run from the source tree.

### Good Tests
* Name the cli package and install smoke behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the cli package and install smoke promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the cli package and install smoke strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat cli package and install smoke coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: SDK package. Tests: `test_wheel_installs_in_clean_env`, `test_import_vidbyte_after_install`, `test_prompt_assets_exist_after_install`, `test_direct_prompt_import_after_install`, `test_prompts_family_after_install`, `test_no_dev_dependency_required_for_import`, `test_package_version_is_available`, `test_pyproject_includes_prompt_data`, `test_readme_example_runs_after_install`, `test_missing_asset_error_is_clear_after_install`.
* Example feature: CLI entrypoint. Tests: `test_console_script_exists`, `test_cli_help_exit_zero`, `test_cli_version_exit_zero`, `test_cli_prompts_list_exit_zero`, `test_cli_bad_command_exit_nonzero`, `test_cli_runs_outside_repo_root`, `test_cli_uses_installed_assets`, `test_cli_error_has_no_traceback_for_user_error`, `test_cli_output_is_stable`, `test_cli_does_not_require_network_for_help`.
* Why this suite exists: install smoke tests catch packaging failures that source-tree tests miss.

## 30. Mutation Testing
Mutation testing checks the tests themselves by intentionally mutating production logic and requiring the suite to fail. It belongs for high-risk pure logic, money paths, security policy, parsers, reducers, and invariants where coverage percentage is not enough. Good mutation checks target meaningful logic changes. Bad mutation checks mutate irrelevant code or treat surviving mutants as acceptable without investigation.

### Good Tests
* Name the mutation testing behavior or risk in terms that match the feature contract in `FEATURE.md`.
* Assert a visible outcome, state transition, error, trace, artifact, or contract shape that proves the mutation testing promise.
* Use realistic actors, permissions, fixtures, configuration, legacy state, and external-boundary shape.
* Cover the ordinary successful path only after naming what the mutation testing strategy is meant to prove.
* Include boundary values, malformed input, duplicate work, stale state, abuse cases, or dependency failure when those risks exist.
* Mock only outside the feature boundary, and verify the boundary contract instead of the mocked implementation.
* Make the test name, setup, and assertion diagnostic enough to reveal the broken promise when it fails.
* Control nondeterminism from clocks, randomness, ordering, generated IDs, providers, retries, and concurrent execution.
* Tie each setup choice to a failure inventory item so the test protects a known feature risk.
* Identify a realistic production mutation that should break the test, then strengthen the assertion until that mutation is caught.

### Bad Tests
* Treat mutation testing coverage as a checkbox detached from the feature contract and failure inventory.
* Assert only that something returned, rendered, exited, saved, logged, or was not null.
* Mock the exact behavior the strategy claims to prove, leaving only the mock under test.
* Use toy fixtures that avoid permissions, old data, invalid combinations, limits, or realistic size.
* Pin private call order, helper names, temporary formatting, local paths, or other details callers cannot observe.
* Cover only happy paths while skipping denial, failure, missing input, stale state, and abuse cases.
* Duplicate production logic in assertions so the test and implementation can share the same defect.
* Use vague names such as `test_success`, `test_error`, `test_handles_case`, or `test_works`.
* Let timing, generated IDs, provider output, shared state, cache order, or randomness decide the result.
* Keep a test that would still pass if a guard were deleted, a policy bypassed, redaction removed, or the public contract broken.

* Example feature: tool policy. Mutations: `delete_disallowed_tool_guard`, `invert_allowlist_condition`, `skip_permission_check`, `remove_budget_gate`, `ignore_sandbox_mode`, `do_not_audit_denial`, `return_success_on_denial`, `drop_error_context`, `execute_before_policy`, `remove_secret_redaction`.
* Example feature: prompt catalog. Mutations: `skip_missing_asset_check`, `ignore_duplicate_enum_value`, `return_empty_prompt_text`, `skip_direct_import_export`, `allow_descriptor_without_key`, `cache_partial_family_on_error`, `ignore_package_data_failure`, `drop_source_url_validation`, `sort_keys_inconsistently`, `swallow_configuration_error`.
* Why this suite exists: mutation testing is the strongest check against easy-to-pass tests because it asks whether wrong code is actually caught.
# Things Not To Do
* Do not treat testing as post-implementation cleanup. The feature definition and failure inventory should shape implementation.
* Do not create a feature pack that contains only happy-path unit tests unless the feature genuinely has no other meaningful risks.
* Do not organize tests only around files when the behavior spans multiple files. File-based tests are allowed, but feature packs own feature intent.
* Do not stop at unit tests when the feature is an orchestration. A function can be correct while the feature is broken.
* Do not mock the behavior under test. Mock outside the feature boundary, not inside it.
* Do not assert incidental private implementation steps unless the internal protocol itself is the feature contract.
* Do not use toy fixtures that skip hard fields, permissions, legacy state, invalid combinations, or realistic object shape.
* Do not write a regression test that would have passed before the bug was fixed.
* Do not let coverage percentage stand in for behavioral protection. Coverage can be high while mutation resistance is low.
* Do not skip negative, security, permission, policy, stress, fuzz, or observability tests merely because they take more thought.
* Do not create every possible test file mechanically. Include many strategies by default, then omit only with a real feature-specific rationale.
* Do not leave `FEATURE.md` stale after adding or deleting a testing strategy.

# Checklist
* Before writing code, define the feature boundary in behavior terms and verify it has a trigger, inputs, outcomes, invariants, failure modes, and a reason someone would care if it broke.
* Before writing tests, create or update `tests/features/<feature_slug>/FEATURE.md`.
* Before choosing files, write the failure inventory and name what an easy generated test would miss.
* Start by considering many testing strategies, including negative, security, policy, stress, fuzz, observability, and failure-injection coverage.
* Omit a strategy only when `FEATURE.md` explains why the omission is safe.
* Write acceptance or contract tests before implementation-shaped unit tests when behavior is ambiguous.
* For every bug fix, add a regression test that fails against the old failure mechanism.
* For every security, permission, policy, parser, provider, or tool feature, include adversarial tests.
* For every retry-capable or concurrent feature, decide explicitly whether idempotency and ordering need tests.
* After writing a test, ask what production mutation would make it fail. If no realistic broken code fails the test, strengthen or delete it.
* After writing a test, verify the mock boundary: mocks must sit outside the feature boundary, never inside the behavior being proven.
* Before opening a pull request, read `FEATURE.md` and confirm the Test Suite Map, Omitted Testing Strategies, and Historical Regressions match the files you actually created.

# Code Examples

## Example 1: Feature test pack FEATURE.md

```markdown
# Feature: Prompt Catalog Loading

## High-Level Feature Description
Prompt catalog loading lets SDK users, agents, and MCP handlers retrieve prompt text through stable enum keys, family keys, and direct imports. The feature matters because prompt assets are packaged Markdown files, so a missing file, enum drift, or bad descriptor can break runtime behavior after installation. A future agent modifying prompt files should understand that the feature is not "read JSON"; it is "make every promised prompt reliably available through every public access path." If this feature regresses, agents may load stale guidance, package users may receive import errors, and catalog failures may become hard to diagnose.

## Contract
The prompt catalog loads every prompt family from packaged JSON and Markdown assets, exposes enum-keyed access through `Prompts().get(...)`, exposes family access through `Prompts().family(...)`, and fails fast when an enum value has no matching asset or a descriptor references a missing Markdown file.

## Actors / Callers
SDK users call `Prompts`, agents import direct prompt names, MCP server handlers list prompt records, and repository maintainers add new prompt families.

## Inputs and Preconditions
Prompt JSON descriptors must contain `name`, `description`, `key`, and `prompts`. Markdown-backed prompts must reference files packaged under `vidbyte/prompts/prompts`. Every flattened `family.prompt` key must have a matching `Prompt` enum member.

## Observable Outcomes
`Prompts().keys()` returns every enum member, direct imports exist in `vidbyte.prompts.__all__`, `Prompts().family("agentic_engineering")` returns all registered principle prompts, and malformed assets raise `ConfigurationError` before partial records are exposed.

## State Transitions
The catalog starts unloaded, loads once into class-level caches, then serves stable records. Failed loading must not expose a partial prompt family.

## Invariants
Every enum member has one asset. Every asset has one enum member. Every direct import name maps to the same text as `Prompts().get(...)`.

## External Dependencies
Python package data, `importlib.resources`, JSON parsing, Markdown asset files, and the `Prompt` enum.

## Known Failure Modes
Missing Markdown path, descriptor key typo, enum value drift, duplicate prompt value, direct import not exported, package data missing after install, stale README index.

## Historical Regressions
None yet. Add one line per fixed bug with the test that protects it.

## Test Suite Map
* `test_contract.py` protects enum/asset/direct import synchronization.
* `test_error_behavior.py` protects fail-fast diagnostics for malformed descriptors.
* `test_cli_package_smoke.py` protects installed package prompt loading.

## Omitted Testing Strategies
* Browser interaction omitted: prompt catalog loading has no UI.
* Accessibility omitted: prompt catalog loading has no user interface.
* Load testing omitted for now: prompt count is small, but stress coverage exists for repeated catalog loading.
```

## Example 2: Pytest folder layout

```text
tests/features/prompt_catalog_loading/
|-- FEATURE.md
|-- test_contract.py
|-- test_error_behavior.py
|-- test_cli_package_smoke.py
|-- fixtures.py
`-- factories.py
```

## Example 3: Contract test for enum/catalog synchronization

```python
def test_prompt_catalog_exports_every_enum_as_direct_import() -> None:
    prompt_module = importlib.import_module("vidbyte.prompts")
    prompts = Prompts()

    assert set(prompts.keys()) == set(Prompt)
    for prompt_key, import_name in prompts.import_names().items():
        assert import_name in prompt_module.__all__
        assert getattr(prompt_module, import_name) == prompts.get(prompt_key)
```

This test protects the public import contract. It does not assert how the catalog discovers files internally, so the loader can be refactored without breaking the test.

## Example 4: Regression test for missing Markdown asset detection

```python
def test_prompt_descriptor_missing_markdown_asset_fails_fast(tmp_path: Path) -> None:
    descriptor = {
        "name": "Broken",
        "description": "Broken prompt family",
        "key": "broken",
        "prompts": {
            "system_prompt": {
                "path": "missing.md",
                "source_url": "https://example.com/missing.md",
            }
        },
    }

    with pytest.raises(ConfigurationError, match="missing Markdown asset"):
        load_prompt_descriptor_for_test(descriptor, root=tmp_path)
```

This is a regression-style test only if the old bug allowed missing assets to pass silently. The assertion names the failure mode: fail fast before partial prompt records exist.

## Example 5: Permission and policy test for tool execution

```python
def test_tool_policy_rejects_disallowed_tool_even_if_model_requests_it() -> None:
    agent = build_agent_with_allowed_tools(["read_file"])
    request = ToolCallRequest(name="delete_file", arguments={"path": "README.md"})

    result = agent.tools.try_execute(request)

    assert result.denied is True
    assert result.executed is False
    assert result.error.type == "ToolPolicyDeniedError"
    assert "delete_file" in result.error.violated_invariant
```

This test protects the policy feature, not the model behavior. The important assertion is that deterministic code rejects the tool call even when the model asks for it.

## Example 6: Property-style invariant for context compaction

```python
@given(message_sequences_with_required_system_prompt())
def test_compaction_never_drops_required_system_prompt(messages: list[Message]) -> None:
    compacted = compact_messages(messages, max_tokens=512)

    assert compacted[0].role == "system"
    assert compacted[0].required is True
    assert token_count(compacted) <= 512
```

The exact compacted output can vary by implementation. The feature contract is not the algorithm; the contract is that required system context survives while the result stays under budget.

# Conclusion
Use this file as a way to think, not as a rigid template to copy blindly. The higher-level purpose is to make agents treat testing as first-class engineering work: define the feature, understand why it matters, search for ways it can break, choose broad and meaningful test strategies, and leave behind executable intent that future agents can rely on. If a detail in this file does not fit the codebase, adapt the detail while preserving the principle: the test pack should make the feature more robust, more secure, more diagnosable, and harder for future code changes to break accidentally.
