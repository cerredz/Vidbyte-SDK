"""FILE: vidbyte/lib/tools/filesystem/newlines.py

PURPOSE: Detects the newline style (CRLF or LF) a text file already uses, splits text into lines at "\\n" only, and diffs two texts by those lines.
ROLE IN CODEBASE: Lets in-place edit tools (PatchTool, ReplaceTextTool) write a file back with its own line endings instead of the platform default, and gives PatchTool and LocalFileSystemBackend.diff_text one diff format.
ARCHITECTURE NOTE: Pure string helper in the lib layer; callers read the raw text and pass the result as open(..., newline=...).
FUNCTION INVENTORY: LineEndings.detect() returns "\\r\\n" or "\\n". LineEndings.split_lines() splits after each "\\n", keeping it. LineEndings.unified_diff() returns a unified diff with git's no-newline marker.
COMMON MODIFICATION PATTERNS: Change the detection rule here only and keep both edit tools using it.
WHAT NOT TO DO: Do not pass universal-newline-translated text; it never contains CRLF.
KNOWN EDGE CASES: Mixed-ending files are treated as CRLF when any CRLF is present; old-Mac lone CR is treated as LF.
RELATED DOCS: docs/design/preserve-line-endings-on-edit.md
TESTS: tests/test_patch_tool.py and tests/test_filesystem_tools.py line-ending regression tests.
"""

from __future__ import annotations

import difflib
import re


class LineEndings:
    """Detects the newline style a text file already uses so in-place edits can keep it."""

    CRLF = "\r\n"
    LF = "\n"

    @staticmethod
    def detect(raw_text: str) -> str:
        """Return CRLF when the untranslated text contains any CRLF, otherwise LF."""
        return LineEndings.CRLF if LineEndings.CRLF in raw_text else LineEndings.LF

    @staticmethod
    def split_lines(text: str) -> list[str]:
        """Split text after each "\\n", keeping it; a last line without one still counts, and "" has no lines."""
        # Unlike str.splitlines(), a form feed, vertical tab, U+2028 or
        # other line separator stays inside its line, as it does on disk.
        return [line for line in re.split(r"(?<=\n)", text) if line]

    @staticmethod
    def unified_diff(before: str, after: str, *, fromfile: str, tofile: str) -> str:
        """Return a unified diff of two texts split at "\\n" only; "" when they have no line-level change."""
        lines = difflib.unified_diff(LineEndings.split_lines(before), LineEndings.split_lines(after), fromfile=fromfile, tofile=tofile)
        # A last line with no newline gets git's marker, so the next
        # diff line does not run onto the end of it.
        return "".join(line if line.endswith("\n") else f"{line}\n\\ No newline at end of file\n" for line in lines)


__all__ = [
    "LineEndings",
]
