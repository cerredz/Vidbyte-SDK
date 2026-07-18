"""Context Protocol Header

Description:
    Exposes the public YAML configuration namespace.
Purpose:
    Gives SDK users a stable class-first interface for safe, declarative settings loading.
Architecture:
    Re-exports ConfigurationLoader and its typed declaration objects.
Relations:
    Available from vidbyte.config, vidbyte, and VidbyteSDK().config.
Non-Goals:
    This package parses declarations only; applications resolve refs to runtime objects.
"""

from vidbyte.config.loader import ConfigurationLoader
from vidbyte.config.types import AgentSettings, MiddlewareDefinition, ToolDefinition

__all__ = ["AgentSettings", "ConfigurationLoader", "MiddlewareDefinition", "ToolDefinition"]
