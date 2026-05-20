# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the ToolRegistry class for the Vidbyte SDK.
# Purpose: Manages tool registrations, lookups, and serialization for prompt insertion.
# Architecture & Functions:
#   - ToolRegistry (class): Storage for registered tools, with thread-safe operations.
#   - ToolRegistry.register(tool): Adds a tool to the registry.
#   - ToolRegistry.get(name): Looks up a single tool by name.
#   - ToolRegistry.specs_as_prompt_str(): Renders all tool specs as a combined prompt instruction.
# Codebase Relation:
#   - Provides the central registry from which harnesses, strategies, and executors pull.
# Similar Files:
#   - vidbyte/prompts/registry.py (manages the versioned prompt templates)
# ==============================================================================

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolSpec


class ToolRegistry:
    """
    Central registry for managing agent tools.
    Decouples strategies and harnesses from specific tool implementations.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self._lock = threading.Lock()

    def register(self, tool: BaseTool) -> ToolRegistry:
        """Registers a tool in a thread-safe manner. Returns self for chaining."""
        with self._lock:
            self._tools[tool.name] = tool
        return self

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieves a registered tool by name."""
        with self._lock:
            return self._tools.get(name)

    def get_many(self, names: List[str]) -> List[BaseTool]:
        """Retrieves a list of registered tools by their names."""
        with self._lock:
            return [self._tools[n] for n in names if n in self._tools]

    def all(self) -> List[BaseTool]:
        """Returns all registered tools."""
        with self._lock:
            return list(self._tools.values())

    def specs(self) -> List[ToolSpec]:
        """Returns the specifications of all registered tools."""
        with self._lock:
            return [t.spec() for t in self._tools.values()]

    def specs_as_prompt_str(self) -> str:
        """Renders all registered tool specifications as a combined block for prompting."""
        with self._lock:
            return "\n\n".join([
                t.spec().to_prompt_str()
                for t in self._tools.values()
            ])

    def unregister(self, name: str) -> ToolRegistry:
        """Unregisters a tool by name in a thread-safe manner. Returns self for chaining."""
        with self._lock:
            self._tools.pop(name, None)
        return self
