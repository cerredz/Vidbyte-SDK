"""Context Protocol Header

Description:
    Implements the Multi-Agent Different Rubrics judge (MultiAgentRubricJudge).
Purpose:
    Different agent instances specialise in different evaluation dimensions.
    Each agent receives a specialised rubric and runs concurrently.
    Results are aggregated via weighted mean or an LLM merge call.
Architecture:
    - MultiAgentRubricJudge: Inherits BaseGrader; fires agents concurrently with per-agent
      rubrics, then merges via weighted mean or secondary LLM call.
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
from vidbyte.lib.dataclasses.llm_judge import MultiAgentRubricJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class MultiAgentRubricJudge(BaseGrader):
    """Judge that runs specialised agents with different rubrics in parallel and aggregates results."""

    name: ClassVar[str] = "multi_agent_rubric"

    def __init__(self, config: MultiAgentRubricJudgeConfig) -> None:
        # Unpacks config fields for agents list, weights, merge strategy, and template overrides.
        self.agents = config.agents
        self.weights = config.weights
        self.merge_strategy = config.merge_strategy
        self.merge_runner = config.merge_runner
        self.threshold = config.threshold
        self.system_prompt = config.system_prompt
        self.agent_prompt_template = config.agent_prompt_template
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
        # Fires all agent evaluations concurrently, then merges results.
        agent_results = await self._run_agents(case, actual)
        if self.merge_strategy == "llm":
            return await self._llm_merge(agent_results)
        return self._weighted_mean_merge(agent_results)

    async def _run_agents(self, case: EvalCase, actual: str) -> list[dict]:
        # Dispatches each (runner, rubric) agent pair concurrently and parses responses.
        agent_template = self._resolve_template(
            "multi_agent_rubric.agent",
            self.agent_prompt_template,
            Prompt.LLM_AS_A_JUDGE_MULTI_AGENT_RUBRIC_AGENT,
        )

        async def run_one(idx: int, runner: object, rubric: str) -> dict:
            prompt_text = agent_template.format(
                rubric=rubric,
                prompt=case.prompt,
                actual=actual,
                expected=case.expected if case.expected is not None else "None specified.",
            )
            raw = await invoke_runner(runner, prompt_text)
            try:
                parsed = parse_json_block(raw)
                return {"agent": idx, "score": float(parsed.get("score", 0.0)), "reason": str(parsed.get("reason", ""))}
            except (ValueError, TypeError):
                return {"agent": idx, "score": 0.0, "reason": f"Parse error: {raw[:100]}"}

        tasks = [run_one(i, runner, rubric) for i, (runner, rubric) in enumerate(self.agents)]
        return list(await asyncio.gather(*tasks))

    def _weighted_mean_merge(self, agent_results: list[dict]) -> GraderResult:
        # Computes weighted average of agent scores; uses equal weights if not specified.
        weights = self.weights or [1.0] * len(agent_results)
        total_weight = sum(weights)
        if total_weight <= 0:
            return GraderResult(score=0.0, passed=False, reason="Invalid agent weights sum to zero.")
        weighted_sum = sum(r["score"] * w for r, w in zip(agent_results, weights))
        final_score = min(1.0, max(0.0, weighted_sum / total_weight))
        reason = "; ".join(f"agent_{r['agent']}: {r['score']:.2f}" for r in agent_results)
        return GraderResult(score=final_score, passed=final_score >= self.threshold, reason=reason)

    async def _llm_merge(self, agent_results: list[dict]) -> GraderResult:
        # Serialises agent results and invokes merge runner for a synthesis call.
        merge_template = self._resolve_template(
            "multi_agent_rubric.merge",
            self.merge_prompt_template,
            Prompt.LLM_AS_A_JUDGE_MULTI_AGENT_RUBRIC_MERGE,
        )
        results_text = json.dumps(agent_results, indent=2)
        merge_prompt = merge_template.format(agent_results=results_text)
        raw = await invoke_runner(self.merge_runner, merge_prompt)
        try:
            parsed = parse_json_block(raw)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            reason = str(parsed.get("reason", "LLM merge verdict."))
            return GraderResult(score=score, passed=score >= self.threshold, reason=reason)
        except (ValueError, TypeError):
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse LLM merge response: {raw[:200]}")
