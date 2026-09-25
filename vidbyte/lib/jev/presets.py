"""FILE: vidbyte/lib/jev/presets.py

PURPOSE: Owns the preflight presets a caller can enable on JevAgent and the validation of each preset's own setting.
ROLE IN CODEBASE: JevAgentSettings calls JevPresets to normalize `preflight` and `security_action`; JevRuntime reads the normalized values.
ARCHITECTURE NOTE: Callers choose named presets from JevPreflightPreset; question text and decision policy stay in `vidbyte/lib/jev/preflight/` and the agents-layer preflight classes.
COMMON MODIFICATION PATTERNS: Add a JevPreflightPreset member, then add a normalize_<setting> method here for any setting that preset owns.
KNOWN EDGE CASES: String names are accepted for every enum; duplicates and bare strings are rejected so `preflight="security"` cannot become nine one-letter presets.
RELATED DOCS: docs/design/jev-tool-selector.md, docs/design/jev-preflight-sensitive-data.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_tool_selector.py and tests/test_jev_sensitive_preflight.py.
"""

from __future__ import annotations

from collections.abc import Iterable

from vidbyte.lib.enums.jev import JevPreflightPreset, JevSecurityAction
from vidbyte.lib.errors import ConfigurationError


class JevPresets:
    """Normalizes the preflight presets and preset settings a caller passes to JevAgentSettings."""

    @staticmethod
    def normalize(values: object) -> tuple[JevPreflightPreset, ...]:
        """Return the enabled presets as enum members in caller order, rejecting unknown or repeated names."""
        if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
            raise ConfigurationError("JevAgentSettings.preflight must be an iterable of JevPreflightPreset values, not a string.")
        try:
            normalized = tuple(value if isinstance(value, JevPreflightPreset) else JevPreflightPreset(value) for value in values)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                "JevAgentSettings.preflight contains an unsupported preset.",
                details={"supported": [preset.value for preset in JevPreflightPreset]},
            ) from exc
        if len(set(normalized)) != len(normalized):
            raise ConfigurationError("JevAgentSettings.preflight cannot contain duplicate presets.")
        return normalized

    @staticmethod
    def normalize_security_action(value: object) -> JevSecurityAction:
        """Return the security action as an enum member, accepting its string value."""
        if isinstance(value, JevSecurityAction):
            return value
        try:
            if isinstance(value, str):
                return JevSecurityAction(value)
        except ValueError as exc:
            raise ConfigurationError(
                "JevAgentSettings.security_action must be 'block', 'pause', 'report', or 'contain'.",
                details={"received": repr(value)},
            ) from exc
        raise ConfigurationError(
            "JevAgentSettings.security_action must be a JevSecurityAction or its string value.",
            details={"received": repr(value)},
        )


__all__ = ["JevPresets"]
