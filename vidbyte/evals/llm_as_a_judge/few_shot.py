"""Context Protocol Header

Description:
    Implements the Few-Shot LLM judge (FewShotJudge).
Purpose:
    Prepends calibrated worked examples to the evaluation prompt so the judge's
    scale is anchored to developer intent and stays consistent across runs.
Architecture:
    - FewShotJudge: Inherits BaseGrader; validates and serialises examples, formats
      prompt with examples block, invokes runner, parses JSON score.
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

_REQUIRED_KEYS = {"prompt", "actual", "expected", "score", "reason"}

_DEFAULT_TEMPLATE = (
    "You are an objective judge evaluating model responses. "
    "Study the examples below to calibrate your scoring scale, then evaluate the final response.\n\n"
    "--- CALIBRATION EXAMPLES ---\n"
    "{examples_block}\n"
    "--- END EXAMPLES ---\n\n"
    "Now evaluate the following response on a scale from 0.0 to 1.0.\n"
    "Output only a valid JSON object:\n"
    "{{\"score\": float, \"passed\": boolean, \"reason\": \"explanation\"}}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}"
)


class FewShotJudge(BaseGrader):
    """Judge that uses calibrated worked examples to anchor scale consistency."""

    name: ClassVar[str] = "few_shot"

    def __init__(self, *, judge_runner: object, examples: list[dict], system_prompt: str | None = None, prompt_template: str | None = None) -> None:
        # Validates examples list and stores runner and optional prompt overrides.
        if not examples:
            raise ValueError("FewShotJudge requires at least one example.")
        for i, ex in enumerate(examples):
            missing = _REQUIRED_KEYS - set(ex.keys())
            if missing:
                raise ValueError(f"Example {i} is missing required keys: {missing}")
        self.judge_runner = judge_runner
        self.examples = examples
        self.system_prompt = system_prompt
        self.prompt_template = prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Serialises examples, formats prompt with examples block, invokes judge, parses JSON.
        template = self._resolve_template()
        examples_block = self._serialise_examples()
        prompt_text = template.format(
            examples_block=examples_block,
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
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_FEW_SHOT_USER)
        except Exception:
            return _DEFAULT_TEMPLATE

    def _serialise_examples(self) -> str:
        # Formats each example dict into a numbered readable block for the prompt.
        lines: list[str] = []
        for i, ex in enumerate(self.examples, 1):
            lines.append(f"Example {i}:")
            lines.append(f"  Prompt: {ex['prompt']}")
            lines.append(f"  Response: {ex['actual']}")
            lines.append(f"  Expected: {ex['expected']}")
            lines.append(f"  Score: {ex['score']}")
            lines.append(f"  Reason: {ex['reason']}")
            lines.append("")
        return "\n".join(lines).strip()

    def _parse_response(self, text: str) -> GraderResult:
        # Parses JSON score/passed/reason from the judge response.
        try:
            parsed = parse_json_block(text)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            passed = bool(parsed.get("passed", score >= 0.7))
            reason = str(parsed.get("reason", "Evaluated by few-shot judge."))
            return GraderResult(score=score, passed=passed, reason=reason)
        except ValueError:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse few-shot judge response: {text[:200]}")
