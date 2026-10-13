# Feature: Native Muse host

## High-Level Feature Description

A developer opens `MuseHost(MuseHostSettings(workspace=...))` with `async with` and drives Meta's Muse Code CLI (`muse`) from Python over MSP 1.0.1, which is JSON-RPC on stdio. The host can:
- check readiness and list models;
- start a live turn and get a handle back while the turn runs;
- continue a session or fork one;
- list, read and page sessions;
- steer, wait for or interrupt a turn;
- track a session's token usage.

Every live turn runs in its own `muse serve` peer. Every read runs in a short-lived peer. On Windows the peer is launched as `wsl.exe -d <distro> -e <muse_path> serve`. That WSL peer carries a random `VIDBYTE_PEER_MARK`, which is forwarded through `WSLENV`. After a turn peer closes, the host runs an in-distro reap that kills every process carrying the mark. Every failure is one `NativeHostError` that carries a `FailureCode` and a non-empty `next_step`. The twelve `MuseTools` expose the same functions to a model. Under the default `PermissionPolicy` only the seven READ tools run.

## Contract

The contract is spec `docs/spec/native-grok-opencode-meta-hosts/spec.md` r3:
- §6.1: INV-1 to INV-17, as they apply to Muse.
- §6.2: AC-2, AC-3, AC-4, AC-6, AC-7, AC-10, AC-11 and AC-12 for Muse, plus the Muse part of AC-15 and AC-19.
- §6.3.2: the shared rows EC-1 to EC-10.
- §6.3.5: the MuseHost rows EC-94 to EC-121 and EC-156.
- §6.3.7 and §6.3.8: EC-144, EC-145, EC-148 and EC-150.
- §8.1: D-9 to D-14, D-19 and D-23.
- §8.5: the MuseHost signatures, `MusePathTranslator`, the MSP calls, `MuseWire.new_command_id()`, and how `MuseTurnDriver` builds the result.
- §9.1: the 15 Muse records.
- §9.2: rows 29 to 40, the Muse tools.
- §9.3: the `MUSE_*` constants, `WSLENV`, `META_API_KEY` and `VIDBYTE_PEER_MARK`.
- §13: the test seams.

The shared plumbing belongs to the `grok_host` pack, which proves it once:
- the code catalog;
- `NativeHostError`, `NativeErrorFactory`, `NativeTurnTable` and `RecordFieldValidator`;
- the process helpers;
- the transport extension;
- EC-138 to EC-143.

## Actors / Callers

- SDK developers using `vidbyte.harnesses.native.muse`.
- Models calling the `MuseTools` through `ToolExecutor`.
- MCP clients reaching `MuseTools.read_only(host)`.

## Inputs and Preconditions

- `MuseHostSettings`:
  - an existing absolute workspace folder;
  - either `wsl_distro` (Windows) or `muse_command` (an argv prefix), never both;
  - `muse_path`;
  - a control timeout and the live-turn cap.
- `MuseTurnRequest`: the prompt, plus an optional model, reasoning effort and turn ceiling.
- The tests never run the real `muse` or the real `wsl.exe`.
  - **Native-mode hosts** get `muse_command=(sys.executable, "-u", "fake_muse_peer.py", <scenario.json>)`, which is the §13 seam.
  - **WSL-mode hosts** run only on win32. They put a fake `wsl.exe` first on PATH. The fake is built from pip's console-script launcher, with a zipped `__main__` that runs the fake peer. The distro name is always `VidbyteFakeDistro`.

## Observable Outcomes

- Returned records:
  - `MuseReadiness`, `MuseModelCatalog`, `MuseSession`, `MuseSessionPage`, `MusePage`;
  - `NativeTurnHandle`, `NativeTurnResult`, `NativeSteerResult`, `NativeInterruptResult`, `NativeSessionUsage`.
- Errors: `NativeHostError.failure_code`, `next_step`, `operation` and `context`.
- Tool results: `ToolResult` status, output and metadata.
- What the fake logged:
  - every argv;
  - the overlay variables (`VIDBYTE_PEER_MARK`, `WSLENV`), and only whether `META_API_KEY` is set, never its value;
  - every frame it received or sent, and any schema violation;
  - the reap script it read and the environment the reap ran with.
- Elapsed time against an upper bound.
- On POSIX, process liveness from `/proc`.

## State Transitions

A host is created, entered once, used, and exited. A second `__aenter__` raises `configuration.invalid_argument`. Using a host before it is entered or after it exits raises `muse.process_exited`. In WSL mode, `__aenter__` runs `wsl.exe -l -q` once and starts no `muse`.

