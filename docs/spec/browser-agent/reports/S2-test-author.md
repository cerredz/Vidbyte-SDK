# S2 report: test author — browser-agent

Spec: `docs/spec/browser-agent/spec.md` r3 (approved) · Branch `feat/browser-agent` · Base `709a9ba1` · Tests commit `c6afb125`

## What was produced

- Feature pack `tests/features/browser_agent/` (12 files, all new): `README.md`, `FEATURE.md`, `browser_agent_fixtures.py`, and eight test modules — `test_browser_agent_acceptance.py` (5 tests), `_contract.py` (11), `_settings.py` (8 functions, 40 items), `_episode.py` (18), `_goal.py` (6), `_recheck.py` (7 functions, 11 items), `_rebuild.py` (3), `_observability.py` (11 functions, 12 items). Total: 69 test functions, 106 collected items.
- `docs/spec/browser-agent/test-plan.md`: the coverage map (every AC-1..AC-33, plus the INV, EC, D, T and NFR IDs the pack pins), the tests deliberately not written, the red run, and notes for the implementer.
- Spec §6.2: only the Proof column was filled (33 rows; `git diff` shows 33 changed lines, all `| AC-` rows).

No production code, stub, or placeholder was written. Nothing outside the pack, the plan, the §6.2 Proof column, and this report was changed.

## Inventory (by layer)

- Seams (spec §13): the model runner at `BaseAgent._runner_for_model`, routed by agent name (`vc-scout`, `vc-scout-episode-<n>`, `vc-scout-recheck`, `vc-scout-done-when`), and the stdio transport at `vidbyte.tools.mcp.attach.McpStdioTransport` (a factory that records every instance, its command, env, timeout, and every `tools/call`). Everything else runs for real, including the MCP client and bridge, `ToolSettings`, the compaction engine, the prompt catalog, the pricebook, and the usage tracker.
- Collection trap: no module imports `vidbyte.agents.browser`, `vidbyte.lib.constants.browser`, `vidbyte.lib.enums.browser`, `vidbyte.lib.dataclasses.browser`, or the new `Prompt` members at module level; each test imports what it needs inside its body. The pack therefore reports 106 failures and never "Interrupted: errors during collection".
- Determinism: no sleeps (ordering uses `asyncio.sleep(0)` and `asyncio.Event`), no wall clock, no network, no subprocess. Property tests use `random.Random(20261017)` and `random.Random(1714)`. Files are LF; paths are built with `pathlib`.
- Vacuity guards: `ScriptedModel.assert_complete()` fails on any unscripted model call; action counts are counts of requests the fake server received; every "absent" assertion has a positive control (the key reached its own server, the worker saw its own observation, the history was over the cap before the rebuild, the recipe passes the worker cap before the trim is checked).
- Assertions read model-facing text from the prompt catalog (`template_regex`, `distinctive_line`) and limits from the `BROWSER_*` constants, so a wording change does not break a test, but a missing or swapped leaf does.

## Calibration (how the numbers in the tests were chosen)

Every count a feature test asserts was first measured on a plain `BaseAgent` with the same two fakes, in scratch scripts outside the repo:

- `max_tool_calls=3` stops a worker with `OutputSchemaViolationError`, `stop_reason "max_tool_calls"`, 3 server calls, 3 model calls, and `max_tool_calls: 0/3` in the first system string; a 4th call in the same turn is not executed (2 model calls).
- A `max_calls_per_tool` denial is an error result with reason `tool_settings_max_calls_per_tool`, state DENIED, and the worker continues.
- The sliding window cuts to `content[:400] + " [... truncated N characters ...]"`; MCP results over 8,000 characters are cut by the client; 17 distinct tools × 9,000 characters pass 32,000 tokens and the trimmed 18th call stays under it with every call paired.
- Free text ends `contract_unsatisfied` after 5 model calls; a provider error reaches the caller as `AgentExecutionError` with `ProviderRequestError` as its cause.
- The orchestrator rebuild recipe from §13 holds: with `bulk_fetch` cut to 20,000 characters, each turn adds about 5,085 tokens of stored JSON; after one patch and 11 bulk turns the history is 56,020, and the 12th takes it to 61,107 (> 60,000).
- Two servers with one tool name raise `ToolRegistrationError("Tool already exists: fetch_markdown")`, close every transport, leave `mcp_servers() == ()`, and make no model call.

## Red run

