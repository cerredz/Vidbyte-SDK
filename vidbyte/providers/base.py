from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.tools import ToolsFormatter
from vidbyte.tools.types import ToolSpec


def tool_spec_to_provider_schema(spec: ToolSpec, provider: str) -> Mapping[str, Any]:
    """Translate a Vidbyte tool spec into a provider-facing schema shape."""
    if provider == "anthropic":
        return ToolsFormatter.to_anthropic_tool(spec)
    if provider == "gemini":
        gemini = ToolsFormatter.to_gemini_tool(spec)
        declaration = gemini["function_declarations"][0]
        return {
            "name": declaration["name"],
            "description": declaration["description"],
            "parameters": declaration["parameters"],
        }
    return ToolsFormatter.to_openai_tool(spec)

