"""Context Protocol Header

Description:
    Implements the Panel / Ensemble LLM judge (PanelJudge).
Purpose:
    Sends the same evaluation prompt to multiple different judge runners concurrently
    and aggregates scores via mean, median, or majority vote. Reduces individual model bias.
Architecture:
    - PanelJudge: Inherits BaseGrader; validates >=2 runners, fires all concurrently,
      aggregates verdicts per aggregation mode, returns GraderResult.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

import asyncio
import statistics
from typing import ClassVar, Literal

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_DEFAULT_TEMPLATE = (
    "You are an objective judge evaluating a model's response.\n\n"
    "Score the response on a scale from 0.0 to 1.0 based on accuracy, completeness, and clarity.\n"
    "Output only a valid JSON object:\n"
    "{{\"score\": float, \"passed\": boolean, \"reason\": \"explanation\"}}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}"
)


class PanelJudge(BaseGrader):
    """Judge that aggregates verdicts from multiple runners to reduce individual model bias."""

    name: ClassVar[str] = "panel"

    def __init__(self, *, judge_runners: list, aggregation: Literal["mean", "median", "majority_vote"] = "mean", threshold: float = 0.7, system_prompt: str | None = None, prompt_template: str | None = None) -> None:
        # Validates at least 2 runners are provided; stores aggregation mode and threshold.
        if len(judge_runners) < 2:
            raise ValueError("PanelJudge requires at least 2 judge_runners.")
        self.judge_runners = judge_runners
        self.aggregation = aggregation
        self.threshold = threshold
        self.system_prompt = system_prompt
        self.prompt_template = prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Fires identical prompt to all runners concurrently and aggregates their verdicts.
        template = self._resolve_template()
        prompt_text = template.format(
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        verdicts = await self._collect_verdicts(prompt_text)
        return self._aggregate(verdicts)

    def _resolve_template(self) -> str:
        # Returns user-supplied template, SDK catalog prompt, or inline default in that order.
        if self.prompt_template:
            return self.prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_PANEL_USER)
        except Exception:
            return _DEFAULT_TEMPLATE

    async def _collect_verdicts(self, prompt_text: str) -> list[dict]:
        # Invokes all runners concurrently and parses each response into a verdict dict.
        async def query_one(runner: object, idx: int) -> dict:
            raw = await invoke_runner(runner, prompt_text)
            try:
                parsed = parse_json_block(raw)
                return {"runner": idx, "score": float(parsed.get("score", 0.0)), "passed": bool(parsed.get("passed", False)), "reason": str(parsed.get("reason", ""))}
            except (ValueError, TypeError):
                return {"runner": idx, "score": 0.0, "passed": False, "reason": f"Parse error: {raw[:100]}"}
        tasks = [query_one(r, i) for i, r in enumerate(self.judge_runners)]
        return list(await asyncio.gather(*tasks))

    def _aggregate(self, verdicts: list[dict]) -> GraderResult:
        # Combines verdicts via mean, median, or majority_vote and computes final pass/fail.
        scores = [v["score"] for v in verdicts]
        passed_flags = [v["passed"] for v in verdicts]
        combined_reason = "; ".join(f"runner_{v['runner']}: {v['score']:.2f}" for v in verdicts)
        if self.aggregation == "mean":
            final_score = sum(scores) / len(scores)
            passed = final_score >= self.threshold
        elif self.aggregation == "median":
            final_score = statistics.median(scores)
            passed = final_score >= self.threshold
        else:
            final_score = sum(scores) / len(scores)
            pass_votes = sum(1 for f in passed_flags if f)
            passed = pass_votes > len(passed_flags) / 2
        return GraderResult(score=min(1.0, max(0.0, final_score)), passed=passed, reason=combined_reason)
