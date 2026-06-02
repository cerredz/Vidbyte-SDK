from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.tools import ToolsFormatter
from vidbyte.tools.types import ToolSpec


def tool_spec_to_provider_schema(spec: ToolSpec, provider: str, *, strict: bool = False) -> Mapping[str, Any]:
    # Translates a Vidbyte tool spec into a provider-facing schema shape.
    if provider == "anthropic":
        return ToolsFormatter.to_anthropic_tool(spec, strict=strict)
    if provider == "gemini":
        gemini = ToolsFormatter.to_gemini_tool(spec, strict=strict)
        declaration = gemini["function_declarations"][0]
        return {
            "name": declaration["name"],
            "description": declaration["description"],
            "parameters": declaration["parameters"],
        }
    return ToolsFormatter.to_openai_tool(spec, strict=strict)

