"""
FILE: vidbyte/tools/base.py

PURPOSE:
    Defines the abstract base class and structural protocol for all Vidbyte SDK tools. Provides shared call validation and a small async execution contract while supporting both class-based and protocol-based developer tools.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/tools layer, which owns top-level tool contracts, catalogs, adapters, decorators, and execution helpers.
    It should be read with `vidbyte/tools/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.tools.types: imported by this file.

FUNCTION INVENTORY:
    - BaseTool (class): public or navigational symbol owned here.
    - ToolLike (class): public or navigational symbol owned here.

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
    - Review async/task state carefully; this file participates in agent, middleware, tool, or actor execution.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec


class BaseTool(ABC):
    """Base class for native and bridged tools."""

    @property
    def name(self) -> str:
        """Return the stable registry name from the tool spec."""
        return self.spec().name

    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResult:
        """Run the tool for an already validated call."""

    def validate_call(self, call: ToolCall) -> str | None:
        """Return a validation error string, or None when arguments are valid."""
        spec = self.spec()
        missing = [
            name
            for name in spec.required_parameter_names()
            if name not in call.arguments or call.arguments[name] is None
        ]
        if missing:
            return f"Missing required parameters: {', '.join(missing)}"
        return None


class ToolLike(Protocol):
    """Structural protocol for developer-provided tools."""

    def spec(self) -> ToolSpec:
        """Return model-facing tool metadata."""

    async def arun(self, **kwargs: Any) -> Any:
        """Execute the tool asynchronously."""
