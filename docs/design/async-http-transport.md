# Design Doc: Async HTTP Transport

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-29
**Last Updated:** 2026-05-29

---

## 1. Overview

Replace the synchronous `urllib`-based `HttpTransport.request()` with an async implementation backed by `httpx.AsyncClient`. Propagate the `async` keyword up through all provider `run_text()` / `run_image()` / `create_video()` / `get_video_status()` methods, `BaseMemoryTool` HTTP helpers, and the three runner classes (`TextModelRunner`, `ImageModelRunner`, `VideoModelRunner`). This restores `ParallelPipeline`'s concurrency guarantee and prevents every model call from freezing the asyncio event loop.

---

## 2. Goals & Non-Goals

### Goals
- `HttpTransport.request()` yields control to the event loop while waiting for a network response
- `asyncio.gather()` in `ParallelPipeline` produces actual wall-clock parallelism across model calls
- `time.sleep()` in the retry backoff is replaced with `asyncio.sleep()` so the event loop can schedule other work during retries
- All existing public sync entry points (`TextModelRunner.run()`, `ImageModelRunner.run()`, `VideoModelRunner.run()` / `.status()`, `BaseAgent.run()`) continue to work unchanged from call sites
- `httpx` promoted from implicit test dependency to declared runtime dependency
- `SyncHttpTransport` preserved and exported for test injection and any sync callers that inject a custom transport

### Non-Goals
- Changing the retry policy ownership (HTTP-level vs middleware-level retries); noted as a follow-up
- Persistent connection pooling (httpx client per-request is sufficient for this change)
- Streaming responses
- Changing any provider's payload shape or API contract

---

## 3. Background & Context

`AgentRuntime._arun_once()` is async and dispatches model calls through `await invoke_runner(runner, message, ...)`. `invoke_runner` resolves to `BaseAgent._invoke_runner()`, which prefers `runner.arun()` if present, otherwise falls back to `runner.run()`. `TextModelRunner` currently only has `run()`, which calls `provider.run_text()`, which calls `transport.request()` — a blocking `urllib.request.urlopen()` call. This call occupies the event loop thread for the full duration of the HTTP round trip (3–15 seconds for a typical model API call), preventing any other coroutines from executing. `ParallelPipeline` wraps agents in `asyncio.gather()`, but because the model calls block the thread, the gather effectively serializes them. The `time.sleep()` in `HttpTransport`'s retry backoff has the same problem.

---

## 4. Requirements

### Functional Requirements
1. `HttpTransport.request()` must be `async def` and must not block the event loop thread
2. All provider `run_text()`, `run_image()`, `create_video()`, and `get_video_status()` methods must be `async def`
3. `BaseMemoryTool._json_post()`, `_json_get()`, `_json_delete()` must `await` the transport call
4. `TextModelRunner` must expose `async def arun()` so `BaseAgent._invoke_runner()` uses the async path automatically
5. `TextModelRunner.run()` must remain callable from sync code and produce the same return type
6. `ImageModelRunner` and `VideoModelRunner` must expose `arun()` (and `astatus()` for video)
7. `SyncHttpTransport` must be exported from `vidbyte.lib.http` for test double injection
8. All existing unit tests must pass without behavior regression

### Non-Functional Requirements
- No new public API surfaces beyond `arun()` on runners and `SyncHttpTransport`
- Retry backoff sleeps must be non-blocking (`asyncio.sleep`)
- `httpx>=0.27` added to `[project].dependencies` in `pyproject.toml`

---

## 5. High-Level Design

`HttpTransport.request()` becomes `async def` and dispatches HTTP calls via `httpx.AsyncClient`. The client is created per call with `async with httpx.AsyncClient()` — this avoids lifecycle management complexity while still releasing the event loop during I/O. The internal `_send_once()` helper becomes async and uses `client.request()`. The retry backoff switches from `time.sleep()` to `await asyncio.sleep()`.

All six provider classes (`AnthropicProvider`, `OpenAIProvider`, `GeminiProvider`, `OpenAICompatibleProvider`, `XAIProvider`, `OpenRouterProvider`) have their HTTP-calling methods converted to `async def`. Since providers accept a `transport` argument and immediately call `transport.request()`, the only change is adding `async def` and `await`.

The three runner classes add an `async def arun()` method that awaits the provider call. `BaseAgent._invoke_runner()` already checks for `arun` before `run`, so the async path is used automatically with no changes to `BaseAgent`. The existing `run()` methods on all three runners are updated to `asyncio.run(self.arun(...))`, so they remain callable from sync contexts.

