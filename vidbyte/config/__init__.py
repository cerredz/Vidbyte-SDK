"""Context Protocol Header

Description:
    Exposes the public YAML configuration namespace.
Purpose:
    Gives SDK users a stable class-first interface for safe, declarative settings loading.
Architecture:
    Re-exports YamlLoader and its typed declaration objects.
Relations:
    Available from vidbyte.config, vidbyte, and VidbyteSDK().config. The declaration
    dataclasses live in vidbyte.lib.dataclasses and are forwarded through vidbyte.config.types.
Non-Goals:
    This package parses declarations only; applications resolve refs to runtime objects.
"""

from vidbyte.config.loader import YamlLoader
from vidbyte.config.types import AgentSettings, MiddlewareDefinition, ToolDefinition

__all__ = ["AgentSettings", "MiddlewareDefinition", "ToolDefinition", "YamlLoader"]
