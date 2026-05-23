"""Context Protocol Header

Description:
    Defines transport contracts for future isolated execution backends.
Purpose:
    Lets risky tools depend on an injectable sandbox interface without binding
    the SDK to Docker, WASM, E2B, or a remote provider.
Architecture:
    - SandboxRequest: Command/code payload plus limits for an isolated run.
    - SandboxResult: Captured status, stdout, stderr, and timeout state.
    - SandboxTransport: Protocol implemented by concrete sandbox backends.
Relations:
    Re-exported by vidbyte.tools.security.sandbox.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SandboxRequest:
    """Payload sent to an isolated execution backend."""

    command: Sequence[str]
    stdin: str = ""
    timeout_seconds: float = 30.0
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """Result captured from an isolated execution backend."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class SandboxTransport(Protocol):
    """Protocol for async isolated execution providers."""

    async def run(self, request: SandboxRequest) -> SandboxResult:
        """Execute a request in isolation and return captured output."""
