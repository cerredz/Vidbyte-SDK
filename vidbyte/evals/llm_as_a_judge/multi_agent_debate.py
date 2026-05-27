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
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_DEFAULT_INITIAL_TEMPLATE = (
    "You are an objective judge. Evaluate the model's response and produce your initial verdict.\n\n"
    "Score from 0.0 to 1.0. Output only a valid JSON object:\n"
    "{{\"score\": float, \"passed\": boolean, \"reason\": \"explanation\"}}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}"
)

_DEFAULT_DEBATE_TEMPLATE = (
    "You are a judge in a panel. Below are the verdicts from other judges on the same response. "
    "Review them and decide whether to maintain or revise your position. You may disagree if you have good reason.\n\n"
    "Other judges' verdicts:\n{prior_verdicts}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}\n\n"
    "Output only a valid JSON object with your (possibly revised) verdict:\n"
    "{{\"score\": float, \"passed\": boolean, \"reason\": \"your reasoning, including whether you changed your position and why\"}}"
)


class MultiAgentDebateJudge(BaseGrader):
    """Judge that runs debate rounds between multiple agents before reaching a final verdict."""

    name: ClassVar[str] = "multi_agent_debate"

    def __init__(self, *, judge_runners: list, debate_rounds: int = 1, require_dissent: bool = True, threshold: float = 0.7, system_prompt: str | None = None, initial_prompt_template: str | None = None, debate_prompt_template: str | None = None) -> None:
        # Validates >=2 runners and >=1 debate round; stores configuration.
        if len(judge_runners) < 2:
            raise ValueError("MultiAgentDebateJudge requires at least 2 judge_runners.")
        if debate_rounds < 1:
            raise ValueError("MultiAgentDebateJudge requires at least 1 debate_round.")
        self.judge_runners = judge_runners
        self.debate_rounds = debate_rounds
        self.require_dissent = require_dissent
        self.threshold = threshold
        self.system_prompt = system_prompt
        self.initial_prompt_template = initial_prompt_template
        self.debate_prompt_template = debate_prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Runs independent round-0, then debate rounds, then final majority vote.
        verdicts = await self._run_independent_round(case, actual)
        for _ in range(self.debate_rounds):
            verdicts = await self._run_debate_round(case, actual, verdicts)
        return self._aggregate_verdicts(verdicts)

    def _resolve_initial_template(self) -> str:
        # Returns user-supplied initial template, SDK catalog prompt, or inline default.
        if self.initial_prompt_template:
            return self.initial_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_MULTI_AGENT_DEBATE_INITIAL)
        except Exception:
            return _DEFAULT_INITIAL_TEMPLATE

    def _resolve_debate_template(self) -> str:
        # Returns user-supplied debate template, SDK catalog prompt, or inline default.
        if self.debate_prompt_template:
            return self.debate_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_MULTI_AGENT_DEBATE_ROUND)
        except Exception:
            return _DEFAULT_DEBATE_TEMPLATE

    async def _run_independent_round(self, case: EvalCase, actual: str) -> list[dict]:
        # Fires all judges independently with no shared information.
        template = self._resolve_initial_template()
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
        template = self._resolve_debate_template()
        prior_text = json.dumps([{"judge": v["judge"], "score": v["score"], "reason": v["reason"]} for v in prior_verdicts], indent=2)

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
