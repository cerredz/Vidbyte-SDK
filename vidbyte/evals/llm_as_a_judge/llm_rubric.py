"""Context Protocol Header

Description:
    Implements the LLM-Generated Rubric judge (LLMRubricJudge).
Purpose:
    Two-call strategy: first generates a rubric from a task description, then evaluates
    the response using that rubric. Scales rubric creation to new task types without manual writing.
Architecture:
    - LLMRubricJudge: Inherits BaseGrader; caches generated rubric per instance,
      runs generation on first call, then evaluates using cached rubric.
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

_DEFAULT_GENERATE_TEMPLATE = (
    "You are an expert evaluator. Create a detailed scoring rubric for evaluating responses "
    "to the following type of task.\n\n"
    "Task type: {task_description}\n\n"
    "Write a rubric with {rubric_scale} levels (1 through {rubric_scale}), where 1 is the lowest "
    "quality and {rubric_scale} is the highest. For each level, write a one-sentence description "
    "of what a response at that level looks like.\n\n"
    "Output a plain-text rubric only. No JSON, no headers."
)

_DEFAULT_EVAL_TEMPLATE = (
    "You are an objective judge. Use the rubric below to evaluate the model's response.\n\n"
    "Rubric:\n{rubric}\n\n"
    "Score the response according to the rubric, then normalise your score to a 0.0-1.0 scale.\n"
    "Output only a valid JSON object:\n"
    "{{\"score\": float, \"passed\": boolean, \"reason\": \"which rubric level best matches and why\"}}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}"
)


class LLMRubricJudge(BaseGrader):
    """Judge that generates a rubric from a task description then evaluates using it."""

    name: ClassVar[str] = "llm_rubric"

    def __init__(self, *, judge_runner: object, task_description: str, rubric_scale: int = 5, system_prompt: str | None = None, rubric_generation_prompt_template: str | None = None, eval_prompt_template: str | None = None) -> None:
        # Stores task description, scale, and template overrides; caches rubric as None until first call.
        self.judge_runner = judge_runner
        self.task_description = task_description
        self.rubric_scale = rubric_scale
        self.system_prompt = system_prompt
        self.rubric_generation_prompt_template = rubric_generation_prompt_template
        self.eval_prompt_template = eval_prompt_template
        self._cached_rubric: str | None = None

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Generates rubric on first call (cached thereafter), then evaluates actual against it.
        if self._cached_rubric is None:
            self._cached_rubric = await self._generate_rubric()
        eval_template = self._resolve_eval_template()
        eval_prompt = eval_template.format(
            rubric=self._cached_rubric,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, eval_prompt)
        return self._parse_response(raw)

    def _resolve_generate_template(self) -> str:
        # Returns user-supplied generation template, SDK catalog prompt, or inline default.
        if self.rubric_generation_prompt_template:
            return self.rubric_generation_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_LLM_RUBRIC_GENERATE)
        except Exception:
            return _DEFAULT_GENERATE_TEMPLATE

    def _resolve_eval_template(self) -> str:
        # Returns user-supplied eval template, SDK catalog prompt, or inline default.
        if self.eval_prompt_template:
            return self.eval_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_LLM_RUBRIC_EVAL)
        except Exception:
            return _DEFAULT_EVAL_TEMPLATE

    async def _generate_rubric(self) -> str:
        # Calls the judge to produce a rubric from the task description; returns plain text.
        template = self._resolve_generate_template()
        gen_prompt = template.format(task_description=self.task_description, rubric_scale=self.rubric_scale)
        return await invoke_runner(self.judge_runner, gen_prompt)

    def _parse_response(self, text: str) -> GraderResult:
        # Parses JSON score/passed/reason from the eval response.
        try:
            parsed = parse_json_block(text)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            passed = bool(parsed.get("passed", score >= 0.7))
            reason = str(parsed.get("reason", "Evaluated by LLM rubric judge."))
            return GraderResult(score=score, passed=passed, reason=reason)
        except ValueError:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse LLM rubric eval response: {text[:200]}")
