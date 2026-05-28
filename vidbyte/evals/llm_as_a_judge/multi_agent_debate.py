"""Context Protocol Header

Description:
    Implements the Multi-Agent Debate LLM judge (MultiAgentDebateJudge).
Purpose:
    ChatEval-style debate: judges first evaluate independently, then share verdicts
    and may revise over N rounds. Surfaces reasoning errors individual judges miss.
Architecture:
    - MultiAgentDebateJudge: Inherits BaseGrader; runs independent round-0 evaluations,
      conducts sequential debate rounds with verdict sharing, aggregates via majority vote.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

import asyncio
import json
from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.dataclasses.llm_judge import MultiAgentDebateJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class MultiAgentDebateJudge(BaseGrader):
    """Judge that runs debate rounds between multiple agents before reaching a final verdict."""

    name: ClassVar[str] = "multi_agent_debate"

    def __init__(self, config: MultiAgentDebateJudgeConfig) -> None:
        # Unpacks config fields for runners list, debate rounds, dissent flag, and template overrides.
        self.judge_runners = config.judge_runners
        self.debate_rounds = config.debate_rounds
        self.require_dissent = config.require_dissent
        self.threshold = config.threshold
        self.system_prompt = config.system_prompt
        self.initial_prompt_template = config.initial_prompt_template
        self.debate_prompt_template = config.debate_prompt_template

    def _resolve_template(self, slot: str, override: str | None, prompt_key: Prompt) -> str:
        # Returns override, SDK catalog prompt, or registry default in priority order.
        if override:
            return override
        try:
            return Prompts().get(prompt_key)
        except Exception:
            return _registry.get(slot)

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Runs independent round-0, then debate rounds, then final majority vote.
        verdicts = await self._run_independent_round(case, actual)
        for _ in range(self.debate_rounds):
            verdicts = await self._run_debate_round(case, actual, verdicts)
        return self._aggregate_verdicts(verdicts)

    async def _run_independent_round(self, case: EvalCase, actual: str) -> list[dict]:
        # Fires all judges independently with no shared information.
        template = self._resolve_template(
            "multi_agent_debate.initial",
            self.initial_prompt_template,
            Prompt.LLM_AS_A_JUDGE_MULTI_AGENT_DEBATE_INITIAL,
        )
        prompt_text = template.format(
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )

        async def judge_one(runner: object, idx: int) -> dict:
            raw = await invoke_runner(runner, prompt_text)
            try:
                parsed = parse_json_block(raw)
                return {"judge": idx, "score": float(parsed.get("score", 0.0)), "passed": bool(parsed.get("passed", False)), "reason": str(parsed.get("reason", ""))}
            except (ValueError, TypeError):
                return {"judge": idx, "score": 0.0, "passed": False, "reason": f"Parse error: {raw[:100]}"}

        return list(await asyncio.gather(*[judge_one(r, i) for i, r in enumerate(self.judge_runners)]))

    async def _run_debate_round(self, case: EvalCase, actual: str, prior_verdicts: list[dict]) -> list[dict]:
        # Shares prior verdicts with all judges and collects revised positions concurrently.
        template = self._resolve_template(
            "multi_agent_debate.round",
            self.debate_prompt_template,
            Prompt.LLM_AS_A_JUDGE_MULTI_AGENT_DEBATE_ROUND,
        )

        async def debate_one(runner: object, idx: int) -> dict:
            own_prior = [v for v in prior_verdicts if v["judge"] == idx]
            others_text = json.dumps([v for v in prior_verdicts if v["judge"] != idx], indent=2)
            prompt_text = template.format(
                prior_verdicts=others_text,
                prompt=case.prompt,
                actual=actual,
                expected=case.expected if case.expected is not None else "None specified.",
            )
            raw = await invoke_runner(runner, prompt_text)
            try:
                parsed = parse_json_block(raw)
                return {"judge": idx, "score": float(parsed.get("score", 0.0)), "passed": bool(parsed.get("passed", False)), "reason": str(parsed.get("reason", ""))}
            except (ValueError, TypeError):
                return own_prior[0] if own_prior else {"judge": idx, "score": 0.0, "passed": False, "reason": "Parse error — retained prior verdict."}

        return list(await asyncio.gather(*[debate_one(r, i) for i, r in enumerate(self.judge_runners)]))

    def _aggregate_verdicts(self, verdicts: list[dict]) -> GraderResult:
        # Computes majority vote on passed; uses mean score to break ties.
        mean_score = sum(v["score"] for v in verdicts) / len(verdicts)
        pass_votes = sum(1 for v in verdicts if v["passed"])
        majority_passed = pass_votes > len(verdicts) / 2 or (pass_votes == len(verdicts) / 2 and mean_score >= self.threshold)
        reason = f"Debate result: {pass_votes}/{len(verdicts)} judges passed, mean score {mean_score:.2f}."
        return GraderResult(score=min(1.0, max(0.0, mean_score)), passed=majority_passed, reason=reason)
