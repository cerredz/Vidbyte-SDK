# S2 test author report: claude-host

**Run.**
- Stage S2 (test author), 2026-10-13.
- Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-claude-host`, branch `feat/claude-host`.
- Base `678136bd`; started at `039049d3`.

**Commits.** Neither is pushed.
- `8e116bc7`, `test(claude-host): add failing tests for claude-host [AC-1..AC-40]`: the pack and `test-plan.md`.
- `docs(spec): record test proof for claude-host`: the §6.2 Proof column. This report rides in the same commit, so that the tree ends clean, together with the red-run figures in `test-plan.md` re-taken at `8e116bc7`.

## Outcome

- **Status.** 165 new tests in `tests/features/claude_host/`. Every one of them is red for the stated reason, and no other test in the repository changed state.
- **Coverage.** All 40 ACs have a test, with no "manual QA" proof cells. 27 candidates are recorded as deliberately not written.
- **Constraints kept.**
  - No production code.
  - No `pyproject.toml` edit.
  - No shared test file or `conftest.py`.
  - No existing test or fixture touched.
  - claude-agent-sdk not installed.
  - No `claude` process started and no network used.
- **Spec names.** Every name the spec commits to is importable at the path the spec gives, so nothing is BLOCKED.

## Inputs read

- `docs/spec/claude-host/spec.md` r3, in full.
- `docs/spec/claude-host/request.md`.
- `docs/spec/claude-host/context/code-map.md`.
- `AGENTS.md`.
- House style and the test-pack doctrine (`feature_test_packs.md`).
- The `report-formats.md` "test-plan.md" shape.
- Prior art:
  - `tests/test_codex_tools.py`;
  - `tests/features/coding_agent/`;
  - `tests/test_mcp_studio_server.py`;
  - `tests/test_agent_tool_loop.py`;
  - `tests/test_codex_failure_recovery.py`;
  - `tests/test_durable_sessions.py`.
- The downloaded claude-agent-sdk 0.2.165 source and `sdk.d.ts`. These were read only, with Read and Grep, to copy class names, fields and defaults into the fakes. Nothing from them was imported, executed, copied into the repository or installed: `find_spec("claude_agent_sdk")` is `None` in the venv.

## Failure inventory

**Spec IDs** (the per-ID map is in `test-plan.md`).

| Group | Disposition |
|---|---|
| AC-1 to AC-40 | All 40 tested. |
| INV-1 to INV-22 | All tested. |
| INV-23 | Already guarded by `tests/test_session_failures.py::test_every_code_has_category_prefix`. |
| INV-24 | Partly guarded by `tests/test_security_executor.py::test_default_policy_denies_write_without_execution` plus the pack. |
| INV-25 and INV-26 | Gate and existing suites; not written, because they would be green before implementation. |
| EC-1 to EC-60 | 51 tested, alone or grouped. 9 accepted limitations (EC-28, 43, 45, 46, 47, 51, 54, 55, 58) are not written. |
| T-1 to T-4 | All tested. T-3's command-line path and T-4's ungated MCP path are stated limitations. |
| NFR | NFR-1, 2, 3, 6, 7, 8 and 9 tested. NFR-4 and NFR-5 are lint and gate. NFR-10 and NFR-11 are not written. |

**Entries added beyond the spec IDs.** Each is written as input + state → wrong output.
- `version_ok("2.1.1000")` compared as text → a newer CLI is refused; `"2.1.29"` → an older CLI is accepted.
- Account `tokenSource="none"` → counted as signed in; a Bedrock or Vertex provider → refused.
- `builtin_tools=()` sent as a tuple → the SDK reads it as the preset and enables every built-in tool; `skills` as a tuple → `TypeError` at connect.
- `effort`, `user` or `settings` left at `""` → an empty flag on the command line.
- A `disconnect()` that raises after a successful turn → the turn turns FAILED, or the error escapes.
- A continue template carrying `session_id`, `fork_session`, `resume_session_at` or `resume_drops_turn` → it leaks into the resumed turn.
- An empty continue prompt → history is read before the refusal.
- Precondition order input.empty → not_installed → cap → busy reversed → the wrong code and next step.
- A natural-key rule broken for one spawn kind → two turns share a session id, or a resume gets a fresh id.
- `ResultError` checked after its `ProcessError` base → `error_max_turns` is reported as `process_exited`.
- The watchdog setting the caller-interrupt flag → a budget stop is reported as INTERRUPTED.
- A grace armed after the result was already read → the steered prompt is disconnected mid-turn (AC-37 d).
- A caller timeout cancels the steer's interrupt task → the grace is never armed and the turn hangs (AC-40).
- A probe cancelled mid-close → `claude` is orphaned.
- A tool rendering `str(exc)` → `ProcessError` stderr reaches the model.
- `"limit": "2"` accepted → a string reaches the semaphore.
- A sync `agent.run()` → drives the client from a foreign loop (EC-25).
- An extra model-written `cwd`, `permission_mode`, `max_budget_usd`, `cli_path`, `env`, `restricted` or `session_id` → it widens the bound request (T-2).
- The §4 snippets: the not-ready branch, and the orchestrator agent driving the tools under `arun`.

Boundaries covered:
- 0, 1 and N prompts;
- `limit=1`;
- `max_live_sessions` of 1 and `None`;
- the minimum version, exactly;
- empty strings;
- `None` versus `""` for optional SDK arguments;
- path case and trailing dots on Windows;
- CRLF and LF;
- far-past and far-future reset times.

Time is handled through events and fixed timestamps; no real clock decides any outcome.

## Selection and pruning

**Why the count is high.** The doctrine's "typical 8–25" fits a single function. This feature has 40 ACs, 26 invariants, 60 edge cases and 15 tools, and every AC is P0 or P1. I kept the count down in four ways:
- **Table-driven subTests.** One test per table instead of one test per row:
  - 13 stream conditions;
  - 16 exception rows;
  - 20 precedence rows;
  - every field-mapping row;
  - every validation rule;
  - 14 wrong JSON types;
  - 15 tools in each tool test.
- **Merging.** One test per behaviour, not per AC sentence.
- **One run, many assertions.** Expensive scenarios such as the grace cases share a helper that asserts the whole AC-37 contract once per case.
- **Pruning.** A test was dropped when it only re-proved another test.

**The 27 omissions.** Each is listed in `test-plan.md` under "Tests deliberately NOT written", with its reason. The main groups are:
- **Real-SDK contract tests.** They would be skipped here, so they could never be proven red, and the extra must not be installed.
- **Live end-to-end runs.** NG-10 rules them out: they spend the user's plan window.
- **Property-based tests.** `hypothesis` is absent, and adding it is forbidden. Exhaustive tables cover the small domains instead.
- **Stress tests.** No threshold exists to assert.
- **Q-1 to Q-11 behaviours.** Not built.
- **Nine accepted-limitation ECs.**
- **Three spec ambiguities** (see "Spec defects" below).
- **Invariants that are green before implementation.** INV-24's export half, INV-25, INV-26 and NFR-10 could never be red.
- **Lint-owned NFRs.** NFR-4 and NFR-5 belong to the gate.

**Changes during this session.**
- **`BoundRequestTests` hardened.** The test accepted either a refusal or a success, then checked only the clients that existed. A tool that refused every call, or refused because a leaked `cwd` caused a cwd conflict, would have passed with no assertions run. Now every call must do one of two things:
  - run its turns, and then each client must keep the bound fields;
  - refuse as `configuration.invalid_argument` and start nothing.

  Any other refusal fails the test.
- **`FEATURE.md`.** EC-46 is now listed with the other accepted limitations.

## Files produced

All of these are new.

| File | Contents |
|---|---|
| `tests/features/claude_host/FEATURE.md` | Feature boundary, contract, failure modes, suite map, omitted strategies. |
| `tests/features/claude_host/README.md` | The folder README. |
| `tests/features/claude_host/claude_host_fixtures.py` | The fake SDK and the shared case class. Fixtures section below. |
| `tests/features/claude_host/test_claude_host_acceptance.py` | 4 tests |
| `tests/features/claude_host/test_claude_host_admission.py` | 25 tests |
| `tests/features/claude_host/test_claude_host_contract.py` | 22 tests |
| `tests/features/claude_host/test_claude_host_history.py` | 11 tests |
| `tests/features/claude_host/test_claude_host_readiness.py` | 24 tests |
| `tests/features/claude_host/test_claude_host_request.py` | 18 tests |
| `tests/features/claude_host/test_claude_host_security.py` | 6 tests |
| `tests/features/claude_host/test_claude_host_stops.py` | 23 tests |
| `tests/features/claude_host/test_claude_host_tools.py` | 10 tests |
| `tests/features/claude_host/test_claude_host_turns.py` | 22 tests |
| `docs/spec/claude-host/test-plan.md` | The test plan. |
| `docs/spec/claude-host/spec.md` | §6.2 Proof cells only: 40 lines, each changed only from `\| \|` to `\| <node ids> \|`. Verified by a script against `git show HEAD:` and against the collected node ids (63 ids). |

**Levels.**

| Level | Tests |
|---|---|
| acceptance | 4 |
| contract | 22 |
| security | 6 |
| unit | 26 |
| integration at the fake seam | 107, of which 23 are lifecycle and concurrency tests in `stops.py` |

## Red output (exact)

**Environment.**
- **Venv.** `C:/Users/422mi/vidbyte-repos/.venvs/sdk-claude-host`, created at the start of S2 with the briefing's two commands and kept afterwards.
- **Import check.** `python -c "import vidbyte, importlib.util; print(vidbyte.__file__, importlib.util.find_spec('claude_agent_sdk'))"` → `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-claude-host\vidbyte\__init__.py None`.
- **Versions.** pytest 8.3.5, pytest-asyncio 1.3.0, and `vidbyte-sdk 0.2.1` as an editable install of this worktree.

All the runs below are at `8e116bc7`, from the worktree root, with `PY=.../.venvs/sdk-claude-host/Scripts/python`.

**Per file.** `PYTHONPATH=$(pwd) $PY -m pytest tests/features/claude_host/test_claude_host_<area>.py -q -p no:cacheprovider --tb=no` → each file's final line:
```
test_claude_host_acceptance.py: 4 failed in 0.69s
test_claude_host_admission.py: 25 failed in 0.76s
test_claude_host_contract.py: 22 failed in 1.32s
test_claude_host_history.py: 11 failed in 0.69s
test_claude_host_readiness.py: 24 failed in 0.73s
test_claude_host_request.py: 18 failed in 0.69s
test_claude_host_security.py: 6 failed in 0.68s
test_claude_host_stops.py: 23 failed in 0.75s
test_claude_host_tools.py: 10 failed in 0.69s
test_claude_host_turns.py: 22 failed in 0.74s
```

**The pack.** `PYTHONPATH=$(pwd) $PY -m pytest tests/features/claude_host -q -p no:cacheprovider --tb=short` → final lines:
```
FAILED tests/features/claude_host/test_claude_host_turns.py::InitializeAndInjectedResultTests::test_a_human_origin_result_is_the_prompts_own
FAILED tests/features/claude_host/test_claude_host_turns.py::InitializeAndInjectedResultTests::test_an_injected_result_updates_usage_while_the_turn_keeps_running
FAILED tests/features/claude_host/test_claude_host_turns.py::InitializeAndInjectedResultTests::test_hooks_applied_is_true_with_hooks_and_none_without
165 failed in 5.63s
```

A typical failure block:
```
_ HostSnippetTests.test_the_snippet_prints_the_status_the_answer_and_the_cost _
tests\features\claude_host\test_claude_host_acceptance.py:185: in setUp
    self.enterContext(self.fake.patched())
