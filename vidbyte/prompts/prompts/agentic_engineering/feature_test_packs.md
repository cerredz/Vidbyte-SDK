# Description
Feature test packs turn testing into executable feature intent. Agents can write tests quickly, so the scarce resource is no longer the typing effort required to create tests; the scarce resource is judgment about what behavior deserves protection and what failure modes matter. The default agent failure mode is shallow confidence theater: many tests that pass, but only prove that the current implementation returns something on the happy path. This principle replaces file-based test thinking with feature-based test thinking. A feature test pack is a folder of tests organized around one durable behavior boundary, with each test file representing a different lens for attacking that feature's contract. The agent's job is not to confirm the implementation it just wrote; the agent's job is to define the feature, inventory how it can fail, and write tests that would catch a future agent violating that feature's promise.

# Intent
The intent of feature test packs is to make behavioral meaning executable at the same granularity users, maintainers, API consumers, and downstream agents actually care about. A codebase is not primarily a collection of files; it is a collection of capabilities, workflows, guarantees, and invariants. Tests organized only by file encourage agents to test implementation containers instead of behavior. Tests organized by feature force the agent to ask what the code promises, who relies on it, which states are allowed, which failures matter, and which observable outputs prove the feature still works.

This principle closes a known agent failure mode: models can generate a large number of tests without understanding what makes a test useful. They often test only the path they just implemented, mock away the collaborator that carries the actual risk, use toy fixtures that avoid real edge cases, assert private implementation steps that should be free to change, and never try to break the code. Feature test packs turn test creation into a sequence of explicit reasoning steps: define the feature boundary, write the failure inventory, choose the test lenses, write behavior-first tests, then audit whether each test would fail for the right reason if the feature promise were broken.

# What Counts as a Feature
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
A feature test pack lives under `tests/features/<feature_slug>/`. The folder is a menu of test lenses, not a demand that every feature must include every file. The README explains which lenses are used, which are omitted, and why.

```text
tests/features/<feature_slug>/
|-- README.md
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
|-- test_accessibility.py
|-- test_serialization_roundtrip.py
|-- test_cli_package_smoke.py
|-- fixtures.py
`-- factories.py
```

* `README.md` is mandatory. It defines the feature, contract, invariants, failure inventory, selected test lenses, and omitted lenses. Without it, the folder is just a pile of tests.
* Test files are optional and selected by risk. A pure transformation feature may need unit, property, metamorphic, and edge-case tests. An agent tool policy feature may need contract, integration, security, permission, error behavior, and regression tests. A UI workflow may need acceptance, browser interaction, accessibility, smoke, and visual or snapshot checks.
* `fixtures.py` and `factories.py` exist to make realistic setup cheap. Prefer named factories that encode domain meaning over anonymous dictionaries copied into every test.
* Existing module-based tests do not have to be moved immediately. When working in a legacy repo, create the feature pack for new or touched behavior and cross-reference existing module tests in the README.
* If the codebase uses another language, preserve the concept and adapt filenames to local convention: `*.spec.ts`, `*.test.ts`, `*_test.go`, or test suites in a nested package are all acceptable if the feature pack remains discoverable.

# Feature Test Pack README
Every feature pack README must be short enough to read before opening test files and specific enough to route an agent to the right lens.

```markdown
# Feature: <feature name>

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

## Omitted Test Lenses
Which test types were intentionally not added and why the omission is acceptable.
```

* The Contract section is the anchor. If a test does not protect something in the contract, invariants, outcomes, or failure modes, challenge whether it belongs.
* The Omitted Test Lenses section prevents false completeness. It is acceptable to omit stress tests for a tiny pure parser; it is not acceptable to omit the rationale.
* Keep the README stable through refactors. File paths can appear in the suite map, but the main contract should describe behavior that survives file movement.

# Failure Inventory Before Test Generation
Before writing any tests, write a failure inventory. This is the step that forces the agent out of "test the code I see" mode and into "attack the behavior the feature promises" mode.

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
What a shallow generated test would miss:
```

