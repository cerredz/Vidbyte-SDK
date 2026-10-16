# Feature: Harness thread functions

## High-Level Feature Description

Twelve async library functions run a vendor coding harness as a one-shot CLI process and return its answer and thread id: `run_`, `continue_` and `fork_` for Grok Build (`grok --single`), opencode (`opencode run --format json`), Muse Code (`muse exec --json`, natively or through `wsl.exe` on Windows) and Claude Code (`claude --print --output-format json`, prompt on stdin; spec `docs/spec/claude-thread-functions/spec.md`). They live in `vidbyte.harnesses.native`. The caller's API key, workspace, model and skill folders reach the vendor only through the child process's argv, environment and stdin, and every failure is one `NativeThreadError` with a closed failure code and a detailed message.

## Contract

Each function takes `prompt` (or `thread_id, prompt`), keyword `api_key` and `workspace`, and optional `model` (required for opencode), `skills` and a per-harness config record. It validates every argument before any I/O and refuses a bad one with `configuration.invalid_argument` naming the argument. It returns a `NativeThreadResult(harness, thread_id, text, text_truncated)`. Continue keeps the thread id; fork returns a new one; an unknown thread is `<harness>.thread_not_found` and never a silently new thread. The key travels only in the child's environment (opencode: inside `OPENCODE_CONFIG_CONTENT`), never in argv, stdin, an error, a `repr` or a log, and the SDK never changes `os.environ`. Grok runs with a private home under `~/.vidbyte/grok-homes/<key>`, opencode with `--dir` and `cwd` set to the workspace, Muse with a fresh temp config folder that is removed after the call. Claude Code runs with `cwd` set to the workspace, `--setting-sources user` and `CLAUDE_CONFIG_DIR` set to a private folder under `~/.vidbyte/claude-configs/<key>` whose only SDK-written content is `skills/`; the caller's `ANTHROPIC_*` and `CLAUDE*` variables are dropped (except `CLAUDE_CODE_GIT_BASH_PATH`), a thread id must be a lowercase UUID, continue keeps the caller's id, and Claude Code's one JSON answer is read for `is_error`, `session_id`, `result` and `api_error_status` (401 and 403 are `claude.key_rejected`). Every run is bounded by `timeout_seconds` and output caps, and on timeout or cancellation the whole process tree (and, in WSL mode, the marked in-distro processes) is stopped. Cancellation reaches the caller unchanged.

## Actors / Callers

Python callers of `vidbyte.harnesses.native`. Underneath: `CliArgv.build` and `CliRunner` in `vidbyte.lib.process`, the records in `vidbyte.lib.dataclasses.native_threads` and `vidbyte.lib.dataclasses.process`, the vocabularies in `vidbyte.lib.enums.native_threads`, and the texts and bounds in `vidbyte.lib.constants.native_threads`.

## Inputs and Preconditions

Offline only. Every vendor program is `fake_harness.py`, reached through the config records' `<harness>_command` fields or as an `.exe` (win32) or script (POSIX) stand-in placed on a PATH that holds only the sandbox's own folder. The user home (`USERPROFILE`, `HOME`) and the temp folder point into the sandbox, and every `ANTHROPIC_*`/`CLAUDE*` variable of the shell running the tests is removed (that shell may hold a real key and its own Claude Code session). No real key, network, vendor CLI or WSL distro is used; the real `claude` under `~/.local/bin` is out of reach because the home is the sandbox's.

## Observable Outcomes

What each stand-in process received (argv, cwd, stdin kind and text, credential digests, the plain variables, the skill folders it could see), the result returned, the error raised (code, attributes, message order), the files left on disk, and which processes are still alive.

## State Transitions

Threads persist in the stand-in's state folder (Grok under `GROK_HOME`, Claude Code under `CLAUDE_CONFIG_DIR/projects/<workspace>/<session>.jsonl`, as the vendors do), so a continue sees the earlier run and a fork copies it, and a Claude thread is found only through the config folder of the workspace that created it. The private Grok home and the private Claude Code config folder are created once per workspace (both through `NativePrivateFolders`) and their `skills/` folders are rebuilt only when the passed skills change. Muse's temp config folder exists only during the call.

## Invariants

