"""FILE: vidbyte/lib/tools/filesystem/newlines.py

PURPOSE: Detects the newline style (CRLF or LF) a text file already uses.
ROLE IN CODEBASE: Lets in-place edit tools (PatchTool, ReplaceTextTool) write a file back with its own line endings instead of the platform default.
ARCHITECTURE NOTE: Pure string helper in the lib layer; callers read the raw text and pass the result as open(..., newline=...).
FUNCTION INVENTORY: LineEndings.detect() returns "\\r\\n" or "\\n".
COMMON MODIFICATION PATTERNS: Change the detection rule here only and keep both edit tools using it.
WHAT NOT TO DO: Do not pass universal-newline-translated text; it never contains CRLF.
KNOWN EDGE CASES: Mixed-ending files are treated as CRLF when any CRLF is present; old-Mac lone CR is treated as LF.
RELATED DOCS: docs/design/preserve-line-endings-on-edit.md
TESTS: tests/test_patch_tool.py and tests/test_filesystem_tools.py line-ending regression tests.
"""

from __future__ import annotations


class LineEndings:
    """Detects the newline style a text file already uses so in-place edits can keep it."""

    CRLF = "\r\n"
    LF = "\n"

    @staticmethod
    def detect(raw_text: str) -> str:
        """Return CRLF when the untranslated text contains any CRLF, otherwise LF."""
        return LineEndings.CRLF if LineEndings.CRLF in raw_text else LineEndings.LF


__all__ = [
    "LineEndings",
]
