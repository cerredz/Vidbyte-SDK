"""Verification script for feat/async-http-transport.

Covers every test case in Section 10 of docs/design/async-http-transport.md.
Run: python scripts/test-async-http-transport.py
Exit code 0 = all pass; non-zero = at least one failure.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import time
from pathlib import Path

# Ensure this worktree's vidbyte package takes precedence over any installed version.
sys.path.insert(0, str(Path(__file__).parent.parent))
import unittest
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0
_results: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    global PASS, FAIL
    _results.append((name, passed, detail))
    if passed:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def check(name: str, condition: bool, detail: str = "") -> None:
    record(name, condition, detail)


# ---------------------------------------------------------------------------
# Fake transport used throughout
# ---------------------------------------------------------------------------

class AsyncFakeTransport:
    """Async fake transport returning pre-configured responses."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.delay: float = 0.0  # optional simulated latency

    async def request(self, *, method: str, url: str, headers: Mapping[str, str],
                      json_body: Mapping[str, object] | None = None,
                      timeout_seconds: float = 60.0, **kwargs: Any) -> Any:
        from vidbyte.lib.http.transport import HttpResponse
        await asyncio.sleep(self.delay)
        self.calls.append({"method": method, "url": url, "headers": dict(headers),
                           "json_body": dict(json_body or {})})
        resp = self._responses.pop(0) if self._responses else {}
        status = resp.pop("__status__", 200)
        return HttpResponse(status_code=status, body=json.dumps(resp), headers={})


class ErrorFakeTransport:
    """Fake transport that raises on request."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def request(self, **kwargs: Any) -> Any:
        raise self._exc


# ---------------------------------------------------------------------------
# Section 6.1 — HttpTransport
# ---------------------------------------------------------------------------

print("\n-- HttpTransport -----------------------------------------------------")


async def _t_transport_is_coroutine() -> None:
    from vidbyte.lib.http.transport import HttpTransport
    t = HttpTransport()
    coro = t.request(method="GET", url="http://x", headers={})
    is_coro = inspect.iscoroutine(coro)
    coro.close()
    check("HttpTransport.request() returns a coroutine", is_coro)


asyncio.run(_t_transport_is_coroutine())


async def _t_sync_transport_is_not_coroutine() -> None:
    from vidbyte.lib.http.transport import SyncHttpTransport
    t = SyncHttpTransport()
    # SyncHttpTransport.request is a normal function, not async
    check("SyncHttpTransport.request() is NOT a coroutine function",
          not inspect.iscoroutinefunction(t.request))


asyncio.run(_t_sync_transport_is_not_coroutine())


async def _t_retry_short_circuits_on_success() -> None:
    """Retry loop must exit on first success even when retry_count > 0."""
    from vidbyte.lib.http.transport import HttpTransport, HttpResponse
    calls = []

    class OneSuccessTransport(HttpTransport):
        async def _send_once(self, client, **kwargs):
            calls.append(1)
            return HttpResponse(status_code=200, body="{}", headers={})

    t = OneSuccessTransport()
    result = await t.request(method="GET", url="http://x", headers={}, retry_count=5)
    check("HttpTransport retry short-circuits on first 200 (1 actual call)",
          len(calls) == 1 and result.status_code == 200)


asyncio.run(_t_retry_short_circuits_on_success())


async def _t_no_retry_on_429_when_retry_count_zero() -> None:
    from vidbyte.lib.http.transport import HttpTransport, HttpResponse
    calls = []

    class Always429(HttpTransport):
        async def _send_once(self, client, **kwargs):
            calls.append(1)
            return HttpResponse(status_code=429, body="{}", headers={})

    t = Always429()
    result = await t.request(method="GET", url="http://x", headers={}, retry_count=0)
    check("retry_count=0 produces exactly 1 attempt even for 429",
          len(calls) == 1 and result.status_code == 429)


asyncio.run(_t_no_retry_on_429_when_retry_count_zero())


async def _t_asyncio_sleep_not_time_sleep() -> None:
    """asyncio.sleep yields to other coroutines; verify it doesn't freeze the loop."""
    from vidbyte.lib.http.transport import HttpTransport, HttpResponse
    side_task_ran = []

    async def side_task():
        await asyncio.sleep(0)
        side_task_ran.append(True)

    class SlowOnFirstAttempt(HttpTransport):
        _attempt = 0

        async def _send_once(self, client, **kwargs):
            SlowOnFirstAttempt._attempt += 1
            if SlowOnFirstAttempt._attempt == 1:
                return HttpResponse(status_code=429, body="{}", headers={})
            return HttpResponse(status_code=200, body="{}", headers={})

    t = SlowOnFirstAttempt()
    await asyncio.gather(
        t.request(method="GET", url="http://x", headers={}, retry_count=1, backoff_seconds=0.01),
        side_task(),
    )
    check("asyncio.sleep in retry backoff yields to other coroutines",
          bool(side_task_ran))


