from __future__ import annotations

from vidbyte.prompts.catalog import Prompts


class VMAOPrompts:
    """JSON-backed prompt accessor for verified multi-agent orchestration."""

    def __init__(self, name: str) -> None:
        self.name = name

    def export(self, **kwargs: object) -> str:
        template = Prompts().family("vmao")[self.name]
        return template.format(**kwargs)


__all__ = [
    "VMAOPrompts",
]
