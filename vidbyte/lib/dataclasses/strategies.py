from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Normalized result returned by agent execution."""

    output: str
    strategy_name: str
    calls: tuple[Any, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    structured: Any = None


StrategyResult = AgentResult