* Core contract: name the promise in one or two sentences. If you cannot write the contract, you are not ready to write tests.
* Valid inputs: include realistic normal data, not only tiny examples. Use domain-shaped fixtures.
* Invalid inputs: include malformed, missing, stale, duplicate, unauthorized, out-of-order, and boundary values.
* Observable outcomes: decide what proves behavior from outside the implementation. Return value alone is often not enough; inspect state, events, errors, traces, and side effects.
* External boundaries: list what should be mocked and what should remain real. Mock outside the feature boundary, not inside the behavior being proven.
* Security and policy risks: list who must not be able to do what. Agent systems need explicit tests for allowed tools, sandbox boundaries, approval gates, budgets, and middleware policy.
* Concurrency and idempotency risks: list duplicate requests, retries, races, stale reads, locks, and partial writes.
* Historical bugs: turn each bug into one test that fails against the old failure mechanism.
* Resource limits: list large inputs, long contexts, high request counts, token/cost ceilings, provider limits, memory pressure, and file counts.
* What a shallow generated test would miss: write the trap explicitly. Then make at least one test catch it.

# What Makes a Good Test
A good test is not a test that passes. A good test is one that would fail for the right reason if the feature's promise were broken.

* Behavior-first: the test names and asserts what the feature promises, not how the current implementation happens to do it. A correct refactor should keep the test green.
* Refactor-stable: the test should survive moving code between files, extracting helper functions, renaming private methods, or changing internal algorithms.
* Failure-seeking: the test tries to break assumptions using bad input, missing state, duplicate calls, forbidden actors, stale data, provider failures, resource limits, and policy bypass attempts.
* Invariant-centered: the test protects rules that must always hold. If no invariant is named, the test may only be checking incidental output.
* Observable: the test asserts return values, persisted state, emitted events, files, network payloads, logs, traces, metrics, UI state, or error packets that a caller can observe.
* Realistic: fixtures resemble real data, including optional fields, legacy shapes, partial state, large values, invalid encodings, timezone boundaries, and messy combinations.
* Boundary-aware: mocks sit outside the feature boundary. Do not mock the service, parser, policy, or state transition that the test claims to prove.
* Diagnostic: the test name, setup, and assertion explain the broken promise. When it fails, the next agent should know what behavior regressed without opening the implementation first.
* Minimal but meaningful: the test asserts the behavior that matters and avoids pinning internal steps that should be free to change.
* Mutation-resistant: deleting the guard, flipping a condition, bypassing the policy, skipping persistence, removing redaction, or changing ordering should make at least one test fail.
* Regression-linked: when the test covers a bug, it encodes the bug's actual failure mechanism, not just the new code path that fixes it.
* Adversarial where needed: security, permission, parser, provider, auth, sandbox, model-tool, and error-handling features require abuse cases, not only valid calls.
* Economical in scope: a test should be as narrow as possible while still proving the behavior. If it needs ten mocks and a fragile setup, the boundary may be wrong.
* Honest about nondeterminism: time, randomness, provider responses, parallelism, and ordering should be controlled or asserted with stable properties rather than exact incidental values.

# Bad Test Smells
* A test named `test_success`, `test_handles_error`, `test_works`, or `test_returns_value`.
* A test that only asserts the result is not `None`.
* A test that mocks the exact function or collaborator whose behavior it claims to verify.
* A test that duplicates the implementation logic in the assertion.
* A test that asserts private helper call order when the public behavior is the real contract.
* A test with toy fixtures that avoid required fields, legacy state, permissions, or realistic object shape.
* A test that only covers the happy path for security, auth, policy, parser, or payment behavior.
* A regression test that would have passed before the bug was fixed.
* A test that cannot explain what feature promise it protects.
* A broad end-to-end test that fails with no diagnostic signal.
* A snapshot that captures unstable incidental output and makes refactors expensive.
* A coverage-increasing test that does not make any meaningful mutation fail.

