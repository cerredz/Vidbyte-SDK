"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/_parsing.py
PURPOSE: Normalizes the raw model arguments shared by the ten hand-maintained reasoning strategy tools.
ROLE IN CODEBASE: Named reasoning tools call ReasoningToolInput for required fields, text, JSON collections, and bounded probabilities.
ARCHITECTURE NOTE: The static helper class centralizes coercion without owning ToolSpecs, context-item construction, or ContextManager placement.
COMMON MODIFICATION PATTERNS: Add a parser only for repeated input shapes and preserve each caller's existing validation/error contract.
KNOWN EDGE CASES: JSON strings may decode to the wrong shape, mappings are not arrays, blank values are removed, and booleans are not probabilities.
RELATED DOCS: field-guide/vidbyte-sdk/class-bound-helpers.md and vidbyte/tools/README.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

Description:
    Implements ReasoningToolInput — a package-private static helper class that
    normalizes and validates the raw ToolCall.arguments shared across every
    reasoning-strategy tool.
Purpose:
    Centralizes the four argument-handling concerns that repeat across the 10
    reasoning-strategy tool files (required-field checking, JSON string-list
    parsing, JSON object-list parsing, and 0.0-1.0 probability parsing) on one
    class instead of duplicating them per file.
Architecture:
    - ReasoningToolInput: Static-method-only helper, never instantiated.
Relations:
    Used by every module in vidbyte.tools.builtins.reasoning. Not re-exported
    from vidbyte.tools.builtins.reasoning.__init__ — package-private.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

_MAX_PROBABILITY = 1.0
_MIN_PROBABILITY = 0.0


class ReasoningToolInput:
    """Static helpers for normalizing model-supplied reasoning-tool arguments."""

    @staticmethod
    def missing_required(args: Mapping[str, Any], names: tuple[str, ...]) -> str | None:
        """Return an error string naming the first missing or empty required field, or None."""
        for name in names:
            value = args.get(name)
            if not value or not str(value).strip():
                return f"Missing or empty required field: '{name}'."
        return None

    @staticmethod
    def text(args: Mapping[str, Any], key: str, default: str = "") -> str:
        """Return the stripped string value of args[key], or default if absent."""
        raw = args.get(key, default)
        return str(raw).strip() if raw is not None else default

    @staticmethod
    def string_list(raw: Any) -> tuple[str, ...]:
        """Coerce a JSON array, JSON string, or single value into a tuple of non-empty strings."""
        if raw is None:
            return ()
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                stripped = raw.strip()
                return (stripped,) if stripped else ()
            raw = parsed
        if isinstance(raw, Mapping):
            return ()
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            return tuple(str(item).strip() for item in raw if str(item).strip())
        return ()

    @staticmethod
    def object_list(raw: Any) -> tuple[Mapping[str, Any], ...]:
        """Coerce a JSON array of objects, a JSON string, or a single object into a tuple of mappings."""
        if raw is None:
            return ()
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return ()
            raw = parsed
        if isinstance(raw, Mapping):
            return (raw,)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            return tuple(item for item in raw if isinstance(item, Mapping))
        return ()

    @staticmethod
    def probability(raw: Any) -> float | None:
        """Parse a string/number to a float clamped to [0.0, 1.0], or None on failure."""
        if raw is None or str(raw).strip() == "":
            return None
        try:
            value = float(str(raw).strip())
        except (ValueError, TypeError):
            return None
        return max(_MIN_PROBABILITY, min(_MAX_PROBABILITY, value))

    @staticmethod
    def enum_error(value: str, allowed: tuple[str, ...], field_name: str) -> str | None:
        """Return an error string if value is not one of allowed, else None."""
        if value in allowed:
            return None
        return f"Unknown {field_name} '{value}'. Supported: {', '.join(allowed)}."


__all__: list[str] = []
