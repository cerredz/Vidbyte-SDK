# Native Muse host feature tests

## Folder Description / Intent

This folder checks the public promise of `vidbyte.harnesses.native.muse.MuseHost` and the twelve `MuseTools`. It also checks the Muse-only collaborators behind them:
- `MuseWire`: the MSP params, the UUIDv7 command ids and the inbound parsers;
- `MuseTurnDriver`: approvals, the ack turn id, and the reply text from `agentMessage` items;
- `MuseLauncher` and `MusePathTranslator`: the WSL argv, the peer mark, `WSLENV` and the in-distro reap.

The tests drive the real host, transport and process helpers against `fake_muse_peer.py`. That file is a scripted stand-in for `muse` and `wsl.exe`, run as a real child process. Nothing in the host, the transport or `CliRunner` is mocked.

The implementations belong here:
- `vidbyte/harnesses/native/muse/`: `host.py`, `turn.py`, `wire.py` and `launcher.py`.
- `vidbyte/lib/dataclasses/muse.py`.
- The `MUSE_*` entries in `vidbyte/lib/constants/native_hosts.py`.
- `vidbyte/tools/builtins/muse/`.
- `vidbyte/tools/toolsets/muse.py`.

## Non-Goals

- Do not run the real `muse` or the real `wsl.exe`, and never name the distro `MuseUbuntu1` in a test that starts a process. Native hosts get an explicit `muse_command`. WSL hosts use the fake `wsl.exe` and the distro `VidbyteFakeDistro`.
- Do not send a live prompt or read Muse credentials. `META_API_KEY` is only ever a placeholder, and the fake logs whether it is set, never its value.
- Do not re-test the shared plumbing (code catalog, `NativeHostError`, hostkit, process helpers, transport extension, EC-138 to EC-143). The `tests/features/grok_host/` pack owns it.

## File Index

- `README.md`: the boundary of the pack and where changes belong.
- `FEATURE.md`: the contract, the failure inventory the tests were chosen from, and the strategies deliberately omitted.
- `conftest.py`:
  - lazy feature imports (`muse_api`, `muse_tools_api`);
  - the scenario writer and log reader for the fake (`muse_fake`);
  - the host builders (`make_muse_host`, and `make_wsl_host`, which builds the fake `wsl.exe`);
  - shrunk stop timings (`fast_stop`);
  - the error-shape checks (`check_native_error`, `check_tool_error`);
  - bounded polling (`wait_until`), POSIX liveness (`process_running`) and `tool_by_name`.
- `fake_muse_peer.py`: the scripted `muse` and `wsl.exe`. Its argv decides its role:
  - `--version`: the version check;
  - `serve`: an MSP 1.0.1 peer that enforces the schema's required members;
  - after `--as-wsl`, the WSL forms: `-l -q`, `-d <distro> -e <muse_path> ...`, and the reap `-d <distro> -e sh -s <mark>`.
  It logs every argv, frame, overlay variable and reap script to JSONL files. `msp["turn/interrupt"]["order"]` fixes whether the interrupt's answer or the turn's own `turn/completed` reaches the host first; without it the two race.
- `test_muse_host_acceptance.py`: AC-6, AC-11 and AC-12, plus the spawn, continue and interrupt happy paths. Start here for a caller-visible regression.
- `test_muse_host_errors.py`: one table-driven case per (function, code) from §6.3.2 and §6.3.5, run against the host and against the matching tool. It also covers EC-1, EC-2 and EC-3.
- `test_muse_host_turns.py`: live-turn behaviour:
  - approvals, user input and server requests;
  - the ack turn id and foreign events;
  - steer and interrupt;
  - truncation, usage and the ceiling;
  - repeated failure, handle scoping and concurrency.
- `test_muse_host_wire.py`: the MSP frames member by member, the launch argv, INV-9 on the wire, and `MuseWire.new_command_id()`.
- `test_muse_host_reads.py`: the successful reads (readiness, models, sessions, pages, usage) and the EC-114 retry.
- `test_muse_host_process_bounds.py`: time bounds, cancellation and reaping. Start here for a hang or a leftover process.
- `test_muse_host_records.py`: the Muse records, their validation and defaults, and INV-9 in the record fields.
- `test_muse_host_tools.py`: the model-facing Muse tools, `read_only`, AC-15, EC-144 and EC-145.
- `test_muse_host_wsl.py`: `MusePathTranslator`, the WSL launch, overlay and reap, the Linux reap-script test, and EC-94 and EC-95 in WSL mode.

## Logs

- 2026-10-13 - The pack was written red before implementation, from spec r3 (S2 test author). Every test fails at setup or in its first assertion until the modules above exist.
- 2026-10-13 - Added RACE-1 regression tests (addendum 3, S2 test author) to `test_muse_host_turns.py`: R-18 (an interrupt that loses the race to `turn/completed`) and R-21 (a steer that does), plus two guards. `fake_muse_peer.py` gained the `turn/interrupt` `order` knob, and the old -32013/-32014 interrupt test now uses `answer_first`, because without it the fake raced the answer against the turn's end and the test flaked in CI.
