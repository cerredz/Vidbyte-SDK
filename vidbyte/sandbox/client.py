"""Context Protocol Header

Description:
    Namespace client for sandbox operations exposed as sdk.sandboxes.
Purpose:
    Owns a SandboxManager instance and surfaces the Sandbox facade so callers can
    create, run, manage, and view sandboxes from the root SDK client.
Architecture:
    - SandboxClient: Holds a manager and convenience create/put/list helpers.
Relations:
    Constructed by vidbyte.client.VidbyteSDK; mirrors ProvidersClient/ToolsClient.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.lib.dataclasses.sandbox import SandboxInfo
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.platform import Platform
from vidbyte.sandbox.facade import Sandbox
from vidbyte.sandbox.manager import SandboxManager


class SandboxClient:
    """Namespace client for creating and managing sandboxes."""

    def __init__(self) -> None:
        # Own a dedicated manager so this client tracks its own sandboxes.
        self.manager = SandboxManager()

    async def create(self, *, platform: Platform | str = Platform.LOCAL, **params: object) -> Sandbox:
        # Create a provisioned sandbox tracked by this client's manager.
        return await Sandbox.create(platform=platform, manager=self.manager, **params)  # type: ignore[arg-type]

    async def put(self, agent: object, task: str, *, platform: Platform | str = Platform.LOCAL, **params: object) -> tuple[AgentResult, Sandbox]:
        # Create a sandbox and run an agent's full loop inside it.
        sandbox = await self.create(platform=platform, **params)
        result = await sandbox.run_agent(agent, task)
        return result, sandbox

    def list(self) -> tuple[SandboxInfo, ...]:
        # List info for every sandbox tracked by this client.
        return self.manager.list()

    async def get(self, sandbox_id: str) -> Sandbox:
        # Fetch a tracked sandbox by id.
        return await Sandbox.get(sandbox_id, manager=self.manager)

    async def destroy_all(self) -> None:
        # Destroy every sandbox tracked by this client.
        await self.manager.destroy_all()


__all__ = [
    "SandboxClient",
]
