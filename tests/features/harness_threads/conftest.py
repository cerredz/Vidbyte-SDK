"""FILE: tests/features/harness_threads/conftest.py

PURPOSE: Shared offline fixtures for the harness_threads pack: lazy imports of the spec §8.5 contract names, a sandbox with a redirected user home, a workspace, skill folders and an empty PATH folder, the scripted stand-in (fake_harness.py) with its log reader, `.exe`/script stand-ins for PATH lookups, the INV-5 error check, and process liveness checks for both platforms.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/harness_threads/. The stand-in runs as a real child process through the config records' <harness>_command fields (spec §13 "Real seams"); nothing in the thread functions, CliRunner or the filesystem is mocked.
ARCHITECTURE NOTE: Every vidbyte import happens inside a fixture (lib_api, api), so a missing module fails each test at setup instead of aborting collection of the whole suite; lib_api needs only the vidbyte.lib names, so the process, argv and record tests can pass before the harness modules land. The sandbox is made by tmp_path_factory.mktemp("case") so no path holds a harness name, and the user home and the workspace are sibling folders (spec §13, R-17). PATH holds only the sandbox's own bin folder, so no test can reach a real grok, opencode, muse or wsl.exe.
FUNCTION INVENTORY: lib_api and api return namespaces of contract names; Sandbox builds the folders, scenarios, stand-ins and snapshots and reads the stand-in logs; sandbox builds one per test with the home, PATH and temp folder redirected; call runs one thread function against the stand-in; check_error asserts the INV-5 attributes and message order; fast_stop shrinks NATIVE_KILL_WAIT_SECONDS; wait_until polls with a deadline; process_alive reports liveness on win32 and POSIX; launcher_bytes finds pip's console-script launcher for `.exe` stand-ins.
COMMON MODIFICATION PATTERNS: Add a stand-in behaviour as a scenario field read by fake_harness.py; add a fixture here only when two or more modules in this pack need it.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub the thread functions, CliRunner or the filesystem; a missing feature must stay red. 2. Do not leave PATH, USERPROFILE or HOME pointing at the developer's machine: the Grok fallback is `~/.grok/bin/grok.exe`, which exists on the author's machine. 3. Never name the WSL distro MuseUbuntu1; the stand-in distro is FAKE_DISTRO.
KNOWN EDGE CASES: pip's distlib `t64.exe` is the launcher behind every `.exe` stand-in; tests that need one skip when pip lacks it. Liveness on win32 uses OpenProcess/GetExitCodeProcess (STILL_ACTIVE 259). Path text in messages is compared in both native and POSIX spelling, and case-insensitively on win32 (shutil.which returns PATHEXT suffixes in upper case).
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6, §8.5, §9, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

PACK = Path(__file__).resolve().parent
REPO_ROOT = PACK.parents[2]
FAKE = PACK / "fake_harness.py"
HARNESSES = ("grok", "opencode", "muse")
VERBS = ("run", "continue", "fork")
LABELS = {"grok": "Grok Build", "opencode": "opencode", "muse": "Muse Code"}
COMMAND_FIELDS = {"grok": "grok_command", "opencode": "opencode_command", "muse": "muse_command"}
CONFIG_NAMES = {"grok": "GrokThreadConfig", "opencode": "OpencodeThreadConfig", "muse": "MuseThreadConfig"}
OPENCODE_MODEL = "deepseek/deepseek-v4-pro"
API_KEY = "vbk-test-0123456789abcdef0123456789abcdef"
PROMPT = "List the top-level folders."
FAKE_DISTRO = "VidbyteFakeDistro"
OTHER_DISTRO = "VidbyteOtherDistro"
CALL_TIMEOUT_SECONDS = 60.0
BUILT_CONFIG = object()
FAST_KILL_WAIT_SECONDS = 0.5
SLACK_SECONDS = 5.0
POLL_SECONDS = 0.05
EXCLUDED_FROM_SNAPSHOT = ("fake",)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def key_digest(text: str) -> dict[str, Any]:
    return {"sha256": sha256(text), "length": len(text)}


def private_home(home: Path, workspace: Path) -> Path:
    # INV-13 / D-24: <home>/.vidbyte/grok-homes/<first 16 hex of
    # sha256(normcase(resolved workspace))>.
    key = hashlib.sha256(os.path.normcase(str(workspace.resolve())).encode("utf-8")).hexdigest()[:16]
    return home / ".vidbyte" / "grok-homes" / key


def wsl_form(path: Path) -> str:
    # MusePathTranslator.to_wsl: C:\a\b -> /mnt/c/a/b.
    resolved = Path(path).resolve()
    return "/mnt/" + resolved.drive[0].lower() + "/" + "/".join(resolved.parts[1:])


def path_spellings(path: Path | str) -> tuple[str, ...]:
    text = str(path)
    return tuple(dict.fromkeys((text, Path(text).as_posix())))


def launcher_bytes() -> bytes | None:
    # pip's console-script launcher: runs `<python from the shebang>
    # <this exe>`, where the exe ends with a zipped __main__.
    try:
        pip = importlib.import_module("pip")
    except ImportError:
        return None
    path = Path(pip.__file__).parent / "_vendor" / "distlib" / "t64.exe"
    return path.read_bytes() if path.is_file() else None


class Sandbox:
    """One test's folders, stand-in scenarios and stand-in logs."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.workspace = root / "ws"
        self.skill_root = root / "skill-src"
        self.bin = root / "bin"
        self.tmp = root / "tmp"
        self.fake_root = root / "fake"
        self.log_dir = self.fake_root / "log"
        self.state_dir = self.fake_root / "state"
        self.release_file = self.fake_root / "release.flag"
        for folder in (self.home, self.workspace, self.skill_root, self.bin, self.tmp, self.log_dir, self.state_dir):
            folder.mkdir(parents=True)
        self.scenarios = 0

    def scenario(self, program: str, **fields: Any) -> Path:
        self.scenarios += 1
        path = self.fake_root / f"scenario-{self.scenarios:03d}.json"
        data = {"program": program, "log_dir": str(self.log_dir), "state_dir": str(self.state_dir), "release_file": str(self.release_file), **fields}
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def command(self, program: str, **fields: Any) -> tuple[str, ...]:
        return (sys.executable, "-u", str(FAKE), str(self.scenario(program, **fields)))

    def stand_in(self, folder: Path, name: str, program: str, *, as_wsl: bool = False, **fields: Any) -> Path:
        # An executable named like the vendor program that runs
        # fake_harness.py: an `.exe` on win32, a script on POSIX.
        scenario = self.scenario(program, **fields)
        extra = ["--as-wsl"] if as_wsl else []
        body = f"import runpy, sys\nsys.argv = [{str(FAKE)!r}, {str(scenario)!r}, *{extra!r}, *sys.argv[1:]]\nrunpy.run_path({str(FAKE)!r}, run_name='__main__')\n"
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            launcher = launcher_bytes()
            if launcher is None:
                pytest.skip("pip's console-script launcher (distlib t64.exe) is needed to build an .exe stand-in")
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("__main__.py", body)
            target = folder / (name if name.lower().endswith(".exe") else name + ".exe")
            target.write_bytes(launcher + f'#!"{sys.executable}"\r\n'.encode("utf-8") + archive.getvalue())
            return target
        target = folder / name
        target.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        target.chmod(0o755)
        return target

    def batch_file(self, folder: Path, name: str) -> tuple[Path, Path]:
        # A Windows batch launcher that would leave a marker file if
        # anything ever ran it.
        folder.mkdir(parents=True, exist_ok=True)
        marker = self.fake_root / f"{name}.ran"
        target = folder / name
        target.write_text(f'@echo off\r\necho ran> "{marker}"\r\n', encoding="utf-8")
        return target, marker

    def make_skill(self, name: str, *, parent: Path | None = None, body: str | None = None, extra_files: dict[str, str] | None = None) -> Path:
        folder = (parent or self.skill_root) / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(body or f"---\nname: {name}\ndescription: Test skill {name}.\n---\nUse {name}.\n", encoding="utf-8")
        for relative, text in (extra_files or {}).items():
            path = folder / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return folder

    def release(self) -> None:
        self.release_file.write_text("go", encoding="utf-8")

    def records(self, kind: str | None = None, role: str | None = None) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for path in sorted(self.log_dir.glob("*.jsonl"), key=lambda item: int(item.name.split("-", 1)[0])):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                record["role_file"] = path.name.split("-", 1)[1].rsplit("-", 1)[0]
                if (kind is None or record["kind"] == kind) and (role is None or record["role_file"] == role):
                    found.append(record)
        return found

    def starts(self, role: str | None = None) -> list[dict[str, Any]]:
        return self.records("start", role)

    def only_start(self, role: str) -> dict[str, Any]:
        starts = self.starts(role)
        assert len(starts) == 1, f"expected exactly one {role} start, got {[record['argv'] for record in starts]}"
        return starts[0]

    def answers(self, role: str | None = None) -> list[dict[str, Any]]:
        return self.records("answer", role)

    def snapshot(self, *, include_fake: bool = False) -> dict[str, tuple[str, int, str]]:
        # Every file and folder under the sandbox root, except the
        # stand-in's own logs, scenarios and vendor state.
        entries: dict[str, tuple[str, int, str]] = {}
        for path in sorted(self.root.rglob("*")):
            relative = path.relative_to(self.root).as_posix()
            if not include_fake and relative.split("/", 1)[0] in EXCLUDED_FROM_SNAPSHOT:
                continue
            if path.is_symlink():
                entries[relative] = ("link", 0, os.readlink(path))
            elif path.is_dir():
                entries[relative] = ("dir", 0, "")
            else:
                data = path.read_bytes()
                entries[relative] = ("file", len(data), hashlib.sha256(data).hexdigest())
        return entries

    def grok_home(self, workspace: Path | None = None) -> Path:
        return private_home(self.home, workspace or self.workspace)


