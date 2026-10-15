"""FILE: tests/features/harness_threads/test_harness_threads_runner.py

PURPOSE: The canonical process helper every thread function runs through (§8.5 CliRunner, CliInvocation; D-13, FR-12): the child inherits the caller's environment, minus the env_remove names, plus an env_overlay that wins, the overlay and stdin text stay out of repr, stdin is a pipe that closes or DEVNULL, output is capped while draining continues, the timeout stops the whole tree within its bound, a run ends when its leader exits even while a grandchild holds the pipes (AC-2, review R-11), launch failures are fields, and cancellation stops the tree and re-raises.
ROLE IN CODEBASE: Start here when a CLI run hangs, leaks a process, reads the caller's stdin, loses the caller's environment, or raises instead of reporting. Carried over from the deleted grok_host pack's process-helper tests, rewritten for env_overlay (the ManagedProcess tests went with ManagedProcess).
ARCHITECTURE NOTE: Children are small inline Python programs run with sys.executable. The stdin test points this process's fd 0 at a pipe that never reaches EOF, so a child that inherited stdin would block and the test would see a timeout. Liveness is checked on win32 and POSIX.
FUNCTION INVENTORY: child builds an argv for an inline program; invocation builds a CliInvocation; never_ending_stdin swaps fd 0 for an open pipe; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Keep children self-contained and bounded (each exits by itself within CHILD_LIMIT_SECONDS).
WHAT NOT TO DO IN THIS FILE: 1. Do not mock asyncio subprocesses; the helper's job is real process handling. 2. Do not assert exact exit codes after a kill; they differ by platform.
KNOWN EDGE CASES: On win32 os.dup2 onto fd 0 also replaces the Win32 standard input handle, so an inheriting child does block there too (checked on Windows 11 with Python 3.11). On win32 a tree stop cannot reach a grandchild once its leader has exited, so the leader-exit test ends the grandchild itself.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §8.5 (CliInvocation, CliRunner), D-13 and its r4 exception, §12.3 rows 27, 30; docs/spec/harness-thread-functions/review.md R-11
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_runner.py
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import signal
import sys
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

CHILD_LIMIT_SECONDS = 30
GRANDCHILD_SOURCE = f"""
import subprocess, sys, time
grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep({CHILD_LIMIT_SECONDS})"])
print(grandchild.pid, flush=True)
time.sleep({CHILD_LIMIT_SECONDS})
"""
LEADER_EXITS_SOURCE = f"""
import subprocess, sys
grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep({CHILD_LIMIT_SECONDS})"])
print(grandchild.pid, flush=True)
print("answer: done", flush=True)
"""


def child(source: str) -> tuple[str, ...]:
    return (sys.executable, "-u", "-c", textwrap.dedent(source))


def invocation(api: Any, argv: tuple[str, ...], /, **fields: Any) -> Any:
    # argv is positional-only, so a test can pass a bad argv through
    # **fields to replace it.
    values: dict[str, Any] = {"argv": argv, "env_overlay": {}, "timeout_seconds": 20.0, "max_output_bytes": 1_000_000}
    values.update(fields)
    return api.CliInvocation(**values)


@contextlib.contextmanager
def never_ending_stdin() -> Iterator[None]:
    read_end, write_end = os.pipe()
    saved = os.dup(0)
    os.dup2(read_end, 0)
    try:
        yield
    finally:
        os.dup2(saved, 0)
        for descriptor in (saved, read_end, write_end):
            os.close(descriptor)


def test_cli_invocation_validates_and_hides_the_overlay_and_stdin(lib_api, tmp_path: Path) -> None:
    # §8.5 / §12.3 row 27: env_overlay (a str mapping, repr=False),
    # timeout up to NATIVE_THREAD_MAX_SECONDS, stdin_text repr=False.
    good = invocation(lib_api, ("grok", "--version"), env_overlay={"VIDBYTE_HIDDEN_ENV": "hidden-env-value"}, stdin_text="hidden-stdin-text", cwd=tmp_path, timeout_seconds=14400.0)
    assert "hidden-env-value" not in repr(good) and "hidden-stdin-text" not in repr(good)
    bad_values = [
        ("argv", ()), ("argv", ("",)), ("env_overlay", {"KEY": 1}), ("timeout_seconds", 0), ("timeout_seconds", math.nan),
        ("timeout_seconds", True), ("timeout_seconds", 14400.5), ("max_output_bytes", 0), ("max_output_bytes", True),
    ]
    for field_name, bad in bad_values:
        with pytest.raises(lib_api.ConfigurationError) as caught:
            invocation(lib_api, ("grok",), **{field_name: bad})
        assert field_name in str(caught.value), field_name
    with pytest.raises(TypeError):
        lib_api.CliInvocation(argv=("grok",), env={}, timeout_seconds=1.0, max_output_bytes=10)


@pytest.mark.asyncio
async def test_child_inherits_the_environment_plus_the_overlay(lib_api, tmp_path: Path, monkeypatch) -> None:
    # D-13: the child starts with {**os.environ, **env_overlay}; the
    # overlay wins; cwd is honoured; os.environ is unchanged.
    monkeypatch.setenv("VIDBYTE_PARENT_PROBE", "from-parent")
    monkeypatch.setenv("VIDBYTE_SHADOWED_PROBE", "parent-value")
    before = dict(os.environ)
    source = "import os; print(os.environ.get('VIDBYTE_PARENT_PROBE')); print(os.environ.get('VIDBYTE_SHADOWED_PROBE')); print(os.environ.get('VIDBYTE_OVERLAY_PROBE')); print(os.getcwd())"
    outcome = await lib_api.CliRunner().run(invocation(lib_api, child(source), env_overlay={"VIDBYTE_OVERLAY_PROBE": "from-overlay", "VIDBYTE_SHADOWED_PROBE": "overlay-value"}, cwd=tmp_path))
    lines = outcome.stdout.splitlines()
    assert lines[:3] == ["from-parent", "overlay-value", "from-overlay"]
    assert Path(lines[3]).resolve() == tmp_path.resolve()
    assert dict(os.environ) == before



@pytest.mark.asyncio
async def test_env_remove_drops_an_inherited_name_before_the_overlay(lib_api, monkeypatch) -> None:
    # D-13 exception / rows 27, 30: the child starts with os.environ
    # minus env_remove, then env_overlay on top; os.environ is
    # unchanged.
    monkeypatch.setenv("VIDBYTE_PARENT_PROBE", "from-parent")
    monkeypatch.setenv("VIDBYTE_KEPT_PROBE", "kept")
    before = dict(os.environ)
    source = "import os; print(os.environ.get('VIDBYTE_PARENT_PROBE', '<absent>')); print(os.environ.get('VIDBYTE_KEPT_PROBE')); print(os.environ.get('VIDBYTE_OVERLAY_PROBE'))"
    outcome = await lib_api.CliRunner().run(invocation(lib_api, child(source), env_overlay={"VIDBYTE_OVERLAY_PROBE": "from-overlay"}, env_remove=("VIDBYTE_PARENT_PROBE",)))
    assert outcome.stdout.splitlines()[:3] == ["<absent>", "kept", "from-overlay"]
    assert dict(os.environ) == before

@pytest.mark.asyncio
async def test_runner_returns_exit_code_and_output(lib_api) -> None:
    outcome = await lib_api.CliRunner().run(invocation(lib_api, child("import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)")))
    assert outcome.exit_code == 3
    assert outcome.stdout.strip() == "out" and outcome.stderr.strip() == "err"
    assert (outcome.stdout_truncated, outcome.stderr_truncated, outcome.timed_out, outcome.launch_failure) == (False, False, False, None)


@pytest.mark.asyncio
async def test_runner_writes_stdin_text_then_closes_the_pipe(lib_api) -> None:
    # INV-10: stdin is a pipe that receives stdin_text and is then
    # closed; the child reads to EOF.
    source = "import sys; data = sys.stdin.read(); print(len(data), data.splitlines()[-1])"
    outcome = await lib_api.CliRunner().run(invocation(lib_api, child(source), stdin_text="line one\nline two\n", timeout_seconds=10.0))
    assert outcome.timed_out is False
    assert outcome.stdout.split() == ["18", "line", "two"]


@pytest.mark.asyncio
async def test_runner_never_lets_the_child_inherit_the_callers_stdin(lib_api) -> None:
    # INV-10: with no stdin_text the child gets DEVNULL, so a read
    # returns at once.
    with never_ending_stdin():
        outcome = await lib_api.CliRunner().run(invocation(lib_api, child("import sys; print(len(sys.stdin.read()))"), timeout_seconds=5.0))
    assert outcome.timed_out is False, "the child blocked on an inherited stdin"
    assert outcome.stdout.strip() == "0"


@pytest.mark.asyncio
async def test_runner_caps_output_and_keeps_draining(lib_api) -> None:
    # INV-8: stdout and stderr are each kept up to max_output_bytes; the
    # child never blocks on a full pipe.
    source = "import sys; sys.stdout.write('o' * 300000); sys.stderr.write('e' * 300000); print('done', file=sys.stderr)"
    outcome = await lib_api.CliRunner().run(invocation(lib_api, child(source), max_output_bytes=100, timeout_seconds=15.0))
    assert outcome.timed_out is False and outcome.exit_code == 0
    assert len(outcome.stdout.encode()) <= 100 and outcome.stdout_truncated is True
    assert len(outcome.stderr.encode()) <= 100 and outcome.stderr_truncated is True


@pytest.mark.asyncio
async def test_runner_timeout_stops_the_whole_tree_within_the_bound(lib_api, fast_stop, alive, wait_until) -> None:
    # INV-8: the run's timeout holds and its whole tree (grandchild
    # included) is stopped.
    started = time.monotonic()
    outcome = await lib_api.CliRunner().run(invocation(lib_api, child(GRANDCHILD_SOURCE), timeout_seconds=1.0))
    assert time.monotonic() - started < 1.0 + 4 * fast_stop.kill_wait + fast_stop.slack
    assert outcome.timed_out is True and outcome.exit_code is not None
    grandchild = int(outcome.stdout.split()[0])
    assert await wait_until(lambda: not alive(grandchild), fast_stop.kill_wait + 1.0)


@pytest.mark.asyncio
async def test_runner_returns_when_the_leader_exits_while_a_grandchild_holds_the_pipes(lib_api, fast_stop, alive) -> None:
    # AC-2 / INV-8 / R-11: the run ends at the leader's exit, and what
    # it printed is kept, although a grandchild still holds its pipes.
    started = time.monotonic()
    outcome = await lib_api.CliRunner().run(invocation(lib_api, child(LEADER_EXITS_SOURCE), timeout_seconds=20.0))
    elapsed = time.monotonic() - started
    lines = outcome.stdout.splitlines()
    grandchild = int(lines[0])
    if alive(grandchild):
        os.kill(grandchild, signal.SIGTERM)
    assert outcome.timed_out is False, f"R-11: the run waited {elapsed:.1f} s for the grandchild's pipes"
    assert outcome.exit_code == 0
    assert lines[1:] == ["answer: done"]
    assert elapsed < 4 * fast_stop.kill_wait + fast_stop.slack


@pytest.mark.asyncio
async def test_runner_reports_a_missing_program_without_raising(lib_api, tmp_path: Path) -> None:
    outcome = await lib_api.CliRunner().run(invocation(lib_api, (str(tmp_path / "no-such-program"),)))
    assert outcome.launch_failure is lib_api.ProcessLaunchFailure.NOT_FOUND
    assert outcome.exit_code is None


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="the execute permission bit exists only on POSIX")
async def test_runner_reports_permission_denied(lib_api, tmp_path: Path) -> None:
    script = tmp_path / "not-executable.sh"
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    script.chmod(0o644)
    outcome = await lib_api.CliRunner().run(invocation(lib_api, (str(script),)))
    assert outcome.launch_failure is lib_api.ProcessLaunchFailure.PERMISSION_DENIED
    assert outcome.exit_code is None


@pytest.mark.asyncio
async def test_runner_cancellation_stops_the_child_then_reraises(lib_api, fast_stop, tmp_path: Path, wait_until, alive) -> None:
    # INV-9: on cancellation the runner stops the tree, then re-raises.
    pid_file = tmp_path / "pid.txt"
    source = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep({CHILD_LIMIT_SECONDS})"
    task = asyncio.create_task(lib_api.CliRunner().run(invocation(lib_api, child(source), timeout_seconds=60.0)))
    assert await wait_until(lambda: pid_file.exists() and pid_file.read_text() != "", 20.0)
    started = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert time.monotonic() - started < 4 * fast_stop.kill_wait + fast_stop.slack
    pid = int(pid_file.read_text())
    assert await wait_until(lambda: not alive(pid), fast_stop.kill_wait + 1.0)
