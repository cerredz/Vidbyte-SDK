# Test plan: coding-agent

This plan was written against spec r3, using pytest 8.3.5 and pytest-asyncio 1.3.0. Prior art:

- `tests/test_agent_tool_loop.py`, for the offline runner, `tool_call_states` and the tool messages.
- `tests/test_web_operation_client_retry.py`, for the `HttpTransport._send_once` seam.
- `tests/features/sdk_operation_costs/`, for the feature-pack layout (README.md, FEATURE.md).
- `tests/agent_test_support.py`, for `build_test_agent` and `bind_test_runner`.

All new tests live in one feature pack, `tests/features/coding_agent/`, which holds `conftest.py`, five test modules, FEATURE.md and README.md. The pack has 42 test functions and 97 collected cases.

## Coverage map

The test files are abbreviated as follows:

| Short name | File in `tests/features/coding_agent/` |
|---|---|
| **acc** | `test_coding_agent_acceptance.py` |
| **con** | `test_coding_agent_contract.py` |
| **web** | `test_coding_agent_web_fetch.py` |
| **bct** | `test_bash_tool_contract.py` |
| **bpb** | `test_bash_tool_process_bounds.py` |

The levels are:

- **E2E**: through `BaseAgent.run`/`arun` with a scripted offline model, real tools, real bash and a real policy.
- **Contract**: the public object surface.
- **Integration**: the real `BashTool` on real OS processes.

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | acc → `test_spec_snippet_builds_seven_tools_over_an_absolute_root_and_runs_through_the_loop` | E2E | The §4 snippet with a relative `"my-project"` gives a relative or cwd-dependent `root_dir`, the wrong or misordered tool names, or a loop in which bash never runs. | It could pass if `run` never reached a tool. It does not, because the model's tool message must start with `snippet-ran` and end with `exit code: 0`, and both states must be `succeeded`. |
| AC-2 | acc → `test_default_policy_lets_the_model_write_edit_and_run_bash_under_root` | E2E | With no policy, `BaseAgent`'s SAFE+READ default denies `write_text`, `replace_text` and `bash`. | It could pass if the calls were only scheduled. It does not, because the file content on disk must be `alpha gamma` and bash's `cat` must show that same text to the model. |
| AC-3 | acc → `test_caller_read_only_policy_denies_bash_and_write_without_side_effects` | E2E | The caller's `PermissionPolicy()` is replaced or merged with allow-all, or a denied bash still spawns. | It could pass if bash ran but wrote nothing. It does not, because the denied bash command itself writes `spawned.txt`, and `tmp_path` must stay empty. The test also checks the identity `agent.permission_policy is policy`. |
| AC-4 | web → `test_two_fetch_keys_are_rejected_naming_both_parameters_but_neither_key` (6 pairs) | Contract | Two keys pass with hidden precedence, or the error echoes a key value. | It could pass on an error that names nothing. It does not, because each supplied parameter name must appear and each distinctive `…-SECRET-7f3a91` value must not. |
| AC-5 | web → `test_blank_or_non_string_fetch_key_is_rejected_without_echoing_it` (4 params × 5 values) | Contract | `""`, whitespace, `12345` or bytes are accepted and fail later as a 401 on every fetch, or the value is echoed. | It could pass if the error came from somewhere unrelated. It does not, because it must be a `ConfigurationError` naming the parameter. Blank values cannot be echo-checked, so only the non-blank ones are. |
| AC-6 | web → `test_the_supplied_key_picks_the_last_tool_without_network_or_process` (5 cases) | Contract | The wrong seventh tool is picked, the provider is chosen from the environment, or construction opens a socket or starts a process. | It could pass if the network were never reachable anyway. It does not, because `socket.connect`/`connect_ex`/`create_connection`, `subprocess.Popen` and `os.system` are all replaced with functions that raise. The environment offers a different key for every provider. |
| AC-7 | acc → `test_keyed_fetch_shows_every_page_to_the_model_and_bills_like_the_bare_tool` | E2E | The model sees only the "N pages" summary (`fetch.py:39-42`), page order is lost, or the view changes billing. | It could pass because the URLs already appear in the summary. It does not, because order is checked only after the bare summary, the bare tool's message must contain no markdown, and the usage records must equal the bare agent's. |
| AC-8 | con → `test_caller_tool_named_like_a_coding_tool_is_rejected_at_construction` (bash, glob, direct_http_fetch) | Contract | A caller tool silently replaces one of the seven (`replace=True`). | It could pass on any error. It does not, because the test requires `ToolRegistrationError` with the exact message "Tool already exists: <name>". |
| AC-9 | con → `test_caller_tools_follow_the_seven_coding_tools_in_caller_order` (list, `Tools`) | Contract | Caller tools are put first, reordered, dropped or copied. A `Tools` catalog is not accepted. | It could pass on names alone. It does not, because the test also checks object identity: `all()[7:] == tuple(caller_tools)`. |
| AC-10 | con → `test_base_agent_identity_errors_pass_through_unchanged` (4 cases) | Contract | `CodingAgent` supplies a default prompt or name, or turns the missing-keyword `TypeError` into something else. | It could pass on any exception. It does not, because the exact `AgentExecutionError` text is required, and so is a `TypeError` naming the missing keyword. |
| AC-11 | con → `test_root_dir_that_is_not_an_existing_directory_is_rejected_at_construction` (missing, file, 42, None, omitted) | Contract | A bad root is accepted and fails differently on every call later. | It could pass on any error. It does not, because it must be a `ConfigurationError` that names the bad value in its message or details (compared as text, so Windows backslashes are not doubled). An omitted root must be a `TypeError`. |
| AC-12 | bct → `test_completed_command_returns_both_streams_in_order_and_its_exit_code_as_success` | Integration | stderr is dropped or reordered, exit 3 becomes an error result, or `exit_code` is a string. | It could pass on unordered text. It does not, because it compares the exact non-empty line list `["to-stderr", "to-stdout", "exit code: 3"]` and checks the `int` type. |
| AC-13 | bct → `test_large_output_keeps_the_first_bytes_counts_the_rest_and_memory_stays_bounded` | Integration | All 20 MB are buffered (as `communicate()` does), the cap is off by a chunk, the omitted count is wrong, or the real exit code (7) is lost. | It could pass if little output were produced. It does not, because exactly `cap` leading `a`s are required, the omitted count must be exactly 19,950,000, and the tracemalloc peak must be below 8 MB. |
| AC-14 | bpb → `test_time_limit_kills_the_command_and_the_child_it_started`, and the timing in `test_command_past_the_time_limit_returns_timeout_with_output_so_far` | Integration | Only the shell is killed and the background `sleep` survives, or the call runs past limit + grace. | It could pass by timing out without killing anything. It does not, because the child and shell pids printed by the command are checked in `/proc` (zombies count as stopped), and the process group must have no live members. |
| AC-15 | bpb → `test_cancellation_kills_the_process_group_even_after_the_shell_has_exited`, `test_agent_tool_timeout_cancels_bash_and_kills_the_background_child`, `test_cancelled_call_reraises_cancellation_within_the_grace_period` | Integration / E2E | `_stop` kills only while `returncode is None`, so the shell has exited and the server survives. Cancellation is swallowed, or the wait after the kill is unbounded. | It could pass by cancelling before the shell exits. It does not, because the test waits until the shell pid is gone while the call is still pending, then cancels. The agent-level test checks the runtime's "timed out" message and that the child is stopped. |
| AC-16 | bct → `test_command_runs_in_the_root_folder_even_when_its_path_has_spaces_and_unicode` | Integration | `cwd` is not set, or a path containing a space or `é` breaks it. | It could pass if the cwd already were the root. It does not, because pytest's cwd is the repo, and the marker file must land in `project root é`. It checks a marker file rather than `pwd` text, because Git Bash prints `/c/…` paths. |
| AC-17 | acc → `test_missing_bash_fails_only_the_bash_call_and_the_other_tools_keep_working`; bct → `test_missing_bash_returns_bash_not_found_with_install_guidance` | E2E / Integration | Construction fails without bash, the agent breaks, or the error gives no guidance. | It could pass if bash were still found. It does not, because `PATH` is an empty folder and cwd is that folder too (Windows also searches cwd). The bash state must be `failed` while write and grep succeed, and the text must name bash, or Git for Windows on win32. |
| AC-18 | bct → `test_bash_rejects_a_missing_blank_or_non_string_command_before_spawning` (6 cases) | Contract | A blank, `None`, non-string or list command reaches the spawn. | It could pass if everything were rejected. It does not, because a valid `echo ok` must validate to `None`. |
| AC-19 | gate-proven: `python lint/run.py` → `SDK-LINT: PASS` with every listed rule at or below baseline | Gate | — | — |
| AC-20 | con → `test_public_names_resolve_to_one_coding_agent_class_and_one_bash_tool_class`; the `--check` half is gate-proven by `python scripts/generate-sdk-public-api.py --check` (C016) | Contract / Gate | The two exports are different objects, `__all__` is missing a name, or the classes have the wrong base. | It could pass on a mere import. It does not, because it checks identity across all the import paths, plus `__all__` membership and the base classes. |
| AC-21 | con → `test_restored_state_keeps_the_seven_tools_and_the_allow_all_policy` | Contract | Restoring loses allow-all, reorders the tools, or sets `__resume_tool_mismatch__`. | It could pass if nothing were restored. It does not, because names, permissions and the marker are all asserted. |
| AC-22 | bct → `test_windows_lookup_runs_git_bin_bash_never_the_path_bash` (cmd, bin, mingw64/bin), `test_windows_lookup_stops_after_three_parent_folders_of_git` | Integration (POSIX host, win32 lookup simulated) | The `PATH` bash (the WSL launcher) is chosen, the walk is too short for `mingw64/bin`, or it is unbounded. | It could pass if both stand-ins printed the same text. It does not, because the stand-ins print different markers, and the test runs the result to prove which executable was chosen. |
| AC-23 | web → `test_key_is_absent_from_exported_state_and_agent_card`, `test_failed_keyed_fetch_passes_through_unchanged_and_never_carries_the_key` | Contract | The key leaks into `RunState`, `card()` or a failed `ToolResult`. | It could pass if the key were never used. It does not, because the 401 path must be the bare tool's own `fetch_failed` result, and the key is distinctive. |
| AC-24 | bpb → `test_command_that_closes_its_output_still_times_out_and_is_killed` | Integration | The limit covers only reading, so an early EOF then blocks `process.wait()` for the full `sleep`. | It could pass if the command finished. It does not, because the shell `wait`s on a 30 s sleep, the elapsed time must be ≤ 2 + 1 + 3 s, and both pids must be stopped. |
| AC-25 | bpb → `test_setsid_descendant_holding_the_output_cannot_stretch_the_call_past_limit_plus_grace` | Integration | `process.wait()` after the kill is unbounded. On Python 3.12+ it waits for the setsid descendant's pipe. | It could pass on Python 3.11, where `wait()` returns at shell exit. It does not on CI 3.12 or in WSL 3.12.3, where this exact mutation was measured failing. |
| AC-26 | bpb → `test_background_process_with_both_streams_redirected_survives_a_completed_call` | Integration | A normal completion still calls `_stop`, killing a properly detached server. | It could pass if the process died for another reason. It does not, because the time limit is raised to 15 s and the result must be a success in under 3 s with the pid still live. |
| AC-27 | bpb → `test_command_past_the_time_limit_returns_timeout_with_output_so_far` (cross-platform; on win32 it is the AC-27 case) | Integration | On Windows the Git launcher's orphan holds the pipe, so the call blocks until `sleep 8` ends, or output so far is lost. | It could pass on Python 3.11, where `wait()` returns at launcher exit. The 3.13 half is a manual run (see Notes). |
| AC-28 | bpb → `test_timed_out_call_closes_its_pipe_so_loop_shutdown_reports_nothing` | Integration | `_stop` never closes the transport, so it stays open after the call. After `asyncio.run`, the transport's finalizer reports "Event loop is closed" or "closed pipe", or warns "unclosed transport". | It could pass if the warnings were filtered. It does not: the test lists `BaseSubprocessTransport` objects created during the call that are not `is_closing()`. It captures `sys.unraisablehook` and records warnings with `simplefilter("always")` around `asyncio.run` + `gc.collect()`, which is an explicit check, since pytest has no `filterwarnings=error`. |
| AC-29 | bpb → `test_endless_printer_times_out_with_the_first_bytes_and_a_truncation_marker` | Integration | The `timeout` result has no truncation signal, reports `truncated False`, keeps more than the cap, or claims an omitted count. | It could pass on a short output. It does not, because the cap is patched to 1000 and exactly 1000 bytes of `y\n` must be kept, followed by one truncation line whose only numbers are the cap. |
| INV-1 | con → `test_coding_agent_adds_only_a_constructor_with_root_keys_tools_and_policy` | Contract | A new `BaseAgent` method or property is overridden (for example `generate_reply`, INV-22), or the signature drifts from §8.5. | It could pass on a signature that merely has the right names. It does not, because the defaults, `KEYWORD_ONLY` kinds and the single `**kwargs` are all compared. |
| INV-2, INV-8, §9.1 | con → `test_coding_agent_exports_the_same_state_as_an_equivalent_base_agent` | Contract | Pass-through keywords change meaning, the prompt is altered, or a key or root enters `RunState`. | It could pass if the state were empty. It does not, because 13 non-default keywords (including `run_id`, `output_schema` and metadata) are compared against a real `BaseAgent`. |
| INV-4, EC-7 | con → `test_root_bound_tools_and_bash_keep_the_construction_root_after_chdir` | E2E | A relative root resolved per call follows a later `chdir` into a decoy `proj`. | It could pass if no decoy existed. It does not, because the decoy exists, the test asserts it stays empty, and all six local tools run. |
| INV-9, D-10 (argv) | bct → `test_command_reaches_bash_verbatim_as_one_argument` | Integration | `shell=True`, string interpolation, or `shlex` mangles `'`, `$` and `;`. | It does not pass vacuously, because the exact first line `it's\|$HOME\|a;b\|bash\|` is required. |
| EC-11 | bct → `test_command_reading_stdin_sees_end_of_file_at_once` | Integration | An inherited stdin makes `read` wait for the time limit. | It does not pass vacuously, because the limit is 10 s and `read` must report status 1 (EOF). |
| EC-15 | bct → `test_command_the_os_cannot_start_returns_spawn_failed_naming_only_the_exception_class` (NUL, 3 MB) | Integration | `ValueError`/`OSError` escape `execute`, or the exception message leaks (S017). | It does not pass vacuously, because `spawn_failed` and a `…Error` class name are required, and the exact OS message fragments must be absent. |
| EC-16 | bct → `test_invalid_utf8_output_is_decoded_with_replacement_characters` | Integration | Strict decoding raises on `\xff\xfe`. | It does not pass vacuously, because the exact `��-tail` is required. |
| FR-5, FR-6, INV-5, INV-6, INV-16 | web → `test_keyed_fetch_sends_the_parameter_key_to_its_provider_and_shows_the_page` (4 providers) | Contract | A key reaches the wrong origin or header, the environment key is used, the view changes the spec or metadata, or the page text is missing. | It could pass if no request were made. It does not, because the recorded send must hit the provider's origin with the key in a header, and the result is compared to the bare tool's output and metadata. |
| FR-9, INV-14, D-11 | bct → `test_bash_tool_declares_one_required_command_with_execute_permission_and_fixed_bounds` | Contract | The permission is not EXECUTE, so bash is retried or allowed by default. The constants or the parameter shape drift. | It does not pass vacuously, because the exact values are compared. |
| INV-10..12, INV-25, INV-26 | covered by AC-13, AC-14, AC-15, AC-24 to AC-29 above | — | — | — |

