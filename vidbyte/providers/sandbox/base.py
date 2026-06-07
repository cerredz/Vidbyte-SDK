"""Context Protocol Header

Description:
    Shared base for sandbox providers and the deterministic provisioner.
Purpose:
    Lowers a SandboxConfig into an ordered sequence of exec/upload calls so every
    provider gets identical repo/branch/local-folder/setup behavior for free.
Architecture:
    - BaseSandboxProvider: Common helper mixin for concrete providers.
    - SandboxProvisioner: Runs secrets -> clone -> seed -> setup in fixed order.
Relations:
    Used by vidbyte.providers.sandbox.local/docker and the lazy vendor adapters.
"""

from __future__ import annotations

import os
import tarfile
import tempfile
from pathlib import Path

from vidbyte.lib.dataclasses.sandbox import Sandbox, SandboxConfig
from vidbyte.lib.errors import SandboxProvisionError


class SandboxProvisioner:
    """Lowers a SandboxConfig into ordered exec/upload calls on a live box."""

    def __init__(self, sandbox: Sandbox, config: SandboxConfig) -> None:
        # Bind the provisioner to one freshly created sandbox and its config.
        self._sandbox = sandbox
        self._config = config

    async def provision(self) -> None:
        # Run every provisioning step in fixed deterministic order before the agent.
        await self._seed_repo()
        await self._seed_local_folder()
        await self._run_setup()

    async def _seed_repo(self) -> None:
        # Clone an optional git repo, then check out a pinned commit or branch.
        if not self._config.repo:
            return
        url = self._clone_url()
        clone = await self._sandbox.exec(["sh", "-c", f"git clone {url} {self._config.workdir}"])
        if clone.exit_code != 0:
            raise SandboxProvisionError("Repository clone failed.", details={"repo": self._config.repo, "stderr": self._redact(clone.stderr)})
        await self._checkout_ref()

    async def _checkout_ref(self) -> None:
        # Pin to a commit (reproducible) or a branch when one is requested.
        ref = self._config.commit or self._config.branch
        if not ref:
            return
        checkout = await self._sandbox.exec(["sh", "-c", f"cd {self._config.workdir} && git checkout {ref}"])
        if checkout.exit_code != 0:
            raise SandboxProvisionError("Repository checkout failed.", details={"ref": ref, "stderr": self._redact(checkout.stderr)})

    async def _seed_local_folder(self) -> None:
        # Tar a host directory, upload it, and extract it into the workdir.
        if not self._config.seed_local:
            return
        source = Path(self._config.seed_local)
        if not source.exists():
            raise SandboxProvisionError("seed_local path does not exist on host.", details={"path": str(source)})
        archive = self._make_archive(source)
        try:
            await self._sandbox.upload(str(archive), "/tmp/seed.tar")
            await self._sandbox.exec(["sh", "-c", f"mkdir -p {self._config.workdir} && tar -xf /tmp/seed.tar -C {self._config.workdir}"])
        finally:
            archive.unlink(missing_ok=True)

    async def _run_setup(self) -> None:
        # Execute setup commands in listed order, aborting on the first failure.
        for command in self._config.setup:
            result = await self._sandbox.exec(["sh", "-c", f"cd {self._config.workdir} && {command}"])
            if result.exit_code != 0:
                raise SandboxProvisionError("Setup command failed.", details={"command": command, "stderr": self._redact(result.stderr)})

    def _clone_url(self) -> str:
        # Build a clone URL that expands an injected token in-box, never logging it.
        repo = self._config.repo or ""
        if repo.startswith("http://") or repo.startswith("https://") or repo.startswith("git@"):
            return repo
        token_keys = [key for key in self._config.secrets if "TOKEN" in key.upper()]
        if token_keys:
            return f"https://x-access-token:${{{token_keys[0]}}}@{repo}"
        return f"https://{repo}"

    def _make_archive(self, source: Path) -> Path:
        # Create a temporary tar of the host directory, skipping common ignores.
        ignored = {".git", "__pycache__", "node_modules", ".venv"}
        handle = tempfile.NamedTemporaryFile(suffix=".tar", delete=False)
        handle.close()
        with tarfile.open(handle.name, "w") as archive:
            for entry in sorted(source.rglob("*")):
                if any(part in ignored for part in entry.parts):
                    continue
                archive.add(entry, arcname=entry.relative_to(source).as_posix())
        return Path(handle.name)

    def _redact(self, text: str) -> str:
        # Strip any injected secret values from captured output before surfacing.
        cleaned = text
        for value in self._config.secrets.values():
            if value:
                cleaned = cleaned.replace(value, "***")
        return cleaned[:1000]


class BaseSandboxProvider:
    """Common helpers shared by concrete sandbox providers."""

    def _merge_env(self, config: SandboxConfig) -> dict[str, str]:
        # Merge process env, user env, and injected secrets for the box runtime.
        merged = dict(os.environ)
        merged.update(dict(config.env))
        merged.update(dict(config.secrets))
        return merged


__all__ = [
    "BaseSandboxProvider",
    "SandboxProvisioner",
]
