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
from vidbyte.lib.dataclasses.llm_judge import PanelJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class PanelJudge(BaseGrader):
    """Judge that aggregates verdicts from multiple runners to reduce individual model bias."""

    name: ClassVar[str] = "panel"

    def __init__(self, config: PanelJudgeConfig) -> None:
        # Unpacks config fields for runners list, aggregation mode, threshold, and template overrides.
        self.judge_runners = config.judge_runners
        self.aggregation = config.aggregation
        self.threshold = config.threshold
        self.system_prompt = config.system_prompt
        self.prompt_template = config.prompt_template

    def _resolve_template(self, slot: str, override: str | None, prompt_key: Prompt) -> str:
        # Returns override, SDK catalog prompt, or registry default in priority order.
        if override:
            return override
        try:
            return Prompts().get(prompt_key)
        except Exception:
            return _registry.get(slot)

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Fires identical prompt to all runners concurrently and aggregates their verdicts.
        template = self._resolve_template("panel.user", self.prompt_template, Prompt.LLM_AS_A_JUDGE_PANEL_USER)
        prompt_text = template.format(
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        verdicts = await self._collect_verdicts(prompt_text)
        return self._aggregate(verdicts)

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
