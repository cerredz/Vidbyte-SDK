# Design Doc: Harden MCP Stdio Transport

**Status:** Draft  
**Author:** Grok  
**Created:** 2026-07-18  
**Last Updated:** 2026-07-18  

## 1. Overview

The Vidbyte SDK already attaches MCP servers over subprocess stdio
(`McpStdioTransport` in `vidbyte/tools/mcp/transport.py`). That transport is
functionally enough for sequential initialize → tools/list → tools/call flows,
but it is not reliable under concurrency, long-running calls, noisy stderr, or
abrupt child-process death.

This change hardens the **existing** stdio JSON-RPC transport in place: demultiplex
responses by request ID, drain stderr continuously with a size bound, apply a
timeout to every request, fail all pending calls when the child exits, restrict
inherited environment variables, and make shutdown (terminate → wait → force-kill)
bounded and idempotent. MCP attachment, client, and bridge public APIs stay
intact; only transport reliability and a thin wiring of timeouts from
`McpServerConfig` change.

## 2. Goals & Non-Goals

### Goals

- Preserve the current MCP attach / client / bridge capability end-to-end.
- Demultiplex concurrent JSON-RPC responses by request `id` so concurrent
  `tools/call` (or other) requests cannot consume each other's replies.
- Continuously drain stderr with a bounded ring buffer so a chatty server cannot
  block on a full stderr pipe.
- Apply a deadline to every transport `request()`, not only the initialize
  handshake in `attach_mcp_server`.
- Resolve (fail) all pending futures when the child process exits or stdout EOF
  is observed.
- Reject duplicate, missing, and unknown response IDs without mis-delivering
  results to the wrong waiter.
- Ignore protocol notifications (and other non-response frames) instead of
  treating them as request replies.
- Make `close()` fully idempotent; prevent new requests once closing begins.
- Terminate, wait, and force-kill the child in a bounded sequence.
- Pass only a minimal safe process environment plus caller-supplied `env`, not
  the full parent `os.environ`.
- Cover malformed messages, process crashes, hangs, concurrent calls,
  cancellation/timeout, and shutdown with automated tests that existing CI runs.

### Non-Goals

- New transports (SSE, streamable HTTP, WebSocket).
- Full bidirectional MCP (client-side handling of server-initiated requests
  beyond safe discard of unexpected frames).
- Changing MCP protocol version, initialize payload, or tool bridging semantics.
- Sandboxing or OS-level confinement of the child command.
- Reworking `McpClient` / `McpToolBridge` / attachment mixin APIs beyond timeout
  and close wiring needed for the hardened transport.
- Feature-test-pack scaffolding (`FEATURE.md` packs); coverage is ordinary
  `tests/` unit tests so `python scripts/run_ci.py` remains the gate.

## 3. Background & Context

### Current implementation (audit)

`McpStdioTransport` today:

1. Starts `asyncio.create_subprocess_exec` with stdin/stdout/stderr PIPEd.
2. Builds `sub_env = dict(os.environ)` then overlays `self.env`.
3. On `request()`, increments `_next_id`, writes one JSON line, then
   **immediately** `await stdout.readline()` and requires `response["id"]` to
   match the just-sent id.
4. On `close()`, `terminate()`, `wait_for(..., 5)`, then `kill()` if needed.

Call chain:

```text
BaseAgent.attach_mcp_server / attach_mcp_servers
  → attach_mcp_server(config)          # tools/mcp/attach.py
      → McpStdioTransport(command, env=config.env)
      → McpClient(transport).initialize()   # only handshake has config.timeout
      → McpToolBridge(...).bridge()         # tools/list
  → tools/call later via McpBridgedTool     # no general request deadline
```

### Robustness risks (confirmed in source)

| Risk | Evidence |
|------|----------|
| Concurrent requests consume wrong responses | Each `request()` reads the next stdout line without a shared demux table; two concurrent writers both call `readline()`. |
| No general request deadline after init | `attach.py` wraps only `client.initialize()` in `asyncio.timeout(config.timeout)`. |
| Stderr piped but never drained | `stderr=PIPE` in `start()`; no reader task. |
| Child exit with pending requests | Empty `readline()` raises once; no fan-out to other waiters. |
| Unexpected / duplicate response IDs | Single strict equality check only for the “current” id; no global pending map. |
| Notifications mistaken for responses | Any line without the expected id raises; notifications have no `id`. |
| Broad env inheritance | Full `os.environ` copy. |
| Non-idempotent / racy close | Second `close()` is mostly safe after `_process = None`, but in-flight `request()` can still write; no “closing” gate; no pending resolution. |

