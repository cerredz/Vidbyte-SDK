# Feature: Native Grok host

## High-Level Feature Description

A developer opens `GrokHost(GrokHostSettings(workspace=...))` with `async with` and drives xAI's Grok Build CLI (`grok`) from Python. The host can check readiness, list models and sessions, search sessions, start a live turn and get a handle back while the turn runs, continue or fork a session, run a one-shot prompt, wait for a turn, and interrupt it. Every live turn runs in its own `grok agent --no-leader ... stdio` peer, spoken to over ACP (JSON-RPC on stdio). Every read uses a short-lived peer or a CLI run. Every failure is one `NativeHostError` that carries a `FailureCode` and a non-empty `next_step`. The ten `GrokTools` expose the same functions to a model. The tools return error results instead of raising. Under the default `PermissionPolicy` only the READ tools run.

This pack also owns the tests of the plumbing shared by all three hosts, because Grok is its first user:
- the `McpStdioTransport` extension;
- the `vidbyte.lib.process` helpers;
- `RecordFieldValidator`;
- `NativeHostError`;
- the `hostkit` error factory and turn table;
- the 53 new `FailureCode` members and `NATIVE_HOST_NEXT_STEPS`;
- the 13 enums and the §9.3 constants;
- the fixed `vidbyte/harnesses/native/__init__.py` bytes;
- the fresh-interpreter imports.

## Contract

The contract is spec `docs/spec/native-grok-opencode-meta-hosts/spec.md` r3:
- §4: the developer snippet.
- §6.1: INV-1 to INV-23.
- §6.2: AC-1, AC-3, AC-4, AC-6 to AC-8, AC-11, AC-12, AC-15 to AC-20.
- §6.3.1 to §6.3.3: the code catalog, the shared rows, and the GrokHost rows EC-1 to EC-53.
- §6.3.7 and §6.3.8: EC-138 to EC-145 and EC-148 to EC-151.
- §8.5: the GrokHost, transport, process helper, error type and hostkit signatures.
- §9.1 to §9.3: the records, tools and constants.

`GrokHost` methods:
- `check_grok_ready`, `list_grok_models`, `spawn_grok_session`, `run_grok_once`;
- `continue_grok_session`, `fork_grok_session`;
- `list_grok_sessions`, `search_grok_sessions`;
- `wait_grok_turn`, `interrupt_grok_turn`;
- the module-level `run_grok_once(request, *, settings)`.

## Actors / Callers

- SDK developers using `vidbyte.harnesses.native.grok`.
- Models calling the `GrokTools` through `ToolExecutor`.
- MCP clients reaching `GrokTools.read_only(host)`.

## Inputs and Preconditions

- `GrokHostSettings`: an existing absolute workspace folder, an optional `grok_command` argv prefix, a control timeout, and the live-turn cap.
- The request records `GrokTurnRequest` and `GrokOneShotRequest`.
- The tests never run the real `grok`. Every host gets `grok_command=(sys.executable, "-u", "fake_grok_peer.py", <scenario.json>)`, which is the §13 seam. The AC-1 snippet runs with PATH and HOME pointed at temporary folders, which hold either a shim for the fake or nothing at all.

## Observable Outcomes

- The returned records: `GrokReadiness`, `GrokModelCatalog`, `GrokSessionPage`, `GrokSessionSearch`, `GrokOneShotResult`, `NativeTurnHandle`, `NativeTurnResult` and `NativeInterruptResult`.
- `NativeHostError.failure_code`, `next_step`, `operation` and `context`.
- `ToolResult` status, output and metadata.
- What the fake logged: every argv, the selected environment keys, every frame it received or sent, its permission answers, and the pids of itself and its grandchild.
- Elapsed time against an upper bound.
- On POSIX, process liveness from `/proc`.

## State Transitions

A host is created, entered once, used, and exited. A second `__aenter__` raises `configuration.invalid_argument`. Using a host before it is entered or after it exits raises `grok.process_exited`.

A turn is `RUNNING` and then reaches exactly one of `COMPLETED`, `INTERRUPTED` or `FAILED`. A `FAILED` turn raises its recorded error on every wait. A finished turn is kept in a table of the last 64.