A turn is `RUNNING` and then reaches exactly one of `COMPLETED`, `INTERRUPTED` or `FAILED`. Its MSP turn id is the one in the `turn/start` ack.

A turn peer stops in this order:
1. `turn/interrupt`, when the turn is live.
2. stdin EOF.
3. Up to `NATIVE_STOP_GRACE_SECONDS` for the peer to exit by itself.
4. A whole-tree stop.
5. In WSL mode, the in-distro reap.

## Invariants

- INV-1 and INV-2: only `NativeHostError`, `ConfigurationError` (while a record is built) and `CancelledError` escape.
- INV-3 and INV-4, NFR-2: every wait is bounded, and every process is reaped on every path.
- INV-5:
  - records and primitive arguments are checked before any I/O;
  - the model is checked against a non-empty `model/list` before `session/start`;
  - session existence and busy state are checked before `turn/start`.
- INV-9 and D-11:
  - `approvalMode` is always `denyUnmatched`;
  - every requirement is decided at most once, with the `denied` choice scoped `once`;
  - user input is cancelled;
  - nothing approve-everything appears in argv, on the wire, in a record or in a tool parameter.
- INV-10: no turn waits on an unanswered request. A failed decide interrupts the turn by policy (EC-156).
- INV-11 to INV-17:
  - the handle comes back once `turn/start` is accepted;
  - a wait never changes the turn;
  - the terminal state is set once;
  - there is one live turn per session;
  - unknown usage is `None`;
  - the text is capped;
  - handles are scoped to their host.

## External Dependencies

- Python 3.11 subprocesses (`sys.executable`).
- On Windows, pip's `distlib/t64.exe` launcher, which builds the fake `wsl.exe` (tests skip without it), and `taskkill` from System32.
- On Linux, `/proc` and `sh` for liveness checks and the reap-script test.
- No network, no vendor SDK and no credentials.

## Known Failure Modes

These are the failure inventory the tests were chosen from, given as input → wrong output.

- **Escaping or wrong-coded errors:**
  - a launch `OSError`, a JSON-RPC error or a missing result member escapes raw;
  - a vendor code maps to the wrong row: -32001, -32031, -32601, -32010, -32002, -32020, -32021, -32023 or -32024 (EC-95 to EC-114).
- **Hangs:**
  - a silent `initialize`, read, steer, interrupt or decide never times out (AC-3, EC-97, EC-156);
  - a stubborn peer is never killed (EC-10).
- **Leaks:**
  - a cancelled spawn, continue, check or list leaves its peer running (AC-4);
  - `__aexit__` leaves turns running (EC-8);
  - a WSL turn peer's in-distro processes survive (D-23);
  - a failed turn that nobody waits on keeps its driver exception unretrieved, so asyncio logs "Task exception was never retrieved" when the task is collected (R-22; EC-119, D-9).
- **Wrong turn or text:**
  - the turn id is derived from the `commandId`;
  - another turn's `item/completed` or `turn/completed` is taken as this turn's (EC-109);
  - the reply text is read from `turn/completed`, or from non-`agentMessage` items;
  - a server-side truncation or `view/gap` is not flagged.
- **Wire drift:**
  - `clientInfo.version` is missing or a literal;
  - `initialized` is not sent first;
  - a top-level `lastTurnId` is sent on fork;
  - `expectedTurnId` or `requirementId` is missing;
  - a `commandId` is not a UUIDv7;
  - an optional member is sent while unset.
- **Over-permissive approvals:**
  - an approved choice, or one scoped to the session or persistent, is picked;
  - an update for an already-decided requirement is decided again;
  - an approval with no deny-once choice is answered instead of interrupted (EC-121).
- **WSL mistakes:**
  - the `.cmd` shim is launched;
  - the workspace is not translated to `/mnt/<drive>/...`;
  - the mark or the `WSLENV` entries are missing;
  - `META_API_KEY/u` is added when the variable is unset;
  - the reap runs with the peer's overlay, which would kill itself, carries a CR, or runs for read peers;
  - a missing distro or in-distro `muse` gets the wrong code (EC-94, EC-95).
- **Busy check and secrets:**
  - a spawn binds an upper-case id from Muse's `session/start`, and a continue or fork by the handle's own id then misses the busy check, so a second turn or a fork starts on a live session (INV-14, EC-112);
  - a credential in an `approval/requested` or `userInput/requested` tool name is recorded verbatim in `NativeApprovalDecision.title` and reaches `wait_muse_turn`'s output (§9.1, INV-6).
