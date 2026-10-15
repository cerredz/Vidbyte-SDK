# Harness thread function tests

## Folder Description / Intent

This folder tests the nine harness thread functions of `vidbyte.harnesses.native` (`run_`, `continue_` and `fork_` for Grok Build, opencode and Muse Code) and the process helpers under them, entirely offline. Every vendor program is the scripted stand-in `fake_harness.py`, which logs what it received; the thread functions, `CliRunner` and the filesystem are real. `NativeThreadError.relevant_tests` points here.

## File Index

- `README.md` describes the folder and its files.
- `FEATURE.md` states the feature contract, the suite map and the strategies left out.
- `conftest.py` provides the lazy contract imports, the sandbox (home, workspace, PATH, temp folder), stand-in builders, the INV-5 error check, timing knobs and process liveness checks.
- `fake_harness.py` is the standard-library stand-in for grok, opencode, muse (exec and batch serve) and wsl.exe.
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

## Logs

- 2026-10-15 - Created for the harness thread functions (spec `docs/spec/harness-thread-functions/spec.md` r3); replaces the `grok_host`, `opencode_host`, `muse_host` and `native_backends` packs of the rejected design.
