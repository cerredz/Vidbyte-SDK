"""Context Protocol Header

Description:
    In-process registry that creates, tracks, views, and destroys many sandboxes.
Purpose:
    Backs the multi-sandbox management surface so callers can list, inspect, and
    tear down more than one live environment, with TTL reaping on access.
Architecture:
    - SandboxManager: Owns provider handles keyed by sandbox id.
Relations:
    Uses vidbyte.providers.sandbox.SandboxProviders; consumed by the Sandbox facade.
"""

from __future__ import annotations

import time

from vidbyte.lib.dataclasses.sandbox import Sandbox as SandboxHandle, SandboxConfig, SandboxInfo
from vidbyte.lib.errors import SandboxError, SandboxNotFoundError
from vidbyte.providers.sandbox import SandboxProviders


class SandboxManager:
    """Creates and tracks multiple live sandboxes in one process."""

    def __init__(self) -> None:
        # Initialize the handle, info-record, creation-time, and ttl maps.
        self._handles: dict[str, SandboxHandle] = {}
        self._records: dict[str, SandboxInfo] = {}
        self._created: dict[str, float] = {}
        self._ttl: dict[str, float | None] = {}

    async def create(self, config: SandboxConfig) -> SandboxHandle:
        # Reap expired boxes, create a provisioned sandbox, and register it.
        await self.reap_expired()
        handle = await SandboxProviders.create(config.platform, config)
        self._handles[handle.sandbox_id] = handle
        self._records[handle.sandbox_id] = await handle.info()
        self._created[handle.sandbox_id] = time.time()
        self._ttl[handle.sandbox_id] = config.ttl_seconds
        return handle

    async def get(self, sandbox_id: str) -> SandboxHandle:
        # Return a tracked handle, reaping expired boxes first.
        await self.reap_expired()
        if sandbox_id not in self._handles:
            raise SandboxNotFoundError("Sandbox not found.", details={"sandbox_id": sandbox_id})
        return self._handles[sandbox_id]

    def list(self) -> tuple[SandboxInfo, ...]:
        # Return cached info records for every currently tracked sandbox.
        return tuple(self._records.values())

    async def view(self, sandbox_id: str) -> SandboxInfo:
        # Fetch a live info snapshot for one sandbox and refresh its record.
        handle = await self.get(sandbox_id)
        info = await handle.info()
        self._records[sandbox_id] = info
        return info

    async def destroy(self, sandbox_id: str) -> None:
        # Deregister and tear down one tracked sandbox.
        handle = self._handles.pop(sandbox_id, None)
        if handle is None:
            raise SandboxNotFoundError("Sandbox not found.", details={"sandbox_id": sandbox_id})
        self._records.pop(sandbox_id, None)
        self._created.pop(sandbox_id, None)
        self._ttl.pop(sandbox_id, None)
        await handle.destroy()

    async def destroy_all(self) -> None:
        # Destroy every tracked sandbox, continuing past individual failures.
        errors: list[Exception] = []
        for sandbox_id in list(self._handles):
            try:
                await self.destroy(sandbox_id)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise SandboxError("One or more sandboxes failed to destroy.", details={"count": len(errors)})

    async def reap_expired(self) -> None:
        # Destroy any sandbox whose age has exceeded its configured ttl.
        now = time.time()
        for sandbox_id in list(self._handles):
            ttl = self._ttl.get(sandbox_id)
            if ttl is not None and (now - self._created.get(sandbox_id, now)) > ttl:
                await self.destroy(sandbox_id)


__all__ = [
    "SandboxManager",
]
