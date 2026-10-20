# S2 test-author report: loop-spend-cap (R3)

- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-loop-spend-cap`
- **Branch:** `feat/loop-spend-cap`
- **Base:** `643a52f6`
- **Spec:** `docs/spec/loop-spend-cap/spec.md` r3 (approved)
- **Run date:** 2026-10-20

## Outputs

- **The new pack `tests/features/loop_spend_cap/`:**
  - `FEATURE.md` and `README.md`;
  - the shared harness `loop_spend_cap_fixtures.py`;
  - ten test files with 59 test functions, giving 123 collected cases:

| File | Cases |
|---|---|
| `test_loop_spend_cap_contract.py` | 46 |
| `test_loop_spend_cap_runtime.py` | 19 |
| `test_loop_spend_cap_copy_paths.py` | 13 |
| `test_loop_spend_cap_refusals.py` | 13 |
| `test_loop_spend_cap_run_ending.py` | 11 |
| `test_loop_spend_cap_jev.py` | 7 |
| `test_loop_spend_cap_docs.py` | 6 |
| `test_loop_spend_cap_acceptance.py` | 4 |
| `test_loop_spend_cap_children.py` | 2 |
| `test_loop_spend_cap_failure_routing.py` | 2 |

- **The one allowed existing-test edit:** `tests/test_codex_output_contracts.py` gets `"max_spend_usd": 1.0,` after `"tool_settings": ToolSettings(),` (§12.3 row 26). No assertion was changed.
- **The test plan:** `docs/spec/loop-spend-cap/test-plan.md`.
- **The spec:** its §6.2 Proof column is filled for AC-1..AC-32. A line-by-line comparison against the previous commit shows that only the last cell of those 32 rows changed.
- **Commits:**
  - `021f73dc` test(agents): add failing tests for loop-spend-cap [AC-1..AC-32];
  - `19bfde45` docs(spec): record test proof for loop-spend-cap;
  - this report.

**What I did not do:**
- no production code, stubs or placeholder modules;
- no install;
- no `scripts/run_ci.py`;
- no merge, and no push.

## 1. Failure inventory

The inventory has three parts:
- every spec ID with a testable promise: AC-1..AC-32; INV-2, INV-4, INV-5, INV-8 to INV-17, INV-20 and INV-23; EC-1 to EC-9, EC-12 to EC-25, EC-28 to EC-30, EC-32, EC-33, EC-39, EC-40 and EC-42; T-1 to T-3; FR-5, FR-10 and D-16;
- the boundary entries I added;
- the "input + state → wrong output" line for each entry, which sits in the test-plan coverage map and in the `FEATURE.md` Known Failure Modes table.

The entries I added beyond the spec's happy path:

| Added entry | Input + state → wrong output | Test |
|---|---|---|
| Exactly at the cap | spend == C → `>` lets one more segment spend | AC-4 and the `stop_output` boundary tests (`nextafter(C, 0)` and `nextafter(C, inf)`) |
| The tightest cap that must not stop | cap = `nextafter(total, inf)` → a cap check with an off-by-one or a rounding step changes the reply | `test_a_cap_the_run_never_reaches_changes_nothing`, five scenarios, each ending on a different existing stop |
| The smallest and largest valid caps | `5e-324` or `sys.float_info.max` is rejected by an overly tight range | `test_settings_accept_valid_caps_unchanged` |
| `-inf` and a very long string | a lower-bound-only check passes `-inf`, and the error message echoes a secret-looking value | AC-2 values plus T-3 |
| Duplicates and ordering in the blind text | repeated unpriced models or operations are listed twice, or causes are not sorted | `test_stop_output_names_every_blind_cause_in_spec_order` records the "b" model before "a", and records duplicates of each |
| Chain order in the construction refusal | the unpriced fallbacks are named sorted, or the priced one between them is named too | `[unpriced_fallbacks_in_chain_order]` uses `-z`, a priced model, then `-b` |
| Partial failure | 1 of N calls is unpriced → its cost is summed as $0 and the run looks cheap | AC-9 asserts `cost_usd` equals the priced call alone, and the run stops blind |
| Concurrency | two capped children run at the same time on one event loop (a barrier, not sleeps) → one child reads its sibling's spend, or the parent misses their total | `test_concurrent_capped_children_…` |
| Ties with every other budget at each check point | CP1 with `max_iterations`, CP2 with `max_tokens`, CP3 with `max_tool_calls` → the other budget's stop reason wins | AC-22, plus the `max_tokens_tie` and `max_tool_calls_tie` cases |
| The flag-off path | every capped test has an uncapped control that proves the step under test really happens without the cap | controls throughout, plus the metamorphic test |
| The model trying to lower or clear the cap | `fork_conversation` with `max_spend_usd` = 0.5 × C or `None` → accepted, since only "raise" was considered | `test_the_fork_tool_refuses_any_model_supplied_cap[raise, lower, clear]` |
| A nested child agent | a sub-agent tool's spend lands after CP3 for the next tool → invisible to the parent | AC-7 through `as_tool()` |

Entries considered and found not applicable:
- unicode and paths with spaces (the field is a number, and no test writes a path except `tmp_path` for the snippet);
- time, DST and clock skew (the pricebook has no clock; §13 notes that DeepSeek is always rated at its peak rate);
- idempotency on retry (the spec forbids retries after a cap stop, and that is what AC-29 tests).

## 2. Selection and pruning

**Count.** The number of test functions (59) is above the template's typical 8-25 because the spec has 32 ACs across about twelve subsystems. Each AC needs its own seam: the runtime, the ledger, construction, copy paths, Jev, multi-agent, algorithms, sessions, evals and docs. Parametrization accounts for the gap between 59 and 123. Each parametrized case is a distinct input the spec names, or a distinct failure:
- the seven invalid values AC-2 lists;
- the sixteen INV-2 combinations, which replace a property-based test because Hypothesis is not installed;
- the four non-linear runtimes AC-11 lists;
- the five metamorphic scenarios, each ending on a different stop.

**Pruned** (the test plan's "Tests deliberately NOT written" table gives the full reason for each):
- AC-24: it passes on `base_commit`, and lint and the pins guard it;
- a "no new FailureCode" test (it passes before the feature exists);
- `dataclasses.replace` revalidation;
- a direct `AgentSpendCap.model_refusal` unit test (it would only re-prove the construction tests);
- EC-27 (the same CP1 as AC-22);
- the "?" chain entry;
- the release record and the prose clauses of AC-26;
- NFR-1 and NFR-2 timing;
- `10**400`;
- EC-35, R-6 and Q-14;
- Q-7..Q-14;
- EC-36;
- EC-10, EC-38, EC-11, EC-26 and EC-31.

**Removed during self-review:**
- a stray environment-variable assert in `test_loop_spend_cap_run_ending.py` that tested nothing;
- an unused `_usage_payload` helper in `test_loop_spend_cap_jev.py`;
- the grader test's original shape, which had no uncapped control. It was rebuilt so that the control must call the grader once.

**Two questions applied to every test:**

1. Would a plausible wrong implementation pass it? This was answered empirically (§5). 42 single-fault mutants of a working prototype were each caught.
2. Would it go red on main after a later, unrelated PR?
   - **Dollar figures:** all come from `reference_cost`, which records the same scripted responses into a fresh `UsageTracker` over the default pricebook. A rate change cannot redden a test.
   - **Model names:** two are named, and both are checked by `assert_price_preconditions()` with a message.
     - `gpt-5.4-mini` is §4's own model.
     - `gpt-unpriced-spend-cap-probe` resolves to the text runner and has no price.
     - If either fact changes, the failure says so, instead of the test silently proving something else.
   - **Other pins:** no test pins a count, a rate, a version, a hash, line numbers or prose. The docs tests pin names only.

## 3. Red run (exact output)

Bootstrap: none. Every command ran from the worktree root with `PYTHONPATH=$(pwd)` inline, on `643a52f6` plus the uncommitted pack, which is identical to `021f73dc`.

```
$ PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/loop_spend_cap
...
FAILED tests/features/loop_spend_cap/test_loop_spend_cap_runtime.py::test_a_failed_operation_recording_stops_the_run_blind
FAILED tests/features/loop_spend_cap/test_loop_spend_cap_runtime.py::test_spend_after_the_last_tool_check_is_caught_at_the_next_iteration_before_max_iterations
123 failed in 1.92s
```

Reasons, grouped with `--tb=line`:

```
 65 TypeError: AgentLoopSettings.__init__() got an unexpected keyword argument 'max_spend_usd'
 20 TypeError: AgentRuntimeConfig.__init__() got an unexpected keyword argument 'max_spend_usd'
 18 AttributeError: 'UsageRollup' object has no attribute 'cost_measured'
  6 AssertionError: Regex pattern did not match.   # YAML: today's loader says "'agent.loop' contains unsupported field(s): max_spend_usd."
  5 ModuleNotFoundError: No module named 'vidbyte.agents.spend_cap'
  1 vidbyte.lib.errors.base.ConfigurationError: 'agent.loop' contains unsupported field(s): max_spend_usd.
  1 AttributeError: MAX_SPEND
  1 AssertionError: assert '\n## Spend Cap\n' in '# Agents\n\nThe Vidbyte SDK uses agents ...
  5 AssertionError: <llms.txt | jev README | vocabulary.md | agentic-loop-settings SKILL | output-contracts SKILL> does not name ...
