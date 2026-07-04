# Design Doc: Agentic Engineering Feature Test Packs

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-28
**Last Updated:** 2026-06-28

---

## 1. Overview

Add a new agentic engineering principle prompt named `feature_test_packs` to the Vidbyte SDK prompt family. The principle teaches models to treat testing as first-class executable feature intent, not file-adjacent confidence theater or afterthought cleanup. It defines a feature as the smallest durable behavior boundary the codebase promises to preserve, requires one organized test pack per feature, uses `FEATURE.md` to explain the actual feature being tested, gives broad testing-strategy guidance, and pushes agents to think like good testers that actively try to break the system. The prompt is intended to be the most detailed testing guidance in the agentic engineering family because agents can write tests quickly, and that speed should be used to create robust, secure, complex, adversarial suites that make future coding safer.

---

## 2. Goals & Non-Goals

### Goals

- Add `feature_test_packs.md` as a new principle deep-dive prompt under `vidbyte/prompts/prompts/agentic_engineering/`.
- Make `feature_test_packs.md` the canonical, high-depth agentic engineering testing principle.
- Register the principle in `agentic_engineering.json` under the key `feature_test_packs`.
- Add `AGENTIC_ENGINEERING_FEATURE_TEST_PACKS = "agentic_engineering.feature_test_packs"` to `vidbyte/lib/enums/prompts.py`.
- Add a new numbered principle entry to `system_prompt.md` with a summary, a 15-20 item `Use Cases:` trigger list, and the GitHub link.
- Update the `system_prompt.md` goal/scope language so testing is included alongside the existing agentic engineering principles.
- Update `vidbyte/prompts/README.md` so the quick-reference row and description include `feature_test_packs`.
- Update `vidbyte/prompts/skills/agentic-engineering.md` so the on-disk helper skill knows the family now includes `feature_test_packs` and so future agents treat test-pack principles as valid additions to the family.
- Follow the existing principle prompt style: `# Description`, `# Intent`, `# Goal`, named body sections, `# Things Not To Do`, `# Checklist`, `# Code Examples`, and `# Conclusion`.

### Non-Goals

- Do not add test files for the SDK itself. This request uses `design-doc-no-tests`, and the change is prompt text plus catalog registration.
- Do not create an actual `tests/features/` directory in this PR. The new prompt teaches the pattern; it does not apply the pattern to the SDK codebase.
- Do not change the prompt catalog loader. The existing loader already discovers Markdown-backed prompt family entries from the JSON descriptor.
- Do not add runtime tooling for test-pack generation, coverage analysis, mutation testing, or browser automation.
- Do not install new Python dependencies such as Hypothesis, Playwright, Locust, Schemathesis, or mutmut. Those tools may be named in the prompt as test-category examples, but they are not SDK dependencies.
- Do not modify unrelated untracked design docs currently present in the local checkout.

---

## 3. Background & Context

The Vidbyte SDK now has an `agentic_engineering` prompt family on `main`, stored in `vidbyte/prompts/prompts/agentic_engineering/`. The family currently includes `system_prompt`, `error_messages`, `file_headers`, `folder_readme`, `function_design`, and `intent_based_commenting`. These prompts teach agents to write code that is easier for downstream agents to read, navigate, debug, and modify.

The current family does not yet contain a testing principle. That is a meaningful gap because agent-written tests are often weak in a specific way: agents generate tests quickly, but they frequently test that code runs rather than that a durable behavior is protected. Common failures include shallow happy-path coverage, tests tied to implementation details, over-mocking the behavior under test, vague test names, toy fixtures, no adversarial edge cases, no security or policy checks, and regression tests that do not encode the bug's actual failure mechanism.

The user wants the testing principle to be more rigorous than generic "write unit and integration tests" guidance. The principle must define what counts as a feature, require a folder of test suites for each feature, include many categories of tests including stress, contract, acceptance, end-to-end, browser/manual interaction, regression, security, property-based, fuzz, metamorphic, observability, chaos, migration, and performance tests, and go deep on what makes an individual test good. This should become a reusable principle in the same style as the merged agentic engineering files, not a one-off article outline.