tests\features\claude_host\claude_host_fixtures.py:890: in patched
    from vidbyte.harnesses.native.claude.sdk import ClaudeSdkLoader
E   ModuleNotFoundError: No module named 'vidbyte.harnesses.native'
```

The last `E` line of every failure, grouped:

| Count | Last `E` line |
|---|---|
| 133 | `ModuleNotFoundError: No module named 'vidbyte.harnesses.native'` |
| 16 | `ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.claude'` |
| 4 | `ModuleNotFoundError: No module named 'vidbyte.tools.toolsets.claude'` |
| 2 | `ModuleNotFoundError: No module named 'vidbyte.lib.constants.claude'` |
| 2 | `ModuleNotFoundError: No module named 'vidbyte.lib.enums.claude'` |
| 1 | `ModuleNotFoundError: No module named 'vidbyte.tools.builtins.claude'` |
| 2 | `ImportError: cannot import name 'ClaudeOperationError' from 'vidbyte.lib.errors'` |
| 1 | `FileNotFoundError: ... vidbyte\harnesses\native\__init__.py` (MarkerContractTests) |
| 1 | `AssertionError: Element counts were not equal:` (FailureCodeContractTests: no `claude.*` members) |
| 1 | `AssertionError: None != ['claude-agent-sdk>=0.2.165,<0.3.0']` (PackageMetadataTests) |
| 2 | `AssertionError` diffs on the missing REPO_MAP entry and README bullet (DocumentationInsertTests) |

