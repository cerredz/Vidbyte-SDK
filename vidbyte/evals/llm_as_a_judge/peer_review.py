"""Context Protocol Header

Description:
    Implements the Peer Review with Confidence Voting judge (PeerReviewJudge).
Purpose:
    Multiple judge agents each produce a verdict AND a confidence score.
    Final vote is weighted by confidence; low-confidence judges are filtered out.
Architecture:
    - PeerReviewJudge: Inherits BaseGrader; validates >=2 runners, fires concurrently,
      filters by confidence_threshold, computes confidence-weighted average score.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.dataclasses.llm_judge import PeerReviewJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class PeerReviewJudge(BaseGrader):
    """Judge that aggregates confidence-weighted verdicts from multiple reviewers."""

    name: ClassVar[str] = "peer_review"

    def __init__(self, config: PeerReviewJudgeConfig) -> None:
        # Unpacks config fields for runners list, confidence threshold, pass threshold, and overrides.
        self.judge_runners = config.judge_runners
        self.confidence_threshold = config.confidence_threshold
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
        # Collects confidence-scored reviews, filters low-confidence, computes weighted score.
        template = self._resolve_template("peer_review.user", self.prompt_template, Prompt.LLM_AS_A_JUDGE_PEER_REVIEW_USER)
        prompt_text = template.format(
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        reviews = await self._collect_reviews(prompt_text)
        return self._aggregate(reviews)

    async def _collect_reviews(self, prompt_text: str) -> list[dict]:
        # Fires all runners concurrently and parses each response for score + confidence.
        async def review_one(runner: object, idx: int) -> dict:
            raw = await invoke_runner(runner, prompt_text)
            try:
                parsed = parse_json_block(raw)
                return {
                    "reviewer": idx,
                    "score": float(parsed.get("score", 0.0)),
                    "passed": bool(parsed.get("passed", False)),
                    "confidence": min(1.0, max(0.0, float(parsed.get("confidence", 0.5)))),
                    "reason": str(parsed.get("reason", "")),
                }
            except (ValueError, TypeError):
                return {"reviewer": idx, "score": 0.0, "passed": False, "confidence": 0.0, "reason": f"Parse error: {raw[:100]}"}

        tasks = [review_one(r, i) for i, r in enumerate(self.judge_runners)]
        return list(await asyncio.gather(*tasks))

    def _aggregate(self, reviews: list[dict]) -> GraderResult:
        # Filters by confidence_threshold, falls back to all if none pass; computes weighted score.
        filtered = [r for r in reviews if r["confidence"] >= self.confidence_threshold]
        if not filtered:
            filtered = reviews
        total_confidence = sum(r["confidence"] for r in filtered)
        if total_confidence <= 0:
            weighted_score = sum(r["score"] for r in filtered) / len(filtered)
        else:
            weighted_score = sum(r["score"] * r["confidence"] for r in filtered) / total_confidence
        weighted_score = min(1.0, max(0.0, weighted_score))
        reason = "; ".join(f"reviewer_{r['reviewer']}: score={r['score']:.2f} conf={r['confidence']:.2f}" for r in filtered)
        return GraderResult(score=weighted_score, passed=weighted_score >= self.threshold, reason=reason)
