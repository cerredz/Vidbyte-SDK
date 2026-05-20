from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Model-facing description of a callable tool."""

    name: str
    description: str
    parameters: Mapping[str, str] = field(default_factory=dict)

    def to_prompt_str(self) -> str:
        """Render a compact prompt-safe description."""

        params = ", ".join(f"{name}: {desc}" for name, desc in self.parameters.items())
        if not params:
            params = "none"
        return f"{self.name}: {self.description} Parameters: {params}"
