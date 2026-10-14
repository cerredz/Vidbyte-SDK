"""FILE: tests/features/prebuilt_tools/test_prebuilt_side_effects.py

PURPOSE: Prove that prebuilt tools touch nothing outside their arguments: no socket, process, environment read, clock read, or file open while they run (AC-13, INV-13), no global-state change, and no eval, exec, compile, unseeded randomness, or security-grade use of md5 or sha1 in their source (INV-13, INV-19, T-5, T-6).
ROLE IN CODEBASE: Instruments socket, subprocess, os.environ, time, and open around FunctionTool.execute calls on the vidbyte.tools.toolsets.PrebuiltTools library, and parses every module under vidbyte/tools/builtins/prebuilt/ with ast.
ARCHITECTURE NOTE: The instruments record a call only when a frame from vidbyte/tools/builtins/prebuilt/ is on the stack, so the event loop's own sockets and pytest's own file access never count. The static scan covers what instruments cannot see, such as datetime.now() on a C type or a name bound with from-import before the patch.
FUNCTION INVENTORY: SideEffectRecorder records calls made from tool frames; RecordingEnviron wraps os.environ; install_instruments patches the seams with monkeypatch; test_tool_calls_touch_no_outside_resource runs every tool; test_global_interpreter_state_is_unchanged checks INV-13's global state list; source_findings and the test_prebuilt_source_* tests scan the source tree.
COMMON MODIFICATION PATTERNS: Add a seam to install_instruments and a name to the banned tables together; keep the recorder's stack filter so harness activity never counts.
WHAT NOT TO DO IN THIS FILE: 1. Do not mock the standard library modules the tools use for their work; only the side-effect seams listed in spec §13 are instrumented. 2. Do not widen the source allow-list to make a finding pass; fix the tool.
KNOWN EDGE CASES: The worker thread posts its result back to the event loop through a socket write; that is a method call on an existing socket from asyncio's own frames, so it is neither a construction nor a tool frame. ast.literal_eval is allowed only in code_analysis.py (python_literal_to_json), as INV-19 states.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (INV-13, INV-19, AC-13, §10 T-5 and T-6, §13)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_side_effects.py
"""

from __future__ import annotations

import ast
import builtins
import csv
import decimal
import inspect
import io
import os
import random
import socket
import subprocess
import sys
import time
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_catalogue_data import ALL_TOOL_NAMES, CATEGORY_TABLE
from tests.features.prebuilt_tools.prebuilt_tool_harness import SchemaArgumentFactory, ToolRunner

PREBUILT_SOURCE_DIRECTORY = Path(__file__).resolve().parents[3] / "vidbyte" / "tools" / "builtins" / "prebuilt"
TOOL_FRAME_MARKER = "/vidbyte/tools/builtins/prebuilt/"
TIME_READERS = ("time", "time_ns", "localtime", "gmtime", "ctime", "asctime", "strftime", "monotonic", "perf_counter", "process_time")
BANNED_IMPORT_ROOTS = frozenset(
    {"socket", "subprocess", "shutil", "tempfile", "threading", "multiprocessing", "concurrent", "ctypes", "secrets", "zoneinfo", "locale"}
    | {"signal", "glob", "pathlib", "pickle", "marshal", "shelve", "sqlite3", "webbrowser", "ftplib", "smtplib", "poplib", "imaplib", "asyncio"}
)
BANNED_IMPORT_MODULES = frozenset({"urllib.request", "http.client", "http.server", "http.cookiejar"})
BANNED_BUILTIN_CALLS = frozenset({"eval", "exec", "compile", "open", "input", "breakpoint", "__import__"})
BANNED_METHOD_CALLS = frozenset(
    {"now", "today", "utcnow", "fromtimestamp", "utcfromtimestamp", "strptime", "set_int_max_str_digits", "setrecursionlimit"}
    | {"getcontext", "setcontext", "field_size_limit", "uuid1", "uuid4", "getenv", "putenv", "system", "popen", "urandom", "getcwd"}
)
WEAK_HASHES = frozenset({"md5", "sha1"})


class SideEffectRecorder:
    """Collects (seam, detail) for each instrumented call made while a prebuilt tool frame is on the stack."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def note(self, seam: str, detail: object) -> None:
        frame = inspect.currentframe()
        while frame is not None:
            if TOOL_FRAME_MARKER in frame.f_code.co_filename.replace("\\", "/"):
                self.calls.append((seam, repr(detail)[:120]))
                return
            frame = frame.f_back


class RecordingEnviron(MutableMapping[str, str]):
    """os.environ stand-in that records every read made from tool code and delegates everything."""

    def __init__(self, wrapped: MutableMapping[str, str], recorder: SideEffectRecorder) -> None:
        self._wrapped = wrapped
        self._recorder = recorder

    def __getitem__(self, key: str) -> str:
        self._recorder.note("os.environ", key)
        return self._wrapped[key]

    def __setitem__(self, key: str, value: str) -> None:
        self._recorder.note("os.environ write", key)
        self._wrapped[key] = value

    def __delitem__(self, key: str) -> None:
        self._recorder.note("os.environ delete", key)
        del self._wrapped[key]

    def __iter__(self) -> Iterator[str]:
        self._recorder.note("os.environ", "iterate")
        return iter(self._wrapped)

    def __len__(self) -> int:
        return len(self._wrapped)

    def copy(self) -> dict[str, str]:
        self._recorder.note("os.environ", "copy")
        return dict(self._wrapped)


def recording(recorder: SideEffectRecorder, seam: str, original: Any) -> Any:
    """Wrap a callable so tool-originated calls are recorded before the original runs."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        recorder.note(seam, args[:2])
        return original(*args, **kwargs)

    return wrapper


