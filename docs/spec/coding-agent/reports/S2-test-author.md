# S2 report: test author, coding-agent

- **Spec:** `docs/spec/coding-agent/spec.md` r3.
- **Branch:** `feat/coding-agent`.
- **Commits:**
  - `a25a3c41` "test(agents): add failing tests for coding-agent [AC-1..AC-29]"
  - `d158d5f6` "docs(spec): record test proof for coding-agent" (fills only the §6.2 Proof column, 29 rows)

This report itself is not committed, because the prescribed commits did not include it.

## What was produced

The new feature pack is `tests/features/coding_agent/`. It has no production code, no stubs, and no edits to existing tests.

| File | Content |
|---|---|
| `conftest.py` (new, local to the pack) | Lazy feature imports: `coding_agent_cls`, `bash_module`. `script_model` (`ScriptedToolRunner`: one tool call per turn, then `isDone`, recording every request). `fake_provider_http`, which patches `HttpTransport._send_once` and records the sends. |
| `test_coding_agent_acceptance.py` | 5 E2E tests through `BaseAgent.run`/`arun` |
| `test_coding_agent_contract.py` | 9 functions, 19 cases |
| `test_coding_agent_web_fetch.py` | 6 functions, 43 cases |
| `test_bash_tool_contract.py` | 12 functions, 20 cases |
| `test_bash_tool_process_bounds.py` | 10 functions, real processes |
| `FEATURE.md`, `README.md` | Feature-pack docs in the `sdk_operation_costs` format |
| `docs/spec/coding-agent/test-plan.md` | Coverage map, omissions, red run, and notes for the implementer |

In total there are 42 test functions and 97 collected cases.

**Fixtures.** Only the new pack-local `conftest.py` was added. No shared fixture file was modified, and `tests/agent_test_support.py` is used unchanged. Bootstrap was not needed, because pytest 8.3.5 and pytest-asyncio 1.3.0 were already present. For the POSIX red proof, I used a WSL1 Ubuntu venv at `/tmp/s2-coding-agent-venv` (Python 3.12.3, same pins). It is outside the repo.

## Failure inventory

It was built from spec §5, §6, §8.5 and §13 only. Each item is listed with where it went: a test, or pruned.

- **Edge cases**
  - Root missing, a file, `42`, `None` or omitted (AC-11): tested.
  - Relative root followed by `chdir` (EC-7): tested.
  - A path with a space and `é` (AC-16): tested.
  - `""`, whitespace, int or bytes keys (AC-5): tested.
  - Two keys, all 6 pairs (AC-4): tested.
  - Caller tool name collisions (AC-8): tested.
  - A `Tools` catalog as caller input (AC-9): tested.
  - A blank, `None`, non-string or list command (AC-18): tested.
  - A NUL byte or a 3 MB command (EC-15): tested.
  - Invalid UTF-8 (EC-16): tested.
  - Exit code 3 (AC-12): tested.
  - Output of exactly the cap or more than it (AC-13): tested.
  - `yes` (AC-29): tested.
- **Hidden failure modes**
  - The limit covers only reading, so an early EOF unbounds the wait (AC-24): tested.
  - An unbounded wait after the kill with a setsid descendant (AC-25) or a Windows orphan (AC-27): tested.
  - Killing only while `returncode is None` (AC-15, EC-29): tested.
  - The transport is never closed (AC-28): tested.
  - A normal completion still kills (AC-26): tested.
  - Memory grows with output (`communicate()`-style buffering, AC-13): tested with tracemalloc.
- **Silent failures**
  - The fetch view shows only the summary (AC-7): tested.
  - The fetch falls back to an environment key (INV-6): tested.
  - A caller tool silently replaces one of the seven (AC-8): tested.
  - stdin inherited, so the call hangs until the limit (EC-11): tested.
  - The caller policy is replaced (AC-3): tested.
- **Hidden assumptions**
  - Constants copied at import, defeating the patch seam: guarded by the process tests, which patch them.
  - The Windows lookup walking too few parents for `mingw64/bin` (AC-22): tested.
  - `PATH` bash chosen on win32 (INV-15): tested.
  - Construction failing without bash (AC-17): tested.