The local `main` branch was fast-forwarded to `origin/main` before this design doc was written. The checkout still contains many tracked generated `.pyc` modifications and several untracked design docs from prior work. Those are not part of this change and must not be reverted or modified. If they block the post-approval worktree setup required by the skill, that blocker will be reported before implementation.

---

## 4. Requirements

### Functional Requirements

1. `feature_test_packs.md` must be created under `vidbyte/prompts/prompts/agentic_engineering/`.
2. `feature_test_packs.md` must open with `# Description`, not YAML or XML, matching current principle files.
3. The `# Description` section must explain the core thesis: agents make test writing cheap, so the scarce resource becomes test judgment; the solution is feature-level test packs that encode executable intent.
4. The `# Intent` section must explain which agent failure mode the principle closes: models writing many tests that do not attack the real feature contract.
5. The prompt must define a feature strictly as the smallest durable behavior boundary the codebase promises to preserve.
6. The feature definition must require at least: a trigger/caller, inputs or preconditions, observable outcome, invariants, meaningful failure modes, and a reason someone would care if it broke.
7. The prompt must explicitly distinguish features from implementation containers such as files, classes, folders, endpoints, helper functions, and modules.
8. The prompt must include a feature-identification rubric that asks whether a bug report, changelog entry, acceptance criterion, invariant, or user/integrator complaint could name the behavior without naming the file.
9. The prompt must define the correct granularity as the "smallest durable behavioral boundary" and provide examples of too broad, too narrow, and right-sized feature names.
10. The prompt must explain when a helper function deserves its own feature test pack versus when it should be tested inside its parent feature's pack.
11. The prompt must define a canonical feature test pack folder shape under `tests/features/<feature_slug>/`.
12. The test pack shape must include `FEATURE.md` and optional files for acceptance, contract, unit, integration, component/service, end-to-end, browser interaction, smoke, regression, edge cases, negative behavior, error behavior, security, permission/policy, concurrency, idempotency, stress, load/performance, property-based, fuzz, metamorphic, snapshot/golden, migration/backward compatibility, observability, chaos/failure injection, compatibility, accessibility where relevant, fixtures, and factories.
13. The prompt must state that the agent should consider many feature testing strategies by default, then justify which strategies are included and which are intentionally omitted.
14. The feature test pack `FEATURE.md` schema must include: Feature, High-Level Feature Description, Contract, Actors/Callers, Inputs, Preconditions, Observable Outcomes, State Transitions, Invariants, External Dependencies, Known Failure Modes, Historical Regressions, Test Suite Map, and Omitted Testing Strategies.
15. The prompt must require a failure inventory before writing tests.
16. The failure inventory must list at minimum: core contract, invariants, valid inputs, invalid inputs, state transitions, external boundaries, security/policy risks, concurrency/idempotency risks, historical bugs, expensive resource limits, observability promises, and what a shallow test would miss.
17. The prompt must include a `# Testing Philosophy` section that tells the model to adopt the mindset of a good tester: search for edge cases, actively try to break the system, avoid irrelevant or easy-to-pass tests, and use cheap agentic test generation to pursue broad meaningful coverage.
18. The prompt must include a universal testing strategy rubric that requires tests to be behavior-first, observable, realistic, adversarial where needed, diagnostic, mutation-resistant, and boundary-aware.
19. The prompt must include bad-test anti-patterns, including: asserting only that something returns, testing only happy paths, mocking the exact behavior under test, asserting incidental implementation steps, using toy fixtures, duplicating source logic in assertions, vague names, and missing failure/abuse/concurrency cases.
20. The prompt must include the rule: a good test is not one that passes; a good test is one that would fail for the right reason if the feature promise were broken.
21. The prompt must include a testing strategy playbook with enough context for each type of test: what it protects, what makes good and bad tests for that strategy, diverse example test names, and why the suite is shaped that way.
22. The taxonomy must cover at least these test types: acceptance, contract, unit, integration, component/service, end-to-end, browser interaction/manual, smoke, regression, edge case, negative, error behavior, security, permission/policy, concurrency, idempotency, stress, load/performance, property-based, fuzz, metamorphic, snapshot/golden, migration/backward compatibility, observability, chaos/failure injection, compatibility, accessibility, serialization/round-trip, CLI/package/install smoke, and mutation testing as a quality check.
23. The prompt must include `# Things Not to Do` with agent-specific anti-patterns.
24. The prompt must include `# Checklist` with high-level workflow reminders, not just a repeated taxonomy list.
25. The checklist must cover before-writing, during-writing, after-writing, and PR-review phases.
26. The prompt must include `# Code Examples` with at least four examples: a feature test pack `FEATURE.md`, a pytest-style folder layout, a concrete contract or acceptance test, and a regression/security/error-behavior example.
27. Code examples must use realistic agentic or SDK-adjacent examples such as prompt catalog loading, tool permission enforcement, context compaction, retry/idempotency policy, or trace redaction.
28. `agentic_engineering.json` must add a `feature_test_packs` entry with `path: "feature_test_packs.md"` and a GitHub `source_url`.
29. `agentic_engineering.json` description should be updated only if needed to mention testing without changing the descriptor structure.
30. `vidbyte/lib/enums/prompts.py` must add `AGENTIC_ENGINEERING_FEATURE_TEST_PACKS = "agentic_engineering.feature_test_packs"` grouped with the other `AGENTIC_ENGINEERING_*` enum members.
31. `system_prompt.md` must add a new numbered principle entry for Feature Test Packs as Executable Intent.
32. The system prompt entry must include a concise summary paragraph, a `Use Cases:` list with 15-20 specific triggers, and a `GitHub:` link.
33. The system prompt `# Goal` or surrounding scope text must mention that testing is part of the agentic engineering discipline.
34. `vidbyte/prompts/README.md` must append `feature_test_packs` to the Agentic Engineering quick-reference row.
35. `vidbyte/prompts/README.md` must update the Agentic Engineering description to mention feature test packs.
36. `vidbyte/prompts/skills/agentic-engineering.md` must be updated so its structure section lists `feature_test_packs.md` as an existing principle.
37. `vidbyte/prompts/skills/agentic-engineering.md` must be updated so its criteria/examples mention feature-level test packs as a valid agentic engineering principle.
38. No unrelated files may be modified.

