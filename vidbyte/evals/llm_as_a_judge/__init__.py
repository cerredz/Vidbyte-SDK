"""Context Protocol Header

Description:
    Exports all 19 LLM-as-a-judge strategy grader classes.
Purpose:
    Provides a single importable namespace for the full strategy library so developers
    can do: from vidbyte.evals.llm_as_a_judge import ChainOfThoughtJudge
Architecture:
    Re-exports from each strategy module; shared utilities in _utils.py are internal.
Relations:
    Imported by vidbyte.evals and vidbyte top-level namespaces.
"""

from __future__ import annotations

from vidbyte.evals.llm_as_a_judge.atomic_claims import AtomicClaimsJudge
from vidbyte.evals.llm_as_a_judge.binary import BinaryJudge
from vidbyte.evals.llm_as_a_judge.branch_solve_merge import BranchSolveMergeJudge
from vidbyte.evals.llm_as_a_judge.chain_of_aspects import ChainOfAspectsJudge
from vidbyte.evals.llm_as_a_judge.chain_of_thought import ChainOfThoughtJudge
from vidbyte.evals.llm_as_a_judge.constitutional import ConstitutionalJudge
from vidbyte.evals.llm_as_a_judge.criteria_decomposition import CriteriaDecompositionJudge
from vidbyte.evals.llm_as_a_judge.few_shot import FewShotJudge
from vidbyte.evals.llm_as_a_judge.llm_rubric import LLMRubricJudge
from vidbyte.evals.llm_as_a_judge.meta_judge import MetaJudge
from vidbyte.evals.llm_as_a_judge.mixture_of_prompts import MixtureOfPromptsJudge
from vidbyte.evals.llm_as_a_judge.multi_agent_debate import MultiAgentDebateJudge
from vidbyte.evals.llm_as_a_judge.multi_agent_rubrics import MultiAgentRubricJudge
from vidbyte.evals.llm_as_a_judge.pairwise import PairwiseJudge
from vidbyte.evals.llm_as_a_judge.panel import PanelJudge
from vidbyte.evals.llm_as_a_judge.peer_review import PeerReviewJudge
from vidbyte.evals.llm_as_a_judge.self_eval import SelfEvalJudge
from vidbyte.evals.llm_as_a_judge.self_reference import SelfReferenceJudge
from vidbyte.evals.llm_as_a_judge.structured_rubric import StructuredRubricJudge

__all__ = [
    "AtomicClaimsJudge",
    "BinaryJudge",
    "BranchSolveMergeJudge",
    "ChainOfAspectsJudge",
    "ChainOfThoughtJudge",
    "ConstitutionalJudge",
    "CriteriaDecompositionJudge",
    "FewShotJudge",
    "LLMRubricJudge",
    "MetaJudge",
    "MixtureOfPromptsJudge",
    "MultiAgentDebateJudge",
    "MultiAgentRubricJudge",
    "PairwiseJudge",
    "PanelJudge",
    "PeerReviewJudge",
    "SelfEvalJudge",
    "SelfReferenceJudge",
    "StructuredRubricJudge",
]
