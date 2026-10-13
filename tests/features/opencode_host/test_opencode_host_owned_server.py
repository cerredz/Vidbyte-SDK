"""FILE: tests/features/opencode_host/test_opencode_host_owned_server.py

PURPOSE: The owned `opencode serve` lifecycle (FR-18, AC-9): the launch argv, the per-host login and random password in the child's environment only, the listening line, backend key copies (D-16), every start failure (EC-54 to EC-56, EC-60, EC-61), a server that dies between calls (EC-153), and the stop and reap on every exit path (INV-4, NFR-2).
ROLE IN CODEBASE: Start here for a leftover opencode process, a password on argv, or a host that hangs at start. Covers vidbyte.harnesses.native.opencode.server and ManagedProcess through OpencodeHost's public surface.
ARCHITECTURE NOTE: fake_opencode_serve.py runs as a real child through OpencodeHostSettings.opencode_command and prints the listening line; HTTP to the printed address is answered by FakeOpencodeServer through the MockTransport patch, so the process lifecycle and the HTTP behaviour are tested together without a real server.
FUNCTION INVENTORY: owned_settings builds owned-mode settings; digest hashes a value the way the fake logs it; poll_until_process_exited calls the host until EC-56 appears or a deadline passes; the test_* functions are one rule each.
COMMON MODIFICATION PATTERNS: Assert upper bounds with fast_timings.slack; keep liveness checks behind posix_only, the prior art in tests/features/coding_agent/test_bash_tool_process_bounds.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare or print the password itself in a message; compare digests. 2. Do not let PATH include a folder that may hold the real opencode in the not-installed test.
KNOWN EDGE CASES: On Windows the server's tree is stopped with taskkill, and liveness is not checked portably, so those checks are POSIX-only. EC-153 is observed through the host: until the process exit is collected, a failed call may still read as server_unreachable, so the test polls the host with a deadline.
RELATED DOCS: tests/features/opencode_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md FR-18, AC-9, EC-54 to EC-56, EC-60, EC-61, EC-153, NFR-2, D-16, D-18
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host/test_opencode_host_owned_server.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

OWNED_PORT = 41234
STARTED_WITHIN_SECONDS = 20.0
EXIT_SEEN_WITHIN_SECONDS = 10.0
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="liveness checks are POSIX-only by spec §13; Windows has no portable equivalent")


def owned_settings(api: Any, workspace: Path, command: tuple[str, ...] | None, **fields: Any) -> Any:
    return api.OpencodeHostSettings(workspace=workspace, opencode_command=command, **fields)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def contains_pair(argv: list[str], flag: str, value: str) -> bool:
    return any(argv[index] == flag and argv[index + 1] == value for index in range(len(argv) - 1))


@pytest.mark.asyncio
async def test_owned_server_starts_on_loopback_with_a_fresh_password_in_its_environment_only(opencode_api, fake_opencode, serve_fake, fast_timings) -> None:
    # AC-9 / FR-18 / T-4: `serve --hostname 127.0.0.1 --port 0`; login and random password only in the child's environment.
    command = serve_fake.command(noise_lines=["Warning: telemetry disabled", "loading config"])
    async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, command)) as host:
        await host.list_opencode_sessions()
    start = serve_fake.records("start")
    assert len(start) == 1
    argv = start[0]["argv"]
    assert argv[0] == "serve"
    assert contains_pair(argv, "--hostname", "127.0.0.1") and contains_pair(argv, "--port", "0")
    env = start[0]["env"]
    assert env["OPENCODE_SERVER_USERNAME"]["value"] == "vidbyte"
    assert env["OPENCODE_SERVER_PASSWORD"]["present"] is True and env["OPENCODE_SERVER_PASSWORD"]["length"] >= 32
    credentials = {item.auth for item in fake_opencode.requests}
    assert len(credentials) == 1, "every request carries the same basic-auth pair"
    login, server_password = credentials.pop()
    assert login == "vidbyte"
    assert digest(server_password) == env["OPENCODE_SERVER_PASSWORD"]["sha256"], "the password the host sends is the one it gave the server"
    assert all(server_password not in part for part in argv), "INV-6: never on argv"
    assert os.environ.get("OPENCODE_SERVER_PASSWORD") != server_password, "D-18: an overlay for the child, never set in the caller's environment"
    assert {(item.host, item.port) for item in fake_opencode.requests} == {("127.0.0.1", OWNED_PORT)}, "the host uses the address the server printed"


@pytest.mark.asyncio
async def test_each_owned_server_gets_its_own_password(opencode_api, fake_opencode, serve_fake, fast_timings) -> None:
    # FR-18: a fresh secrets.token_urlsafe(32) per host.
    for _ in range(2):
        async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, serve_fake.command())):
            pass
    digests = [record["env"]["OPENCODE_SERVER_PASSWORD"]["sha256"] for record in serve_fake.records("start")]
    assert len(digests) == 2 and digests[0] != digests[1]


@pytest.mark.asyncio
@posix_only
async def test_owned_server_and_its_tree_are_stopped_on_exit_within_the_bound(opencode_api, fake_opencode, serve_fake, fast_timings, wait_until, process_running) -> None:
    # AC-9 / INV-4 / NFR-2: the owned server stops within 2 × K, its whole tree included, even when it ignores SIGTERM.
    command = serve_fake.command(grandchild=True, ignore_term=True)
    async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, command)):
        started = time.monotonic()
    elapsed = time.monotonic() - started
    pids = serve_fake.pids()
    assert len(pids) == 2
    assert await wait_until(lambda: not any(process_running(pid) for pid in pids), fast_timings.slack)
    assert elapsed < 2 * fast_timings.kill_wait + fast_timings.slack


@pytest.mark.asyncio
async def test_owned_server_exit_returns_within_the_bound(opencode_api, fake_opencode, serve_fake, fast_timings) -> None:
    # NFR-2 on every OS: __aexit__ of an owned server returns within 2 × K plus slack.
    async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, serve_fake.command(grandchild=True))):
        started = time.monotonic()
    assert time.monotonic() - started < 2 * fast_timings.kill_wait + fast_timings.slack


@pytest.mark.asyncio
async def test_no_opencode_anywhere_raises_not_installed(opencode_api, fake_opencode, fast_timings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, check_native_error) -> None:
    # EC-54: opencode_command unset and shutil.which("opencode") finds nothing.
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with pytest.raises(opencode_api.NativeHostError) as caught:
        async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, None)):
            pass
    check_native_error(caught.value, code="opencode.not_installed", token="opencode_command")
    assert caught.value.next_step == "Install opencode 1.18.31 or newer, or set OpencodeHostSettings.opencode_command."
    assert fake_opencode.requests == []


@pytest.mark.asyncio
async def test_a_missing_launcher_raises_not_installed(opencode_api, fake_opencode, serve_fake, fast_timings, check_native_error) -> None:
    # EC-54: the launch raises FileNotFoundError.
    with pytest.raises(opencode_api.NativeHostError) as caught:
        async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, serve_fake.missing_command())):
            pass
    check_native_error(caught.value, code="opencode.not_installed", token="opencode_command")


@pytest.mark.asyncio
async def test_a_launcher_that_cannot_run_raises_process_exited(opencode_api, fake_opencode, serve_fake, fast_timings, check_native_error) -> None:
    # EC-56: the launch raises another OSError.
    with pytest.raises(opencode_api.NativeHostError) as caught:
        async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, serve_fake.not_executable_command())):
            pass
    check_native_error(caught.value, code="opencode.process_exited", token="OpencodeHost")


@pytest.mark.asyncio
async def test_a_server_that_exits_before_its_address_raises_process_exited(opencode_api, fake_opencode, serve_fake, fast_timings, check_native_error) -> None:
    # EC-56: the owned server exits before printing the listening line; the exit code is in the context.
    with pytest.raises(opencode_api.NativeHostError) as caught:
        async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, serve_fake.command(mode="exit_early", exit_code=3))):
            pass
    check_native_error(caught.value, code="opencode.process_exited", token="OpencodeHost")
    assert caught.value.context["exit_code"] == "3"
    assert fake_opencode.requests == []


@pytest.mark.asyncio
async def test_a_server_that_never_prints_its_address_is_stopped_and_unreachable(opencode_api, fake_opencode, serve_fake, fast_timings, wait_until, process_running, check_native_error) -> None:
    # EC-55 / INV-3 / INV-4: no listening line within startup_timeout_seconds; the server is stopped and reaped first.
    settings = owned_settings(opencode_api, fake_opencode.workspace, serve_fake.command(mode="silent"), startup_timeout_seconds=0.5)
    started = time.monotonic()
    with pytest.raises(opencode_api.NativeHostError) as caught:
        async with opencode_api.OpencodeHost(settings):
            pass
    elapsed = time.monotonic() - started
    check_native_error(caught.value, code="opencode.server_unreachable", token="request_timeout_seconds")
    assert elapsed < 0.5 + 2 * fast_timings.kill_wait + fast_timings.slack
    if sys.platform != "win32":
        pids = serve_fake.pids()
        assert pids and await wait_until(lambda: not any(process_running(pid) for pid in pids), fast_timings.slack)


@pytest.mark.asyncio
async def test_an_old_owned_server_is_stopped_and_reported(opencode_api, fake_opencode, serve_fake, fast_timings, wait_until, process_running, check_native_error) -> None:
    # EC-60: the version from /global/health is below 1.18.31; the owned server is stopped.
    fake_opencode.health = {"healthy": True, "version": "1.18.30"}
    with pytest.raises(opencode_api.NativeHostError) as caught:
        async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, serve_fake.command())):
            pass
    check_native_error(caught.value, code="opencode.version_unsupported", token="opencode upgrade")
    if sys.platform != "win32":
        pids = serve_fake.pids()
        assert pids and await wait_until(lambda: not any(process_running(pid) for pid in pids), 2 * fast_timings.kill_wait + fast_timings.slack)


@pytest.mark.asyncio
@pytest.mark.parametrize(("backend", "variable", "value"), [("GLM", "GLM_API_KEY", None), ("DEEPSEEK", "DEEPSEEK_API_KEY", "   ")])
async def test_a_backend_without_its_key_fails_before_the_server_starts(backend: str, variable: str, value: str | None, opencode_api, fake_opencode, serve_fake, fast_timings, monkeypatch: pytest.MonkeyPatch, check_native_error) -> None:
    # EC-61: the source key variable is unset or blank; checked before any process starts.
    if value is None:
        monkeypatch.delenv(variable, raising=False)
    else:
        monkeypatch.setenv(variable, value)
    settings = owned_settings(opencode_api, fake_opencode.workspace, serve_fake.command(), backends=(opencode_api.HarnessBackendName[backend],))
    with pytest.raises(opencode_api.NativeHostError) as caught:
        async with opencode_api.OpencodeHost(settings):
            pass
    check_native_error(caught.value, code="backend.not_signed_in", token=variable)
    assert serve_fake.records("start") == [], "EC-61: no process starts"


@pytest.mark.asyncio
async def test_backend_keys_reach_the_server_environment_only(opencode_api, fake_opencode, serve_fake, fast_timings, monkeypatch: pytest.MonkeyPatch) -> None:
    # D-16 / D-18: GLM_API_KEY is copied into ZHIPU_API_KEY and DEEPSEEK_API_KEY is passed, in the server's environment only.
    glm_value = "glm-" + uuid.uuid4().hex
    deepseek_value = "ds-" + uuid.uuid4().hex
    monkeypatch.setenv("GLM_API_KEY", glm_value)
    monkeypatch.setenv("DEEPSEEK_API_KEY", deepseek_value)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    backends = (opencode_api.HarnessBackendName.GLM, opencode_api.HarnessBackendName.DEEPSEEK)
    async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, serve_fake.command(), backends=backends)):
        pass
    start = serve_fake.records("start")[0]
    assert start["env"]["ZHIPU_API_KEY"]["sha256"] == digest(glm_value)
    assert start["env"]["DEEPSEEK_API_KEY"]["sha256"] == digest(deepseek_value)
    assert all(glm_value not in part and deepseek_value not in part for part in start["argv"]), "INV-6: keys never go on argv"
    assert "ZHIPU_API_KEY" not in os.environ, "the copy is an overlay for the child only"


@pytest.mark.asyncio
async def test_a_server_that_dies_between_calls_is_not_restarted(opencode_api, fake_opencode, serve_fake, fast_timings, wait_until, check_native_error) -> None:
    # EC-153 / EC-56: later calls raise process_exited with the exit code; the host never restarts the server.
    async with opencode_api.OpencodeHost(owned_settings(opencode_api, fake_opencode.workspace, serve_fake.command(exit_code=7))) as host:
        await host.list_opencode_sessions()
        serve_fake.kill_server()
        assert await wait_until(lambda: bool(serve_fake.records("exiting")), EXIT_SEEN_WITHIN_SECONDS)
        fake_opencode.dead = True
        error = await poll_until_process_exited(host, opencode_api)
    check_native_error(error, code="opencode.process_exited", token="OpencodeHost", operation="list_opencode_sessions")
    assert error.context["exit_code"] == "7"
    assert len(serve_fake.records("start")) == 1, "EC-153: the host does not restart the server"


async def poll_until_process_exited(host: Any, api: Any) -> Any:
    # Until the exit is collected a failed call may read as server_unreachable; anything else is a defect.
    loop = asyncio.get_running_loop()
    deadline = loop.time() + EXIT_SEEN_WITHIN_SECONDS
    last: Any = None
    while loop.time() < deadline:
        try:
            await host.list_opencode_sessions()
        except api.NativeHostError as error:
            last = error
            if error.failure_code is api.FailureCode.OPENCODE_PROCESS_EXITED:
                return error
            assert error.failure_code is api.FailureCode.OPENCODE_SERVER_UNREACHABLE, f"unexpected {error.failure_code.value}"
        await asyncio.sleep(0.05)
    raise AssertionError(f"no opencode.process_exited within {EXIT_SEEN_WITHIN_SECONDS} s; last error {last!r}")


@pytest.mark.asyncio
async def test_cancelling_aenter_stops_the_server_it_started(opencode_api, fake_opencode, serve_fake, fast_timings, wait_until, process_running) -> None:
    # AC-4 / EC-4 / INV-2: cancellation while waiting for the listening line propagates and reaps the server.
    settings = owned_settings(opencode_api, fake_opencode.workspace, serve_fake.command(mode="silent", grandchild=True), startup_timeout_seconds=60.0)
    host = opencode_api.OpencodeHost(settings)
    task = asyncio.create_task(host.__aenter__())
    assert await wait_until(lambda: bool(serve_fake.records("grandchild")), STARTED_WITHIN_SECONDS)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    if sys.platform != "win32":
        pids = serve_fake.pids()
        assert await wait_until(lambda: not any(process_running(pid) for pid in pids), 2 * fast_timings.kill_wait + fast_timings.slack)