A peer stops in this order:
1. `session/cancel`, when a turn is live.
2. stdin EOF.
3. Up to `NATIVE_STOP_GRACE_SECONDS` for the peer to exit by itself.
4. A whole-tree stop.
5. Reaping.

## Invariants

- INV-1 and INV-2: only `NativeHostError`, `ConfigurationError` (while a record is built) and `CancelledError` escape. Cancellation is never swallowed.
- INV-3 and INV-4, NFR-2: every wait is bounded, and every process is reaped on every path.
- INV-5: inputs are checked before any process starts. The model and effort are checked live before `session/new`.
- INV-6 and INV-9: no secret and no approve-everything value appears in argv, on the wire, or in an error.
- INV-11 to INV-17: the handle comes back while the turn runs, a wait never changes the turn, the terminal state is set once, there is one live turn per session, unknown usage is `None`, memory is bounded, and handles are scoped to their host.
- INV-18 to INV-22: the transport is unchanged at its defaults, the `native/__init__.py` bytes are fixed, existing `FailureCode` members are unchanged, and `import vidbyte` starts nothing.

## External Dependencies

- Python 3.11 subprocesses (`sys.executable`).
- `/proc` on Linux for liveness checks.
- `cmd.exe` and `taskkill` on Windows, from System32.
- No network, no vendor SDK and no credentials.

## Known Failure Modes

These are the failure inventory the tests were chosen from, given as input → wrong output.

- **Escaping exceptions:** a launch `OSError`, an `McpProtocolError`, a `KeyError` on a missing result member, or a JSON decode error escapes raw instead of becoming its row code (EC-5, EC-11 to EC-16).
- **Hangs:**
  - a silent `initialize` or `session/list` never times out (EC-13, AC-3);
  - a peer that ignores EOF and TERM is never killed (EC-10);
  - a grandchild holding a pipe blocks the close;
  - a CLI run never stops at `max_turn_seconds` (EC-38).
- **Leaks:**
  - a cancelled spawn, continue, check or list leaves its peer running (AC-4, EC-4);
  - a short-lived peer outlives its read;
  - `__aexit__` leaves turns running (EC-8);
  - a turn's grandchild survives the turn (EC-10);
  - the host closes while a spawn or continue is starting, after `session/prompt` was written, and the dropped answer future fails when the peer closes, so asyncio logs "Future exception was never retrieved" (R-24; EC-2, EC-8).
- **Silent wrong model:** Grok falls back to its default for an unknown `--model`, so a turn runs on the wrong model unless `currentModelId` is checked before `session/new` (EC-25, AC-7). An unoffered reasoning effort is accepted silently (EC-26).
- **Over-permissive approvals:**
  - an `*_always` option is chosen (AC-8);
  - a permission with no reject option is allowed;
  - an unknown server request goes unanswered and the turn hangs (INV-10);
  - an approve-everything flag reaches argv (INV-9, T-2).
- **Argv injection:**
  - a prompt that looks like a flag (`--always-approve`) becomes its own argv element;
  - a model id starting with `-` reaches argv (EC-23, T-2).
- **Wait semantics:**
  - a timed-out or cancelled wait cancels the turn (INV-12);
  - a second interrupt raises (AC-12);
  - a failed turn returns different errors on later waits (EC-148);
  - a handle from another host is accepted (INV-17).