- **End-to-end and acceptance:** AC-1, AC-2, AC-3, AC-7 and AC-17 run through the real loop, and INV-4 runs all six local tools.
- **Contract:** the public names and `__all__` (AC-20), the signature and constructor-only subclass (INV-1), `export_state` parity (INV-2), restore (AC-21), and the bash spec and constants (FR-9, D-11).
- **Security**
  - Keys never in errors, `RunState`, `card()` or failed results (AC-4, AC-5, AC-23): tested.
  - Key confined to its own provider origin and header (FR-5): tested.
  - No network or process at construction (INV-18): tested.
  - `spawn_failed` never echoes the exception message (S017): tested.
  - Default allow-all versus a caller's read-only policy (AC-2, AC-3): tested.
  - Prompt injection (EC-23) and bash not being root-scoped (EC-12) are accepted risks with nothing to test, so they were pruned.
- **Concurrency**
  - Cancellation propagates within the grace period (INV-12), directly and through `ToolSettings.tool_timeout_seconds`: tested.
  - Parallel calls (EC-19) and the `ProcessLookupError` race (EC-25) were pruned, because they are non-deterministic and independent processes share no state.
- **Property-based:** none. No invariant is algebraic, and the one adversarial argv case covers quoting.

## What was pruned and why

The full list is in test-plan.md under "Tests deliberately NOT written". In short:

- **Covered elsewhere or unchanged code:** fork (EC-21, INV-23), the Jev specialist (INV-22, which holds through the `generate_reply` identity assertion), non-linear runtimes (INV-24), EC-22, and INV-19/20/21.
- **Accepted risks:** EC-12 and EC-23.
- **Existing `ToolSettings` behaviour:** EC-17 and EC-18.
- **Not deterministic:** EC-19 and EC-25.
- **Python's own behaviour:** EC-20.
- **Same path as AC-12:** EC-24.
- **asyncio's own error, and forcing it would affect the whole session:** EC-26.
- **Owned by the existing fetch tools:** EC-27.
- **Not-built options Q-2 to Q-6:** no test demands them.

## Red run (exact output)

Windows 11, Python 3.11.0, run from the worktree root:

```
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_acceptance.py
      5 E       ImportError: cannot import name 'CodingAgent' from 'vidbyte' (…\vidbyte\__init__.py)
5 errors in 0.25s
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_contract.py
     19 E       ImportError: cannot import name 'CodingAgent' from 'vidbyte' (…\vidbyte\__init__.py)
1 failed, 18 errors in 0.39s
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_web_fetch.py
     43 E       ImportError: cannot import name 'CodingAgent' from 'vidbyte' (…\vidbyte\__init__.py)
43 errors in 0.65s
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_bash_tool_contract.py
     16 E       ModuleNotFoundError: No module named 'vidbyte.tools.builtins.bash'
4 skipped, 16 errors in 0.41s
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_bash_tool_process_bounds.py
      3 E       ModuleNotFoundError: No module named 'vidbyte.tools.builtins.bash'
7 skipped, 3 errors in 0.24s
```

WSL1 Ubuntu, Python 3.12.3. Here no POSIX test skips:

```
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_bash_tool_contract.py
     20 E       ModuleNotFoundError: No module named 'vidbyte.tools.builtins.bash'
20 errors in 0.43s
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_bash_tool_process_bounds.py
     10 E       ModuleNotFoundError: No module named 'vidbyte.tools.builtins.bash'
10 errors in 0.33s
```

The rest of the suite:

- **Focused area:** `158 passed in 2.55s`.
- **Full suite, Windows:** `1 failed, 2629 passed, 12 skipped, 85 errors`.
- **Full suite, WSL:** `1 failed, 2621 passed, 9 skipped, 12 warnings, 96 errors`.

Every failure and error in both full runs is inside `tests/features/coding_agent/`, so no comparison against merge-base `8f23fd67` was needed. `python lint/run.py` reports `SDK-LINT: PASS` with the pack staged, and A001 stays at 643/643.

## Satisfiability and mutation check

The prototype was never committed and lives outside the repo.