# Test Type Taxonomy
Use the taxonomy as a lens menu. Each test type is included when it protects a real risk in the feature inventory.

## Acceptance Tests
* Protect stakeholder-visible acceptance criteria. Include them when a product owner, user, customer, or external consumer would recognize the workflow as complete or broken.
* Agents commonly get these wrong by asserting an internal return value rather than the outcome the stakeholder cares about.
* Example: `test_cancel_subscription_keeps_access_until_paid_period_ends`.

## Contract Tests
* Protect stable boundaries between consumers and providers: SDK public APIs, HTTP schemas, tool schemas, provider adapters, package exports, prompt enum keys, event payloads, and CLI interfaces.
* Include them when another module, service, agent, or external user depends on a shape or behavior remaining stable.
* Agents commonly get these wrong by testing the producer alone and never proving that the consumer can still rely on the contract.
* Example: `test_prompt_catalog_fails_when_enum_key_has_no_asset`.

## Unit Tests
* Protect pure logic, decision rules, validation, transformations, parsing, formatting, and small domain computations.
* Include them when behavior can be verified without real external systems.
* Agents commonly get these wrong by testing trivial getters or implementation helpers instead of the rule with real branches.
* Example: `test_retry_policy_marks_post_payment_charge_non_retryable`.

## Integration Tests
* Protect collaborating internal components working together.
* Include them when a feature spans multiple modules and the seam between them carries risk.
* Agents commonly get these wrong by mocking every collaborator, leaving only the current file tested.
* Example: `test_tool_execution_applies_policy_before_executor_call`.

## Component or Service Tests
* Protect one subsystem through its public boundary while replacing expensive or external dependencies.
* Include them when the feature has a service-level API and several internal helpers.
* Agents commonly get these wrong by reaching into private helpers instead of exercising the service boundary.
* Example: `test_compaction_service_preserves_required_messages_under_budget`.

## End-to-End Tests
* Protect a full workflow through the highest practical boundary.
* Include them for critical user, CLI, API, or agent workflows where multiple layers must cooperate.
* Agents commonly get these wrong by making the test too broad without a diagnostic assertion at each important outcome.
* Example: `test_cli_installs_package_and_lists_prompt_families`.

## Browser Interaction / Manual Agent Tests
* Protect UI behavior by driving a browser: click, type, inspect DOM state, verify network behavior, capture screenshots, and check visible outcomes.
* Include them when the feature depends on frontend state, browser APIs, layout, accessibility, or user interaction timing.
* Agents commonly get these wrong by checking that a page loads while never exercising the actual workflow.
* Example: `test_browser_recording_export_downloads_playable_artifact`.

## Smoke Tests
* Protect basic boot and main-path execution.
* Include them for package imports, CLI entrypoints, service startup, prompt family loading, and feature toggles.
* Agents commonly overvalue smoke tests. A smoke test says the feature starts; it does not prove the feature is correct.
* Example: `test_vidbyte_mcp_server_entrypoint_imports`.

## Regression Tests
* Protect a bug's actual failure mechanism.
* Include one for every fixed bug, review comment, production incident, or recurring footgun.
* Agents commonly get these wrong by testing the new implementation rather than proving the old bug would fail.
* Example: `test_trace_export_redacts_api_key_in_error_metadata`.

## Edge Case Tests
* Protect boundary values and weird-but-valid states: empty, null, min, max, duplicate, ordering, timezone, encoding, pagination, limits, and legacy data.
* Include them whenever the failure inventory has input diversity.
* Agents commonly get these wrong by listing edge cases but writing only one empty-input test.
* Example: `test_context_window_handles_message_exactly_at_token_budget`.

