"""Context Protocol Header

Description:
    Implements the Pairwise LLM judge (PairwiseJudge).
Purpose:
    Compares two responses (A and B) to the same prompt. With swap_check enabled,
    runs both orderings and only declares a winner if both agree, debiasing position preference.
Architecture:
    - PairwiseJudge: Inherits BaseGrader; reads response_b from case.metadata,
      runs one or two comparison calls, applies consensus rule, returns GraderResult.
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
    "You are an objective judge comparing two responses to the same prompt. "
    "Decide which response is better.\n\n"
    "Output only a valid JSON object:\n"
    "{{\"winner\": \"A\" or \"B\" or \"Tie\", \"reason\": \"explanation\"}}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Response A:\n{response_a}\n\n"
    "Response B:\n{response_b}\n\n"
    "Expected Output:\n{expected}"
)


class PairwiseJudge(BaseGrader):
    """Judge that compares two responses and returns a winner with optional position-bias debiasing."""

    name: ClassVar[str] = "pairwise"

    def __init__(self, *, judge_runner: object, swap_check: bool = True, system_prompt: str | None = None, prompt_template: str | None = None) -> None:
        # Stores runner and swap_check flag; swap_check=True runs both orderings for debiasing.
        self.judge_runner = judge_runner
        self.swap_check = swap_check
        self.system_prompt = system_prompt
        self.prompt_template = prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Reads response_b from metadata, runs comparison(s), applies consensus rule.
        response_b = case.metadata.get("response_b")
        if response_b is None:
            raise ValueError("PairwiseJudge requires case.metadata['response_b'] to be set.")
        verdict_1 = await self._compare(case, actual, response_b)
        if not self.swap_check:
            return self._verdict_to_result(verdict_1, actual_is_a=True)
        verdict_2 = await self._compare(case, response_b, actual)
        return self._consensus(verdict_1, verdict_2)

    def _resolve_template(self) -> str:
        # Returns user-supplied template, SDK catalog prompt, or inline default in that order.
        if self.prompt_template:
            return self.prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_PAIRWISE_USER)
        except Exception:
            return _DEFAULT_TEMPLATE

    async def _compare(self, case: EvalCase, response_a: str, response_b: str) -> str:
        # Formats a single pairwise prompt and returns the raw winner string (A/B/Tie).
        template = self._resolve_template()
        prompt_text = template.format(
            prompt=case.prompt,
            response_a=response_a,
            response_b=response_b,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, prompt_text)
        try:
            parsed = parse_json_block(raw)
            return str(parsed.get("winner", "Tie")).strip()
        except ValueError:
            upper = raw.strip().upper()
            if upper.startswith("A"):
                return "A"
            if upper.startswith("B"):
                return "B"
            return "Tie"

    def _verdict_to_result(self, winner: str, actual_is_a: bool) -> GraderResult:
        # Maps a winner label to a GraderResult score where 1.0 means actual wins.
        if winner == "Tie":
            return GraderResult(score=0.5, passed=True, reason="Pairwise judge: Tie.")
        actual_label = "A" if actual_is_a else "B"
        if winner == actual_label:
            return GraderResult(score=1.0, passed=True, reason=f"Pairwise judge: actual response ({actual_label}) wins.")
        return GraderResult(score=0.0, passed=False, reason=f"Pairwise judge: response_b wins over actual ({actual_label}).")

    def _consensus(self, verdict_1: str, verdict_2: str) -> GraderResult:
        # Applies swap-check consensus: actual wins only if both agree; any disagreement → Tie.
        # verdict_1: A=actual, B=response_b. verdict_2: A=response_b, B=actual.
        actual_wins_1 = verdict_1 == "A"
        actual_wins_2 = verdict_2 == "B"
        if actual_wins_1 and actual_wins_2:
            return GraderResult(score=1.0, passed=True, reason="Pairwise judge (swap-checked): actual response wins both orderings.")
        responseb_wins_1 = verdict_1 == "B"
        responseb_wins_2 = verdict_2 == "A"
        if responseb_wins_1 and responseb_wins_2:
            return GraderResult(score=0.0, passed=False, reason="Pairwise judge (swap-checked): response_b wins both orderings.")
        return GraderResult(score=0.5, passed=True, reason=f"Pairwise judge (swap-checked): disagreement across orderings ({verdict_1}/{verdict_2}) → Tie.")