There are no collection errors and no skips. 0 of the 165 `FAILED` lines lie outside `tests/features/claude_host/`.

**Neighbours pass.** `PYTHONPATH=$(pwd) $PY -m pytest tests/features --ignore=tests/features/claude_host tests/test_codex_tools.py tests/test_mcp_studio_server.py tests/test_session_failures.py tests/test_agent_tool_loop.py tests/test_security_executor.py -q -p no:cacheprovider` →
```
............................................................sss......... [ 90%]
........................................................................ [ 97%]
.......................                                                  [100%]
943 passed, 16 skipped in 17.56s
```

**The whole suite without the pack passes.** `PYTHONPATH=$(pwd) $PY -m pytest -q -p no:cacheprovider --tb=line --ignore=tests/features/claude_host` →
```
........................................................................ [ 98%]
.........s.s............................s............................... [ 99%]
..                                                                       [100%]
3935 passed, 27 skipped in 32.31s
```
Nothing fails, so there is no pre-existing failure to report.

**Collection.** `PYTHONPATH=$(pwd) $PY -m pytest -q -p no:cacheprovider --collect-only` → `4127 tests collected in 1.32s`, which is 3962 + 165.

**Lint.** `PYTHONPATH=$(pwd) $PY lint/run.py` →
```
A001 RATCHETED: 643 known finding(s). Inspect with: python lint/run.py --rule A001 --all
S062 RATCHETED: 889 known finding(s). Inspect with: python lint/run.py --rule S062 --all
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```
`diff` against the lint output captured before the pack existed, with timings stripped, is empty.

