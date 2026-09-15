"""FILE: vidbyte/lib/text.py

PURPOSE: Provides bounded text operations shared by source integrations.
ROLE IN CODEBASE: Clips decoded provider output by UTF-8 bytes without splitting a code point.
ARCHITECTURE NOTE: TextClipper owns the helper state and policy; callers do not duplicate byte arithmetic.
COMMON MODIFICATION PATTERNS: Change the marker or clipping policy here and update integration tests together.
KNOWN EDGE CASES: Small ceilings may contain only part of the marker, and malformed input types are rejected.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

from typing import Final

from vidbyte.lib.constants.integrations import SOURCES_TRUNCATION_MARKER


class TextClipper:
    """Clips text to a UTF-8 byte ceiling with an explicit marker."""

    MARKER: Final[str] = SOURCES_TRUNCATION_MARKER

    @classmethod
    def clip(cls, text: str, max_bytes: int) -> str:
        """Return text within max_bytes, preserving complete UTF-8 code points."""
        if not isinstance(text, str):
            raise TypeError("TextClipper.clip expects text to be a string.")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0:
            raise ValueError("TextClipper.clip expects a nonnegative integer byte limit.")
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text
        marker_bytes = cls.MARKER.encode("utf-8")
        if max_bytes <= len(marker_bytes):
            return marker_bytes[:max_bytes].decode("utf-8", errors="ignore")
        room = max_bytes - len(marker_bytes)
        prefix = encoded[:room].decode("utf-8", errors="ignore")
        return f"{prefix}{cls.MARKER}"


__all__ = ["TextClipper"]
