"""Context Protocol Header

Description:
    Declares root level exports for the Vidbyte SDK evaluation module.
Purpose:
    Exposes clean public interfaces for runners, data cases, SQLite registries, and all prebuilt graders.
Architecture:
    Consolidates submodules (types, base, suite, runner, registry, client, graders)
    under the unified vidbyte.evals namespace.
Relations:
    Imported by vidbyte to expose evaluation hooks on the root VidbyteSDK client.
"""

from __future__ import annotations

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.behavior import Behavior, RunProbe
from vidbyte.evals.client import EvalClient
from vidbyte.evals.graders import (
    ContainsGrader,
    ExactMatchGrader,
    JSONSchemaGrader,
    LLMJudgeGrader,
    PredicateGrader,
    RegexMatchGrader,
    RubricGrader,
)
from vidbyte.evals.registry import ComparisonReport, EvalRegistry
from vidbyte.evals.runner import EvalRunner
from vidbyte.evals.suite import EvalSuite
from vidbyte.evals.types import EvalCase, EvalResult, EvalSuiteResult, GraderResult

__all__ = [
    "BaseGrader",
    "Behavior",
    "ComparisonReport",
    "ContainsGrader",
    "EvalCase",
    "EvalClient",
    "EvalRegistry",
    "EvalResult",
    "EvalRunner",
    "EvalSuite",
    "EvalSuiteResult",
    "ExactMatchGrader",
    "GraderResult",
    "JSONSchemaGrader",
    "LLMJudgeGrader",
    "PredicateGrader",
    "RegexMatchGrader",
    "RunProbe",
    "RubricGrader",
]