### Non-Functional Requirements

- The prompt must be self-contained and deep enough that a model can apply the principle without reading the article discussion that motivated it.
- The prompt must be more detailed than the existing function design principle and comparable in depth to the largest agentic engineering principle files.
- The prompt must use the family style: Markdown `#` headers, `*` bullets, authoritative operational language, no emoji, no callouts, and no XML tags.
- The prompt should avoid adding new SDK dependencies or implying that every listed test tool is installed in the repo.
- The prompt should avoid saying every feature must include every test category. It should instead push agents to consider many strategies by default and require explicit selected-strategy and omitted-strategy rationale.
- The principle must preserve catalog compatibility: every JSON prompt key must have a matching enum value, and every Markdown path must exist.
- Reliability requirement: the new prompt should reduce agent false confidence by forcing a failure inventory before test generation.
- Maintainability requirement: updates to system prompt, README, and helper skill must not duplicate the entire deep-dive; they should route agents to the new prompt.

---

## 5. High-Level Design

This change adds one new Markdown-backed principle prompt to the existing `agentic_engineering` prompt family and wires it into the same catalog path as the other principles. No loader change is needed. The prompt catalog already discovers `agentic_engineering.json`, resolves Markdown files referenced by `path`, validates non-empty text, and checks enum sync.

