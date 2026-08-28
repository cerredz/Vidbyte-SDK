"""Context Protocol Header

Description:
    Defines the abstract base class and structural protocol for all Vidbyte SDK tools.
Purpose:
    Provides shared call validation, model-facing description customization, and a small
    async execution contract while supporting both class-based and protocol-based developer
    tools. Customization is limited to descriptions; this file must not add business
    parameters or alter a tool's execution contract.
Architecture:
    - BaseTool: Abstract contract requiring spec() and execute(), plus the
      with_activity() and customize() bindings used to add controlled model-facing views.
      customize() requires a concrete tool description and parameter-description mapping.
    - _ToolWrapper and _unwrap_tool: Private shared wrapper identity used by activity and
      specification customization so runtime pricing can recover the original tool.
    - ToolLike: Structural protocol for developer-provided tools.
Relations:
    Called by vidbyte.tools.activity, vidbyte.tools.customization, vidbyte.tools.adapters,
    and built-in tool modules. It calls vidbyte.tools.types for tool contracts and lazily
    calls vidbyte.lib.dataclasses.tools for customization validation, plus
    vidbyte.tools.activity and vidbyte.tools.customization for wrapper construction.
    vidbyte.agents.runtime relies on the wrapper unwrapping path for priced operations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Protocol

from vidbyte.tools.types import ToolActivity, ToolCall, ToolResult, ToolSpec

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
        from vidbyte.tools.customization import _CustomizedTool

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
