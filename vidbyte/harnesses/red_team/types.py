from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import HarnessConfigurationError
from vidbyte.shared import ArtifactRevision, FilteredContextView, LedgerEntry, ModelFunction


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True, slots=True)
class HarnessPipeline:
    """One execution pipeline in the adversarial harness."""

    name: str
    model_fn: ModelFunction
    tools: tuple[object, ...] = ()
    strategy: object | None = None
    prompt_key: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise HarnessConfigurationError("pipeline name must not be empty")
        if not callable(self.model_fn):
            raise HarnessConfigurationError("pipeline model_fn must be callable")


@dataclass(frozen=True, slots=True)
class RedTeamHarnessConfig:
    """Configuration for adversarial coordination and termination."""

    max_rounds: int = 5
    max_steps: int | None = None
    consecutive_clean_attacks_for_win: int = 3
    fatal_severity_threshold: float = 1.0
    warning_severity_threshold: float = 0.25
    return_best_on_exhaustion: bool = True

    def __post_init__(self) -> None:
        if self.max_rounds <= 0:
            raise HarnessConfigurationError("max_rounds must be greater than zero")
        if self.max_steps is not None and self.max_steps <= 0:
            raise HarnessConfigurationError("max_steps must be greater than zero when provided")
        if self.consecutive_clean_attacks_for_win <= 0:
            raise HarnessConfigurationError("consecutive_clean_attacks_for_win must be greater than zero")
        if not 0.0 <= self.fatal_severity_threshold <= 1.0:
            raise HarnessConfigurationError("fatal_severity_threshold must be between 0.0 and 1.0")
        if not 0.0 <= self.warning_severity_threshold <= 1.0:
            raise HarnessConfigurationError("warning_severity_threshold must be between 0.0 and 1.0")


@dataclass(frozen=True, slots=True)
class AttackFinding:
    """A red-team finding against the current artifact."""

    payload: str
    severity: float
    category: str
    description: str
    fatal: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", _clamp_score(float(self.severity)))


@dataclass(frozen=True, slots=True)
class ResilienceScore:
    """Round-level resilience score."""

    exploit_severity: float
    defensive_adaptability: float
    equilibrium: float
    consecutive_clean_attacks: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "exploit_severity", _clamp_score(float(self.exploit_severity)))
        object.__setattr__(self, "defensive_adaptability", _clamp_score(float(self.defensive_adaptability)))
        object.__setattr__(self, "equilibrium", _clamp_score(float(self.equilibrium)))


@dataclass(slots=True)
class RedTeamChallengeState:
    """Mutable state for one adversarial harness run."""

    original_prompt: str
    master_ledger: list[LedgerEntry]
    blue_view: FilteredContextView
    red_view: FilteredContextView
    artifacts: list[ArtifactRevision]
    findings: list[AttackFinding]
    scores: list[ResilienceScore]
    round_index: int = 0
    step_index: int = 0


@dataclass(frozen=True, slots=True)
class RedTeamChallengeResult:
    """Terminal result for defensive wins or exhausted runs."""

    outcome: str
    artifact: ArtifactRevision
    score: ResilienceScore
    rounds: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


__all__ = [
    "AttackFinding",
    "HarnessPipeline",
    "RedTeamChallengeResult",
    "RedTeamChallengeState",
    "RedTeamHarnessConfig",
    "ResilienceScore",
]
