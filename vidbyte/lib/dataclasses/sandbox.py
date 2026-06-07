"""Context Protocol Header

Description:
    Defines transport and environment contracts for isolated execution backends.
Purpose:
    Lets risky tools and full agent loops depend on an injectable sandbox
    interface without binding the SDK to Docker, E2B, Modal, or any provider.
Architecture:
    - SandboxRequest/SandboxResult: One-shot command payload and captured output.
    - SandboxTransport: Protocol for stateless isolated execution providers.
    - SandboxConfig: Internal facade->provider transport for environment settings.
    - SandboxStatus/SandboxInfo: Lifecycle status and read-only snapshot.
    - Sandbox: Protocol for a live, stateful isolated environment handle.
    - SandboxProvider: Protocol implemented by concrete sandbox backends.
    - AgentManifest: Serializable agent config shipped into a box (Architecture B).
Relations:
    Re-exported by vidbyte.tools.security.sandbox and consumed by
    vidbyte.providers.sandbox, vidbyte.sandbox, and vidbyte.lib.runners.sandbox.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from vidbyte.lib.enums.platform import Platform


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
    """Protocol for async stateless isolated execution providers."""

    async def run(self, request: SandboxRequest) -> SandboxResult:
        """Execute a request in isolation and return captured output."""


class SandboxStatus(str, Enum):
    """Lifecycle state of a live sandbox environment."""

    CREATING = "creating"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    DESTROYED = "destroyed"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """Internal transport carrying resolved environment settings to a provider."""

    platform: Platform = Platform.LOCAL
    image: str = "python:3.12-slim"
    repo: str | None = None
    branch: str | None = None
    commit: str | None = None
    seed_local: str | None = None
    workdir: str = "/workspace"
    setup: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    secrets: Mapping[str, str] = field(default_factory=dict)
    cpu: float | None = None
    mem_mb: int | None = None
    disk_mb: int | None = None
    timeout_seconds: float = 60.0
    network_allow: tuple[str, ...] = ()
    expose_ports: tuple[int, ...] = ()
    ttl_seconds: float | None = None
    labels: Mapping[str, str] = field(default_factory=dict)

    def redacted(self) -> Mapping[str, Any]:
        """Return a log-safe view of the config with secret values masked."""
        return {"platform": self.platform.value, "image": self.image, "repo": self.repo, "branch": self.branch, "commit": self.commit, "workdir": self.workdir, "setup": self.setup, "secret_keys": tuple(self.secrets.keys()), "expose_ports": self.expose_ports}


@dataclass(frozen=True, slots=True)
class SandboxInfo:
    """Read-only snapshot of a sandbox for list/view operations."""

    sandbox_id: str
    platform: Platform
    status: SandboxStatus
    workdir: str
    created_at: float
    exposed_urls: Mapping[int, str] = field(default_factory=dict)
    labels: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class Sandbox(Protocol):
    """Protocol for a live, stateful isolated environment handle."""

    sandbox_id: str

    async def exec(self, command: Sequence[str], *, timeout: float | None = None) -> SandboxResult:
        """Run a command in the box and return captured output."""

    async def upload(self, local_path: str, remote_path: str) -> None:
        """Copy a host file or directory into the box."""

    async def download(self, remote_path: str, local_path: str) -> None:
        """Copy a file out of the box to the host."""

    async def write_file(self, remote_path: str, content: str) -> None:
        """Write text content to a path inside the box."""

    async def read_file(self, remote_path: str) -> str:
        """Read text content from a path inside the box."""

    async def expose_port(self, port: int) -> str:
        """Expose a port and return a reachable URL."""

    async def snapshot(self) -> str:
        """Capture the box state and return a snapshot identifier."""

    async def info(self) -> SandboxInfo:
        """Return a read-only snapshot of this sandbox."""

    async def destroy(self) -> None:
        """Tear down the box; safe to call more than once."""


@runtime_checkable
class SandboxProvider(Protocol):
    """Protocol implemented by concrete sandbox backends."""

    platform: Platform

    async def create(self, config: SandboxConfig) -> Sandbox:
        """Boot and provision an isolated environment from config."""


@dataclass(frozen=True, slots=True)
class AgentManifest:
    """Serializable agent configuration shipped into a box (Architecture B)."""

    name: str
    system_prompt: str
    runtime: str
    model: str | None = None
    provider: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    tools: tuple[str, ...] = ()
    middleware: tuple[Mapping[str, Any], ...] = ()
    context_window: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict for shipping into a sandbox."""
        return {"name": self.name, "system_prompt": self.system_prompt, "runtime": self.runtime, "model": self.model, "provider": self.provider, "params": dict(self.params), "tools": list(self.tools), "middleware": [dict(item) for item in self.middleware], "context_window": dict(self.context_window) if self.context_window else None}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentManifest":
        """Rebuild a manifest from its JSON dict form."""
        return cls(name=data["name"], system_prompt=data.get("system_prompt", ""), runtime=data.get("runtime", "linear"), model=data.get("model"), provider=data.get("provider"), params=dict(data.get("params", {})), tools=tuple(data.get("tools", ())), middleware=tuple(dict(item) for item in data.get("middleware", ())), context_window=dict(data["context_window"]) if data.get("context_window") else None)


__all__ = [
    "AgentManifest",
    "Sandbox",
    "SandboxConfig",
    "SandboxInfo",
    "SandboxProvider",
    "SandboxRequest",
    "SandboxResult",
    "SandboxStatus",
    "SandboxTransport",
]
