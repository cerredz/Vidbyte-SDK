"""Context Protocol Header

Description:
    Abstract base contract and result type for sandbox execution backends.
Purpose:
    Defines the interface that all sandbox backends must implement and the
    normalized result shape returned to tool callers.
Architecture:
    - SandboxResult: Immutable dataclass capturing stdout, stderr, exit code,
      truncation flag, and optional metadata.
    - BaseSandboxBackend: ABC with abstract execute, write_file, read_file,
      list_dir and an optional cleanup hook.
Relations:
    Provides the contract for vidbyte.lib.providers.sandbox.local_backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class SandboxResult:
    """Normalized result from a sandboxed command execution."""

    stdout: str
    stderr: str
    exit_code: int
    truncated: bool = False
    metadata: dict = field(default_factory=dict)


class BaseSandboxBackend(ABC):
    """Abstract interface for sandboxed command and filesystem operations."""

    @abstractmethod
    async def execute(
        self,
        command: str,
        timeout_ms: int,
        workdir: str,
        env: dict[str, str],
    ) -> SandboxResult:
        """Run *command* inside the sandbox and return a normalized result."""

    @abstractmethod
    async def write_file(self, path: str, content: str | bytes) -> None:
        """Create or overwrite a file at *path* with *content*."""

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Return the text contents of the file at *path*."""

    @abstractmethod
    async def list_dir(self, path: str) -> list[str]:
        """Return a sorted list of entry names inside directory *path*."""

    async def cleanup(self) -> None:
        """Optional resource cleanup; default is a no-op."""
