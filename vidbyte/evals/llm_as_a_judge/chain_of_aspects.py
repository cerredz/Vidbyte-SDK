"""Context Protocol Header

Description:
    Implements the Chain-of-Aspects LLM judge (ChainOfAspectsJudge).
Purpose:
    Evaluates a fixed ordered list of aspects sequentially, writing a short prose
    evaluation for each before producing a final score. Distinct from RubricGrader —
    produces full written rationale per aspect rather than just a number.
Architecture:
    - ChainOfAspectsJudge: Inherits BaseGrader; serialises aspect instructions,
      invokes judge, parses per-aspect scores and overall score with mean fallback.
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

_DEFAULT_TEMPLATE = (
    "You are an objective judge. Evaluate the model's response aspect by aspect, "
    "then produce an overall score.\n\n"
    "{aspects_instructions}\n\n"
    "Finally, provide an overall score from 0.0 to 1.0.\n\n"
    "Output only a valid JSON object:\n"
    "{{\"scores\": {{\"aspect_name\": float}}, \"reasons\": {{\"aspect_name\": \"explanation\"}}, \"overall\": float}}\n\n"
    "Evaluate each aspect independently — do not let one aspect influence another.\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}"
)


class ChainOfAspectsJudge(BaseGrader):
    """Judge that writes prose evaluation per aspect sequentially before scoring."""

    name: ClassVar[str] = "chain_of_aspects"

    def __init__(self, *, judge_runner: object, aspects: list[str], words_per_aspect: int = 30, system_prompt: str | None = None, prompt_template: str | None = None) -> None:
        # Validates that aspects is non-empty and stores runner and prompt overrides.
        if not aspects:
            raise ValueError("ChainOfAspectsJudge requires at least one aspect.")
        self.judge_runner = judge_runner
        self.aspects = aspects
        self.words_per_aspect = words_per_aspect
        self.system_prompt = system_prompt
        self.prompt_template = prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Serialises aspect instructions, formats prompt, invokes judge, parses scores.
        template = self._resolve_template()
        aspects_instructions = self._serialise_aspects()
        prompt_text = template.format(
            aspects_instructions=aspects_instructions,
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
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_CHAIN_OF_ASPECTS_USER)
        except Exception:
            return _DEFAULT_TEMPLATE

    def _serialise_aspects(self) -> str:
        # Formats each aspect as a numbered instruction with a word budget.
        lines = []
        for i, aspect in enumerate(self.aspects, 1):
            lines.append(f"{i}. Evaluate {aspect}. Write ~{self.words_per_aspect} words.")
        return "\n".join(lines)

    def _parse_response(self, text: str) -> GraderResult:
        # Parses per-aspect scores and overall; computes mean if overall absent.
        try:
            parsed = parse_json_block(text)
            scores: dict = parsed.get("scores", {})
            reasons: dict = parsed.get("reasons", {})
            overall = parsed.get("overall")
            if overall is None and scores:
                overall = sum(float(v) for v in scores.values()) / len(scores)
            overall = min(1.0, max(0.0, float(overall or 0.0)))
            reason_parts = "; ".join(f"{k}: {reasons.get(k, '')} ({scores.get(k, 0.0)})" for k in self.aspects)
            return GraderResult(score=overall, passed=overall >= 0.7, reason=reason_parts or "Evaluated by chain-of-aspects judge.")
        except (ValueError, TypeError, ZeroDivisionError):
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse chain-of-aspects response: {text[:200]}")
