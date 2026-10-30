"""FILE: tests/features/claude_code_agent/claude_code_support.py

PURPOSE: Shared helpers for the offline Claude Code harness agent tests: a sandbox whose PATH holds only a `claude` stand-in that runs fake_claude.py, whose temp folder is redirected into the test's own folder, and whose environment has no provider credential; helpers to script the stand-in, read what it received, build settings, and tell whether a process is still alive.
ROLE IN CODEBASE: Imported by conftest.py (the sandbox fixture) and by every offline test in this folder as tests.features.claude_code_agent.claude_code_support. The stand-in is the only `claude` any test starts.
ARCHITECTURE NOTE: The stand-in is a real executable found through PATH, as the agent finds Claude Code: on Windows a claude.exe made from pip's console-script launcher (distlib t64.exe) with a zipped __main__, on POSIX a script with a shebang. It sets FAKE_CLAUDE_HOME to the sandbox's state folder before running fake_claude.py, so the state path never depends on the environment the agent passes on.
FUNCTION INVENTORY: launcher_bytes finds pip's launcher; ClaudeSandbox builds the folders and the stand-in, scripts scenarios and reads the log; make_sandbox prepares one with the environment patched; settings builds ClaudeCodeHarnessAgentSettings with test defaults; process_alive reports whether a pid still runs.
COMMON MODIFICATION PATTERNS: A new stand-in behavior is a `mode` in fake_claude.py, scripted here through ClaudeSandbox.scenario.
KNOWN EDGE CASES: Tests that need an .exe stand-in skip when pip ships no t64.exe. tempfile.tempdir is patched, so the agent's own temporary workspace and instructions folders are created under the sandbox and can be inspected.
RELATED DOCS: tests/features/claude_code_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/claude_code_agent
"""

from __future__ import annotations

import importlib
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

from vidbyte.agents.claude_code import ClaudeCodeHarnessAgentSettings

FAKE = Path(__file__).with_name("fake_claude.py")
INSTRUCTIONS = "You are a careful test advisor.\nAnswer in one line."
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
PARENT_VARIABLES = {
    "CLAUDECODE": "1",
    "CLAUDE_CODE_ENTRYPOINT": "cli",
    "CLAUDE_CODE_SESSION_ID": "11111111-2222-3333-4444-555555555555",
    "CLAUDE_CODE_CHILD_SESSION": "1",
    "CLAUDE_CODE_MESSAGING_SOCKET": "parent-socket",
    "CLAUDE_CODE_MESSAGING_TOKEN": "parent-token-value",
    "CLAUDE_CODE_SESSION_ATTENDED": "1",
    "CLAUDE_CODE_EXECPATH": "parent-claude.exe",
    "CLAUDE_EFFORT": "xhigh",
    "CLAUDE_PID": "4242",
}
CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_BEARER_TOKEN_BEDROCK", "ANTHROPIC_VERTEX_API_KEY")


def launcher_bytes() -> bytes | None:
    # pip's console-script launcher: runs `<python from the shebang> <this exe>`,
    # where the exe ends with a zipped __main__.
    try:
        pip = importlib.import_module("pip")
    except ImportError:
        return None
    path = Path(pip.__file__).parent / "_vendor" / "distlib" / "t64.exe"
    return path.read_bytes() if path.is_file() else None


class ClaudeSandbox:
    """One test's folders, the claude stand-in on PATH, its scenarios and its log."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.bin = root / "bin"
        self.home = root / "fake-home"
        self.tmp = root / "tmp"
        self.workspace = root / "workspace"
        for folder in (self.bin, self.home, self.tmp, self.workspace):
            folder.mkdir(parents=True)
        self.claude = self.stand_in(self.bin, "claude")

    def stand_in(self, folder: Path, name: str) -> Path:
        # An executable named like Claude Code that runs fake_claude.py with
        # this sandbox's state folder.
        body = f"import os, runpy, sys\nos.environ['FAKE_CLAUDE_HOME'] = {str(self.home)!r}\nsys.argv = [{str(FAKE)!r}, *sys.argv[1:]]\nrunpy.run_path({str(FAKE)!r}, run_name='__main__')\n"
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            launcher = launcher_bytes()
            if launcher is None:
                pytest.skip("pip's console-script launcher (distlib t64.exe) is needed to build a claude.exe stand-in")
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("__main__.py", body)
            target = folder / (name if name.lower().endswith(".exe") else name + ".exe")
            target.write_bytes(launcher + f'#!"{sys.executable}"\r\n'.encode() + archive.getvalue())
            return target
        target = folder / name
        target.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        target.chmod(0o755)
        return target

    def scenario(self, *entries: dict[str, Any]) -> None:
        # One entry per run, in order; the last one repeats.
        (self.home / "scenario.json").write_text(json.dumps(list(entries) or [{}]), encoding="utf-8")

    def records(self) -> list[dict[str, Any]]:
        # What the stand-in received, one record per run.
        log = self.home / "log.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def leftovers(self) -> list[str]:
        # Folders the agent left in the redirected temp folder.
        return sorted(item.name for item in self.tmp.iterdir())


def make_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ClaudeSandbox:
    # PATH holds only the stand-in; temp folders land in the sandbox; no
    # provider credential is in the environment; the parent Claude Code
    # session's variables are set, so tests can prove they are left out.
    box = ClaudeSandbox(tmp_path.resolve())
    monkeypatch.setenv("PATH", str(box.bin))
    monkeypatch.setattr(tempfile, "tempdir", str(box.tmp))
    for name in CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
    for name, value in PARENT_VARIABLES.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(box.root / "claude-config"))
    return box


def settings(**overrides: Any) -> ClaudeCodeHarnessAgentSettings:
    # Test settings: a short time bound and fixed instructions.
    fields: dict[str, Any] = {"name": "test-advisor", "instructions": INSTRUCTIONS, "timeout_seconds": 60.0}
    fields.update(overrides)
    return ClaudeCodeHarnessAgentSettings(**fields)


def process_alive(pid: int) -> bool:
    # Whether pid still runs, without signalling it (os.kill on Windows would end it).
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
    stat = Path("/proc") / str(pid) / "stat"
    if Path("/proc/self").exists():
        try:
            return stat.read_text(encoding="utf-8").split(") ", 1)[1][:1] not in {"Z", "X"}
        except (OSError, IndexError):
            return False
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