@pytest.fixture
def lib_api() -> SimpleNamespace:
    # vidbyte.lib names only (spec §8.5), imported lazily so a missing
    # module fails setup, not collection.
    records = importlib.import_module("vidbyte.lib.dataclasses.native_threads")
    process_records = importlib.import_module("vidbyte.lib.dataclasses.process")
    process = importlib.import_module("vidbyte.lib.process")
    errors = importlib.import_module("vidbyte.lib.errors")
    return SimpleNamespace(
        records=records,
        NativeThreadRequest=records.NativeThreadRequest,
        NativeThreadResult=records.NativeThreadResult,
        GrokThreadConfig=records.GrokThreadConfig,
        OpencodeThreadConfig=records.OpencodeThreadConfig,
        MuseThreadConfig=records.MuseThreadConfig,
        CliOption=process_records.CliOption,
        CliInvocation=process_records.CliInvocation,
        CliOutcome=process_records.CliOutcome,
        CliArgv=process.CliArgv,
        CliRunner=process.CliRunner,
        ProcessStopper=process.ProcessStopper,
        process=process,
        CliOptionStyle=importlib.import_module("vidbyte.lib.enums.process").CliOptionStyle,
        ProcessLaunchFailure=importlib.import_module("vidbyte.lib.enums.process").ProcessLaunchFailure,
        enums=importlib.import_module("vidbyte.lib.enums.native_threads"),
        enums_package=importlib.import_module("vidbyte.lib.enums"),
        constants=importlib.import_module("vidbyte.lib.constants.native_threads"),
        FailureCode=importlib.import_module("vidbyte.lib.enums.failure").FailureCode,
        NativeThreadError=errors.NativeThreadError,
        ConfigurationError=errors.ConfigurationError,
        AgentExecutionError=errors.AgentExecutionError,
    )


