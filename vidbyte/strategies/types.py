from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class StrategyResult:
    """Minimal normalized strategy result."""

    output: str
    strategy_name: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

