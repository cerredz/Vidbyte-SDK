from __future__ import annotations

from typing import ClassVar

from vidbyte.strategies.react import ReActStrategy


class CodeActStrategy(ReActStrategy):
    """Placeholder tool-aware CodeAct strategy sharing the same tool plumbing."""

    name: ClassVar[str] = "codeact"