## Fixtures added or extended

Every fixture is new and lives in `tests/features/claude_host/claude_host_fixtures.py`. No shared fixture, `conftest.py` or existing test was added to or edited.

- **`FakeClaudeSdk`** is per test. `types()` builds the real `ClaudeSdkTypes` from fakes, and `patched()` patches the one seam. Its controls are:
  - `hold`, `reply` and `release_gates`;
  - gates and error factories for `connect`, `interrupt` and `disconnect`;
  - `interrupt_answer` and `interrupt_reply`;
  - the `connected_now` and `max_connected` counters;
  - `client_for_session`, `turn_clients` and `all_queries`.
- **`FakeClaudeClient`** implements `connect`, `get_server_info`, `query`, `receive_messages`, `interrupt` and `disconnect`. It records `calls`, `queries`, interrupt and disconnect counts, and whether the disconnect finished or was cancelled. Tests drive it with `emit`, `finish`, `end_stream` and `fail_stream`.
- **`FakeHistory`** provides `list_sessions`, `get_session_info`, `get_session_messages` and `fork_session`. Each call records its thread id, and errors are injectable.
- **Copies of the 0.2.165 shapes:**
  - a `ClaudeAgentOptions` dataclass with exactly the 0.2.165 fields and defaults, so an unknown keyword raises `TypeError`;
  - the error hierarchy, with `ResultError` a subclass of `ProcessError`;
  - the message dataclasses, `AgentDefinition` and `HookMatcher`;
  - `create_sdk_mcp_server` and `tool`.