- **Wrong session:** a missing session or one from another folder is resumed (EC-31). A fork spends money on a session that does not exist (EC-35), or forks onto an existing id (EC-36).
- **Concurrency:** two continues on one session both pass the busy check (EC-9). A failed spawn keeps its reserved slot. A spawn binds an upper-case id from Grok's `session/new`, and a continue or fork by the handle's own id then misses the busy check, so a second turn starts or a paid fork runs on a live session (INV-14).
- **Interrupt racing Grok's answer (RACE-1):** Grok answers `end_turn` while `session/cancel` is still being written, the driver closes the peer, and `interrupt_grok_turn` raises `grok.process_exited` for a cancel it sent to a running turn (INV-13, EC-53). Or Grok has answered and the driver is still closing the peer, and the interrupt reports `was_running=True` for a finished turn (EC-52).
- **Secret leaks:** a credential the agent writes into a permission's tool-call title is recorded verbatim in `NativeApprovalDecision.title` and reaches `wait_grok_turn`'s output (§9.1, INV-6).
- **Memory:** turn text, decisions or tool output are not capped (EC-150, INV-16, EC-143). A tool output is cut inside a UTF-8 character.
- **Vocabulary drift:**
  - a next step's text differs from §6.3.1;
  - a new member is inserted in the wrong place or renames an existing one (INV-20);
  - a record accepts a bool as a number or a bare string as an enum (EC-23, EC-33).
- **Transport regressions:**
  - a server request with an `id` resolves a pending request of the same id (the dispatch fix);
  - an exception in the callback kills the reader;
  - the per-call timeout is ignored;
  - the default MCP path changes (INV-18).
- **Import cycles:** importing a host, the toolsets or `vidbyte.agents` first fails (AC-20). `import vidbyte` starts a process or loads a vendor SDK (AC-18).

## Historical Regressions

