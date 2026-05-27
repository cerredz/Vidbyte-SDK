"""Context Protocol Header

Description:
    Implements the Self-Evaluation LLM judge (SelfEvalJudge).
Purpose:
    Uses the same model as both generator and judge, framed in third-person to reduce
    self-preference bias. Cheapest possible setup — one runner, one API key.
Architecture:
    - SelfEvalJudge: Inherits BaseGrader; selects framing header based on framing param,
      formats prompt, invokes runner, parses JSON.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

from typing import ClassVar, Literal

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_FRAMING_HEADERS: dict[str, str] = {
    "third_person": "another assistant's response",
    "anonymous": "an AI assistant's response",
}

_DEFAULT_TEMPLATE = (
    "You are an objective judge evaluating {framing_header}.\n\n"
    "Score the response on a scale from 0.0 to 1.0 based on accuracy, completeness, and clarity.\n"
    "Output only a valid JSON object:\n"
    "{{\"score\": float, \"passed\": boolean, \"reason\": \"explanation\"}}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Response to evaluate:\n{actual}\n\n"
    "Expected Output:\n{expected}"
)


class SelfEvalJudge(BaseGrader):
    """Judge that uses third-person framing to reduce self-preference bias when the runner evaluates its own output."""

    name: ClassVar[str] = "self_eval"

    def __init__(self, *, judge_runner: object, framing: Literal["third_person", "anonymous"] = "third_person", system_prompt: str | None = None, prompt_template: str | None = None) -> None:
        # Stores the runner and framing mode used to reduce self-preference bias.
        self.judge_runner = judge_runner
        self.framing = framing
        self.system_prompt = system_prompt
        self.prompt_template = prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Selects framing header, formats prompt, invokes runner, parses JSON score.
        template = self._resolve_template()
        framing_header = _FRAMING_HEADERS.get(self.framing, _FRAMING_HEADERS["third_person"])
        prompt_text = template.format(
            framing_header=framing_header,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, prompt_text)
        return self._parse_response(raw)

    def _resolve_template(self) -> str:
        # Returns user-supplied template, SDK catalog prompt, or inline default in that order.
        if self.prompt_template:
            return self.prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_SELF_EVAL_USER)
        except Exception:
            return _DEFAULT_TEMPLATE

    def _parse_response(self, text: str) -> GraderResult:
        # Parses JSON score/passed/reason from the judge response.
        try:
            parsed = parse_json_block(text)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            passed = bool(parsed.get("passed", score >= 0.7))
            reason = str(parsed.get("reason", "Evaluated by self-eval judge."))
            return GraderResult(score=score, passed=passed, reason=reason)
        except ValueError:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse self-eval response: {text[:200]}")