### Related modules (unchanged behavior unless noted)

- `vidbyte/tools/mcp/client.py` — initialize / list_tools / call_tool over `McpTransport`.
- `vidbyte/tools/mcp/attach.py` — must pass `request_timeout=config.timeout` into the transport.
- `vidbyte/tools/mcp/types.py` — `McpServerConfig.timeout` remains the single timeout knob.
- `vidbyte/lib/errors/base.py` — reuse `McpProtocolError` for protocol/transport failures.
- Existing tests mock the transport (`test_mcp_attachment.py`, `test_mcp_discovery_tools.py`,
  `test_mcp_bridge.py`); they stay valid as long as constructor/`request`/`close` signatures
  remain compatible.

### Canonical CI (origin/main)

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

Diagnostic stages: `python scripts/run_ci.py --stage source|package`.

## 4. Requirements

### Functional Requirements

1. **Demultiplex by ID:** Concurrent `await transport.request(...)` calls must each
   receive the response whose JSON-RPC `id` matches their request, or a typed
   error if no such response arrives before timeout/close/exit.
2. **Per-request timeout:** Every `request()` fails with `McpProtocolError` (or a
   clear subclass message) when the deadline elapses. Default equals
   `McpServerConfig.timeout` when constructed via `attach_mcp_server`
   (default `30.0` seconds). Direct `McpStdioTransport(...)` construction also
   accepts `request_timeout: float = 30.0`.
3. **Stderr drain:** A background task continuously reads stderr. Captured output
   is retained only up to a fixed byte budget (default **64 KiB**, newest data
   preferred). Excess is dropped. Captured stderr may be included in error
   `details` on transport failures.
4. **Process-exit fan-out:** On stdout EOF or process exit, every pending future
   is completed with `McpProtocolError` describing process death / closed stream.
5. **Response ID hygiene:**
   - Missing `id` on a frame that is not a clear notification: discard safely
     (do not complete any waiter); optionally record in diagnostics.
   - Unknown `id`: discard; do not invent a waiter.
   - Duplicate `id` (already completed or not in pending): discard second frame;
     do not overwrite a completed result.
   - JSON-RPC notifications (`method` present, `id` absent): discard without
     raising to waiters.
6. **Malformed lines:** Invalid JSON on a stdout line does not deliver a result
   to a random waiter; it is discarded as a protocol anomaly. Persistent stream
   corruption is surfaced via timeout or process-exit paths rather than
   mis-association.
7. **Close gate:** Once `close()` begins, new `request()` / `start()` attempts
   raise `McpProtocolError`. In-flight waiters are failed. Subsequent `close()`
   calls are no-ops.
8. **Bounded shutdown sequence:** `close()` shall: mark closed → fail pendings →
   stop accepting writes → close stdin if open → `terminate()` → wait up to
   `shutdown_timeout` (default **5s**) → `kill()` if still alive → wait → cancel
   reader tasks → clear process state. Each step must be safe if the process is
   already dead or streams already closed.
9. **Idempotent detach/close:** Public `close()` is idempotent. Internal process
   detachment (clearing `_process`, task handles, pending map) is also idempotent
   and may run from both normal close and process-exit paths.
10. **Restricted environment:** Child `env` is built from a platform allowlist of
    process-necessary variables plus `self.env` overlays. Full parent environment
    is **not** inherited by default.
11. **API compatibility:** `McpTransport.request(method, params=None)` signature
    stays; `McpStdioTransport(command, *, env=None)` gains optional kwargs only
    (`request_timeout`, optionally `shutdown_timeout`, `stderr_max_bytes`).
12. **Tests:** Automated coverage for malformed messages, process crash/exit,
    hangs/timeouts, concurrent calls, cancellation/timeout, and shutdown
    idempotence (see §6.4).

### Non-Functional Requirements

- No new third-party dependencies (stdlib `asyncio` / `json` / `os` only).
- Transport must not block the event loop on stderr fullness or on large
  concurrent waiter fan-out beyond O(pending) work.
- Structured errors via existing `McpProtocolError(..., details={...})` so agents
  and callers can diagnose without reading source.