## Tests deliberately NOT written

- **Fork (EC-21, INV-23).** `vidbyte/agents/fork.py` is unchanged and covered by `tests/test_agent_fork_isolation.py`. The view's `_rewrap` is reachable only through a clone hook that no coding tool has.
- **JevAgent specialist (INV-22).** It holds because `generate_reply is BaseAgent.generate_reply`, which the INV-1 test asserts. A Jev integration run would only re-test Jev.
- **Non-linear runtimes (INV-24).** These are a pure pass-through of `**kwargs`. The INV-2 parity test already proves the keywords arrive unchanged.
- **Caller EXECUTE/WRITE tools allowed (EC-22).** This is a direct consequence of INV-7's allow-all, which AC-2 proves.
- **Bash is not root-scoped (EC-12) and prompt injection (EC-23).** Both are accepted risks with no guarantee to test.
- **Result size (EC-17) and a tool timeout above `BASH_TIMEOUT_SECONDS` (EC-18).** These are existing `ToolSettings` behaviour. Bash's own limit firing first is the AC-14 path.
- **Parallel calls (EC-19).** They are independent processes with no shared state to race. A test would be timing-dependent.
- **`CodingAgent.restore(state)` raising `TypeError` (EC-20).** This is Python's own missing-keyword error, and testing it would pin the absence of Q-5.
- **Signal exit codes (EC-24).** These take the same path as any exit code (AC-12), and the negative POSIX code is the OS's.
- **The `ProcessLookupError` race (EC-25).** It cannot be made deterministic without mocking `os.killpg`, which §13 does not list as a seam.
- **A selector event loop on Windows (EC-26).** The error is raised by asyncio, not by the tool, and forcing that loop would affect the whole session.
- **No network (EC-27).** The existing fetch tools own this. The pass-through of a failed fetch is proven by the 401 test.
- **INV-19, INV-20 and INV-21.** These are protected by unchanged code and existing tests: `tests/test_agent_tool_loop.py::test_agent_denies_write_tool_by_default` and the filesystem tool tests. AC-7 additionally asserts that the bare tool's message is unchanged (it holds no markdown).
- **Property-based and fuzz tests.** No contract here is algebraic. Command text goes to bash verbatim, and the one adversarial argv case covers quoting.
- **Not-built options Q-2 to Q-6.** No test demands a configurable timeout or cap, an environment allow-list, a default `result_max_chars`, `CodingAgent.restore`, or a Windows job-object kill.

