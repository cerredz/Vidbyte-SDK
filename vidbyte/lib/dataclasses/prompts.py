"""FILE: vidbyte/lib/dataclasses/prompts.py

PURPOSE: Defines SystemPromptPresetSelection, the validated record for an agent's own system-prompt presets.
ROLE IN CODEBASE: BaseAgent.__init__ and JevAgentSettings.__post_init__ both pass their caller's loose value through SystemPromptPresetSelection.parse, so the accepted shapes and the error messages exist once.
ARCHITECTURE NOTE: parse keeps None as None, because None means "inherit the presets of the run this agent runs in" (vidbyte/lib/system_prompt_presets.py), while an empty tuple means "none, and do not inherit". The record itself only ever holds a concrete tuple.
COMMON MODIFICATION PATTERNS: A new preset is a SystemPromptPreset member plus its prompt family; this record needs no change.
KNOWN EDGE CASES: A bare string is rejected, because iterating it would read one character per preset. String members are coerced to the enum, so YAML-style values work. A generator is consumed once.
RELATED DOCS: docs/design/working-principles-preset.md.
TESTS: tests/features/system_prompt_presets/test_system_prompt_presets_units.py.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from vidbyte.lib.enums.prompts import SystemPromptPreset
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class SystemPromptPresetSelection:
    """An agent's own system-prompt presets: known members only, each at most once."""

    presets: tuple[SystemPromptPreset, ...]

    def __post_init__(self) -> None:
        # Rejects any value that is not a preset member, and any member given twice.
        for preset in self.presets:
            if not isinstance(preset, SystemPromptPreset):
                raise ConfigurationError(
                    "System-prompt presets must be SystemPromptPreset members.",
                    details={"value": repr(preset)},
                )
        if len(set(self.presets)) != len(self.presets):
            raise ConfigurationError(
                "System-prompt presets must not repeat a preset.",
                details={"presets": [preset.value for preset in self.presets]},
            )

    @classmethod
    def parse(cls, value: object, owner: str) -> tuple[SystemPromptPreset, ...] | None:
        """Return the validated presets for a caller's value, or None when the caller left it unset to inherit."""
        if value is None:
            return None
        # @intent bare-string-is-not-a-preset-list
        # A string is iterable, so tuple() would read "working_principles"
        # as one preset per character instead of failing clearly.
        if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
            raise ConfigurationError(
                f"{owner} must be a list of SystemPromptPreset values or None, not {type(value).__name__}.",
                details={"owner": owner, "value_type": type(value).__name__},
            )
        return cls(presets=tuple(cls._member(item, owner) for item in value)).presets

    @staticmethod
    def _member(item: object, owner: str) -> SystemPromptPreset:
        # Coerces one string value to its preset member and names the allowed values when it is unknown.
        if isinstance(item, SystemPromptPreset):
            return item
        try:
            return SystemPromptPreset(item)
        except ValueError as exc:
            raise ConfigurationError(
                f"{owner} has an unknown system-prompt preset: {item!r}.",
                details={"owner": owner, "value": repr(item), "allowed": [preset.value for preset in SystemPromptPreset]},
            ) from exc


__all__ = ["SystemPromptPresetSelection"]
