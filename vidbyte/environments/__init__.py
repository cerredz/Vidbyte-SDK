"""Context Protocol Header

Description:
    Public package for RL environment abstractions built on Vidbyte SDK
    primitives.
Purpose:
    Exposes the Environment contract, declarative HarnessSpec, rollout runner,
    JSONL recorder, verifier audit kit, and environment registry as one surface.
Architecture:
    - types: EnvTask, EnvSession, Reward, RolloutRecord, calibration types.
    - base: Environment ABC, TaskGenerator protocol, StaticTaskSet.
    - grading: evals-grader adapter (criterion_from_grade, grade_with).
    - spec: HarnessSpec and its sub-specs (name dispatch tables live in
      vidbyte.lib.config.harness_tables).
    - resolver: HarnessSpecResolver building live BaseAgents from specs.
    - runner / records: Rollout execution and JSONL persistence.
    - audit / registry / client: Verifier audits, name registry, namespace client.
Relations:
    Re-exported by vidbyte.__init__; namespace client attached to VidbyteSDK.
"""

from __future__ import annotations

from vidbyte.environments.audit import AuditReport, DoNothingPolicy, EchoPolicy, EnvironmentAudit
from vidbyte.environments.base import Environment, StaticTaskSet, TaskGenerator
from vidbyte.environments.client import EnvironmentsClient
from vidbyte.environments.grading import criterion_from_grade, grade_with
from vidbyte.environments.records import RolloutRecorder
from vidbyte.environments.registry import EnvironmentRegistry
from vidbyte.environments.resolver import HarnessSpecResolver
from vidbyte.environments.runner import EnvironmentRunner
from vidbyte.environments.spec import (
    ContextAlgorithmSpec,
    ContextPrimitiveSpec,
    HarnessSpec,
    HarnessToolSpec,
    LoopSpec,
    MiddlewareSpec,
    ModelSpec,
    RuntimeSpec,
    TraceSpec,
)
from vidbyte.environments.types import (
    CalibrationCell,
    CalibrationReport,
    CriterionResult,
    EnvSession,
    EnvTask,
    Reward,
    RolloutRecord,
)

__all__ = [
    "AuditReport",
    "CalibrationCell",
    "CalibrationReport",
    "ContextAlgorithmSpec",
    "ContextPrimitiveSpec",
    "CriterionResult",
    "DoNothingPolicy",
    "criterion_from_grade",
    "grade_with",
    "EchoPolicy",
    "EnvSession",
    "EnvTask",
    "Environment",
    "EnvironmentAudit",
    "EnvironmentRegistry",
    "EnvironmentRunner",
    "EnvironmentsClient",
    "HarnessSpec",
    "HarnessSpecResolver",
    "HarnessToolSpec",
    "LoopSpec",
    "MiddlewareSpec",
    "ModelSpec",
    "Reward",
    "RolloutRecord",
    "RolloutRecorder",
    "RuntimeSpec",
    "StaticTaskSet",
    "TaskGenerator",
    "TraceSpec",
]
