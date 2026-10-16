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