- **r8 (S4 review R-1): a no-cursor `-32602` was a protocol mismatch.** `GrokWire` mapped every `-32602` answer sent without a cursor to `grok.protocol_mismatch` and dropped `vendor_error`, but EC-16 requires `grok.api_error` (only EC-41's non-null cursor is `configuration.invalid_argument`). Caught by the `EC-16 … minus-32602-no-cursor` rows for `spawn_grok_session` and `list_grok_sessions` in `test_grok_host_errors.py` and by `test_invalid_params_without_a_cursor_is_an_api_error_carrying_the_vendor_message`.
- **r8 (S4 review R-2): a win32 batch Grok launcher ran the argv through `cmd.exe`.** A `grok.cmd` on PATH, or an explicit `.cmd`/`.bat` `grok_command`, was started, so a prompt, model id or rule could run as a command. EC-157 refuses it at `__aenter__`. Caught by `test_grok_host_windows_launcher.py` (win32-only).
- **r8 (S4 review R-8 / S4-6): the busy check and fork listing checks compared session ids case-sensitively.** INV-14 says Grok ids compare ignoring letter case. Caught by `test_grok_host_session_id_case.py` (continue busy on the upper-cased id, fork on an upper-cased source, and an upper-cased `new_session_id` that collides with an existing id). EC-39's target comparison was already case-insensitive, so its two cases are locks.
- **Re-review round 1 (R-16): the busy check missed a vendor-chosen upper-case id.** Spawn bound the id from `session/new` verbatim, but continue and fork lower-cased their argument and the turn table compared exactly, so a continue or fork by the handle's own `session_id` (or its lower-cased form) started a second live turn or ran the fork CLI. Caught by `test_continue_on_a_live_session_whose_vendor_id_is_upper_case_is_busy` and `test_fork_of_a_live_session_whose_vendor_id_is_upper_case_is_busy` in `test_grok_host_session_id_case.py`.
- **Re-review round 1 (R-17): approval titles were recorded unscrubbed.** §9.1 says `NativeApprovalDecision.title` is scrubbed; the Grok driver recorded the tool-call title verbatim, so a credential in it reached the result and `wait_grok_turn`'s output. Caught by `test_a_credential_in_a_permission_title_is_scrubbed_from_the_result_and_the_wait_tool` in `test_grok_host_turns.py`.
- **RACE-1 (R-19): a cancel write that lost the race to Grok's answer raised `grok.process_exited`.** On CPython 3.11 the cancel's drain yields once; if the `session/prompt` answer is handled in that yield, the driver closes the peer and the post-drain check turns a write that reached Grok into `BrokenPipeError`. Caught by `test_interrupt_whose_cancel_write_loses_to_the_turn_end_succeeds` in `test_grok_host_turns.py`, which forces the window with the delegating `cancel_drain_gate` seam. EC-51's POSIX test still guards a peer that exited before answering.
- **RACE-1 (R-20): an interrupt during the driver's close reported `was_running=True`.** Grok had answered, so nothing was sent, but the host still saw a live task. Caught by `test_interrupt_after_grok_answered_while_the_driver_is_still_closing_sends_nothing` in `test_grok_host_turns.py`.
- **Post-S6 (R-24): a host closed during spawn left an unretrieved future.** `_launch` wrote `session/prompt`, saw the host closed and raised `grok.process_exited` before any driver started, so nothing read the answer future that the peer close then failed. Caught by `test_host_closed_during_spawn_leaves_no_unretrieved_future` in `test_grok_host_turns.py`, which also requires the spawn to keep raising `grok.process_exited`.

## Test Suite Map

- `test_grok_host_acceptance.py`: the §4 snippet as written (both outcomes), spawn with a held turn, wait timeout then result, double interrupt, and the module-level `run_grok_once`.
- `test_grok_host_errors.py`: the table-driven error rows for every (function, code), in host mode and tool mode. It also covers the unopened or closed host, re-entry, invalid primitive arguments, the PATH lookup, and the no-cursor `-32602` api_error (r8, R-1).
- `test_grok_host_session_id_case.py`: INV-14 case-insensitivity (r8, R-8): a continue busy on the upper-cased id, a fork on an upper-cased source, an upper-cased `new_session_id` that collides, and the two EC-39 locks. Re-review R-16: a continue or fork by the handle's id, or its lower-cased form, after Grok returned an upper-case id is busy.
- `test_grok_host_windows_launcher.py`: EC-157 (r8, R-2, win32-only): a `grok.cmd` on PATH and an explicit `.cmd`/`.bat` `grok_command` are refused at `__aenter__` and never run.
- `test_grok_host_turns.py`: approvals and decisions (with a credential in the title scrubbed, re-review R-17), stop reasons, interrupt and ceiling, an interrupt racing Grok's own answer (RACE-1: R-19, R-20), a host closed during spawn (R-24), unknown notifications, the text cap, unknown usage, repeated failure, handle scoping, concurrency, wire shapes and peer argv, and a peer that exits mid-write.
- `test_grok_host_reads.py`: readiness, catalog, pages and cursors, casefolded search and its page cap, one-shot and fork results and argv, live model checks, text capping, garbage frames, and the child environment.
- `test_grok_host_process_bounds.py`: the AC-3 bound with shrunk and default timings, cancellation of each call, cancelled waits, `__aexit__` with live turns or on error or cancellation, grandchild reaping, and the one-shot tree stop.
- `test_grok_host_records.py`: `RecordFieldValidator`, the shared native records, the Grok settings and request records (EC-23, EC-33), and frozen slotted dataclasses.
- `test_grok_host_tools.py`: the toolset table, `read_only`, AC-15, and EC-138 to EC-145.
- `test_grok_host_shared_contract.py`: the code catalog, `NativeHostError`, `NativeErrorFactory`, `NativeTurnTable`, enums, constants, INV-19, AC-18 and AC-20.
- `test_grok_host_process_helpers.py`: `CliRunner`, `ManagedProcess`, `ProcessStopper` and `CliInvocation`.
- `test_grok_transport_extension.py`: the `McpStdioTransport` additions and the dispatch fix.

Run everything with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host`.

## Omitted Testing Strategies

- **Live Grok runs.** The spec forbids live prompts. Every vendor fact comes from the §6.3 rows that quote the S1 probes.
- **EC-4's "cancelled after the prompt was written but before the handle returned" window.** It cannot be hit deterministically. The cancel tests cover the windows before the prompt and during the wait.
- **NFR-7 latency targets.** These depend on the machine. Only upper bounds with slack are asserted.
- **Windows process liveness.** There is no portable check (§13). Windows asserts time bounds and outcomes only.
- **The second EC-21 trigger (a sign-in marker on `grok models` stderr).** It re-proves the same code and token as the stdout line.
- **The `max_turn_seconds` default of 240 on the one-shot tools.** Observing it would mean waiting 240 seconds or mocking the host. The cap itself (EC-144) is tested.
