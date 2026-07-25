"""Context Protocol Header

Description:
    Defines the HandoffAgentDescriptor dataclass — a thin configuration wrapper
    for YAML-loaded handoff agent configurations. Holds the handoff spec (title,
    instructions, sections) and source provider/model for the internal HandoffAgent.
Purpose:
    Provides a typed configuration object that the YamlLoader produces from a
    handoff-agent YAML document. Validates section presence, title length, and
    provider/model pairing.
Architecture:
    - HandoffAgentDescriptor: frozen dataclass holding handoff metadata and source config.
    - __post_init__ validates sections, title, and provider/model.
Relations:
    - Produced by vidbyte/lib/config/loader.py.
    - Used to construct HandoffAgent instances at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.errors import ConfigurationError

_MAX_TITLE_CHARS = 200
_MAX_INSTRUCTIONS_CHARS = 2000
_MAX_SECTION_TITLE_CHARS = 100


@dataclass(frozen=True, slots=True)
class HandoffAgentDescriptor:
    """Typed handoff agent configuration loaded from a YAML document."""

    name: str = "handoff"
    handoff_title: str = "Handoff"
    handoff_instructions: str = ""
    sections: tuple[str, ...] = ()
    source_provider: str | None = None
    source_model_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates handoff title, sections list, and optional provider/model pairing.
        self._validate_title()
        self._validate_sections()
        self._validate_provider_model()

    def to_agent_kwargs(self) -> dict[str, Any]:
        # Returns the handoff spec as a dict for HandoffAgent construction.
        return {
            "name": self.name,
            "title": self.handoff_title,
            "instructions": self.handoff_instructions,
            "sections": dict.fromkeys(self.sections, ""),
            "source_provider": self.source_provider,
            "source_model_name": self.source_model_name,
        }

    def _validate_title(self) -> None:
        # Validates the handoff title is non-empty and within length limits.
        if not self.handoff_title or not self.handoff_title.strip():
            raise ConfigurationError(
                "Handoff title must be a non-empty string.",
                details={"field": "handoff.title", "expected": "non-empty string"},
            )
        if len(self.handoff_title) > _MAX_TITLE_CHARS:
            raise ConfigurationError(
                f"Handoff title must be at most {_MAX_TITLE_CHARS} characters.",
                details={"field": "handoff.title", "max_chars": _MAX_TITLE_CHARS, "actual_chars": len(self.handoff_title)},
            )
        if len(self.handoff_instructions) > _MAX_INSTRUCTIONS_CHARS:
            raise ConfigurationError(
                f"Handoff instructions must be at most {_MAX_INSTRUCTIONS_CHARS} characters.",
                details={"field": "handoff.instructions", "max_chars": _MAX_INSTRUCTIONS_CHARS, "actual_chars": len(self.handoff_instructions)},
            )

    def _validate_sections(self) -> None:
        # Validates at least one section and each section title is non-empty within length limits.
        if not self.sections:
            raise ConfigurationError(
                "Handoff must have at least one section.",
                details={"field": "handoff.sections", "expected": "at least one section title"},
            )
        seen: set[str] = set()
        for index, section in enumerate(self.sections):
            if not section or not section.strip():
                raise ConfigurationError(
                    f"Handoff section at index {index} must be non-empty.",
                    details={"field": f"handoff.sections[{index}]", "expected": "non-empty string"},
                )
            if len(section) > _MAX_SECTION_TITLE_CHARS:
                raise ConfigurationError(
                    f"Handoff section '{section}' must be at most {_MAX_SECTION_TITLE_CHARS} characters.",
                    details={"field": f"handoff.sections[{index}]", "max_chars": _MAX_SECTION_TITLE_CHARS, "actual_chars": len(section)},
                )
            if section in seen:
                raise ConfigurationError(
                    f"Duplicate handoff section '{section}' at index {index}.",
                    details={"field": f"handoff.sections[{index}]", "actual": section},
                )
            seen.add(section)

    def _validate_provider_model(self) -> None:
        # Validates provider/model are both set or both absent, and provider is recognized.
        if self.source_provider is None and self.source_model_name is None:
            return
        if self.source_provider is None or self.source_model_name is None:
            raise ConfigurationError(
                "Handoff source_provider and source_model_name must both be provided or both omitted.",
                details={
                    "field": "handoff.source_provider" if self.source_provider is None else "handoff.source_model_name",
                    "expected": "both provider and model_name",
                },
            )
        try:
            ModelProvider(self.source_provider)
        except ValueError as exc:
            known = sorted(p.value for p in ModelProvider)
            raise ConfigurationError(
                f"Unrecognized source_provider '{self.source_provider}'. Known providers: {known}.",
                details={"field": "handoff.source_provider", "actual": self.source_provider, "expected": known},
            ) from exc


__all__ = ["HandoffAgentDescriptor"]
