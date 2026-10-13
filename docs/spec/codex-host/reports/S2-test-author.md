# S2 test author report: codex-host

**Stage facts**

| | |
|---|---|
| Stage | S2 test author |
| Spec | `docs/spec/codex-host/spec.md` r3 (approved) |
| Branch | `feat/codex-host` |
| Stage base | `f96b95cb` |
| Test commit | `46f1a9db` test(harnesses): add failing tests for codex-host [AC-1..AC-37] |
| Proof commit | `55f01f44` docs(spec): record test proof for codex-host |
| Report commit | a third docs commit holding this report |

Nothing was pushed.

**What was not touched:**
- No production code, no stubs, no `pyproject.toml` edit and no pytest config.
- No conftest, and no shared test file.
- No live `codex` run and no app-server process.
- No network.
- Not the claude-host worktree, and not the field guide.

The only docs read were request.md, spec.md and context/code-map.md.

## Inventory

The pack holds 101 tests in 11 modules under `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host/tests/features/codex_host/`.

| Module | Tests | Classes (tests) | Level | In CI |
|---|---|---|---|---|
| `test_codex_host_records.py` | 11 | RecordValidation (5), ErrorContract (4), Enum (2) | unit | 10 run; `test_wire_values_match_openai_codex` skips |
| `test_codex_host_packaging.py` | 7 | ImportSafety (2), FixedBytes (3), Export (2) | packaging (fresh `python -I` child, file bytes) | 6 run; `test_imports_leave_an_installed_sdk_unloaded` skips |
| `test_codex_host_bridge.py` | 2 | ValidateNames (1), BridgeHandler (1) | unit | run |
| `test_codex_host_tools.py` | 17 | Shape (2), Error (2), Scope (5), Argument (5), Output (1), Construction (1), Mcp (1) | unit, over `StubCodexHost` | run |
| `test_codex_host_lifecycle.py` | 13 | Snippet (1), Open (4), Guard (3), Close (3), ModuleFunction (2) | integration | skip |
| `test_codex_host_turns.py` | 13 | Spawn (3), Wait (4), TurnOutcome (4), SteerAndUsage (2) | integration | skip |
| `test_codex_host_threads.py` | 19 | Continue (4), LaunchAndFork (4), Read (4), Reviewer (3), ThreadConfig (4) | integration | skip |
| `test_codex_host_review_goals.py` | 9 | Review (4), Goal (5) | integration | skip |
| `test_codex_host_failures.py` | 6 | LateAcceptance (5), Privacy (1) | integration | skip |
| `test_codex_host_router.py` | 1 | Router (1) | integration | skip |
| `test_codex_host_sdk_contract.py` | 3 | SdkContract (3) | contract (the installed openai-codex) | skip |

Totals:
- 35 tests run in CI, and all are red now.
- 66 skip in CI with the reason "requires the optional openai-codex extra". CI installs only `.[dev]`. These run wherever the `codex` extra is installed.

Coverage:
- Every row from AC-1 to AC-37 has at least one test, or "manual QA", or "not testable here" with the reason. See the spec's §6.2 Proof column.
- The test plan's coverage map also maps D-29, INV-1, INV-2, INV-6, INV-11, INV-25, INV-29, INV-30, INV-34, INV-35, INV-41, D-20, D-28, EC-14, EC-39, EC-44, EC-46, EC-53 to EC-57, EC-72, T-1, T-2, T-3, T-6 and T-8.
- The test most likely to catch a real bug is `test_the_output_cap_counts_only_the_turns_own_tokens_and_interrupts_once`. Codex's `total` usage counts the whole thread. A cap compared against it interrupts a new turn on any thread with history. The test also pins the exact boundary, so that reaching 50 is not a crossing.

## Pruned, and why

The test plan's "Tests deliberately NOT written" table has the full reasons. In short:
- **AC-1, the live half.** It is manual QA, because a live turn spends the user's plan (NG-13).
- **Duplicates of existing suites:**
  - `translate` and `attach`: `tests/test_codex_tools.py` already covers them (AC-28, INV-39).
  - The existing `FailureCode` rules: `tests/test_session_failures.py` and `tests/test_codex_failure_recovery.py` already enforce them (INV-40).