## Negative Tests
* Protect invalid behavior: malformed inputs, forbidden operations, impossible states, missing dependencies, unsupported modes, and wrong permissions.
* Include them when rejection behavior is part of the feature contract.
* Agents commonly get these wrong by asserting that an exception is raised but not checking which contract was violated.
* Example: `test_attach_tool_rejects_unknown_mcp_transport`.

## Error Behavior Tests
* Protect error type, message, violated invariant, expected-vs-actual detail, remediation context, redaction, chaining, and test references.
* Include them for agentic error classes and important failure paths.
* Agents commonly get these wrong by checking only `with raises(Exception)`.
* Example: `test_missing_prompt_asset_error_names_blast_radius_and_fix_approaches`.

## Security Tests
* Protect authentication, authorization, injection, path traversal, confused deputy, unsafe deserialization, secret leakage, and privilege escalation.
* Include them for any feature that handles identity, permissions, user input, filesystem paths, tools, tokens, provider keys, or external payloads.
* Agents commonly get these wrong by testing the allowed user and skipping the forbidden user.
* Example: `test_workspace_file_reader_rejects_path_traversal_outside_root`.

## Permission / Policy Tests
* Protect agent-specific boundaries: allowed tools, sandbox modes, approvals, budgets, rate limits, provider allowlists, and middleware policy.
* Include them whenever a model request must be constrained by deterministic code.
* Agents commonly get these wrong by trusting the model's requested action rather than asserting the policy layer rejects it.
* Example: `test_tool_policy_rejects_disallowed_tool_even_if_model_requests_it`.

## Concurrency Tests
* Protect races, locks, duplicate requests, stale reads, ordering, and simultaneous writes.
* Include them when multiple callers, workers, tasks, threads, async calls, or retries can touch the same state.
* Agents commonly get these wrong by writing a sequential test and calling it concurrency coverage.
* Example: `test_actor_inbox_preserves_message_order_under_parallel_senders`.

## Idempotency Tests
* Protect duplicate event handling, retry safety, repeated requests, payment operations, queue workers, and at-least-once delivery semantics.
* Include them when the same operation can run more than once.
* Agents commonly get these wrong by checking that the second call does not crash while failing to assert state did not duplicate.
* Example: `test_retry_does_not_repeat_non_idempotent_payment_charge`.

## Stress Tests
* Protect behavior under high volume, repeated calls, large payloads, many files, many users, long contexts, or many tool calls.
* Include them when scale changes behavior or resource pressure can trigger bugs.
* Agents commonly get these wrong by making a stress test indistinguishable from a normal test with ten items.
* Example: `test_prompt_catalog_loads_all_families_repeatedly_without_record_drift`.

## Load / Performance Tests
* Protect latency, throughput, memory, DB query count, provider calls, token usage, and cost ceilings.
* Include them when the feature has a budget that users or infrastructure rely on.
* Agents commonly get these wrong by measuring wall-clock time without stable inputs or thresholds.
* Example: `test_context_compaction_stays_under_token_budget_for_large_trace`.

## Property-Based Tests
* Protect invariants across many generated valid inputs.
* Include them for parsers, serializers, reducers, compaction, ranking, scheduling, calculations, and normalization logic.
* Agents commonly get these wrong by generating arbitrary nonsense rather than valid domain-shaped data.
* Example: `test_compaction_never_drops_system_prompt_for_valid_message_sequences`.

## Fuzz Tests
* Protect parsers and boundary handlers against malformed, adversarial, random, or corrupted input.
* Include them for JSON, Markdown, CLI args, model outputs, webhooks, file formats, and network payloads.
* Agents commonly get these wrong by expecting all fuzz cases to succeed instead of asserting safe failure.
* Example: `test_prompt_descriptor_loader_rejects_malformed_json_without_partial_records`.

## Metamorphic Tests
* Protect properties that should remain true after controlled input transformations.
* Include them when exact expected output is hard but relationships are clear.
* Agents commonly miss these because they think every test needs a single fixed expected value.
* Example: `test_context_compaction_output_is_stable_when_irrelevant_old_messages_are_added`.