asyncio.run(_t_asyncio_sleep_not_time_sleep())


async def _t_connect_error_raises_provider_request_error() -> None:
    import httpx
    from vidbyte.lib.http.transport import HttpTransport
    from vidbyte.lib.errors import ProviderRequestError

    class ConnectErrorTransport(HttpTransport):
        async def _send_once(self, client, **kwargs):
            raise httpx.ConnectError("refused")

    t = ConnectErrorTransport()
    try:
        await t.request(method="GET", url="http://x", headers={})
        check("ConnectError raises ProviderRequestError", False, "no exception raised")
    except ProviderRequestError:
        check("ConnectError raises ProviderRequestError", True)
    except Exception as exc:
        check("ConnectError raises ProviderRequestError", False, type(exc).__name__)


asyncio.run(_t_connect_error_raises_provider_request_error())


# ---------------------------------------------------------------------------
# Section 6.5 — TextModelRunner
# ---------------------------------------------------------------------------

print("\n-- TextModelRunner ---------------------------------------------------")

from vidbyte.lib.config import TextModelConfig, ModelProvider
from vidbyte.lib.runners import TextModelRunner


def _make_text_runner(responses: list[dict]) -> tuple[TextModelRunner, AsyncFakeTransport]:
    transport = AsyncFakeTransport(responses)
    runner = TextModelRunner(
        TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"),
        transport=transport,
    )
    return runner, transport


def _t_run_sync_works() -> None:
    """TextModelRunner.run() from sync context should return text."""
    runner, _ = _make_text_runner([{"output_text": "hello"}])
    result = runner.run("ping")
    check("TextModelRunner.run() works from sync context", result.text == "hello")


_t_run_sync_works()


def _t_arun_exists_and_is_coroutinefunction() -> None:
    runner, _ = _make_text_runner([])
    check("TextModelRunner.arun() exists and is a coroutine function",
          hasattr(runner, "arun") and inspect.iscoroutinefunction(runner.arun))


_t_arun_exists_and_is_coroutinefunction()


async def _t_arun_returns_correct_text() -> None:
    runner, _ = _make_text_runner([{"output_text": "world"}])
    result = await runner.arun("ping")
    check("TextModelRunner.arun() returns TextModelResponse with correct text",
          result.text == "world")


asyncio.run(_t_arun_returns_correct_text())


async def _t_invoke_runner_prefers_arun() -> None:
    """BaseAgent._invoke_runner checks arun before run; verify arun is chosen."""
    from vidbyte.agents.base import BaseAgent

    arun_called = []
    run_called = []

    class TrackingRunner:
        _config = None

        async def arun(self, prompt: str, **kwargs: Any):
            arun_called.append(True)
            from vidbyte.lib.runners.types import TextModelResponse
            return TextModelResponse(provider=ModelProvider.OPENAI, model="x", text="ok", raw={})

        def run(self, prompt: str, **kwargs: Any):
            run_called.append(True)
            from vidbyte.lib.runners.types import TextModelResponse
            return TextModelResponse(provider=ModelProvider.OPENAI, model="x", text="ok", raw={})

    # Call _invoke_runner directly on a fresh instance without going through the agent loop.
    agent = BaseAgent(name="test", system_prompt="sp", runner=TrackingRunner())
    await agent._invoke_runner(TrackingRunner(), "hello")
    check("BaseAgent._invoke_runner() uses arun() when available, not run()",
          bool(arun_called) and not bool(run_called))


