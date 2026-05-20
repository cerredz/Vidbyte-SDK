from __future__ import annotations

from typing import Any, Mapping

from vidbyte.providers.base import tool_spec_to_provider_schema
from vidbyte.tools.types import ToolSpec


def tool_schema(spec: ToolSpec) -> Mapping[str, Any]:
    return tool_spec_to_provider_schema(spec, "openai")

