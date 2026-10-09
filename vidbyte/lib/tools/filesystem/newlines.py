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
