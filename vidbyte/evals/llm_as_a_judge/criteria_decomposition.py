"""Context Protocol Header

Description:
    Implements the Criteria Decomposition LLM judge (CriteriaDecompositionJudge).
Purpose:
    Two-call strategy: first expands a vague criterion into specific sub-questions,
    then evaluates the response against that checklist. Reduces inter-run variance.
Architecture:
    - CriteriaDecompositionJudge: Inherits BaseGrader; runs decomposition call,
      injects checklist into eval call, parses JSON score.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_DEFAULT_DECOMPOSE_TEMPLATE = (
    "You are a careful evaluator. Break the following evaluation criterion into exactly "
    "{num_sub_criteria} specific, non-overlapping sub-questions that can each be answered yes or no.\n\n"
    "Criterion: {criterion}\n\n"
    "Output a numbered list of sub-questions only. No other text."
)

_DEFAULT_EVAL_TEMPLATE = (
    "You are an objective judge. Evaluate a model's response by reasoning through each "
    "sub-question below, then produce a final score.\n\n"
    "Sub-questions:\n{checklist}\n\n"
    "Output only a valid JSON object:\n"
    "{{\"score\": float, \"passed\": boolean, \"reason\": \"brief explanation referencing the sub-questions\"}}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}"
)


class CriteriaDecompositionJudge(BaseGrader):
    """Judge that decomposes a criterion into a checklist before running evaluation."""

    name: ClassVar[str] = "criteria_decomposition"

    def __init__(self, *, judge_runner: object, criterion: str, num_sub_criteria: int = 4, system_prompt: str | None = None, decomposition_prompt_template: str | None = None, eval_prompt_template: str | None = None) -> None:
        # Stores criterion, sub-criteria count, runner, and optional template overrides.
        self.judge_runner = judge_runner
        self.criterion = criterion
        self.num_sub_criteria = num_sub_criteria
        self.system_prompt = system_prompt
        self.decomposition_prompt_template = decomposition_prompt_template
        self.eval_prompt_template = eval_prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Decomposes criterion into checklist, then evaluates response against checklist.
        checklist = await self._decompose_criterion()
        eval_template = self._resolve_eval_template()
        eval_prompt = eval_template.format(
            checklist=checklist,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, eval_prompt)
        return self._parse_response(raw)

    def _resolve_decompose_template(self) -> str:
        # Returns user-supplied decomposition template, SDK catalog prompt, or inline default.
        if self.decomposition_prompt_template:
            return self.decomposition_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_CRITERIA_DECOMPOSITION_DECOMPOSE)
        except Exception:
            return _DEFAULT_DECOMPOSE_TEMPLATE

    def _resolve_eval_template(self) -> str:
        # Returns user-supplied eval template, SDK catalog prompt, or inline default.
        if self.eval_prompt_template:
            return self.eval_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_CRITERIA_DECOMPOSITION_EVAL)
        except Exception:
            return _DEFAULT_EVAL_TEMPLATE

    async def _decompose_criterion(self) -> str:
        # Calls the judge to expand self.criterion into a numbered sub-question checklist.
        template = self._resolve_decompose_template()
        decompose_prompt = template.format(criterion=self.criterion, num_sub_criteria=self.num_sub_criteria)
        return await invoke_runner(self.judge_runner, decompose_prompt)

    def _parse_response(self, text: str) -> GraderResult:
        # Parses JSON score/passed/reason from the evaluation response.
        try:
            parsed = parse_json_block(text)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            passed = bool(parsed.get("passed", score >= 0.7))
            reason = str(parsed.get("reason", "Evaluated by criteria decomposition judge."))
            return GraderResult(score=score, passed=passed, reason=reason)
        except ValueError:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse criteria decomposition response: {text[:200]}")