```

The area command (the pack plus `tests/features/sdk_loop_settings`, `tests/features/sdk_model_usage`, `tests/test_agent_runtime.py`, `tests/test_session_failures.py`, `tests/test_fork_tool.py`, `tests/test_jev_usage_ledger.py` and `tests/test_codex_output_contracts.py`):

```
FAILED tests/test_codex_output_contracts.py::ContractValidationTests::test_rejects_every_field_the_constant_lists
124 failed, 303 passed in 2.45s
```

The single red outside the pack is the expected row-26 red (`AssertionError: Items in the first set but not the second: 'max_spend_usd'`). It goes green when rows 2, 25 and 26 land. No other test in the area fails, so there is no pre-existing red to name.

Further checks on the worktree:
- `pytest --collect-only tests` collects 7690 tests with no collection error.
- The suites the pack borrows from or sits beside give 1099 passed: `tests/multi_agent`, `test_multi_provider_agentic_grader.py`, `test_pdj_stage_model_provenance.py`, `test_reflexion_algorithm.py`, `test_independent_critic_algorithm.py`, `test_queued_prompt_usage.py`, `tests/features/infinite_memory_agent`, `tests/features/agent_output_connectors` and `test_algorithms_honor_middleware_abort.py`.
- The three tests §13 says must keep passing unedited are included in that run.

**Import guard.** The prompt pointed to the `FEATURE_MISSING` autouse-fixture idiom. I used the other idiom the prompt allows: new names are imported inside the tests. The shared fixture module imports only names that already exist. The effect is the same. The pack collects, and each test fails in its call phase on its own missing name, rather than all failing on one import error.

## 4. Fixtures added or extended

- **Added:** `tests/features/loop_spend_cap/loop_spend_cap_fixtures.py`. It provides:
  - the scripted runner and the response builders;
  - `reference_cost` and `usage_costing_at_least`, which are pricebook-derived;
  - `assert_price_preconditions`;
  - the recording tools;
  - the runtime and agent builders.
- **Extended:** no shared fixture file. These existing names are imported, unchanged:
  - `bind_test_runner` and `OfflineTestAgent` from `tests/agent_test_support.py`;
  - `_answer` from `tests/test_jev_usage_ledger.py`;
  - `_ALLEGATIONS`, `_DEFENSES` and `_DECISIONS` from `tests/test_pdj_stage_model_provenance.py`.

  If one of those files is later renamed, the pack fails at import, loudly.
- **Fake seams used**, which are only the model wire as §13 requires:
  - a runner bound with `bind_test_runner`, or a `RunnerHandle` given to `AgentRuntime`;
  - `HttpTransport.request`, patched with a callable instance, because a plain function would be bound as a method;
  - `TypeSafeProvider.run_decision`;
  - the grader's `ModalityDetector.create_runner`;
  - InfiniteMemory's `BaseAgent._runner_for_model`.
- **Not mocked:** `UsageTracker`, `_arun_once`, the ledger scope in `generate_reply`, and `FailureMetadataNormalizer`.
- **Keys:** keys are built at runtime (`"vb_live_" + "a" * 32`), and AC-1 removes every other `*_API_KEY` variable. A scan of the pack finds no `sk-`-shaped literal.

## 5. Independent verification (scratch only, never committed)

To check that the tests are satisfiable and that they discriminate, I built a throwaway prototype of spec §12 in a scratch copy of the tree, outside the worktree. That copy is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/proto`, patched by `scratchpad/proto_patch.py`.

