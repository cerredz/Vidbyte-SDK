# Feature: Native opencode host

## High-Level Feature Description

A developer opens `OpencodeHost(OpencodeHostSettings(workspace=...))` with `async with` and drives an opencode server (`opencode serve`, version 1.18.31 or later) over HTTP from Python. The host either attaches to a running server through `server_url` with optional basic-auth credentials, or starts its own server on `127.0.0.1` with a random port and a random password that only the child's environment ever holds. Through that server the host can:
- check readiness;
- list models, providers and provider auth methods;
- start a session with a live turn and return a handle while the turn runs;
- continue, fork, revert and unrevert a session;
- list sessions, read a session, its messages, one message and its diff;
- wait for or interrupt a turn;
- total a session's usage;
- add a registered MCP server.

A live turn is posted with `prompt_async` and then watched by polling `GET /session/status` and the session's newest messages. The reply set is every assistant message whose `parentID` is the turn's user message. Pending permission and question requests anywhere in the turn's session tree are rejected and recorded. Every failure is one `NativeHostError` that carries a `FailureCode` and a non-empty `next_step`. The 18 `OpencodeTools` expose the same functions to a model, return error results instead of raising, and under the default `PermissionPolicy` run only the 11 READ tools.

## Contract

The contract is spec `docs/spec/native-grok-opencode-meta-hosts/spec.md` r3:
- §6.1: INV-5, INV-6, INV-9, INV-12, INV-15, INV-16.
- §6.2: AC-2 to AC-7, AC-9, AC-11, AC-12, AC-19.
- §6.3.2 and §6.3.4: the shared rows EC-1 to EC-9 for the 18 functions, the host-wide rows EC-54 to EC-63, and the function rows EC-64 to EC-93, plus EC-152 to EC-155.
- §6.3.7 and §6.3.8: EC-138, EC-144 to EC-146, EC-148 and EC-150 as the opencode tools reach them.
- §8.5: the `OpencodeHost` signatures, the routes, the owned-server launch, and the turn watcher.
- §9.1 to §9.3: the opencode records, §9.2 rows 11 to 28, and the opencode constants.
- §10: T-2, T-3 and T-5.

`OpencodeHost` methods:
- `check_opencode_ready`, `list_opencode_models`, `list_opencode_providers`, `get_opencode_provider_auth`;
- `spawn_opencode_session`, `continue_opencode_session`, `fork_opencode_session`, `revert_opencode_session`, `unrevert_opencode_session`;
- `list_opencode_sessions`, `get_opencode_session`, `get_opencode_session_messages`, `get_opencode_message`, `get_opencode_session_diff`;
- `wait_opencode_turn`, `interrupt_opencode_turn`, `track_opencode_session_usage`, `add_opencode_mcp_server`.

## Actors / Callers

- SDK developers using `vidbyte.harnesses.native.opencode`.
- Models calling the `OpencodeTools` through `ToolExecutor`.
- MCP clients reaching `OpencodeTools.read_only(host)`.

## Inputs and Preconditions

- `OpencodeHostSettings`: an existing absolute workspace folder, and either a `server_url` with optional paired credentials, an `opencode_command` argv prefix, or neither (PATH lookup). It also takes backends, startup and request timeouts, registered MCP servers and the live-turn cap.
- The request records `OpencodePromptRequest`, `OpencodeSpawnRequest`, `OpencodePermissionRule` and `OpencodeMcpServerConfig`.
- The tests never run the real `opencode`. HTTP goes through the real `HttpTransport`, with `vidbyte.lib.http.transport.httpx.AsyncClient` patched to an `httpx.MockTransport` over `FakeOpencodeServer` (the §13 seam). Owned mode runs `fake_opencode_serve.py` as a real child process through `opencode_command`. AC-3 uses a real loopback socket that accepts and never answers.

## Observable Outcomes