## Snapshot / Golden Tests
* Protect stable generated output, serialized artifacts, prompt text bundles, schemas, CLI output, rendered files, and compatibility surfaces.
* Include them when exact output is a public or reviewable artifact.
* Agents commonly get these wrong by snapshotting unstable timestamps, IDs, ordering, or internal debug output.
* Example: `test_prompt_catalog_readme_quick_reference_matches_golden_order`.

## Migration / Backward Compatibility Tests
* Protect old data shapes, new data shapes, mixed versions, rollback assumptions, and persisted artifacts.
* Include them when users may already have data, config, caches, saved traces, serialized prompts, or installed packages.
* Agents commonly get these wrong by testing only the new schema.
* Example: `test_trace_loader_accepts_pre_redaction_trace_schema`.

## Observability Tests
* Protect logs, traces, metrics, audit records, debug artifacts, and diagnostic metadata.
* Include them when operations teams, agents, or support workflows rely on emitted context.
* Agents commonly get these wrong by checking that "something was logged" rather than asserting the useful fields are present and secrets are absent.
* Example: `test_agent_run_trace_includes_tool_call_ids_and_redacts_api_keys`.

## Chaos / Failure Injection Tests
* Protect behavior under dependency timeout, provider failure, network partition, partial write, retry exhaustion, filesystem error, or queue failure.
* Include them when resilience and recovery are part of the contract.
* Agents commonly get these wrong by injecting a failure but never asserting recovery, rollback, or diagnostic behavior.
* Example: `test_provider_timeout_returns_retryable_context_packet_without_losing_history`.

## Compatibility Tests
* Protect supported OS, Python, browser, provider, API, package, and protocol versions.
* Include them when the feature promises compatibility across versions or environments.
* Agents commonly get these wrong by assuming the local runtime is the whole support matrix.
* Example: `test_mcp_prompt_list_response_matches_protocol_shape`.

## Accessibility Tests
* Protect keyboard navigation, labels, focus order, semantic roles, contrast, screen reader names, and error announcements.
* Include them for UI features and browser workflows.
* Agents commonly get these wrong by testing pixels while ignoring whether the workflow can be used without a mouse.
* Example: `test_export_dialog_focuses_filename_input_and_announces_errors`.

## Serialization / Round-Trip Tests
* Protect encode/decode behavior, persistence hydration, config loading, schema conversion, and artifact regeneration.
* Include them when data crosses a process, file, API, queue, or storage boundary.
* Agents commonly get these wrong by testing serialization without deserializing back and comparing semantic equality.
* Example: `test_agent_run_probe_roundtrips_through_json_without_losing_tool_calls`.

## CLI / Package / Install Smoke Tests
* Protect importability, package data, entrypoints, extras, command startup, and installed-resource lookup.
* Include them for SDKs, CLIs, plugin packages, and prompt catalogs.
* Agents commonly get these wrong by testing from the source tree only, missing package-data failures after install.
* Example: `test_installed_package_can_load_agentic_engineering_prompt_family`.

## Mutation Testing
* Mutation testing is a quality check on the tests themselves, not usually a feature test file. It intentionally mutates production logic and checks whether the test suite fails.
* Include it for high-risk pure logic, money paths, security policy, parser behavior, and invariants where coverage percentage is not enough.
* Agents commonly skip it because the normal tests are green; use it when you need evidence that tests catch wrong logic.
* Example: `mutation_check_tool_policy_rejects_deleted_allowlist_guard`.

