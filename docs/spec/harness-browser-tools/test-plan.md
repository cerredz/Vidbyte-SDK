# Test plan: harness-browser-tools

Spec `docs/spec/harness-browser-tools/spec.md` r3 (approved) · Framework: pytest 8.3.5 + pytest-asyncio 1.3.0 (`--strict-config --strict-markers`) · Prior art copied: `tests/features/harness_threads/conftest.py` (Sandbox, `call`, `check_error`, `fast_stop`, `alive`, `wsl_ready`, `lib_api`, `api`) and `fake_harness.py` (scripted stand-in run as a real child, per-launch JSONL logs, credentials logged as digests)

All tests live in `tests/features/harness_threads/`. Every vendor program is a real child process: `fake_harness.py` plays grok, opencode, Muse and `wsl.exe`. The new `fake_browser.py` plays three more things:
- `node` (`--version`, the bundled `npm-cli.js`, the ten pinned stdio MCP servers);
- the orphaned Chrome stand-in;
- the three remote endpoints, answered offline.

The fakes apply the vendor rules that §13 lists. The test `test_harness_threads_browser_fakes.py` checks them without any SDK code:
- opencode: the last matching permission wins, a denied tool leaves the list, and a global entry deep-merges;
- Grok: deny beats allow, and a tool with neither rule cancels the turn;
- Muse: no `schema_version` exits 1, a bad entry silently drops all MCP, and a server that fails to start fails the run.

Nothing in the SDK is mocked. Only module constants are monkeypatched, as §13 allows: timing knobs, the Chrome locations, `NATIVE_PS_PATHS` and `tempfile.tempdir`. `runner_spy` records each `CliInvocation`, then runs the real `CliRunner.run`.

## Coverage map