- Existing attachment/bridge unit tests that mock `McpStdioTransport` continue to
  pass without mock API changes beyond optional unused kwargs.
- **Canonical full local CI:** `python scripts/run_ci.py` after
  `python -m pip install -e ".[dev]"`.
- Required remote checks: repository GitHub Actions CI on the draft PR must be green.

## 5. High-Level Design

### Decision: demultiplex by ID (not serialize)

Serialization would fix mis-association cheaply but would serialize all MCP tool
calls on one server. Agents commonly issue concurrent tools; demultiplexing
preserves concurrency while remaining correct.

```text
                    ┌─────────────────────────────────────┐
  request(A) ──────►│ pending[1] = Future_A               │
  request(B) ──────►│ pending[2] = Future_B               │
                    │                                     │
                    │  stdin writer (lock-protected)      │
                    │       │                             │
                    │       v                             │
                    │  child MCP process                  │
                    │       │ stdout (NDJSON)             │
                    │       v                             │
                    │  _stdout_reader loop                │
                    │    id=2 → set_result Future_B       │
                    │    id=1 → set_result Future_A       │
                    │    notify / unknown / dupe → drop   │
                    │                                     │
                    │  _stderr_reader loop (bounded buf)  │
                    └─────────────────────────────────────┘
```

### Lifecycle states

```text
  NEW ──start()──► RUNNING ──close()/exit──► CLOSED
                     │                         ▲
                     └──── process EOF ────────┘
```

- `RUNNING`: reader tasks active; requests accepted.
- `CLOSED`: no new requests; process ref cleared; close is no-op.

### Environment construction

```text
child_env = {k: os.environ[k] for k in ALLOWLIST if k in os.environ}
child_env.update(self.env or {})
```

Allowlist (illustrative; implemented as a frozen module-level tuple):

- **POSIX:** `PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TMPDIR`,
  `TERM`, `TZ`
- **Windows:** `PATH`, `PATHEXT`, `SYSTEMROOT`, `SYSTEMDRIVE`, `WINDIR`,
  `COMSPEC`, `TEMP`, `TMP`, `USERPROFILE`, `HOMEDRIVE`, `HOMEPATH`, `APPDATA`,
  `LOCALAPPDATA`, `USERNAME`, `NUMBER_OF_PROCESSORS`

Caller-supplied keys from `McpServerConfig.env` (API keys, preset env) always
override. This matches “pass only required environment variables” while still
allowing presets that inject credentials via `env=`.

## 6. Detailed Design

### 6.1 McpStdioTransport (hardened)

**Files:** `vidbyte/tools/mcp/transport.py`  
**Type:** Modified  

#### Responsibility

Owns the MCP child process, NDJSON framing on stdio, response demultiplexing,
stderr capture, request deadlines, and bounded shutdown.

#### Interface / API

```python
class McpTransport(Protocol):
    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        ...


class McpStdioTransport:
    def __init__(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        request_timeout: float = 30.0,
        shutdown_timeout: float = 5.0,
        stderr_max_bytes: int = 64 * 1024,
    ) -> None: ...

    async def start(self) -> None: ...
    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]: ...
    async def close(self) -> None: ...

    # Diagnostics (optional read-only helpers for tests / errors)
    @property
    def closed(self) -> bool: ...
    def stderr_snapshot(self) -> str: ...
```

`McpTransport` protocol remains request-only so existing fakes keep working.
`close()` stays a concrete method used by `McpServerHandle` and `attach.py`.

#### Logic / Algorithm

**`start()`**

1. If `_closed`: raise `McpProtocolError("MCP transport is closed")`.
2. If process already running: return.
3. Build restricted `child_env`.
4. Spawn subprocess with PIPEd stdin/stdout/stderr.
5. Create `_stdout_task` and `_stderr_task` on the running loop.
6. Initialize `_pending: dict[int, asyncio.Future[Mapping[str, Any]]] = {}`,
   `_write_lock = asyncio.Lock()`, `_id_lock` or single-threaded id increment
   under the write lock.

**`request(method, params)`**

1. If `_closed`: raise.
2. `await start()`.
3. Allocate `request_id` under write lock (monotonic int starting at 1).
4. Create Future; register in `_pending[request_id]`.
5. Write `json.dumps({jsonrpc, id, method, params}) + "\n"` under write lock;
   `drain()`.
