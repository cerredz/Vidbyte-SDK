"""FILE: vidbyte/lib/jev/presets.py

PURPOSE: Owns the preflight flags a JevAgent user can enable and the fixed policy each flag turns on: which question keys it asks and the score it must reach.
ROLE IN CODEBASE: JevPreflight.validate normalizes JevAgentSettings.preflight through JevPresets, and JevPreflight.combine and JevPreflight.run read each enabled preset's definition from here.
ARCHITECTURE NOTE: The flag vocabulary is JevPreflightPreset in vidbyte/lib/enums/jev.py and the definition record is JevPresetDefinition in vidbyte/lib/dataclasses/jev.py; this module holds only the mapping and the flag logic.
COMMON MODIFICATION PATTERNS: Add a JevPreflightPreset member, its question keys, and one JevPresetDefinition entry here, then register every new question in vidbyte/lib/jev/preflight/.
KNOWN EDGE CASES: A bare string is rejected rather than iterated character by character, and enabling the same flag twice is an error because it would ask Jev every question twice.
RELATED DOCS: docs/design/jev-preflight-clarity.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.lib.constants.jev import JEV_CLARITY_THRESHOLD
from vidbyte.lib.dataclasses.jev import JevPresetDefinition
from vidbyte.lib.enums.jev import JevPreflightPreset, JevPreflightQuestionKey
from vidbyte.lib.errors import ConfigurationError


class JevPresets:
    """The preflight flags a JevAgent user can enable, each mapped to the fixed policy it turns on."""

    _definitions: Mapping[JevPreflightPreset, JevPresetDefinition] = MappingProxyType(
        {
            JevPreflightPreset.CLARITY: JevPresetDefinition(
                preset=JevPreflightPreset.CLARITY,
                question_keys=(
                    JevPreflightQuestionKey.CLARITY_GOAL,
                    JevPreflightQuestionKey.CLARITY_DELIVERABLE,
                    JevPreflightQuestionKey.CLARITY_TARGET,
                    JevPreflightQuestionKey.CLARITY_REFERENCES,
                    JevPreflightQuestionKey.CLARITY_SCOPE,
                    JevPreflightQuestionKey.CLARITY_COMPLETION,
                    JevPreflightQuestionKey.CLARITY_INFORMATION,
                    JevPreflightQuestionKey.CLARITY_CONSTRAINTS,
                    JevPreflightQuestionKey.CLARITY_PRIORITIES,
                    JevPreflightQuestionKey.CLARITY_CONSISTENCY,
                    JevPreflightQuestionKey.CLARITY_TIME_CONTEXT,
                    JevPreflightQuestionKey.CLARITY_SINGLE_READING,
                ),
                threshold=JEV_CLARITY_THRESHOLD,
            ),
        }
    )

    @classmethod
    def definition(cls, preset: JevPreflightPreset) -> JevPresetDefinition:
        """Return the policy a registered flag turns on, or reject a flag with no definition."""
        found = cls._definitions.get(preset)
        if found is None:
            raise ConfigurationError(
                f"Jev preflight preset {preset!r} has no definition in JevPresets.",
                details={"preset": str(preset), "registered": [item.value for item in cls._definitions]},
            )
        return found

    @classmethod
    def available(cls) -> tuple[JevPreflightPreset, ...]:
        """Return every flag a user can enable, in declaration order."""
        return tuple(cls._definitions)

    @classmethod
    def resolve(cls, value: object) -> JevPreflightPreset:
        """Convert one user-supplied flag (enum member or its string value) to a registered preset."""
        try:
            preset = value if isinstance(value, JevPreflightPreset) else JevPreflightPreset(value)
        except ValueError as exc:
            raise ConfigurationError(
                f"Unsupported Jev preflight preset: {value!r}.",
                details={"received": repr(value), "available": [item.value for item in cls.available()]},
            ) from exc
        cls.definition(preset)
        return preset

    @classmethod
    def normalize(cls, values: Iterable[object]) -> tuple[JevPreflightPreset, ...]:
        """Convert the user's enabled flags to a tuple of unique registered presets, in the order given."""
        # @intent preflight-flags-fail-before-any-jev-call
        # Settings construction calls this, so a typo, a bare string, or a repeated flag fails when the
        # agent is built instead of silently asking Jev the wrong (or duplicated) questions on every run.
        if isinstance(values, (str, bytes)):
            raise ConfigurationError("JevAgentSettings.preflight must be an iterable of Jev preflight presets, not a string.", details={"received": repr(values)})
        try:
            presets = tuple(cls.resolve(value) for value in values)
        except TypeError as exc:
            raise ConfigurationError("JevAgentSettings.preflight must be an iterable of Jev preflight presets.", details={"received": type(values).__name__}) from exc
        if len(set(presets)) != len(presets):
            raise ConfigurationError("JevAgentSettings.preflight cannot enable the same preset twice.", details={"received": [preset.value for preset in presets]})
        return presets


__all__ = ["JevPresets"]
