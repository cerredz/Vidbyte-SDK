"""Context Protocol Header

Description:
    Implements a model-graded evaluation judge (LLMJudgeGrader).
Purpose:
    Enables open-ended, semantic evaluation of responses against rubrics or expectation prompts
    using another LLM as a judge.
Architecture:
    - LLMJudgeGrader: Inherits from BaseGrader, coordinates prompt template rendering and response JSON parsing.
Functions:
    - agrade: Core grading algorithm preparing prompt, calling model, and parsing JSON scores.
    - _invoke_judge: Dispatches prompt to the judge runner asynchronously or synchronously.
    - _parse_response: Safely extracts and decodes json output from the judge runner response.
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


class LLMJudgeGrader(BaseGrader):
    """Grader that uses a separate LLM runner as an objective judge to score model outputs."""

    name: ClassVar[str] = "llm_judge"

    def __init__(self, *, judge_runner: object, prompt_template: str | None = None) -> None:
        # Initializes the LLMJudgeGrader with a target judge runner and customizable templates.
        self.judge_runner = judge_runner
        self.prompt_template = prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Asynchronously renders prompt templates, calls the judge runner, and parses the returned JSON score.
        template = self._resolve_template()
        prompt_text = template.format(
            prompt=case.prompt,
            expected=case.expected if case.expected is not None else "None specified.",
            actual=actual
        )

        raw_response = await self._invoke_judge(prompt_text)
        return self._parse_response(raw_response)

    def _resolve_template(self) -> str:
        # Resolves the prompt template from user config or falls back to the registered SDK prompts.
        if self.prompt_template:
            return self.prompt_template
        try:
            return Prompts().get(Prompt.EVALS_LLM_JUDGE)
        except Exception:
            return (
                "You are an objective judge assessing the accuracy of a response to a prompt.\n"
                "Grade the response against the expected output on a scale from 0.0 to 1.0.\n"
                "Output only a valid JSON object matching this structure:\n"
                "{{\n"
                "  \"score\": float,\n"
                "  \"passed\": boolean,\n"
                "  \"reason\": \"explanation of the grading decision\"\n"
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
        # Safely extracts the JSON object from model outputs and converts it into a GraderResult.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return GraderResult(score=0.0, passed=False, reason=f"Failed to find JSON block in judge response: {text}")

        try:
            parsed = json.loads(match.group(0))
            score = float(parsed.get("score", 0.0))
            passed = bool(parsed.get("passed", False))
            reason = str(parsed.get("reason", "Graded by LLM Judge."))
            return GraderResult(score=score, passed=passed, reason=reason)
        except Exception as exc:
            return GraderResult(score=0.0, passed=False, reason=f"Failed to parse judge JSON: {str(exc)}")
