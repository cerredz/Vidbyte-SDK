# Harness thread function tests

## Folder Description / Intent

This folder tests the nine harness thread functions of `vidbyte.harnesses.native` (`run_`, `continue_` and `fork_` for Grok Build, opencode and Muse Code), the keyless thread helpers (list, get, read, lineage, search, delete) and the built-in command and skill functions, and the process helpers under them, entirely offline. Every vendor program is the scripted stand-in `fake_harness.py`, which logs what it received; the thread functions, `CliRunner` and the filesystem are real. `NativeThreadError.relevant_tests` points here.

## File Index

- `README.md` describes the folder and its files.
- `FEATURE.md` states the feature contract, the suite map and the strategies left out.
- `conftest.py` provides the lazy contract imports, the sandbox (home, workspace, PATH, temp folder), stand-in builders, the INV-5 error check, timing knobs and process liveness checks.
- `fake_harness.py` is the standard-library stand-in for grok, opencode, muse (exec and batch serve) and wsl.exe.
- `fake_harness_helpers.py` holds the stand-in's helper and skill paths: Grok streaming runs, export and delete over the real store layout, opencode `session list`, `db`, `export`, `session delete` and `--command`, and Muse `session/list`, `session/read` items, `export` and `init`.
- `test_harness_threads_surface.py` checks exports, signatures, vocabularies, failure codes, contract constants, removed names and files, and `import vidbyte`.
- `test_harness_threads_acceptance.py` runs the spec's example and all nine functions end to end.
- `test_harness_threads_threads.py` checks continue and fork identity and unknown threads.
- `test_harness_threads_credentials.py` checks where the API key travels and what the SDK writes.
- `test_harness_threads_records.py` checks the request, config, result and option records.
- `test_harness_threads_arguments.py` checks that bad arguments are refused before any I/O.
- `test_harness_threads_argv.py` checks the argv builder and the exact argv of each harness.
- `test_harness_threads_errors.py` checks failure classification and error detail.
- `test_harness_threads_process_bounds.py` checks timeouts, output caps, cancellation and process-tree stops.
- `test_harness_threads_launcher.py` checks launcher resolution and batch launcher refusal.
- `test_harness_threads_skills.py` checks where each harness finds the caller's skills.
- `test_harness_threads_runner.py` checks `CliRunner` and `CliInvocation`.
- `test_harness_threads_wsl.py` checks Muse WSL mode on Windows.
- `test_harness_threads_static_policy.py` checks the `ast` source rules of the harness modules.
- `test_harness_threads_helper_surface.py` checks the 47 new signatures, the summary and output records, and the new error texts.
- `test_harness_threads_grok_helpers.py` checks the Grok store scan, scopes, get, read, lineage, search and delete.
- `test_harness_threads_opencode_helpers.py` checks the opencode list, `db` lookups, export and delete.
- `test_harness_threads_muse_helpers.py` checks the Muse list, read, lineage, export and init helpers.
- `test_harness_threads_grok_commands.py` checks the Grok command lines, evidence and minted thread ids.
- `test_harness_threads_opencode_commands.py` checks the opencode `--command` and plan functions.
- `test_harness_threads_muse_commands.py` checks the Muse skill prompts and their evidence.
- `test_harness_threads_helper_arguments.py` checks that bad helper and skill arguments are refused before any I/O.
- `test_harness_threads_helper_credentials.py` checks keyless helper children, read helpers that write nothing, and key scrubbing in skill runs.
- `test_harness_threads_helper_bounds.py` checks launch failures, timeouts, output caps and cancellation for the new functions.
- `test_harness_threads_acceptance_helpers.py` runs the helpers spec's example and checks that the helpers see the run functions' threads.
- `test_harness_threads_listing_properties.py` checks the listing and lineage rules over seeded generated stores.

## Logs

- 2026-10-15 - Created for the harness thread functions (spec `docs/spec/harness-thread-functions/spec.md` r3); replaces the `grok_host`, `opencode_host`, `muse_host` and `native_backends` packs of the rejected design.
- 2026-10-15 - Added regression tests for the S4 review findings R-4, R-6 to R-11 and R-24 (`docs/spec/harness-thread-functions/review.md`).
- 2026-10-15 - Added regression tests for the re-review findings R-27 to R-30, and made the current-folder tests remove `NoDefaultCurrentDirectoryInExePath` (R-31).
- 2026-10-16 - Added the failing tests for the thread helpers and skill functions (spec `docs/spec/harness-thread-helpers-skills/spec.md` r3), the stand-in's helper paths in `fake_harness.py` and `fake_harness_helpers.py`, and the surface, errors and static-policy pins of spec §12.3 rows 35 to 38.
