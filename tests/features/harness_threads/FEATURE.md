# Feature: Harness thread functions, thread helpers and skill functions

## High-Level Feature Description

Nine async library functions run a vendor coding harness as a one-shot CLI process and return its answer and thread id: `run_`, `continue_` and `fork_` for Grok Build (`grok --single`), opencode (`opencode run --format json`) and Muse Code (`muse exec --json`, natively or through `wsl.exe` on Windows). They live in `vidbyte.harnesses.native`. The caller's API key, workspace, model and skill folders reach the vendor only through the child process's argv, environment and stdin, and every failure is one `NativeThreadError` with a closed failure code and a detailed message.

On top of those nine, 47 more async functions (spec `docs/spec/harness-thread-helpers-skills/spec.md`) list, get, read, trace, search and delete the threads each vendor keeps, and run the vendors' built-in commands and skills with proof that they ran. The 22 keyless thread helpers return `NativeThreadSummary` records (or a whole transcript, or `None` after a delete): Grok reads its own store (`<home>/sessions/<url-encoded cwd>/<id>/summary.json`) in the private home of the workspace (`GrokThreadScope.SDK`) or in `~/.grok` (`USER`) and runs `grok export` / `grok sessions delete`; opencode runs `session list`, `db`, `export` and `session delete`; Muse runs batch `muse serve` (`session/list`, `session/read`) and `muse export`. The 25 command and skill functions (`run_grok_command` and 13 named Grok wrappers, `run_opencode_command` and 3 wrappers, `run_muse_skill` and 5 wrappers, and the keyless `init_muse_workspace`) launch like the nine run functions and return only when the run's own record shows the command ran (Grok streaming tool calls, the new thread's `agent_name`, or its export transcript; Muse `session/read` items, or the export transcript after compaction; opencode's own refusal of an unknown command), otherwise `<harness>.command_not_run` with the new thread's id.

## Contract

Each function takes `prompt` (or `thread_id, prompt`), keyword `api_key` and `workspace`, and optional `model` (required for opencode), `skills` and a per-harness config record. It validates every argument before any I/O and refuses a bad one with `configuration.invalid_argument` naming the argument. It returns a `NativeThreadResult(harness, thread_id, text, text_truncated)`. Continue keeps the thread id; fork returns a new one; an unknown thread is `<harness>.thread_not_found` and never a silently new thread. The key travels only in the child's environment (opencode: inside `OPENCODE_CONFIG_CONTENT`), never in argv, stdin, an error, a `repr` or a log, and the SDK never changes `os.environ`. Grok runs with a private home under `~/.vidbyte/grok-homes/<key>`, opencode with `--dir` and `cwd` set to the workspace, Muse with a fresh temp config folder that is removed after the call. Every run is bounded by `timeout_seconds` and output caps, and on timeout or cancellation the whole process tree (and, in WSL mode, the marked in-distro processes) is stopped. Cancellation reaches the caller unchanged.

Helpers validate every argument before any file is read or any process starts, and refuse with `configuration.invalid_argument` naming the public parameter. Lists come back newest `updated_at` first, ties by `thread_id` descending, each id once, at most `limit`, and only `updated_at >= now - since`; the `recent` and `since` wrappers return exactly what the base list returns. Lineage is root first, linked, and ends at a missing parent; a cycle or a chain past `NATIVE_LINEAGE_MAX_DEPTH` is `protocol_mismatch`. Vendor data the SDK cannot read is `protocol_mismatch` naming the member (and the `summary.json` path), never a skipped thread or a partial list, except a folder with no `summary.json` yet (bounded by `GROK_SUMMARY_GRACE_SECONDS`), a folder removed mid-scan, and the non-session files of a real Grok store. Operations on one id read only that id's file. Helper children carry no key, run with self-update off and within `NATIVE_CONTROL_TIMEOUT_SECONDS`, and read helpers write nothing (never a Grok home). A Grok command run mints its `--session-id`, so every post-launch error names the thread it paid for.

## Actors / Callers

Python callers of `vidbyte.harnesses.native`. Underneath: `CliArgv.build` and `CliRunner` in `vidbyte.lib.process`, the records in `vidbyte.lib.dataclasses.native_threads` and `vidbyte.lib.dataclasses.process`, the vocabularies in `vidbyte.lib.enums.native_threads`, and the texts and bounds in `vidbyte.lib.constants.native_threads`.

## Inputs and Preconditions

Offline only. Every vendor program is `fake_harness.py`, reached through the config records' `<harness>_command` fields or as an `.exe` (win32) or script (POSIX) stand-in placed on a PATH that holds only the sandbox's own folder. The user home (`USERPROFILE`, `HOME`) and the temp folder point into the sandbox. No real key, network, vendor CLI or WSL distro is used. Vendor stores are seeded as real files in the vendor's layout (`Stores` in `conftest.py`): Grok `summary.json` files under the sandbox home, opencode rows in a SQLite file with opencode's `session` columns, and Muse session metadata with MSP items. Timestamps are fixed aware datetimes, or whole-hour offsets from the current time where a `since` window needs one (the helpers read the clock once per call, spec §13).