Bootstrap: `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` → `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-browser-agent\vidbyte\__init__.py`.

`PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q -p no:cacheprovider` (final lines):

```
FAILED tests/features/browser_agent/test_browser_agent_settings.py::test_keys_never_appear_in_a_settings_repr_or_a_settings_error
FAILED tests/features/browser_agent/test_browser_agent_settings.py::test_a_non_settings_object_is_refused_naming_its_type
FAILED tests/features/browser_agent/test_browser_agent_settings.py::test_defaults_are_the_named_constants
FAILED tests/features/browser_agent/test_browser_agent_settings.py::test_a_preset_is_stored_as_its_registered_definition_and_env_is_read_only
106 failed in 2.07s
```

Every failure is the feature being absent (grouped from `--tb=line`): 88 `No module named 'vidbyte.agents.browser'`, 11 `No module named 'vidbyte.lib.constants.browser'`, 2 `cannot import name 'BrowserAgent' from 'vidbyte'`, 1 each `cannot import name 'browser' from 'vidbyte.lib.constants'`, `'BrowserEpisodeOutcome' from 'vidbyte.lib.enums'`, `'BrowserAgentRuntime' from 'vidbyte.agents'`, 1 `AssertionError: vidbyte/agents/browser does not exist`, 1 `assert {} == {'BROWSER_AGE…` (no prompt members). No error, no skip, no xfail.

Neighbours (must stay green), `PYTHONPATH=$(pwd) python -m pytest tests/test_mcp_attachment.py tests/test_mcp_bridge.py tests/test_agent_runtime.py tests/test_agent_fork_isolation.py tests/features/infinite_memory_agent -q -p no:cacheprovider`:

```
........................................................................ [ 97%]
......                                                                   [100%]
222 passed in 7.02s
```

AC-29 baselines at `709a9ba1`: the three stop-reason test files → `83 passed in 1.19s`; the nine `tests/features/jev_*` packs → `467 passed, 1 skipped in 5.04s` (the skip is pre-existing).

Focused lint on the committed pack: `python lint/run.py --rule S020` → `SDK-LINT: PASS` (README File Index matches the tracked files); `--rule A001` → `SDK-LINT: PASS`; `--rule A009` → `CLEAN`. `--all` listings show no finding under `tests/features/browser_agent/`. The full gate was not run (instructed).

## Pruned or not written

See the test plan's "Tests deliberately NOT written". In short: AC-29 is proved by the existing suites (a copy could never be red); NFR-2/NG-12 are git-diff properties; NFR-6..8 belong to the gate; INV-28's shared behaviors are pinned by the MCP tests; EC-9, EC-10, EC-21, EC-24, EC-26, EC-27 (beyond the not-capped side), EC-29, EC-30, EC-32 and EC-36's message order are accepted limitations or shared behavior; `hypothesis` is not a dependency. During review of my own draft I removed assertions the spec does not support: `BrowserAgentResponse()` equality in INV-23 (the record may be pre-filled), the settings class name in the INV-1 message, first-line leaf checks (two leaves could share a heading), and a `response.goal` check before any accepted patch.

## Spec defects and open questions found while writing the tests

1. **§4 snippet model is unpriced.** `gpt-4.1` has no pricebook row, so the snippet run against a real provider would raise `UsageAccountingError` under INV-21 (A-5 only checked the provider/model pair). The fakes report `gpt-5.4-mini`. Either price `gpt-4.1` or change the snippet's model.
2. **AC-12 "Its tool list is empty" and AC-5/INV-7 "only the ACTION tools" are not reachable as written:** `BaseAgent` adds its internal `isDone` to every catalog. The tests accept `isDone` there; the spec wording should say "no tool but the loop's `isDone`".
3. **A worker's provider error arrives wrapped** in `AgentExecutionError` (cause `ProviderRequestError`). INV-12 says the stuck card names "the error type name" without saying which; the test accepts either.
4. **The progress total measure is unspecified** (with or without line separators). The AC-32 test asserts the extra line overflows under either measure at the current constants.
5. **Unspecified, so untested:** whether a finish recheck resets the `recheck_every` counter; whitespace normalization inside a progress line; whether `goal_patched` fires on refusals; what `BrowserRecheckResult.episodes` counts; whether `<n>` in `browser-<role>-<n>` is 0- or 1-based (the tests accept either, consecutive per role).
6. **INV-27 says `_LINEAR_LOOP_RUNTIMES` keeps "its three members"**, while §12.3 row 21 adds `BROWSER`. The test follows row 21 (four members).
7. **Assumed constructors:** the property tests build `BrowserResponse()` with no arguments (the `JevResponse()` precedent) and `BrowserGoal(card, settings, response, events)` per §8.5.

