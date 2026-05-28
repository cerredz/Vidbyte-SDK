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
from vidbyte.lib.dataclasses.llm_judge import ChainOfAspectsJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class ChainOfAspectsJudge(BaseGrader):
    """Judge that writes prose evaluation per aspect sequentially before scoring."""

    name: ClassVar[str] = "chain_of_aspects"

    def __init__(self, config: ChainOfAspectsJudgeConfig) -> None:
        # Unpacks config fields for aspects list, word budget, runner, and template overrides.
        self.judge_runner = config.judge_runner
        self.aspects = config.aspects
        self.words_per_aspect = config.words_per_aspect
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
        # Serialises aspect instructions, formats prompt, invokes judge, parses scores.
        template = self._resolve_template("chain_of_aspects.user", self.prompt_template, Prompt.LLM_AS_A_JUDGE_CHAIN_OF_ASPECTS_USER)
        aspects_instructions = self._serialise_aspects()
        prompt_text = template.format(
            aspects_instructions=aspects_instructions,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, prompt_text)
        return self._parse_response(raw)

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
