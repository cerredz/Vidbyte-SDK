"""Context Protocol Header

Description:
    Declares root level exports for the Vidbyte SDK evaluation module.
Purpose:
    Exposes clean public interfaces for runners, data cases, SQLite registries, prebuilt graders, and templates.
Architecture:
    Consolidates submodules (types, base, suite, runner, registry, client, graders)
    under the unified vidbyte.evals namespace.
Relations:
    Imported by vidbyte to expose evaluation hooks on the root VidbyteSDK client.
"""

from __future__ import annotations

from vidbyte.evals import templates
from vidbyte.evals.base import BaseGrader
from vidbyte.evals.behavior import Behavior, RunProbe
from vidbyte.evals.client import EvalClient
from vidbyte.evals.graders import (
    AllOfGrader,
    AnyOfGrader,
    ChoiceMatchGrader,
    ContainsAllGrader,
    ContainsGrader,
    ExactMatchGrader,
    ForbiddenContentGrader,
    JSONExactMatchGrader,
    JSONSchemaGrader,
    JSONSubsetGrader,
    LengthGrader,
    LLMJudgeGrader,
    NumericMatchGrader,
    PredicateGrader,
    RegexMatchGrader,
    RubricGrader,
    WeightedGrader,
)
from vidbyte.evals.registry import ComparisonReport, EvalRegistry
from vidbyte.evals.runner import EvalRunner
from vidbyte.evals.suite import EvalSuite
from vidbyte.evals.templates import (
    ClassificationTemplate,
    ConciseGroundedAnswerTemplate,
    EvalTemplate,
    EvalTemplateRegistry,
    MultipleChoiceTemplate,
    NumericAnswerTemplate,
    SafeCustomerSupportTemplate,
    ShortAnswerFactTemplate,
    StructuredJsonTemplate,
)
from vidbyte.evals.types import EvalCase, EvalResult, EvalSuiteResult, GraderResult

__all__ = [
    "AllOfGrader",
    "AnyOfGrader",
    "BaseGrader",
    "Behavior",
    "ChoiceMatchGrader",
    "ClassificationTemplate",
    "ComparisonReport",
    "ConciseGroundedAnswerTemplate",
    "ContainsAllGrader",
    "ContainsGrader",
    "EvalCase",
    "EvalClient",
    "EvalRegistry",
    "EvalResult",
    "EvalRunner",
    "EvalSuite",
    "EvalSuiteResult",
    "EvalTemplate",
    "EvalTemplateRegistry",
    "ExactMatchGrader",
    "ForbiddenContentGrader",
    "GraderResult",
    "JSONExactMatchGrader",
    "JSONSchemaGrader",
    "JSONSubsetGrader",
    "LengthGrader",
    "LLMJudgeGrader",
    "MultipleChoiceTemplate",
    "NumericAnswerTemplate",
    "NumericMatchGrader",
    "PredicateGrader",
    "RegexMatchGrader",
    "RunProbe",
    "RubricGrader",
    "SafeCustomerSupportTemplate",
    "ShortAnswerFactTemplate",
    "StructuredJsonTemplate",
    "WeightedGrader",
    "templates",
]
