"""Context Protocol Header

Description:
    Exposes all consolidated registry layers from the Vidbyte SDK.
Purpose:
    Allows modular lookup of agents, models, prompts, tools, and concurrent actors.
Architecture:
    Package initializer.
Relations:
    Located in vidbyte/lib/registries/__init__.py. Imported across the SDK.
Similar Files:
    - vidbyte/agents/runtimes/__init__.py: Runtimes exports.
"""

from __future__ import annotations

from vidbyte.lib.registries.agents import AgentRegistry
from vidbyte.lib.registries.handoffs import HandoffRegistry
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.registries.prompts import PromptRecord, Prompts
from vidbyte.lib.registries.runtimes import RuntimeRegistry
from vidbyte.lib.registries.tools import ToolRegistry
from vidbyte.lib.registries.actors import ActorRegistry, actor_registry

__all__ = [
    "AgentRegistry",
    "HandoffRegistry",
    "ProviderModelRegistry",
    "PromptRecord",
    "Prompts",
    "RuntimeRegistry",
    "ToolRegistry",
    "ActorRegistry",
    "actor_registry",
]