6. `await asyncio.wait_for(future, timeout=self.request_timeout)`.
7. On timeout: pop pending if still present; cancel future; raise
   `McpProtocolError("MCP request timed out", details={method, id, timeout})`.
8. On success: validate result is a Mapping (already done in reader or here);
   return.
9. `finally`: ensure id is not left dangling in `_pending` if the future
   completed exceptionally via close/exit (pop is best-effort).

**`_stdout_reader` loop**

1. Read lines until EOF or cancellation.
2. Empty line / EOF → `_fail_all_pending("MCP server closed stdout")` and exit.
3. `json.loads`; on failure → record anomaly; continue (do not touch pendings).
4. If not a `dict`: discard; continue.
5. If `"id" not in message`: treat as notification / server push; discard;
   continue.
6. `rid = message["id"]`; if not int (or not matching type we send): discard.
7. Look up `_pending.pop(rid, None)`:
   - None → unknown or duplicate; discard.
   - Future done → discard (duplicate).
   - Else if `"error" in message`: `set_exception(McpProtocolError(...))`.
   - Else `result = message.get("result")`; if not Mapping:
     `set_exception(...)`; else `set_result(result)`.

**`_stderr_reader` loop**

1. Read chunks (or lines) until EOF/cancel.
2. Append to `bytearray` / deque of chunks; if total `> stderr_max_bytes`, drop
   oldest bytes so retained suffix length ≤ bound.
3. Never raise into the event loop from this task except cancellation.

**`close()`**

1. If already `_closed` and process cleared: return immediately (idempotent).
2. Set `_closed = True` first (gate new requests).
3. `_fail_all_pending("MCP transport closed")`.
4. Try close stdin (ignore errors).
5. If process is None: still cancel reader tasks; return.
6. If process still running: `terminate()`; wait up to `shutdown_timeout`; on
   timeout `kill()` and wait (bounded; ignore `ProcessLookupError`).
7. Cancel and await `_stdout_task` / `_stderr_task` with a short shield/timeout.
8. `_detach_process_state()` — set `_process = None`, clear task refs, clear
   pending (already empty). Safe to call twice.

**`_detach_process_state()` (internal “detach”)**

Idempotent clear of ownership fields after the OS process has been waited or
is known dead. Invoked from `close()` and from the stdout EOF path after
failing pendings. This satisfies “make detach and close idempotent” without
introducing a second public lifecycle API that would confuse attachment code.

#### Edge Cases & Error Handling

| Case | Behavior |
|------|----------|
| Concurrent `request` | Distinct ids; demux delivers correct futures. |
| Hang (no response) | Per-request timeout; pending entry removed. |
| Child crash mid-flight | stdout EOF / exit → all pending failed. |
| Notification mid-flight | Discarded; waiters unaffected. |
| Duplicate response id | Second discarded. |
| Unknown response id | Discarded. |
| Double `close()` | No-op after first. |
| `request` after `close` | `McpProtocolError`. |
| `terminate` already dead | Catch and continue to detach. |
| stderr flood | Bound enforced; no pipe deadlock. |
| Write after process death | `McpProtocolError` from write failure or start gate. |

---

### 6.2 attach_mcp_server timeout wiring

**Files:** `vidbyte/tools/mcp/attach.py`  
**Type:** Modified  

#### Responsibility

Construct the hardened transport with the server config timeout so post-init
calls share the same deadline policy.

#### Interface / API

No public signature change to `attach_mcp_server(config)`.

#### Logic / Algorithm

1. Construct:

```python
transport = McpStdioTransport(
    list(config.command),
    env=config.env,
    request_timeout=config.timeout,
)
```

2. Keep the existing `asyncio.timeout(config.timeout)` around `initialize()` as
   a belt-and-suspenders outer bound (harmless double-bound; initialize still
   fails fast). Prefer not to remove it in this change to minimize attach
   behavior risk.
3. On any failure path, `await transport.close()` remains (now idempotent).

#### Edge Cases & Error Handling

- `config.timeout <= 0`: leave validation as-is today (no new validation unless
  existing code already rejects). Optional follow-up: reject non-positive
  timeouts in `McpServerConfig` (out of scope unless already enforced).

---

### 6.3 Error details enrichment

**Files:** `vidbyte/lib/errors/base.py` (only if needed)  
**Type:** Unchanged preferred  

#### Responsibility

Continue using `McpProtocolError` with `details` dicts. No new exception types
unless implementation proves a distinct class is required for attach mapping.