The new principle key will be `feature_test_packs`. That name is more precise than `testing` because the principle is not generic test advice. It is a feature-granularity organization model: first define the feature boundary, then create a test pack that encodes the feature's executable intent through multiple testing strategies.

The on-disk helper skill at `vidbyte/prompts/skills/agentic-engineering.md` will also be updated. That file is not part of the import-validated prompt catalog, but it is a repository skill that teaches agents how to extend the family. Because the user specifically asked for an "agentic engineering skill" and because this file already describes the family structure, the design updates it so future agents know `feature_test_packs` exists and so its examples of valid principles stay current.

```text
[feature_test_packs.md]
        |
        v
[agentic_engineering.json]       adds feature_test_packs key
        |
        v
[Prompt enum]                    adds AGENTIC_ENGINEERING_FEATURE_TEST_PACKS
        |
        v
[system_prompt.md]               routes agents to the new principle
        |
        v
[prompts README + helper skill]   keeps human and skill-level indexes current
```

---

## 6. Detailed Design

### 6.1 Feature Test Packs Principle Prompt

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/feature_test_packs.md`
**Type:** New file

#### What it does

Provides the deep-dive testing principle for agentic engineering. A model loads this prompt when creating, modifying, reviewing, or expanding tests for a feature. The file teaches the model to identify the feature boundary, build a feature test pack folder, explain the feature in `FEATURE.md`, enumerate failure modes before writing tests, consider many testing strategies, and judge whether each generated test actually protects behavior.

#### Interface / API

No executable API. This is a Markdown prompt asset consumed through:

```python
from vidbyte.prompts import Prompts
from vidbyte.lib.enums.prompts import Prompt

text = Prompts().get(Prompt.AGENTIC_ENGINEERING_FEATURE_TEST_PACKS)
```

The direct import generated by the prompt catalog will be:

```python
from vidbyte.prompts import agentic_engineering_feature_test_packs
```

#### Logic / Algorithm

The file will follow this section order:

1. `# Description`
2. `# Intent`
3. `# Goal`
4. `# Definition of a Feature`
5. `# Feature Test Pack Structure`
6. `# Feature Test Pack FEATURE.md`
7. `# Failure Inventory Before Test Generation`
8. `# Testing Philosophy`
9. `# Universal Strategy Rubric`
10. `# Testing Strategy Playbook`
11. `# Things Not To Do`
12. `# Checklist`
13. `# Code Examples`
14. `# Conclusion`

`# Description` will state the principle in article-ready terms: agent-native testing is not about generating more tests; it is about making behavioral intent executable at feature granularity. It will explain that tests should map to feature intent, not files, and that agent speed makes comprehensive packs feasible while making judgment more important.

`# Intent` will state that the prompt closes the failure mode where models write tests that mirror the implementation or only confirm the patch. It will say the agent's job is to attack the feature contract, not prove that its own code runs.

`# Definition of a Feature` will define a feature as:

```text
A feature is the smallest durable behavior boundary the codebase promises to preserve.
It has a trigger or caller, inputs or preconditions, observable outcomes, invariants,
meaningful failure modes, and a reason someone would care if it broke.
```

This section will include examples:

```text
Too broad: billing, agents, auth, prompts
Too narrow: format_billing_date, _get_prompt_path, normalize_tool_name
Right-sized: billing invoice generation, agent runtime tool execution,
auth token refresh, prompt enum/catalog synchronization,
context compaction preserving required messages
```

`# Feature Test Pack Structure` will describe a canonical folder:

```text
tests/features/<feature_slug>/
├── FEATURE.md
├── test_acceptance.py
├── test_contract.py
├── test_unit.py
├── test_integration.py
├── test_component.py
├── test_e2e.py
├── test_browser_interaction.py
├── test_smoke.py
├── test_regression.py
├── test_edge_cases.py
├── test_negative.py
├── test_error_behavior.py
├── test_security.py
├── test_policy_permissions.py
├── test_concurrency.py
├── test_idempotency.py
├── test_stress.py
├── test_performance.py
├── test_property.py
├── test_fuzz.py
├── test_metamorphic.py
├── test_snapshot_golden.py
├── test_migration_compatibility.py
├── test_observability.py
├── test_chaos_failure_injection.py
├── test_accessibility.py
├── test_serialization_roundtrip.py
├── test_cli_package_smoke.py
├── fixtures.py
└── factories.py
```

