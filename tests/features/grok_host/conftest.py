"""FILE: tests/features/grok_host/conftest.py

PURPOSE: Shared offline fixtures for the grok_host feature pack: the lazy feature imports, the scripted fake `grok` (fake_grok_peer.py) and its log reader, host builders, shrunk stop timings, and the error-shape checks every row test uses.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/grok_host/. The fake runs as a real child process through GrokHostSettings.grok_command, the seam spec §13 names; nothing in the host, the transport or CliRunner is mocked.
ARCHITECTURE NOTE: Every vidbyte import happens inside a fixture, so a missing GrokHost, record or constant fails each test at setup instead of aborting collection of the suite. Helpers are exposed as fixtures because pack folders have no __init__.py and a second conftest module cannot be imported by name.
FUNCTION INVENTORY: grok_api returns a namespace of the spec §8.5 and §9.1 names; GrokFake writes scenarios and reads the fake's JSONL logs; grok_fake builds one per test; make_grok_host builds a GrokHost on the fake; fast_stop shrinks NATIVE_STOP_GRACE_SECONDS and NATIVE_KILL_WAIT_SECONDS; check_native_error and check_tool_error assert the INV-7/INV-8 error shapes; wait_until polls a condition with a deadline; process_running reports POSIX liveness.
COMMON MODIFICATION PATTERNS: Add a scenario default in default_scenario and read it in fake_grok_peer.py; add a fixture here only when two or more modules in this pack need it.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub GrokHost, McpStdioTransport or CliRunner; a missing feature must stay red. 2. Do not let any fixture resolve the real grok: every host here gets an explicit grok_command, and the PATH tests point PATH and HOME at empty folders.
KNOWN EDGE CASES: The scenario's release file is how a test ends a held turn; held fakes exit by themselves after sixty seconds. Context keys are checked against the spec §13 list, so a new key needs a spec change first.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5, §9, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import json
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

FAKE_GROK = Path(__file__).with_name("fake_grok_peer.py")
KNOWN_SESSION = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
OTHER_SESSION = "0c9b8a7d-6e5f-4a3b-9c2d-1e0f9a8b7c6d"
NEW_SESSION = "11111111-2222-4333-8444-555555555555"
PROMPT = "List the top-level folders."
FAST_GRACE_SECONDS = 0.3
FAST_KILL_WAIT_SECONDS = 0.5
SLACK_SECONDS = 2.0
POLL_SECONDS = 0.05
CONTEXT_KEYS = frozenset({
    "reason", "field", "vendor_code", "vendor_error", "vendor_kind", "retryable", "status_code", "version",
    "available_models", "available_providers", "live_turns", "truncated", "session_id", "exit_code", "status",
    "features", "distros", "retry_attempt", "method", "error_type",
})
DEFAULT_MODELS = [
    {"modelId": "grok-code-fast-1", "name": "Grok Code Fast", "description": "Fast coding model.", "_meta": {"reasoningEfforts": ["low", "medium", "high"]}},
    {"modelId": "grok-4-heavy", "name": "Grok 4 Heavy", "description": "Deep reasoning model.", "_meta": {"reasoningEfforts": ["high"]}},
]


def default_scenario(log_dir: Path, release_file: Path) -> dict[str, Any]:
    # The happy path for every invocation the host can make; tests override single keys.
    return {
        "log_dir": str(log_dir),
        "release_file": str(release_file),
        "env_keys": [],
        "version": {"stdout": "grok 1.0.52 (0920c8169e27) [stable]\n", "exit": 0},
        "models_cli": {"stdout": "grok-code-fast-1\ngrok-4-heavy\n", "exit": 0},
        "oneshot": {"text": "one-shot answer"},
        "acp": {
            "initialize": {"models": DEFAULT_MODELS, "agent_version": "1.0.52", "protocol_version": 1},
            "session_list": {"pages": [[{"sessionId": KNOWN_SESSION, "title": "Refactor the Parser"}, {"sessionId": OTHER_SESSION, "title": "Write release notes"}]]},
            "session_prompt": {"mode": "complete", "chunks": ["alpha", "-beta"], "stop_reason": "end_turn"},
        },
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


class GrokFake:
    """Writes scenarios for fake_grok_peer.py and reads what its processes logged."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        self.log_dir = root / "fake-log"
        self.log_dir.mkdir()
        self.release_file = root / "release.flag"
        self.scenarios = 0

    def scenario(self, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return deep_merge(default_scenario(self.log_dir, self.release_file), overrides or {})

    def command(self, overrides: Mapping[str, Any] | None = None) -> tuple[str, ...]:
        self.scenarios += 1
        path = self.root / f"scenario-{self.scenarios}.json"
        path.write_text(json.dumps(self.scenario(overrides)), encoding="utf-8")
        return (sys.executable, "-u", str(FAKE_GROK), str(path))

    def missing_command(self) -> tuple[str, ...]:
        return (str(self.root / "no-such-folder" / "grok"),)

    def not_executable_command(self) -> tuple[str, ...]:
        path = self.root / "grok-not-a-program.txt"
        path.write_text("this file is not a program\n", encoding="utf-8")
        return (str(path),)

    def release(self) -> None:
        self.release_file.write_text("go", encoding="utf-8")

    def records(self, kind: str | None = None) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        # Each fake names its log after its launch number (claim_launch_number), so this reads the processes in launch order.
        for path in sorted(self.log_dir.glob("*.jsonl"), key=lambda path: int(path.name.split("-", 1)[0])):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = json.loads(line)
                    if kind is None or record["kind"] == kind:
                        found.append(record)
        return found

    def launches(self, role: str | None = None) -> list[list[str]]:
        return [record["argv"] for record in self.records("start") if role is None or record["role"] == role]

    def pids(self, role: str | None = None) -> list[int]:
        return [record["pid"] for record in self.records("start") if role is None or record["role"] == role]

    def received(self, method: str | None = None) -> list[dict[str, Any]]:
        frames = [record["frame"] for record in self.records("frame")]
        return [frame for frame in frames if method is None or frame.get("method") == method]

    def received_methods(self) -> list[str]:
        return [frame["method"] for frame in self.received() if isinstance(frame.get("method"), str)]


@pytest.fixture
def grok_api() -> SimpleNamespace:
    # Spec §8.5 and §9.1 names, imported lazily so a missing module fails setup, not collection.
    host_module = importlib.import_module("vidbyte.harnesses.native.grok")
    grok_records = importlib.import_module("vidbyte.lib.dataclasses.grok")
    native_records = importlib.import_module("vidbyte.lib.dataclasses.native_hosts")
    native_enums = importlib.import_module("vidbyte.lib.enums.native_hosts")
    errors = importlib.import_module("vidbyte.lib.errors")
    failure = importlib.import_module("vidbyte.lib.enums.failure")
    return SimpleNamespace(
        GrokHost=host_module.GrokHost,
        run_grok_once=host_module.run_grok_once,
        GrokHostSettings=grok_records.GrokHostSettings,
        GrokTurnRequest=grok_records.GrokTurnRequest,
        GrokOneShotRequest=grok_records.GrokOneShotRequest,
        NativeTurnHandle=native_records.NativeTurnHandle,
        NativeTurnResult=native_records.NativeTurnResult,
        NativeHarness=native_enums.NativeHarness,
        NativeTurnStatus=native_enums.NativeTurnStatus,
        InterruptSource=native_enums.InterruptSource,
        ApprovalOutcome=native_enums.ApprovalOutcome,
        AcpToolKind=native_enums.AcpToolKind,
        GrokPermissionMode=native_enums.GrokPermissionMode,
        NativeHostError=errors.NativeHostError,
        ConfigurationError=errors.ConfigurationError,
        FailureCode=failure.FailureCode,
        constants=importlib.import_module("vidbyte.lib.constants.native_hosts"),
    )


@pytest.fixture
def grok_tools_api() -> SimpleNamespace:
    toolsets = importlib.import_module("vidbyte.tools.toolsets")
    tool_types = importlib.import_module("vidbyte.tools.types")
    return SimpleNamespace(
        GrokTools=toolsets.GrokTools,
        ToolCall=tool_types.ToolCall,
        ToolStatus=tool_types.ToolStatus,
        ToolPermission=tool_types.ToolPermission,
        ToolExecutor=importlib.import_module("vidbyte.tools.executor").ToolExecutor,
        PermissionPolicy=importlib.import_module("vidbyte.tools.security").PermissionPolicy,
        grok_tools_module=importlib.import_module("vidbyte.tools.builtins.grok"),
    )


@pytest.fixture
def grok_fake(tmp_path: Path) -> GrokFake:
    return GrokFake(tmp_path)


@pytest.fixture
def make_grok_host(grok_api: SimpleNamespace, grok_fake: GrokFake) -> Callable[..., Any]:
    def build(overrides: Mapping[str, Any] | None = None, *, command: tuple[str, ...] | None = None, control_timeout_seconds: float = 10.0, max_live_turns: int = 4) -> Any:
        grok_command = command if command is not None else grok_fake.command(overrides)
        settings = grok_api.GrokHostSettings(
            workspace=grok_fake.workspace,
            grok_command=grok_command,
            control_timeout_seconds=control_timeout_seconds,
            max_live_turns=max_live_turns,
        )
        return grok_api.GrokHost(settings)

    return build


@pytest.fixture
def fast_stop(grok_api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    # Spec §9.3: the stop timings are read through the constants module at call time.
    monkeypatch.setattr(grok_api.constants, "NATIVE_STOP_GRACE_SECONDS", FAST_GRACE_SECONDS)
    monkeypatch.setattr(grok_api.constants, "NATIVE_KILL_WAIT_SECONDS", FAST_KILL_WAIT_SECONDS)
    return SimpleNamespace(grace=FAST_GRACE_SECONDS, kill_wait=FAST_KILL_WAIT_SECONDS, slack=SLACK_SECONDS)


@pytest.fixture
def check_native_error(grok_api: SimpleNamespace) -> Callable[..., None]:
    def check(error: BaseException, *, code: str, token: str, operation: str | None = None) -> None:
        assert isinstance(error, grok_api.NativeHostError), f"expected NativeHostError, got {type(error).__name__}: {error}"
        assert error.failure_code is grok_api.FailureCode[member_name(code)], f"expected {code}, got {error.failure_code.value}: {error}"
        assert error.next_step.strip(), "INV-8: next_step is never empty"
        assert token in error.next_step, f"next_step {error.next_step!r} lacks the required token {token!r}"
        if operation is not None:
            assert error.operation == operation
        assert all(isinstance(key, str) and isinstance(value, str) for key, value in error.context.items()), "spec §13: every context value is a str"
        assert set(error.context) <= CONTEXT_KEYS, f"unexpected context keys {set(error.context) - CONTEXT_KEYS}"

    return check


@pytest.fixture
def check_tool_error(grok_tools_api: SimpleNamespace) -> Callable[..., None]:
    def check(result: Any, *, code: str, token: str, tool_name: str, harness: str = "grok") -> None:
        assert result.status is grok_tools_api.ToolStatus.ERROR, f"expected an error result, got {result.output!r}"
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
