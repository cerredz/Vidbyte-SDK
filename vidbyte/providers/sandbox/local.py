"""Context Protocol Header

Description:
    Local subprocess sandbox provider (reference and test backend).
Purpose:
    Runs commands in a dedicated temp working directory with zero dependencies.
    NOT a security boundary: it isolates the working directory only, not the
    process, network, or host. Use Docker/E2B/microVM backends for real isolation.
Architecture:
    - LocalSandboxProvider: Creates and provisions LocalSandbox instances.
    - LocalSandbox: Implements the Sandbox protocol over asyncio subprocesses.
Relations:
    Registered in vidbyte.providers.sandbox as Platform.LOCAL.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import time
import uuid
from collections.abc import Sequence
from pathlib import Path

from vidbyte.lib.dataclasses.sandbox import SandboxConfig, SandboxInfo, SandboxResult, SandboxStatus
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.errors import SandboxExecutionError
from vidbyte.providers.sandbox.base import BaseSandboxProvider, SandboxProvisioner


class LocalSandbox:
    """Subprocess-backed sandbox confined to a temp working directory."""

    def __init__(self, sandbox_id: str, root: Path, config: SandboxConfig, env: dict[str, str]) -> None:
        # Bind the handle to its working root, config, and resolved environment.
        self.sandbox_id = sandbox_id
        self._root = root
        self._config = config
        self._env = env
        self._created_at = time.time()
        self._status = SandboxStatus.READY
        self._exposed: dict[int, str] = {}

    async def exec(self, command: Sequence[str], *, timeout: float | None = None) -> SandboxResult:
        # Spawn a subprocess in the working root and capture its output.
        if not tuple(command):
            raise SandboxExecutionError("exec requires a non-empty command.")
        if self._status is SandboxStatus.DESTROYED:
            raise SandboxExecutionError("Sandbox has been destroyed.", details={"sandbox_id": self.sandbox_id})
        return await self._spawn(tuple(command), timeout if timeout is not None else self._config.timeout_seconds)

    async def _spawn(self, command: tuple[str, ...], timeout: float) -> SandboxResult:
        # Run the command with a timeout, killing and flagging it if it overruns.
        process = await asyncio.create_subprocess_exec(*command, cwd=str(self._root), env=self._env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return SandboxResult(exit_code=124, stdout="", stderr="", timed_out=True)
        return SandboxResult(exit_code=process.returncode or 0, stdout=stdout.decode("utf-8", "replace"), stderr=stderr.decode("utf-8", "replace"))

    async def upload(self, local_path: str, remote_path: str) -> None:
        # Copy a host file or directory into the confined working root.
        target = self._resolve(remote_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        source = Path(local_path)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
            return
        shutil.copy2(source, target)

    async def download(self, remote_path: str, local_path: str) -> None:
        # Copy a file out of the working root to a host path.
        source = self._resolve(remote_path)
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    async def write_file(self, remote_path: str, content: str) -> None:
        # Write text to a path confined within the working root.
        target = self._resolve(remote_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    async def read_file(self, remote_path: str) -> str:
        # Read text from a path confined within the working root.
        return self._resolve(remote_path).read_text(encoding="utf-8")

    async def expose_port(self, port: int) -> str:
        # Return a localhost URL; the local backend runs no real proxy.
        url = f"http://127.0.0.1:{port}"
        self._exposed[port] = url
        return url

    async def snapshot(self) -> str:
        # Copy the working root to a sibling directory as a degenerate snapshot.
        snapshot_id = f"snap-{uuid.uuid4().hex[:12]}"
        shutil.copytree(self._root, self._root.parent / snapshot_id)
        return snapshot_id

    async def info(self) -> SandboxInfo:
        # Return a read-only snapshot of this sandbox's current state.
        return SandboxInfo(sandbox_id=self.sandbox_id, platform=Platform.LOCAL, status=self._status, workdir=str(self._root), created_at=self._created_at, exposed_urls=dict(self._exposed), labels=dict(self._config.labels))

    async def destroy(self) -> None:
        # Remove the working root; idempotent and safe after errors.
        if self._status is SandboxStatus.DESTROYED:
            return
        shutil.rmtree(self._root, ignore_errors=True)
        self._status = SandboxStatus.DESTROYED

    def _resolve(self, remote_path: str) -> Path:
        # Resolve a path inside the root, rejecting traversal outside it.
        candidate = (self._root / remote_path.lstrip("/")).resolve()
        root = self._root.resolve()
        if root != candidate and root not in candidate.parents:
            raise SandboxExecutionError("Path escapes sandbox working directory.", details={"path": remote_path})
        return candidate


class LocalSandboxProvider(BaseSandboxProvider):
    """Creates subprocess-backed local sandboxes for development and tests."""

    platform = Platform.LOCAL

    async def create(self, config: SandboxConfig) -> LocalSandbox:
        # Make a temp workdir, build the env, construct the box, then provision it.
        sandbox_id = f"local-{uuid.uuid4().hex[:12]}"
        root = Path(tempfile.mkdtemp(prefix="vidbyte-sbx-"))
        sandbox = LocalSandbox(sandbox_id, root, config, self._merge_env(config))
        await SandboxProvisioner(sandbox, config).provision()
        return sandbox


__all__ = [
    "LocalSandbox",
    "LocalSandboxProvider",
]
