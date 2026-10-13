# Native Grok host feature tests

## Folder Description / Intent

This folder checks the public promise of `vidbyte.harnesses.native.grok.GrokHost`, the module-level `run_grok_once`, and the ten `GrokTools`. It also checks the plumbing that all three native hosts share, because Grok is its first user: the `McpStdioTransport` extension, `vidbyte.lib.process`, `RecordFieldValidator`, `NativeHostError`, the `hostkit` error factory and turn table, the code catalog, the enums and constants, and the fixed `native/__init__.py` bytes. The tests drive the real host, transport and process helpers against `fake_grok_peer.py`, a scripted stand-in for `grok` run as a real child process through `GrokHostSettings.grok_command`. Nothing in the host, the transport or `CliRunner` is mocked.

The implementations belong here:
- `vidbyte/harnesses/native/grok/`: the host, turn driver, wire codec and CLI adapter.
- `vidbyte/harnesses/native/hostkit/`.
- `vidbyte/tools/mcp/transport.py`.
- `vidbyte/lib/process/`.
- `vidbyte/lib/dataclasses/{validation,native_hosts,grok,process}.py`.
- `vidbyte/lib/enums/{native_hosts,harness_backends,process,failure}.py`.
- `vidbyte/lib/constants/native_hosts.py`.
- `vidbyte/lib/errors/base.py`.
- `vidbyte/tools/builtins/native_host_tool.py` and `vidbyte/tools/builtins/grok/`.
- `vidbyte/tools/toolsets/grok.py`.

## Non-Goals

- Do not run the real `grok`. Every host here gets an explicit `grok_command`, and the PATH tests point PATH and HOME at temporary folders.
- Do not send a live prompt or read `~/.grok/auth.json`.
- Do not test opencode, Muse or the backend profiles here. Their packs are `tests/features/opencode_host/`, `tests/features/muse_host/` and `tests/features/native_backends/`.
- Do not edit `tests/test_mcp_stdio_transport.py` or `tests/test_mcp_studio_server.py`. They must stay green unchanged (INV-18). The new transport options are tested here instead.

## File Index

- `README.md`: the boundary of the pack and where changes belong.
- `FEATURE.md`: the contract, the failure inventory the tests were chosen from, and the strategies deliberately omitted.
- `conftest.py`:
  - lazy feature imports (`grok_api`, `grok_tools_api`);
  - the scenario writer and log reader for the fake (`grok_fake`);
  - the host builder (`make_grok_host`);
  - shrunk stop timings (`fast_stop`);
  - the error-shape checks (`check_native_error`, `check_tool_error`);
  - bounded polling (`wait_until`) and POSIX liveness (`process_running`).
- `fake_grok_peer.py`: the scripted `grok`. Its argv decides its role:
  - `--version` and `models`: the CLI checks;
  - `agent --no-leader ... stdio`: an ACP peer;
  - `--single=`: a one-shot or fork run.
  It logs every argv, frame and answer to JSONL files.
- `test_grok_host_acceptance.py`: the §4 snippet as written, plus AC-6, AC-11, AC-12 and `run_grok_once`. Start here for a caller-visible regression.
- `test_grok_host_errors.py`: one table-driven case per (function, code) from §6.3.2 and §6.3.3, run against the host and against the matching tool.
- `test_grok_host_session_id_case.py`: INV-14 session-id case-insensitivity for the busy check and the fork id checks (r8).
- `test_grok_host_windows_launcher.py`: EC-157, the win32-only rule that Grok never starts a batch launcher (r8).
- `test_grok_host_turns.py`: live-turn behaviour: approvals, interrupts, the ceiling, text and usage, concurrency, and wire shapes.
- `test_grok_host_reads.py`: the successful reads and CLI runs, with their argv.
- `test_grok_host_process_bounds.py`: time bounds, cancellation and reaping. Start here for a hang or a leftover process.
- `test_grok_host_records.py`: the validator, the shared native records, and the Grok records.
- `test_grok_host_tools.py`: the model-facing tools and the shared tool base.
- `test_grok_host_shared_contract.py`: the cross-host vocabulary, error type, hostkit, enums, constants, fixed bytes and imports.
- `test_grok_host_process_helpers.py`: `CliRunner`, `ManagedProcess`, `ProcessStopper` and `CliInvocation`.
- `test_grok_transport_extension.py`: the `McpStdioTransport` additions (messages, server requests, notifications, per-call deadlines, exit grace, tree stop) and the dispatch fix.

## Logs

- 2026-10-13 - The pack was written red before implementation, from spec r3 (S2 test author). Every test fails at setup or in its first assertion until the modules above exist.
- 2026-10-13 - Added S4 regression tests (addendum r8, S2 test author): R-1 (no-cursor `-32602` api_error rows and a focused test in `test_grok_host_errors.py`), R-2 (new `test_grok_host_windows_launcher.py`, EC-157), and R-8 (new `test_grok_host_session_id_case.py`, INV-14 case-insensitivity). AC-1's win32 completed-text branch in `test_grok_host_acceptance.py` moved to the §13 seam (grant a), because EC-157 now refuses the `grok.cmd` shim.
- 2026-10-13 - Added RACE-1 regression tests (addendum 3, S2 test author) to `test_grok_host_turns.py`: R-19 (a cancel write that loses the race to Grok's answer) and R-20 (an interrupt while the driver closes an answered turn). R-19's window sits inside one await, so the file's `cancel_drain_gate` fixture wraps `NativePeer.notify` and `asyncio.wait_for` and only delays the cancel's drain until the fake logs stdin EOF.
