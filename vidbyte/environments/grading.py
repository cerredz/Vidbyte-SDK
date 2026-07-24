"""Context Protocol Header

Description:
    Adapter that lets an Environment verifier reuse the vidbyte.evals grader
    catalog (contains, regex, json_schema, rubric, llm_judge, composite, ...)
    to score a rollout.
Purpose:
    The evals package already implements battle-tested graders over strings;
    environments grade world state. This bridge turns any BaseGrader's
    GraderResult into a CriterionResult and folds a set of them into a Reward,
    so authors do not reimplement grading logic inside verify().
Architecture:
    - criterion_from_grade: One GraderResult -> one CriterionResult.
    - grade_with: Run a sequence of graders over one string, fold into a Reward.
Relations:
    Consumes vidbyte.evals.base.BaseGrader and vidbyte.evals.types; produces
    vidbyte.environments.types.Reward for Environment.verify().
Similar Files:
    - vidbyte/evals/runner.py: Runs graders over prompt->reply eval cases.

Design note — what string do you grade?
    evals graders score a string; environments grade final world state. The
    author chooses what string to hand a grader: the agent's final output for
    output-shaped criteria, or the contents of a file read out of
    session.workspace_dir for state-shaped criteria. Checks with no string at
    all (a file exists, tests exit 0, a checksum matches) stay as hand-written
    CriterionResults -- this adapter complements state grading, it does not
    replace it. Graders belong to the Environment (the verifier), never to the
    swept HarnessSpec: grading with a config you are also sweeping makes pass
    rates uninterpretable.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.environments.types import CriterionResult, Reward
from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


def criterion_from_grade(grader_name: str, result: GraderResult) -> CriterionResult:
    """Adapt one evals GraderResult into an environments CriterionResult."""
    # GraderResult carries (score, passed, reason); CriterionResult names it and
    # renames reason -> detail so the reward records which check spoke.
    return CriterionResult(
        name=grader_name,
        passed=result.passed,
        score=result.score,
        detail=result.reason,
    )


async def grade_with(graders: Sequence[BaseGrader], case: EvalCase, actual: str) -> Reward:
    """Run evals graders over one string and fold their results into a Reward.

    Each grader becomes one criterion named by its ``grader.name``. The fold
    reuses ``Reward.from_criteria``: overall ``passed`` is all-pass across
    graders and ``score`` is their mean, so an empty grader sequence fails
    rather than awarding free reward.
    """
    criteria = [criterion_from_grade(grader.name, await grader.agrade(case, actual)) for grader in graders]
    return Reward.from_criteria(criteria)


__all__ = [
    "criterion_from_grade",
    "grade_with",
]