- The returned records: `OpencodeReadiness`, `OpencodeModel`, `OpencodeProvider`, `OpencodeProviderAuth`, `OpencodeSession`, `OpencodeMessage`, `OpencodeMessagePage`, `OpencodeFileDiff`, `OpencodeMcpStatus`, `NativeTurnHandle`, `NativeTurnResult`, `NativeInterruptResult` and `NativeSessionUsage`.
- `NativeHostError.failure_code`, `next_step`, `operation` and `context`.
- `ToolResult` status, output and metadata.
- What the fake server recorded: every method, route, path, query, JSON body and basic-auth pair, and the host and port each request went to.
- What the fake launcher logged: argv, the working folder, the username, and length-and-digest records of the secret environment values (never the values).
- Elapsed time against an upper bound.
- On POSIX, process liveness from `/proc`.

## State Transitions

A host is created, entered once, used, and exited. A second `__aenter__` raises `configuration.invalid_argument`. Using a host before it is entered or after it exits raises `opencode.process_exited`.

A turn moves from RUNNING to exactly one of:
- COMPLETED, after `OPENCODE_IDLE_CONFIRMATIONS` idle polls once the newest reply is completed;
- INTERRUPTED, by the caller, the deadline, the host closing, policy, or an abort from elsewhere;
- FAILED, with the code its assistant error, a deleted session, retry exhaustion or repeated poll failures maps to.

A finished turn keeps its result for every later wait.

## Invariants

- INV-5: records and primitive arguments fail before any request is sent.
- INV-6: no secret appears in argv, an error, a tool result, a `repr` or a log record. Vendor text is scrubbed and capped at 1000 characters.
- INV-9: no field, parameter or body carries the allow-everything rule.
- INV-12: cancellation propagates and releases any reservation; cancelling a wait leaves the turn running.
- INV-16: result text at most 100,000 characters, patches 20,000, message pages 200, the session tree 64, the body 8 MiB.
- Every request carries `directory=<workspace>` and, when credentials exist, basic auth in a header.

## External Dependencies

- `httpx` 0.28 through `HttpTransport`; the host never builds its own client.
- The opencode 1.18.31 HTTP API (the routes in §8.5), modelled by `FakeOpencodeServer`.
- The owned-server launch line `opencode server listening on http://127.0.0.1:<port>`.
- POSIX `/proc` for the reaping checks.

## Known Failure Modes

- **Server down or slow:** a refused connection, a timeout, a 503 or an unhealthy health body raises `opencode.server_unreachable` (EC-55, AC-3).
- **Wrong credentials:** a 401 raises `opencode.not_signed_in` naming `server_password` (EC-57).
- **Bad bodies:** non-JSON, oversize or missing relied-on members raise `opencode.protocol_mismatch` (EC-58).
- **Vendor errors:** a 500 raises `opencode.api_error` with the scrubbed vendor text (EC-59).
- **Old server:** a version below 1.18.31 raises `opencode.version_unsupported` and stops an owned server (EC-60).
- **Missing binary or key:** no command and nothing on PATH raises `opencode.not_installed` (EC-54). A backend with no key fails before the server starts (EC-61).
- **Unknown model, session or message:** checked before any turn starts or any write is sent (EC-65, EC-68, EC-72, EC-75), including the routes that answer 200 for a missing session (diff, abort).
- **Busy session or full host:** EC-67 and EC-73, with no request after the check.
- **Turn failures:** assistant errors map to `not_signed_in`, `usage_limited`, `billing_error` or `api_error` (EC-82 to EC-85). Retry at `OPENCODE_RETRY_ATTEMPT_LIMIT` aborts the turn (EC-155). Five failed polls in a row fail it (EC-87). A deleted session fails it (EC-86).
- **Turn identification:** a reply to an earlier turn, a reply still being written, or a reply that left the 50-message window must not decide the turn.
- **Approvals:** a pending permission or question in the session tree must be rejected. One outside the tree must be left alone. A tree over 64 sessions aborts the turn (EC-154).
- **Leaks:** a password, backend key or MCP secret echoed by the vendor; provider `key` or `options` copied into a result; a secret field in a `repr`.
- **Processes:** an owned server or its grandchild outliving `__aexit__`. A server that dies between calls being restarted (EC-153).