asyncio.run(_t_invoke_runner_prefers_arun())



async def _t_run_raises_in_event_loop() -> None:
    """TextModelRunner.run() must raise when called from inside a running loop."""
    from vidbyte.lib.errors import AgentExecutionError
    runner, _ = _make_text_runner([])
    try:
        runner.run("ping")
        check("TextModelRunner.run() raises AgentExecutionError inside event loop", False, "no exception")
    except AgentExecutionError:
        check("TextModelRunner.run() raises AgentExecutionError inside event loop", True)
    except Exception as exc:
        check("TextModelRunner.run() raises AgentExecutionError inside event loop", False, type(exc).__name__)


asyncio.run(_t_run_raises_in_event_loop())


# ---------------------------------------------------------------------------
# Section 6.6 — ImageModelRunner
# ---------------------------------------------------------------------------

print("\n-- ImageModelRunner --------------------------------------------------")

from vidbyte.lib.config import ImageModelConfig
from vidbyte.lib.runners import ImageModelRunner


def _t_image_arun_exists() -> None:
    transport = AsyncFakeTransport([])
    runner = ImageModelRunner(
        ImageModelConfig(provider=ModelProvider.OPENAI, model="img-test", api_key="key"),
        transport=transport,
    )
    check("ImageModelRunner.arun() exists and is a coroutine function",
          hasattr(runner, "arun") and inspect.iscoroutinefunction(runner.arun))


_t_image_arun_exists()


async def _t_image_arun_returns_images() -> None:
    transport = AsyncFakeTransport([{"data": [{"url": "https://img.test/x.png"}]}])
    runner = ImageModelRunner(
        ImageModelConfig(provider=ModelProvider.OPENAI, model="img-test", api_key="key"),
        transport=transport,
    )
    result = await runner.arun("draw a cat")
    check("ImageModelRunner.arun() returns ImageModelResponse with correct url",
          result.images[0].url == "https://img.test/x.png")


asyncio.run(_t_image_arun_returns_images())


# ---------------------------------------------------------------------------
# Section 6.7 — VideoModelRunner
# ---------------------------------------------------------------------------

print("\n-- VideoModelRunner --------------------------------------------------")

from vidbyte.lib.config import VideoModelConfig
from vidbyte.lib.runners import VideoModelRunner


async def _t_video_arun_and_astatus() -> None:
    transport = AsyncFakeTransport([
        {"id": "job_99", "status": "queued"},
        {"id": "job_99", "status": "completed"},
    ])
    runner = VideoModelRunner(
        VideoModelConfig(provider=ModelProvider.OPENAI, model="sora-test", api_key="key"),
        transport=transport,
    )
    created = await runner.arun("make a film")
    polled = await runner.astatus(created.job_id)
    check("VideoModelRunner.arun() returns queued job", created.status == "queued")
    check("VideoModelRunner.astatus() returns updated status", polled.status == "completed")


asyncio.run(_t_video_arun_and_astatus())


# ---------------------------------------------------------------------------
# Section 6.8 — BaseMemoryTool
# ---------------------------------------------------------------------------

print("\n-- BaseMemoryTool ----------------------------------------------------")


async def _t_memory_tool_awaits_transport() -> None:
    """_json_post must await the transport call — verify side-effect occurs."""
    from vidbyte.tools.builtins.memory.supermemory import SupermemoryAddMemoryTool
    from vidbyte.tools.types import ToolCall

    transport = AsyncFakeTransport([{"id": "doc_abc"}])
    tool = SupermemoryAddMemoryTool("key123")
    tool._transport = transport

    call = ToolCall(tool_name="supermemory_add_memory",
                    arguments={"content": "remember this"})
    result = await tool.execute(call)
    check("BaseMemoryTool._json_post awaits transport (request recorded)",
          len(transport.calls) == 1)
    check("BaseMemoryTool._json_post produces ToolResult.SUCCESS",
          result.status.value == "success")


