# S2 test author report: byok-api-keys (SDK)

Stage: S2 test author. Spec: `docs/spec/byok-api-keys/spec.md` r4 (approved). Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-byok-api-keys`, branch `feat/byok-api-keys`, base `52aab816`, start HEAD `661fe8bf`. No production code, stub, or placeholder was written. `docs/spec/byok-api-keys/pipeline.md` (the orchestrator's edit) was left unstaged.

The detailed coverage map, the tests left out, the red run, and the superseded table are in `docs/spec/byok-api-keys/test-plan.md`. This report records how they were reached.

## 1. Inventory

Sources of behaviour to test: §6.2 AC-1 to AC-42, §6.1 INV-1 to INV-26, §6.3 EC-1 to EC-58, table M (M-1 to M-21), table G, table R, tables F and A, §8.5 and §12.3 (names, signatures, field orders), and §13 (superseded rows).

Every AC got at least one test except AC-28, which is a gate (lint plus `run_ci.py`). INVs and ECs got a test where an AC test did not already bind them; the second table in test-plan.md §1 lists them.

New pack `tests/features/sdk_provider_keys/` (117 tests):

| File | Tests | Main IDs |
|---|---|---|
| `test_provider_keys_acceptance.py` | 10 | AC-1 to AC-5, AC-11 to AC-13, AC-27, AC-36 |
| `test_provider_keys_matching.py` | 28 | AC-8, AC-10, AC-29, AC-35, AC-39, AC-42, INV-10, INV-24 to INV-26 |
| `test_provider_keys_property.py` | 2 | INV-9, INV-10 (seeded random plus exhaustive permutations) |
| `test_provider_keys_agents.py` | 21 | AC-7, AC-9, AC-16 to AC-18, AC-23, AC-25, AC-26, AC-31 to AC-34, AC-37, AC-38 |
| `test_provider_keys_sessions.py` | 6 | AC-19, AC-41, INV-14, D-30, EC-53 |
| `test_provider_keys_modes.py` | 16 | AC-6, AC-40, FR-3, table R, INV-7, INV-8, INV-12, M-8, M-9, M-14 |
| `test_provider_keys_wire_contract.py` | 12 | INV-2, INV-3, INV-16, INV-20, INV-21, EC-14, EC-37, EC-38 |
| `test_provider_keys_failures.py` | 4 | AC-14, AC-15, table G, INV-17 |
| `test_provider_keys_security.py` | 5 | AC-20, AC-21, AC-22 |
| `test_provider_keys_contract.py` | 13 | AC-24, AC-30, FR-1, FR-6, D-20, §8.5/§12.3 names |

## 2. Pruning

Kept a test only when it can fail for a reason a user would see. Dropped or folded in:

- One test per table M row: folded into the behaviour tests, which bind each row's facts column. The spec makes the wording the implementer's.
- Separate tests per provider for relay headers: one table-driven test over the six served providers.
- A Decision relay test: Decision is unchanged (INV-18); one exact-message test is enough.
- `AgentFallbackSettings` in the repr test: after D-26 it holds no key, so the case could not fail.
- `credential_mismatch`, Q-3 to Q-6, NG-1 to NG-19: out of scope or rejected.
- Live calls and the live E2E (NG-15): forbidden.
- `hypothesis`: not installed (NFR-6). `test_provider_keys_property.py` covers INV-9 with a seeded generator and `itertools.permutations`, in two environments. It also asserts that both outcomes are common, so the property cannot pass on an all-refused set.

## 3. Red run (exact output)

Command, from the worktree:

```
env -u DEEPSEEK_API_KEY PYTHONPATH=C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-byok-api-keys python -m pytest -q -p no:cacheprovider
```

- Baseline (HEAD `661fe8bf`, base tests): `3912 passed, 13 skipped in 47.21s`.
- Red run: `295 failed, 3727 passed, 13 skipped, 7 errors in 39.47s`.
- `tests/features/sdk_provider_keys`: `117 failed in 2.10s`.
- `tests/features/sdk_managed_text`: `19 failed, 20 passed in 1.14s`. `test_managed_text_failures.py:126-146` passes, as §13 requires.

Accounting: 3,925 base tests plus 117 new tests gives 4,042, which matches 295 + 3,727 + 13 + 7. Every failure is in a new or §13 file. None is in an untouched file, so none is pre-existing; HEAD differs from base only in `docs/`.

The 302 failures and errors, by reason, were read from the junit XML:

- 113: `AttributeError: DIRECT` (7 of them in `setUp`).
- 40: `JevAgentSettings`/`JevRunBriefSettings` reject `api_keys`.
- 39: `BaseAgent` rejects `api_keys`/`vidbyte_api_key`/`model_mode`.
- 29: `vidbyte.lib.registries.provider_keys` is missing.
- 28: `TextModelConfig` rejects the new keywords.
- 12: `AggregateAgent`/`AgentRoleSettings` reject `api_keys`.
- 9: `ProviderKeys`, `TextCredentials`, or `VIDBYTE_PROVIDER_KEY_HEADER` cannot be imported.
- 32: behaviour assertions on the base code. Examples:
  - a refusal not raised at construction;
  - a call that went vendor-direct instead of relaying;
  - base wording ("Missing API key … Pass api_key", "Vidbyte managed openai request failed: …", the old streaming refusal);
  - base field orders and signatures;
  - `scripts/test-new-runners.py:315` still passing `api_key=`;
  - the harness redactor leaving the second key of a list;
  - `FallbackModel(api_key=)` still accepted.

Two base-behaviour failures look unusual but are the right reason:

- In `test_provider_keys_modes.py`, the streaming test and the pinning test raise the base "Missing API key for provider openai" error. Base reads the key first, or re-reads the environment per call, which is exactly what AC-6 and INV-12 forbid.

Lint: after `git add` of the new pack, `python lint/run.py` ended `SDK-LINT: PASS`. Every new module has an A001 header, and no baseline was raised.

## 4. Fixtures

`provider_keys_fixtures.py` is new. It imports `GATEWAY_URL`, `answer`, and `header` from the managed pack's fixtures.

- **Fake keys, all built by concatenation:**
  - proven: `K_ANTHROPIC`/`_2` (`sk-ant-`), `K_OPENAI`/`_2` (`sk-proj-`), `K_OPENAI_ADMIN` (`sk-admin-`), `K_XAI`, `K_OPENROUTER` (`sk-or-v1-`), `K_GEMINI_AQ` (`"AQ" + "." + …`);
  - unproven: `K_UNPROVEN`/`_2`, `K_SK_UNPROVEN`/`_2`;
  - Vidbyte fakes reuse `VIDBYTE_KEY` or `VIDBYTE_API_KEY_PREFIX`.

  The `AIza` + 35, `sk-ant-api03-` + 93 + `AA`, and `T3BlbkFJ` shapes appear only in the AC-29 test, built at runtime.
- **`ProviderRouter`:** records a deep copy of every inner request and answers per provider: gateway calls by the envelope's provider, vendor calls by URL. An unknown provider raises, so it cannot pass silently.
- **`RecordingEnviron`:** a dict that replaces `os.environ` and records every read made through `get`, `[]`, and `in`.
- **Helpers:** `done_answer` builds per-dialect `isDone` answers; `flat` renders a request or an error as text; `key_view` gives an order-free view of a record; `provider_key_header` reads the relay header.

Every new test that builds a runner or an agent clears the environment and patches only the inner transport. The exceptions are the retry wait, patched where the gateway module looks up `asyncio`, and `RUNNER_TRANSPORT_TARGET`, used for agents.

## 5. Superseded updates and stragglers

All §13 rows were applied. Test-plan.md §5 lists each one with its spec ID and what changed. Summary:

- **24 mechanical files** (renames to `api_keys=[<matching fake>]` and `DIRECT`). A helper subagent applied them before an API 429 stop. I re-read every hunk after the stop: each was complete and matched its row. The helper's second batch had touched nothing.
- **Managed pack:**
  - `test_managed_text_selection.py`: 13 tests, 5 renamed.
  - `…_acceptance.py`: 2 tests, 1 renamed.
  - `…_wire_contract.py`: `byok_body` and the floor test.
  - `…_deadline.py`: 2 tests.
  - `FEATURE.md` and `README.md`: contract text.
- **Semantic files** (D-13, D-26, D-27, D-30, INV-14, INV-15, INV-24, INV-25, EC-47): `test_agent_fork_isolation.py` (6 tests, 2 renamed), `test_agent_settings_validation.py` (8 tests, 1 renamed), `test_aggregate_agent.py` (4 tests, 1 renamed), `test_durable_sessions.py` (4), `test_session_failures.py` (1), `test_fork_tool.py` (1).
  - The protective intent of each test was kept. For example, "a DeepSeek key never reaches OpenAI" is now checked through the child's record and `find_provider_api_key`. A mixed panel holding one unproven key now has to be refused (M-19) rather than silently dropping the key.

**Straggler hunt (static).** The spec says a red run finds stragglers. It cannot: a test that passes a provider key only through the environment in `AUTO`, or a list missing the primary's key, passes on base and fails only after the change. So I searched the source instead:

- `api_key=` and `.api_key` on renamed surfaces: none left. The remaining hits are non-text configs, Decision, other secrets, test names, and the gateway transport's own `api_key` (which the spec keeps).
- Provider environment variables in tests outside the two packs: only `tests/test_multi_provider_agentic_grader.py`, which mocks `create_runner` or fails in the algorithm first; the spec says it is unaffected. Also the not-superseded `test_tracing.py` and `test_model_registry.py`.
- Every `api_keys=` list against its primaries and table A takers: each binds (for example `["sk-main-key"]` on openai through D-29, `["k"]` on deepseek with an anthropic backup). None would raise M-6, M-18, or M-19 by accident.

Result: no stragglers beyond the §13 rows.

## 6. Spec defects and ambiguities (none blocking)

1. **AC-7** says "equal `ProviderKeys`", but step 7 orders the record by first appearance, so `[K_x, K_a]` and `[K_a, K_x]` give different tuples. The tests compare an order-free `key_view` plus identical requests.
2. **AC-24's "when" column** lists `create_runner_for_modality` among the `TypeError` surfaces, while its "then" column and M-17 say `ConfigurationError`. The tests bind `ConfigurationError` with `details["model"]`.
3. **The error type for an impossible `TextCredentials` combination** is unspecified. The tests assume `ConfigurationError`.
4. **AC-22 versus §13.** §13 puts `tests/test_harness_redaction.py` on the "Not superseded" list but says it "gains `api_keys` list and tuple cases". The briefing forbids touching it, so the AC-22 cases are in `test_provider_keys_security.py`.
5. **INV-4 lists `AgentFallbackSettings`**, which holds no key after D-26. Its repr cannot leak, so it has no case. `AgentFallback`'s repr is already credential-free at base, so its case documents rather than discriminates.
6. **The §13 row for `test_fallback_runner_inherits_the_agent_timeout`** files it under `FallbackApiKeyInheritanceTests`; it lives in `FallbackRunnerTimeoutTests`. A plain rename would break after implementation, because the backup runner would be a gateway runner and floor 300 s to 630 s. The test now runs in `DIRECT` with an anthropic key in the record.
7. **Check order** for `AUTO` with `OPENAI_API_KEY=vb_live_…` and no `VIDBYTE_API_KEY` (M-9 or M-14 first) is unspecified. The test asserts `error_kind` only.
8. **Pinning of a `DIRECT` runner** is unspecified: INV-12 covers gateway runners only. The base half "an unpinned BYOK runner falls to the placeholder" was dropped, as its §13 row directs.
9. **"A red run finds the stragglers"** (§13) is not true for the three kinds it lists, because they pass before the change. A static hunt was done instead (§5).
10. **A primary written as `ProposerSpec(" DeepSeek ", …)`** (kept from base) must be normalised by the matcher. The spec does not say so explicitly; it is noted for the implementer in test-plan.md §4.

## 7. Commits

- `test(sdk): move superseded tests to api_keys and DIRECT for byok-api-keys`: the §13 files and the managed pack's docs.
- `test(sdk): add failing tests for byok-api-keys [AC-1..AC-42]`: the new pack and `test-plan.md`.
- `docs(spec): record test proof for byok-api-keys`: the §6.2 Proof column only. A script checked that the 42 Proof cells are the only lines that changed.
- `docs(spec): add byok-api-keys S2 test author report`: this file.

Not pushed.

## 8. Rebase onto origin/main (2026-10-13)

- **Rebase.** The branch was rebased from `52aab816` onto origin/main `b53c8811` (48 commits). There were three conflicts, all in import blocks: `test_compatible_provider_text.py`, `test_deepseek_provider.py`, and `test_output_schema_provider_dialect.py`. Each keeps main's new imports and the §13 `TextModelMode` import. The other five edited files that main touched merged on their own.
- **Straggler search.** A static search covered every test file main added or changed since `52aab816`: `api_key` on a renamed surface, a real runner or agent in `AUTO` with only a provider key, lists without the primary's key, and an unserved provider or endpoint in `AUTO` (an AST scan of the whole `tests/` tree).
- **Tests updated.** It found 11 of main's new tests across seven files, one of them the new `test_gemini_provider_text.py`. It also found one base test the first hunt missed: the mistral `TextModelConfig` in `test_compatible_native_schema_payload_closes_every_object`, which D-23 would refuse in `AUTO`.
- **Recording and commit.** Each one is in test-plan.md §5 as "(post-rebase straggler)". They were committed as `test(sdk): update post-rebase stragglers for byok-api-keys`.
- **Red run.**
  - origin/main baseline: 3981 passed, 13 skipped.
  - Rebased red run: 307 failed, 3784 passed, 13 skipped, 7 errors. That breaks down as 117 in the pack plus 190 failures and 7 errors in §13 or straggler files, with none pre-existing.
  - `test_managed_text_failures.py` passes 10 of 10.
  - `python lint/run.py` reports SDK-LINT: PASS.
- **Spec §12.3.** Of the §12.3 files, main changed only `vidbyte/harnesses/serialization.py` (row 16). The leading `\b` of `_ERROR_ASSIGNMENT` became a lookbehind that also redacts prefixed and camelCase credential names (#993). Row 16's changes now apply on top of that.

### 8.1 Second rebase onto origin/main 595a7260 (#1023)

- **Rebase.** Main moved one commit, #1023, which changed `vidbyte/providers/output_schema.py` and added three tests to `test_output_schema_provider_dialect.py`. The rebase merged with no conflict: the §13 `TextModelMode` import and the `DIRECT` edits sit beside main's new `Field` import and tests.
- **Stragglers.** One of the three new tests is a straggler. `test_openai_responses_payload_unravels_annotated_refs` built `OpenAIProvider(api_key="k")`; it now uses `api_keys=["sk-k"]` and `mode=DIRECT`, like its sibling. Its `TextModelConfig` is openai in `AUTO`, which builds without a key, so it is unchanged. The other two new tests call `OutputSchemaFormatter` directly and stay green. The straggler is recorded in test-plan.md §5.
- **Red run.**
  - origin/main `595a7260` baseline: 3984 passed, 13 skipped.
  - Rebased red run: 308 failed, 3786 passed, 13 skipped, 7 errors. That is the earlier run plus the straggler (`AttributeError: DIRECT`) and the two new passing tests; every other failure is unchanged.
  - `test_managed_text_failures.py` passes 10 of 10, and lint passes.
- **Spec §12.3.** `output_schema.py` is not a §12.3 row and touches no key, mode, or credential path. It only rewrites the response schema, inlining `$ref` nodes that carry sibling keywords. So it does not interact with this feature.
- **Spec §13 line references.** The line numbers §13 cites for this file (`:91`, `:102`) are now stale, because the tests sit lower in the file. Only the line numbers changed; the tests are the same.