## Historical Regressions

- **r8 (S4 review R-6): a single non-counted poll failure orphaned a running server turn.** One transient HTTP 500 (`opencode.api_error`, EC-59) is not counted by EC-87, so it failed the turn locally, but no `POST …/abort` was sent, leaving a still-spending server turn the SDK could not stop. INV-10/INV-13 and the EC-154/EC-155 abort-first paths imply one best-effort abort before raising. Caught by `test_a_single_non_counted_poll_failure_aborts_before_failing_the_turn` in `test_opencode_host_watcher.py`. The spec does not state this abort rule outright, so it is recorded as a spec gap resting on INV-10/INV-13 and the review.

## Test Suite Map

- `test_opencode_host_acceptance.py`:
  - AC-2, AC-4, AC-6, AC-7, AC-11 and AC-12;
  - AC-3 against a silent loopback socket;
  - the concurrency rows EC-9 and EC-67;
  - the request shapes of spawn, continue, fork, revert, unrevert and MCP add;
  - the mapping of every read;
  - the directory and basic-auth rule on every request.
- `test_opencode_host_errors.py`:
  - one table-driven case per (function, code) from §6.3.2 and §6.3.4, in host mode and tool mode;
  - the `__aenter__` rows;
  - the unopened or closed host and re-entry;
  - invalid primitive arguments.
- `test_opencode_host_watcher.py`:
  - the reply set, text and summed usage;
  - the message window, earlier turns and partial replies;
  - stop reasons, the ceiling, host close and abort from elsewhere;
  - poll failures, deleted sessions and retry, including one best-effort abort before a single non-counted poll failure fails the turn (r8, R-6);
  - the text cap;
  - the session-tree walk for permissions and questions (EC-154).
- `test_opencode_host_owned_server.py`:
  - AC-9 (loopback, port 0, a random password in the environment only);
  - EC-54, EC-55, EC-56, EC-60, EC-61 and EC-153 in owned mode;
  - backend key overlay;
  - tree stop and cancellation of `__aenter__`.
- `test_opencode_host_security.py`:
  - AC-5 for the attached and owned passwords, a backend key, and MCP env and header values;
  - the vendor-text cap;
  - provider `key` and `options`;
  - `repr`;
  - no logging;
  - INV-9 on the wire.
- `test_opencode_host_records.py`: EC-66, EC-91, EC-152, AC-19, and the remaining `OpencodeHostSettings` rules.
- `test_opencode_host_tools.py`:
  - the §9.2 table and `read_only`;
  - AC-15 and the success encoding;
  - EC-138, EC-144, EC-145 and EC-146;
  - T-2 for the MCP add tool.

Run everything with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host`.

## Omitted Testing Strategies

- **Live opencode runs.** The spec forbids live prompts. Every vendor fact comes from the §6.3 rows and §8.5, which quote the S1 probes.
- **EC-56 for every function.** A process exit is a property of the owned server, not of a route. It is proved once at start-up and once between calls (EC-153).
- **EC-58 on the abort answer.** The host does not rely on the abort body (it answers `true` even for a missing session).
- **EC-62.** It cannot be reached with the two declared backend profiles.
- **EC-4's "cancelled after `prompt_async` returned 204 but before the handle returned" window.** It cannot be hit deterministically. The cancel tests cover the windows before the request and during the wait.
- **The shared hostkit pieces** (EC-143 clipping, EC-149 eviction, the decision cap, EC-140, EC-141). They are tested once in `tests/features/grok_host`.
- **NFR-7 latency targets.** These depend on the machine. Only upper bounds with slack are asserted.
- **Windows process liveness.** There is no portable check (§13). Windows asserts time bounds and outcomes only.