**Green on the prototype:**
- The pack gives 123 passed.
- The area command gives 427 passed, so the row-26 test goes green with rows 2, 25 and 26.
- A wider run of 16 suites earlier gave 1520 passed.
- Each test file passes when run alone, and the whole pack passes in reverse file order three times.

**Mutation sweep** (`scratchpad/mutants.py`): 42 single-fault mutants, each killed by at least one test, with no survivors. Among them:
- **The comparison and the blind check:**
  - `>` for `>=`;
  - the blind check removed;
  - the blind check run before the reached check;
  - the model causes unsorted;
  - the unaccounted cause dropped.
- **`cost_measured`:** it ignores operations, or ignores integrity, or reads an empty rollup as unmeasured.
- **The check points:**
  - CP1 moved after `max_iterations`;
  - CP2 removed;
  - CP3 moved after the internal-tool return, or removed;
  - CP4 removed;
  - the cap reading only generative usage.
- **The refusals:**
  - each refusal removed;
  - fallbacks ignored, or sorted;
  - the OpenRouter exemption removed.
- **The copy paths:** the cap dropped by the export, the forker, the fork tool, YAML, `to_runtime_config` or `repr`, and the settings accepting `bool`.
- **The queued-prompt drain:** it ignores the cap, or checks only the primary reply.
- **Jev:** the specialist guard uses `>=`, or allows an uncapped specialist, or is never called.
- **The router, efficiency and Codex entries removed.**
- **Each run-ending guard removed:**
  - reflexion;
  - the critic;
  - PDJ;
  - the grader (both the grading and the stop-text sites);
  - the worker blocker made retryable;
  - the manager-phase retry;
  - InfiniteMemory verification.