| Spec ID | Test (file → name) | Level | Failure it catches | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | acceptance → `test_the_developer_snippet_runs_as_documented` | e2e (fake opencode on PATH, fake node, cache) | The documented snippet does not run as written, or prints the wrong id, text, calls or artifacts | The snippet is executed verbatim except the workspace literal, which is asserted to occur exactly twice. The printed id is compared to the session the fake logged, and the artifact path to the file the fake server wrote. |
| AC-2 | mounts → `test_every_browser_function_mounts_a_tool_and_reads_the_vendors_calls` (9); `test_muse_in_wsl_mode_mounts_jina_without_node_or_chrome` (3, win32) | e2e | A function is missing or mis-wired; the vendor's own web tools are left on; the per-call folder is in the workspace; the prompt is altered | `tool_calls` must equal the one call the fake made through a real server process. Web-off is read from what the fake vendor parsed, not from SDK state. The folder is derived from the profile option the server received. |
| AC-3 | contract → `test_native_and_subpackages_export_the_browser_functions`, `test_browser_functions_take_the_plain_parameters_with_tools_after_model`; surface pin `test_native_package_exports_exactly_the_nine_functions_and_their_records` | surface | Missing exports; signatures that drift from the plain sibling | The signatures are compared parameter by parameter (name, kind, default, normalised annotation) against the live plain functions, not against a copy. |
| AC-4 | registry → `test_registry_suggests_a_close_name_or_lists_the_mountable_tools`, `test_public_functions_refuse_bad_tools_before_any_process_or_file[playwrite, skyvern]` | unit + e2e | No suggestion; the item is quoted; a process starts | The observation must name `tools[0]` and `playwright`. "playwrite" must be absent from the text, and the snapshot and start log must be unchanged. |
| AC-5 | registry → `test_registry_refuses_exclusions_hosts_and_duplicates`, public-function cases `puppeteer` and `playwright@browserbase` | unit + e2e | An excluded name or a host is accepted, or refused without its reason | The recorded reason words are checked per exclusion, and the hosts text exactly. |
| AC-6 | mounts → `test_opencode_narrowing_denies_the_server_then_allows_one_tool`, `test_grok_narrowing_allows_exactly_and_denies_every_other_known_tool`, `test_muse_refuses_narrowing_and_keys_before_any_io[firecrawl:search]` | e2e | A wildcard allow survives narrowing; the rule order is wrong; Muse mounts an unfilterable catalog | opencode order is read from the fake's ordered rule list, because a logged mapping is key-sorted. The fake hides denied tools exactly as opencode does, so `visible` must hold one tool. Grok denies are compared with `selection.denied` (25). |
| AC-7 | mounts → `test_tool_key_travels_only_in_the_child_environment[grok, opencode]`, `test_muse_refuses_narrowing_and_keys_before_any_io[brave]` | e2e | The key is in argv, stdin, a file, `os.environ`, the wrong overlay member, or error text | Every recorded `CliInvocation` is scanned, and the whole sandbox tree for UTF-8 and UTF-16 copies. The fake brave server exits at start without its key, so the key must really arrive. |
| AC-8 | registry → `test_registry_refuses_keys_by_meaning_without_echoing_them`; public case `brave` with no key | unit + e2e | A missing, superfluous or misplaced key is accepted or echoed | The fragment scan covers `str`, `repr` and details. |
| AC-9 | mounts → `test_a_key_in_the_callers_environment_is_never_used_silently[grok, opencode]` | e2e | The caller's `FIRECRAWL_API_KEY` reaches the harness or its server | Both the harness start and the server start record the variable's digest or `None`. |
| AC-10 | runtime → `test_no_node_on_path_is_runtime_missing` (3), `test_node_below_the_floor_is_runtime_missing_naming_the_version` (2), `test_a_batch_file_node_is_refused_unrun` (2, win32), `test_no_chrome_is_runtime_missing_listing_the_searched_locations` (2) | e2e | A missing, old or batch Node, or a missing Chrome, is accepted; the harness starts anyway | The batch file writes a marker if run. The found version and the searched path must appear in the message. Every refusal checks that no harness start was logged. |
| AC-11 | runtime → `test_cold_cache_installs_once_with_the_pinned_argv_and_publishes`, `test_a_failing_install_publishes_nothing_and_attaches_npms_text` | e2e (fake npm) | npx, a floating version, a second install, a non-atomic publish, a half-published folder | The fake npm accepts only the exact FR-9 argv and exits 2 otherwise. The server must start from the published entry. A second call must leave the npm start count at 1. |
| AC-12 | lifecycle → `test_grok_names_each_server_it_never_listed[playwright, jina]`, `test_opencode_without_a_mounted_tool_call_says_so`, `test_muse_required_server_failure_carries_muses_reason` | e2e | A dead mount returns success | Each fake produces the vendor's own evidence: Grok leaves the server out of `available_commands`, opencode makes no call, and Muse fails the run with its reason. The thread id and vendor text are compared with what the fake printed. |
| AC-13 | lifecycle → `test_a_returned_call_reaps_its_browser_and_removes_its_folder` (3), `test_artifacts_survive_a_successful_return_and_profiles_do_not` (3), `test_a_failed_run_reaps_and_discards_everything` (3), `test_a_cancelled_call_reaps_and_re_raises` (3), `test_a_timed_out_call_reaps_and_raises_the_timeout`, `test_process_reaper_kills_by_marker_and_spares_the_rest` | e2e + unit | A browser outlives the call; profiles stay; artifacts are kept after a failure | The fake browser is an orphan on both platforms (a spawner that exits), so a tree stop cannot end it. Only a reap by marker can, before its 30 s limit. `gone()` first asserts that a browser pid was logged. |
| AC-14 | mounts → `test_grok_browser_runs_switch_off_compat_scans_and_stream` | e2e | Compat scans stay on; the plain path changes | The browser start and the plain start are both read from the same fake. |
| AC-15 | the existing suite, plus the §13 pins (see the S2 report) | regression | The plain functions drift | All existing assertions are kept; only expected-value constants changed. |
| AC-16 | lifecycle → `test_the_sdk_writes_only_in_its_four_places` (3), `test_a_failing_call_leaves_no_trace` | e2e | Files are written in the workspace or outside the four places; a failure leaves debris | A byte-level snapshot of the whole sandbox, excluding only the fakes' own log folder. |
| AC-17 | every error test, through `conftest.check_browser_error` | e2e | `expected` names `NativeThreadResult`; message parts are missing or out of order | `expected` is compared exactly and must equal `details["expected"]`. |
| AC-18 | mounts → `test_grok_refuses_rules_beyond_the_argv_budget` | e2e | An over-budget argv starts Grok | Two narrowed servers come to about 2,677 units, well over 1,800, and nothing may start. |
| AC-19 | mounts → `test_muse_in_wsl_mode_refuses_every_stdio_tool_before_any_io` (4), `test_muse_in_wsl_mode_mounts_jina_without_node_or_chrome` | e2e | A stdio tool is mounted in WSL mode; the guidance does not name what can be mounted | WSL mode is a config (§13), so the refusals run on every platform, and not even `node --version` may start. |
| AC-21 | lifecycle → `test_concurrent_calls_keep_their_own_folders_and_browsers` | e2e | One call's reap kills the other's browser; a shared folder or agent file | The held call's browser pid is checked alive after the quick call returns, and only then is it released. |
| AC-22 | mounts → `test_opencode_mounts_a_keyed_remote_tool_with_a_bearer_header`, `test_grok_refuses_a_keyed_remote_tool_before_any_io[browserbase]` | e2e | A missing `oauth: false` or Bearer header; a key written into a Grok file | The fake Browserbase refuses a call without the header, and the call must complete. |
| AC-23 | registry → `test_stdio_rows_pin_package_version_entry_key_and_options`, `test_remote_rows_pin_https_urls_and_bearer_keys`, `test_capability_tool_names_match_vendor_facts`, `test_playwright_core_and_server_flag_groups_match_vendor_facts`, `test_every_exclusion_has_its_recorded_reason` | unit | Registry rows drift from §9.1 and the vendor facts | Tool sets are compared with the lists the fakes serve, which come from vendor facts §4, never with the registry itself. |
| AC-25 | registry → `test_request_record_refuses_bad_tools_without_quoting`; public case with a key-shaped item | unit + e2e | A key pasted into `tools` is quoted | An 8-character fragment scan over every surface. |
| AC-26 | mounts → `test_muse_settings_have_the_one_verified_shape`; fakes → `test_fake_muse_needs_schema_version_and_silently_drops_mcp_on_a_bad_entry` | e2e | A wrong settings shape silently disables MCP | The fake applies Muse's silent-disable rules, so a bad file would leave `tool_calls` empty and the equality fails. |
| AC-27 | mounts → `test_playwright_caps_add_tools_and_deny_none` (3) | e2e | Caps replace the core tools, or deny some | The fake server exposes 39 tools only with `--caps=devtools,pdf`, and opencode's visible count is read from the fake. |
| AC-28 | mounts → `test_opencode_ids_are_prefixed_and_enabled_beside_a_users_own_entry` | e2e | A user's disabled `mcp.playwright` disables or merges into the SDK's server | The fake deep-merges a global entry of the same id, as opencode does. |
| AC-29, AC-30 | registry → `test_request_record_refuses_bad_tool_keys_without_quoting`; public cases with a trailing line break and with swapped key and name | unit + e2e | A key is echoed through `tool_keys` naming | Fragment scan; the field must be `tool_keys[firecrawl]` or `tool_keys entry 0`. |
| AC-31 | mounts → `test_opencode_mounts_jina_with_no_node_and_no_chrome`; `test_muse_in_wsl_mode_mounts_jina_without_node_or_chrome` (win32) | e2e | A remote-only call demands Node or Chrome | PATH holds no node, and the Chrome search is patched to a missing file. |
| AC-32 | mounts → `test_grok_mounts_keyless_jina_as_a_url_only_entry`, `test_grok_refuses_a_keyed_remote_tool_before_any_io[jina]` | e2e | Keyless jina is not mounted on Grok, or a keyed one is | The fake Grok parses the url-only entry and calls it. |
| AC-33 | mounts → `test_readers_skip_vendor_names_that_fail_the_name_rule` (3) | e2e | A vendor-written name raises `configuration.invalid_argument` | The fakes emit the bogus names after the real call, so a reader that raises fails the test. |
| INV-8, D-21 | mounts → `test_grok_agent_file_lives_in_the_call_folder_with_a_neutral_body`, `test_chrome_devtools_starts_quiet` (3); runtime → `test_spaced_non_ascii_node_and_cache_paths_still_mount` (3, EC-37) | e2e | npx or relative entries; a shell-joined argv; Chrome DevTools phoning home | The node and entry paths are compared with the stand-in and the cache entry. |
| INV-11 | mounts → `test_same_strings_compile_the_same_mount[opencode, grok]`; registry → `test_selection_keeps_request_order_carries_keys_hidden_and_is_deterministic` | e2e + unit | Non-deterministic compiles | The two folders must differ, and the configs are equal only once the folder path is replaced. |
| D-18 | mounts → `test_grok_agent_file_lives_in_the_call_folder_with_a_neutral_body` | e2e | The agent body names a tool or claims tools are mounted | Word-boundary matching, so "example" does not count as "exa". |
| D-19 | lifecycle → `test_grok_browser_output_is_capped_at_the_process_cap`; contract → `test_widened_texts_name_both_grok_caps_and_the_browser_siblings` | e2e + unit | A Grok browser run cut at 4 MiB, or uncapped | The text is longer than the 4 MiB plain cap, and a 64 MiB + 64 KiB flood must raise `grok.output_too_large`. |
| D-22, D-15, FR-16 | contract → `test_widened_texts_…`, `test_result_record_table_covers_all_eighteen_operations`, `test_native_thread_error_expected_names_the_result_record`, `test_browser_codes_follow_main_and_map_for_every_harness`; errors pin | unit | Texts or tables missing | The live tables are compared with the spec lists. |
| D-27 | contract → `test_harness_subpackage_imports_run_one_way` (3), `test_hostkit_browser_and_lib_modules_import_only_downward`, `test_each_new_module_imports_first_in_a_fresh_interpreter` (7) | static + subprocess | Import cycles and layer breaks | `ast` reads the real files, and the fresh-interpreter import sees cycles that a warm `sys.modules` hides. |
| EC-1 to EC-7 | registry record and public tests | unit + e2e | Bad items and keys | As AC-4, AC-8 and AC-25. |
| EC-8, EC-9 | runtime (see AC-10) | e2e | | |
| EC-10 | runtime → `test_two_racing_installs_converge_on_one_published_copy` | e2e | Racing installs corrupt the cache | The fake npm waits at a file rendezvous for both installs; the staging folders must differ and only one published folder may remain. |
| EC-11 | runtime → `test_an_install_past_its_bound_is_stopped_and_cleaned`, `test_a_cancelled_install_is_stopped_cleaned_and_re_raised` | e2e | npm outlives its bound or the cancel; staging is left behind | The npm pid comes from the fake's log, and `npm_mode="hold"` would run for 30 s if not stopped. |
| EC-12 | runtime → `test_a_broken_published_folder_is_named_not_repaired` | e2e | A broken folder is silently reinstalled or used | The npm start count must stay 0, and the folder must still be broken afterwards. |
| EC-13 | runtime → `test_a_node_without_its_bundled_npm_cannot_install`, `test_a_failing_install_publishes_nothing_and_attaches_npms_text` | e2e | A Debian node "installs" | The fake node now fails "Cannot find module" for a missing `npm-cli.js`, as real node does; the fakes test pins that. |
| EC-14 | runtime → `test_an_unknown_home_is_tool_install_failed` | e2e | `RuntimeError` escapes as `runtime.error` | Patches `Path.home` as the existing Grok home test does. |
| EC-15 | runtime → `test_an_uncreatable_call_folder_is_launch_failed` | e2e | `mkdtemp` failing escapes uncaught | `tempfile.tempdir` points at a missing folder. |
| EC-17 | lifecycle (see AC-12) | e2e | | |
| EC-18 | lifecycle (see AC-12) | e2e | | |
| EC-19, EC-20, EC-21 | lifecycle (see AC-13) | e2e | | |
| EC-22 | lifecycle → `test_a_missing_ps_is_not_raised` (POSIX) | e2e | A missing `ps` raises, or the reaper falls back to PATH | It asserts the browser survived. That proves no other `ps` ran, so the test cannot pass by reaping normally. |
| EC-26, EC-27 | mounts (see AC-6, AC-7, AC-19, AC-22) | e2e | | |
| EC-28 | mounts → `test_grok_denied_call_is_a_failed_tool_call` | e2e | A denied call is dropped or marked completed | The fake Grok answers a denied call as Grok does. |
| EC-29 | lifecycle → `test_tool_calls_and_artifacts_cap_at_a_thousand` | e2e | Caps unenforced, or files deleted | 1,001 events and files; all 1,001 files must stay. |
| EC-30 | mounts → `test_continue_remounts_a_different_tool_set[opencode, grok]` | e2e | A stale mount is reused on continue | The second mount must hold only firecrawl. |
| EC-38 | runtime → `test_a_missing_harness_after_a_cold_install_keeps_the_install` | e2e | The install is discarded, or the wrong code is raised | Exactly one npm start, and the published entry remains. |
| EC-40 | mounts (see AC-28) | e2e | | |
| EC-41, EC-32 | mounts → `test_grok_unlisted_server_tool_cancels_the_turn_loudly` | e2e | A tool the registry does not list is silently allowed | The fake Grok cancels the turn with exit 0, exactly as vendor facts §9 records. |
| EC-42 | mounts (see AC-19) | e2e | | |
| EC-44 | mounts (see AC-33) | e2e | | |
| EC-45 | lifecycle → `test_grok_names_each_server_it_never_listed[jina]` | e2e | | |
| INV-4, NFR-3 | lifecycle → `test_keys_echoed_by_the_vendor_never_reach_the_error[grok, opencode]` | e2e | Echoed keys reach the error | The fake echoes the tool key and the harness key in its error output. |
| NFR-5 | runtime → `test_a_warm_call_starts_at_most_one_child_before_and_one_after[playwright, jina]` | e2e | Extra children, or an install on a warm cache | Every `CliInvocation` is counted by `runner_spy`. |
| §8.5 ProcessReaper | lifecycle → `test_process_reaper_kills_by_marker_and_spares_the_rest`, `test_process_reaper_never_raises_on_its_own_timeout` | unit (real processes) | Wrong process killed; marker on argv; raising on timeout | A control process must survive, and a second reap must return 0. |

