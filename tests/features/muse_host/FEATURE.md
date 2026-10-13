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
  - a WSL turn peer's in-distro processes survive (D-23).
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
- **Usage:**
  - an unreported field becomes 0;
  - cost is set;
  - the backward usage search does not stop at the first event or at `MUSE_USAGE_MAX_PAGES` (D-14).

## Historical Regressions

None yet. The pack was written red before implementation, from spec r3.

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
  - approvals and user input (D-11, EC-121, EC-156);
  - the -32601 answer;
  - the ack turn id and foreign events (EC-109);
  - steer and interrupt wire;
  - truncation (EC-150, `view/gap`);
  - usage, the ceiling (D-10), EC-148, INV-17 and EC-9.
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
  - `__aexit__` (EC-8);
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
