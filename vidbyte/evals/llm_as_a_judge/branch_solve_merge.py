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
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_DEFAULT_BRANCH_TEMPLATE = (
    "You are a specialist judge evaluating one dimension of a model's response.\n\n"
    "Dimension: {branch_name}\n"
    "Evaluation Criteria: {rubric}\n\n"
    "Score this dimension from 0.0 to 1.0.\n"
    "Output only a valid JSON object:\n"
    "{{\"score\": float, \"reason\": \"explanation\"}}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}"
)

_DEFAULT_MERGE_TEMPLATE = (
    "You are a senior judge synthesising multiple specialist evaluations into a single final score.\n\n"
    "Specialist evaluations:\n{branch_results}\n\n"
    "Produce a final overall score from 0.0 to 1.0, weighing the evaluations appropriately.\n"
    "Output only a valid JSON object:\n"
    "{{\"score\": float, \"reason\": \"synthesis of the evaluations\"}}"
)


class BranchSolveMergeJudge(BaseGrader):
    """Judge that evaluates independent branches in parallel then merges results."""

    name: ClassVar[str] = "branch_solve_merge"

    def __init__(self, *, judge_runner: object, branches: dict[str, str], branch_weights: dict[str, float] | None = None, merge_strategy: Literal["weighted_mean", "llm"] = "weighted_mean", system_prompt: str | None = None, branch_prompt_template: str | None = None, merge_prompt_template: str | None = None) -> None:
        # Stores branches dict, optional weights, merge strategy, and template overrides.
        self.judge_runner = judge_runner
        self.branches = branches
        self.branch_weights = branch_weights
        self.merge_strategy = merge_strategy
        self.system_prompt = system_prompt
        self.branch_prompt_template = branch_prompt_template
        self.merge_prompt_template = merge_prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Runs all branch evaluations concurrently then aggregates via weighted mean or LLM.
        branch_results = await self._run_branches(case, actual)
        if self.merge_strategy == "llm":
            return await self._llm_merge(branch_results)
        return self._weighted_mean_merge(branch_results)

    def _resolve_branch_template(self) -> str:
        # Returns user-supplied branch template, SDK catalog prompt, or inline default.
        if self.branch_prompt_template:
            return self.branch_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_BRANCH_SOLVE_MERGE_BRANCH)
        except Exception:
            return _DEFAULT_BRANCH_TEMPLATE

    def _resolve_merge_template(self) -> str:
        # Returns user-supplied merge template, SDK catalog prompt, or inline default.
        if self.merge_prompt_template:
            return self.merge_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_BRANCH_SOLVE_MERGE_MERGE)
        except Exception:
            return _DEFAULT_MERGE_TEMPLATE

    async def _run_branches(self, case: EvalCase, actual: str) -> list[dict]:
        # Formats and fires all branch prompts concurrently, returns parsed result dicts.
        branch_template = self._resolve_branch_template()
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
        merge_template = self._resolve_merge_template()
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
