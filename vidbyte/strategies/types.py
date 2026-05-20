from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class StrategyContext:
    """Per-run context passed through strategies and agents."""

    system_prompt: str | None = None
    agent_name: str | None = None
    role: str | None = None
    history: Sequence[object] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyResult:
    """Normalized result returned by all strategies."""

    output: str
    strategy_name: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