The text will explicitly say this is a strategy menu, not a mandatory file list for every feature. The model must consider many strategies by default and omit only with a feature-specific rationale.

`# Feature Test Pack FEATURE.md` will provide a schema:

```markdown
# Feature: <name>

## High-Level Feature Description
## Contract
## Actors / Callers
## Inputs and Preconditions
## Observable Outcomes
## State Transitions
## Invariants
## External Dependencies
## Known Failure Modes
## Historical Regressions
## Test Suite Map
## Omitted Testing Strategies
```

`# Failure Inventory Before Test Generation` will require the model to list failure modes before writing tests. This section is load-bearing because it converts test writing from "cover code" into "attack promises."

`# Testing Philosophy` will explain that the model needs to adopt the mindset of a good tester. It should actively think about edge cases and ways to break the system, avoid irrelevant and easy-to-pass tests, and use cheap agentic test generation to pursue meaningful coverage that would have been too tedious for humans to write manually.

`# Universal Strategy Rubric` will define the shared standard for every testing strategy. It will require behavior-first names, observable assertions, realistic fixtures, invalid and adversarial inputs, mocks outside the feature boundary, diagnostic failures, mutation resistance, stable nondeterminism handling, regression linkage, and deletion or strengthening of tests that prove no meaningful behavior.

`# Testing Strategy Playbook` will include at least these categories. Each category will have a description, good and bad test guidance, example suite names, and a short explanation of why the suite is shaped that way.

| Test Type | Purpose |
|-----------|---------|
| Acceptance | Stakeholder-visible behavior and product acceptance criteria |
| Contract | Stable interfaces between consumers and providers |
| Unit | Pure logic, decisions, transformations, validation |
| Integration | Internal collaborators working together |
| Component / Service | One subsystem through its public boundary |
| End-to-End | Full workflow through real outer boundary where practical |
| Browser Interaction / Manual Agent | UI flows, DOM state, screenshots, network behavior |
| Smoke | Fast minimal boot/main-path confidence |
| Regression | Historical bug mechanisms |
| Edge Case | Empty, null, min, max, malformed, duplicate, ordering, timezone, encoding, pagination, limits |
| Negative | Invalid inputs, forbidden operations, wrong permissions, impossible states |
| Error Behavior | Error type, rich message, invariant, remediation context, redaction, chaining |
| Security | Auth, authorization, injection, confused deputy, path traversal, data leakage |
| Permission / Policy | Agent tool permissions, sandbox, approvals, budgets, middleware gates |
| Concurrency | Races, locks, duplicate requests, ordering, stale reads |
| Idempotency | Retry safety, duplicate event handling, exactly-once or at-least-once semantics |
| Stress | High volume, repeated calls, large payloads, many files, many users |
| Load / Performance | Latency, memory, DB query count, token usage, provider calls, cost ceilings |
| Property-Based | Generated valid inputs asserting invariants |
| Fuzz | Malformed or adversarial generated inputs |
| Metamorphic | Input transformations that should preserve a property |
| Snapshot / Golden | Stable generated output, serialized artifacts, schemas, CLI output, render output |
| Migration / Backward Compatibility | Old data, new data, mixed versions, rollback assumptions |
| Observability | Logs, traces, metrics, audit records, debugging artifacts |
| Chaos / Failure Injection | Timeouts, dependency failures, partial network failure, retry exhaustion |
| Compatibility | Provider version, API version, OS/runtime, browser, package compatibility |
| Accessibility | Keyboard navigation, labels, focus, screen reader semantics for UI features |
| Serialization / Round-Trip | Encode/decode, persistence hydration, schema round trips |
| CLI / Package / Install Smoke | Import, entrypoint, package data, command startup |
| Mutation Testing | Quality check that tests fail when logic is intentionally mutated |

