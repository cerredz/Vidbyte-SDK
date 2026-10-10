"""FILE: tests/features/coding_agent/test_bash_tool_contract.py

PURPOSE: Pin what one completed BashTool call promises: its model-facing schema and fixed bounds, argument validation, combined output with a final exit-code line, the root folder as working directory, closed stdin, bounded capture, clear start failures, and the executable it picks on each OS.
ROLE IN CODEBASE: Calls vidbyte.tools.builtins.bash.BashTool directly with real bash subprocesses (Linux bash in CI, Git for Windows bash on Windows hosts).
ARCHITECTURE NOTE: Nothing is mocked except PATH, shutil.which, and sys.platform in the executable-lookup tests, which spec §13 names as the construction-time seam; every other test spawns a real process.
FUNCTION INVENTORY: test_bash_tool_declares_* (FR-9, D-11, INV-14); test_bash_rejects_* (AC-18); test_completed_command_* (AC-12, INV-13); test_command_runs_in_the_root_* (AC-16); test_command_reaches_bash_verbatim_* (INV-9); test_command_reading_stdin_* (EC-11); test_command_the_os_cannot_start_* (EC-15); test_invalid_utf8_* (EC-16); test_large_output_* (AC-13, INV-10, NFR-3); test_missing_bash_* (AC-17); test_windows_lookup_* (AC-22, INV-15, EC-13, EC-31).
COMMON MODIFICATION PATTERNS: Keep commands portable between GNU bash and Git for Windows bash; anything that needs process groups, setsid, or /proc belongs in test_bash_tool_process_bounds.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not replace the subprocess with a fake; the process boundary is the feature. 2. Do not pin the exact wording of the truncation or hint lines beyond what spec §8.5 fixes.
KNOWN EDGE CASES: A command's output may or may not end with a newline before the exit-code line, so tests read the first and last lines instead of comparing the whole text. The Windows lookup is exercised on POSIX hosts with shell-script stand-ins and sys.platform patched only while BashTool is built.
RELATED DOCS: tests/features/coding_agent/FEATURE.md; docs/spec/coding-agent/spec.md (§6.1 INV-9 to INV-15; §6.2 AC-12, AC-13, AC-16 to AC-18, AC-22; §8.5)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_bash_tool_contract.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tracemalloc
from pathlib import Path

import pytest

from vidbyte.tools.types import ToolCall, ToolPermission, ToolStatus

TWENTY_MEGABYTES = 20_000_000
# Generous ceiling for a capture that must stay near BASH_MAX_OUTPUT_BYTES plus one read chunk while 20 MB flow past.
PEAK_TRACED_BYTES = 8_000_000

posix_host_only = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in Git layout uses shell scripts, which only a POSIX host can execute")


def _bash_call(command: object) -> ToolCall:
    return ToolCall("bash", {"command": command})


def _write_script(path: Path, marker: str) -> None:
    # An executable stand-in that prints which binary was chosen, whatever arguments it gets.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\necho {marker}\n", encoding="utf-8")
    path.chmod(0o755)


def _stand_in_git_install(tmp_path: Path, git_location: str) -> dict[str, str]:
    # Builds <G>/bin/bash.exe, a git.exe at git_location under <G>, and an earlier PATH bash; returns what shutil.which should answer.
    git_root = tmp_path / "Git"
    _write_script(git_root / "bin" / "bash.exe", "git-bin-bash-chosen")
    git = git_root / git_location
    git.parent.mkdir(parents=True, exist_ok=True)
    git.write_text("", encoding="utf-8")
    path_bash = tmp_path / "earlier-on-path" / "bash"
    _write_script(path_bash, "path-bash-chosen")
    return {"git": str(git), "git.exe": str(git), "bash": str(path_bash), "bash.exe": str(path_bash)}


def _build_as_windows(bash_module, monkeypatch: pytest.MonkeyPatch, root: Path, which_answers: dict[str, str]) -> object:
    # The executable is resolved once in BashTool.__init__ (FR-11), so the platform is faked only while building it.
    with monkeypatch.context() as patch:
        patch.setattr(sys, "platform", "win32")
        patch.setattr(shutil, "which", lambda name, *args, **kwargs: which_answers.get(name))
        return bash_module.BashTool(root)


def test_bash_tool_declares_one_required_command_with_execute_permission_and_fixed_bounds(bash_module, tmp_path) -> None:
    # FR-9 / INV-14 / D-11: EXECUTE keeps bash denied under BaseAgent's default policy and out of automatic retries.
    tool = bash_module.BashTool(tmp_path)
    spec = tool.spec()

    assert spec.name == "bash"
    assert spec.permission is ToolPermission.EXECUTE
    assert [(parameter.name, parameter.type, parameter.required) for parameter in spec.parameters] == [("command", "string", True)]
    assert tool.root_dir == tmp_path.resolve()
    bounds = (bash_module.BASH_TIMEOUT_SECONDS, bash_module.BASH_MAX_OUTPUT_BYTES, bash_module.BASH_READ_CHUNK_BYTES, bash_module.BASH_KILL_GRACE_SECONDS)
    assert bounds == (600.0, 50_000, 65_536, 5.0)


@pytest.mark.parametrize(
    "arguments",
    [{}, {"command": None}, {"command": ""}, {"command": "  \t\n"}, {"command": 42}, {"command": ["echo", "hi"]}],
    ids=["missing", "null", "empty", "whitespace", "integer", "list"],
)
def test_bash_rejects_a_missing_blank_or_non_string_command_before_spawning(bash_module, tmp_path, arguments) -> None:
    # AC-18: the runtime calls validate_call before execute, so a rejected call never starts a process.
    tool = bash_module.BashTool(tmp_path)

    assert tool.validate_call(ToolCall("bash", arguments)) is not None
    assert tool.validate_call(_bash_call("echo ok")) is None


@pytest.mark.asyncio
async def test_completed_command_returns_both_streams_in_order_and_its_exit_code_as_success(bash_module, tmp_path) -> None:
    # AC-12 / INV-13 / D-12: a non-zero exit is information, not a failed call; stderr shares stdout's pipe and order.
    result = await bash_module.BashTool(tmp_path).execute(_bash_call("echo to-stderr 1>&2; echo to-stdout; exit 3"))

    assert result.status is ToolStatus.SUCCESS
    assert [line for line in result.output.splitlines() if line] == ["to-stderr", "to-stdout", "exit code: 3"]
    assert result.metadata["exit_code"] == 3
    assert type(result.metadata["exit_code"]) is int
    assert result.metadata["truncated"] is False


@pytest.mark.asyncio
async def test_command_runs_in_the_root_folder_even_when_its_path_has_spaces_and_unicode(bash_module, tmp_path) -> None:
    # AC-16 / INV-4: the working directory is the root (a relative write lands there), whatever characters its path holds.
    root = tmp_path / "project root é"
    root.mkdir()
    tool = bash_module.BashTool(str(root))

    result = await tool.execute(_bash_call("printf root-ok > cwd-marker.txt"))

    assert result.status is ToolStatus.SUCCESS
    assert (root / "cwd-marker.txt").read_text(encoding="utf-8") == "root-ok"
    assert tool.root_dir == root.resolve()


@pytest.mark.asyncio
async def test_command_reaches_bash_verbatim_as_one_argument(bash_module, tmp_path) -> None:
    # INV-9 / D-10: bash -c <command> through exec, so quotes, $, and ; arrive untouched and bash-only syntax works.
    command = "printf '%s|' \"it's\" '$HOME' 'a;b' \"${BASH_VERSION:+bash}\""

    result = await bash_module.BashTool(tmp_path).execute(_bash_call(command))

    assert result.output.splitlines()[0] == "it's|$HOME|a;b|bash|"


@pytest.mark.asyncio
async def test_command_reading_stdin_sees_end_of_file_at_once(bash_module, tmp_path, monkeypatch) -> None:
    # EC-11 / D-10: stdin is the null device; an open stdin would hang this call until the (shortened) time limit.
    # pytest's capture already puts the null device on fd 0, so give this process a stdin that never reaches end of
    # file: only the tool's own stdin=DEVNULL can then let the read see end of file.
    monkeypatch.setattr(bash_module, "BASH_TIMEOUT_SECONDS", 10.0)
    read_end, write_end = os.pipe()
    saved_stdin = os.dup(0)
    os.dup2(read_end, 0)
    try:
        result = await bash_module.BashTool(tmp_path).execute(_bash_call("read -r line; echo read-status:$?"))
    finally:
        os.dup2(saved_stdin, 0)
        for fd in (saved_stdin, read_end, write_end):
            os.close(fd)

    assert result.status is ToolStatus.SUCCESS
    assert result.output.splitlines()[0] == "read-status:1"


@pytest.mark.parametrize(
    ("command", "exception_messages"),
    [("echo a\x00b", ("embedded null",)), ("echo " + "a" * 3_000_000, ("argument list too long", "extension is too long"))],
    ids=["nul-byte", "over-the-argument-limit"],
)
@pytest.mark.asyncio
async def test_command_the_os_cannot_start_returns_spawn_failed_naming_only_the_exception_class(bash_module, tmp_path, command, exception_messages) -> None:
    # EC-15 / S017: ValueError and OSError become one classified error result; the exception's own message (POSIX or Windows wording) stays out.
    result = await bash_module.BashTool(tmp_path).execute(_bash_call(command))

    assert result.status is ToolStatus.ERROR
    assert result.metadata["error"] == "spawn_failed"
    assert re.search(r"\b[A-Z]\w*Error\b", result.output)
    assert not [message for message in exception_messages if message in result.output.lower()]


@pytest.mark.asyncio
async def test_invalid_utf8_output_is_decoded_with_replacement_characters(bash_module, tmp_path) -> None:
    # EC-16: binary output never raises; each invalid byte becomes U+FFFD.
    result = await bash_module.BashTool(tmp_path).execute(_bash_call("printf '\\377\\376-tail'"))

    assert result.status is ToolStatus.SUCCESS
    assert result.output.splitlines()[0] == "��-tail"


@pytest.mark.asyncio
async def test_large_output_keeps_the_first_bytes_counts_the_rest_and_memory_stays_bounded(bash_module, tmp_path) -> None:
    # AC-13 / INV-10 / NFR-3: 20 MB pass through a 64 KB pipe; the tool keeps the cap, drains the rest, and reports the real exit code.
    cap = bash_module.BASH_MAX_OUTPUT_BYTES
    omitted = TWENTY_MEGABYTES - cap
    tool = bash_module.BashTool(tmp_path)

    tracemalloc.start()
    try:
        result = await tool.execute(_bash_call(f"head -c {TWENTY_MEGABYTES} /dev/zero | tr '\\0' a; exit 7"))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result.status is ToolStatus.SUCCESS
    assert len(result.output) - len(result.output.lstrip("a")) == cap
    assert re.search(f"{omitted}|{omitted:,}", result.output)
    assert result.output.splitlines()[-1] == "exit code: 7"
    assert result.metadata["exit_code"] == 7
    assert result.metadata["truncated"] is True
    assert peak < PEAK_TRACED_BYTES


@pytest.mark.asyncio
async def test_missing_bash_returns_bash_not_found_with_install_guidance(bash_module, tmp_path, monkeypatch) -> None:
    # AC-17 / FR-11: POSIX with no bash on PATH, or Windows with no git on PATH, is an error result that says how to fix it.
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    # Windows also searches the current folder before PATH; make that folder empty too.
    monkeypatch.chdir(empty_path)
    tool = bash_module.BashTool(tmp_path)

    result = await tool.execute(_bash_call("echo hi > should-not-exist.txt"))

    assert result.status is ToolStatus.ERROR
    assert result.metadata["error"] == "bash_not_found"
    assert ("Git for Windows" if sys.platform == "win32" else "bash") in result.output
    assert not (tmp_path / "should-not-exist.txt").exists()


@posix_host_only
@pytest.mark.parametrize("git_location", ["cmd/git.exe", "bin/git.exe", "mingw64/bin/git.exe"], ids=["from-powershell", "git-bin", "from-git-bash-terminal"])
@pytest.mark.asyncio
async def test_windows_lookup_runs_git_bin_bash_never_the_path_bash(bash_module, tmp_path, monkeypatch, git_location) -> None:
    # AC-22 / INV-15 / EC-13 / EC-31: <G>/bin/bash.exe is found one or two folders above git, never the PATH bash (the WSL launcher).
    which_answers = _stand_in_git_install(tmp_path, git_location)
    tool = _build_as_windows(bash_module, monkeypatch, tmp_path, which_answers)

    result = await tool.execute(_bash_call("echo ran"))

    assert result.status is ToolStatus.SUCCESS
    assert result.output.splitlines()[0] == "git-bin-bash-chosen"


@posix_host_only
@pytest.mark.asyncio
async def test_windows_lookup_stops_after_three_parent_folders_of_git(bash_module, tmp_path, monkeypatch) -> None:
    # FR-11 / D-13: git four folders below <G> is beyond the lookup, which reports bash_not_found rather than falling back to PATH.
    which_answers = _stand_in_git_install(tmp_path, "mingw64/libexec/git-core/git.exe")
    tool = _build_as_windows(bash_module, monkeypatch, tmp_path, which_answers)

    result = await tool.execute(_bash_call("echo ran"))

    assert result.status is ToolStatus.ERROR
    assert result.metadata["error"] == "bash_not_found"
    assert "path-bash-chosen" not in result.output
