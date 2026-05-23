from __future__ import annotations

from vidbyte.lib.prompts import PromptRegistry


class VMAOPrompts:
    """JSON-backed prompt accessor for verified multi-agent orchestration."""

    def __init__(self, name: str) -> None:
        self.name = name

    def export(self, **kwargs: object) -> str:
        template = PromptRegistry.default().get("vmao")[self.name]
        return template.format(**kwargs)


__all__ = [
    "VMAOPrompts",
]
