# Feature: Harness thread functions

## High-Level Feature Description

Nine async library functions run a vendor coding harness as a one-shot CLI process and return its answer and thread id: `run_`, `continue_` and `fork_` for Grok Build (`grok --single`), opencode (`opencode run --format json`) and Muse Code (`muse exec --json`, natively or through `wsl.exe` on Windows). They live in `vidbyte.harnesses.native`. The caller's API key, workspace, model and skill folders reach the vendor only through the child process's argv, environment and stdin, and every failure is one `NativeThreadError` with a closed failure code and a detailed message.

## Contract

Each function takes `prompt` (or `thread_id, prompt`), keyword `api_key` and `workspace`, and optional `model` (required for opencode), `skills` and a per-harness config record. It validates every argument before any I/O and refuses a bad one with `configuration.invalid_argument` naming the argument. It returns a `NativeThreadResult(harness, thread_id, text, text_truncated)`. Continue keeps the thread id; fork returns a new one; an unknown thread is `<harness>.thread_not_found` and never a silently new thread. The key travels only in the child's environment (opencode: inside `OPENCODE_CONFIG_CONTENT`), never in argv, stdin, an error, a `repr` or a log, and the SDK never changes `os.environ`. Grok runs with a private home under `~/.vidbyte/grok-homes/<key>`, opencode with `--dir` and `cwd` set to the workspace, Muse with a fresh temp config folder that is removed after the call. Every run is bounded by `timeout_seconds` and output caps, and on timeout or cancellation the whole process tree (and, in WSL mode, the marked in-distro processes) is stopped. Cancellation reaches the caller unchanged.

## Actors / Callers

Python callers of `vidbyte.harnesses.native`. Underneath: `CliArgv.build` and `CliRunner` in `vidbyte.lib.process`, the records in `vidbyte.lib.dataclasses.native_threads` and `vidbyte.lib.dataclasses.process`, the vocabularies in `vidbyte.lib.enums.native_threads`, and the texts and bounds in `vidbyte.lib.constants.native_threads`.

## Inputs and Preconditions

Offline only. Every vendor program is `fake_harness.py`, reached through the config records' `<harness>_command` fields or as an `.exe` (win32) or script (POSIX) stand-in placed on a PATH that holds only the sandbox's own folder. The user home (`USERPROFILE`, `HOME`) and the temp folder point into the sandbox. No real key, network, vendor CLI or WSL distro is used.

## Observable Outcomes

What each stand-in process received (argv, cwd, stdin kind and text, credential digests, the plain variables, the skill folders it could see), the result returned, the error raised (code, attributes, message order), the files left on disk, and which processes are still alive.

## State Transitions

Threads persist in the stand-in's state folder (Grok under `GROK_HOME`, as Grok does), so a continue sees the earlier run and a fork copies it. The private Grok home is created once per workspace and its `skills/` folder is rebuilt only when the passed skills change. Muse's temp config folder exists only during the call.

## Invariants

The spec's INV-1 to INV-23 (`docs/spec/harness-thread-functions/spec.md` §6.1). The ones these tests pin most directly: the key path (INV-2, INV-3), argument validation before I/O (INV-4, INV-7), message parts and order (INV-5), the closed code table (INV-6), bounds and tree stop (INV-8, INV-9), stdin (INV-10), thread identity (INV-11), skill locations (INV-12, INV-13), batch refusal (INV-14), the `ast` source rules (INV-15), plain-`str` argv (INV-16), no self-update (INV-17), the workspace flags (INV-18), and a side-effect-free `import vidbyte` (INV-23).

## External Dependencies

None at test time. Windows `.exe` stand-ins use pip's distlib `t64.exe` launcher; the tests that need one skip when pip does not ship it.

## Known Failure Modes

A vendor that silently creates a new session for an unknown id (Muse `exec --session-id`, opencode `--session`), a key leaking into argv or an error message through vendor output, a batch launcher on Windows turning prompt text into `cmd.exe` commands, a grandchild holding the output pipes after a timeout, a Grok home or a skills folder written inside the workspace, and WSL forwarding the caller's own key into a credential-less serve exchange.

## Historical Regressions

2026-10-15: the rejected design (hosts, 43 tools, 4 toolsets, backends, stdio peers, a managed process and 53 failure codes) was replaced by these nine functions; its four test packs (`grok_host`, `opencode_host`, `muse_host`, `native_backends`) were removed with it.

## Test Suite Map

- `test_harness_threads_surface.py`: exports, signatures, enums, failure codes, contract constants, removed names and files, restored files, `import vidbyte`.
- `test_harness_threads_acceptance.py`: the spec's verbatim example (AC-1), all nine functions end to end (AC-2), opencode text parts, and nothing written outside the private locations (AC-17).
- `test_harness_threads_threads.py`: continue and fork identity, unknown threads, the Muse serve pre-check and fork exchange.
- `test_harness_threads_credentials.py`: where the key travels, stored logins ignored, scrubbing of vendor echoes, `repr`, stdin, cwd, self-update switches, nothing written (AC-19).
- `test_harness_threads_records.py`: config, request and result records, `CliOption`.
- `test_harness_threads_arguments.py`: every argument refusal before any I/O, and the boundary values that must pass.
- `test_harness_threads_argv.py`: `CliArgv.build`, the exact §9.2 argv per harness and verb, enum-valued flags, plain `str` elements and the invocation fields.
- `test_harness_threads_errors.py`: each INV-6 condition and its message, the error class's diagnostic packet, per-code texts.
- `test_harness_threads_process_bounds.py`: timeouts with whole-tree stop, output caps, text cap, cancellation, the newest thread id on failures.
- `test_harness_threads_launcher.py`: PATH and Grok fallback resolution, not installed, batch launcher refusal, an unpreparable private home.
- `test_harness_threads_skills.py`: the skill locations for each harness and links inside skills.
- `test_harness_threads_runner.py`: `CliRunner` and `CliInvocation` with the environment overlay.
- `test_harness_threads_wsl.py`: Muse WSL mode on win32.
- `test_harness_threads_static_policy.py`: INV-15's two `ast` rules and INV-20's import rule.

Run `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads`.

## Omitted Testing Strategies

Real vendor CLIs and real keys (they spend money and need accounts; the spec's live checks cover them), network probes, a UNC workspace in WSL mode (no UNC path a non-admin test can create), timing budgets (NFR-1) and source line counts (NFR-2), and the full local gate (AC-18, run by the gate itself). See `docs/spec/harness-thread-functions/test-plan.md` for every candidate that was left out and why.
