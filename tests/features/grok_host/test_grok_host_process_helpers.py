"""FILE: tests/features/grok_host/test_grok_host_process_helpers.py

PURPOSE: The canonical process helpers in vidbyte.lib.process that every host uses: CliRunner (stdin pipe or DEVNULL, output caps, timeout, tree stop, cancellation), ManagedProcess (ready line, early exit, continued draining, idempotent stop), ProcessStopper (tree stop even after the leader exited), and the CliInvocation record (FR-9, FR-16, INV-3, INV-4, D-21, EC-10).
ROLE IN CODEBASE: Start here when a CLI run hangs, leaks a process, reads the caller's stdin, or raises. Grok's --version, models, one-shot and fork runs, the opencode server and the Muse reap all go through these helpers.
ARCHITECTURE NOTE: Children are small inline Python programs run with sys.executable. The stdin tests point this process's fd 0 at a pipe that never reaches EOF, so a child that inherited stdin would block and the test would see a timeout.
FUNCTION INVENTORY: child builds an argv for an inline program; invocation builds a CliInvocation; never_ending_stdin swaps fd 0 for an open pipe; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Keep children self-contained and bounded (each exits by itself within a minute).
WHAT NOT TO DO IN THIS FILE: 1. Do not mock asyncio subprocesses; the helpers' job is real process handling. 2. Do not assert exact exit codes after a kill; they differ by platform.
KNOWN EDGE CASES: Grandchild liveness is checked on POSIX only (spec §13). On Windows a never-ending stdin swap may not reach the Win32 standard handle, so the stdin tests can only fail there, never pass wrongly.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Process helpers, Standard input), §9.1 vidbyte.lib.dataclasses.process
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_process_helpers.py
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import math
import os
import re
import sys
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="process-group liveness checks are POSIX-only by spec §13")
READY = re.compile(r"opencode server listening on (http://127\.0\.0\.1:\d+)")
CHILD_LIMIT_SECONDS = 30


@pytest.fixture
def process_api() -> SimpleNamespace:
    package = importlib.import_module("vidbyte.lib.process")
    records = importlib.import_module("vidbyte.lib.dataclasses.process")
    return SimpleNamespace(
        CliRunner=package.CliRunner,
        ManagedProcess=package.ManagedProcess,
        ProcessStopper=package.ProcessStopper,
        CliInvocation=records.CliInvocation,
        CliOutcome=records.CliOutcome,
        ProcessStartOutcome=records.ProcessStartOutcome,
        ProcessLaunchFailure=importlib.import_module("vidbyte.lib.enums.process").ProcessLaunchFailure,
    )


def child(source: str) -> tuple[str, ...]:
    return (sys.executable, "-u", "-c", textwrap.dedent(source))


def invocation(api: SimpleNamespace, argv: tuple[str, ...], **fields: Any) -> Any:
    values: dict[str, Any] = {"argv": argv, "env": dict(os.environ), "timeout_seconds": 20.0, "max_output_bytes": 1_000_000}
    values.update(fields)
    return api.CliInvocation(**values)


@contextlib.contextmanager
def never_ending_stdin() -> Iterator[None]:
    # Point fd 0 at a pipe whose write end stays open, so an inherited stdin never reaches EOF.
    read_end, write_end = os.pipe()
    saved = os.dup(0)
    os.dup2(read_end, 0)
    try:
        yield
    finally:
        os.dup2(saved, 0)
        for descriptor in (saved, read_end, write_end):
            os.close(descriptor)


GRANDCHILD_SOURCE = f"""
import subprocess, sys, time
grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep({CHILD_LIMIT_SECONDS})"])
print(grandchild.pid, flush=True)
time.sleep({CHILD_LIMIT_SECONDS})
"""


def test_cli_invocation_validates_and_hides_env_and_stdin(process_api, tmp_path: Path, grok_api) -> None:
    # §9.1: require_argv; mapping of str; number <= NATIVE_TURN_MAX_SECONDS; int in 1..NATIVE_PROCESS_MAX_OUTPUT_BYTES; env and stdin_text repr=False.
    good = invocation(process_api, ("grok", "--version"), env={"VIDBYTE_HIDDEN_ENV": "hidden-env-value"}, stdin_text="hidden-stdin-text", cwd=tmp_path)
    assert "hidden-env-value" not in repr(good) and "hidden-stdin-text" not in repr(good)
    bad_values = [
        ("argv", ()), ("argv", ("",)), ("env", {"KEY": 1}), ("timeout_seconds", 0), ("timeout_seconds", math.nan), ("timeout_seconds", True),
        ("timeout_seconds", 14400.5), ("max_output_bytes", 0), ("max_output_bytes", 67108865), ("max_output_bytes", True),
    ]
    for field_name, bad in bad_values:
        with pytest.raises(grok_api.ConfigurationError) as caught:
            invocation(process_api, **{"argv": ("grok",), field_name: bad})
        assert f"CliInvocation.{field_name}" in str(caught.value), field_name


@pytest.mark.asyncio
async def test_cli_runner_returns_exit_code_and_output(process_api) -> None:
    outcome = await process_api.CliRunner().run(invocation(process_api, child("import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)")))
    assert outcome.exit_code == 3
    assert outcome.stdout.strip() == "out" and outcome.stderr.strip() == "err"
    assert (outcome.stdout_truncated, outcome.stderr_truncated, outcome.timed_out, outcome.launch_failure) == (False, False, False, None)


@pytest.mark.asyncio
async def test_cli_runner_writes_stdin_text_then_closes_the_pipe(process_api) -> None:
    # §8.5: stdin is a pipe that receives stdin_text and is then closed; the child reads to EOF.
    source = "import sys; data = sys.stdin.read(); print(len(data), data.splitlines()[-1])"
    outcome = await process_api.CliRunner().run(invocation(process_api, child(source), stdin_text="line one\nline two\n", timeout_seconds=10.0))
    assert outcome.timed_out is False
    assert outcome.stdout.split() == ["18", "line", "two"]


@pytest.mark.asyncio
async def test_cli_runner_never_inherits_the_callers_stdin(process_api) -> None:
    # D-21 / §8.5 Standard input: with no stdin_text the child gets DEVNULL, so a read returns at once.
    with never_ending_stdin():
        outcome = await process_api.CliRunner().run(invocation(process_api, child("import sys; print(len(sys.stdin.read()))"), timeout_seconds=5.0))
    assert outcome.timed_out is False, "the child blocked on an inherited stdin"
    assert outcome.stdout.strip() == "0"


@pytest.mark.asyncio
async def test_cli_runner_caps_output_and_keeps_draining(process_api) -> None:
    # INV-16: stdout and stderr are each read up to max_output_bytes; the child never blocks on a full pipe.
    source = "import sys; sys.stdout.write('o' * 300000); sys.stderr.write('e' * 300000); print('done', file=sys.stderr)"
    outcome = await process_api.CliRunner().run(invocation(process_api, child(source), max_output_bytes=100, timeout_seconds=15.0))
    assert outcome.timed_out is False and outcome.exit_code == 0
    assert len(outcome.stdout.encode()) <= 100 and outcome.stdout_truncated is True
    assert len(outcome.stderr.encode()) <= 100 and outcome.stderr_truncated is True


@pytest.mark.asyncio
async def test_cli_runner_stops_at_the_timeout_within_the_bound(process_api, fast_stop) -> None:
    # INV-3: a CLI run uses its invocation's timeout; its tree stop waits at most NATIVE_KILL_WAIT_SECONDS per wait.
    started = time.monotonic()
    outcome = await process_api.CliRunner().run(invocation(process_api, child(f"import time; time.sleep({CHILD_LIMIT_SECONDS})"), timeout_seconds=0.5))
    elapsed = time.monotonic() - started
    assert outcome.timed_out is True
    assert outcome.exit_code is not None
    assert elapsed < 0.5 + 3 * fast_stop.kill_wait + fast_stop.slack


@pytest.mark.asyncio
@posix_only
async def test_cli_runner_timeout_stops_the_whole_tree(process_api, fast_stop, wait_until, process_running) -> None:
    # INV-4 / EC-38: the run's whole process tree is stopped and reaped.
    outcome = await process_api.CliRunner().run(invocation(process_api, child(GRANDCHILD_SOURCE), timeout_seconds=1.0))
    grandchild = int(outcome.stdout.split()[0])
    assert outcome.timed_out is True
    assert await wait_until(lambda: not process_running(grandchild), 2 * fast_stop.kill_wait + fast_stop.slack)


@pytest.mark.asyncio
async def test_cli_runner_reports_a_missing_program_without_raising(process_api, tmp_path: Path) -> None:
    # §8.5: the helpers never raise; a launch failure is a field of the record and exit_code stays None.
    outcome = await process_api.CliRunner().run(invocation(process_api, (str(tmp_path / "no-such-program"),)))
    assert outcome.launch_failure is process_api.ProcessLaunchFailure.NOT_FOUND
    assert outcome.exit_code is None


@pytest.mark.asyncio
@posix_only
async def test_cli_runner_reports_permission_denied(process_api, tmp_path: Path) -> None:
    script = tmp_path / "not-executable.sh"
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    script.chmod(0o644)
    outcome = await process_api.CliRunner().run(invocation(process_api, (str(script),)))
    assert outcome.launch_failure is process_api.ProcessLaunchFailure.PERMISSION_DENIED
    assert outcome.exit_code is None


@pytest.mark.asyncio
async def test_cli_runner_passes_env_and_cwd(process_api, tmp_path: Path) -> None:
    env = {**os.environ, "VIDBYTE_RUNNER_PROBE": "reached"}
    source = "import os; print(os.environ.get('VIDBYTE_RUNNER_PROBE')); print(os.getcwd())"
    outcome = await process_api.CliRunner().run(invocation(process_api, child(source), env=env, cwd=tmp_path))
    lines = outcome.stdout.splitlines()
    assert lines[0] == "reached"
    assert Path(lines[1]).resolve() == tmp_path.resolve()


@pytest.mark.asyncio
async def test_cli_runner_cancellation_propagates_and_stops_the_child(process_api, fast_stop, tmp_path: Path, wait_until, process_running) -> None:
    # INV-2: on cancellation the runner stops and reaps the tree, then re-raises.
    pid_file = tmp_path / "pid.txt"
    source = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep({CHILD_LIMIT_SECONDS})"
    task = asyncio.create_task(process_api.CliRunner().run(invocation(process_api, child(source), timeout_seconds=60.0)))
    assert await wait_until(lambda: pid_file.exists() and pid_file.read_text() != "", 20.0)
    started = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert time.monotonic() - started < 3 * fast_stop.kill_wait + fast_stop.slack
    if sys.platform != "win32":
        assert not process_running(int(pid_file.read_text()))


SERVER_SOURCE = f"""
import sys, time
print("starting up", flush=True)
print("opencode server listening on http://127.0.0.1:4321", flush=True)
time.sleep({CHILD_LIMIT_SECONDS})
"""


@pytest.mark.asyncio
async def test_managed_process_reports_the_ready_line_and_stops_idempotently(process_api, fast_stop) -> None:
    managed = process_api.ManagedProcess(invocation(process_api, child(SERVER_SOURCE), timeout_seconds=15.0))
    outcome = await managed.start(READY)
    assert outcome.ready_line is not None and READY.search(outcome.ready_line)
    assert (outcome.launch_failure, outcome.exit_code, outcome.timed_out) == (None, None, False)
    assert managed.exit_code is None, "still running after the ready line"
    first = await managed.stop()
    second = await managed.stop()
    assert first is not None and second == first
    assert managed.exit_code == first


@pytest.mark.asyncio
async def test_managed_process_reports_an_early_exit_with_its_stderr(process_api, fast_stop) -> None:
    source = "import sys; print('boot failed: port in use', file=sys.stderr); sys.exit(7)"
    managed = process_api.ManagedProcess(invocation(process_api, child(source), timeout_seconds=15.0))
    outcome = await managed.start(READY)
    await managed.stop()
    assert outcome.ready_line is None and outcome.exit_code == 7 and outcome.timed_out is False
    assert "port in use" in outcome.stderr_tail


@pytest.mark.asyncio
async def test_managed_process_times_out_when_never_ready(process_api, fast_stop) -> None:
    managed = process_api.ManagedProcess(invocation(process_api, child(f"import time; print('booting', flush=True); time.sleep({CHILD_LIMIT_SECONDS})"), timeout_seconds=0.5))
    started = time.monotonic()
    outcome = await managed.start(READY)
    await managed.stop()
    assert outcome.timed_out is True and outcome.ready_line is None
    assert time.monotonic() - started < 0.5 + 3 * fast_stop.kill_wait + fast_stop.slack


@pytest.mark.asyncio
async def test_managed_process_keeps_draining_after_ready(process_api, fast_stop, tmp_path: Path, wait_until) -> None:
    # §8.5: after the ready line, stdout and stderr keep draining so the child never blocks on a full pipe.
    marker = tmp_path / "wrote-everything.txt"
    source = f"""
