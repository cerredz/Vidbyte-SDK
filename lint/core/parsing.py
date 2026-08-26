"""FILE: lint/core/parsing.py

PURPOSE:
    Gives every AST-based lint rule one shared, safe way to turn a file path
    into a parsed module, so each rule module does not reimplement
    read-decode-parse-and-swallow-syntax-errors independently.
ROLE IN CODEBASE:
    Called by every rule under lint/rules/ whose ruff_selectors is empty
    (a pure-AST rule): c001-c005 as of docs/design/sdk-lint-contract-rules.md.
ARCHITECTURE NOTE:
    A file that fails to parse is already S001's own E9 finding (Ruff's
    parser/runtime selector). An AST rule silently skipping it on a None
    return avoids a duplicate, less-informative report and avoids crashing
    the whole rule over one bad file.
RELATED DOCS:
    docs/design/sdk-lint-contract-rules.md
"""

from __future__ import annotations

import ast
from pathlib import Path


class PythonSourceParser:
    """Safely turns a file path into a parsed ast.Module, or None."""

    @staticmethod
    def parse(path: Path) -> ast.Module | None:
        # Reads path as UTF-8 (BOM-tolerant) and parses it; returns None, never raises, on failure.
        try:
            text = path.read_text(encoding="utf-8-sig")
            return ast.parse(text, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            return None


__all__ = ["PythonSourceParser"]