- **Gate steps** for the rest of AC-36: Semgrep, the public-API check, the git-blob SHA-256 and `CI passed.`. They run in S3–S5.
- **Real 300 s bounds** (EC-5, EC-35, EC-68, EC-70). The bound is patched to 0.3 s instead.
- **Windows npm launcher trees** (EC-3, EC-69). T-7 is covered by structure: the schema test shows that no tool takes `config_overrides` or `env`.
- **Out of scope or accepted by the spec:**
  - EC-65, memory growth: no deterministic check exists without timing.
  - T-4: stdio only, so there is no host behaviour to test.
  - EC-77: an accepted residual.
  - Q-7, Q-8 and Q-9: forbidden by the brief.
- **Hypothesis property tests.** Hypothesis is not a repo dependency, so exhaustive tables are used instead.
- **Direct unit tests of `CodexGoalFinishRule`.** The spec gives it no API of its own.
- **The wire source of `limit_reached`.** The spec leaves it open; see the spec defects below.
- **Late acceptance (INV-11) for continue, the goal start and launch items.** AC-32 names only spawn and review, and those are tested. The goal-start variant takes a different cleanup path (`cancel_goal_operation` instead of `turn/interrupt`). It is the one worth adding if S4 asks, so it is listed under OPEN ITEMS.

## Fixtures added

All fixtures live in the pack. No conftest was added and no shared fixture was changed.

**`codex_host_support.py`**
- The spec's literal texts and tables:
  - `NEXT_STEPS`, `NEW_FAILURE_CODES`, `CLASSIFICATION_ROWS`, `TOOL_TABLE` and `TOOL_NAMES`.
  - `EXPERIMENTAL_API_TEXT`, `USER_REVIEWER_TEXT`, `UNREGISTERED_TOOL_TEXT` and `PIP_INSTALL_FRAGMENT`.
  - `MINIMUM_VERSION`.
- The privacy canaries: `SECRET_EMAIL`, `ENV_SECRET`, `STDERR_SECRET` and `LINE_SECRET`.
- `error_texts(exc)` returns each error's message, repr, details and next step, together with its visible chain (`__cause__`, and `__context__` unless suppressed).
- `assert_no_canary` and `input_texts`.
- The `requires_sdk` gate.
- `HostTestCase`:
  - It imports the connection module first, then patches the seam `vidbyte.harnesses.native.codex.connection.CodexClient` and `shutil.which`.
  - Its helpers are `open_host`, `close_host`, `spawn`, `wait_done`, `assert_problem`, `assert_codex_error`, `patch_connection`, `patch_platform`, `wait_for_request`, `wait_until`, `ask`, `count` and `run_in_other_loop`.
  - It fails any test whose fake recorded an internal handler error.
- `make_echo_tool` and `_EchoTool`, which records its calls.
- `StubCodexHost`, a duck-typed host for the tool tests. It records every call and offers `raises`, `gates` and `finish`.

**`codex_host_fakes.py`**
- `FakeAppServer` is an in-memory codex app-server 0.162.1. It logs every request with the thread that wrote it.
- It offers:
  - holds that wait up to `WAIT_SECONDS`;
  - scripted `fail(...)` and `before_response(...)`;
  - notification drivers: `complete_turn`, `emit_usage`, `goal_update`, `die`, `send_raw` and `server_request`;
  - `seed_thread`, and knobs for the account, usage, sandbox, version, reviewer and policy, and the paging cursor.
- `client_class(server)` builds a subclass of the real `CodexClient` whose process is an in-memory pipe. The real reader thread, router, retry helper and goal routing all run.
- The client records writes attempted after close as `write_after_close`.
- `RecordingGoalState` logs `finish` and `wake_notification_reader`. The client logs `cancel_goal_operation`, `unregister_goal_operation` and `next_goal_notification`, each with its thread.

