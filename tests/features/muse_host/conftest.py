"""FILE: tests/features/muse_host/conftest.py

PURPOSE: Shared offline fixtures for the muse_host feature pack: the lazy feature imports, the scripted fake `muse` (fake_muse_peer.py) and its log reader, a fake `wsl.exe` for the Windows WSL mode, host builders, shrunk stop timings, and the error-shape checks every row test uses.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/muse_host/. The fake runs as a real child process through MuseHostSettings.muse_command, the seam spec §13 names; nothing in the host, the transport or CliRunner is mocked.
ARCHITECTURE NOTE: Every vidbyte import happens inside a fixture, so a missing MuseHost, record or constant fails each test at setup instead of aborting collection of the suite. The WSL mode is reached on Windows through a fake wsl.exe built at test time from pip's own console-script launcher (the bytes pip puts in front of every entry-point .exe) plus a zipped __main__ that runs fake_muse_peer.py; the distro name is always FAKE_DISTRO, so even a host that wrongly ran the real wsl.exe could only reach a distro that does not exist.
FUNCTION INVENTORY: muse_api returns a namespace of the spec §8.5 and §9.1 names; MuseFake writes scenarios and reads the fake's JSONL logs; muse_fake builds one per test; make_muse_host builds a MuseHost on the fake; make_wsl_host builds one in WSL mode on the fake wsl.exe; fast_stop shrinks NATIVE_STOP_GRACE_SECONDS and NATIVE_KILL_WAIT_SECONDS; check_native_error and check_tool_error assert the INV-7/INV-8 error shapes; wait_until polls a condition with a deadline; process_running reports POSIX liveness.
COMMON MODIFICATION PATTERNS: Add a scenario default in default_scenario and read it in fake_muse_peer.py; add a fixture here only when two or more modules in this pack need it.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub MuseHost, McpStdioTransport or CliRunner; a missing feature must stay red. 2. Do not let any fixture resolve the real muse or wsl.exe: every native host gets an explicit muse_command, and every WSL host uses FAKE_DISTRO with the fake wsl.exe first on PATH. 3. Never use the distro name MuseUbuntu1 in a test that starts a process.
KNOWN EDGE CASES: The scenario's release file is how a test ends a held turn; held fakes exit by themselves after sixty seconds. Context keys are checked against the spec §13 list, so a new key needs a spec change first. make_wsl_host skips outside Windows and when pip's launcher file is missing.
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5, §9, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import io
import json
import os
import sys
import zipfile
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

FAKE_MUSE = Path(__file__).with_name("fake_muse_peer.py")
KNOWN_SESSION = "2d4c6e8f-1a3b-4c5d-8e7f-9a0b1c2d3e4f"
OTHER_SESSION = "7e6d5c4b-3a29-4817-b6a5-948372615040"
NEW_SESSION = "0192f0c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f"
FORK_SESSION = "0192f0c4-aaaa-7bbb-8ccc-dddddddddddd"
TURN_ID = "turn-0001"
FAKE_DISTRO = "VidbyteFakeDistro"
PROMPT = "List the top-level folders."
REPLY_TEXT = "alpha\n\nbeta"
FAST_GRACE_SECONDS = 0.3
FAST_KILL_WAIT_SECONDS = 0.5
SLACK_SECONDS = 2.0
POLL_SECONDS = 0.05
CONTEXT_KEYS = frozenset({
    "reason", "field", "vendor_code", "vendor_error", "vendor_kind", "retryable", "status_code", "version",
    "available_models", "available_providers", "live_turns", "truncated", "session_id", "exit_code", "status",
    "features", "distros", "retry_attempt", "method", "error_type",
})


def default_scenario(log_dir: Path, release_file: Path) -> dict[str, Any]:
    # The happy path for every invocation the host can make; tests override single keys.
    return {
        "log_dir": str(log_dir),
        "release_file": str(release_file),
        "env_keys": [],
        "version": {"stdout": "Muse Code 1.0.1 (1.0.1-R2006.1)\n", "exit": 0},
        "sessions": [KNOWN_SESSION, OTHER_SESSION],
        "new_session_id": NEW_SESSION,
        "fork_session_id": FORK_SESSION,
        "fork_turns": [TURN_ID],
        "msp": {
            "model/list": {"models": [{"modelId": "muse-large"}, {"modelId": "muse-fast"}]},
            "session/list": {"pages": [[KNOWN_SESSION, OTHER_SESSION]]},
        },
        "turn": {"turn_id": TURN_ID, "items": [{"text": "alpha"}, {"text": "beta"}], "mode": "complete", "terminal": "completed"},
        "wsl": {"distros": [FAKE_DISTRO, "OtherDistro"], "muse_path": "/usr/local/bin/muse"},
    }


def deep_merge(base: dict[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    # Nested dicts merge key by key; any other value, lists included, replaces the default.
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def member_name(code: str) -> str:
    # Spec §6.3.1: member names are the upper-cased value with "." replaced by "_".
    return code.upper().replace(".", "_")


def wsl_launcher_bytes() -> bytes | None:
    # pip's console-script launcher: run `<python> <this exe> args...`, where the exe ends with a zipped __main__.
    try:
        pip = importlib.import_module("pip")
    except ImportError:
        return None
    path = Path(pip.__file__).parent / "_vendor" / "distlib" / "t64.exe"
    return path.read_bytes() if path.is_file() else None


class MuseFake:
    """Writes scenarios for fake_muse_peer.py and reads what its processes logged."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        self.log_dir = root / "fake-log"
        self.log_dir.mkdir()
        self.release_file = root / "release.flag"
        self.wsl_folder = root / "wsl-bin"
        self.scenarios = 0

    def scenario(self, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return deep_merge(default_scenario(self.log_dir, self.release_file), overrides or {})

    def write_scenario(self, overrides: Mapping[str, Any] | None = None) -> Path:
        self.scenarios += 1
        path = self.root / f"scenario-{self.scenarios}.json"
        path.write_text(json.dumps(self.scenario(overrides)), encoding="utf-8")
        return path

    def command(self, overrides: Mapping[str, Any] | None = None) -> tuple[str, ...]:
        return (sys.executable, "-u", str(FAKE_MUSE), str(self.write_scenario(overrides)))

    def missing_command(self) -> tuple[str, ...]:
        return (str(self.root / "no-such-folder" / "muse"),)

    def not_executable_command(self) -> tuple[str, ...]:
        path = self.root / "muse-not-a-program.txt"
        path.write_text("this file is not a program\n", encoding="utf-8")
        return (str(path),)

    def build_wsl(self, launcher: bytes, overrides: Mapping[str, Any] | None = None) -> Path:
        # A fake wsl.exe whose zipped __main__ runs the fake with this scenario and `--as-wsl wsl.exe` first.
        scenario_path = self.write_scenario(overrides)
        main = f"import runpy, sys\nsys.argv = [{str(FAKE_MUSE)!r}, {str(scenario_path)!r}, '--as-wsl', 'wsl.exe', *sys.argv[1:]]\nrunpy.run_path({str(FAKE_MUSE)!r}, run_name='__main__')\n"
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("__main__.py", main)
        self.wsl_folder.mkdir(exist_ok=True)
        shebang = f'#!"{sys.executable}"\r\n'.encode("utf-8")
        (self.wsl_folder / "wsl.exe").write_bytes(launcher + shebang + archive.getvalue())
        return self.wsl_folder

    def release(self) -> None:
        self.release_file.write_text("go", encoding="utf-8")

    def records(self, kind: str | None = None) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for path in sorted(self.log_dir.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = json.loads(line)
                    if kind is None or record["kind"] == kind:
                        found.append(record)
        return found

    def starts(self, role: str | None = None) -> list[dict[str, Any]]:
        return [record for record in self.records("start") if role is None or record["role"] == role]

    def launches(self, role: str | None = None) -> list[list[str]]:
        return [record["argv"] for record in self.starts(role)]

    def pids(self, role: str | None = None) -> list[int]:
        return [record["pid"] for record in self.starts(role)]

    def received(self, method: str | None = None) -> list[dict[str, Any]]:
        frames = [record["frame"] for record in self.records("frame")]
        return [frame for frame in frames if method is None or frame.get("method") == method]

    def received_methods(self) -> list[str]:
        return [frame["method"] for frame in self.received() if isinstance(frame.get("method"), str)]


@pytest.fixture
def muse_api() -> SimpleNamespace:
    # Spec §8.5 and §9.1 names, imported lazily so a missing module fails setup, not collection.
    host_module = importlib.import_module("vidbyte.harnesses.native.muse")
    muse_records = importlib.import_module("vidbyte.lib.dataclasses.muse")
    native_records = importlib.import_module("vidbyte.lib.dataclasses.native_hosts")
    native_enums = importlib.import_module("vidbyte.lib.enums.native_hosts")
    errors = importlib.import_module("vidbyte.lib.errors")
    return SimpleNamespace(
        MuseHost=host_module.MuseHost,
        MuseHostSettings=muse_records.MuseHostSettings,
        MuseTurnRequest=muse_records.MuseTurnRequest,
        records=muse_records,
        NativeTurnHandle=native_records.NativeTurnHandle,
        NativeTurnResult=native_records.NativeTurnResult,
        NativeHarness=native_enums.NativeHarness,
        NativeTurnStatus=native_enums.NativeTurnStatus,
        InterruptSource=native_enums.InterruptSource,
        ApprovalOutcome=native_enums.ApprovalOutcome,
        MuseReasoningEffort=native_enums.MuseReasoningEffort,
        MuseViewDirection=native_enums.MuseViewDirection,
        NativeHostError=errors.NativeHostError,
        ConfigurationError=errors.ConfigurationError,
        FailureCode=importlib.import_module("vidbyte.lib.enums.failure").FailureCode,
        constants=importlib.import_module("vidbyte.lib.constants.native_hosts"),
    )


@pytest.fixture
def muse_tools_api() -> SimpleNamespace:
    toolsets = importlib.import_module("vidbyte.tools.toolsets")
    tool_types = importlib.import_module("vidbyte.tools.types")
    return SimpleNamespace(
        MuseTools=toolsets.MuseTools,
        ToolCall=tool_types.ToolCall,
        ToolStatus=tool_types.ToolStatus,
        ToolPermission=tool_types.ToolPermission,
        ToolExecutor=importlib.import_module("vidbyte.tools.executor").ToolExecutor,
        PermissionPolicy=importlib.import_module("vidbyte.tools.security").PermissionPolicy,
        muse_tools_module=importlib.import_module("vidbyte.tools.builtins.muse"),
    )


@pytest.fixture
def muse_fake(tmp_path: Path) -> MuseFake:
    return MuseFake(tmp_path)


@pytest.fixture
def make_muse_host(muse_api: SimpleNamespace, muse_fake: MuseFake) -> Callable[..., Any]:
    def build(overrides: Mapping[str, Any] | None = None, *, command: tuple[str, ...] | None = None, control_timeout_seconds: float = 10.0, max_live_turns: int = 4) -> Any:
        muse_command = command if command is not None else muse_fake.command(overrides)
        settings = muse_api.MuseHostSettings(
            workspace=muse_fake.workspace,
            muse_command=muse_command,
            control_timeout_seconds=control_timeout_seconds,
            max_live_turns=max_live_turns,
        )
        return muse_api.MuseHost(settings)

    return build


@pytest.fixture
def make_wsl_host(muse_api: SimpleNamespace, muse_fake: MuseFake, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    # Spec §13: WSL mode is win32-only; the fake wsl.exe stands in for the real one, which no test may run.
    if sys.platform != "win32":
        pytest.skip("MuseHost's WSL mode exists only on win32 (D-19)")
    launcher = wsl_launcher_bytes()
    if launcher is None:
        pytest.skip("pip's console-script launcher (distlib t64.exe) is needed to build the fake wsl.exe")
    system_folder = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")

    def build(overrides: Mapping[str, Any] | None = None, *, muse_path: str | None = None, control_timeout_seconds: float = 10.0) -> Any:
        folder = muse_fake.build_wsl(launcher, overrides)
        monkeypatch.setenv("PATH", os.pathsep.join([str(folder), system_folder]))
        fields: dict[str, Any] = {"workspace": muse_fake.workspace, "wsl_distro": FAKE_DISTRO, "control_timeout_seconds": control_timeout_seconds}
        if muse_path is not None:
            fields["muse_path"] = muse_path
        return muse_api.MuseHost(muse_api.MuseHostSettings(**fields))

    return build


@pytest.fixture
def fast_stop(muse_api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    # Spec §9.3: the stop timings are read through the constants module at call time.
    monkeypatch.setattr(muse_api.constants, "NATIVE_STOP_GRACE_SECONDS", FAST_GRACE_SECONDS)
    monkeypatch.setattr(muse_api.constants, "NATIVE_KILL_WAIT_SECONDS", FAST_KILL_WAIT_SECONDS)
    return SimpleNamespace(grace=FAST_GRACE_SECONDS, kill_wait=FAST_KILL_WAIT_SECONDS, slack=SLACK_SECONDS)


@pytest.fixture
def check_native_error(muse_api: SimpleNamespace) -> Callable[..., None]:
    def check(error: BaseException, *, code: str, token: str, operation: str | None = None) -> None:
        assert isinstance(error, muse_api.NativeHostError), f"expected NativeHostError, got {type(error).__name__}: {error}"
        assert error.failure_code is muse_api.FailureCode[member_name(code)], f"expected {code}, got {error.failure_code.value}: {error}"
        assert error.next_step.strip(), "INV-8: next_step is never empty"
        assert token in error.next_step, f"next_step {error.next_step!r} lacks the required token {token!r}"
        if operation is not None:
            assert error.operation == operation
        assert all(isinstance(key, str) and isinstance(value, str) for key, value in error.context.items()), "spec §13: every context value is a str"
        assert set(error.context) <= CONTEXT_KEYS, f"unexpected context keys {set(error.context) - CONTEXT_KEYS}"

    return check


@pytest.fixture
def check_tool_error(muse_tools_api: SimpleNamespace) -> Callable[..., None]:
    def check(result: Any, *, code: str, token: str, tool_name: str, harness: str = "muse") -> None:
        assert result.status is muse_tools_api.ToolStatus.ERROR, f"expected an error result, got {result.output!r}"
        metadata = result.metadata
        assert metadata["error"] == code, f"expected {code}, got {metadata.get('error')}: {result.output}"
        assert token in metadata["next_step"], f"next_step {metadata['next_step']!r} lacks {token!r}"
        assert metadata["hint"] == metadata["next_step"], "INV-7: hint repeats next_step"
        assert metadata["operation"] == tool_name
        assert metadata["harness"] == harness
        assert result.output.startswith(f"{code}: "), result.output
        assert result.output.endswith(f" Next step: {metadata['next_step']}"), result.output

    return check


@pytest.fixture
def wait_until() -> Callable[[Callable[[], bool], float], Awaitable[bool]]:
    async def poll(predicate: Callable[[], bool], timeout: float) -> bool:
        # Bounded polling, the prior art in test_bash_tool_process_bounds.py; never a fixed sleep.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if predicate():
                return True
            await asyncio.sleep(POLL_SECONDS)
        return predicate()

    return poll


@pytest.fixture
def process_running() -> Callable[[int], bool]:
    def running(pid: int) -> bool:
        # POSIX only. A zombie has already exited, so only a live process counts as running.
        stat_path = Path("/proc") / str(pid) / "stat"
        if Path("/proc/self").exists():
            try:
                stat = stat_path.read_text(encoding="utf-8")
            except OSError:
                return False
            return stat.rsplit(")", 1)[1].split()[0] not in ("Z", "X")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    return running


def tool_named(toolset: Any, name: str) -> Any:
    tools = {tool.name: tool for tool in toolset.all()}
    assert name in tools, f"toolset lacks {name}: {sorted(tools)}"
    return tools[name]


@pytest.fixture
def tool_by_name() -> Callable[[Any, str], Any]:
    return tool_named