- **Races with the turn's own end (RACE-1):**
  - `turn/completed` reaches the host before the `turn/interrupt` answer, or the answer never comes, and the driver's own close of the peer makes `interrupt_muse_turn` raise `muse.process_exited` for an interrupt it sent to a running turn (INV-13);
  - a fix keyed on the answer code instead of the turn's own end lets a -32030 for a turn that is still running pass silently (EC-102), or swallows a real peer exit (EC-96, EC-97);
  - the turn completes while `turn/steer` waits, and the steer raises `muse.process_exited` instead of `muse.turn_not_found` (EC-115).
- **Usage:**
  - an unreported field becomes 0;
  - cost is set;
  - the backward usage search does not stop at the first event or at `MUSE_USAGE_MAX_PAGES` (D-14).

## Historical Regressions

- **r8 (S4 review R-5): `__aexit__` held for `control_timeout_seconds` when a peer was silent on `approval/decide`.** `MuseHost.__aexit__` did `await asyncio.wait(tasks)` with no timeout, so a silent decide held exit for the control timeout (up to 600 s) instead of the NFR-2 bound; Grok closed its peers after the grace, Muse never did. Caught by `test_aexit_returns_within_the_bound_when_a_peer_is_silent_on_decide` in `test_muse_host_process_bounds.py`.
- **r8 (S4 review R-7): WSL read peers never got `META_API_KEY/u` in `WSLENV`.** Only turn peers did, but §9.3/D-18 tie the key entry to the variable being set, not to being a turn peer. Caught by `test_read_peer_forwards_meta_api_key_through_wslenv` in `test_muse_host_wsl.py`.
- **r8 (S4 review R-8 / S4-6): the busy check compared session ids case-sensitively.** INV-14 says Muse ids compare ignoring letter case. Caught by `test_continue_on_the_upper_cased_id_of_a_live_session_is_busy` in `test_muse_host_turns.py`.
- **Re-review round 1 (R-16): the busy check missed a vendor-chosen upper-case id.** Spawn bound the id from `session/start` verbatim, but continue and fork lower-cased their argument and the turn table compared exactly, so a continue or fork by the handle's own `session_id` (or its lower-cased form) started a second turn or a fork. Caught by `test_continue_on_a_live_session_whose_vendor_id_is_upper_case_is_busy` and `test_fork_of_a_live_session_whose_vendor_id_is_upper_case_is_busy` in `test_muse_host_turns.py`.
- **Re-review round 1 (R-17): approval and user-input titles were recorded unscrubbed.** §9.1 says `NativeApprovalDecision.title` is scrubbed; the Muse driver recorded both titles verbatim, so a credential in a tool name reached the result and `wait_muse_turn`'s output. Caught by `test_a_credential_in_a_request_title_is_scrubbed_from_the_result_and_the_wait_tool` (both request kinds) in `test_muse_host_turns.py`.
- **RACE-1 (R-18, CI run 38437336454): an interrupt that lost the race to `turn/completed` raised `muse.process_exited`.** The driver read `turn/completed`, left its loop and closed the peer while `turn/interrupt` was pending, and the closed-transport failure escaped as "The Muse Code process stopped before it answered." The old interrupt test flaked on it because its fake raced the answer against the turn's end. Caught by `test_interrupt_that_loses_to_turn_completed_succeeds` and `test_interrupt_answered_after_turn_completed_succeeds` (-32013, -32014, -32030, accepted) in `test_muse_host_turns.py`; the old test now fixes the answer first (`order: answer_first`). `test_interrupt_rejected_with_32030_while_the_turn_still_runs_raises_api_error` guards EC-102, and the EC-96 and EC-97 rows in `test_muse_host_errors.py` guard a real peer exit or silence.
- **RACE-1 (R-21): a steer that lost the race to `turn/completed` raised `muse.process_exited`.** EC-115 calls for `muse.turn_not_found`, because the turn is no longer running. Caught by `test_steer_that_loses_to_turn_completed_raises_turn_not_found` in `test_muse_host_turns.py`.
- **Post-S6 (R-22): a failed turn that nobody waited on logged "Task exception was never retrieved".** Only `wait_muse_turn` read the driver task's exception; the host's done-callback and `__aexit__` never did, unlike Grok and opencode. No error was lost, but asyncio logged the scrubbed failure with a traceback when the task was collected. Caught by `test_failed_turn_never_waited_logs_no_unretrieved_exception` in `test_muse_host_turns.py`, whose waited twin still has to raise `muse.api_error` (EC-119).

## Test Suite Map

- `test_muse_host_acceptance.py`:
  - AC-6, AC-11 and AC-12;
  - spawn and continue happy paths;
  - an interrupt by the caller.