## Tests deliberately NOT written

| Candidate | Why not |
|---|---|
| AC-20 full local gate, NFR-7 line counts and lint ratchets | These are run by the gate (`scripts/run_ci.py`, `lint/run.py`), not by pytest. |
| AC-24 README contents | Review and lint A009 cover them. A pytest check of prose would only pin wording. |
| Real Node, npm, Chrome, MCP servers, remote endpoints and vendor CLIs | They need network, money or accounts (NFR-2). The fakes encode the vendor facts that the live probes established. |
| Exact NFR-6 budget boundary (a call at 1,800 units passes) | The spec fixes the budget's inputs but not a formula a test could reproduce exactly. AC-18 tests a refusal far over it, and the positive narrowed Grok tests stay far under it. |
| EC-16 timing (a server slower than Grok's 2 s grace) | It would be wall-clock dependent. The test covers the same evidence (the server is absent from `available_commands`) through `grok_unlisted`. |
| EC-23, EC-24, EC-33 to EC-36, EC-39 residual, EC-43 | These are accepted residuals or vendor behaviour (spec §6.3), with no SDK guarantee to test. EC-39's prevention is AC-26. |
| EC-31 (a plain continue of a browser thread) | The plain path is unchanged (INV-14). The widened next steps are pinned in contract; whether Grok keeps the agent body is vendor behaviour. |
| A real Muse WSL-mode run off win32 | WSL exists only on win32. The refusals run everywhere (§13); the runs use `wsl_ready`. |
| A pinned per-capability tool assignment for Playwright | §9.1 gives only counts. Counts and the union with vendor facts are pinned instead (see the S2 report, defect 3). |

## Red run (before implementation)

Bootstrap: none. The worktree's existing interpreter (`py -3.11`, with pytest 8.3.5 and pytest-asyncio 1.3.0 already installed); no `pip install`, no network.

Command (from the worktree root):

```
PYTHONPATH=$(pwd) py -3.11 -m pytest tests/features/harness_threads -p no:cacheprovider -q --tb=line -rfEs
```

Final lines:

```
ERROR tests/features/harness_threads/test_harness_threads_browser_runtime.py::test_spaced_non_ascii_node_and_cache_paths_still_mount[muse]
SKIPPED [1] tests\features\harness_threads\test_harness_threads_browser_lifecycle.py:134: the POSIX reaper reads NATIVE_PS_PATHS; win32 uses System32 PowerShell
SKIPPED [1] tests\features\harness_threads\test_harness_threads_launcher.py:100: Muse is looked up on PATH only outside win32 (EC-29)
SKIPPED [1] tests\features\harness_threads\test_harness_threads_runner.py:245: the execute permission bit exists only on POSIX
18 failed, 439 passed, 3 skipped, 155 errors in 49.78s
```

Counts: 18 failed, 439 passed, 3 skipped, 155 errors (611 tests).
- New files: 155 setup errors, all `ModuleNotFoundError: No module named 'vidbyte.lib.enums.browser_tools'`; 11 contract failures (the missing §12.3 modules, and their fresh-interpreter imports); `test_harness_threads_browser_fakes.py` is green (10), because it checks only the fakes; 1 skip (EC-22 is POSIX-only).
- Existing files: 429 passed and 2 skipped, as before.
- 6 pinned tests are red only for the missing production names: errors 1, static_policy 2, and surface 3 (`test_native_package_exports_exactly_the_nine_functions_and_their_records`, `test_vocabularies_are_str_enums_carrying_the_vendor_values`, `test_old_public_names_no_longer_import`).
- 1 test was already red on pristine HEAD (below).

Every error and failure is caused by missing production code:
- all setup errors are `ModuleNotFoundError: No module named 'vidbyte.lib.enums.browser_tools'`;
- the contract failures are the missing §12.3 modules;
- the pinned tests fail on the missing names.

The one pre-existing red is `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`. Its merge-base half (`assert 148 == 120`) fails on pristine HEAD `4d3a9d55` as well.

## Notes for the implementer

1. **Chrome locations.** Name them `BROWSER_CHROME_PATHS` in `vidbyte.lib.constants.browser_tools`: a non-empty `tuple[str, ...]`, read through the module at call time. Pass each entry through `os.path.expandvars`, search them in order, and take the first existing file. The `runtime_missing` message names each searched location. The spec names no constant (§9.3 says only "Chrome location constants").
2. **Read these through their modules at call time**, because the tests monkeypatch them:
   - `BROWSER_TOOL_INSTALL_TIMEOUT_SECONDS`, `BROWSER_CHROME_PATHS`, `NATIVE_PS_PATHS`;
   - `tempfile.tempdir`, through `tempfile.mkdtemp(prefix="vidbyte-browser-")` with no `dir`.
   Use `Path.home()` for the cache root, since EC-14 patches it.
3. **Per-call folder layout.** The profile option value must be exactly `<folder>/profiles/<tool>` (Playwright `--user-data-dir`, Chrome DevTools `--userDataDir`). Playwright's `--output-dir` must be `<folder>/artifacts`. The tests find the folder from the profile path.
4. **Staging.** Staging lives under `~/.vidbyte/tools/.staging/`. After any outcome, `.staging` may exist but must be empty.
5. **Message contents.** The tests check these on `str(error)`, in the existing message order (function, code, label, workspace, thread id, observations, vendor text, cause, next step):
   - `browser.mount_unsupported`: in WSL mode the message names "jina" and "parallel"; for the Grok budget it matches `narrow|fewer`. One next-step text per code (FR-16) can carry both.
   - `runtime_missing`: the found Node version, the batch file path, or the searched Chrome paths.
   - `tool_install_failed`: npm's stderr as `vendor_message` (the test looks for `E404`), or the broken published folder's path.
   - `tools_unavailable`: for Grok, each missing tool as an observation. For opencode, the exact phrase "no mounted tool was used", each mounted tool's name, and the answer text as `vendor_message`. For Muse, Muse's reason as `vendor_message`.
   - `opencode.launch_failed` (EC-15): the temp folder path.
6. **Grok reader.** Only `tool_call` events with `toolName == "use_tool"` count; the fake also emits a built-in `read_file` call, which must be ignored. Denied calls end with status `failed`. A turn cancelled by an unruled tool is `grok.run_failed`, and its message contains "cancelled".
7. **Grok agent body.** The body must contain neither "mount" nor any `BrowserTool` value as a word.
8. **Children.** Every child goes through `CliRunner.run`:
   - `node --version` is exactly `[<node>, "--version"]`;
   - nothing runs before the harness for a remote-only selection;
   - at most one child runs after the harness.
9. **Key routes.**
   - opencode: a tool key is only inside `OPENCODE_CONFIG_CONTENT` (`mcp.vidbyte-<tool>.environment`), never as its own overlay member.
   - Grok: the key is an overlay member named by its variable.
   - Remove unpassed key variables (`env_remove`).
10. **Fake vocabulary.** It is in the headers of `fake_browser.py` and `conftest.py`. The fakes accept exactly the §9.1 shapes; the S2 report's probe drove them with those shapes, including a marker reap through System32 PowerShell.