#### Details keys (convention)

```python
{
  "method": str,
  "request_id": int,
  "timeout": float,          # on timeout
  "stderr_tail": str,        # truncated snapshot when useful
  "error": object,           # remote JSON-RPC error object
  "reason": str,             # closed | process_exited | ...
}
```

---

### 6.4 Transport tests

**Files:** `tests/test_mcp_stdio_transport.py`  
**Type:** Create  

#### Responsibility

Prove the hardening contracts without requiring live third-party MCP servers.
Use short-lived local subprocesses (`sys.executable -c ...` scripts) or
async-stream fakes injected via a test seam if needed.

#### Preferred strategy

Drive a real `McpStdioTransport` against tiny Python child programs printed to
stdout/stderr:

1. **Happy path** — echo `{"jsonrpc":"2.0","id":N,"result":{...}}` per line.
2. **Concurrent calls** — child replies out-of-order; both callers get correct
   results.
3. **Hang / timeout** — child never answers; `request` times out with small
   `request_timeout`.
4. **Process crash** — child exits after first reply; second pending fails.
5. **Malformed JSON** — garbage line then valid response for another id;
   waiter for the valid id still succeeds.
6. **Notification** — line with `method` and no `id` does not complete waiters.
7. **Unknown / duplicate id** — extra response lines do not crash the transport
   or corrupt other waiters.
8. **Stderr flood** — child writes > bound; transport remains responsive;
   `stderr_snapshot()` length ≤ bound.
9. **Shutdown** — `close()` twice is safe; `request` after close raises;
   pending cancelled/failed on close.
10. **Restricted env** — child prints selected env keys; assert a marker from
    parent `os.environ` that is **not** on the allowlist is absent, while a
    key passed via `env=` is present.
11. **Cancellation** — cancelling the waiting task removes/abandons the pending
    entry without leaving forever-stuck state (and does not break the reader).

#### Edge Cases & Error Handling

- Windows process termination timing differs; tests use generous but finite
  waits and avoid asserting exact kill path.
- Avoid flaky sleeps; prefer event-driven child scripts (`sys.stdin.readline`
  driven).

---

### 6.5 Public export surface

**Files:** `vidbyte/tools/mcp/__init__.py`  
**Type:** Modified only if new public helpers are exported  

Default: **no export change**. `McpStdioTransport` remains the public transport.
Do not export internal allowlists or reader helpers unless tests need them
via package-private names (`_INHERITED_ENV_KEYS`).

---

### 6.6 Documentation touch (optional, minimal)

**Files:** `vidbyte/tools/mcp/` folder README if one exists; else skip.  
**Type:** N/A if no dedicated MCP folder README beyond package headers  

Update the Context Protocol Header on `transport.py` to describe demux,
stderr drain, timeouts, and restricted env.

## 7. Data Model Changes

N/A — no persistent schemas, dataclasses, or migrations.  
`McpServerConfig.timeout` already models the single user-facing timeout.

Optional in-memory-only fields on `McpStdioTransport` instances (not public
dataclasses): `_pending`, `_closed`, `_stderr_buf`, task handles.

## 8. API Changes

| Surface | Change |
|---------|--------|
| `McpStdioTransport.__init__` | Additive optional kwargs: `request_timeout`, `shutdown_timeout`, `stderr_max_bytes`. |
| `McpStdioTransport.request` | Same signature; stronger concurrency/timeout semantics. |
| `McpStdioTransport.close` | Same signature; idempotent + pending fan-out + bounded kill. |
| `McpTransport` Protocol | Unchanged. |
| `attach_mcp_server` | Passes `request_timeout=config.timeout`. |
| `McpServerConfig` | Unchanged. |
| Deprecated APIs | None. |

