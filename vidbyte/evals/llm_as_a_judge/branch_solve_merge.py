"""Context Protocol Header

Description:
    Implements the Branch-Solve-Merge LLM judge (BranchSolveMergeJudge).
Purpose:
    Splits evaluation into independent branch sub-tasks run in parallel, then merges
    results via weighted mean or a final LLM merge call.
Architecture:
    - BranchSolveMergeJudge: Inherits BaseGrader; runs N concurrent branch calls,
      aggregates via weighted mean or LLM merge, returns final GraderResult.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

import asyncio
import json
from typing import ClassVar, Literal

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.dataclasses.llm_judge import BranchSolveMergeJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class BranchSolveMergeJudge(BaseGrader):
    """Judge that evaluates independent branches in parallel then merges results."""

    name: ClassVar[str] = "branch_solve_merge"

    def __init__(self, config: BranchSolveMergeJudgeConfig) -> None:
        # Unpacks config fields for branches dict, optional weights, merge strategy, and template overrides.
        self.judge_runner = config.judge_runner
        self.branches = config.branches
        self.branch_weights = config.branch_weights
        self.merge_strategy = config.merge_strategy
        self.system_prompt = config.system_prompt
        self.branch_prompt_template = config.branch_prompt_template
        self.merge_prompt_template = config.merge_prompt_template

    def _resolve_template(self, slot: str, override: str | None, prompt_key: Prompt) -> str:
        # Returns override, SDK catalog prompt, or registry default in priority order.
        if override:
            return override
        try:
            return Prompts().get(prompt_key)
        except Exception:
            return _registry.get(slot)

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Runs all branch evaluations concurrently then aggregates via weighted mean or LLM.
        branch_results = await self._run_branches(case, actual)
        if self.merge_strategy == "llm":
            return await self._llm_merge(branch_results)
        return self._weighted_mean_merge(branch_results)

    async def _run_branches(self, case: EvalCase, actual: str) -> list[dict]:
        # Formats and fires all branch prompts concurrently, returns parsed result dicts.
        branch_template = self._resolve_template(
            "branch_solve_merge.branch",
            self.branch_prompt_template,
            Prompt.LLM_AS_A_JUDGE_BRANCH_SOLVE_MERGE_BRANCH,
        )

        async def run_one(name: str, rubric: str) -> dict:
            prompt_text = branch_template.format(
                branch_name=name,
                rubric=rubric,
                prompt=case.prompt,
                actual=actual,
                expected=case.expected if case.expected is not None else "None specified.",
            )
            raw = await invoke_runner(self.judge_runner, prompt_text)
            try:
                parsed = parse_json_block(raw)
                return {"name": name, "score": float(parsed.get("score", 0.0)), "reason": str(parsed.get("reason", ""))}
            except (ValueError, TypeError):
                return {"name": name, "score": 0.0, "reason": f"Parse error: {raw[:100]}"}

        tasks = [run_one(name, rubric) for name, rubric in self.branches.items()]
        return list(await asyncio.gather(*tasks))

    def _weighted_mean_merge(self, branch_results: list[dict]) -> GraderResult:
        # Computes weighted average of branch scores; uses equal weights if not specified.
        weights = self.branch_weights or {r["name"]: 1.0 for r in branch_results}
        total_weight = sum(weights.get(r["name"], 1.0) for r in branch_results)
        if total_weight <= 0:
            return GraderResult(score=0.0, passed=False, reason="Invalid branch weights sum to zero.")
        weighted_sum = sum(r["score"] * weights.get(r["name"], 1.0) for r in branch_results)
        final_score = min(1.0, max(0.0, weighted_sum / total_weight))
        reason = "; ".join(f"{r['name']}: {r['score']:.2f}" for r in branch_results)
        return GraderResult(score=final_score, passed=final_score >= 0.7, reason=reason)

    async def _llm_merge(self, branch_results: list[dict]) -> GraderResult:
        # Serialises branch results and invokes the judge runner for a synthesis call.
        merge_template = self._resolve_template(
            "branch_solve_merge.merge",
            self.merge_prompt_template,
            Prompt.LLM_AS_A_JUDGE_BRANCH_SOLVE_MERGE_MERGE,
        )
        results_text = json.dumps(branch_results, indent=2)
        merge_prompt = merge_template.format(branch_results=results_text)
        raw = await invoke_runner(self.judge_runner, merge_prompt)
        try:
            parsed = parse_json_block(raw)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            reason = str(parsed.get("reason", "LLM merge verdict."))
            return GraderResult(score=score, passed=score >= 0.7, reason=reason)
        except (ValueError, TypeError):
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse LLM merge response: {raw[:200]}")
