"""Context Protocol Header

Description:
    Defines internal data contracts for code-search tooling.
Purpose:
    Keeps code-search dataclasses in the shared dataclass namespace while
    allowing built-in tools to keep behavior in their package.
Architecture:
    - _CodeChunk: Internal indexed text chunk for semantic-style search.
Relations:
    Related to vidbyte.tools.builtins.code_search.semantic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _CodeChunk:
    """Internal representation of an indexed code chunk."""

    path: str
    start_line: int
    end_line: int
    text: str
    vector: tuple[float, ...] = ()