asyncio.run(_t_memory_tool_awaits_transport())


# ---------------------------------------------------------------------------
# Section 6.1 — SyncHttpTransport export
# ---------------------------------------------------------------------------

print("\n-- SyncHttpTransport export ------------------------------------------")


def _t_sync_transport_exported() -> None:
    from vidbyte.lib.http import SyncHttpTransport
    from vidbyte.lib.http.transport import HttpResponse
    t = SyncHttpTransport()
    check("SyncHttpTransport is importable from vidbyte.lib.http", True)
    check("SyncHttpTransport.request() is not a coroutine function",
          not inspect.iscoroutinefunction(t.request))


_t_sync_transport_exported()


# ---------------------------------------------------------------------------
# ParallelPipeline concurrency proof
# ---------------------------------------------------------------------------

print("\n-- ParallelPipeline concurrency --------------------------------------")


async def _t_concurrent_arun_calls() -> None:
    """Two TextModelRunner.arun() calls via asyncio.gather should overlap in wall time."""
    LATENCY = 0.1

    class DelayedTransport:
        async def request(self, **kwargs: Any) -> Any:
            from vidbyte.lib.http.transport import HttpResponse
            await asyncio.sleep(LATENCY)
            return HttpResponse(200, json.dumps({"output_text": "done"}), {})

    config = TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key")
    r1 = TextModelRunner(config, transport=DelayedTransport())
    r2 = TextModelRunner(config, transport=DelayedTransport())

    t0 = time.monotonic()
    results = await asyncio.gather(r1.arun("a"), r2.arun("b"))
    elapsed = time.monotonic() - t0

    check("Two arun() calls via asyncio.gather overlap (wall time < 1.5x single latency)",
          elapsed < LATENCY * 1.5,
          f"elapsed={elapsed:.3f}s threshold={LATENCY * 1.5:.3f}s")
    check("Both arun() calls return correct text", all(r.text == "done" for r in results))


asyncio.run(_t_concurrent_arun_calls())


# ---------------------------------------------------------------------------
# Provider coroutine check (spot-check Anthropic and OpenAI)
# ---------------------------------------------------------------------------

print("\n-- Provider methods are coroutine functions --------------------------")


def _t_provider_methods_are_async() -> None:
    from vidbyte.providers.anthropic import AnthropicProvider
    from vidbyte.providers.openai import OpenAIProvider
    from vidbyte.providers.gemini import GeminiProvider
    from vidbyte.providers.compatible import OpenAICompatibleProvider

    checks = [
        ("AnthropicProvider.run_text", inspect.iscoroutinefunction(AnthropicProvider.run_text)),
        ("OpenAIProvider.run_text", inspect.iscoroutinefunction(OpenAIProvider.run_text)),
        ("OpenAIProvider.run_image", inspect.iscoroutinefunction(OpenAIProvider.run_image)),
        ("OpenAIProvider.create_video", inspect.iscoroutinefunction(OpenAIProvider.create_video)),
        ("OpenAIProvider.get_video_status", inspect.iscoroutinefunction(OpenAIProvider.get_video_status)),
        ("GeminiProvider.run_text", inspect.iscoroutinefunction(GeminiProvider.run_text)),
        ("OpenAICompatibleProvider.run_text", inspect.iscoroutinefunction(OpenAICompatibleProvider.run_text)),
    ]
    for name, result in checks:
        check(f"{name}() is async def", result)


_t_provider_methods_are_async()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"{PASS + FAIL} tests run — {PASS} passed, {FAIL} failed")
print('='*60)

if FAIL:
    import sys
    sys.exit(1)
