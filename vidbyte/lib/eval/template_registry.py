"""Context Protocol Header

Description:
    Provides TemplatesRegistry for centralised management of LLM-as-a-judge prompt templates.
Purpose:
    Gives developers a discoverable, overridable interface to all judge default templates
    without touching individual judge files.
Architecture:
    - TemplatesRegistry: dict-backed registry loaded from JUDGE_TEMPLATES on instantiation.
      Each instance is isolated; mutations do not affect other instances or the source dict.
Relations:
    Loads from vidbyte.lib.config.templates.JUDGE_TEMPLATES.
    Consumed by all judge files in vidbyte/evals/llm_as_a_judge/.
"""

from __future__ import annotations

from vidbyte.lib.config.templates import JUDGE_TEMPLATES


class TemplatesRegistry:
    """Isolated, mutable registry of judge prompt templates loaded from the SDK defaults."""

    def __init__(self) -> None:
        # Copies JUDGE_TEMPLATES so per-instance mutations stay isolated.
        self._templates: dict[str, str] = dict(JUDGE_TEMPLATES)

    def get(self, name: str) -> str:
        # Returns the template string for name; raises KeyError if not registered.
        if name not in self._templates:
            raise KeyError(
                f"Template '{name}' not found. Call .names() to list all registered templates."
            )
        return self._templates[name]

    def search(self, keyword: str) -> list[str]:
        # Returns sorted list of template names whose key contains keyword (case-insensitive).
        lower = keyword.lower()
        return sorted(k for k in self._templates if lower in k.lower())

    def create(self, name: str, template: str) -> None:
        # Registers or overwrites a template; raises ValueError if name or template is empty.
        if not name or not isinstance(name, str):
            raise ValueError("Template name must be a non-empty string.")
        if not template or not isinstance(template, str):
            raise ValueError("Template body must be a non-empty string.")
        self._templates[name] = template

    def exists(self, name: str) -> bool:
        # Returns True if name is registered in this registry instance.
        return name in self._templates

    def names(self) -> list[str]:
        # Returns a sorted list of all registered template names.
        return sorted(self._templates.keys())


__all__ = ["TemplatesRegistry"]