## Observable Outcomes

What each stand-in process received (argv, cwd, stdin kind and text, credential digests, the plain variables, the skill folders it could see, the SQL an `opencode db` child got, the serve frames), the result returned (summaries compared field by field), the error raised (code, attributes, message order), the files left on disk, and which processes are still alive.

## State Transitions

Threads persist in the stand-in's state folder (Grok under `GROK_HOME` in Grok's real layout, opencode in a SQLite `session` table, Muse as MSP session metadata), so a continue sees the earlier run, a fork copies it (opencode forks record no parent; Grok and Muse forks do), and every helper sees what a run wrote. The private Grok home is created once per workspace and its `skills/` folder is rebuilt only when the passed skills change. Muse's temp config folder exists only during the call.

## Invariants

The spec's INV-1 to INV-23 (`docs/spec/harness-thread-functions/spec.md` §6.1). The ones these tests pin most directly: the key path (INV-2, INV-3), argument validation before I/O (INV-4, INV-7), message parts and order (INV-5), the closed code table (INV-6), bounds and tree stop (INV-8, INV-9), stdin (INV-10), thread identity (INV-11), skill locations (INV-12, INV-13), batch refusal (INV-14), the `ast` source rules (INV-15), plain-`str` argv (INV-16), no self-update (INV-17), the workspace flags (INV-18), and a side-effect-free `import vidbyte` (INV-23).

The helpers spec's INV-1 to INV-29 (`docs/spec/harness-thread-helpers-skills/spec.md` §6.1), pinned most directly: the 68-name surface (INV-1), keyless helpers (INV-2), validation first (INV-3), read helpers write nothing (INV-4), one `NativeThreadError` per failure (INV-5), strict vendor reads with the D-27 scope (INV-6), the list order, window, limit and wrapper equivalence (INV-7), evidence from the run's own record (INV-8), no caller value as a flag (INV-9), lineage (INV-10), exact delete (INV-11), SDK scope equals the run home (INV-13), cancellation (INV-14), bounds (INV-16), self-update off (INV-17), whole transcripts (INV-21), the 148 + 4 failure codes (INV-22), the private Muse config for helper children (INV-23), the key path of skill runs (INV-24) and the minted Grok session id (INV-29).

## External Dependencies

None at test time. Windows `.exe` stand-ins use pip's distlib `t64.exe` launcher; the tests that need one skip when pip does not ship it.

## Known Failure Modes

A vendor that silently creates a new session for an unknown id (Muse `exec --session-id`, opencode `--session`), a key leaking into argv or an error message through vendor output, a batch launcher on Windows turning prompt text into `cmd.exe` commands, a grandchild holding the output pipes after a timeout, or after the vendor already exited with its answer, a Grok home or a skills folder written inside the workspace, WSL forwarding the caller's own key into a credential-less serve exchange, a program named like the vendor CLI in the current folder winning over PATH on Windows, a prompt within the character cap whose quoted command line passes the Windows limit, read-only skill files that block the next rebuild or removal, a Muse temp folder left behind by one or two cancels during its preparation, a `taskkill.exe` in the current folder replacing the system one during a tree stop, a cancel during the wait after the leader exits that leaves the tree and its reader tasks running, a prose prompt at the character cap refused by the Windows command-line check, and a shell's `NoDefaultCurrentDirectoryInExePath` that keeps the current-folder tests from ever failing.

For the helpers and skill functions: a listing that trusts the vendor's order (Muse ties come back ascending), keeps a duplicated id twice, keeps an out-of-window thread or cuts before the window; a `recent` or `since` wrapper that drifts from the base list; a lineage that is leaf first, loops forever on a cycle, or fails on a deleted parent; a Grok scan that treats `session_search.sqlite` as a group, skips a corrupt `summary.json` silently, reads a multi-GB file, turns a renamed `summary.json` into a silent `()`, or fails an operation on one id because of a sibling's corrupt file; a read path that creates `~/.vidbyte/grok-homes/<key>`; USER scope that reads `GROK_HOME` or another workspace's group; a delete that trusts exit 0 while the folder stays; opencode lists capped at 100 rows, chosen by an inherited `PWD`, missing subagent children, or quietly cut at the scan cap; a Muse export that writes into the workspace or reads a decoy file named like the id; a skill run reported as success when the slash command went out as text, the skill was shadowed, the history was compacted or unreadable, or `end.sessionId` names another thread; a paid Grok run whose timeout or overflow loses its thread id; caller text that sets a slash-command option (`--budget`, `--effort`, a design doc with a space) or clears a goal; and a key reaching a helper child, an argv element, a file or an error.