## Notes for the next stage

- Do not edit these tests (§14). If one looks wrong, report it with the spec ID.
- Keep the agent-name templates, the two seam paths, and the §8.5 names; the tests bind to them.
- The S020 rule now indexes this pack's README; a new file in the pack must be added to its File Index.

## S5 grant (R-5, R-4, R-19, R-20)

2026-10-17, on the S4 review of `3f9e63c9` (branch head `5d1d6f30` before these commits). Only additions under `tests/`: no assertion was weakened or removed, and no source file was changed. All runs are offline (`env -u` on every provider key, `-p no:cacheprovider`). The mutants are the S4 probes, loaded as pytest plugins from the scratchpad.

| Finding | Commit | Test | Proof |
|---|---|---|---|
| R-5 | `4f73cf31` | epi → `test_default_settings_keep_the_two_newest_observations_of_each_tool` | Branch: `1 passed in 0.74s`. `-p mutant_keep_one` ("MUTANT ACTIVE: keep_recent forced to 1") and `-p mutant_default_one` ("MUTANT ACTIVE: keep_observations default and constant forced to 1") both fail on `E AssertionError: the settled default keeps the two newest snapshots of a tool whole` (`1 failed in 0.25s` / `0.28s`). |
| R-4 | `6dae8247` | obs → `test_an_unpriced_call_raises_usage_accounting_error` gains an `EventLog` sink and two asserts: the last event is `run_stopped`, and `run_finished` never appears | Red on the branch, for the right reason: `E AssertionError: ['run_started', 'goal_set', 'goal_rechecked', 'run_finished']` / `E assert 'run_finished' == 'run_stopped'`. With the S4 `fix_r_e1` probe loaded as a plugin (not applied to source): "FIX R-E1 ACTIVE", `109 passed in 0.73s`. The UsageAccountingError assertion is kept as it was. |
| R-19 | `5753478b`, `447c5896` (comment wrap) | epi → `test_episode_and_recheck_models_reach_their_own_agents`; `ModelCall.model` records each calling agent's `runner_config.model_name` | Branch: `1 passed`. A mutant that pins every worker and recheck `BaseAgent` to `model_name` ("MUTANT ACTIVE: model overrides ignored") fails on `assert ['gpt-5.4-min...gpt-5.4-mini'] == ['gpt-5.4-nan...gpt-5.4-nano']`. The overrides are `gpt-5.4-nano` and `gpt-5.4`: both are priced and pass the pair check (`gpt-4.1` passes the pair check but has no price). The fixture field is named `recorded_model`, not `model_name`, because `BaseAgent` reads `model_name` off a runner. |
| R-20 | `169f548c` | obs → `test_attached_tools_carry_no_server_key` | Branch: `1 passed`. It reads every tool's `repr` and `spec()` after `arun` and before `close_mcp_servers()`. Positive controls: the SEARCH, FETCH and ACTION tools are present, and the key is in the SEARCH server's env. A key planted in the tool description fails both this test and the AC-3 test (`2 failed`). A key planted only in the spec metadata fails this test alone (`1 failed, 1 passed`), so the new test is not vacuous. The existing `repr(agent.tools)` clause is unchanged, and no assertion is made on the `McpServerConfig` repr (Q-8/T-3). |

Pack at the docs commit: `1 failed, 108 passed in 1.57s`. The only failure is the R-4 assertion above, which turns green once `runtime.py` settles usage before it emits the terminal event. Focused lint: `S020`, `A001` and `A009` print `SDK-LINT: PASS`. Every full-line comment added to the tests is at most 72 columns wide. `FEATURE.md` gains four failure-mode bullets (`24c6f212`).

`git diff 5db0eaa0..HEAD -- tests/` shows the AC-13 line (`test_browser_agent_recheck.py:112`) plus the additions above. Some lines show as replaced rather than added:
- the fixture signatures and call sites that now pass the model through (each with a defaulted argument);
- the fixture's ARCHITECTURE NOTE and the function inventories, which are extended;
- the R-4 test's docstring and its `build_agent()` call, which now passes `on_event=log`.