`# Things Not to Do` will include anti-patterns:

- Do not make a file's tests equal a feature's tests by default.
- Do not stop at unit tests when the feature is an orchestration.
- Do not mock the exact behavior being proven.
- Do not assert private implementation steps unless the feature contract is explicitly the internal protocol.
- Do not use toy fixtures that avoid the hard path.
- Do not write regression tests that only assert the new code path, rather than the old bug mechanism.
- Do not write vague names like `test_success` or `test_handles_error`.
- Do not omit negative/security/policy tests for agent-tool features.
- Do not treat coverage percentage as proof of feature protection.
- Do not skip hard testing strategies merely because they take more thought.
- Do not create every possible test file mechanically when the feature risk does not justify it.

`# Checklist` will include workflow-stage items:

- Before writing tests, define the feature boundary using the strict feature schema.
- Before creating a pack, write the failure inventory.
- Choose testing strategies and justify omissions in `FEATURE.md`.
- Write acceptance/contract tests before implementation-specific unit tests when behavior is unclear.
- Add regression tests for every fixed bug.
- Verify each test would fail for the right reason if a key invariant were broken.
- Run a mock-boundary audit: mocks must sit outside the feature boundary.
- Run an assertion audit: each test must assert observable behavior.
- Run a name audit: the test name must name the promise being protected.
- Before PR, identify what a shallow generated test would have missed.

`# Code Examples` will include:

1. A `tests/features/prompt_catalog_loading/FEATURE.md` example.
2. A pytest folder layout for `prompt_catalog_loading`.
3. A contract test for prompt enum/catalog synchronization.
4. A regression test for missing Markdown asset detection.
5. A policy/security test for disallowed tool execution.
6. A property/metamorphic example for context compaction preserving required messages.

#### Edge Cases & Error Handling

- If a codebase already organizes tests by module rather than feature, the prompt will instruct agents to create feature packs for new work and cross-reference existing module tests rather than moving all old tests immediately.
- If a feature is too small for a full folder, the prompt will instruct the agent to keep it inside the parent feature pack unless it has its own contract and failure modes.
- If a feature spans packages or services, the prompt will instruct the agent to define the feature pack at the repository boundary that owns the behavior, with contract tests against external consumers/providers.
- If a test type requires unavailable tooling, the prompt will require an omission rationale rather than hallucinating a dependency.

---

### 6.2 Agentic Engineering Descriptor

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json`
**Type:** Modified

#### What it does

Registers the new `feature_test_packs` prompt in the existing family descriptor so `Prompts().family("agentic_engineering")` includes it and the catalog can resolve the Markdown file.

#### Interface / API

Add this entry to the `prompts` object:

```json
"feature_test_packs": {
  "path": "feature_test_packs.md",
  "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/feature_test_packs.md"
}
```

The top-level description may be updated to mention feature test packs, while preserving the descriptor schema.

#### Logic / Algorithm

No algorithmic change. The catalog loader will discover the new entry as part of existing loading behavior.

#### Edge Cases & Error Handling

- If the Markdown file is missing, `_resolve_prompt_text()` raises `ConfigurationError`.
- If the enum member is missing, `_validate_enum_sync()` or `Prompt(prompt_id)` raises `ConfigurationError`.
- If the JSON key and enum value differ, the catalog fails at import time.

---

### 6.3 Prompt Enum

**File(s):** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### What it does

Adds the typed enum member for the new prompt.

#### Interface / API

```python
AGENTIC_ENGINEERING_FEATURE_TEST_PACKS = "agentic_engineering.feature_test_packs"
```

#### Logic / Algorithm

Place the enum member with the other `AGENTIC_ENGINEERING_*` entries. The current file groups those entries at the top of the enum.

#### Edge Cases & Error Handling

N/A - enum registration only.

---

### 6.4 Agentic Engineering System Prompt

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md`
**Type:** Modified

