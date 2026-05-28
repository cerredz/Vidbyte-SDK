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
from vidbyte.evals.client import EvalClient
from vidbyte.evals.graders import (
    ContainsGrader,
    ExactMatchGrader,
    JSONSchemaGrader,
    LLMJudgeGrader,
    RegexMatchGrader,
    RubricGrader,
)
from vidbyte.evals.llm_as_a_judge import (
    AtomicClaimsJudge,
    BinaryJudge,
    BranchSolveMergeJudge,
    ChainOfAspectsJudge,
    ChainOfThoughtJudge,
    ConstitutionalJudge,
    CriteriaDecompositionJudge,
    FewShotJudge,
    LLMRubricJudge,
    MetaJudge,
    MixtureOfPromptsJudge,
    MultiAgentDebateJudge,
    MultiAgentRubricJudge,
    PairwiseJudge,
    PanelJudge,
    PeerReviewJudge,
    SelfEvalJudge,
    SelfReferenceJudge,
    StructuredRubricJudge,
)
from vidbyte.evals.registry import ComparisonReport, EvalRegistry
from vidbyte.evals.runner import EvalRunner
from vidbyte.evals.suite import EvalSuite
from vidbyte.evals.types import EvalCase, EvalResult, EvalSuiteResult, GraderResult

__all__ = [
    "AtomicClaimsJudge",
    "BaseGrader",
    "BinaryJudge",
    "BranchSolveMergeJudge",
    "ChainOfAspectsJudge",
    "ChainOfThoughtJudge",
    "ComparisonReport",
    "ConstitutionalJudge",
    "ContainsGrader",
    "CriteriaDecompositionJudge",
    "EvalCase",
    "EvalClient",
    "EvalRegistry",
    "EvalResult",
    "EvalRunner",
    "EvalSuite",
    "EvalSuiteResult",
    "ExactMatchGrader",
    "FewShotJudge",
    "GraderResult",
    "JSONSchemaGrader",
    "LLMJudgeGrader",
    "LLMRubricJudge",
    "MetaJudge",
    "MixtureOfPromptsJudge",
    "MultiAgentDebateJudge",
    "MultiAgentRubricJudge",
    "PairwiseJudge",
    "PanelJudge",
    "PeerReviewJudge",
    "RegexMatchGrader",
    "RubricGrader",
    "SelfEvalJudge",
    "SelfReferenceJudge",
    "StructuredRubricJudge",
]