**`README.md` and `FEATURE.md`**
- They state the pack's boundary, its non-goals, its file index and the CI skip.
- They hold the failure inventory the tests were chosen from, and the strategies that were left out.

## Red output (before implementation)

The bootstrap is one venv outside the worktree; nothing was installed globally:

```
python -m venv C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host
C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host/Scripts/python -m pip install -e "C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host[dev,codex]"
```

It installed openai-codex 0.162.1, pytest 8.3.5, pytest-asyncio 1.3.0 and pydantic 2.14.1.

**The pack in the `[dev,codex]` venv.** Command: `PYTHONPATH=$(pwd) $PY -m pytest -q -p no:cacheprovider -rfE tests/features/codex_host`

```
FAILED tests/features/codex_host/test_codex_host_turns.py::CodexHostSteerAndUsageTests::test_steer_and_interrupt_act_only_on_a_running_turn_this_host_returned - ModuleNotFoundError: No module named 'vidbyte.harnesses.native'
FAILED tests/features/codex_host/test_codex_host_turns.py::CodexHostSteerAndUsageTests::test_usage_tracking_lists_terminal_turns_with_their_own_deltas_and_rollup_cost - ModuleNotFoundError: No module named 'vidbyte.harnesses.native'
101 failed in 4.55s
```

The reasons all mean "the feature is missing":

| Count | Reason |
|---|---|
| 65 | `No module named 'vidbyte.harnesses.native'` |
| 12 | `cannot import name 'CodexHostTools'` |
| 6 | `No module named 'vidbyte.lib.dataclasses.codex_host'` |
| 2 | `No module named 'vidbyte.tools.builtins.codex'` |
| 2 | `cannot import name 'codex_host'` |
| 2 | no attribute `CodexApprovalPolicy` |
| 2 | the import probe failed: the child cannot import `vidbyte.harnesses.native` |
| 1 | `CodexAgentError.__init__() got an unexpected keyword argument 'next_step'` |
| 1 | `cannot import name 'CodexApprovalsReviewer'` |
| 1 | `cannot import name 'CODEX_NEXT_STEPS'` |
| 1 | `FileNotFoundError` for `native/__init__.py` |
| 1 | no `CodexToolTranslator.validate_names` |
| 1 | no `CODEX_HOST_REQUEST_TIMEOUT_SECONDS` |
| 1 | no `CodexToolBridge.handler` |
| 1 | the `FailureCode` list lacks the new codes |
| 1 | the README bullet is absent |
| 1 | the REPO_MAP section is absent |

Per file:

| File | Result |
|---|---|
| records | `11 failed in 0.80s` |
| packaging | `7 failed in 2.06s` |
| bridge | `2 failed in 0.73s` |
| tools | `17 failed in 0.94s` |
| lifecycle | `13 failed in 1.43s` |
| turns | `13 failed in 1.42s` |
| threads | `19 failed in 1.57s` |
| review_goals | `9 failed in 1.30s` |
| failures | `6 failed in 1.21s` |
| router | `1 failed in 1.07s` |
| sdk_contract | `3 failed in 1.05s` |

**The CI view.** Command: `PYTHONPATH=$(pwd) $PY -c "import sys; sys.modules['openai_codex']=None; import pytest; sys.exit(pytest.main(['-q','-p','no:cacheprovider','-rfEs','tests/features/codex_host']))"`

```
FAILED tests/features/codex_host/test_codex_host_tools.py::CodexHostToolsMcpTests::test_mcp_server_lists_and_runs_the_toolset - ImportError: cannot import name 'CodexHostTools' from 'vidbyte.tools.toolsets' (…)
SKIPPED [1] tests\features\codex_host\test_codex_host_turns.py:413: requires the optional openai-codex extra
35 failed, 66 skipped in 1.75s
```

**The whole suite.** Command: `PYTHONPATH=$(pwd) $PY -m pytest -q -p no:cacheprovider -rfE tests`

