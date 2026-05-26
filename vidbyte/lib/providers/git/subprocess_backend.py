"""Context Protocol Header

Description:
    Implements BaseGitBackend using asyncio subprocess execution.
Purpose:
    Provides the default git command runner for all built-in git tools.
Architecture:
    - SubprocessGitBackend: Spawns `git -C <repo_path> <args>` with timeout.
Relations:
    Related to vidbyte.lib.providers.git.base and vidbyte.tools.builtins.git.
"""

from __future__ import annotations

import asyncio

from vidbyte.lib.providers.git.base import BaseGitBackend


class SubprocessGitBackend(BaseGitBackend):
    """Runs git commands via asyncio subprocess with configurable timeout."""

    async def run(self, repo_path: str, args: list[str], timeout_ms: int = 30000) -> tuple[int, str, str]:
        """Execute `git -C <repo_path> <args>` and return (exit_code, stdout, stderr)."""
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                repo_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_ms / 1000,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return (-1, "", "Command timed out")

            exit_code = process.returncode if process.returncode is not None else -1
            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            return (exit_code, stdout, stderr)
        except FileNotFoundError:
            return (-1, "", "git executable not found")
        except Exception as exc:
            return (-1, "", str(exc))