- **Factories:** `result_message`, `interrupted_result`, `assistant_message`, `init_message`, `rate_limit_event`, `task_progress`, `task_notification`, `model_usage_entry`, `initialize_response`, `signed_in_account`, `api_key_account` and `session_message`.
- **`TicketTool`**, a `BaseTool` that returns ok, returns an error or raises.
- **`ClaudeHostCase`**, an `IsolatedAsyncioTestCase` with `open_host`, `close_host`, `spawn`, `finished`, `snapshot`, `client_for` and `raises`, and cleanup that releases every gate and closes every host.
- **Helpers:** `eventually`, `eventually_async`, `settle`, `star_calls`, `passed_options` and `is_sdk_default`.
- **Constants:**
  - the verbatim §9.2 next-step texts;
  - the dummy markers (`sdk-error-marker-41c7`, `env-marker-value-8d2e`, `header-marker-value-3a9f`, `prompt-marker-text-6b1d`);
  - the fixed reset timestamps;
  - the patch targets `GRACE_TARGET` and `WHICH_TARGET`.

## Spec defects and things that made tests hard to write

**Loose wording the tests had to read one way.** S3 must follow these readings; S4 and S5 may want the spec clarified.
1. **D-8 and AC-16, "overage not allowed".** The spec does not cover a window whose `overage_status` is absent. The tests treat absent as not allowed, so the spawn is refused.
2. **EC-33.** It names codes only for a template with `session_id` (`unsupported_combination`) and one with `resume` (`session_busy`). For `continue_conversation=True` without fork and N>1, the test accepts either code.
3. **Rules worded "X requires Y" in the §9.1 validation.** The spec does not say whether a missing requirement is `invalid_argument` or `unsupported_combination`. Those cases accept either configuration code.
4. **The exception mapping has no row for a history read error.** A builtin `OSError` from an SDK file function has no named code. The test requires only a `ClaudeOperationError` with non-empty fields and no marker.
5. **D-27, "different after normalization".** The normalization is undefined (case, separators, trailing slash). The tests use clearly different folders and compare paths through `pathlib`.
6. **The sandbox `network` key.** The spec does not say whether an empty `network` object is sent, so the key is asserted only when a domain is set.

**Behaviour the spec leaves undefined, so no test pins it.**
7. **Classification row 5 with a success result.** It is unclear whether `rate_limit_rejected` follows D-8's overage condition, so a rejected window is tested only together with an error result.
8. **`launch_claude_subagents` of one prompt with a template `session_id`.** EC-33 covers N>1 only.
9. **A second `__aenter__` or `aclose`.** INV-15 says only "never reopened". The pack pins that calls stay refused after a re-entry attempt.
10. **§12.3 row 3, "load SDK (except history and fork)".** It does not say where history and fork load the SDK functions they need. AC-2 still requires `sdk_unavailable` from them. The tests pass valid primitives, so either order passes.

**Facts about the vendor SDK and the repository.**
11. **Python SDK literals.** The 0.2.165 `AssistantMessageError` and `RateLimitType` `Literal`s omit `model_not_found` and `seven_day_overage_included`, which the spec (EC-10, `ClaudeRateLimitType`) relies on. `message_parser.py` passes `data.get("error")` and `info.get("rateLimitType")` through unchanged, so the fakes emit them. The implementation must map raw strings. No real-SDK test confirms this at run time, because the extra may not be installed.
12. **No test can be red for INV-24's "keep every export" half.** A snapshot of today's export lists is green before implementation. It is left to the existing suites and S4.

**Seam constraints that shape the implementation.** These are not defects, but the spec states them only implicitly.
- The probe must `import shutil` and call `shutil.which`, because the patch target is `...probe.shutil.which`.
- The session module must read `CLAUDE_INTERRUPT_GRACE_SECONDS` as a module global at call time.
- `__aenter__` must pass `windows=` and `home=` by keyword.
- A client whose `connect()` raised must still be disconnected once.

**Repository facts.**
- Ruff is not enforced on tests; A001 and S062 are.
- C006 also scans tests, so the fakes carry no numeric range guards.

## Notes for S3

Read "Notes for the implementer" in `docs/spec/claude-host/test-plan.md`. It lists:
- every import path and signature the tests bind to;
- the patch targets;
- what the fakes model;
- the readings above.

Run the pack with `PYTHONPATH=$(pwd) <venv python> -m pytest tests/features/claude_host` from the worktree root. Do not edit any file under `tests/features/claude_host/`.