`SyncHttpTransport` retains the original urllib-based implementation as a named export for test injection. Tests update their anonymous `FakeTransport.request()` stubs to `async def`.

```
[BaseAgent._invoke_runner()]  ← checks arun() first
          |
          v
[TextModelRunner.arun()]   (new async method)
          |
          v
[AnthropicProvider.run_text()]  (now async)
          |
          v
[HttpTransport.request()]  (now async, httpx)
          |
          v
  [httpx.AsyncClient]  ← releases event loop during I/O
```

---

## 6. Detailed Design

### 6.1 HttpTransport

**File:** `vidbyte/lib/http/transport.py`
**Type:** Modified

#### What it does
Async HTTP transport using httpx. One client per request via `async with`. Retry loop uses `await asyncio.sleep()`.

#### Interface / API
```python
class HttpTransport:
    async def request(self, *, method: str, url: str, headers: Mapping[str, str],
                      json_body: Mapping[str, object] | None = None,
                      timeout_seconds: float = 60.0, retry_count: int = 0,
                      backoff_seconds: float = 0.5, backoff_multiplier: float = 2.0,
                      retry_status_codes: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504)) -> HttpResponse: ...
    async def _send_once(self, client: httpx.AsyncClient, ...) -> HttpResponse: ...

class SyncHttpTransport:
    def request(self, *, method: str, url: str, headers: Mapping[str, str],
                json_body: Mapping[str, object] | None = None,
                timeout_seconds: float = 60.0, **kwargs: object) -> HttpResponse: ...
```