- `test_muse_host_errors.py`:
  - one table row per (function, code) of §6.3.2 and §6.3.5, in host mode and tool mode (AC-2);
  - AC-7's context;
  - EC-2 for all 12 methods, EC-3, EC-1 and EC-110;
  - the POSIX native `which` check.
- `test_muse_host_turns.py`:
  - approvals and user input (D-11, EC-121, EC-156), with a credential in either title scrubbed (re-review R-17);
  - the -32601 answer;
  - the ack turn id and foreign events (EC-109);
  - steer and interrupt wire;
  - truncation (EC-150, `view/gap`);
  - usage, the ceiling (D-10), EC-148, INV-17 and EC-9;
  - the INV-14 busy check on an upper-cased id (r8, R-8), and on a continue or fork after Muse returned an upper-case id (re-review R-16);
  - an interrupt or steer that loses the race to the turn's own `turn/completed` (RACE-1: R-18, R-21), with guards for a -32030 on a running turn and for an interrupt while the driver closes a completed turn;
  - a failed turn that nobody waits on, which must not be logged as never retrieved (R-22).
- `test_muse_host_wire.py`:
  - `clientInfo` and `initialized`;
  - every command's members;
  - fork's `cutPoint`;
  - the launch argv;
  - INV-9 on the wire;
  - the UUIDv7 layout and order rule.
- `test_muse_host_reads.py`:
  - readiness (EC-105) and the catalog;
  - an empty catalog with EC-108 pass-through;
  - session pages, read and fork;
  - view events, compact and cut;
  - usage tracking and its page limit;
  - the EC-114 resume-and-retry.
- `test_muse_host_process_bounds.py`:
  - the AC-3 bound for nine functions, plus the 9 s default;
  - AC-4 cancellation and the cancelled wait;
  - `__aexit__` (EC-8), including the NFR-2 bound with a peer silent on `approval/decide` (r8, R-5);
  - grandchild reaping (EC-10).
- `test_muse_host_records.py`:
  - EC-106 and the `MuseHostSettings` checks, naming `<Record>.<field>`;
  - defaults;
  - the field sets of the 15 records;
  - immutability and the closed enums.
- `test_muse_host_tools.py`:
  - §9.2 rows 29 to 40 and `read_only`;
  - AC-15;
  - success metadata;
  - Muse argument parsing, EC-144 and EC-145.
- `test_muse_host_wsl.py`:
  - `to_wsl` and the reap constants;
  - the Linux reap-script test;
  - the WSL argv, overlay and reap;
  - the read peer's `META_API_KEY/u` in `WSLENV` (r8, R-7);
  - EC-94 and EC-95 in WSL mode.

Run everything with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host`.

## Omitted Testing Strategies

- **Live Muse or WSL runs.** The spec forbids live prompts and the real distro. Every vendor fact comes from the §6.3.5 rows and the MSP 1.0.1 schema, read as data.
- **AC-10 with its literal settings.** `MuseHostSettings(workspace=WindowsPath("C:/w/repo"), wsl_distro="MuseUbuntu1")` needs an existing `C:/w/repo` and the user's real distro. The test splits AC-10 instead:
  - the translator is checked on `PureWindowsPath("C:/w/repo")`;
  - the full argv and `workspaceRoot` path is checked on a temporary workspace with the fake distro.
- **`MuseLauncher` unit tests.** §8.5 and §13 call its argv and overlay "pure and testable", but name no method. They are proven at host level through the fake `wsl.exe` instead.
- **Pruned duplicates.** One case per (function, code) is kept, plus a named variant only for a distinct guard. These are not written, because the same guard is already proven:
  - EC-97 and EC-98 for every MSP method of a function;
  - EC-102 for each of the listed vendor codes;
  - EC-111 with -32011;
  - EC-119 for each error kind;
  - EC-1 for every argument on every method.
- **Shared plumbing.** It is proven once, in `tests/features/grok_host/`:
  - EC-138 to EC-143;
  - EC-149, the 64-turn eviction, which would need 65 peers here;
  - the code catalog;
  - the turn table.
- **Unpinned mappings.** The spec leaves these open, so they are not asserted:
  - `forked_from` from MSP's `ForkProvenance` object;
  - `MuseModel.display_name`;
  - `MuseViewEvent.kind`;
  - the outcome recorded for a plain denied decide;
  - `cachedTokens` against `cacheReadTokens`.
- **The reap's own timeout and failure paths, and the mark-mismatch skip.** The mark is generated inside the host, and a reap that fails is not raised (EC-10), so there is no caller-visible outcome to assert.
