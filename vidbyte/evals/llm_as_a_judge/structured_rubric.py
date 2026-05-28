"""Context Protocol Header

Description:
    Implements the Structured Multi-Dimensional Rubric judge (StructuredRubricJudge).
Purpose:
    Evaluates responses across dimensions where each dimension has explicit per-level
    anchor descriptions (e.g. 1="multiple errors", 3="mostly accurate", 5="fully precise").
    Distinct from RubricGrader which only takes weights, not level descriptions.
Architecture:
    - StructuredRubricJudge: Inherits BaseGrader; serialises anchor descriptions into rubric
      block, parses integer level scores, normalises to 0.0-1.0, computes weighted aggregate.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.dataclasses.llm_judge import StructuredRubricJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class StructuredRubricJudge(BaseGrader):
    """Judge that uses named dimensions with per-level anchor descriptions for calibrated scoring."""

    name: ClassVar[str] = "structured_rubric"

    def __init__(self, config: StructuredRubricJudgeConfig) -> None:
        # Unpacks config fields for dimension-level anchors, optional weights, threshold, and overrides.
        self.judge_runner = config.judge_runner
        self.dimensions = config.dimensions
        self.weights = config.weights
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
        # Serialises rubric block, formats prompt, invokes judge, parses and normalises scores.
        template = self._resolve_template("structured_rubric.user", self.prompt_template, Prompt.LLM_AS_A_JUDGE_STRUCTURED_RUBRIC_USER)
        rubric_block = self._serialise_rubric()
        prompt_text = template.format(
            rubric_block=rubric_block,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, prompt_text)
        return self._parse_response(raw)

    def _serialise_rubric(self) -> str:
        # Formats each dimension with numbered level descriptions as a readable rubric block.
        lines: list[str] = []
        for dim, levels in self.dimensions.items():
            lines.append(f"Dimension: {dim}")
            for level in sorted(levels.keys()):
                lines.append(f"  {level}: {levels[level]}")
            lines.append("")
        return "\n".join(lines).strip()

    def _parse_response(self, text: str) -> GraderResult:
        # Parses integer level scores, normalises per dimension max, computes weighted aggregate.
        try:
            parsed = parse_json_block(text)
            raw_scores: dict = parsed.get("scores", {})
            reasons: dict = parsed.get("reasons", {})
            weights = self.weights or {dim: 1.0 for dim in self.dimensions}
            total_weight = sum(weights.get(dim, 1.0) for dim in self.dimensions)
            if total_weight <= 0:
                return GraderResult(score=0.0, passed=False, reason="Invalid weights sum to zero.")
            weighted_sum = 0.0
            parts: list[str] = []
            for dim, level_map in self.dimensions.items():
                max_level = max(level_map.keys()) if level_map else 1
                raw_level = float(raw_scores.get(dim, 0))
                normalised = min(1.0, max(0.0, raw_level / max_level))
                w = weights.get(dim, 1.0)
                weighted_sum += normalised * w
                parts.append(f"{dim}: {raw_level}/{max_level} — {reasons.get(dim, '')}")
            final_score = min(1.0, max(0.0, weighted_sum / total_weight))
            return GraderResult(score=final_score, passed=final_score >= self.threshold, reason="; ".join(parts))
        except (ValueError, TypeError, ZeroDivisionError) as exc:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse structured rubric response: {exc}")