# Choosing Test Lenses
* Start with the failure inventory, not the taxonomy. The taxonomy is a menu; the inventory tells you what to order.
* Include acceptance tests when a user, stakeholder, or API consumer has visible acceptance criteria.
* Include contract tests when another module, package, service, provider, CLI, or agent depends on a stable interface.
* Include integration or component tests when the feature is an orchestration across files.
* Include permission, policy, security, and negative tests whenever the feature constrains what an actor or model can do.
* Include concurrency and idempotency tests when retries, duplicate events, queues, async actors, or parallel users can touch the same state.
* Include stress, load, and performance tests when behavior changes at scale or when cost, memory, latency, token usage, or provider calls have budgets.
* Include property, fuzz, and metamorphic tests when input space is large and invariants are clearer than individual expected examples.
* Include observability tests when future agents, support engineers, or operators rely on logs, traces, metrics, or audit output to debug the feature.
* Include browser interaction and accessibility tests when the feature is a real user workflow in a browser.
* Omit a lens only after writing why it is safe to omit. "No time" is not a rationale; "pure function with no external boundary, no state transition, no policy risk, and complete property coverage" is a rationale.

# Things Not to Do
* Do not organize tests only around files when the behavior spans multiple files. File-based tests are allowed, but feature packs own feature intent.
* Do not stop at unit tests when the feature is an orchestration. A function can be correct while the feature is broken.
* Do not mock the behavior under test. Mock outside the feature boundary, not inside it.
* Do not assert incidental private implementation steps unless the internal protocol itself is the feature contract.
* Do not use toy fixtures that skip the hard fields, permissions, legacy state, or invalid combinations that make the feature risky.
* Do not write a regression test that would have passed before the bug was fixed.
* Do not let coverage percentage stand in for behavioral protection. Coverage can be high while mutation resistance is low.
* Do not write broad end-to-end tests with vague assertions and call them comprehensive.
* Do not skip negative, security, permission, or policy tests for agent-tool features. Those tests are the feature.
* Do not create every possible test file just because the template lists it. Unused lenses create noise and maintenance drag.
* Do not write tests that depend on unstable time, randomness, external services, provider text, ordering, or generated IDs unless those values are controlled.
* Do not write test names that describe mechanics instead of promises. `test_parse` is weak; `test_prompt_descriptor_rejects_missing_markdown_asset` is useful.
* Do not leave the feature pack README stale after adding or deleting a test lens.

# Checklist
* Before writing tests, define the feature boundary in behavior terms and verify it has a trigger, inputs, outcomes, invariants, failure modes, and a reason someone would care if it broke.
* Before creating a pack, write the failure inventory. Do not write test files until the inventory names what a shallow generated test would miss.
* Choose test lenses from the inventory and record omitted lenses in the README with a rationale.
* Write acceptance or contract tests before implementation-shaped unit tests when the behavior is ambiguous.
* Place helper function tests inside the parent feature pack unless the helper owns a reusable invariant or public contract.
* For every bug fix, add a regression test that fails against the old failure mechanism.
* For every security, permission, policy, parser, provider, or tool feature, include at least one adversarial or negative test.
* For every concurrency or retry-capable feature, decide explicitly whether idempotency and ordering need tests.
* After writing a test, ask what production mutation would make it fail. If no realistic broken code fails the test, strengthen or delete it.
* After writing a test, verify the mock boundary: mocks must sit outside the feature boundary, never inside the behavior being proven.
* After writing a test, verify the assertion boundary: assert observable outcomes, not incidental internal steps.
* Before opening a pull request, read the feature pack README and confirm the Test Suite Map, Omitted Test Lenses, and Historical Regressions match the files you actually created.

# Code Examples

## Example 1: Feature test pack README

```markdown
# Feature: Prompt Catalog Loading

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

## Omitted Test Lenses
* Browser interaction omitted: prompt catalog loading has no UI.
* Concurrency omitted: class-level cache load is not currently a documented thread-safety contract.
* Stress omitted: prompt count is small and package-data loading is already covered by smoke tests.
```

## Example 2: Pytest folder layout

```text
tests/features/prompt_catalog_loading/
|-- README.md
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