The spec's INV-1 to INV-23 (`docs/spec/harness-thread-functions/spec.md` §6.1). The ones these tests pin most directly: the key path (INV-2, INV-3), argument validation before I/O (INV-4, INV-7), message parts and order (INV-5), the closed code table (INV-6), bounds and tree stop (INV-8, INV-9), stdin (INV-10), thread identity (INV-11), skill locations (INV-12, INV-13), batch refusal (INV-14), the `ast` source rules (INV-15), plain-`str` argv (INV-16), no self-update (INV-17), the workspace flags (INV-18), and a side-effect-free `import vidbyte` (INV-23). For Claude Code, `docs/spec/claude-thread-functions/spec.md` §6.1 INV-1 to INV-21: the twelve-function surface (INV-1, INV-2), the key path and dropped inherited variables (INV-3, INV-4, INV-17), argument rules including lowercase-UUID ids and the 200,000-character stdin prompt (INV-5), message parts and the newest thread id (INV-6), the JSON answer readings in order (INV-7, INV-12), bounds and cancellation (INV-9, INV-10), the private config folder (INV-13), workspace settings never loaded (INV-14), batch refusal (INV-15), the `ast` source rules (INV-16), no approve-everything mode (INV-18), and PR #1044's stack removed (INV-19).

## External Dependencies

None at test time. Windows `.exe` stand-ins use pip's distlib `t64.exe` launcher; the tests that need one skip when pip does not ship it.

## Known Failure Modes

A vendor that silently creates a new session for an unknown id (Muse `exec --session-id`, opencode `--session`), a key leaking into argv or an error message through vendor output, a batch launcher on Windows turning prompt text into `cmd.exe` commands, a grandchild holding the output pipes after a timeout, or after the vendor already exited with its answer, a Grok home or a skills folder written inside the workspace, WSL forwarding the caller's own key into a credential-less serve exchange, a program named like the vendor CLI in the current folder winning over PATH on Windows, a prompt within the character cap whose quoted command line passes the Windows limit, read-only skill files that block the next rebuild or removal, a Muse temp folder left behind by one or two cancels during its preparation, a `taskkill.exe` in the current folder replacing the system one during a tree stop, a cancel during the wait after the leader exits that leaves the tree and its reader tasks running, a prose prompt at the character cap refused by the Windows command-line check, and a shell's `NoDefaultCurrentDirectoryInExePath` that keeps the current-folder tests from ever failing. For Claude Code: `claude --resume` accepting a session title or an upper-case id, a resume from another workspace's config folder silently missing the thread, a workspace's `.claude/settings.json`, `CLAUDE.md`, skills or `.mcp.json` steering a run, a caller's `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` or Bedrock switch redirecting the key, an `is_error` answer that exits 0, and a fork that answers with its source id.

## Historical Regressions

2026-10-15: the rejected design (hosts, 43 tools, 4 toolsets, backends, stdio peers, a managed process and 53 failure codes) was replaced by these nine functions; its four test packs (`grok_host`, `opencode_host`, `muse_host`, `native_backends`) were removed with it.

2026-10-15: the S4 review (`docs/spec/harness-thread-functions/review.md`) found R-4, R-6 to R-11 and the weak cancellation proof R-24; each has a regression test here, mapped in the test plan's coverage table.

2026-10-15: the post-repair re-review found R-27 to R-31 (`review.md`); R-27 to R-30 have regression tests here, and R-31 fixed the `decoy_log` fixture so the R-4 tests can fail in any shell.

2026-10-15: PR #1044's `ClaudeHost` design (a long-lived Agent SDK host, Claude tools and a toolset) was rejected for three thread functions that mirror Grok's (`docs/spec/claude-thread-functions/spec.md`); its `tests/features/claude_host/` pack was removed, and the shared pins here (exports, enums, `FailureCode` tail, harness tables, named modules) were extended to the fourth harness.

## Test Suite Map

