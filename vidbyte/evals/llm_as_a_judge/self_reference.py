"""Context Protocol Header

Description:
    Implements the Self-Reference LLM judge (SelfReferenceJudge).
Purpose:
    Before evaluating, the judge generates its own answer to the prompt and uses that
    as a soft reference. Exploits the correlation between generation and judgment capability.
Architecture:
    - SelfReferenceJudge: Inherits BaseGrader; runs concurrent self-generation calls,
      uses first result as soft reference, then runs an evaluation call comparing actual to it.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_DEFAULT_GENERATION_TEMPLATE = "Answer the following question or task as completely and accurately as you can.\n\nTask:\n{prompt}"

_DEFAULT_EVAL_TEMPLATE = (
    "You are an objective judge comparing a model's response to a reference answer.\n\n"
    "Score the model's response on a scale from 0.0 to 1.0 based on how well it matches the reference.\n"
    "Output only a valid JSON object:\n"
    "{{\"score\": float, \"passed\": boolean, \"reason\": \"explanation\"}}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Reference Answer:\n{reference}\n\n"
    "Model Response:\n{actual}"
)


class SelfReferenceJudge(BaseGrader):
    """Judge that generates its own answer first, then uses it as a soft reference for evaluation."""

    name: ClassVar[str] = "self_reference"

    def __init__(self, *, judge_runner: object, num_self_generations: int = 1, system_prompt: str | None = None, generation_prompt_template: str | None = None, eval_prompt_template: str | None = None) -> None:
        # Stores runner, generation count, and optional template overrides.
        self.judge_runner = judge_runner
        self.num_self_generations = max(1, num_self_generations)
        self.system_prompt = system_prompt
        self.generation_prompt_template = generation_prompt_template
        self.eval_prompt_template = eval_prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Generates self-answers concurrently, picks first as reference, then evaluates actual against it.
        gen_template = self._resolve_generation_template()
        gen_prompt = gen_template.format(prompt=case.prompt)
        generation_calls = [invoke_runner(self.judge_runner, gen_prompt) for _ in range(self.num_self_generations)]
        generations = await asyncio.gather(*generation_calls)
        soft_reference = generations[0]
        eval_template = self._resolve_eval_template()
        eval_prompt = eval_template.format(prompt=case.prompt, reference=soft_reference, actual=actual)
        raw = await invoke_runner(self.judge_runner, eval_prompt)
        return self._parse_response(raw)

    def _resolve_generation_template(self) -> str:
        # Returns user-supplied generation template or inline default.
        if self.generation_prompt_template:
            return self.generation_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_SELF_REFERENCE_GENERATION)
        except Exception:
            return _DEFAULT_GENERATION_TEMPLATE

    def _resolve_eval_template(self) -> str:
        # Returns user-supplied eval template or inline default.
        if self.eval_prompt_template:
            return self.eval_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_SELF_REFERENCE_EVAL)
        except Exception:
            return _DEFAULT_EVAL_TEMPLATE

    def _parse_response(self, text: str) -> GraderResult:
        # Parses JSON score/passed/reason from the eval response.
        try:
            parsed = parse_json_block(text)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            passed = bool(parsed.get("passed", score >= 0.7))
            reason = str(parsed.get("reason", "Evaluated by self-reference judge."))
            return GraderResult(score=score, passed=passed, reason=reason)
        except ValueError:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse self-reference eval response: {text[:200]}")