import sys, time
print("opencode server listening on http://127.0.0.1:4321", flush=True)
sys.stdout.write("x" * 2_000_000); sys.stdout.flush()
sys.stderr.write("y" * 2_000_000); sys.stderr.flush()
open({str(marker)!r}, "w").write("done")
time.sleep({CHILD_LIMIT_SECONDS})
"""
    managed = process_api.ManagedProcess(invocation(process_api, child(source), timeout_seconds=15.0))
    await managed.start(READY)
    try:
        assert await wait_until(marker.exists, 20.0), "the child blocked writing to an undrained pipe"
    finally:
        await managed.stop()


@pytest.mark.asyncio
async def test_managed_process_ignores_stdin_text_and_uses_devnull(process_api, fast_stop) -> None:
    # §8.5: ManagedProcess always gives the child DEVNULL and ignores invocation.stdin_text.
    source = "import sys; data = sys.stdin.read(); print('opencode server listening on http://127.0.0.1:' + str(1000 + len(data)), flush=True); import time; time.sleep(30)"
    with never_ending_stdin():
        managed = process_api.ManagedProcess(invocation(process_api, child(source), stdin_text="ignored text", timeout_seconds=5.0))
        outcome = await managed.start(READY)
    await managed.stop()
    assert outcome.timed_out is False
    assert outcome.ready_line is not None and outcome.ready_line.endswith(":1000")


@pytest.mark.asyncio
async def test_managed_process_reports_a_missing_program(process_api, tmp_path: Path) -> None:
    managed = process_api.ManagedProcess(invocation(process_api, (str(tmp_path / "no-opencode"),)))
    outcome = await managed.start(READY)
    assert outcome.launch_failure is process_api.ProcessLaunchFailure.NOT_FOUND
    assert await managed.stop() is None


@pytest.mark.asyncio
@posix_only
async def test_stop_tree_kills_a_term_ignoring_process_and_its_group(process_api, fast_stop, wait_until, process_running) -> None:
    # §8.5 ProcessStopper: killpg TERM, wait, killpg KILL, bounded final wait; returns the exit code.
    source = GRANDCHILD_SOURCE.replace("import subprocess, sys, time", "import signal, subprocess, sys, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)")
    process = await asyncio.create_subprocess_exec(*child(source), stdout=asyncio.subprocess.PIPE, start_new_session=True)
    grandchild = int((await process.stdout.readline()).split()[0])
    started = time.monotonic()
    code = await process_api.ProcessStopper.stop_tree(process, grace_seconds=0.3)
    assert time.monotonic() - started < 3 * 0.3 + fast_stop.slack
    assert code is not None and process.returncode is not None
    assert await wait_until(lambda: not process_running(grandchild), 2.0)


@pytest.mark.asyncio
@posix_only
async def test_stop_tree_reaches_the_group_after_the_leader_exited(process_api, fast_stop, wait_until, process_running) -> None:
    # EC-10 / D-23: killpg runs even when the leader already exited and was reaped.
    source = f"""
import subprocess, sys
grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep({CHILD_LIMIT_SECONDS})"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(grandchild.pid, flush=True)
"""
    process = await asyncio.create_subprocess_exec(*child(source), stdout=asyncio.subprocess.PIPE, start_new_session=True)
    grandchild = int((await process.stdout.readline()).split()[0])
    await process.wait()
    assert process_running(grandchild)
    await process_api.ProcessStopper.stop_tree(process, grace_seconds=0.3)
    assert await wait_until(lambda: not process_running(grandchild), 2.0)
