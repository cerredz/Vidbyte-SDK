# Harness thread function tests

## Folder Description / Intent

This folder tests the twelve harness thread functions of `vidbyte.harnesses.native` (`run_`, `continue_` and `fork_` for Grok Build, opencode, Muse Code and Claude Code) and the process helpers under them, entirely offline. Every vendor program is the scripted stand-in `fake_harness.py`, which logs what it received; the thread functions, `CliRunner` and the filesystem are real. `NativeThreadError.relevant_tests` points here.

## File Index

- `README.md` describes the folder and its files.
- `FEATURE.md` states the feature contract, the suite map and the strategies left out.
- `conftest.py` provides the lazy contract imports, the sandbox (home, workspace, PATH, temp folder), stand-in builders, the INV-5 error check, timing knobs and process liveness checks.
- `fake_harness.py` is the standard-library stand-in for grok, opencode, muse (exec and batch serve), claude and wsl.exe.
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
- `test_harness_threads_claude_surface.py` checks the Claude Code exports, enums, constants, `ClaudeThreadConfig`, the Claude request rules and the removal of PR #1044's host stack.
- `test_harness_threads_claude_acceptance.py` runs the Claude spec's example and checks that workspace settings, instructions, skills and MCP servers reach nothing, and the README and REPO_MAP entries.
- `test_harness_threads_claude_threads.py` checks Claude continue and fork identity and unknown or foreign threads.
- `test_harness_threads_claude_argv.py` checks the exact Claude argv per verb and option and the invocation handed to `CliRunner`.
- `test_harness_threads_claude_credentials.py` checks the Claude child's environment, scrubbing and `repr`.
- `test_harness_threads_claude_errors.py` checks the Claude JSON answer readings and their failure codes.
- `test_harness_threads_claude_process_bounds.py` checks Claude timeouts, output caps, the text cap and cancellation.
- `test_harness_threads_claude_launcher.py` checks Claude launcher resolution, batch refusal and an unpreparable config folder.
- `test_harness_threads_claude_arguments.py` checks Claude argument refusal before any I/O and the boundary values that must pass.
- `test_harness_threads_claude_skills.py` checks the private Claude config folder's `skills/` and the shared `NativePrivateFolders` helper.

## Logs

- 2026-10-15 - Created for the harness thread functions (spec `docs/spec/harness-thread-functions/spec.md` r3); replaces the `grok_host`, `opencode_host`, `muse_host` and `native_backends` packs of the rejected design.
- 2026-10-15 - Added regression tests for the S4 review findings R-4, R-6 to R-11 and R-24 (`docs/spec/harness-thread-functions/review.md`).
- 2026-10-15 - Added regression tests for the re-review findings R-27 to R-30, and made the current-folder tests remove `NoDefaultCurrentDirectoryInExePath` (R-31).
- 2026-10-15 - Added the Claude Code thread function tests (spec `docs/spec/claude-thread-functions/spec.md` r3), extended the shared pins to a fourth harness, and removed the superseded `claude_host` pack of PR #1044.
