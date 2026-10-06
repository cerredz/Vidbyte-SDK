"""FILE: vidbyte/tools/base.py

PURPOSE: Defines the abstract SDK tool contract, shared wrapper identity, immutable customized wrapper, and developer ToolLike protocol.
ROLE IN CODEBASE: Builtins and adapters subclass BaseTool; activity/customization views delegate through _ToolWrapper so runtime pricing can unwrap them.
ARCHITECTURE NOTE: Base owns wrapper lifecycle and execution delegation, while activity and customization modules own presentation transformations.
COMMON MODIFICATION PATTERNS: Add only behavior shared by every tool and preserve spec, validation, execution, and unwrapping semantics together.
KNOWN EDGE CASES: Wrappers may compose in either order, protocol tools need not subclass BaseTool, and customization may not add arguments.
RELATED DOCS: docs/design/tool-spec-customization.md and vidbyte/tools/README.md.
TESTS: tests/test_tool_core.py, tests/test_provider_tool_schema_translation.py, and scripts/run_ci.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

from vidbyte.tools.types import ToolActivity, ToolCall, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.lib.dataclasses.tools import ToolCustomization

_EMPTY_PARAMETER_DESCRIPTIONS: Mapping[str, str] = MappingProxyType({})


class BaseTool(ABC):
    """Base class for native and bridged tools."""

    @property
    def name(self) -> str:
        """Return the stable registry name from the tool spec."""
        return self.spec().name

    def with_activity(self, activity: ToolActivity) -> "BaseTool":
        """Return this tool with one reserved activity annotation the model fills in per call."""
        from vidbyte.tools.activity import ActivityToolFormatter

        return ActivityToolFormatter.bind(self, activity)

    # @intent description-only-tool-view
    # Applications may adapt the language a model sees for local terminology,
    # but that adaptation must never create a second runtime contract. The
    # current ToolSpec is passed into ToolCustomization so unknown parameter
    # names and provider-schema shape errors fail before a wrapper is cataloged.
    # Requiring a concrete description while defaulting the mapping to empty
    # communicates that this is an explicit model-facing replacement, not a
    # partial mutable patch.
    def customize(
        self,
        *,
        description: str,
        parameter_descriptions: Mapping[str, str] = _EMPTY_PARAMETER_DESCRIPTIONS,
    ) -> "BaseTool":
        """Return a validated model-facing description view over this tool."""
        from vidbyte.lib.dataclasses.tools import ToolCustomization

        customization = ToolCustomization(
            tool_spec=self.spec(),
            description=description,
            parameter_descriptions=parameter_descriptions,
        )
        return _CustomizedTool(self, customization)

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


class _ToolWrapper(BaseTool, ABC):
    """Private base contract for SDK wrappers that preserve one underlying tool."""

    @property
    @abstractmethod
    def wrapped_tool(self) -> BaseTool:
        # Return the implementation whose runtime behavior the wrapper preserves.
        raise NotImplementedError


class _CustomizedTool(_ToolWrapper):
    """Private wrapper that changes model-facing descriptions only."""

    def __init__(self, tool: BaseTool, customization: ToolCustomization) -> None:
        # Retains validated immutable replacement data beside the shared wrapper contract.
        self._tool = tool
        self._customization = customization

    @property
    def wrapped_tool(self) -> BaseTool:
        """Return the original tool whose runtime behavior this view preserves."""
        return self._tool

    def spec(self) -> ToolSpec:
        """Return a fresh model-facing spec with validated descriptions replaced."""
        from vidbyte.tools.customization import _ToolSpecCustomizer

        return _ToolSpecCustomizer.apply(self._tool.spec(), self._customization)

    def validate_call(self, call: ToolCall) -> str | None:
        """Delegate call validation without changing arguments or errors."""
        return self._tool.validate_call(call)

    async def execute(self, call: ToolCall) -> ToolResult:
        """Delegate execution without changing business behavior."""
        return await self._tool.execute(call)


def _unwrap_tool(tool: BaseTool) -> BaseTool:
    # Follow every private SDK wrapper until the executable implementation is reached.
    unwrapped = tool
    while isinstance(unwrapped, _ToolWrapper):
        unwrapped = unwrapped.wrapped_tool
    return unwrapped


class ToolLike(Protocol):
    """Structural protocol for developer-provided tools."""

    def spec(self) -> ToolSpec:
        """Return model-facing tool metadata."""

    async def arun(self, **kwargs: Any) -> Any:
        """Execute the tool asynchronously."""
