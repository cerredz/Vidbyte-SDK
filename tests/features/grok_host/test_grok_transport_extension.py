"""FILE: tests/features/grok_host/test_grok_transport_extension.py

PURPOSE: The additive McpStdioTransport extension that Grok and Muse peers need (FR-15, D-3): the on_message callback and the dispatch fix, send_request, notify, respond, per-call timeout_seconds, exit_grace_seconds, stop_process_tree, and the invalid_call checks on every new value.
ROLE IN CODEBASE: Lives in grok_host because GrokHost is the extension's first user and no shared test file may be edited (spec §13). The existing tests/test_mcp_stdio_transport.py keeps proving INV-18 for the default options.
ARCHITECTURE NOTE: Each test runs a small inline Python child over real pipes, the _python_child prior art in tests/test_mcp_stdio_transport.py. Children record the frames they receive to a file, so the tests can check exactly what the transport wrote.
FUNCTION INVENTORY: python_child builds the child argv; read_frames parses a child's record file; the test_* functions each pin one §8.5 transport rule.
COMMON MODIFICATION PATTERNS: A new transport option gets a child behaviour in PEER_SOURCE and one test; invalid values join the invalid_call parametrisations.
WHAT NOT TO DO IN THIS FILE: 1. Do not edit or duplicate tests/test_mcp_stdio_transport.py; this file covers only the new surface. 2. Do not mock create_subprocess_exec here; every child is real.
KNOWN EDGE CASES: The dispatch-fix tests fail on the base transport even with default options, because today a frame with an int id resolves the pending request whether or not it carries a method. Process-group checks are POSIX-only; the bounded-close test runs everywhere and leaves a short-lived orphan on Windows (EC-10, Q-19).
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (transport extension), INV-18, EC-10
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_transport_extension.py
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from vidbyte.lib.errors import McpProtocolError
from vidbyte.tools.mcp.transport import McpStdioTransport

SLACK_SECONDS = 3.0
SHORT_SECONDS = 0.3
SHUTDOWN_SECONDS = 0.5
ORPHAN_SECONDS = 8
LIVENESS_SECONDS = 5.0
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="process groups and liveness checks are POSIX-only (EC-10)")

PEER_SOURCE = dedent(
    """
    import json, os, subprocess, sys, time
    record = open(sys.argv[1], "a", encoding="utf-8")
    marker = sys.argv[2]
    pending = None
    def send(frame):
        sys.stdout.write(json.dumps(frame) + "\\n")
        sys.stdout.flush()
    for raw in sys.stdin:
        frame = json.loads(raw)
        record.write(json.dumps(frame) + "\\n")
        record.flush()
        method = frame.get("method")
        if method == "echo":
            send({"jsonrpc": "2.0", "id": frame["id"], "result": {"echo": frame.get("params")}})
        elif method == "ask_back":
            send({"jsonrpc": "2.0", "id": frame["id"], "method": "server/ping", "params": {"n": 1}})
            send({"jsonrpc": "2.0", "method": "server/notice", "params": {"n": 2}})
            send({"jsonrpc": "2.0", "id": frame["id"], "result": {"answered": True}})
        elif method == "wait_for_go":
            pending = frame["id"]
        elif method == "go" and pending is not None:
            send({"jsonrpc": "2.0", "id": pending, "result": {"went": True}})
        elif method == "ids":
            send({"jsonrpc": "2.0", "id": frame["id"], "result": {"pid": os.getpid(), "pgid": os.getpgid(0) if hasattr(os, "getpgid") else -1}})
        elif method == "spawn":
            holds = frame["params"].get("hold_pipes", False)
            sleeper = [sys.executable, "-c", "import time; time.sleep(%d)" % frame["params"]["seconds"]]
            if holds:
                child = subprocess.Popen(sleeper)
            else:
                child = subprocess.Popen(sleeper, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            send({"jsonrpc": "2.0", "id": frame["id"], "result": {"grandchild": child.pid}})
    if marker != "-":
        time.sleep(0.3)
        open(marker, "w", encoding="utf-8").write("clean exit")
    """
)


def python_child(tmp_path: Path, marker: str = "-") -> tuple[list[str], Path]:
    record = tmp_path / f"frames-{len(list(tmp_path.glob('frames-*')))}.jsonl"
    return [sys.executable, "-u", "-c", PEER_SOURCE, str(record), marker], record


def read_frames(record: Path) -> list[dict[str, Any]]:
    if not record.exists():
        return []
    return [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines() if line.strip()]


def is_running(pid: int) -> bool:
    proc = Path("/proc") / str(pid) / "stat"
    if Path("/proc/self").exists():
        try:
            return proc.read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0] not in ("Z", "X")
        except OSError:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def stopped_within(pid: int, seconds: float) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        if not is_running(pid):
            return True
        await asyncio.sleep(0.05)
    return not is_running(pid)


@pytest.mark.asyncio
async def test_method_frame_with_a_pending_id_goes_to_on_message(tmp_path: Path) -> None:
    # Dispatch fix: a frame with a string method never resolves a pending request, even with the same int id.
    received: list[dict[str, Any]] = []
    command, _ = python_child(tmp_path)
    transport = McpStdioTransport(command, on_message=received.append)
    try:
        result = await transport.request("ask_back", {})
    finally:
        await transport.close()
    assert dict(result) == {"answered": True}
    assert [frame["method"] for frame in received] == ["server/ping", "server/notice"]
    assert received[0]["params"] == {"n": 1}


@pytest.mark.asyncio
async def test_method_frames_are_dropped_without_a_callback(tmp_path: Path) -> None:
    # Default options plus the dispatch fix (INV-18's one exception): the request still gets its real answer.
    command, _ = python_child(tmp_path)
    transport = McpStdioTransport(command)
    try:
        result = await transport.request("ask_back", {})
    finally:
        await transport.close()
    assert dict(result) == {"answered": True}


@pytest.mark.asyncio
async def test_callback_exception_drops_the_frame_and_the_reader_keeps_going(tmp_path: Path) -> None:
    # @intent mcp-stdio-callback-cannot-kill-reader: an Exception from on_message drops that frame only.
    seen: list[str] = []

    def explode_on_ping(frame: Any) -> None:
        seen.append(frame["method"])
        if frame["method"] == "server/ping":
            raise RuntimeError("callback bug")

    command, _ = python_child(tmp_path)
    transport = McpStdioTransport(command, on_message=explode_on_ping)
    try:
        first = await transport.request("ask_back", {})
        second = await transport.request("echo", {"again": True})
    finally:
        await transport.close()
    assert dict(first) == {"answered": True}
    assert dict(second) == {"echo": {"again": True}}
    assert seen == ["server/ping", "server/notice"]


@pytest.mark.asyncio
async def test_send_request_returns_a_future_once_the_frame_is_written(tmp_path: Path) -> None:
    # send_request returns after write and drain, before the answer; spawn_grok_session relies on it (INV-11).
    command, record = python_child(tmp_path)
    transport = McpStdioTransport(command)
    try:
        future = await transport.send_request("wait_for_go", {"x": 1})
        assert isinstance(future, asyncio.Future)
        assert not future.done()
        await transport.notify("go", {})
        result = await asyncio.wait_for(future, timeout=10)
    finally:
        await transport.close()
    assert dict(result) == {"went": True}
    assert [frame["method"] for frame in read_frames(record)] == ["wait_for_go", "go"]


@pytest.mark.asyncio
async def test_notify_and_respond_write_the_expected_frames(tmp_path: Path) -> None:
    command, record = python_child(tmp_path)
    transport = McpStdioTransport(command)
    try:
        await transport.notify("session/cancel", {"sessionId": "abc"})
        await transport.respond(7, result={"outcome": {"outcome": "cancelled"}})
        await transport.respond("perm-1", error={"code": -32601, "message": "Method not found"})
        await transport.request("echo", {})
    finally:
        await transport.close()
    notify, result, error, _ = read_frames(record)
    assert notify == {"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": "abc"}}
    assert result == {"jsonrpc": "2.0", "id": 7, "result": {"outcome": {"outcome": "cancelled"}}}
    assert error == {"jsonrpc": "2.0", "id": "perm-1", "error": {"code": -32601, "message": "Method not found"}}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"result": {"a": 1}, "error": {"code": 1, "message": "m"}}, {}], ids=["both", "neither"])
async def test_respond_needs_exactly_one_of_result_and_error(payload: dict[str, Any], tmp_path: Path) -> None:
    command, record = python_child(tmp_path)
    transport = McpStdioTransport(command)
    try:
        with pytest.raises(McpProtocolError) as caught:
            await transport.respond(3, **payload)
        await transport.request("echo", {})
    finally:
        await transport.close()
    assert caught.value.details["reason"] == "invalid_call"
    assert [frame.get("method") for frame in read_frames(record)] == ["echo"], "nothing was written for the invalid respond"


@pytest.mark.asyncio
async def test_per_call_timeout_overrides_the_transport_default(tmp_path: Path) -> None:
    # INV-3: request(..., timeout_seconds=) bounds this call only; reason stays "timeout".
    command, _ = python_child(tmp_path)
    transport = McpStdioTransport(command, request_timeout=30.0)
    try:
        started = time.monotonic()
        with pytest.raises(McpProtocolError) as caught:
            await transport.request("silent", {}, timeout_seconds=SHORT_SECONDS)
        elapsed = time.monotonic() - started
        echoed = await transport.request("echo", {"still": "usable"})
    finally:
        await transport.close()
    assert caught.value.details["reason"] == "timeout"
    assert elapsed < SHORT_SECONDS + SLACK_SECONDS
    assert dict(echoed) == {"echo": {"still": "usable"}}


BAD_SECONDS = [True, math.nan, math.inf, -math.inf, 0, -1, 86400.5, "1"]
BAD_SECONDS_IDS = ["bool", "nan", "inf", "minus-inf", "zero", "negative", "over-max", "str"]


async def _call_with_timeout(transport: McpStdioTransport, method: str, value: Any) -> Any:
    if method == "request":
        return await transport.request("echo", {}, timeout_seconds=value)
    if method == "send_request":
        return await transport.send_request("echo", {}, timeout_seconds=value)
    if method == "notify":
        return await transport.notify("note", {}, timeout_seconds=value)
    return await transport.respond(1, result={}, timeout_seconds=value)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["request", "send_request", "notify", "respond"])
@pytest.mark.parametrize("value", BAD_SECONDS, ids=BAD_SECONDS_IDS)
async def test_invalid_per_call_timeout_raises_invalid_call(method: str, value: Any, tmp_path: Path) -> None:
    # §8.5: RecordFieldValidator.require_number(maximum=NATIVE_STDIO_MAX_WAIT_SECONDS), re-raised as invalid_call.
    command, record = python_child(tmp_path)
    transport = McpStdioTransport(command)
    try:
        with pytest.raises(McpProtocolError) as caught:
            await _call_with_timeout(transport, method, value)
        await transport.request("echo", {})
    finally:
        await transport.close()
    assert caught.value.details["reason"] == "invalid_call"
    assert [frame.get("method") for frame in read_frames(record)] == ["echo"], "an invalid call writes nothing"


@pytest.mark.parametrize("value", BAD_SECONDS, ids=BAD_SECONDS_IDS)
def test_invalid_exit_grace_raises_invalid_call_at_construction(value: Any) -> None:
    with pytest.raises(McpProtocolError) as caught:
        McpStdioTransport([sys.executable, "-c", "pass"], exit_grace_seconds=value)
    assert caught.value.details["reason"] == "invalid_call"


@pytest.mark.parametrize("value", [1, 0, "yes", None], ids=["one", "zero", "str", "none"])
def test_non_bool_stop_process_tree_raises_invalid_call_at_construction(value: Any) -> None:
    with pytest.raises(McpProtocolError) as caught:
        McpStdioTransport([sys.executable, "-c", "pass"], stop_process_tree=value)
    assert caught.value.details["reason"] == "invalid_call"


@pytest.mark.asyncio
async def test_exit_grace_lets_the_child_finish_by_itself(tmp_path: Path) -> None:
    # D-23: after stdin EOF the transport waits up to exit_grace_seconds before stopping anything.
    marker = tmp_path / "clean-exit.txt"
    command, _ = python_child(tmp_path, marker=str(marker))
    transport = McpStdioTransport(command, exit_grace_seconds=10.0, shutdown_timeout=SHUTDOWN_SECONDS)
    await transport.request("echo", {})
    started = time.monotonic()
    await transport.close()
    elapsed = time.monotonic() - started
    assert marker.read_text(encoding="utf-8") == "clean exit", "the child was not stopped before it exited by itself"
    assert elapsed < 0.3 + SLACK_SECONDS


@pytest.mark.asyncio
@posix_only
async def test_stop_process_tree_starts_the_child_as_a_group_leader(tmp_path: Path) -> None:
    command, _ = python_child(tmp_path)
    transport = McpStdioTransport(command, stop_process_tree=True)
    try:
        ids = await transport.request("ids", {})
    finally:
        await transport.close()
    assert ids["pgid"] == ids["pid"], "start_new_session=True makes the child lead its own process group"


@pytest.mark.asyncio
@posix_only
async def test_close_stops_the_whole_tree_even_after_the_child_exited(tmp_path: Path) -> None:
    # EC-10: the tree stop runs whether or not the child already exited, so a grandchild in its group dies.
    command, _ = python_child(tmp_path)
    transport = McpStdioTransport(command, stop_process_tree=True, exit_grace_seconds=SHORT_SECONDS, shutdown_timeout=SHUTDOWN_SECONDS)
    spawned = await transport.request("spawn", {"seconds": 60})
    grandchild = spawned["grandchild"]
    assert is_running(grandchild)
    await transport.close()
    assert await stopped_within(grandchild, LIVENESS_SECONDS), "the grandchild in the peer's group must be stopped"


@pytest.mark.asyncio
async def test_close_is_bounded_when_a_grandchild_holds_the_pipes(tmp_path: Path) -> None:
    # EC-10: post-kill waits are bounded by shutdown_timeout, then the pipes are closed, so a pipe-holding grandchild cannot hang close.
    command, _ = python_child(tmp_path)
    transport = McpStdioTransport(command, stop_process_tree=True, exit_grace_seconds=SHORT_SECONDS, shutdown_timeout=SHUTDOWN_SECONDS)
    await transport.request("spawn", {"seconds": ORPHAN_SECONDS, "hold_pipes": True})
    started = time.monotonic()
    await asyncio.wait_for(transport.close(), timeout=SHORT_SECONDS + 2 * SHUTDOWN_SECONDS + SLACK_SECONDS + 5)
    elapsed = time.monotonic() - started
    assert elapsed < SHORT_SECONDS + 2 * SHUTDOWN_SECONDS + SLACK_SECONDS
    assert transport.closed
