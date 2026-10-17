# S3 implementer report — claude-thread-functions

Status: DONE. Every §12.3 row is implemented; the branch is pushed (`feat/claude-host`), PR #1044 is retitled, CI and Static policy are dispatched, the spec is `status: implemented` and §17 records the S3 row and deviations.

History: the first pass stopped BLOCKED at the push because one S2 test contradicted the spec (see "Blocking finding"). The test author fixed it in `140cc2fa` (`model=pack.OPENCODE_MODEL` on the opencode request, no assertion changed), with docs `3839c7bc` and the orchestrator's `adbffcfe`; S3 then re-ran the gates, caught up with main twice and finished Phases 6 and 7 (see "Round 2").

## Phase 2 — catch-up merge and drift check

- `git fetch origin`; origin/main = `0105b5b7` (#1104 on top of #1103 and #1095 `0754e01f`).
- `git merge origin/main` → merge commit `752fd795`, no conflicts (git's default message). Merge base is now `0105b5b7`.
- Pack after the merge: `203 failed, 427 passed, 2 skipped in 79.56s` (same as S2's red figure).
- Drift check `git diff --stat 72a4ade1..origin/main -- <spec §11/§12.3 paths>`: only `vidbyte/lib/enums/__init__.py` (+`SystemPromptPreset`, additive) and `vidbyte/lib/enums/prompts.py` (not touched by this spec). No structural drift.

## Blocking finding (round 1; resolved by S2 in 140cc2fa)

`tests/features/harness_threads/test_harness_threads_claude_surface.py::test_request_applies_the_claude_rules_only_to_claude` (line 219–220) builds

```python
lib_api.NativeThreadRequest(harness=enums.NativeHarness.OPENCODE, verb=enums.NativeThreadVerb.CONTINUE, thread_id="fix-login", **fields)
```

with `fields = {"prompt", "api_key", "workspace"}` and no `model`. opencode requires a `provider/model` (`NativeThreadRequest._checked_model`, unchanged since the merge base), so the record raises `ConfigurationError: model must be non-empty text of at most 160 characters; got None.` before the thread-id rule the test means to check. The test contradicts:

- spec §9.1 / INV-20: "Grok, opencode and Muse keep exactly their current rules";
- the existing pin `tests/features/harness_threads/test_harness_threads_arguments.py` MODEL_CASES, where opencode with model `None` must be refused.

Satisfying the test needs either a test change (forbidden without approval) or relaxing opencode's model rule (forbidden by INV-20). Evidence that the rest of the test passes with a one-line fix: the scratch replay `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/c726d777-284c-4c17-9776-72f9da8a13f9/scratchpad/check_option_a.py` (the test body with `model="deepseek/deepseek-v4-pro"` added for opencode only) prints `option A replay: PASS`.

Proposed fix (option A, needs the orchestrator's approval because it edits a test): in that loop pass `**({"model": "deepseek/deepseek-v4-pro"} if harness is enums.NativeHarness.OPENCODE else {})`.

## Commits (after the catch-up merge, oldest first)

```
fdd21650 revert(enums): restore the enums export file to the merge base [W-7 row 2; FR-14, INV-19]
f80c69f6 revert(errors): restore the errors exports to the merge base, dropping ClaudeOperationError [W-7 row 4; FR-14, AC-20]
76ba12e7 revert(errors): restore errors/base.py to the merge base, dropping ClaudeOperationError [W-7 row 5; FR-14]
38dcda9a revert(tools): restore the builtins registry to the merge base [W-7 row 6; FR-14, INV-22, AC-20]
7335ea53 revert(tools): restore the toolsets registry to the merge base [W-7 row 7; FR-14, INV-22, AC-20]
ac7f9c8d refactor(harnesses): delete the ClaudeHost host stack of PR #1044 [W-7 row 8; FR-14, INV-19]
c90c10ee refactor(tools): delete the Claude agent tools and toolset [W-7 row 10; FR-14, INV-22, AC-20]
24d6beca refactor(lib): delete the ClaudeHost constants, enums and records [W-7 row 9; FR-14, INV-19]
f15669e1 revert(enums): restore FailureCode to the merge base, dropping the 16 ClaudeHost codes [W-7 row 3; FR-14, INV-21]
8cd5db96 revert(build): drop the claude-agent-sdk optional extra [W-7 row 1; FR-14, NFR-2, AC-20]
29ec0755 docs(spec): delete the superseded claude-host design record [W-7 row 11; FR-14, AC-20]
270bf5ed feat(enums): add the Claude Code harness, operations, modes, efforts, flags and variables [W-6 row 13; ...]
a09cf10b feat(enums): export ClaudeFlag, ClaudePermissionMode and ClaudeReasoningEffort [W-6 row 14; ...]
54091965 feat(enums): append the nine claude.* failure codes after the Muse codes [W-5 row 15; ...]
b8f0a8f5 feat(constants): add the Claude Code constants, labels, versions, failure codes and texts [W-5, W-6 row 16; ...]
8ebd6f59 feat(records): add ClaudeThreadConfig and the Claude Code id and stdin prompt rules [W-4 row 17; ...]
ab9ebcfa feat(hostkit): add NativePrivateFolders, the shared private per-workspace folder helper [W-2, W-3 row 32; ...]
35801d3a feat(hostkit): export NativePrivateFolders from the hostkit package [W-2 row 22; ...]
ec529290 refactor(grok): prepare the private Grok home through NativePrivateFolders [W-2 row 34; FR-15, INV-20]
fa41955b feat(claude): add ClaudeWire, the reader of one claude --print JSON answer [W-5 row 20; ...]
477a6a56 feat(claude): add the Claude Code thread functions and the flow of one call [W-1, W-2, W-3 row 19; ...]
82d96245 feat(claude): bind run_claude_thread, continue_claude_thread and fork_claude_thread [W-1 row 18; ...]
b7a43c06 feat(harnesses): re-export the Claude Code functions, config and enums from vidbyte.harnesses.native [W-1 row 21; ...]
7945385f docs(hostkit): name Claude Code in the NativeErrorFactory header and wrong_thread comment [W-8 row 23; FR-15]
1041fb0d docs(hostkit): name ClaudeThreadRun among the NativeLauncher callers [W-8 row 24; FR-15]
62133292 docs(hostkit): describe NativeSkillFolders callers through NativePrivateFolders [W-8 row 25; FR-15]
2c379ad7 docs(process): name the claude runs among the CliRunner callers [W-8 row 26; FR-15]
c75b3f01 docs(process): name Claude Code among the separate-style CliArgv callers [W-8 row 27; FR-15]
555e56ac docs(errors): name Claude Code in the NativeThreadError line of the errors docstring [W-8 row 28; FR-15]
52ae9f0d docs(records): name ClaudeWire among the accepts_text callers [W-8 row 33; FR-15]
5bfa8f74 docs(harnesses): describe the Claude Code thread functions in the native/ README entry [W-8 row 29; FR-15, AC-23]
6db7517c docs(map): name the Claude Code thread functions in the vidbyte/harnesses/native/ section [W-8 row 30; FR-15, AC-23]
```

Every commit ends with the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer.

After those: `27d5cd1b` (this report, round 1); S2's `140cc2fa` and `3839c7bc` and the orchestrator's `adbffcfe`; merges `5454d057` (origin/main `8cfe3e93`) and `cf9c541d` (origin/main `b28c3027`); `1443f2e4 docs(spec): record implementation for claude-thread-functions`; then `docs(spec): record implementation proof for claude-thread-functions` (§17 row, deviations, this report).

## What was built, in data-flow order

1. `vidbyte/lib/enums/native_threads.py`: `NativeHarness.CLAUDE`, three `NativeThreadOperation` members, `ClaudePermissionMode` (no approve-everything member), `ClaudeReasoningEffort`, `ClaudeFlag`, four `NativeEnvironmentVariable` members; exported from `vidbyte/lib/enums/__init__.py`.
2. `vidbyte/lib/enums/failure.py`: the nine `claude.*` codes appended after `MUSE_WSL_UNAVAILABLE` in `NativeThreadProblem` order.
3. `vidbyte/lib/constants/native_threads.py`: every §8.5 constant, the label and tested-version rows, the nine failure-code rows and one likely cause and next step per code, written from the row 16 content list.
4. `vidbyte/lib/dataclasses/native_threads.py`: `ClaudeThreadConfig`; the prompt cap and Windows unit check keyed on `NATIVE_STDIN_PROMPT_HARNESSES`; Claude thread ids checked against `CLAUDE_THREAD_ID_PATTERN`.
5. `vidbyte/harnesses/native/hostkit/folders.py`: `NativePrivateFolders.prepare`, Grok's `_prepare_home` with every constant as a keyword parameter; exported from `hostkit/__init__.py`. Grok now calls it with its own constants (`_prepare_home` and the four imports only it used are gone).
6. `vidbyte/harnesses/native/claude/wire.py`: `ClaudeWire.read` in INV-7 order, seven `if`s (ruff C901 complexity 8), helpers `_answer`, `_session`, `_text`, `_missing_member`, `_error_text`.
7. `vidbyte/harnesses/native/claude/threads.py`: `ClaudeThreads` (three functions plus `_call`) and `ClaudeThreadRun` (`execute`, `_fallback`, `_environment`, `_inherited_names`, `_argv`).
8. `vidbyte/harnesses/native/claude/__init__.py` and `vidbyte/harnesses/native/__init__.py`: the three functions and the six new public names (23 in `__all__`, sorted).
9. Headers of `hostkit/errors.py`, `launcher.py`, `skills.py`, `lib/process/runner.py`, `argv.py`, `lib/dataclasses/validation.py`; one docstring line of `lib/errors/base.py`; the `native/` entry of `vidbyte/harnesses/README.md` (now 13,772 characters) and the `vidbyte/harnesses/native/` section of `REPO_MAP.md`.

## §12.3 rows

| Row | Done | Commit |
|---|---|---|
| 1–11 | yes (P1) | 8cd5db96, fdd21650, f15669e1, f80c69f6, 76ba12e7, 38dcda9a, 7335ea53, ac7f9c8d, 24d6beca, c90c10ee, 29ec0755 |
| 12 | S2's row, not touched | — |
| 13–17 | yes (P2) | 270bf5ed, a09cf10b, 54091965, b8f0a8f5, 8ebd6f59 |
| 32, 22, 34, 20, 19, 18, 21 | yes (P3, in that order) | ab9ebcfa, 35801d3a, ec529290, fa41955b, 477a6a56, 82d96245, b7a43c06 |
| 23–30, 33 | yes (P4) | 7945385f, 1041fb0d, 62133292, 2c379ad7, c75b3f01, 555e56ac, 5bfa8f74, 6db7517c, 52ae9f0d |
| 31 | S2's row, not touched | — |

Grok tests were run right after row 34: every Grok case in the pack passed; the only Grok-named failures at that point needed the Claude functions (`test_grok_and_claude_prepare_their_folders_through_the_one_helper`, `test_config_that_is_not_a_claude_thread_config_is_refused[GrokThreadConfig]`) and pass now.

## Deviations

1. `ClaudeWire.read`, step 6 (combined member check): the error's `thread_id` is the "newest" id (the caller's id on continue, else `session`) instead of the literal `thread_id=session`. For run and fork the two are identical (`session`, or `None` falling back to the caller's id). For continue it follows INV-6 ("a failed continue reports the caller's id") and the test-plan note; the literal form would report Claude's answered id when only `is_error` or `result` is bad. The same "newest" value is used for the is_error, non-zero-exit, no-JSON and wrong-thread errors.
2. `ClaudeWire._missing_member(answer, session, text)` keeps the §8.5 signature; its body returns exactly what row 20 says (is_error, else session_id when `session` is None, else result), so `text` is accepted but not read. No lint rule flags it (ruff ARG is not selected).
3. `OUTPUT_TOO_LARGE` is raised without `vendor_text` (row 20 lists only `cap_bytes`); Grok passes stderr there. Tests do not check it either way.
4. The `vidbyte/harnesses/README.md` hostkit sentence now also lists "private per-workspace folders", and the REPO_MAP section says "Plumbing the harnesses share" instead of "the three", because both became wrong with this change.

## Budget (§8.4)

- New files: 4 (`claude/__init__.py`, `claude/threads.py`, `claude/wire.py`, `hostkit/folders.py`) — at budget.
- New classes: 8 (`ClaudeThreads`, `ClaudeThreadRun`, `ClaudeWire`, `NativePrivateFolders`, `ClaudeThreadConfig`, `ClaudeFlag`, `ClaudePermissionMode`, `ClaudeReasoningEffort`) — at budget.
- `claude/*.py`: 360 lines in total (NFR-3 ≤ 400). New dependencies 0; new config keys 0.

## Gates

Pack per phase (`PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads`):

- after P1: `198 failed, 432 passed, 2 skipped in 100.25s`
- after P2: `170 failed, 460 passed, 2 skipped in 66.83s (0:01:06)`
- after row 34: `167 failed, 463 passed, 2 skipped in 78.48s (0:01:18)` (no Grok case among the non-Claude failures)
- after P3: `3 failed, 627 passed, 2 skipped in 94.13s (0:01:34)` (README/REPO_MAP and the errors docstring, both P4, plus the blocking test)
- after P4: final lines

```
=========================== short test summary info ===========================
FAILED tests/features/harness_threads/test_harness_threads_claude_surface.py::test_request_applies_the_claude_rules_only_to_claude
1 failed, 629 passed, 2 skipped in 85.27s (0:01:25)
```

Lint (`python lint/run.py`, PYTHONPATH unset), final lines:

```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

Zero-headroom ratchets all at baseline: S008 19/19, S009 350/350, A007 255/255, S015 13/13, S051 259/259, S017 79/79, S019 5/5, A006 34/34, C006 104/104, C008 45/45; A001 640/642. A002 579/703 (IMPROVED; was 575 before P3, the four new findings are the Claude copies of Grok's `_call`, `execute` and `read` pattern). The same nine rules report IMPROVED as before (A001, A002, C011, C012, S001, S010, S025, S061, S063); `lint/baseline.json` untouched. `ClaudeWire.read` is ruff C901 complexity 8.

Semgrep (`semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, semgrep 1.170.1 venv):

```
Ran 1 rule on 966 files: 0 findings.
```

Full gate, source stage (`PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`): lint `SDK-LINT: PASS`, compileall, the three context/trace checks `ok`, then pytest:

```
FAILED tests/features/harness_threads/test_harness_threads_claude_surface.py::test_request_applies_the_claude_rules_only_to_claude
FAILED tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport
=========== 2 failed, 6028 passed, 16 skipped in 215.03s (0:03:35) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-claude-thread-functions).
```

The MCP test is the known flake; rerun alone: `1 passed in 0.90s`. The other is the blocking finding above.

Full gate, package stage (`python scripts/run_ci.py --stage package`, PYTHONPATH unset):

```
No broken requirements found.
Installed vidbyte-sdk 0.3.0 passed smoke checks.
CI passed.
```

Scope checks against the merge base `0105b5b7`: `pyproject.toml`, `vidbyte/tools`, `vidbyte/lib/errors/__init__.py` and `lint/baseline.json` are byte-identical; the files changed outside `docs/spec/claude-thread-functions/` and `tests/` are exactly the §12.3 files. No commit of this stage touches `tests/` (`git log --no-merges 25211e79..HEAD --not origin/main -- tests` is empty); every test file that differs from `25211e79` is identical to `origin/main` (brought in by the catch-up merge).

The gate lines above are round 1 (before the S2 fix). Round 2 follows.

## Round 2 — after the S2 test fix

1. Pack on `adbffcfe`: `1 failed, 629 passed, 2 skipped in 160.49s` — the one failure was the known load-sensitive `test_harness_threads_launcher.py::test_tree_stop_never_runs_a_taskkill_from_the_current_folder[cancel]`; rerun alone: `2 passed in 3.95s`.
2. `git fetch`: origin/main had moved to `8cfe3e93` (#1105–#1108, algorithm and runtime files only, no overlap with this spec). Merged → `5454d057`, no conflicts, no `tests/` conflict. Pack after the merge:

```
.......s................................................                 [100%]
630 passed, 2 skipped in 212.80s (0:03:32)
```

3. Source stage on `5454d057` (machine at 60–100% CPU from other sessions' pytest, lint and multiprocessing jobs): lint `SDK-LINT: PASS`, compileall and the three context/trace checks `ok`, then

```
FAILED tests/features/harness_threads/test_harness_threads_process_bounds.py::test_run_past_its_timeout_is_timed_out_with_its_tree_stopped[grok-hold-False]
FAILED tests/features/harness_threads/test_harness_threads_wsl.py::test_wsl_run_past_its_timeout_is_reaped_with_the_calls_mark
FAILED tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport
====== 3 failed, 6041 passed, 16 skipped, 1 warning in 365.32s (0:06:05) ======
```

   All three are timing tests over code this branch does not change in behaviour. Evidence, A/B against a `git archive origin/main` export run under the same load:
   - process-bounds tree stop: at 100% load, branch `2 failed, 3 passed` and main `2 failed, 3 passed` (both `muse-hold-False` among them); once load fell below 40%, branch `5 passed` (together with the MCP test: `1 failed, 5 passed in 16.55s`, the failure being the MCP test).
   - WSL reap: branch reruns `1 passed in 3.22s`, `1 passed in 4.37s`; main `1 passed in 3.89s`.
   - MCP cancelled waiter (`vidbyte/tools` and its test are byte-identical to origin/main): five interleaved runs, branch 2 failed / 3 passed, main 2 failed / 3 passed (`try 1 branch: 1 failed in 6.02s | main: 1 failed in 6.19s` … `try 5 branch: 1 passed in 0.81s | main: 1 failed in 6.39s`).
4. Package stage on `5454d057` (PYTHONPATH unset):

```
Installed vidbyte-sdk 0.3.0 passed smoke checks.
CI passed.
```

5. Pushed `5454d057`; `gh pr edit 1044` retitled it. `gh pr view 1044` then said `"mergeStateStatus":"BEHIND"`: main had moved again to `b28c3027` (#1109, #1110; algorithm files and two new tests, no overlap). Merged → `cf9c541d`, no conflicts. Pack plus main's two new test files:

```
......................                                                   [100%]
668 passed, 2 skipped in 81.24s (0:01:21)
```

6. Pushed `cf9c541d`. PR: `{"baseRefName":"main","isDraft":false,"mergeable":"MERGEABLE","title":"[WIP] feat(harnesses): run, continue and fork Claude Code threads with the caller's API key","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1044"}` (state read before the second merge said BEHIND). Dispatched on `cf9c541d`:
   - CI: run `38839502990` (https://github.com/cerredz/Vidbyte-SDK/actions/runs/38839502990)
   - Static policy: run `38839504682` (https://github.com/cerredz/Vidbyte-SDK/actions/runs/38839504682)
7. `1443f2e4 docs(spec): record implementation for claude-thread-functions` (status `implemented`), pushed. Then the §17 r3 S3 row and the "Implementation deviations (S3)" list (no §6.2 Proof cell was blank; AC-21 already names its gate commands), committed and pushed with this report.

Test-tree check: `git log --no-merges --oneline 3839c7bc..HEAD --not origin/main -- tests` prints nothing, and `git show --cc` of both merge commits prints nothing for `tests/`.

## Tricky parts

- S008 and S009 have zero headroom. `ClaudeWire.read` keeps the two problem choices as conditional expressions and the exit-0 member checks as one `if ... or ... or ...`, so mypy narrows `session` and `text` to `str` after it without a `cast`.
- `api_error_status` can be a list or a dict; `isinstance(status, int)` must come before `status in CLAUDE_KEY_REJECTED_STATUSES`, or the frozenset lookup raises `TypeError` on an unhashable value. `True` is an int, so it is shown in the vendor text and is never a key rejection.
- A pycache-only `vidbyte/tools/builtins/claude/` folder left by #1044 made `find_spec("vidbyte.tools.builtins.claude")` succeed as a namespace package; it was removed (ignored files, not tracked).
- Comments in `vidbyte/harnesses/native/**` must stay ≤ 72 columns and the modules may hold no literals besides docstrings, `__all__` strings, `""`, `0` and `1`.