## Red run (before implementation)

Bootstrap: none needed. pytest 8.3.5 and pytest-asyncio 1.3.0 were already installed for Windows Python 3.11.0. A WSL1 Ubuntu venv at `/tmp/s2-coding-agent-venv` (Python 3.12.3, the same pins) runs the POSIX-only tests red. It lives outside the repo.

Every new case fails or errors at import, either with `ImportError: cannot import name 'CodingAgent' from 'vidbyte'` or with `ModuleNotFoundError: No module named 'vidbyte.tools.builtins.bash'`. These are the two modules the spec creates. No case fails for any other reason. The imports sit inside the `conftest.py` fixtures (`coding_agent_cls`, `bash_module`) or the test body, so collection succeeds and the rest of the suite is unaffected.

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

The 11 Windows skips are the POSIX-only tests (see Notes).

WSL1 Ubuntu, Python 3.12.3. All POSIX tests run here, and none skip:

```
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_bash_tool_contract.py
     20 E       ModuleNotFoundError: No module named 'vidbyte.tools.builtins.bash'
20 errors in 0.43s
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_bash_tool_process_bounds.py
     10 E       ModuleNotFoundError: No module named 'vidbyte.tools.builtins.bash'
10 errors in 0.33s
```

The rest of the suite still collects and passes:

```
$ PYTHONPATH=$(pwd) python -m pytest -q tests/test_agent_base.py tests/test_agent_tool_loop.py tests/test_agent_fork_isolation.py tests/test_code_search_tools.py tests/test_filesystem_tools.py tests/test_patch_tool.py tests/test_security_executor.py tests/test_restore_permission_policy.py tests/test_jev_agent.py tests/test_web_operation_client_retry.py
158 passed in 2.55s
$ PYTHONPATH=$(pwd) python -m pytest -q            # Windows 3.11.0
1 failed, 2629 passed, 12 skipped, 85 errors in 15.26s
$ PYTHONPATH=$(pwd) python -m pytest -q            # WSL1 Ubuntu 3.12.3
1 failed, 2621 passed, 9 skipped, 12 warnings, 96 errors in 9.00s
```

In both full runs, every failure and error is in `tests/features/coding_agent/` (97 cases = 1 failed + 96 errors in WSL). Nothing outside the pack fails, so no comparison against merge-base `8f23fd67` was needed. `python lint/run.py` reports `SDK-LINT: PASS` with the pack staged, and A001 stays at 643/643.

## Notes for the implementer

- **Names the tests import.** `from vidbyte import CodingAgent`, `vidbyte.agents.CodingAgent`, `vidbyte.agents.coding.CodingAgent`, `from vidbyte.tools.builtins import BashTool`, and the module `vidbyte.tools.builtins.bash` with `BashTool`, `BASH_TIMEOUT_SECONDS`, `BASH_MAX_OUTPUT_BYTES`, `BASH_READ_CHUNK_BYTES` and `BASH_KILL_GRACE_SECONDS`. The keyed view needs a public `wrapped_tool` property. The names must appear in the `__all__` lists of `vidbyte`, `vidbyte.agents` and `vidbyte.tools.builtins`.
- **Read the constants at call time.** The process-bound tests `monkeypatch.setattr(bash_module, "BASH_TIMEOUT_SECONDS", 2.0)` and set the grace to 1.0, and AC-29 sets the cap to 1000. The implementation must not copy the constants into `__init__`, default arguments or closures.
- **The lookup seam is construction time.** AC-22 patches `sys.platform` and `shutil.which` only while `BashTool(root)` is being built. Use `sys.platform` and `shutil.which` through those modules (as §8.5 says), not `os.name`, `platform.system()` or `from shutil import which`.
- **Output format.**
  - The timeout result's last line must contain the patched limit as text (`f"{BASH_TIMEOUT_SECONDS:g}"` gives `2`, and `2.0` also passes).
  - The omitted count may be plain digits or comma-grouped.
  - The `spawn_failed` text must name the class (`ValueError` / `OSError`) and must not include the exception message: no "embedded null", "argument list too long" or "extension is too long".
