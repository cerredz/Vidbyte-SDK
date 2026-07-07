"""
FILE: vidbyte/tools/client.py

PURPOSE:
    Provides the SDK namespace client for tool operations. Owns the default registry and executor exposed from VidbyteSDK().tools without auto-registering potentially environment-specific tools.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/tools layer, which owns top-level tool contracts, catalogs, adapters, decorators, and execution helpers.
    It should be read with `vidbyte/tools/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.tools.adapters: imported by this file.
    - vidbyte.tools.base: imported by this file.
    - vidbyte.tools.catalog: imported by this file.
    - vidbyte.tools.executor: imported by this file.
    - vidbyte.tools.security: imported by this file.
    - vidbyte.tools.types: imported by this file.

FUNCTION INVENTORY:
    - ToolsClient (class): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - None observed in this file; preserve this when adding new failure paths.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; tests/test_custom_function_tools.py and tool-related scripts when changing tool behavior.

CONCURRENCY MODEL:
    - No explicit concurrency primitive; keep future mutable state local to calls unless documented here.
"""
from __future__ import annotations

from typing import Any

from vidbyte.tools.adapters import ToolInput
from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolSpec


class ToolsClient:
    """Namespace client for tool registration and execution."""

    tool_spec_type = ToolSpec

    def __init__(self, *, permission_policy: PermissionPolicy | None = None) -> None:
        """Create a registry and executor for tool operations."""
        from vidbyte.lib.registries.tools import ToolRegistry

        self.catalog = Tools()
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(
            self.registry,
            permission_policy=permission_policy,
        )

    def register(self, tool: ToolInput) -> BaseTool:
        """Register a tool and return it for fluent setup in scripts."""
        self.registry.register(tool)
        self.catalog = self.catalog.add(tool)
        return self.registry.get(self.registry.all()[-1].name)

    def with_tools(self, tools: ToolInput | list[ToolInput] | tuple[ToolInput, ...]) -> "ToolsClient":
        """Attach tools to this namespace catalog and compatibility registry."""
        items = (tools,) if isinstance(tools, BaseTool) or callable(tools) else tuple(tools)
        self.registry.register_many(items)
        self.catalog = self.catalog.extend(items)
        return self
