from __future__ import annotations

from vidbyte.strategies.codeact import CodeActStrategy
from vidbyte.strategies.react import ReActStrategy


class StrategyClient:
    """Namespace client for strategy constructors."""

    def react(self) -> ReActStrategy:
        return ReActStrategy()

    def codeact(self) -> CodeActStrategy:
        return CodeActStrategy()