- **Missing bash is legal.** The AC-17 acceptance test builds the agent with `PATH` set to an empty folder, so neither `BashTool.__init__` nor `CodingAgent.__init__` may raise when bash is missing.
- **Timing bounds.** The process tests use limit 2 s, grace 1 s and 3 s of slack. They poll for pid files and never sleep a fixed time. The agent-level test uses `ToolSettings(tool_timeout_seconds=1.5)` and requires that the cancellation path is bounded by `BASH_KILL_GRACE_SECONDS`.
- **The AC-28 check.** The check looks for `asyncio.base_subprocess.BaseSubprocessTransport` objects created during the call that are not `is_closing()` when `execute` returns. Closing through `getattr(process, "_transport", None)` after the bounded wait (D-18) satisfies it.
- **POSIX-only tests** skip on win32 hosts with a reason. They cover the group kill, `/proc` liveness, setsid, `yes` and the background survival test. The Windows lookup simulations also skip there, because their stand-in executables are shell scripts. On Windows, the time bound, the cancel bound and pipe cleanup still run, with an 8 s orphan.
- **Manual run, not in CI.** AC-27 on Python 3.13 (`py -3.13 -m pytest -q tests/features/coding_agent/test_bash_tool_process_bounds.py` from the repo root with `PYTHONPATH` set) and AC-22 against a real Git for Windows layout. CI runs only Linux 3.11 and 3.12.
- **Satisfiability check.** Before committing, a throwaway prototype of `bash.py`/`coding.py`, written from §8.5 into a scratch copy outside the repo and never committed, made all 97 cases pass on Windows 3.11 and WSL 3.12.3. Mutations of it were caught by the tests (see the S2 report). The prototype is not part of the deliverable. Implement from the spec.
