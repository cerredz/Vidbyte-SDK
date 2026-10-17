# S2 · Test author report — claude-thread-functions

Stage: S2 test author. Date: 2026-10-15. Spec: `docs/spec/claude-thread-functions/spec.md` r3 (approved). Branch `feat/claude-host`, merge base `72a4ade1`. No production code, no stubs, no install, no push, no real `claude`, no real key. `lint/baseline.json`, `request.md`, `pipeline.md`, `code-map.md`, `vendor-facts.md` and every spec section other than the §6.2 Proof column are untouched.

## Commits

| SHA | Message | Content |
|---|---|---|
| `48186352` | test(harnesses): remove the superseded claude_host pack | Briefing §5 (a): `tests/features/claude_host/` (14 tracked files, spec §12.3 row 12) |
| `688c2747` | test(harnesses): add failing tests for claude-thread-functions [AC-1..AC-23] | 10 new test files, 3 extended existing tests, `conftest.py`, `fake_harness.py`, the pack's `FEATURE.md`/`README.md`, `test-plan.md` |
| `0a709aee` | docs(spec): record test proof for claude-thread-functions | §6.2 Proof column, AC-1 … AC-23 |
| (this report) | docs(spec): add the claude-thread-functions S2 test-author report | this file |

## What I read

- Pipeline record: `spec.md` r3, `request.md`, `context/code-map.md`, `context/vendor-facts.md` (nothing else under `docs/`).
- Code at HEAD and the merge base: `vidbyte/harnesses/native/` (`grok/threads.py`, `grok/wire.py`, `hostkit/errors.py`, `hostkit/launcher.py`, `hostkit/skills.py`), `vidbyte/lib/dataclasses/native_threads.py` and `validation.py`, `vidbyte/lib/enums/native_threads.py` and `failure.py`, `vidbyte/lib/constants/native_threads.py`, `vidbyte/lib/errors/base.py`, `vidbyte/lib/process/runner.py`.
- The whole `tests/features/harness_threads/` pack (prior art), `vidbyte/harnesses/README.md` and the `REPO_MAP.md` native section (for AC-23's shape).

## What I produced

- **10 new files, 188 tests**, all in `tests/features/harness_threads/`: `test_harness_threads_claude_surface.py` (32), `_acceptance.py` (4), `_threads.py` (9), `_argv.py` (19), `_credentials.py` (6), `_errors.py` (32), `_process_bounds.py` (6), `_launcher.py` (14), `_arguments.py` (60), `_skills.py` (6). Levels: 1 e2e (the §4 snippet in a child Python), ~150 integration (public functions awaited against the real-child stand-in), ~35 unit/static (records, enums, constants, `NativePrivateFolders`, git/`ast` checks).
- **6 more test cases** from adding `"claude"` to `test_harness_threads_errors.py`'s harness list, and **4 extended pins** (surface exports, signatures, vocabularies, the repaired FailureCode test) plus `NAMED_MODULES` in the static policy.
- **Fixtures**: `conftest.py` (fourth harness in `HARNESSES`/`LABELS`/`COMMAND_FIELDS`/`CONFIG_NAMES`, `private_config`, lazy `ContractNames`/`ThreadFunctions`/`ConfigRecords`, the sandbox removes every `ANTHROPIC_*`/`CLAUDE*` variable); `fake_harness.py` (the `claude` role: 2.1.301's JSON answer shapes, transcripts under `CLAUDE_CONFIG_DIR/projects/…`, the not-found marker, `override`/`drop`/`exit_code` knobs; `CREDENTIAL_NAMES` + `ANTHROPIC_API_KEY`).
- `test-plan.md`: coverage map (every AC and the INV/EC rows they pin), 10 tests deliberately not written, every existing-test change with before/after, the red run, implementer notes.
- Spec §6.2 Proof column filled for AC-1 … AC-23 (AC-21 names the gate and the guard, as it is not a pytest test).

## Changes to existing tests (all within briefing §5; details with before/after in `test-plan.md`)

1. §5 (a): deleted `tests/features/claude_host/`.
2. §5 (b): `test_harness_threads_surface.py` — `FUNCTIONS` over four harnesses, `EXPECTED_EXPORTS` + 3 names, `NativeHarness` + `claude`, `NativeEnvironmentVariable` + 4 names; the exports test renamed nine → twelve and its subpackage loop runs over four harnesses. `test_harness_threads_errors.py` — `HARNESSES` + `claude`. `test_harness_threads_static_policy.py` — `NAMED_MODULES` + 4 modules. Nothing about Grok, opencode or Muse was removed or loosened.
3. §5 (c): `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` repaired and renamed `test_failure_codes_keep_main_and_append_exactly_the_nine_claude_codes`: the merge base holds 148 members ending in the 28 harness codes, the branch keeps all 148 unchanged and appends exactly the nine `claude.*` after `MUSE_WSL_UNAVAILABLE`, in §8.5 order, 157 in total.

## Red run

Command and final lines (whole pack, implementation absent):

```
$ PYTHONPATH=$(pwd) timeout 1200 python -m pytest -q -p no:cacheprovider tests/features/harness_threads < /dev/null | tail -n 15
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_thread_functions_are_coroutines_with_the_contract_signature
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_vocabularies_are_str_enums_carrying_the_vendor_values
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_nine_claude_codes
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them
203 failed, 427 passed, 2 skipped in 84.46s (0:01:24)
```

Baseline before this stage: `5 failed, 431 passed, 2 skipped in 46.53s`. 203 = 188 new + 6 `[claude]` cases + 4 extended pins + 5 pre-existing. Every failure was grouped by message from a JUnit report: all new ones fail on the missing feature (`no attribute 'run_claude_thread'`, `'ClaudeThreadConfig'`, `'ClaudePermissionMode'`, `NativeHarness.CLAUDE`, `hostkit.NativePrivateFolders`, missing constants, #1044 files still present); no failure comes from a fixture, the stand-in or collection. The 427 passing tests are the pre-existing ones (guards, green before and after).

Pre-existing failures: at the merge base itself only the FailureCode test (`len(main_members) == 120` vs 148; repaired). At this branch's starting head `b28fc072`, also `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` and the three static-policy tests, all caused by #1044 code that §12.3 rows 8 and 10 delete.

Other checks: `python lint/run.py --format json` exits 0 with no finding in `tests/features/harness_threads/` (A001 headers fine); `ruff check --config lint/ruff.toml tests/features/harness_threads` → `All checks passed!`. Each new file was also run alone (1–2 s each).

## Decisions and findings

- **Lazy contract lookups.** `api` used to resolve every thread function eagerly, so one missing Claude name would have errored all 438 existing tests. `ThreadFunctions`/`ConfigRecords`/`ContractNames` resolve on first use, so only Claude tests are red. This changes fixture mechanics, not any assertion.
- **The sandbox now drops `ANTHROPIC_*`/`CLAUDE*`.** The agent shell carries a real `ANTHROPIC_API_KEY`, `CLAUDECODE` and `CLAUDE_CONFIG_DIR`; without this, the AC-6 child-environment test could pass or fail on the shell, and the AC-1 snippet would inherit the real key.
- **Python 3.11.0 crash, avoided.** A task left with an unretrieved exception (a held call that failed at once) is finalised by the garbage collector; its logged traceback calls `ast.parse` while pytest is inside `ast.parse` for a report, and 3.11.0 raises `SystemError: AST constructor recursion depth mismatch` as an INTERNALERROR that aborts the session. The two task-based Claude tests now wait for "started or finished" and await an early-finished call. Same pattern exists in Grok's tests but never fires there (their calls succeed).
- **Continue reports the caller's id** (INV-6, §12.3 row 20 step 3) even on a wrong-thread answer, unlike Grok's wire. Tests pin the spec.
- **Pre-existing timing flake** seen once in three complete runs: `test_harness_threads_launcher.py::test_tree_stop_never_runs_a_taskkill_from_the_current_folder[cancel]` (Grok; 1.5 s tree-death wait under load); passed in the other runs and three isolated runs. Not caused here, but it could trip AC-21's "every Grok test passes" on a loaded machine.
- **Spec defects:** none blocking. One wording gap: AC-21's guard ("every Grok, opencode and Muse test passes") does not say what to do with the timing flake above.

## Most likely to catch a real bug

`test_harness_threads_claude_threads.py::test_continue_answered_on_another_valid_id_is_thread_not_found` (with `test_harness_threads_claude_errors.py::test_failed_continue_reports_the_callers_id`). The spec tells the implementer to copy `GrokThreads._call` and `grok/wire.py`, and Grok's wire passes the answered session as the error's `thread_id`; a straight copy fails these two.

## Notes for the next agent (S3)

- Run: `PYTHONPATH=$(pwd) timeout 1200 python -m pytest -q -p no:cacheprovider tests/features/harness_threads < /dev/null | tail -n 15` from the worktree root; one file: replace the folder with the file path.
- Names imported (exactly §8.5): `run_/continue_/fork_claude_thread`, `ClaudeThreadConfig`, `ClaudePermissionMode`, `ClaudeReasoningEffort` from `vidbyte.harnesses.native`; `ClaudeFlag` from `vidbyte.lib.enums`; `NativePrivateFolders` from `vidbyte.harnesses.native.hostkit` (module `hostkit/folders.py`, `__all__ == ["NativePrivateFolders"]`, hostkit `__all__` sorted with it); every `CLAUDE_*` constant and `NATIVE_STDIN_PROMPT_HARNESSES` from `vidbyte.lib.constants.native_threads`.
- `NativePrivateFolders.prepare(request, errors, *, parts, key_hex_chars, skills_dir, unknown_detail, failure_detail)` is spied with exactly those keywords for Grok and Claude, called through the class attribute.
- Validate every argument before `NativeLauncher.resolve` and `NativePrivateFolders.prepare`: refusal tests assert no `~/.vidbyte` folder appears.
- Do not change the sandbox's PATH/home redirection or its removal of `ANTHROPIC_*`/`CLAUDE*`; do not edit tests to make them pass.
- `test_branch_changes_only_the_files_the_spec_lists` diffs the working tree against the merge base: any changed path outside §12.3's list, `docs/spec/claude-thread-functions/` and `tests/` fails it, and `pyproject.toml`, `vidbyte/tools`, `vidbyte/lib/errors/__init__.py`, `lint/baseline.json` must equal the merge base.

## Addendum: S3 fix (2026-10-15)

After S3 landed (HEAD `27d5cd1b`, which includes a merge of origin/main), the orchestrator found that `test_harness_threads_claude_surface.py::test_request_applies_the_claude_rules_only_to_claude` contradicted the spec. Its Grok/opencode/Muse loop built an opencode `NativeThreadRequest` without a model, but opencode has always required one (spec §9.1, INV-20; `test_harness_threads_arguments.py` `MODEL_CASES`), so the test raised `ConfigurationError: model must be non-empty text …; got None.` The red run hid this, because the test failed earlier on the missing `NativeHarness.CLAUDE`. Commit `140cc2fa` passes `model=pack.OPENCODE_MODEL` (`"deepseek/deepseek-v4-pro"`) for opencode only and changes no assertion; only that test file was touched, and nothing under `vidbyte/` was read. The test passes alone (`1 passed in 0.96s`). The first full-pack run after the fix ended `2 failed, 628 passed, 2 skipped in 188.50s`: existing timing-bound tests `test_harness_threads_process_bounds.py::test_cancellation_propagates_after_the_tree_is_stopped[opencode]` and `test_harness_threads_wsl.py::test_wsl_run_past_its_timeout_is_reaped_with_the_calls_mark` missed their tree-death waits on a loaded machine (the run took more than twice the usual time). Run alone three times, the pair failed once and passed twice. The second full run was clean:

```
$ PYTHONPATH=$(pwd) timeout 1200 python -m pytest -q -p no:cacheprovider tests/features/harness_threads < /dev/null | tail -n 5
........................................................................ [ 68%]
.............................................s.......................... [ 79%]
........................................................................ [ 91%]
.......s................................................                 [100%]
630 passed, 2 skipped in 136.12s (0:02:16)
```

Lesson for this stage: a test that is red only because an earlier line fails cannot show its later lines are right. Lines that build records for the other harnesses should be run against the merge base, where those harnesses exist, before the red run is recorded.

## S5 test changes (after S4)

Brief: the coordinator's S5 message, bounded to the regression tests spec r4 (`cabf0f80`) requires for S4 findings R-1 to R-4 (`review.md`). I read `git show cabf0f80`, `review.md` and the test pack, and nothing under `vidbyte/`, `REPO_MAP.md` or `vidbyte/harnesses/README.md`. No real `claude` and no real key were used; every stand-in ran with the sandbox's HOME and USERPROFILE.

What changed (test commit `test(harnesses): regression tests for S4 findings [R-1 R-2 R-3 R-4]`):
- **R-2** (INV-5 rule 5, AC-8, EC-38): `PROMPT_CASES` in `test_harness_threads_claude_arguments.py` gained `("lone-surrogate", "list \ud800 files")`. It runs through the same `refuse` fixture, so the refusal must be `configuration.invalid_argument` naming `prompt`, with nothing started and no `~/.vidbyte` folder. There is no such case for Grok, opencode or Muse (EC-38, INV-20).
- **R-3** (INV-6, INV-7 item 4, EC-14): `fake_harness.py` gained the `answer_then_hold` mode, which prints a valid success answer, logs `printed`, then holds. The new `test_answer_printed_before_the_timeout_gives_the_newest_thread_id[run|continue|fork]` expects `claude.timed_out` with the printed `session_id` (run, fork) or the caller's id (continue), the seconds waited, and stderr as the vendor text. It uses `PRINTED_TIMEOUT = 3.0` so a slow stand-in still prints first; a stand-in stopped before printing fails on its own assertion. The existing nothing-printed tests already assert `thread_id=None` (run) and the caller's id (continue, fork), as r4 says, and are unchanged.
- **R-1** (INV-6, INV-7 item 5, EC-15): the new `test_stdout_past_the_cap_carries_claudes_stderr_as_the_vendor_text` sits beside the unchanged cap test. It combines `flood` with `stderr_text` and checks `vendor=`.
- **R-4** (AC-23 as rewritten in r4): `test_harnesses_readme_and_repo_map_describe_the_claude_functions` now requires the six tokens in the README, and requires `Claude Code` with none of the three function names, `claude-configs`, `--setting-sources` or `CLAUDE.md` in the REPO_MAP `native/` section. This is the only changed assertion; its before and after are in test-plan.md "Changes to existing tests" item 7.
- The headers of the three test files and the stand-in name the new cases.

Red, at the unchanged code (HEAD `cabf0f80`):

```
$ PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/ -k claude < /dev/null
FAILED tests/features/harness_threads/test_harness_threads_claude_process_bounds.py::test_answer_printed_before_the_timeout_gives_the_newest_thread_id[run]
FAILED tests/features/harness_threads/test_harness_threads_claude_process_bounds.py::test_answer_printed_before_the_timeout_gives_the_newest_thread_id[fork]
5 failed, 195 passed, 437 deselected, 1 warning in 37.90s
$ PYTHONPATH=$(pwd) timeout 1200 python -m pytest -q -p no:cacheprovider tests/features/harness_threads/ < /dev/null
5 failed, 630 passed, 2 skipped, 1 warning in 67.25s (0:01:07)
```

Each failure names its finding: the REPO_MAP section holds all six forbidden tokens (R-4); the surrogate prompt gives `runtime.error` from `UnicodeEncodeError` instead of `configuration.invalid_argument` (R-2); `vendor_message` is None on `output_too_large` (R-1); and `thread_id` is None on the run and the source id on the fork (R-3). `[continue]` passes now and must keep passing (a guard), because the caller's id is already the fallback. Every earlier Claude test still passes, apart from the changed AC-23 check. The one warning comes from the garbage collector closing the child that the surrogate call leaked (R-2's own symptom).

For the repair agent:
- Apply R-1 and R-3 as one patch (`review.md` Fix notes). The three new process-bounds tests need the answer read before the timeout and output-cap checks, with `thread_id=newest` and `vendor_text=outcome.stderr` on both.
- The R-4 test now *forbids* the tokens in REPO_MAP. Reword the REPO_MAP Claude sentences in plain words, keep `Claude Code`, and keep the exact names in the README.
- Do not route R-2 through `NATIVE_STDIN_PROMPT_HARNESSES`: opencode must keep its behaviour (INV-20).

Open: there is no guard that emoji and accented prompts still run after the new pattern (r4 INV-5 rule 5 says they must). It was outside this brief and is a recommended small follow-up.
