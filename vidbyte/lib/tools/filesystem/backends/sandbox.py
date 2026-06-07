"""Context Protocol Header

Description:
    Filesystem backend that operates inside a sandbox (Architecture A).
Purpose:
    Lets existing platform-neutral filesystem tools read/write/list against a
    sandbox by mapping the sync backend interface onto async sandbox calls.
Architecture:
    - SandboxFileSystemBackend: BaseFileSystemBackend over a Sandbox handle.
Relations:
    Implements vidbyte.lib.tools.filesystem.backends.base.BaseFileSystemBackend
    using vidbyte.lib.dataclasses.sandbox.Sandbox.
"""

from __future__ import annotations

import asyncio
import difflib
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

from vidbyte.lib.dataclasses import FileStat
from vidbyte.lib.dataclasses.sandbox import Sandbox
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem.backends.base import BaseFileSystemBackend

T = TypeVar("T")


class SandboxFileSystemBackend(BaseFileSystemBackend):
    """Bridges the sync filesystem backend interface onto an async sandbox."""

    def __init__(self, sandbox: Sandbox, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
        # Bind to a sandbox and an event loop used to drive its coroutines.
        self._sandbox = sandbox
        self._loop = loop

    def read_text(self, path: Path, *, encoding: str) -> str:
        # Read text from a path inside the sandbox.
        return self._await(self._sandbox.read_file(self._as_posix(path)))

    def read_binary(self, path: Path) -> bytes:
        # Read text and encode it; the sandbox protocol exposes text transfer.
        return self.read_text(path, encoding="utf-8").encode("utf-8")

    def write_text(self, path: Path, content: str, *, encoding: str, create_parents: bool) -> None:
        # Write text to a path inside the sandbox, creating parents as needed.
        if create_parents:
            self._exec_checked(["mkdir", "-p", self._as_posix(path.parent)])
        self._await(self._sandbox.write_file(self._as_posix(path), content))

    def append_text(self, path: Path, content: str, *, encoding: str, create_parents: bool) -> None:
        # Append text to a path inside the sandbox.
        existing = self.read_text(path, encoding=encoding) if self._exists(path) else ""
        self.write_text(path, existing + content, encoding=encoding, create_parents=create_parents)

    def list_dir(self, path: Path) -> tuple[str, ...]:
        # List one directory inside the sandbox.
        result = self._exec_checked(["ls", "-1A", self._as_posix(path)])
        return tuple(line for line in result.splitlines() if line)

    def make_dir(self, path: Path, *, parents: bool, exist_ok: bool) -> None:
        # Create a directory inside the sandbox.
        flag = ["-p"] if parents or exist_ok else []
        self._exec_checked(["mkdir", *flag, self._as_posix(path)])

    def delete(self, path: Path, *, recursive: bool) -> None:
        # Delete a file or directory inside the sandbox.
        flag = ["-rf"] if recursive else ["-f"]
        self._exec_checked(["rm", *flag, self._as_posix(path)])

    def move(self, source: Path, destination: Path) -> None:
        # Move or rename a path inside the sandbox.
        self._exec_checked(["mv", self._as_posix(source), self._as_posix(destination)])

    def copy(self, source: Path, destination: Path) -> None:
        # Copy a path inside the sandbox.
        self._exec_checked(["cp", "-r", self._as_posix(source), self._as_posix(destination)])

    def stat(self, path: Path) -> FileStat:
        # Return portable metadata for a path inside the sandbox.
        posix = self._as_posix(path)
        exists = self._exists(path)
        is_dir = exists and self._exec(["sh", "-c", f"test -d {posix}"]).exit_code == 0
        size = int((self._exec_checked(["sh", "-c", f"wc -c < {posix}"]).strip() or 0)) if exists and not is_dir else None
        return FileStat(path=posix, exists=exists, is_file=exists and not is_dir, is_dir=is_dir, size=size, modified_time=None)

    def find(self, root: Path, pattern: str) -> tuple[str, ...]:
        # Find matching paths under a root inside the sandbox.
        result = self._exec_checked(["sh", "-c", f"find {self._as_posix(root)} -name '{pattern}'"])
        return tuple(line for line in result.splitlines() if line)

    def diff_text(self, left: Path, right_content: str, *, encoding: str, label: str) -> str:
        # Return a unified diff between sandbox text and provided content.
        current = self.read_text(left, encoding=encoding) if self._exists(left) else ""
        diff = difflib.unified_diff(current.splitlines(keepends=True), right_content.splitlines(keepends=True), fromfile=label, tofile=label)
        return "".join(diff)

    def zip_path(self, source: Path, destination: Path) -> None:
        # Create a zip archive from a sandbox source path.
        self._exec_checked(["sh", "-c", f"cd {self._as_posix(source.parent)} && zip -r {self._as_posix(destination)} {source.name}"])

    def unzip_path(self, source: Path, destination: Path) -> tuple[str, ...]:
        # Extract a zip archive into a sandbox destination path.
        self._exec_checked(["sh", "-c", f"mkdir -p {self._as_posix(destination)} && unzip -o {self._as_posix(source)} -d {self._as_posix(destination)}"])
        return self.list_dir(destination)

    def _exists(self, path: Path) -> bool:
        # Report whether a path exists inside the sandbox.
        return self._exec(["sh", "-c", f"test -e {self._as_posix(path)}"]).exit_code == 0

    def _exec(self, command: list[str]) -> Any:
        # Run a command in the sandbox and return the raw result.
        return self._await(self._sandbox.exec(command))

    def _exec_checked(self, command: list[str]) -> str:
        # Run a command and raise ToolExecutionError on a non-zero exit.
        result = self._exec(command)
        if result.exit_code != 0:
            raise ToolExecutionError("Sandbox filesystem command failed.", details={"command": command, "stderr": result.stderr})
        return result.stdout

    def _await(self, coro: Coroutine[Any, Any, T]) -> T:
        # Drive a sandbox coroutine to completion on the bound or a temporary loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise ToolExecutionError("SandboxFileSystemBackend cannot be used from inside a running event loop; use the async sandbox API instead.")

    def _as_posix(self, path: Path) -> str:
        # Render a path as a POSIX string for in-box shell commands.
        return path.as_posix()


__all__ = [
    "SandboxFileSystemBackend",
]
