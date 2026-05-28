"""Context Protocol Header

Description:
    Implements the Chain-of-Thought LLM judge (ChainOfThoughtJudge).
Purpose:
    Instructs the judge to write step-by-step reasoning before emitting a final score,
    producing better-calibrated results constrained by the judge's own reasoning (G-Eval style).
Architecture:
    - ChainOfThoughtJudge: Inherits BaseGrader; resolves cot_length budget, formats prompt,
      invokes runner, and parses a trailing Score line with JSON fallback.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

import re
from typing import ClassVar, Literal

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.dataclasses.llm_judge import ChainOfThoughtJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()

_COT_BUDGETS: dict[str, str] = {
    "short": "~2 sentences",
    "medium": "3-5 sentences",
    "long": "as many steps as needed",
}


class ChainOfThoughtJudge(BaseGrader):
    """Judge that reasons step-by-step before emitting a calibrated final score."""

    name: ClassVar[str] = "chain_of_thought"

    def __init__(self, config: ChainOfThoughtJudgeConfig) -> None:
        # Unpacks config fields for runner, reasoning verbosity, and optional prompt overrides.
        self.judge_runner = config.judge_runner
        self.cot_length = config.cot_length
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
        # Renders the CoT prompt, invokes the judge, and parses the Score line or JSON fallback.
        template = self._resolve_template("chain_of_thought.user", self.prompt_template, Prompt.LLM_AS_A_JUDGE_CHAIN_OF_THOUGHT_USER)
        cot_budget = _COT_BUDGETS.get(self.cot_length, _COT_BUDGETS["medium"])
        prompt_text = template.format(
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
            cot_budget=cot_budget,
        )
        raw = await invoke_runner(self.judge_runner, prompt_text)
        return self._parse_response(raw)

    def _parse_response(self, text: str) -> GraderResult:
        # Extracts trailing Score line first; falls back to JSON block parsing.
        score_match = re.search(r"Score:\s*([\d.]+)", text, re.IGNORECASE)
        if score_match:
            score = min(1.0, max(0.0, float(score_match.group(1))))
            reason = text[: score_match.start()].strip()
            return GraderResult(score=score, passed=score >= 0.7, reason=reason or "Evaluated by chain-of-thought judge.")
        try:
            parsed = parse_json_block(text)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            passed = bool(parsed.get("passed", score >= 0.7))
            reason = str(parsed.get("reason", "Evaluated by chain-of-thought judge."))
            return GraderResult(score=score, passed=passed, reason=reason)
        except ValueError:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse CoT judge response: {text[:200]}")
