"""FILE: tests/features/coding_agent/test_bash_tool_process_bounds.py

PURPOSE: Prove every bash call returns in bounded time and leaves nothing behind that it promised to stop: the time limit, the process-group kill, the bounded wait after the kill, the closed pipe, and cancellation that always propagates.
ROLE IN CODEBASE: Runs vidbyte.tools.builtins.bash.BashTool on real processes, directly and once through BaseAgent's runtime with ToolSettings.tool_timeout_seconds; liveness is read from /proc on Linux.
ARCHITECTURE NOTE: BASH_TIMEOUT_SECONDS and BASH_KILL_GRACE_SECONDS are patched to seconds, as spec §13 allows, so the bounds are observable without waiting minutes. Each timing assertion is an upper bound with fixed slack; nothing sleeps a fixed time, it polls for a pid file or a stopped process.
FUNCTION INVENTORY: test_command_past_the_time_limit_* (AC-27, AC-14, EC-8); test_time_limit_kills_* (AC-14, EC-9); test_command_that_closes_its_output_* (AC-24, EC-28); test_setsid_descendant_* (AC-25, EC-30); test_background_process_* (AC-26, INV-25); test_endless_printer_* (AC-29, EC-10); test_timed_out_call_closes_* (AC-28, INV-26); test_cancelled_call_* (INV-12, AC-15); test_cancellation_kills_* (AC-15, EC-29); test_agent_tool_timeout_* (AC-15, EC-29).
COMMON MODIFICATION PATTERNS: A new stop path gets one command that would outlive it, a pid printed or written to a file, an upper-bound timing assertion, and a liveness check; kill leftovers in finally.
WHAT NOT TO DO IN THIS FILE: 1. Do not call os.kill on Windows hosts; there it terminates processes, so liveness checks are POSIX-only. 2. Do not raise the slack to make a slow implementation pass; the bound is the contract.
KNOWN EDGE CASES: On Python 3.11 Process.wait() returns at shell exit even while a setsid descendant holds the pipe, so AC-25 is an upper bound there and a real wait on 3.12+. On Windows only Git's launcher can be killed (EC-14), so Windows checks timing and cleanup of the pipe, never that the command stopped. A killed process is a zombie until reaped; zombies count as stopped.
RELATED DOCS: tests/features/coding_agent/FEATURE.md; docs/spec/coding-agent/spec.md (§6.1 INV-10 to INV-12, INV-25, INV-26; §6.2 AC-14, AC-15, AC-24 to AC-29; §8.1 D-14, D-17, D-18, D-19)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_bash_tool_process_bounds.py
"""

from __future__ import annotations

import asyncio
import gc
import os
import re
import shutil
import signal
import sys
import time
import warnings
from asyncio import base_subprocess
from pathlib import Path

import pytest

from tests.agent_test_support import build_test_agent
from vidbyte.agents import AgentLoopSettings, ToolSettings
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolResult, ToolStatus

TIME_LIMIT_SECONDS = 2.0  # patched over BASH_TIMEOUT_SECONDS
KILL_GRACE_SECONDS = 1.0  # patched over BASH_KILL_GRACE_SECONDS
SLACK_SECONDS = 3.0  # scheduling allowance on a loaded CI runner
OUTLIVES_SECONDS = 30  # long enough that a missing bound or kill is unmistakable
WINDOWS_ORPHAN_SECONDS = 8  # Windows cannot stop the command (EC-14); keep the orphan short-lived
AGENT_TOOL_TIMEOUT_SECONDS = 1.5
SMALL_CAP_BYTES = 1000  # even, so a run of "y\n" lines fills it exactly
STOP_POLL_SECONDS = 0.05
STOPPED_WITHIN_SECONDS = 2.0
STARTED_WITHIN_SECONDS = 10.0
PROC = Path("/proc")

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="process-group kill and liveness checks are POSIX-only by spec (EC-14)")
needs_setsid = pytest.mark.skipif(sys.platform != "win32" and shutil.which("setsid") is None, reason="this POSIX host has no setsid")


def _shrink_bounds(bash_module, monkeypatch: pytest.MonkeyPatch, *, time_limit: float = TIME_LIMIT_SECONDS) -> None:
    # Spec §13: the constants are read at call time, so patching them changes the bound a call uses.
    monkeypatch.setattr(bash_module, "BASH_TIMEOUT_SECONDS", time_limit)
    monkeypatch.setattr(bash_module, "BASH_KILL_GRACE_SECONDS", KILL_GRACE_SECONDS)


def _bash_call(command: str) -> ToolCall:
    return ToolCall("bash", {"command": command})


def _labelled_pid(label: str, output: str) -> int:
    # Reads a pid the command printed as "<label>:<pid>".
    match = re.search(rf"{label}:(\d+)", output)
    assert match is not None, f"the command output should carry {label}:<pid>; got {output!r}"
    return int(match.group(1))