To make sure no test is impossible or vacuous, I wrote a throwaway prototype of `bash.py` and `coding.py` from §8.5 / D-10 to D-19 into a scratch copy of the tree under the session scratchpad. With it, all 97 cases pass on Windows 3.11.0 (86 passed, 11 skipped) and on WSL 3.12.3 (97 passed in 17 s). One real test defect was found this way and fixed before commit: AC-11 compared against `repr(details)`, which doubles Windows backslashes, so it now compares the detail values as text.

Mutations of the prototype, and the tests that caught them:

| Mutation | Caught by |
|---|---|
| `killpg` only while `returncode is None` | `test_cancellation_kills_the_process_group_even_after_the_shell_has_exited`, `test_agent_tool_timeout_cancels_bash_and_kills_the_background_child` |
| no transport close | `test_timed_out_call_closes_its_pipe_so_loop_shutdown_reports_nothing` (WSL 3.12, Windows 3.11, and Python 3.13.1 standalone: 1 open transport and 2 unraisable "Event loop is closed") |
| unbounded wait after the kill | `test_setsid_descendant_…` (30.0 s > 6 s on 3.12). On Windows 3.13.1 the call took 8.03 s against the test's 6 s bound. It is not caught on 3.11, which is expected: `wait()` returns at launcher exit. |
| limit over reading only | `test_command_that_closes_its_output_still_times_out_and_is_killed` |
| `process.kill()` instead of `killpg` | 4 process tests |
| `_stop` after a normal completion | `test_background_process_…` |
| no truncation line on timeout | `test_endless_printer_…` |
| `CancelledError` swallowed | 3 cancel tests |
| no `_stop` on cancel | the 2 POSIX cancel tests (on Windows the command cannot be stopped anyway, per EC-14) |
| keep everything / `communicate()` then slice | `test_large_output_…` (cap assertion; tracemalloc peak 40 MB > 8 MB) |
| bare fetch tool without the view | AC-7 plus 4 web tests |
| `BaseAgent` default policy | AC-1, AC-2, AC-17, the INV-2 parity test, and AC-21 |
| relative root passed to the file tools | `test_root_bound_tools_and_bash_keep_the_construction_root_after_chdir` |
| environment key overrides the parameter | 4 web tests |

The spec's own design takes 3.02 s on Windows Python 3.13.1 for the AC-27 command, with no open transport and no unraisable errors.

**Environment note.** In one WSL1 session, `ps aux` hung for minutes while reading `/proc`. That is a WSL1 quirk, not a test problem, and real Linux CI is unaffected. The pack's `/proc` reads are all bounded scans of `/proc/<pid>/stat`.

## Spec defects and notes

There are no blocking defects. Notes for S3 and the reviewers:

1. **AC-16** says "the printed path is the root folder (POSIX)". Git Bash prints `/c/...` paths, so the test proves the working directory through a marker file the command writes. That check is portable and also runs on Windows. The Proof cell says so.
2. **AC-27** requires Python 3.13. CI is Linux 3.11/3.12 only, so the 3.13 run is manual. It was measured on the prototype as above.
3. **AC-29** promises "a truncation line without a byte count", while §8.5's line `[output truncated at <BASH_MAX_OUTPUT_BYTES> bytes]` contains the cap's number. The test accepts exactly one truncation line whose only digits are the cap, so the two texts are consistent. A reviewer might still read "without a byte count" literally.
4. **AC-22 seam.** The test patches `sys.platform` and `shutil.which` at construction. It binds the implementation to read both through their modules, which is how §8.5 / FR-11 phrase the lookup.
5. **AC-28 detection** uses `gc.get_objects()` for `asyncio.base_subprocess.BaseSubprocessTransport`, plus `sys.unraisablehook` and recorded warnings. These are CPython internals, but they are stable across 3.11 to 3.13 and are the only observable signal of the leak.
6. **EC-15.** The over-long command is an `OSError` on both OSes, with different messages: "Argument list too long" on Linux and WinError 206 "The filename or extension is too long" on Windows. The test forbids both message fragments.

There are no tests I could not make deterministic. All timing assertions are upper bounds (limit 2 s + grace 1 s + 3 s slack) and use polling, not fixed sleeps.