#### What it does

Updates the family entry point so agents know the testing principle exists and when to load the deep-dive.

#### Interface / API

Add a numbered principle entry after the existing intent-based commenting principle:

```markdown
6. Feature Test Packs as Executable Intent
   [Summary paragraph]

   Use Cases: adding a feature with no tests, modifying behavior with existing tests, fixing a bug that needs regression coverage, defining a feature boundary before writing tests, creating tests for orchestration across modules, testing agent tool permission policy, adding browser-driven UI coverage, writing contract tests for SDK public APIs, writing stress tests for large contexts, writing property tests for invariants, adding fuzz tests for parsers, adding observability tests for trace output, auditing generated tests for shallow coverage, replacing file-based tests with feature-level packs, writing regression tests from review feedback

   GitHub: https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/feature_test_packs.md
```

The exact principle number may shift if other local untracked design docs become merged PRs first. The implementation should append after the existing merged principles on the branch used for implementation.

#### Logic / Algorithm

No runtime logic. The prompt acts as a router.

#### Edge Cases & Error Handling

- If other principle PRs land before implementation, renumber the entry against current `main`.
- Do not duplicate the full taxonomy in the system prompt; route to the deep-dive.

---

### 6.5 Prompts README

**File(s):** `vidbyte/prompts/README.md`
**Type:** Modified

#### What it does

Keeps the human-readable prompt catalog index accurate.

#### Interface / API

Update the quick-reference Agentic Engineering row:

```markdown
system_prompt, error_messages, file_headers, folder_readme, function_design, intent_based_commenting, feature_test_packs
```

Update the Agentic Engineering description with one or two sentences describing feature test packs as executable feature intent.

#### Logic / Algorithm

N/A - documentation only.

#### Edge Cases & Error Handling

N/A - documentation only.

---

### 6.6 Agentic Engineering Helper Skill

**File(s):** `vidbyte/prompts/skills/agentic-engineering.md`
**Type:** Modified

#### What it does

Updates the on-disk helper skill that teaches agents how to add principles to the family. This keeps the skill's current-family inventory and examples aligned with the new testing principle.

#### Interface / API

Modify these sections:

- Frontmatter description: mention that the family includes feature test packs as a testing principle.
- `<identity>`: update "currently has two principles" language, which is already stale after the merged PR.
- `<structure>`: add `feature_test_packs.md` with a concise description.
- `<criteria>` examples: include "feature test packs as executable feature intent" as a principle-sized practice.
- `<procedure>` or `<conventions>` if needed: mention that testing principles should include feature definition, `FEATURE.md`, broad testing-strategy guidance, and the universal strategy rubric.

#### Logic / Algorithm

N/A - skill text only.

#### Edge Cases & Error Handling

- Do not turn the helper skill into a duplicate copy of `feature_test_packs.md`; it should route future agents to the principle.
- Preserve existing procedural instructions for adding principles.

---

## 7. Data Model Changes

N/A - no database, schema, dataclass, or persisted data changes.

The only typed interface change is a new `Prompt` enum member, covered in API Changes.

---

## 8. API Changes

### 8.1 Prompt Catalog Enum Access

**Change type:** Modified

**Request:**

N/A - no HTTP request.

**Response:**

N/A - no HTTP response.

**New programmatic access:**

