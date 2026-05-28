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
from vidbyte.lib.dataclasses.llm_judge import CriteriaDecompositionJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class CriteriaDecompositionJudge(BaseGrader):
    """Judge that decomposes a criterion into a checklist before running evaluation."""

    name: ClassVar[str] = "criteria_decomposition"

    def __init__(self, config: CriteriaDecompositionJudgeConfig) -> None:
        # Unpacks config fields for criterion, sub-criteria count, runner, and template overrides.
        self.judge_runner = config.judge_runner
        self.criterion = config.criterion
        self.num_sub_criteria = config.num_sub_criteria
        self.system_prompt = config.system_prompt
        self.decomposition_prompt_template = config.decomposition_prompt_template
        self.eval_prompt_template = config.eval_prompt_template

    def _resolve_template(self, slot: str, override: str | None, prompt_key: Prompt) -> str:
        # Returns override, SDK catalog prompt, or registry default in priority order.
        if override:
            return override
        try:
            return Prompts().get(prompt_key)
        except Exception:
            return _registry.get(slot)

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Decomposes criterion into checklist, then evaluates response against checklist.
        checklist = await self._decompose_criterion()
        eval_template = self._resolve_template(
            "criteria_decomposition.eval",
            self.eval_prompt_template,
            Prompt.LLM_AS_A_JUDGE_CRITERIA_DECOMPOSITION_EVAL,
        )
        eval_prompt = eval_template.format(
            checklist=checklist,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, eval_prompt)
        return self._parse_response(raw)

    async def _decompose_criterion(self) -> str:
        # Calls the judge to expand self.criterion into a numbered sub-question checklist.
        template = self._resolve_template(
            "criteria_decomposition.decompose",
            self.decomposition_prompt_template,
            Prompt.LLM_AS_A_JUDGE_CRITERIA_DECOMPOSITION_DECOMPOSE,
        )
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
