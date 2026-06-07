"""Context Protocol Header

Description:
    Thin public facade for the Vidbyte sandbox feature.
Purpose:
    Re-exports the clean user surface (Sandbox, SandboxManager, SandboxClient) and
    key contracts so callers can create, run, and manage isolated environments
    from one import without reaching into the provider/runner layers.
Architecture:
    - Sandbox: Ergonomic per-box handle + create/put/list/get classmethods.
    - SandboxManager: In-process multi-sandbox registry.
    - SandboxClient: Namespace client mounted at sdk.sandboxes.
Relations:
    Aggregates vidbyte.sandbox.facade, vidbyte.sandbox.manager,
    vidbyte.sandbox.client, and vidbyte.providers.sandbox.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sandbox import (
    AgentManifest,
    SandboxConfig,
    SandboxInfo,
    SandboxResult,
    SandboxStatus,
)
from vidbyte.lib.enums.platform import Platform
from vidbyte.providers.sandbox import SandboxProviders
from vidbyte.sandbox.client import SandboxClient
from vidbyte.sandbox.facade import Sandbox
from vidbyte.sandbox.manager import SandboxManager

__all__ = [
    "AgentManifest",
    "Platform",
    "Sandbox",
    "SandboxClient",
    "SandboxConfig",
    "SandboxInfo",
    "SandboxManager",
    "SandboxProviders",
    "SandboxResult",
    "SandboxStatus",
]