**Breaking risk:** Callers that *relied* on full `os.environ` inheritance without
passing `env=` may see missing variables (e.g. custom `FOO=bar` in the shell).
Mitigation: document that MCP credentials and process-specific variables must be
passed via `McpServerConfig.env` / preset `required_env` (already the preset
pattern). Allowlist can be expanded if CI discovers legitimate gaps.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/harden-mcp-stdio-transport.md` | This design document (source of truth). |
| MODIFY | `vidbyte/tools/mcp/transport.py` | Demux reader, stderr drain, timeouts, restricted env, idempotent close. |
| MODIFY | `vidbyte/tools/mcp/attach.py` | Pass `request_timeout=config.timeout` into transport. |
| CREATE | `tests/test_mcp_stdio_transport.py` | Hardening scenarios: concurrent, hang, crash, malformed, notify, shutdown, env. |
| MODIFY | `tests/test_mcp_attachment.py` | Mock constructor accepts additive transport kwargs. |
| MODIFY | `tests/test_mcp_discovery_tools.py` | Mock constructor accepts additive transport kwargs. |
| MODIFY | `tests/test_agent_fork_isolation.py` | Mock constructor accepts additive transport kwargs. |

**Manifest counts:** 1 CREATE design + 1 CREATE tests + 2 MODIFY source + 3 MODIFY mocks = **7 files**.

No changes expected to `client.py`, `bridge.py`, `types.py`, `presets.py`, or
error modules unless implementation evidence forces a tiny adjustment (then
update this manifest in the same PR).

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `asyncio` | ≥3.11 (repo requires 3.11+) | Subprocess, tasks, futures, timeouts | Low — already used |
| Python stdlib `json` / `os` | stdlib | Framing and env allowlist | Low |
| External MCP servers | N/A | Not required for unit tests | N/A |
| New PyPI packages | None | — | None |

## 11. Rollout & Deployment

- **Rollout:** Merge as a normal library change on `main`. No feature flag.
  Behavior is transparent for sequential MCP use; concurrent use becomes
  correct; env inheritance tightens.
- **Compatibility:** Additive constructor kwargs; mock transports in existing
  tests unaffected.
- **Rollback:** Revert the PR. No data migration. Downstream users who began
  relying on demux concurrency simply lose concurrency safety again.
- **Ops note:** If a deployment depended on ambient secrets in the parent env
  without `config.env`, operators must pass those variables explicitly after
  upgrade.

## 12. Open Questions

- [ ] **Allowlist completeness:** Should Windows-only or CI-only variables beyond
  the listed set be included from day one (e.g. `PYTHONPATH`)?  
  **Proposal for approval:** Do **not** inherit `PYTHONPATH` by default (avoids
  leaking parent import paths into MCP children). Commands that need it must
  pass it via `env=`. Confirm or override at approval.
- [ ] **Public `detach()` method:** The request names “detach and close”. This
  design treats detach as an **internal** idempotent ownership clear, with
  public `close()` only.  
  **Proposal:** Keep detach internal unless you want a public no-kill detach
  for rare shared-process cases (non-goal today).
- [ ] **Timeout double-wrap on initialize:** Keep attach-level `asyncio.timeout`
  and transport-level timeout both, or remove attach-level after transport
  hardening?  
  **Proposal:** Keep both for minimal attach risk.

## 13. Alternatives Considered

### Serialize all requests with a single lock

- **What:** One global mutex around write+read of a full request/response pair
  (current shape, but exclusive).
- **Why rejected:** Fixes mis-association but forbids concurrent MCP tool calls
  on one server. Demux is only moderately more complex and matches real agent
  workloads.

### Full `os.environ` inheritance with a denylist

- **What:** Copy all env vars, drop secrets matching patterns.
- **Why rejected:** Denylists are incomplete by nature; allowlist + explicit
  `config.env` matches preset design (`required_env`) and the request’s
  “pass only required environment variables”.

### New exception types per failure mode

- **What:** `McpTimeoutError`, `McpTransportClosedError`, etc.
- **Why rejected for this change:** Existing `McpProtocolError` + `details`
  already carries structured context; attach paths already map broad exceptions
  to `McpInitializeError` / `McpConnectionError`. Can split later without
  blocking hardening.

### Content-Length framed MCP instead of NDJSON

- **What:** Support official MCP stdio Content-Length framing.
- **Why rejected as non-goal:** Current stack and studio server paths use
  newline-delimited JSON; framing migration is a separate protocol project.

---

## Implementation Checklist (post-approval)

1. Branch `feat/harden-mcp-stdio-transport` from clean current `main` in an
   isolated worktree.
2. Commit this design doc first.
3. Implement `transport.py` + `attach.py` wiring.
4. Add `tests/test_mcp_stdio_transport.py`.
5. Adversarial pass against Requirements §4 and Manifest §9.
6. Run full local CI: `python -m pip install -e ".[dev]"` then
   `python scripts/run_ci.py`.
7. Push, open **draft** PR with this doc as the body, watch required checks
   until green.
)
