"""Context Protocol Header

Description:
    Defines the typed data boundary for the environments package: tasks,
    sessions, rewards, rollout records, and calibration reports.
Purpose:
    Gives environments, runners, recorders, and audits one stable set of
    serializable dataclasses so rollout data stays replayable and sellable.
Architecture:
    - EnvTask: Frozen task minted by a TaskGenerator from a seed and knobs.
    - EnvSession: Live materialized world for one rollout attempt.
    - CriterionResult / Reward: Verifier output with partial credit and all-pass.
    - RolloutRecord: Structured record of one verified rollout (JSONL line).
    - CalibrationCell / CalibrationReport: Aggregated pass-rate spec sheet data.
Relations:
    Used by vidbyte.environments.base, runner, records, and audit.
Similar Files:
    - vidbyte/evals/types.py: Equivalent typed boundary for the evals package.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.catalog import Tools

RECORD_VERSION = "1"


@dataclass(frozen=True)
class EnvTask:
    """Single environment task minted by a TaskGenerator from a seed and knobs."""

    id: str
    instructions: str
    params: Mapping[str, Any] = field(default_factory=dict)
    seed: int = 0
    difficulty: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # Returns a JSON-safe dict representation of this task.
        return {
            "id": self.id,
            "instructions": self.instructions,
            "params": dict(self.params),
            "seed": self.seed,
            "difficulty": self.difficulty,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvTask":
        # Rebuilds an EnvTask from a to_dict() payload.
        return cls(
            id=str(payload["id"]),
            instructions=str(payload["instructions"]),
            params=dict(payload.get("params") or {}),
            seed=int(payload.get("seed", 0)),
            difficulty=payload.get("difficulty"),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class EnvSession:
    """Live materialized world for one rollout attempt against an environment."""

    task: EnvTask
    workspace_dir: Path
    tools: Tools = field(default_factory=Tools)
    verifier_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CriterionResult:
    """Outcome of one verifier criterion with pass flag and partial-credit score."""

    name: str
    passed: bool
    score: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        # Returns a JSON-safe dict representation of this criterion result.
        return {"name": self.name, "passed": self.passed, "score": self.score, "detail": self.detail}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CriterionResult":
        # Rebuilds a CriterionResult from a to_dict() payload.
        return cls(
            name=str(payload["name"]),
            passed=bool(payload["passed"]),
            score=float(payload["score"]),
            detail=str(payload.get("detail", "")),
        )


@dataclass(frozen=True)
class Reward:
    """Verifier output carrying the shaped training signal and the all-pass flag."""

    score: float
    passed: bool
    criteria: tuple[CriterionResult, ...] = ()

    @classmethod
    def from_criteria(cls, criteria: Sequence[CriterionResult]) -> "Reward":
        """Build a Reward whose score is the mean criterion score and passed is all-pass."""
        # Empty criteria must never award success: a verifier that checks nothing fails.
        items = tuple(criteria)
        if not items:
            return cls(score=0.0, passed=False, criteria=())
        mean_score = sum(item.score for item in items) / len(items)
        return cls(score=mean_score, passed=all(item.passed for item in items), criteria=items)

    @classmethod
    def failure(cls, detail: str) -> "Reward":
        """Build a zero-score Reward carrying an error detail as its single criterion."""
        criterion = CriterionResult(name="verifier_error", passed=False, score=0.0, detail=detail)
        return cls(score=0.0, passed=False, criteria=(criterion,))

    def to_dict(self) -> dict[str, Any]:
        # Returns a JSON-safe dict representation of this reward.
        return {
            "score": self.score,
            "passed": self.passed,
            "criteria": [criterion.to_dict() for criterion in self.criteria],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Reward":
        # Rebuilds a Reward from a to_dict() payload.
        return cls(
            score=float(payload["score"]),
            passed=bool(payload["passed"]),
            criteria=tuple(CriterionResult.from_dict(item) for item in payload.get("criteria") or ()),
        )


@dataclass(frozen=True)
class RolloutRecord:
    """Structured record of one verified rollout, serialized as one JSONL line."""

    env_name: str
    env_version: str
    task: EnvTask
    harness: Mapping[str, Any]
    trajectory: tuple[Mapping[str, Any], ...]
    reward: Reward
    record_version: str = RECORD_VERSION
    consent: str = "private"
    interruptions: tuple[Mapping[str, Any], ...] = ()
    cost: Mapping[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation of this record."""
        return {
            "record_version": self.record_version,
            "env_name": self.env_name,
            "env_version": self.env_version,
            "task": self.task.to_dict(),
            "harness": dict(self.harness),
            "trajectory": [dict(step) for step in self.trajectory],
            "reward": self.reward.to_dict(),
            "consent": self.consent,
            "interruptions": [dict(item) for item in self.interruptions],
            "cost": dict(self.cost),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RolloutRecord":
        """Rebuild a RolloutRecord from a to_dict() payload, gating on record_version."""
        version = str(payload.get("record_version", ""))
        if version != RECORD_VERSION:
            raise ConfigurationError(
                f"Unsupported rollout record_version {version!r}; this reader supports {RECORD_VERSION!r}."
            )
        return cls(
            record_version=version,
            env_name=str(payload["env_name"]),
            env_version=str(payload["env_version"]),
            task=EnvTask.from_dict(payload["task"]),
            harness=dict(payload.get("harness") or {}),
            trajectory=tuple(dict(step) for step in payload.get("trajectory") or ()),
            reward=Reward.from_dict(payload["reward"]),
            consent=str(payload.get("consent", "private")),
            interruptions=tuple(dict(item) for item in payload.get("interruptions") or ()),
            cost=dict(payload.get("cost") or {}),
            started_at=str(payload.get("started_at", "")),
            finished_at=str(payload.get("finished_at", "")),
            error=payload.get("error"),
        )


@dataclass(frozen=True)
class CalibrationCell:
    """Aggregated rollout outcomes for one harness spec against one environment."""

    spec_name: str
    n_rollouts: int
    pass_rate: float
    mean_score: float
    by_difficulty: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibrationReport:
    """Pass-rate spec sheet across harness specs for one environment version."""

    env_name: str
    env_version: str
    cells: tuple[CalibrationCell, ...]


__all__ = [
    "RECORD_VERSION",
    "CalibrationCell",
    "CalibrationReport",
    "CriterionResult",
    "EnvSession",
    "EnvTask",
    "Reward",
    "RolloutRecord",
]