@pytest.fixture
def api(lib_api: SimpleNamespace) -> SimpleNamespace:
    # The nine public functions (spec §8.5), imported lazily from
    # vidbyte.harnesses.native.
    native = importlib.import_module("vidbyte.harnesses.native")
    functions = {(harness, verb): getattr(native, f"{verb}_{harness}_thread") for harness in HARNESSES for verb in VERBS}
    return SimpleNamespace(**vars(lib_api), native=native, functions=functions, configs={harness: getattr(lib_api, CONFIG_NAMES[harness]) for harness in HARNESSES})


@pytest.fixture
def sandbox(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    # Spec §13 user-home seam: USERPROFILE (win32) and HOME (POSIX)
    # point at the sandbox home, a sibling of the workspace.
    box = Sandbox(tmp_path_factory.mktemp("case").resolve())
    monkeypatch.setenv("USERPROFILE", str(box.home))
    monkeypatch.setenv("HOME", str(box.home))
    monkeypatch.setenv("PATH", str(box.bin))
    monkeypatch.setattr(tempfile, "tempdir", str(box.tmp))
    return box


@pytest.fixture
def call(api: SimpleNamespace, sandbox: Sandbox) -> Callable[..., Awaitable[Any]]:
    async def run(harness: str, verb: str = "run", prompt: str = PROMPT, *, thread_id: str | None = None, command: tuple[str, ...] | None = None, fake: dict[str, Any] | None = None, config: dict[str, Any] | None = None, raw_config: Any = BUILT_CONFIG, **arguments: Any) -> Any:
        # One thread function against the stand-in; `fake` is the
        # stand-in scenario, `config` extra config fields; `raw_config`
        # is handed to the function as `config=` unchanged (EC-33: a
        # value of the wrong type).
        function = api.functions[(harness, verb)]
        launcher = command if command is not None else sandbox.command(harness, **(fake or {}))
        config_fields = {COMMAND_FIELDS[harness]: launcher, "timeout_seconds": CALL_TIMEOUT_SECONDS, **(config or {})}
        keywords: dict[str, Any] = {"api_key": API_KEY, "workspace": sandbox.workspace, "config": api.configs[harness](**config_fields) if raw_config is BUILT_CONFIG else raw_config}
        if harness == "opencode":
            keywords["model"] = OPENCODE_MODEL
        keywords.update(arguments)
        positional = (prompt,) if verb == "run" else (thread_id, prompt)
        return await function(*positional, **keywords)

    return run


def find_in_order(message: str, parts: Iterable[tuple[str, tuple[str, ...]]], *, fold: bool = False) -> None:
    # INV-5: each element must appear after the previous one; any
    # spelling in a tuple counts.
    haystack = message.lower() if fold else message
    position = 0
    for label, spellings in parts:
        hits = [(haystack.find(text.lower() if fold else text, position), text) for text in spellings]
        hits = [(index, text) for index, text in hits if index >= 0]
        assert hits, f"INV-5: {label} ({spellings[0]!r}) is missing from the message after position {position}: {message!r}"
        index, text = min(hits)
        position = index + len(text)


@pytest.fixture
def check_error(api: SimpleNamespace, sandbox: Sandbox) -> Callable[..., None]:
    def check(error: BaseException, *, harness: str, verb: str, code: str, workspace: Path | None = None, thread_id: str | None | bool = False, observations: Iterable[tuple[str, tuple[str, ...]]] = (), vendor: str | None = None, exit_code: int | None | bool = False) -> None:
        # INV-5 attributes and message order; thread_id/exit_code False
        # means "do not check".
        assert isinstance(error, api.NativeThreadError), f"expected NativeThreadError, got {type(error).__name__}: {error}"
        assert isinstance(error, api.AgentExecutionError)
        assert error.failure_code.value == code, f"expected {code}, got {error.failure_code.value}: {error}"
        assert isinstance(error.failure_code, api.FailureCode)
        assert error.harness == api.enums.NativeHarness(harness)
        operation = f"{verb}_{harness}_thread"
        assert error.operation == api.enums.NativeThreadOperation(operation)
        assert error.likely_cause == api.constants.NATIVE_THREAD_LIKELY_CAUSES[error.failure_code], "likely_cause must be the text written for this code"
        assert error.next_step == api.constants.NATIVE_THREAD_NEXT_STEPS[error.failure_code], "next_step must be the text written for this code"
        assert error.likely_cause.strip() and error.next_step.strip()
        if thread_id is not False:
            assert error.thread_id == thread_id, f"thread_id {error.thread_id!r} != {thread_id!r}"
        if exit_code is not False:
            assert error.exit_code == exit_code, f"exit_code {error.exit_code!r} != {exit_code!r}"
        message = str(error)
        parts: list[tuple[str, tuple[str, ...]]] = [("function name", (operation,)), ("failure code", (code,)), ("harness label", (LABELS[harness],))]
        if workspace is not None:
            parts.append(("workspace", path_spellings(workspace.resolve())))
        if isinstance(thread_id, str):
            parts.append(("thread id", (thread_id,)))
        parts.extend(observations)
        if vendor is not None:
            parts.append(("vendor text", (vendor,)))
            assert error.vendor_message is not None and vendor in error.vendor_message
        parts.extend([("likely cause", (error.likely_cause,)), ("next step", (error.next_step,))])
        find_in_order(message, parts, fold=sys.platform == "win32")
        assert len(re.findall(r"[.!?](?:\s|$)", message)) >= 3, f"INV-5: the message is several complete sentences: {message!r}"

    return check


@pytest.fixture
def fast_stop(lib_api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    # Spec §13 timing knobs: read through
    # vidbyte.lib.constants.native_threads at call time.
    monkeypatch.setattr(lib_api.constants, "NATIVE_KILL_WAIT_SECONDS", FAST_KILL_WAIT_SECONDS)
    return SimpleNamespace(kill_wait=FAST_KILL_WAIT_SECONDS, slack=SLACK_SECONDS)


@pytest.fixture
def wait_until() -> Callable[[Callable[[], bool], float], Awaitable[bool]]:
    async def poll(predicate: Callable[[], bool], timeout: float) -> bool:
        # Bounded polling; never a fixed sleep.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if predicate():
                return True
            await asyncio.sleep(POLL_SECONDS)
        return predicate()

    return poll


def process_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259
        finally:
            kernel32.CloseHandle(handle)
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


@pytest.fixture
def alive() -> Callable[[int], bool]:
    return process_alive


@pytest.fixture
def wsl_ready(sandbox: Sandbox) -> None:
    # Muse WSL mode exists only on win32, and the wsl.exe stand-in needs
    # pip's launcher.
    if sys.platform != "win32":
        pytest.skip("Muse WSL mode exists only on win32 (spec §9.2, EC-29)")
    if launcher_bytes() is None:
        pytest.skip("pip's console-script launcher (distlib t64.exe) is needed to build the wsl.exe stand-in")


@pytest.fixture
def pack() -> SimpleNamespace:
    # Pack constants and pure helpers; test modules cannot import
    # conftest by name (no __init__.py in pack folders).
    return SimpleNamespace(
        API_KEY=API_KEY, PROMPT=PROMPT, LABELS=LABELS, HARNESSES=HARNESSES, VERBS=VERBS, OPENCODE_MODEL=OPENCODE_MODEL,
        FAKE_DISTRO=FAKE_DISTRO, OTHER_DISTRO=OTHER_DISTRO, REPO_ROOT=REPO_ROOT, FAKE=FAKE, CALL_TIMEOUT_SECONDS=CALL_TIMEOUT_SECONDS,
        COMMAND_FIELDS=COMMAND_FIELDS, SLACK_SECONDS=SLACK_SECONDS, key_digest=key_digest, private_home=private_home, wsl_form=wsl_form,
        path_spellings=path_spellings, find_in_order=find_in_order, launcher_bytes=launcher_bytes,
    )