```
FAILED tests/features/codex_host/test_codex_host_turns.py::CodexHostSteerAndUsageTests::test_steer_and_interrupt_act_only_on_a_running_turn_this_host_returned
FAILED tests/features/codex_host/test_codex_host_turns.py::CodexHostSteerAndUsageTests::test_usage_tracking_lists_terminal_turns_with_their_own_deltas_and_rollup_cost
101 failed, 3940 passed, 22 skipped in 37.92s
```

All 101 failures are under `tests/features/codex_host/`. No other test fails.

## Commands claimed to pass (final lines)

**The existing Codex suites (NG-5).** These are the nine `tests/*.py` files that mention codex: `test_codex_agent_input_bridge`, `test_codex_failure_recovery`, `test_codex_middleware`, `test_codex_output_contracts`, `test_codex_pipelines`, `test_codex_tools`, `test_codex_usage_tracking`, `test_readme_size_limit` and `test_skills_interface`.

```
...............................                                          [100%]
247 passed in 1.98s
```

**Collection.** `--collect-only -q tests` gives 3962 tests from before, plus the 101 new ones:

```
4063 tests collected in 1.29s
```

**Lint.** `PYTHONPATH=$(pwd) $PY lint/run.py`, run with the pack and the test plan staged:

```
S063 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S063 --all

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

Every rule reports FOUND equal to its baseline, so nothing new appeared. The findings it does report (for example, S063 and S064 at 4 each, and S020 at 1 in `vidbyte/agents/multi/README.md`) sit in existing files, none of them in the pack.

## Spec defects

1. **INV-23 contradicts EC-67 and AC-32.**
   - INV-23 says wait, get, steer and interrupt "accept only handles this host returned".
   - EC-67 and AC-32 say a turn whose spawn was cancelled is registered, and that "a later get shows the turn's terminal status". That spawn never returned a handle.
   - The tests read the spec this way: a handle is owned by value, as `(thread_id, turn_id)` of a turn this host registered, late-accepted turns included. They rebuild `CodexTurnHandle(thread_id=…, turn_id=…)` from ids.
   - A fix in S3 or S4 would reword INV-23 to "handles of turns this host registered".
2. **The source of `CodexRateLimits.limit_reached` is not specified.** §9.1 types it as `str`, but §9.2 names no wire field for it. The tests check only the record's JSON shape, through the tool output test.
3. **The problem on a late-accepted, interrupted turn is not specified.** INV-11 says the turn is registered and sent one interrupt, but not which problem code (if any) its snapshot carries. The tests assert only the INTERRUPTED status.

## Test-side limits (deterministic: none can fail falsely)

- **EC-78, the queued start.** The test cannot observe the host executor's queue, so it yields 200 loop turns before it cancels. If the spawn had not queued its `turn/start` by then, the test passes without exercising the withdrawal.
- **The goal update after the last completion.** A 0.2 s wait must return RUNNING. On a host slower than 0.2 s, a wrong finish rule could pass. A right rule always passes.
- **Close wins.** The turn is registered by a callback that a host worker posts to the loop. The test therefore polls `get_codex_turn_result` every 0.01 s, bounded by `WAIT_SECONDS`, until the turn appears.
- **The request bound.** It is patched to 0.3 s around a spawn, as AC-32 prescribes. Preflight requests to the in-memory fake answer in milliseconds, so the margin is about 100 times.

## Decisions

- **`README.md` was added to the pack.** An earlier draft decided against it. I reversed that because every sibling pack with tests has one, and spec §13 describes it. Lint rule S020 passes.
- **`error_texts` follows the visible exception chain.** §12.3 row 10 has every caller raise the mapped error `from None`. A chained SDK exception that carries a canary is therefore a leak.
- **D-29 has its own test**, `test_a_fork_answers_tool_calls_with_its_parent_threads_tools`. I added it in the final review because nothing else proved that a fork answers its parent's dynamic tools.

## OPEN ITEMS

- Spec defects 1 to 3 above. The first one binds the implementation: ownership must be by value.
- INV-11's late acceptance for a goal start (`cancel_goal_operation` exactly once), a continue and a launch item has no test of its own. AC-32 names only spawn and review.
- The 66 gated tests never run in CI. S3–S5 must run the pack in a venv with the `codex` extra.
