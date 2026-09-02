"""Context Protocol Header

Description:
    Implements a multi-dimensional weighted rubric grader (RubricGrader).
Purpose:
    Allows fine-grained evaluations using weighted average scores across distinct categories
    (such as accuracy, clarity, and conciseness) scored by an LLM judge.
Architecture:
    - RubricGrader: Inherits from BaseGrader, renders multi-dimension prompts, parses scores,
      and calculates weighted final results.
Functions:
    - agrade: Prepares the rubric prompt, invokes the judge runner, and computes the weighted score.
    - _resolve_template: Fetches prompt assets or falls back to system defaults.
    - _invoke_judge: Invokes the judge runner asynchronously or synchronously.
    - _parse_response: Decodes the multidimensional JSON scores and calculates the weighted result.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    and vidbyte.prompts (fetches judgment templates).
"""

from __future__ import annotations

import json
import re
import inspect
from typing import Any, ClassVar
from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts


class RubricGrader(BaseGrader):
    """Grader that evaluates responses across multiple weighted dimensions using an LLM judge."""

    name: ClassVar[str] = "rubric"

    def __init__(self, *, judge_runner: object, rubric: dict[str, float], threshold: float = 0.7, prompt_template: str | None = None) -> None:
        # Initializes the RubricGrader with a target judge, weighted criteria dictionary, and threshold.
        self.judge_runner = judge_runner
        self.rubric = rubric
        self.threshold = threshold
        self.prompt_template = prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Asynchronously prepares the multidimensional template, fetches scores, and returns the weighted results.
        template = self._resolve_template()
        dimensions_list = "\n".join(f"- {dim} (weight: {weight})" for dim, weight in self.rubric.items())
        prompt_text = template.format(
            prompt=case.prompt,
            expected=case.expected if case.expected is not None else "None specified.",
            actual=actual,
            dimensions=dimensions_list
        )

        raw_response = await self._invoke_judge(prompt_text)
        return self._parse_response(raw_response)

    def _resolve_template(self) -> str:
        # Resolves the rubric prompt template from user config or falls back to the registered SDK prompts.
        if self.prompt_template:
            return self.prompt_template
        try:
            return Prompts().get(Prompt.EVALS_RUBRIC)
        except Exception:
            return (
                "You are an objective judge assessing a response to a prompt.\n"
                "Please grade the response across the following dimensions on a scale from 0.0 to 1.0:\n"
                "{dimensions}\n\n"
                "Output only a valid JSON object matching this structure:\n"
                "{{\n"
                "  \"scores\": {{\n"
                "    \"dimension_name\": float\n"
                "  }},\n"
                "  \"reasons\": {{\n"
                "    \"dimension_name\": \"explanation\"\n"
                "  }}\n"
                "}}\n\n"
                "Task Prompt:\n{prompt}\n\n"
                "Model Response:\n{actual}\n\n"
                "Expected Output:\n{expected}\n"
            )

    async def _invoke_judge(self, prompt: str) -> str:
        # Invokes the judge runner asynchronously if supported, otherwise runs it synchronously.
        runner = self.judge_runner
        if hasattr(runner, "arun"):
            res = await runner.arun(prompt, temperature=0.0)
        elif hasattr(runner, "generate_reply"):
            res = await runner.generate_reply(prompt, temperature=0.0)
        elif hasattr(runner, "run"):
            if inspect.iscoroutinefunction(runner.run):
                res = await runner.run(prompt, temperature=0.0)
            else:
                res = runner.run(prompt, temperature=0.0)
        else:
            raise TypeError("Judge runner must expose run(), generate_reply(), or arun() method.")

        if isinstance(res, str):
            return res
        if hasattr(res, "text"):
            return str(res.text)
        if hasattr(res, "content"):
            return str(res.content)
        if isinstance(res, dict) and "text" in res:
            return str(res["text"])
        return str(res)

    def _parse_response(self, text: str) -> GraderResult:
        # Safely extracts the dimension scores and calculates the weighted average against the threshold.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return GraderResult(score=0.0, passed=False, reason=f"Failed to find JSON block in rubric response: {text}")

        try:
            parsed = json.loads(match.group(0))
            scores = parsed.get("scores", {})
            reasons = parsed.get("reasons", {})
            
            total_weight = sum(self.rubric.values())
            if total_weight <= 0.0:
                return GraderResult(score=0.0, passed=False, reason="Invalid rubric weights summation <= 0.0")

            weighted_score_sum = 0.0
            for dim, weight in self.rubric.items():
                val = float(scores.get(dim, 0.0))
                weighted_score_sum += val * weight

            final_score = weighted_score_sum / total_weight
            passed = final_score >= self.threshold
            
            reasons_summary = "; ".join(f"{dim}: {reasons.get(dim, 'No explanation.')} ({scores.get(dim, 0.0)})" for dim in self.rubric)
            reason = f"Final weighted score: {final_score:.2f} (Threshold: {self.threshold}). Explanations: {reasons_summary}"
            return GraderResult(score=final_score, passed=passed, reason=reason)
        except Exception as exc:
            return GraderResult(score=0.0, passed=False, reason=f"Failed to parse rubric response JSON: {str(exc)}")
