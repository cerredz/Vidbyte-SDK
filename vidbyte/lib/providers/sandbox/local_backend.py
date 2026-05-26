"""Context Protocol Header

Description:
    Local-machine sandbox backend using asyncio subprocess and pathlib.
Purpose:
    Provides the default sandbox implementation for shell tool execution and
    local filesystem operations without external dependencies.
Architecture:
    - Wraps asyncio.create_subprocess_shell for command execution.
    - Uses pathlib.Path for file and directory I/O.
    - Enforces a blocked-command allowlist to prevent interactive / privileged
      commands from running.
Relations:
    Implements vidbyte.lib.providers.sandbox.base.BaseSandboxBackend.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from vidbyte.lib.providers.sandbox.base import BaseSandboxBackend, SandboxResult

BLOCKED_COMMANDS: set[str] = {
    "vim",
    "vi",
    "nano",
    "less",
    "more",
    "top",
    "htop",
    "sudo",
    "su",
    "passwd",
}

MAX_OUTPUT_CHARS: int = 30000


class LocalSandboxBackend(BaseSandboxBackend):
    """Runs commands locally via asyncio.create_subprocess_shell."""

    async def execute(
        self,
        command: str,
        timeout_ms: int,
        workdir: str,
        env: dict[str, str],
    ) -> SandboxResult:
        """Execute *command* in a local subprocess and return a result."""
        cmd_parts = command.strip().split()
        if cmd_parts and cmd_parts[0] in BLOCKED_COMMANDS:
            return SandboxResult(
                stdout="",
                stderr=f"Blocked command: {cmd_parts[0]}",
                exit_code=1,
                truncated=False,
            )

        merged_env = dict(os.environ)
        merged_env.update(env or {})

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                env=merged_env,
            )
        except Exception as exc:
            return SandboxResult(
                stdout="",
                stderr=f"Failed to start process: {exc}",
                exit_code=-1,
                truncated=False,
            )

        truncated = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=5.0,
                )
            except (asyncio.TimeoutError, Exception):
                try:
                    stdout_bytes, stderr_bytes = process.stdout and await process.stdout.read() or b"", process.stderr and await process.stderr.read() or b""
                except Exception:
                    stdout_bytes, stderr_bytes = b"", b""
            truncated = True

        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        combined_len = len(stdout) + len(stderr)
        if combined_len > MAX_OUTPUT_CHARS:
            ratio = MAX_OUTPUT_CHARS / combined_len
            stdout = stdout[: max(1, int(len(stdout) * ratio))]
            stderr = stderr[: max(0, int(len(stderr) * ratio))]
            truncated = True

        exit_code = process.returncode if process.returncode is not None else -1

        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            truncated=truncated,
        )

    async def write_file(self, path: str, content: str | bytes) -> None:
        """Create or overwrite a file. Creates parent directories as needed."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            p.write_text(content)
        else:
            p.write_bytes(content)

    async def read_file(self, path: str) -> str:
        """Return the text contents of the file at *path*."""
        return Path(path).read_text()

    async def list_dir(self, path: str) -> list[str]:
        """Return sorted entry names inside the directory at *path*."""
        return sorted(entry.name for entry in Path(path).iterdir())
