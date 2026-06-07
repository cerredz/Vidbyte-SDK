"""Context Protocol Header

Description:
    Central registration and factory registry for sandbox provider adapters.
Purpose:
    Exposes a Platform-keyed SandboxProviders factory to resolve and instantiate
    sandbox backends, mirroring vidbyte.providers.ModelProviders. Third parties
    can register custom platforms via register_provider.
Architecture:
    - SandboxProviders: Static factory + registry over Platform values.
Relations:
    Used by vidbyte.sandbox.manager and vidbyte.lib.runners.sandbox.
Similar Files:
    - vidbyte/providers/__init__.py: Model provider factory.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sandbox import Sandbox, SandboxConfig, SandboxProvider
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.errors import SandboxProviderError
from vidbyte.providers.sandbox.daytona import DaytonaSandboxProvider
from vidbyte.providers.sandbox.docker import DockerSandboxProvider
from vidbyte.providers.sandbox.e2b import E2BSandboxProvider
from vidbyte.providers.sandbox.fly import FlySandboxProvider
from vidbyte.providers.sandbox.local import LocalSandboxProvider
from vidbyte.providers.sandbox.modal import ModalSandboxProvider


class SandboxProviders:
    """Central factory and registry for sandbox provider adapters."""

    _registry: dict[Platform, type[SandboxProvider]] = {
        Platform.LOCAL: LocalSandboxProvider,
        Platform.DOCKER: DockerSandboxProvider,
        Platform.E2B: E2BSandboxProvider,
        Platform.MODAL: ModalSandboxProvider,
        Platform.DAYTONA: DaytonaSandboxProvider,
        Platform.FLY: FlySandboxProvider,
    }

    @staticmethod
    def create_provider(platform: Platform | str) -> SandboxProvider:
        # Resolve and instantiate the provider adapter for a platform.
        resolved = SandboxProviders._normalize(platform)
        provider_cls = SandboxProviders._registry.get(resolved)
        if provider_cls is None:
            raise SandboxProviderError(f"Unsupported sandbox platform: {resolved.value}", details={"supported": [item.value for item in SandboxProviders._registry]})
        return provider_cls()

    @staticmethod
    def register_provider(platform: Platform, provider_cls: type[SandboxProvider]) -> None:
        # Register or override a provider class for a platform (extensibility hook).
        SandboxProviders._registry[platform] = provider_cls

    @staticmethod
    async def create(platform: Platform | str, config: SandboxConfig) -> Sandbox:
        # Resolve the provider and create a provisioned sandbox from config.
        provider = SandboxProviders.create_provider(platform)
        return await provider.create(config)

    @staticmethod
    def supported() -> tuple[str, ...]:
        # Return the platform values currently registered.
        return tuple(item.value for item in SandboxProviders._registry)

    @staticmethod
    def _normalize(platform: Platform | str) -> Platform:
        # Coerce a string platform into the Platform enum, raising on unknown ones.
        if isinstance(platform, Platform):
            return platform
        try:
            return Platform(str(platform).lower())
        except ValueError as exc:
            raise SandboxProviderError(f"Unknown sandbox platform: {platform!r}", details={"supported": [item.value for item in SandboxProviders._registry]}) from exc


__all__ = [
    "DaytonaSandboxProvider",
    "DockerSandboxProvider",
    "E2BSandboxProvider",
    "FlySandboxProvider",
    "LocalSandboxProvider",
    "ModalSandboxProvider",
    "SandboxProviders",
]