## Historical Regressions

2026-10-15: the rejected design (hosts, 43 tools, 4 toolsets, backends, stdio peers, a managed process and 53 failure codes) was replaced by these nine functions; its four test packs (`grok_host`, `opencode_host`, `muse_host`, `native_backends`) were removed with it.

2026-10-15: the S4 review (`docs/spec/harness-thread-functions/review.md`) found R-4, R-6 to R-11 and the weak cancellation proof R-24; each has a regression test here, mapped in the test plan's coverage table.

2026-10-15: the post-repair re-review found R-27 to R-31 (`review.md`); R-27 to R-30 have regression tests here, and R-31 fixed the `decoy_log` fixture so the R-4 tests can fail in any shell.

2026-10-15: the thread helpers and skill functions (`docs/spec/harness-thread-helpers-skills/spec.md` r3) were added with failing tests first (S2). The Grok stand-in now keeps Grok's real store layout instead of a hashed `<id>.json` file, the Muse fork reply carries `forkedFrom` as an object (MSP `ForkProvenance`), and the stale `120` pin in the surface test became a post-merge invariant.

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
- `test_harness_threads_static_policy.py`: INV-15's two `ast` rules and INV-20's import rule, over the 14 + 10 named modules.
- `test_harness_threads_helper_surface.py`: the 47 signatures and defaults, keyless helpers, the operation members, the §9.3 tables, the `NativeThreadSummary` and `NativeCommandOutput` records, `to_utc_datetime`, the new error texts (AC-20) and the untouched root `__all__` lists.
- `test_harness_threads_grok_helpers.py`: the Grok store scan, both scopes, get, read, lineage, search, delete, strict reads, the non-session files and the layout bound (AC-2 to AC-9, AC-19, AC-27, AC-28).
- `test_harness_threads_opencode_helpers.py`: `session list` with `--max-count` and the directory filter, `db` lookups by id with subagent chains, export, delete, empty and malformed output (AC-2 to AC-8, AC-31, AC-32).
- `test_harness_threads_muse_helpers.py`: `session/list` and `session/read` over batch serve, the export child in an empty temp folder, `init_muse_workspace`, the private config (AC-2 to AC-6, AC-18, AC-19, INV-23).
- `test_harness_threads_grok_commands.py`: the §9.2 slash lines, `--session-id`, `GROK_WORKFLOWS`, evidence, agents, the code-review export, the minted id on every failure, `skills=` shadowing (AC-13 to AC-15, AC-29, AC-30, AC-33).
- `test_harness_threads_opencode_commands.py`: `--command`, stdin, the plan agent and `command_not_run` (AC-16).
- `test_harness_threads_muse_commands.py`: the skill prompt, items evidence, history modes and the export fallback after compaction (AC-17, AC-34).
- `test_harness_threads_helper_arguments.py`: every refusal before any I/O, naming the public parameter, and the texts that must pass (AC-12).
- `test_harness_threads_helper_credentials.py`: keyless helper children, nothing written by read helpers, the echoed key in skill runs (AC-10, AC-11, AC-24).
- `test_harness_threads_helper_bounds.py`: not installed, batch launchers, timeouts, output caps, run failures and cancellation for helpers and skill runs (AC-23, AC-25).
- `test_harness_threads_acceptance_helpers.py`: the helpers spec's §4 example (AC-1), and the nine run functions' threads seen by the helpers (INV-13).
- `test_harness_threads_listing_properties.py`: seeded, deterministic property checks of INV-7 and INV-10 over generated Grok stores, and the wrapper equivalence.

Run `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads`.

## Omitted Testing Strategies

Real vendor CLIs and real keys (they spend money and need accounts; the spec's live checks cover them), network probes, a UNC workspace in WSL mode (no UNC path a non-admin test can create), timing budgets (NFR-1) and source line counts (NFR-2), and the full local gate (AC-18, run by the gate itself). See `docs/spec/harness-thread-functions/test-plan.md` for every candidate that was left out and why.

For the helpers and skill functions: the README and REPO_MAP text of AC-26 (proven by review), the full local gate of AC-22 (run by the gate), timing of a 10,000-thread Grok store (EC-64, NFR-12; the opencode scan cap is tested at its exact value instead), vendor behaviour that only a key-bearing probe can show (A-7, A-25, A-27, A-28: the stand-ins encode the documented behaviour, and the spec's manual probe owns the rest), EC-24 (a delete racing a continue is vendor-owned), and generated stores through Hypothesis (not installed in this environment; the property file uses seeded loops instead). See `docs/spec/harness-thread-helpers-skills/test-plan.md`.