```python
Prompts().get(Prompt.AGENTIC_ENGINEERING_FEATURE_TEST_PACKS)
Prompts().family("agentic_engineering")["feature_test_packs"]
from vidbyte.prompts import agentic_engineering_feature_test_packs
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Missing enum member or missing Markdown asset raises `ConfigurationError` during prompt catalog loading |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agentic-engineering-feature-test-packs.md` | This design doc |
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/feature_test_packs.md` | New testing principle deep-dive prompt |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json` | Register `feature_test_packs` in the prompt family |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add `AGENTIC_ENGINEERING_FEATURE_TEST_PACKS` enum member |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` | Add router entry and scope mention for the testing principle |
| MODIFY | `vidbyte/prompts/README.md` | Update prompt catalog quick reference and description |
| MODIFY | `vidbyte/prompts/skills/agentic-engineering.md` | Update helper skill inventory and examples so it recognizes the testing principle |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | N/A | Prompt text and catalog registration only | No dependency risk |

The prompt may mention external testing tools as examples, but this PR will not add dependencies or require those tools to be installed.

---

## 11. Rollout & Deployment

- No feature flag required.
- No migration required.
- No breaking change expected. Existing prompt keys remain unchanged.
- Deployment is normal package publication when the SDK is released.
- Rollback procedure: revert the PR. That removes the new Markdown file, descriptor entry, enum member, system prompt entry, README text, and helper skill text.
- Verification after implementation:
  - `python -m compileall vidbyte`
  - `python -m unittest tests.test_prompts_interface`
  - `python -c "from vidbyte.prompts import Prompts; from vidbyte.lib.enums.prompts import Prompt; p = Prompts(); print(p.family('agentic_engineering').keys())"`
  - `python -c "from vidbyte.prompts import agentic_engineering_feature_test_packs; print(len(agentic_engineering_feature_test_packs))"`

---

## 12. Open Questions

- [ ] Should the principle key be `feature_test_packs` or `testing`? Recommendation: `feature_test_packs`, because the principle is specifically about feature-granularity executable intent, not generic testing.
- [ ] Should the helper skill `vidbyte/prompts/skills/agentic-engineering.md` be updated in the same PR? Recommendation: yes, because it is already stale after the merged PR and the user specifically asked for an agentic engineering skill inside the repo.
- [x] If `intent_based_commenting` merges before implementation, should this PR rebase and renumber the system prompt entry? Resolved: yes. The implementation branch is based on current `main`, keeps `intent_based_commenting`, and adds feature test packs as the next principle.
- [ ] Should the new prompt include real tool commands for every testing type? Recommendation: no. Include tool examples where helpful, but the principle is language-agnostic and should not imply SDK dependencies.
- [ ] Will local dirty `.pyc` changes and untracked design docs block the mandatory worktree workflow after approval? Unknown until Phase 3. If blocked, stop and report rather than cleaning user changes.

---

## 13. Alternatives Considered

### Alternative 1: Use `testing.md` as the principle key

- What: Add a generic `testing` prompt key.
- Why rejected: Too broad and less memorable. The unique principle is not "write tests"; it is "define feature boundaries and create executable intent packs around them." `feature_test_packs` encodes that shape directly.

### Alternative 2: Only update `vidbyte/prompts/skills/agentic-engineering.md`

- What: Treat the request as only a repository skill update, not a prompt-family addition.
- Why rejected: The existing agentic engineering principles live as prompt-family Markdown files under `vidbyte/prompts/prompts/agentic_engineering/` and are exposed through the SDK prompt catalog. A testing principle should be available through the same route as the other principles, otherwise the system prompt cannot load it consistently.

### Alternative 3: Add testing guidance to `function_design.md`

- What: Expand the existing function design prompt with a testing section.
- Why rejected: Function-level tests are only one slice of the testing problem. The user's requested principle centers on feature folders, feature definition, and a broad taxonomy of testing strategies. That is a standalone principle.

### Alternative 4: Create one prompt per test type

- What: Add separate principle prompts for contract testing, stress testing, browser testing, property-based testing, and so on.
- Why rejected: The agent first needs one coherent testing model that decides which strategies apply to a feature. Splitting test types into many prompts would make routing harder and would duplicate the feature-boundary, testing philosophy, and universal strategy rubric across files.

### Alternative 5: Add a generator script that creates feature test pack folders

- What: Implement tooling to scaffold `tests/features/<feature_slug>/`.
- Why rejected: Useful later, but out of scope for this prompt asset change. The current request asks for the agentic engineering principle text, not repository automation.
