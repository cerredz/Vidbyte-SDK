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
from vidbyte.lib.dataclasses.llm_judge import LLMRubricJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class LLMRubricJudge(BaseGrader):
    """Judge that generates a rubric from a task description then evaluates using it."""

    name: ClassVar[str] = "llm_rubric"

    def __init__(self, config: LLMRubricJudgeConfig) -> None:
        # Unpacks config fields; initialises mutable rubric cache to None.
        self.judge_runner = config.judge_runner
        self.task_description = config.task_description
        self.rubric_scale = config.rubric_scale
        self.system_prompt = config.system_prompt
        self.rubric_generation_prompt_template = config.rubric_generation_prompt_template
        self.eval_prompt_template = config.eval_prompt_template
        self._cached_rubric: str | None = None

    def _resolve_template(self, slot: str, override: str | None, prompt_key: Prompt) -> str:
        # Returns override, SDK catalog prompt, or registry default in priority order.
        if override:
            return override
        try:
            return Prompts().get(prompt_key)
        except Exception:
            return _registry.get(slot)

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Generates rubric on first call (cached thereafter), then evaluates actual against it.
        if self._cached_rubric is None:
            self._cached_rubric = await self._generate_rubric()
        eval_template = self._resolve_template(
            "llm_rubric.eval",
            self.eval_prompt_template,
            Prompt.LLM_AS_A_JUDGE_LLM_RUBRIC_EVAL,
        )
        eval_prompt = eval_template.format(
            rubric=self._cached_rubric,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, eval_prompt)
        return self._parse_response(raw)

    async def _generate_rubric(self) -> str:
        # Calls the judge to produce a rubric from the task description; returns plain text.
        template = self._resolve_template(
            "llm_rubric.generate",
            self.rubric_generation_prompt_template,
            Prompt.LLM_AS_A_JUDGE_LLM_RUBRIC_GENERATE,
        )
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