def refusing(recorder: SideEffectRecorder, seam: str) -> Any:
    """Wrap a process-starting callable so a tool-originated call is recorded and never starts anything."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        recorder.note(seam, args[:1])
        raise RuntimeError(f"{seam} was called during a prebuilt tool test")

    return wrapper


def install_instruments(monkeypatch: pytest.MonkeyPatch) -> SideEffectRecorder:
    """Patch every AC-13 seam with a recorder that only counts calls from tool frames."""
    recorder = SideEffectRecorder()

    class RecordingSocket(socket.socket):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            recorder.note("socket.socket", args[:2])
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", RecordingSocket)
    monkeypatch.setattr(socket, "create_connection", recording(recorder, "socket.create_connection", socket.create_connection))
    monkeypatch.setattr(socket, "getaddrinfo", recording(recorder, "socket.getaddrinfo", socket.getaddrinfo))
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, refusing(recorder, f"subprocess.{name}"))
    monkeypatch.setattr(os, "system", refusing(recorder, "os.system"))
    monkeypatch.setattr(os, "environ", RecordingEnviron(os.environ, recorder))
    for name in TIME_READERS:
        monkeypatch.setattr(time, name, recording(recorder, f"time.{name}", getattr(time, name)))
    monkeypatch.setattr(builtins, "open", recording(recorder, "open", builtins.open))
    monkeypatch.setattr(io, "open", recording(recorder, "io.open", io.open))
    return recorder


@pytest.mark.parametrize("name", ALL_TOOL_NAMES)
def test_tool_calls_touch_no_outside_resource(tool_runner: ToolRunner, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """AC-13 and INV-13: running the tool on varied arguments opens no socket, process, environment, clock, or file."""
    schema = dict(tool_runner.tool(name).spec().input_schema or {})
    argument_sets = SchemaArgumentFactory().argument_sets(name, schema)[:4]
    recorder = install_instruments(monkeypatch)
    for arguments in argument_sets:
        tool_runner.result(name, arguments)
    assert recorder.calls == [], f"{name} touched outside resources: {recorder.calls[:5]}"


def global_state() -> tuple[Any, ...]:
    """The INV-13 global settings: int digit limit, recursion limit, decimal context, csv field limit, random state."""
    context = decimal.getcontext()
    field_limit = csv.field_size_limit()
    return (sys.get_int_max_str_digits(), sys.getrecursionlimit(), context.prec, context.rounding, tuple(context.traps.items()), field_limit, random.getstate())


def test_global_interpreter_state_is_unchanged(tool_runner: ToolRunner) -> None:
    """INV-13: running every tool leaves the int digit limit, recursion limit, decimal context, csv limit, and random generator as they were."""
    before = global_state()
    for name in ALL_TOOL_NAMES:
        schema = dict(tool_runner.tool(name).spec().input_schema or {})
        for arguments in SchemaArgumentFactory().argument_sets(name, schema)[:2]:
            tool_runner.result(name, arguments)
    assert global_state() == before


def prebuilt_modules() -> list[Path]:
    """Every Python module of the prebuilt package; asserting the expected set keeps the scan from passing on an empty tree."""
    modules = sorted(PREBUILT_SOURCE_DIRECTORY.glob("*.py"))
    expected = {f"{value}.py" for value, _, _ in CATEGORY_TABLE} | {"__init__.py", "_support.py"}
    assert expected <= {path.name for path in modules}, f"missing prebuilt modules: {sorted(expected - {path.name for path in modules})}"
    return modules


def import_findings(node: ast.AST) -> list[str]:
    names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
    return [f"imports {name}" for name in names if name.split(".")[0] in BANNED_IMPORT_ROOTS or name in BANNED_IMPORT_MODULES]


def call_findings(node: ast.Call, module_name: str) -> list[str]:
    function = node.func
    if isinstance(function, ast.Name) and function.id in BANNED_BUILTIN_CALLS:
        return [f"calls {function.id}()"]
    if not isinstance(function, ast.Attribute):
        return []
    receiver = function.value.id if isinstance(function.value, ast.Name) else ""
    findings = []
    if function.attr in BANNED_METHOD_CALLS:
        findings.append(f"calls .{function.attr}()")
    if receiver == "random" and function.attr != "Random":
        findings.append(f"uses the global random generator: random.{function.attr}()")
    if receiver in {"time", "os"} and function.attr not in {"path", "fspath"}:
        findings.append(f"calls {receiver}.{function.attr}()")
    if function.attr == "literal_eval" and module_name != "code_analysis.py":
        findings.append("calls ast.literal_eval outside python_literal_to_json")
    weak = function.attr in WEAK_HASHES or (function.attr == "new" and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in WEAK_HASHES)
    security_flag = any(keyword.arg == "usedforsecurity" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False for keyword in node.keywords)
    if receiver == "hashlib" and weak and not security_flag:
        findings.append(f"builds hashlib.{function.attr} without usedforsecurity=False (T-6)")
    return findings


def source_findings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings = []
    for node in ast.walk(tree):
        findings.extend(import_findings(node))
        if isinstance(node, ast.Call):
            findings.extend(call_findings(node, path.name))
        if isinstance(node, ast.Attribute) and node.attr == "environ":
            findings.append("reads os.environ")
    return [f"{path.name}:{finding}" for finding in findings]


def test_prebuilt_source_has_no_side_effect_or_code_execution_calls() -> None:
    """INV-13, INV-19, T-5, T-6: no banned import, no eval/exec/compile/open, no clock or environment read, no global random, and md5/sha1 only for checksums."""
    findings = [finding for path in prebuilt_modules() for finding in source_findings(path)]
    assert findings == [], findings
