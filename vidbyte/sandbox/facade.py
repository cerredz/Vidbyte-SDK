"""Context Protocol Header

Description:
    Thin, clean user-facing facade over the sandbox provider and runner layers.
Purpose:
    Gives developers an ergonomic API: Sandbox.create(...), Sandbox.put(agent,
    task), sandbox.exec(cmd), plus delegation to a default multi-sandbox manager.
    Users pass configuration as direct params; no spec object is required.
Architecture:
    - Sandbox: Wraps a provider handle with ergonomic, param-direct methods.
Relations:
    Uses vidbyte.sandbox.manager.SandboxManager, vidbyte.providers.sandbox, and
    vidbyte.lib.runners.sandbox.SandboxAgentRunner.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vidbyte.lib.dataclasses.sandbox import Sandbox as SandboxHandle, SandboxConfig, SandboxInfo, SandboxResult
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.platform import Platform
from vidbyte.sandbox.manager import SandboxManager

_DEFAULT_MANAGER = SandboxManager()


class Sandbox:
    """Ergonomic handle for one isolated environment, with multi-box helpers."""

    def __init__(self, handle: SandboxHandle, manager: SandboxManager) -> None:
        # Wrap a provider handle and the manager that tracks it.
        self._handle = handle
        self._manager = manager
        self.sandbox_id = handle.sandbox_id

    @classmethod
    async def create(cls, *, platform: Platform | str = Platform.LOCAL, image: str = "python:3.12-slim", repo: str | None = None, branch: str | None = None, commit: str | None = None, seed_local: str | None = None, workdir: str = "/workspace", setup: Sequence[str] = (), env: Mapping[str, str] | None = None, secrets: Mapping[str, str] | None = None, cpu: float | None = None, mem_mb: int | None = None, timeout_s: float = 60.0, network_allow: Sequence[str] = (), expose_ports: Sequence[int] = (), ttl_seconds: float | None = None, labels: Mapping[str, str] | None = None, manager: SandboxManager | None = None) -> "Sandbox":
        # Build a config from direct params, create + provision a box, and register it.
        config = cls._build_config(platform=platform, image=image, repo=repo, branch=branch, commit=commit, seed_local=seed_local, workdir=workdir, setup=setup, env=env, secrets=secrets, cpu=cpu, mem_mb=mem_mb, timeout_s=timeout_s, network_allow=network_allow, expose_ports=expose_ports, ttl_seconds=ttl_seconds, labels=labels)
        active = manager or _DEFAULT_MANAGER
        handle = await active.create(config)
        return cls(handle, active)

    @classmethod
    async def put(cls, agent: object, task: str, *, platform: Platform | str = Platform.LOCAL, dry_run: bool = False, python_executable: str = "python", **params: object) -> tuple[AgentResult, "Sandbox"]:
        # Convenience: create a box and run the agent's full loop inside it.
        sandbox = await cls.create(platform=platform, **params)  # type: ignore[arg-type]
        result = await sandbox.run_agent(agent, task, dry_run=dry_run, python_executable=python_executable)
        return result, sandbox

    async def exec(self, command: str | Sequence[str], *, timeout: float | None = None) -> SandboxResult:
        # Run a shell string or argv command inside the box.
        argv = ["sh", "-c", command] if isinstance(command, str) else list(command)
        return await self._handle.exec(argv, timeout=timeout)

    async def upload(self, local_path: str, remote_path: str) -> None:
        # Copy a host file or directory into the box.
        await self._handle.upload(local_path, remote_path)

    async def download(self, remote_path: str, local_path: str) -> None:
        # Copy a file out of the box to the host.
        await self._handle.download(remote_path, local_path)

    async def write_file(self, remote_path: str, content: str) -> None:
        # Write text content to a path inside the box.
        await self._handle.write_file(remote_path, content)

    async def read_file(self, remote_path: str) -> str:
        # Read text content from a path inside the box.
        return await self._handle.read_file(remote_path)

    async def expose_port(self, port: int) -> str:
        # Expose a port and return a reachable URL.
        return await self._handle.expose_port(port)

    async def snapshot(self) -> str:
        # Capture the box state and return a snapshot identifier.
        return await self._handle.snapshot()

    async def info(self) -> SandboxInfo:
        # Return a live read-only snapshot of this sandbox.
        return await self._handle.info()

    async def run_agent(self, agent: object, task: str, *, dry_run: bool = False, python_executable: str = "python") -> AgentResult:
        # Run an agent's full loop inside THIS box (Architecture B).
        from vidbyte.lib.runners.sandbox import SandboxAgentRunner

        return await SandboxAgentRunner(self._handle, python_executable=python_executable).run(agent, task, dry_run=dry_run)

    async def destroy(self) -> None:
        # Tear down this box and deregister it from the manager.
        try:
            await self._manager.destroy(self.sandbox_id)
        except Exception:
            await self._handle.destroy()

    @classmethod
    def list(cls, *, manager: SandboxManager | None = None) -> tuple[SandboxInfo, ...]:
        # List info for every sandbox tracked by the default or given manager.
        return (manager or _DEFAULT_MANAGER).list()

    @classmethod
    async def get(cls, sandbox_id: str, *, manager: SandboxManager | None = None) -> "Sandbox":
        # Fetch a tracked sandbox by id and wrap it in a facade.
        active = manager or _DEFAULT_MANAGER
        handle = await active.get(sandbox_id)
        return cls(handle, active)

    @classmethod
    async def destroy_all(cls, *, manager: SandboxManager | None = None) -> None:
        # Destroy every sandbox tracked by the default or given manager.
        await (manager or _DEFAULT_MANAGER).destroy_all()

    @staticmethod
    def _build_config(*, platform: Platform | str, image: str, repo: str | None, branch: str | None, commit: str | None, seed_local: str | None, workdir: str, setup: Sequence[str], env: Mapping[str, str] | None, secrets: Mapping[str, str] | None, cpu: float | None, mem_mb: int | None, timeout_s: float, network_allow: Sequence[str], expose_ports: Sequence[int], ttl_seconds: float | None, labels: Mapping[str, str] | None) -> SandboxConfig:
        # Coerce direct params into the internal frozen SandboxConfig.
        resolved = platform if isinstance(platform, Platform) else Platform(str(platform).lower())
        return SandboxConfig(platform=resolved, image=image, repo=repo, branch=branch, commit=commit, seed_local=seed_local, workdir=workdir, setup=tuple(setup), env=dict(env or {}), secrets=dict(secrets or {}), cpu=cpu, mem_mb=mem_mb, timeout_seconds=timeout_s, network_allow=tuple(network_allow), expose_ports=tuple(expose_ports), ttl_seconds=ttl_seconds, labels=dict(labels or {}))


__all__ = [
    "Sandbox",
]