S4 owns the official mutation run. This sweep only shows that the pack is not vacuous against the obvious wrong implementations.

## 6. Lint and format

| Check | Command | Result |
|---|---|---|
| A001 | `PYTHONPATH=$(pwd) py -3.11 lint/run.py --rule A001` | `SDK-LINT: PASS`; `--all` lists no finding under the pack |
| S020 | `PYTHONPATH=$(pwd) py -3.11 lint/run.py --rule S020` | `SDK-LINT: PASS`; the one ratcheted finding is the pre-existing `vidbyte/agents/multi/README.md` entry |
| Ruff lint | `py -3.11 -m ruff check tests/features/loop_spend_cap` | All checks passed |
| Ruff format | `py -3.11 -m ruff format --check tests/features/loop_spend_cap` | 13 files already formatted |

Notes on the ruff results:
- Ruff ran with its default settings, because the repository has no ambient ruff config.
- To clear the `exec` finding (S102), the §4 snippet runs through `runpy.run_path` from a `tmp_path` file, in-process, so the scripted wire still answers it.
- The repository's own ruff policy (`lint/ruff.toml` plus the `lint/core/ruff.py` selectors) is scoped to `vidbyte/`. Run on the pack, it would flag ANN401 on test-helper `**kwargs: Any`, as it would on existing tests.
- Many neighbouring test files are not `ruff format`-clean (6 of 10 sampled). The pack is therefore wrapped at 88 columns, where its neighbours use long lines.

## 7. Spec issues and things that made tests hard to write

None blocks. No spec name was impossible, so nothing was invented.

1. **AC-24 cannot be proven red first.** It passes on `base_commit` by construction, because nothing changes. It is recorded as covered by lint C016, `generate-sdk-public-api.py --check` and the harness-threads pins. The pack adds only the "not exported" check.
2. **AC-26's release-record clause and its "no line calls unmeasured spend capped" clause cannot be tested here.** The record lives under `docs/`, which tests must not read, and the second clause is prose. S5 must review both.
3. **AC-5 and AC-7 name two private methods, `_continue_finish_attempt` and `_after_tool_iteration`, as observables, but §13 does not list them as seams.** The runtime tests observe them through `AgentRuntime` subclasses that count calls and then call the real method. The implementer must keep those names and signatures (`(result, state, messages)` and `(state, messages)`).
4. **The prototype surfaced an implementation trap.** `vidbyte/agents/base.py` has no module-level `AgentStopReason` import, but the row-6 drain condition compares against `AgentStopReason.MAX_SPEND`. Without an import, the drain raises a `NameError` that surfaces as `queued_prompt_error`, and AC-31 goes red. This is an implementer note, not a spec defect.
5. **`_LOOP_FIELDS` in `vidbyte/lib/dataclasses/config.py:92` is a `frozenset({...})` call.** Row 9 says "add `"max_spend_usd"`". The name must go inside the set literal; a careless append produces a second positional argument.
6. **The grader's trials share one tracker (EC-23), so both trials can stop on the cap.** The test therefore asserts that the run's result is a capped trial's own output and that the grader is called zero times. It does not assert which trial stopped.

## 8. For the next stage

- **Run command:** `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap tests/test_codex_output_contracts.py`.
- **Expected result after implementation:** 174 pass (123 in the pack, 51 in the Codex file). That is what the prototype gives.
- **Names and exact strings the implementer must match:** see the test plan's "Notes for the implementer".
- **Do not edit `tests/multi_agent/test_worker_stop_report.py::STOPPED_REPLIES`.**
