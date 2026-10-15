# S2 test author report: harness-thread-functions

Spec: `docs/spec/harness-thread-functions/spec.md` r3. Branch `feat/native-grok-opencode-meta-hosts`, merge-base with `origin/main` `179d8adc`. Commits: `2a712138` (tests + test plan), `634b1954` (spec §6.2 Proof column). This report is not committed (the stage's two commits were fixed by the brief).

## Inventory

New pack `tests/features/harness_threads/` (19 files, 393 tests):

| File | Tests | Covers |
|---|---|---|
| `conftest.py` | — | lazy `lib_api`/`api` fixtures, `Sandbox`, `sandbox`, `call`, `check_error`, `fast_stop`, `wait_until`, `alive`, `wsl_ready`, `pack` |
| `fake_harness.py` | — | stdlib stand-in for grok, opencode, muse exec, muse batch serve, wsl.exe (list, run, reap, failures) |
| `test_harness_threads_surface.py` | 9 | INV-1, §8.5 signatures, StrEnums, INV-22, contract constants, AC-13, INV-19, INV-21, INV-23 |
| `test_harness_threads_acceptance.py` | 7 | AC-1 (verbatim §4 snippet), AC-2, D-21, AC-17 |
| `test_harness_threads_threads.py` | 18 | AC-6, AC-7, AC-8, EC-19–EC-22, EC-40, INV-11 |
| `test_harness_threads_credentials.py` | 16 | AC-3, AC-4, INV-2, INV-10, INV-17, INV-18, AC-19 |
| `test_harness_threads_records.py` | 35 | §9.1 config/request/result/`CliOption` records, D-26 |
| `test_harness_threads_arguments.py` | 185 | AC-5/INV-4 (EC-1–EC-3, EC-5, EC-6, EC-33, D-25) plus boundary positives |
| `test_harness_threads_argv.py` | 24 | `CliArgv` (D-12, INV-7, INV-16), exact §9.2 argv, AC-14 flags, AC-15 |
| `test_harness_threads_errors.py` | 28 | AC-10/INV-6 conditions, EC-9, EC-13, EC-18, EC-23, EC-32, D-10 packet |
| `test_harness_threads_process_bounds.py` | 17 | AC-9, AC-11, AC-21, EC-15–EC-17, EC-31, serve control timeout |
| `test_harness_threads_launcher.py` | 28 | D-16, EC-11, AC-12/INV-14, EC-12, EC-14, EC-29 |
| `test_harness_threads_skills.py` | 4 | AC-16/INV-12, EC-27 (single-call rules), T-5 |
| `test_harness_threads_runner.py` | 10 | `CliRunner`/`CliInvocation` with `env_overlay` (D-13, rows 27, 30), INV-8/9/10 at the runner |
| `test_harness_threads_wsl.py` | 9 | Muse WSL mode: §9.2 prefix/paths/WSLENV, reap on timeout and cancel, EC-29, EC-30 |
| `test_harness_threads_static_policy.py` | 3 | INV-15 rules 1 and 2 (AC-14), INV-20 |
| `FEATURE.md`, `README.md` | — | pack contract, suite map, file index |

Deleted: the 49 tracked files of `tests/features/{grok_host,opencode_host,muse_host,native_backends}/` (`git rm`; none exists on `origin/main`). No test file on `origin/main` was touched.

## Pruned and why

Full list with reasons is in `test-plan.md` "Tests deliberately NOT written". Main cuts: AC-18 and AC-20 (gate and review replies, not code); NFR-1/NFR-2 (wall-clock budget, line counts); EC-2 UNC workspace (no non-admin UNC path); accepted-limitation and vendor-behaviour edge cases (EC-25, 26, 28, 35–37, 39, 41–44); EC-27 concurrency and EC-34 locked temp folder (timing-dependent, no observable success); a Muse fork-returns-source rule (the spec gives no code); the tested-version constants (not in §8.5's contract list); the `vidbyte.lib` half of INV-20 (lint A006 already enforces it); the carried-over `ProcessStopper` unit tests (they pass on the current code, so they cannot be red under rule 6; the tree stop is covered through timeouts and cancellation).

## Exact red output

Per file:
```
test_harness_threads_acceptance.py: 1 failed, 6 errors in 1.99s
test_harness_threads_arguments.py: 185 errors in 4.51s
test_harness_threads_argv.py: 24 errors in 1.37s
test_harness_threads_credentials.py: 16 errors in 1.24s
test_harness_threads_errors.py: 28 errors in 1.41s
test_harness_threads_launcher.py: 1 skipped, 27 errors in 1.39s
test_harness_threads_process_bounds.py: 17 errors in 1.18s
test_harness_threads_records.py: 35 errors in 1.47s
test_harness_threads_runner.py: 1 skipped, 9 errors in 1.00s
test_harness_threads_skills.py: 4 errors in 0.91s
test_harness_threads_static_policy.py: 3 failed in 0.32s
test_harness_threads_surface.py: 3 failed, 6 errors in 2.04s
test_harness_threads_threads.py: 18 errors in 1.19s
test_harness_threads_wsl.py: 9 errors in 1.06s
```
Pack: `7 failed, 2 skipped, 384 errors in 10.13s`. Whole suite: `7 failed, 5173 passed, 16 skipped, 384 errors in 62.82s (0:01:02)`; every failure and error is in the new pack, and the rest equals the pre-stage baseline (5173 passed, 14 skipped outside the old packs).

Reasons: 384 × `ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.native_threads'` at fixture setup. Failures: AC-1 `ImportError: cannot import name 'GrokPermissionMode' from 'vidbyte.harnesses.native'`; INV-15 rules 1 and 2 (`§12.3 names these modules … missing: ['grok/threads.py', 'opencode/threads.py', 'muse/threads.py', 'hostkit/launcher.py', 'hostkit/skills.py']`); INV-20 (`hostkit/peers.py line 26: vidbyte.tools.mcp.transport`); AC-13 (32 rejected files present); INV-21 (50 paths differ from main); INV-23 (`import vidbyte` loads `vidbyte.harnesses.native`). The 2 skips are POSIX-only cases on win32. Nothing passes before implementation.

Lint (`python lint/run.py`, pack staged so `git ls-files` sees it): exit 0, zero findings in the pack.

## Checks made on the test tooling itself

Because S3 may not edit tests, the tooling was exercised without the feature:
- A scratch driver ran `fake_harness.py` with the exact §9.2 argv and environment for every role (grok run/continue/fork/unknown/no key; opencode run/continue/fork/unknown session/unbound key/stdin; muse exec, serve read known/unknown (-32020)/fork, exec on the forked id, `--name=value` refusal; `.exe` stand-ins; wsl.exe list (UTF-16-LE), run, reap, unknown distro, missing muse path): 25/25 checks passed.
- The runner tests ran against the branch's current `CliRunner` through a scratch adapter (`env_overlay` mapped to `env={**os.environ, **overlay}`): 8 passed, 1 skipped (POSIX), the record test deselected (field names differ).
- `os.dup2` of a never-ending pipe onto fd 0 does reach a child's stdin on Windows (an inheriting child blocked; a DEVNULL child returned), so the INV-10 runner test can detect inheritance on both platforms.
- An `ast` scan confirmed every fixture, `sandbox.*`, `pack.*` and `api.*` name the tests use exists in `conftest.py`.

## Fixtures added (conftest.py)

`lib_api` (vidbyte.lib names only), `api` (adds the nine functions and configs), `sandbox` (home, workspace, skill sources, PATH-only bin, temp folder, stand-in logs; sets `USERPROFILE`, `HOME`, `PATH`, `tempfile.tempdir`), `call` (one thread function against the stand-in, default timeout 60 s), `check_error` (INV-5 attributes, per-code texts, ordered message parts), `fast_stop` (`NATIVE_KILL_WAIT_SECONDS` = 0.5, slack 5 s), `wait_until` (bounded polling), `alive` (process liveness on win32 and POSIX), `wsl_ready` (win32 + distlib launcher), `pack` (constants and pure helpers). `test_harness_threads_arguments.py` has its own `refuse` fixture.

## Pack name chosen

`tests/features/harness_threads` → `NativeThreadError.relevant_tests == ("tests/features/harness_threads",)` (spec §12.3 row 24).

## Spec defects that made tests hard

1. §9.2's table and row 44 step 6 list the five `WSLENV` names in different orders; the tests check the caller's value first and the five names as a set.
2. AC-16's bare `st_ino` proof can be fooled by inode reuse after a remove-and-copy; the test holds a hard link to the old file, so a rebuild breaks `samefile` and the old inode cannot be reused.
3. The spec gives no failure code for Muse `session/fork` answering the source id, or for a Muse exec answering another stream; EC-22 and rows 37/40 cover Grok and opencode only. Not tested.
4. AC-5 lists malformed agent, variant and distro as refused "when the function is called", but §9.1 validates them in the config record's constructor (a `ConfigurationError` before any call). Tested at the record.
5. `OPENCODE_CONFIG_CONTENT`'s `skills` member is shown in brackets in §9.2; the tests read it as omitted when no skills are passed and compare the JSON exactly.
6. §9.2 says Muse serve runs "without `META_API_KEY`", but D-13's `{**os.environ, **overlay}` lets a native serve inherit a caller's own `META_API_KEY`. Only WSL mode (where `WSLENV` decides) is tested for absence; the native test checks that serve never gets `api_key`.
7. EC-30 says "exit 127 or 'No such file or directory'"; the stand-in reproduces WSL's real `execvpe(...) failed: No such file or directory` text with exit 1.
8. INV-15 rule 2 is stated over `ast.Constant`, so `-1` (a unary minus on 1) passes it; noted in the test's KNOWN EDGE CASES.

## Addendum: spec r4 (commit 90265f78)

The spec author resolved defects 1, 3, 4 and 6 above in r4 (§16 rows S2-1 to S2-8, EC-45, the D-13 exception, §12.3 rows 27, 30, 42 to 44). Four tests follow from r4, all red for the same reason as the rest of the pack (`ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.native_threads'` at fixture setup):

| Test | Spec | Catches |
|---|---|---|
| `test_harness_threads_threads.py::test_muse_fork_answered_with_its_source_is_protocol_mismatch_before_any_exec` | EC-45, INV-6, INV-11 | a `session/fork` answer equal to the source id accepted, or decided only after an exec ran; `thread_id` must be the source id |
| `test_harness_threads_threads.py::test_muse_continue_answered_on_another_stream_is_thread_not_found` | EC-45, INV-11, INV-5 | a Muse exec answering on another session stream returned as the caller's thread; `thread_id` must be the stream id Muse answered |
| `test_harness_threads_credentials.py::test_muse_serve_never_sees_a_key_even_the_callers_own` | AC-3, INV-3, §9.2, D-13 exception | a native serve inheriting the caller's own `META_API_KEY` (no `env_remove`); every exec still gets `api_key` |
| `test_harness_threads_runner.py::test_env_remove_drops_an_inherited_name_before_the_overlay` | D-13 exception, rows 27, 30 | `env_remove` ignored, applied after the overlay, or written into `os.environ` |

Stand-in change: Muse exec gained `mode=continue_other_id` (answers an existing `--session-id` on a new stream, like the Grok and opencode modes). The fork case uses the existing `serve_mode=fork_returns_source`. Both modes were driven directly with the §9.2 argv, and the `env_remove` test passed against the branch's current `CliRunner` through a scratch adapter that applies `env_remove` itself (9 passed, 1 POSIX skip).

Red lines:
```
4 errors in 1.04s                                  (the four new tests)
test_harness_threads_threads.py: 20 errors in 1.32s
test_harness_threads_credentials.py: 17 errors in 1.25s
test_harness_threads_runner.py: 1 skipped, 10 errors in 1.11s
pack:  7 failed, 2 skipped, 388 errors in 10.97s
suite: 7 failed, 5173 passed, 16 skipped, 388 errors in 61.54s (0:01:01)
```
Lint: exit 0, no finding in the pack. Commits: `e3dcb214` (tests, stand-in mode, test plan), `5a1813da` (AC-3 Proof cell, the only spec edit). The existing WSL tests already matched r4's `WSLENV` wording (caller's value first, names in any order; serve without `META_API_KEY`), so they were not changed.

Post-S3 fix (`14ec6702`): two test helpers raised TypeError before the code under test ran. `call` now takes `raw_config`, which it hands to the function as `config=` unchanged, so EC-33 really passes another harness's record or a dict. The runner helper `invocation` takes `argv` positional-only, so a bad `argv` can replace it. No assertion changed. The pack now gives `395 passed, 2 skipped in 37.26s`.