def _is_running(pid: int) -> bool:
    # POSIX only. A zombie has already exited, so only a live process counts as running.
    if not (PROC / "self").exists():
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True
    try:
        stat = (PROC / str(pid) / "stat").read_text(encoding="utf-8")
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] not in ("Z", "X")


def _live_group_members(pgid: int) -> list[int]:
    # Linux only: every live process whose process group is pgid (empty where /proc is missing).
    members = []
    for entry in PROC.glob("[0-9]*"):
        try:
            fields = (entry / "stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
        except OSError:
            continue
        if int(fields[2]) == pgid and fields[0] not in ("Z", "X"):
            members.append(int(entry.name))
    return members


async def _stopped_within(pid: int, seconds: float = STOPPED_WITHIN_SECONDS) -> bool:
    # Polls until the process is gone or a zombie; a killed process needs a moment to be reaped.
    deadline = time.monotonic() + seconds
    while _is_running(pid):
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(STOP_POLL_SECONDS)
    return True


async def _pid_from_file(path: Path, call: asyncio.Task) -> int:
    # Waits for the command to write "<pid>\n" while the call is still running.
    deadline = time.monotonic() + STARTED_WITHIN_SECONDS
    while not (path.exists() and path.read_text(encoding="utf-8").endswith("\n")):
        assert not call.done(), f"the call ended before {path.name} was written: {call.result()!r}"
        assert time.monotonic() < deadline, f"{path.name} was not written within {STARTED_WITHIN_SECONDS}s"
        await asyncio.sleep(STOP_POLL_SECONDS)
    return int(path.read_text(encoding="utf-8").strip())


def _kill_quietly(*pids: int) -> None:
    # Test cleanup on POSIX: never leave a sleeper behind when the implementation under test fails to.
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _open_subprocess_transports() -> list[base_subprocess.BaseSubprocessTransport]:
    return [obj for obj in gc.get_objects() if isinstance(obj, base_subprocess.BaseSubprocessTransport) and not obj.is_closing()]


async def _execute_and_list_open_transports(tool, command: str) -> tuple[ToolResult, list[str]]:
    # Runs one call, then lists subprocess transports it created that are still open once it has returned.
    before = {id(transport) for transport in _open_subprocess_transports()}
    result = await tool.execute(_bash_call(command))
    left_open = [repr(transport) for transport in _open_subprocess_transports() if id(transport) not in before]
    return result, left_open


@pytest.mark.asyncio
async def test_command_past_the_time_limit_returns_timeout_with_output_so_far(bash_module, tmp_path, monkeypatch) -> None:
    # AC-27 / AC-14 / EC-8 / INV-11: on every OS and Python, a never-ending command ends as a timeout result within limit + grace.
    _shrink_bounds(bash_module, monkeypatch)
    sleep_seconds = WINDOWS_ORPHAN_SECONDS if sys.platform == "win32" else OUTLIVES_SECONDS
    tool = bash_module.BashTool(tmp_path)

    started = time.monotonic()
    result = await tool.execute(_bash_call(f"echo before-the-limit; sleep {sleep_seconds}"))
    elapsed = time.monotonic() - started

    assert elapsed <= TIME_LIMIT_SECONDS + KILL_GRACE_SECONDS + SLACK_SECONDS
    assert result.status is ToolStatus.ERROR
    assert result.metadata["error"] == "timeout"
    assert result.metadata["truncated"] is False
    lines = result.output.splitlines()
    assert lines[0] == "before-the-limit"
    # The final line tells the model why the command stopped, naming the (patched) limit of 2 seconds.
    assert lines[-1] != "before-the-limit"
    assert "2" in lines[-1]


@posix_only
@pytest.mark.asyncio
async def test_time_limit_kills_the_command_and_the_child_it_started(bash_module, tmp_path, monkeypatch) -> None:
    # AC-14 / EC-9 / D-14: the shell leads its own process group, and the whole group is killed at the limit.
    _shrink_bounds(bash_module, monkeypatch)
    result = await bash_module.BashTool(tmp_path).execute(_bash_call(f"sleep {OUTLIVES_SECONDS} & echo child:$!; echo shell:$$; wait"))
    child = _labelled_pid("child", result.output)
    shell = _labelled_pid("shell", result.output)

    try:
        assert result.metadata["error"] == "timeout"
        assert await _stopped_within(child)
        assert await _stopped_within(shell)
        assert _live_group_members(shell) == []
    finally:
        _kill_quietly(child)


@posix_only
@pytest.mark.asyncio
async def test_command_that_closes_its_output_still_times_out_and_is_killed(bash_module, tmp_path, monkeypatch) -> None:
    # AC-24 / EC-28 / D-17: reading to end of output and waiting for exit share one limit, so an early EOF cannot unbound the wait.
    _shrink_bounds(bash_module, monkeypatch)
    command = f"echo shell:$$; exec >/dev/null 2>&1; sleep {OUTLIVES_SECONDS} & echo $! > sleeper.pid; wait"

    started = time.monotonic()
    result = await bash_module.BashTool(tmp_path).execute(_bash_call(command))
    elapsed = time.monotonic() - started
    shell = _labelled_pid("shell", result.output)
    sleeper = int((tmp_path / "sleeper.pid").read_text(encoding="utf-8").strip())

    try:
        assert elapsed <= TIME_LIMIT_SECONDS + KILL_GRACE_SECONDS + SLACK_SECONDS
        assert result.metadata["error"] == "timeout"
        assert await _stopped_within(shell)
        assert await _stopped_within(sleeper)
    finally:
        _kill_quietly(sleeper)


@posix_only
@needs_setsid
@pytest.mark.asyncio
async def test_setsid_descendant_holding_the_output_cannot_stretch_the_call_past_limit_plus_grace(bash_module, tmp_path, monkeypatch) -> None:
    # AC-25 / EC-30 / INV-11: the group kill cannot reach a new session; the bounded wait after the kill still returns the call.
    _shrink_bounds(bash_module, monkeypatch)

    started = time.monotonic()
    result = await bash_module.BashTool(tmp_path).execute(_bash_call(f"setsid sleep {OUTLIVES_SECONDS} & echo descendant:$!; wait"))
    elapsed = time.monotonic() - started
    descendant = _labelled_pid("descendant", result.output)

    try:
        assert elapsed <= TIME_LIMIT_SECONDS + KILL_GRACE_SECONDS + SLACK_SECONDS
        assert result.status is ToolStatus.ERROR
        assert result.metadata["error"] == "timeout"
    finally:
        _kill_quietly(descendant)


@posix_only
@pytest.mark.asyncio
async def test_background_process_with_both_streams_redirected_survives_a_completed_call(bash_module, tmp_path, monkeypatch) -> None:
    # AC-26 / INV-25 / EC-9: a normal completion returns when the shell exits and kills nothing, so a properly detached server keeps running.
    _shrink_bounds(bash_module, monkeypatch, time_limit=15.0)

    started = time.monotonic()
    result = await bash_module.BashTool(tmp_path).execute(_bash_call(f"sleep {OUTLIVES_SECONDS} >/dev/null 2>&1 & echo background:$!"))
    elapsed = time.monotonic() - started
    background = _labelled_pid("background", result.output)

    try:
        assert result.status is ToolStatus.SUCCESS
        assert result.metadata["exit_code"] == 0
        assert elapsed < SLACK_SECONDS
        assert _is_running(background)
    finally:
        _kill_quietly(background)


@posix_only
@pytest.mark.asyncio
async def test_endless_printer_times_out_with_the_first_bytes_and_a_truncation_marker(bash_module, tmp_path, monkeypatch) -> None:
    # AC-29 / EC-10 / D-19: `yes` never exits; the timeout result keeps exactly the cap and says the output was cut.
    _shrink_bounds(bash_module, monkeypatch)
    monkeypatch.setattr(bash_module, "BASH_MAX_OUTPUT_BYTES", SMALL_CAP_BYTES)

    started = time.monotonic()
    result = await bash_module.BashTool(tmp_path).execute(_bash_call("yes"))
    elapsed = time.monotonic() - started

    assert elapsed <= TIME_LIMIT_SECONDS + KILL_GRACE_SECONDS + SLACK_SECONDS
    assert result.status is ToolStatus.ERROR
    assert result.metadata["error"] == "timeout"
    assert result.metadata["truncated"] is True
    kept = re.match(r"(?:y\n)+", result.output)
    assert kept is not None
    assert len(kept.group(0).encode("utf-8")) == SMALL_CAP_BYTES
    # Spec §8.5: the timeout truncation line names the cap but no omitted-byte count (that count is unknown while the command runs).
    marker_lines = [line for line in result.output[kept.end():].splitlines() if "truncated" in line.lower()]
    assert len(marker_lines) == 1
    assert set(re.findall(r"\d[\d,]*", marker_lines[0])) <= {str(SMALL_CAP_BYTES), f"{SMALL_CAP_BYTES:,}"}


@needs_setsid
def test_timed_out_call_closes_its_pipe_so_loop_shutdown_reports_nothing(bash_module, tmp_path, monkeypatch) -> None:
    # AC-28 / INV-26 / D-18: the command outlives the stop (POSIX: a setsid descendant; Windows: anything still running) and keeps the pipe open.
    _shrink_bounds(bash_module, monkeypatch)
    if sys.platform == "win32":
        command = f"echo started; sleep {WINDOWS_ORPHAN_SECONDS}"
    else:
        command = f"setsid sleep {OUTLIVES_SECONDS} & echo descendant:$!; wait"
    tool = bash_module.BashTool(tmp_path)
    result: ToolResult | None = None
    unraisable: list[object] = []
    previous_hook = sys.unraisablehook
    sys.unraisablehook = unraisable.append
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # BaseAgent.run uses asyncio.run too, so the loop is closed right after the call, as in production.
            result, left_open = asyncio.run(_execute_and_list_open_transports(tool, command))
            gc.collect()
    finally:
        sys.unraisablehook = previous_hook
        if result is not None and sys.platform != "win32":
            _kill_quietly(*(int(pid) for pid in re.findall(r"descendant:(\d+)", result.output)))

    assert result.metadata["error"] == "timeout"
    assert left_open == []
    loop_errors = [f"{report.err_msg} {report.exc_value!r}" for report in unraisable]
    assert not [text for text in loop_errors if "Event loop is closed" in text or "closed pipe" in text]
    assert not [str(warning.message) for warning in caught if "unclosed transport" in str(warning.message)]


@pytest.mark.asyncio
async def test_cancelled_call_reraises_cancellation_within_the_grace_period(bash_module, tmp_path, monkeypatch) -> None:
    # INV-12 / AC-15: on every OS, cancelling a running call stops the command and lets CancelledError out within the grace bound.
    _shrink_bounds(bash_module, monkeypatch, time_limit=60.0)
    tool = bash_module.BashTool(tmp_path)
    sleep_seconds = WINDOWS_ORPHAN_SECONDS if sys.platform == "win32" else OUTLIVES_SECONDS
    call = asyncio.create_task(tool.execute(_bash_call(f"echo $$ > shell.pid; sleep {sleep_seconds}")))
    await _pid_from_file(tmp_path / "shell.pid", call)

    call.cancel()
    cancelled_at = time.monotonic()
    with pytest.raises(asyncio.CancelledError):
        await call

    assert time.monotonic() - cancelled_at <= KILL_GRACE_SECONDS + SLACK_SECONDS


@posix_only
@pytest.mark.asyncio
async def test_cancellation_kills_the_process_group_even_after_the_shell_has_exited(bash_module, tmp_path, monkeypatch) -> None:
    # AC-15 / EC-29 / D-14: the shell is gone but its background child still holds the output; cancellation must kill the group anyway.
    _shrink_bounds(bash_module, monkeypatch, time_limit=60.0)
    tool = bash_module.BashTool(tmp_path)
    call = asyncio.create_task(tool.execute(_bash_call(f"echo $$ > shell.pid; sleep {OUTLIVES_SECONDS} & echo $! > child.pid")))
    shell = await _pid_from_file(tmp_path / "shell.pid", call)
    child = await _pid_from_file(tmp_path / "child.pid", call)

    try:
        assert await _stopped_within(shell, STARTED_WITHIN_SECONDS)
        assert not call.done()
        call.cancel()
        cancelled_at = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await call
        assert time.monotonic() - cancelled_at <= KILL_GRACE_SECONDS + SLACK_SECONDS
        assert await _stopped_within(child)
        assert _live_group_members(shell) == []
    finally:
        _kill_quietly(child)


@posix_only
@pytest.mark.asyncio
async def test_agent_tool_timeout_cancels_bash_and_kills_the_background_child(bash_module, script_model, tmp_path, monkeypatch) -> None:
    # AC-15 / EC-29: ToolSettings.tool_timeout_seconds cancels the call; the runtime reports its own timeout and no server is left running.
    monkeypatch.setattr(bash_module, "BASH_KILL_GRACE_SECONDS", KILL_GRACE_SECONDS)
    runner = script_model([("bash", {"command": f"sleep {OUTLIVES_SECONDS} & echo $! > child.pid"})], final_answer="gave up on the server")
    agent = build_test_agent(
        name="runner",
        system_prompt="Run commands.",
        tools=[bash_module.BashTool(tmp_path)],
        permission_policy=PermissionPolicy.allow_all(),
        agent_loop_settings=AgentLoopSettings(tool_settings=ToolSettings(tool_timeout_seconds=AGENT_TOOL_TIMEOUT_SECONDS)),
        runner=runner,
    )

    started = time.monotonic()
    reply = await agent.arun("Start the server.")
    elapsed = time.monotonic() - started
    child = int((tmp_path / "child.pid").read_text(encoding="utf-8").strip())

    try:
        assert reply.metadata["tool_call_states"] == ("failed", "succeeded")
        assert "timed out" in runner.tool_messages()[0][1]
        assert elapsed <= AGENT_TOOL_TIMEOUT_SECONDS + KILL_GRACE_SECONDS + SLACK_SECONDS
        assert await _stopped_within(child)
    finally:
        _kill_quietly(child)
