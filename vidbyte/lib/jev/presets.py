"""FILE: vidbyte/lib/jev/presets.py

PURPOSE: Owns the preflight flags a JevAgent user can enable and, for each flag with fixed questions, the question keys it asks and the score it must reach.
ROLE IN CODEBASE: JevPreflightRegistry.validate normalizes JevAgentSettings.preflight through JevPresets, and JevPreflightGate (vidbyte/agents/jev/gate/) reads each fixed preset's definition from here when it combines questions and scores answers.
ARCHITECTURE NOTE: The flag vocabulary is JevPreflightPreset in vidbyte/lib/enums/jev.py and the definition record is JevPresetDefinition in vidbyte/lib/dataclasses/jev.py; this module holds only the mapping and the flag logic.
COMMON MODIFICATION PATTERNS: Add a JevPreflightPreset member; if its questions are fixed, add its question keys and one JevPresetDefinition entry here and register every new question in vidbyte/lib/jev/preflight/.
KNOWN EDGE CASES: A bare string is rejected rather than iterated character by character, and enabling the same flag twice is an error because it would ask Jev every question twice. TOOL_SELECTOR is a valid flag with no definition, because it asks one question per configured tool and builds them at run time.
RELATED DOCS: docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.lib.constants.jev import JEV_CLARITY_THRESHOLD
from vidbyte.lib.dataclasses.jev import JevPresetDefinition
from vidbyte.lib.enums.jev import JevPreflightPreset, JevPreflightQuestionKey
from vidbyte.lib.errors import ConfigurationError


class JevPresets:
    """The preflight flags a JevAgent user can enable, with the fixed policy each fixed-question flag turns on."""

    _definitions: Mapping[JevPreflightPreset, JevPresetDefinition] = MappingProxyType(
        {
            JevPreflightPreset.CLARITY: JevPresetDefinition(
                preset=JevPreflightPreset.CLARITY,
                question_keys=(
                    JevPreflightQuestionKey.CLARITY_ACTION,
                    JevPreflightQuestionKey.CLARITY_OBJECT,
                    JevPreflightQuestionKey.CLARITY_DELIVERABLE,
                    JevPreflightQuestionKey.CLARITY_TARGET,
                    JevPreflightQuestionKey.CLARITY_REFERENCES,
                    JevPreflightQuestionKey.CLARITY_SCOPE_PARTS,
                    JevPreflightQuestionKey.CLARITY_SCOPE_SIZE,
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
        """Return the policy a fixed-question flag turns on, or reject a flag with no fixed questions."""
        found = cls._definitions.get(preset)
        if found is None:
            raise ConfigurationError(
                f"Jev preflight preset {preset!r} has no fixed questions in JevPresets.",
                details={"preset": str(preset), "fixed": [item.value for item in cls._definitions]},
            )
        return found

    @classmethod
    def has_fixed_questions(cls, preset: JevPreflightPreset) -> bool:
        """Return True when the flag asks fixed, registered questions instead of questions built per run."""
        return preset in cls._definitions

    @classmethod
    def available(cls) -> tuple[JevPreflightPreset, ...]:
        """Return every flag a user can enable, in declaration order."""
        return tuple(JevPreflightPreset)

    @classmethod
    def resolve(cls, value: object) -> JevPreflightPreset:
        """Convert one user-supplied flag (enum member or its string value) to a preset."""
        try:
            return value if isinstance(value, JevPreflightPreset) else JevPreflightPreset(value)
        except ValueError as exc:
            raise ConfigurationError(
                f"Unsupported Jev preflight preset: {value!r}.",
                details={"received": repr(value), "available": [item.value for item in cls.available()]},
            ) from exc

    @classmethod
    def normalize(cls, values: Iterable[object]) -> tuple[JevPreflightPreset, ...]:
        """Convert the user's enabled flags to a tuple of unique presets, in the order given."""
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