#### Logic / Algorithm
1. `request()`: compute `attempts = max(0, retry_count) + 1`; open `async with httpx.AsyncClient()` once per outer call
2. Loop `attempts` times: call `await self._send_once(client, ...)`, return if status not in retry set or last attempt, else `await asyncio.sleep(delay)` and multiply delay
3. `_send_once()`: build `httpx.Request`, call `await client.send(request, timeout=timeout_seconds)`, return `HttpResponse`; catch `httpx.HTTPStatusError` for HTTP errors (httpx raises by default only if `raise_for_status()` called — don't call it, read status directly); catch `httpx.RequestError` and re-raise as `ProviderRequestError`

#### Edge Cases & Error Handling
- `httpx.ConnectError`, `httpx.TimeoutException` → wrapped in `ProviderRequestError` (same behavior as urllib `URLError`)
- HTTP error status codes → returned as `HttpResponse` with that status (same as current urllib `HTTPError` handling)
- `retry_count=0` → single attempt, no retry loop

### 6.2 SyncHttpTransport

**File:** `vidbyte/lib/http/transport.py`
**Type:** New class (same file)

#### What it does
Preserves the original urllib-based sync behavior. Used as test double and exported for external callers that need sync injection.

#### Interface / API
```python
class SyncHttpTransport:
    def request(self, *, method: str, url: str, headers: Mapping[str, str],
                json_body: Mapping[str, object] | None = None,
                timeout_seconds: float = 60.0, **kwargs: object) -> HttpResponse: ...
```

### 6.3 HttpTransport __init__.py export

**File:** `vidbyte/lib/http/__init__.py`
**Type:** Modified

Add `SyncHttpTransport` to `__all__` and the import.

### 6.4 Provider methods (all six providers)

**Files:**
- `vidbyte/providers/anthropic.py` — `run_text()`
- `vidbyte/providers/openai.py` — `run_text()`, `run_image()`, `create_video()`, `get_video_status()`
- `vidbyte/providers/gemini.py` — `run_text()`
- `vidbyte/providers/compatible.py` — `OpenAICompatibleProvider.run_text()`
- `vidbyte/providers/xai.py` — `run_image()`
- `vidbyte/providers/openrouter.py` — `run_text()`

**Type:** Modified

#### What it does
Each method gains `async def` and `await` before `transport.request(...)`. No logic changes.

#### Interface / API
```python
# Before
def run_text(self, *, prompt, system, metadata, transport, config) -> TextModelResponse: ...
# After
async def run_text(self, *, prompt, system, metadata, transport, config) -> TextModelResponse: ...
```

### 6.5 TextModelRunner

**File:** `vidbyte/lib/runners/text.py`
**Type:** Modified

#### What it does
Adds `async def arun()` which `BaseAgent._invoke_runner()` will detect and use. Updates `run()` to `asyncio.run(self.arun(...))`.

#### Interface / API
```python
class TextModelRunner:
    async def arun(self, prompt: str, *, system: str | None = None,
                   metadata: Mapping[str, object] | None = None,
                   tools: Iterable[Mapping[str, Any]] = (),
                   tool_choice: str | Mapping[str, Any] | None = None,
                   messages: Iterable[Mapping[str, Any]] = ()) -> TextModelResponse: ...
    def run(self, prompt: str, ...) -> TextModelResponse: ...  # wraps asyncio.run(self.arun(...))
```

#### Logic / Algorithm
1. `arun()`: build `call_config` (same as current `run()`), `return await self._provider.run_text(...)`
2. `run()`: check if a loop is already running (guard against nested `asyncio.run()`), call `asyncio.run(self.arun(prompt, ...))`

#### Edge Cases & Error Handling
- `run()` raises `RuntimeError` if called from inside a running event loop (same as current `BaseAgent.run()` guard)

### 6.6 ImageModelRunner

**File:** `vidbyte/lib/runners/image.py`
**Type:** Modified

Same pattern as TextModelRunner: add `async def arun()`, update `run()` to call `asyncio.run(self.arun(...))`.

### 6.7 VideoModelRunner

**File:** `vidbyte/lib/runners/video.py`
**Type:** Modified

Add `async def arun()` (wraps `create_video`) and `async def astatus()` (wraps `get_video_status`). Update `run()` and `status()` to call `asyncio.run(...)`.

### 6.8 BaseMemoryTool

**File:** `vidbyte/tools/builtins/memory/base.py`
**Type:** Modified

#### What it does
`_json_post()`, `_json_get()`, and `_json_delete()` are already `async def` but currently call `self._transport.request()` synchronously. Add `await` before the transport call.

#### Interface / API
No change to signatures — methods are already `async def`.

### 6.9 pyproject.toml

**File:** `pyproject.toml`
**Type:** Modified

Add `httpx>=0.27` to `[project].dependencies`.

### 6.10 Test fake transports

**Files:**
- `tests/test_text_model_runner.py`
- `tests/test_image_video_runners.py`
- `tests/test_openrouter_provider.py`
- `tests/test_memory_tools.py`

**Type:** Modified

Each `FakeTransport.request()` / `MockTransport.request()` stub becomes `async def request(...)` returning the same `HttpResponse`. The test class and test method signatures do not change (sync `TestCase` methods call `runner.run()` which calls `asyncio.run()` internally).

---

## 7. Data Model Changes

N/A — no schema or dataclass changes.

---

## 8. API Changes

N/A — no external HTTP endpoints added or modified.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `pyproject.toml` | Add `httpx>=0.27` runtime dependency |
| MODIFY | `vidbyte/lib/http/transport.py` | Replace urllib with httpx async; add SyncHttpTransport |
| MODIFY | `vidbyte/lib/http/__init__.py` | Export SyncHttpTransport |
| MODIFY | `vidbyte/providers/anthropic.py` | Make `run_text()` async |
| MODIFY | `vidbyte/providers/openai.py` | Make `run_text()`, `run_image()`, `create_video()`, `get_video_status()` async |
| MODIFY | `vidbyte/providers/gemini.py` | Make `run_text()` async |
| MODIFY | `vidbyte/providers/compatible.py` | Make `OpenAICompatibleProvider.run_text()` async |
| MODIFY | `vidbyte/providers/xai.py` | Make `run_image()` async |
| MODIFY | `vidbyte/providers/openrouter.py` | Make `run_text()` async |
| MODIFY | `vidbyte/lib/runners/text.py` | Add `arun()`, update `run()` to asyncio.run wrapper |
| MODIFY | `vidbyte/lib/runners/image.py` | Add `arun()`, update `run()` to asyncio.run wrapper |
| MODIFY | `vidbyte/lib/runners/video.py` | Add `arun()`, `astatus()`; update sync wrappers |
| MODIFY | `vidbyte/tools/builtins/memory/base.py` | Add `await` to transport calls in `_json_post/get/delete` |
| MODIFY | `tests/test_text_model_runner.py` | Make FakeTransport.request() async |
| MODIFY | `tests/test_image_video_runners.py` | Make FakeTransport.request() async |
| MODIFY | `tests/test_openrouter_provider.py` | Make FakeTransport.request() async |
| MODIFY | `tests/test_memory_tools.py` | Make MockTransport.request() async |

---

## 10. Testing Plan

### Unit Tests

- `describe('HttpTransport')` → `it('returns HttpResponse for 200 from a real-like httpx response')` — [Hidden Assumption: sync tests assumed urllib; now verifies async path produces same shape]
- `describe('HttpTransport')` → `it('retries the configured number of times on retry_status_codes and sleeps without blocking')` — [Hidden Failure: time.sleep was blocking; asyncio.sleep must not block]
- `describe('HttpTransport')` → `it('raises ProviderRequestError on connection error (httpx.ConnectError)')` — [Edge Case]
- `describe('HttpTransport')` → `it('returns the response immediately on first success even when retry_count > 0')` — [Silent Failure: retry loop must short-circuit on success]
- `describe('HttpTransport')` → `it('does not retry when retry_count=0 even for a 429 status')` — [Edge Case]
- `describe('TextModelRunner')` → `it('run() works from a synchronous context (no event loop) and returns text')` — [Hidden Assumption: asyncio.run() guard]
- `describe('TextModelRunner')` → `it('arun() is detected and called by BaseAgent._invoke_runner() over run()')` — [Hidden Failure: ensure BaseAgent picks async path]
- `describe('ImageModelRunner')` → `it('arun() resolves image response correctly')` — [Hidden Assumption]
- `describe('VideoModelRunner')` → `it('arun() and astatus() resolve job fields correctly')` — [Hidden Assumption]
- `describe('BaseMemoryTool')` → `it('_json_post awaits transport call and returns (status, dict)')` — [Hidden Failure: previously called sync request in async def without await]
- `describe('ParallelPipeline')` → `it('two concurrent agent calls do not serialize — wall time is max, not sum')` — [Hidden Failure: the key correctness invariant of this entire change]
- `describe('AnthropicProvider')` → `it('run_text() is a coroutine — calling it without await returns a coroutine object')` — [Silent Failure: if not async, it silently returned a non-awaitable]

### Integration Tests
- End-to-end: `ParallelPipeline` with two fake agents backed by async fake transport — verify `asyncio.gather()` interleaves correctly (use `asyncio.sleep` inside fake transport to prove overlap)
- `ModelRetryMiddleware` + `HttpTransport` retry: verify total sleep is not additive when both retry the same error; document known double-sleep as a follow-up

### Manual / QA Test Cases
1. Given a `TextModelRunner` with a real Anthropic API key, when `runner.run("hello")` is called from a Python script, then it returns text without hanging — [Hidden Assumption: asyncio.run() wrapper works in a script context]
2. Given a `ParallelPipeline` with two `BaseAgent` instances, when `.run("prompt")` is called, then both agents make their model calls concurrently (verify via timing or asyncio task inspection) — [Hidden Failure: was serializing before this fix]
3. Given a `BaseAgent.run()` called from a Jupyter notebook cell (which runs an event loop), then it raises a clear error rather than deadlocking — [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `httpx` | `>=0.27` | Async HTTP client replacing urllib | Low — httpx is stable and widely used; was already implicitly present in test environment |

---

## 12. Rollout & Deployment

- No feature flags. This is a correctness fix with no behavioral change from the user's perspective.
- Not a breaking change: all public sync entry points (`runner.run()`, `agent.run()`) retain the same signature and return type.
- `SyncHttpTransport` is added as a named export — no removal of `HttpTransport`.
- `httpx` must be installed in any environment running the SDK. If an environment pins deps strictly, adding `httpx` is the only change needed.
- Rollback: revert the branch. The old urllib-based code is preserved in git history.

---

## 13. Open Questions

- [ ] Should `HttpTransport`'s internal retry loop be scoped to network-layer errors only (removing HTTP status code retries from transport) to eliminate the additive sleep interaction with `ModelRetryMiddleware`? Proposed as a follow-up — not in this scope.
- [ ] Should `httpx.AsyncClient` be long-lived (constructed once, shared across calls) for connection reuse? Currently a per-call client is used for simplicity. A shared client would require explicit teardown (context manager or `aclose()`), complicating test injection.

---

## 14. Alternatives Considered

### Alternative 1: `asyncio.to_thread()` at TextModelRunner
- **What:** Wrap `self._provider.run_text(...)` in `asyncio.to_thread()` in `TextModelRunner.run()`, keeping transport and providers sync.
- **Why rejected:** Runs in a thread pool, introducing thread-safety requirements on `HttpTransport` state and urllib connection objects. Under high parallelism (e.g., 20 agents), spawns 20+ threads vs. 20 coroutines. Does not fix `time.sleep()` in the retry loop. httpx async is the architecturally correct solution and is lower cost under concurrency.

### Alternative 2: Keep `request()` sync, add `request_async()` as a parallel method
- **What:** Providers grow both `run_text()` (sync) and `run_text_async()` (async) methods. Runners choose which to call.
- **Why rejected:** Doubles the surface area for all six providers. Any logic bug gets fixed in only one path. The user confirmed no sync public surface consumes `run_text()` directly, so there is no caller to protect.
