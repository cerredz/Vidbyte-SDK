# Native opencode host feature tests

## Folder Description / Intent

This folder checks the public promise of `vidbyte.harnesses.native.opencode.OpencodeHost` and the 18 `OpencodeTools`. The tests drive the real host, `HttpTransport` and turn watcher against `FakeOpencodeServer`, an in-memory opencode 1.18.31 server reached by patching `vidbyte.lib.http.transport.httpx.AsyncClient` with an `httpx.MockTransport`. Owned-server tests also run `fake_opencode_serve.py` as a real child process through `OpencodeHostSettings.opencode_command`. Nothing in the host, `HttpTransport` or `ManagedProcess` is mocked.

The implementations belong here:
- `vidbyte/harnesses/native/opencode/`: the host, HTTP client, wire codec, owned server and turn watcher.
- `vidbyte/lib/dataclasses/opencode.py`.
- `vidbyte/lib/enums/native_hosts.py`: `OpencodePermissionAction` and `OpencodeMcpKind`.
- `vidbyte/lib/constants/native_hosts.py`: the `OPENCODE_*` constants.
- `vidbyte/tools/builtins/opencode/`.
- `vidbyte/tools/toolsets/opencode.py`.

## Non-Goals

- Do not run the real `opencode` or reach the network. Attached hosts talk to the in-memory server, owned hosts launch the fake, and the PATH test points PATH at an empty folder.
- Do not send a live prompt or read opencode's `auth.json`.
- Do not test the shared contract here: the code catalog, `NativeHostError`, the hostkit, `CliRunner`, `ManagedProcess`, the transport extension and the shared tool base (EC-140, EC-141, EC-143) belong to `tests/features/grok_host/`. The backend profiles belong to `tests/features/native_backends/`.

## File Index

- `README.md`: the boundary of the pack and where changes belong.
- `FEATURE.md`: the contract, the failure inventory the tests were chosen from, and the strategies deliberately omitted.
- `conftest.py`:
  - lazy feature imports (`opencode_api`, `opencode_tools_api`);
  - the in-memory server (`FakeOpencodeServer`, installed by `fake_opencode`);
  - the attached host builder (`make_opencode_host`);
  - the owned-server launcher scenarios and log reader (`serve_fake`);
  - the silent loopback socket for AC-3 (`silent_loopback`);
  - shrunk timings (`fast_timings`);
  - the error-shape checks (`check_native_error`, `check_tool_error`);
  - bounded polling (`wait_until`) and POSIX liveness (`process_running`).
- `fake_opencode_serve.py`: the scripted `opencode serve`. It prints the listening line (or stays silent, or exits early), optionally starts a grandchild or ignores TERM, and logs its argv and digests of its secret environment values to JSONL files.
- `test_opencode_host_acceptance.py`: AC-3, AC-4, AC-6, AC-7, AC-11 and AC-12, concurrency, request shapes, and the mapping of every read. Start here for a caller-visible regression.
- `test_opencode_host_errors.py`: one table-driven case per (function, code) from §6.3.2 and §6.3.4, run against the host and against the matching tool, plus the `__aenter__` rows and invalid primitive arguments.
- `test_opencode_host_watcher.py`: how a live turn is identified, finished, failed or interrupted, and how pending permissions and questions in its session tree are rejected.
- `test_opencode_host_owned_server.py`: the owned server's launch, password, backend keys, start-up failures, stop bounds and death between calls. Start here for a leftover process.
- `test_opencode_host_security.py`: secret scrubbing (AC-5), provider keys, `repr`, logging and the allow-everything rule on the wire.
- `test_opencode_host_records.py`: the opencode request, rule, MCP and settings records.
- `test_opencode_host_tools.py`: the toolset table, `read_only`, the default policy, the success encoding and the tool-only rows.

## Logs

- 2026-10-13 - The pack was written red before implementation, from spec r3 (S2 test author). Every test fails at setup or in its first assertion until the modules above exist.