- `test_harness_threads_surface.py`: exports, signatures, enums, failure codes, contract constants, removed names and files, restored files, `import vidbyte`.
- `test_harness_threads_acceptance.py`: the spec's verbatim example (AC-1), all nine functions end to end (AC-2), opencode text parts, and nothing written outside the private locations (AC-17).
- `test_harness_threads_threads.py`: continue and fork identity, unknown threads, the Muse serve pre-check and fork exchange.
- `test_harness_threads_credentials.py`: where the key travels, stored logins ignored, scrubbing of vendor echoes, `repr`, stdin, cwd, self-update switches, nothing written (AC-19).
- `test_harness_threads_records.py`: config, request and result records, `CliOption`.
- `test_harness_threads_arguments.py`: every argument refusal before any I/O, and the boundary values that must pass.
- `test_harness_threads_argv.py`: `CliArgv.build`, the exact §9.2 argv per harness and verb, enum-valued flags, plain `str` elements and the invocation fields.
- `test_harness_threads_errors.py`: each INV-6 condition and its message, the error class's diagnostic packet, per-code texts.
- `test_harness_threads_process_bounds.py`: timeouts with whole-tree stop, output caps, text cap, cancellation (also during Muse's folder preparation), the vendor's stderr on timeouts and caps, a vendor exiting while a grandchild holds its pipes, the newest thread id on failures.
- `test_harness_threads_launcher.py`: PATH and Grok fallback resolution, not installed, batch launcher refusal, no program (vendor CLI, `wsl.exe` or `taskkill.exe`) from the current folder, an unpreparable private home.
- `test_harness_threads_skills.py`: the skill locations for each harness, links inside skills, and read-only skill files.
- `test_harness_threads_runner.py`: `CliRunner` and `CliInvocation` with the environment overlay, a run that ends at its leader's exit, and a cancel in the wait that follows.
- `test_harness_threads_wsl.py`: Muse WSL mode on win32.
- `test_harness_threads_static_policy.py`: INV-15's two `ast` rules and INV-20's import rule, now also over the `claude` subpackage and `hostkit/folders.py`.
- `test_harness_threads_claude_surface.py`: Claude exports and identities, `ClaudeFlag`/`ClaudePermissionMode`/`ClaudeReasoningEffort`, the §8.5 constants, the Claude rows of every table, `ClaudeThreadConfig` fields, defaults and refusals, the Claude request rules, and #1044's names, modules, files, extra and imports gone with the shared files restored (AC-18, AC-20).
- `test_harness_threads_claude_acceptance.py`: the Claude spec's verbatim example (AC-1), run returning the answer (AC-2), hostile workspace settings (AC-22), README and REPO_MAP (AC-23).
- `test_harness_threads_claude_threads.py`: continue and fork identity (AC-3, AC-4), unknown and foreign threads (AC-12, EC-7), another workspace spelling, answers on another or upper-case id, a fork answering with its source (AC-14).
- `test_harness_threads_claude_argv.py`: the exact §9.2 argv per verb and option (AC-5), each permission mode and effort, cwd, and the `CliInvocation` fields.
- `test_harness_threads_claude_credentials.py`: the child's environment (AC-6), `os.environ` untouched, an echoed key scrubbed everywhere and never written, and `repr` (AC-7).
- `test_harness_threads_claude_errors.py`: key rejected (AC-10), other API statuses and budget errors (AC-11), bare non-zero exits, unreadable answers and bad members (AC-13), stderr on success, and the thread id each failure reports.
- `test_harness_threads_claude_process_bounds.py`: timeout with tree stop, output cap (AC-15), text cap, cancellation (AC-16).
- `test_harness_threads_claude_launcher.py`: PATH and `~/.local/bin` fallback, not installed, batch refusal (AC-17), the current folder never searched, an unpreparable config folder or home (EC-3).
- `test_harness_threads_claude_arguments.py`: every argument refusal before any I/O (AC-8) and the 200,000-character and quote-dense prompts that must pass.
- `test_harness_threads_claude_skills.py`: the private config folder's `skills/` (AC-9), rebuild only on change, `NativePrivateFolders.prepare` with Grok's and Claude's constants.

Run `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads`.

## Omitted Testing Strategies

Real vendor CLIs and real keys (they spend money and need accounts; the spec's live checks cover them), network probes, a UNC workspace in WSL mode (no UNC path a non-admin test can create), timing budgets (NFR-1) and source line counts (NFR-2), and the full local gate (AC-18, run by the gate itself). See `docs/spec/harness-thread-functions/test-plan.md` for every candidate that was left out and why. For Claude Code the same holds (no real `claude`, no real Anthropic key, AC-21's full gate run by the gate), and vendor behaviour the stand-in cannot reproduce (auto memory, the 30-day transcript sweep, API retries) is left to the spec's live checks; see `docs/spec/claude-thread-functions/test-plan.md`.
