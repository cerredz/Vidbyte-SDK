"""Context Protocol Header

Description:
    Docker CLI sandbox provider for real OS-level isolation.
Purpose:
    Boots a container per sandbox and proxies exec/upload/download to the docker
    CLI, with no Python docker dependency.
Architecture:
    - DockerSandboxProvider: Runs a container and provisions a DockerSandbox.
    - DockerSandbox: Implements the Sandbox protocol over docker exec/cp/rm.
Relations:
    Registered in vidbyte.providers.sandbox as Platform.DOCKER.
"""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from collections.abc import Sequence
from pathlib import Path

from vidbyte.lib.dataclasses.sandbox import SandboxConfig, SandboxInfo, SandboxResult, SandboxStatus
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.errors import SandboxExecutionError, SandboxProviderError
from vidbyte.providers.sandbox.base import BaseSandboxProvider, SandboxProvisioner


class DockerSandbox:
    """Container-backed sandbox proxied through the docker CLI."""

    def __init__(self, sandbox_id: str, config: SandboxConfig) -> None:
        # Bind the handle to its container id and config.
        self.sandbox_id = sandbox_id
        self._config = config
        self._created_at = time.time()
        self._status = SandboxStatus.READY
        self._exposed: dict[int, str] = {}

    async def exec(self, command: Sequence[str], *, timeout: float | None = None) -> SandboxResult:
        # Run a command inside the container via docker exec.
        if not tuple(command):
            raise SandboxExecutionError("exec requires a non-empty command.")
        joined = " ".join(command) if command[0] not in {"sh", "bash"} else command[-1]
        argv = ["docker", "exec", "-w", self._config.workdir, self.sandbox_id, "sh", "-c", joined]
        return await _run_cli(argv, timeout if timeout is not None else self._config.timeout_seconds)

    async def upload(self, local_path: str, remote_path: str) -> None:
        # Copy a host path into the container with docker cp.
        await _run_cli(["docker", "cp", local_path, f"{self.sandbox_id}:{remote_path}"], self._config.timeout_seconds)

    async def download(self, remote_path: str, local_path: str) -> None:
        # Copy a container path out to the host with docker cp.
        await _run_cli(["docker", "cp", f"{self.sandbox_id}:{remote_path}", local_path], self._config.timeout_seconds)

    async def write_file(self, remote_path: str, content: str) -> None:
        # Pipe text into a file inside the container via docker exec.
        argv = ["docker", "exec", "-i", self.sandbox_id, "sh", "-c", f"cat > {remote_path}"]
        process = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process.communicate(content.encode("utf-8"))

    async def read_file(self, remote_path: str) -> str:
        # Read a file from inside the container.
        result = await self.exec(["cat", remote_path])
        if result.exit_code != 0:
            raise SandboxExecutionError("read_file failed.", details={"path": remote_path, "stderr": result.stderr})
        return result.stdout

    async def expose_port(self, port: int) -> str:
        # Resolve the published host port for a container port.
        result = await _run_cli(["docker", "port", self.sandbox_id, str(port)], self._config.timeout_seconds)
        mapping = result.stdout.strip().splitlines()[0] if result.stdout.strip() else f"127.0.0.1:{port}"
        url = f"http://{mapping.split('->')[-1].strip()}" if "->" in mapping else f"http://{mapping}"
        self._exposed[port] = url
        return url

    async def snapshot(self) -> str:
        # Commit the container to an image as a snapshot.
        snapshot_id = f"vidbyte-snap-{uuid.uuid4().hex[:12]}"
        await _run_cli(["docker", "commit", self.sandbox_id, snapshot_id], self._config.timeout_seconds)
        return snapshot_id

    async def info(self) -> SandboxInfo:
        # Return a read-only snapshot of this sandbox's current state.
        return SandboxInfo(sandbox_id=self.sandbox_id, platform=Platform.DOCKER, status=self._status, workdir=self._config.workdir, created_at=self._created_at, exposed_urls=dict(self._exposed), labels=dict(self._config.labels))

    async def destroy(self) -> None:
        # Force-remove the container; idempotent (ignores missing container).
        if self._status is SandboxStatus.DESTROYED:
            return
        await _run_cli(["docker", "rm", "-f", self.sandbox_id], self._config.timeout_seconds)
        self._status = SandboxStatus.DESTROYED


class DockerSandboxProvider(BaseSandboxProvider):
    """Boots containers through the docker CLI and provisions them."""

    platform = Platform.DOCKER

    async def create(self, config: SandboxConfig) -> DockerSandbox:
        # Verify docker, run a detached container, then provision it.
        self._require_docker()
        container_id = await self._run_container(config)
        sandbox = DockerSandbox(container_id, config)
        await SandboxProvisioner(sandbox, config).provision()
        return sandbox

    def _require_docker(self) -> None:
        # Raise a clear, actionable error when the docker CLI is unavailable.
        if shutil.which("docker") is None:
            raise SandboxProviderError("Docker CLI not found. Install Docker to use Platform.DOCKER.", details={"platform": "docker"})

    async def _run_container(self, config: SandboxConfig) -> str:
        # Start a detached container with resource, env, and network flags.
        argv = ["docker", "run", "-d", "-w", config.workdir]
        argv += ["--entrypoint", "sh"] if not config.expose_ports else []
        for key, value in {**dict(config.env), **dict(config.secrets)}.items():
            argv += ["-e", f"{key}={value}"]
        if config.cpu is not None:
            argv += ["--cpus", str(config.cpu)]
        if config.mem_mb is not None:
            argv += ["--memory", f"{config.mem_mb}m"]
        if not config.network_allow:
            argv += ["--network", "none"]
        for port in config.expose_ports:
            argv += ["-p", f"{port}"]
        argv += [config.image, "-c", "mkdir -p " + config.workdir + " && tail -f /dev/null"]
        result = await _run_cli(argv, config.timeout_seconds)
        if result.exit_code != 0:
            raise SandboxProviderError("Failed to start docker container.", details={"image": config.image, "stderr": result.stderr[:500]})
        return result.stdout.strip()


async def _run_cli(argv: list[str], timeout: float) -> SandboxResult:
    # Run a docker CLI command with a timeout and capture its output.
    process = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return SandboxResult(exit_code=124, stdout="", stderr="", timed_out=True)
    return SandboxResult(exit_code=process.returncode or 0, stdout=stdout.decode("utf-8", "replace"), stderr=stderr.decode("utf-8", "replace"))


__all__ = [
    "DockerSandbox",
    "DockerSandboxProvider",
]
