"""FILE: vidbyte/lib/cli.py

PURPOSE: Provides one safe asynchronous boundary for allowlisted native CLI calls.
ROLE IN CODEBASE: GitHub integrations pass fixed command arguments and credentials to CliRunner.
ARCHITECTURE NOTE: The runner owns process lifecycle, secret environment handling, timeout, and output limits.
COMMON MODIFICATION PATTERNS: Add provider planning outside this file; keep this boundary independent of provider routes.
KNOWN EDGE CASES: Missing executables fall back at the provider layer, while attempted failures do not.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from typing import Any

from vidbyte.lib.constants.integrations import (
    SOURCES_CLI_ENV_VAR,
    SOURCES_CLI_EXECUTABLE,
    SOURCES_CLI_MAX_OUTPUT_BYTES,
    SOURCES_CLI_READ_CHUNK_BYTES,
    SOURCES_CLI_READ_OVERFLOW_BYTES,
    SOURCES_CLI_TIMEOUT_MAX_SECONDS,
    SOURCES_CLI_TIMEOUT_MIN_SECONDS,
    SOURCES_MAX_CONTROL_CODE,
)


class CliError(RuntimeError):
    """Base class for safe native CLI boundary failures."""


class CliUnavailableError(CliError):
    """Raised when the configured executable is not installed or discoverable."""


class CliTimeoutError(CliError):
    """Raised when a native command exceeds its configured timeout."""


class CliOutputLimitError(CliError):
    """Raised when stdout or stderr exceeds the configured byte ceiling."""


class CliCommandError(CliError):
    """Raised when an attempted command exits unsuccessfully with a safe category."""

    def __init__(self, category: str) -> None:
        """Store only an SDK-authored failure category, never native output."""
        self.category = category
        super().__init__(f"Native CLI command failed with category {category}.")


@dataclass(frozen=True, slots=True)
class CliRequest:
    """Validated native invocation data with the secret separated from argv."""

    executable: str
    args: tuple[str, ...]
    api_key: str
    timeout_seconds: float
    max_output_bytes: int = SOURCES_CLI_MAX_OUTPUT_BYTES

    def __post_init__(self) -> None:
        """Reject unsafe invocation values before process creation."""
        if self.executable != SOURCES_CLI_EXECUTABLE:
            raise ValueError("CliRequest.executable must be the approved GitHub CLI executable.")
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("CliRequest.api_key must be a nonempty string.")
        if not self.args or not all(isinstance(arg, str) and arg for arg in self.args):
            raise ValueError("CliRequest.args must contain nonempty strings.")
        if any(any(ord(char) <= SOURCES_MAX_CONTROL_CODE for char in arg) for arg in self.args):
            raise ValueError("CliRequest.args must not contain control characters.")
        if any(self.api_key in arg for arg in self.args):
            raise ValueError("CliRequest must not place the API key in command arguments.")
        self.validate_timeout(self.timeout_seconds)
        self.validate_output_limit(self.max_output_bytes)

    @staticmethod
    def validate_timeout(timeout_seconds: float) -> None:
        """Validate one native-process timeout against the shared CLI bounds."""
        if not isinstance(timeout_seconds, (int, float)) or not SOURCES_CLI_TIMEOUT_MIN_SECONDS <= float(timeout_seconds) <= SOURCES_CLI_TIMEOUT_MAX_SECONDS:
            raise ValueError("CliRequest.timeout_seconds is outside the approved range.")

    @staticmethod
    def validate_output_limit(max_output_bytes: int) -> None:
        """Validate one positive native output limit."""
        if type(max_output_bytes) is not int or max_output_bytes <= 0:
            raise ValueError("CliRequest.max_output_bytes must be a positive integer.")


@dataclass(frozen=True, slots=True)
class CliResult:
    """Bounded native output returned after a successful process lifecycle."""

    stdout: str
    stderr: str
    returncode: int


class CliRunner:
    """Runs the approved native CLI without a shell and without leaking secrets."""

    def __init__(self, *, executable: str = SOURCES_CLI_EXECUTABLE) -> None:
        """Bind the one approved executable for this runner instance."""
        if executable != SOURCES_CLI_EXECUTABLE:
            raise ValueError("CliRunner only supports the approved GitHub CLI executable.")
        self._executable = executable

    # @intent process-boundary
    async def run(self, request: CliRequest) -> CliResult:
        """Run one request with bounded streams, timeout, and a sanitized child environment."""
        if request.executable != self._executable:
            raise ValueError("CliRequest executable does not match this runner.")
        if shutil.which(self._executable) is None:
            raise CliUnavailableError("The approved native CLI is unavailable.")
        child_environment = os.environ.copy()
        child_environment.pop(SOURCES_CLI_ENV_VAR, None)
        child_environment[SOURCES_CLI_ENV_VAR] = request.api_key
        try:
            process = await asyncio.create_subprocess_exec(
                request.executable,
                *request.args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=child_environment,
            )
        except OSError as exc:
            raise CliUnavailableError("The approved native CLI could not be started.") from exc
        stdout_task = asyncio.create_task(self._read_bounded(process.stdout, request.max_output_bytes))
        stderr_task = asyncio.create_task(self._read_bounded(process.stderr, request.max_output_bytes))
        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task),
                timeout=float(request.timeout_seconds),
            )
        except TimeoutError as exc:
            await self._stop_process(process, stdout_task, stderr_task)
            raise CliTimeoutError("The native CLI command exceeded its timeout.") from exc
        except CliOutputLimitError:
            await self._stop_process(process, stdout_task, stderr_task)
            raise
        except BaseException:
            await self._stop_process(process, stdout_task, stderr_task)
            raise
        returncode = await process.wait()
        if returncode != 0:
            raise CliCommandError(self._classify_stderr(stderr))
        return CliResult(stdout=stdout, stderr=stderr, returncode=returncode)

    async def _read_bounded(self, stream: Any, max_bytes: int) -> str:
        """Read one subprocess stream incrementally and reject output over the ceiling."""
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await stream.read(min(SOURCES_CLI_READ_CHUNK_BYTES, max_bytes + SOURCES_CLI_READ_OVERFLOW_BYTES - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise CliOutputLimitError("The native CLI response exceeded its output limit.")
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")

    async def _stop_process(self, process: Any, *tasks: asyncio.Task[Any]) -> None:
        """Stop a failed child and drain its reader tasks before returning control."""
        for task in tasks:
            if not task.done():
                task.cancel()
        if getattr(process, "returncode", None) is None:
            process.kill()
        await process.wait()
        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def _classify_stderr(stderr: str) -> str:
        """Reduce native diagnostics to a safe provider access category."""
        lowered = stderr.lower()
        if "rate limit" in lowered or "too many requests" in lowered:
            return "RATE_LIMITED"
        if "authentication" in lowered or "bad credentials" in lowered or "login" in lowered:
            return "AUTH_REQUIRED"
        if "not found" in lowered or "could not resolve" in lowered:
            return "RESOURCE_UNAVAILABLE"
        if "forbidden" in lowered or "permission" in lowered:
            return "INSUFFICIENT_SCOPE"
        return "TRANSPORT_FAILED"


__all__ = [
    "CliCommandError",
    "CliError",
    "CliOutputLimitError",
    "CliRequest",
    "CliResult",
    "CliRunner",
    "CliTimeoutError",
    "CliUnavailableError",
]
