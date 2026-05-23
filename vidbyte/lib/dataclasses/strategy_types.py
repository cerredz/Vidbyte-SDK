from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vidbyte.lib.runners.types import TextModelResponse


@dataclass(frozen=True, slots=True)
class StrategyResult:
    """Normalized result returned by prompt/API strategies."""

    output: str
    strategy_name: str
    calls: tuple[TextModelResponse, ...]
    metadata: Mapping[str, Any]


__all__ = [
    "StrategyResult",
]
