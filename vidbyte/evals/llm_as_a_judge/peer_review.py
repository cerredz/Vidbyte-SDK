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
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_DEFAULT_TEMPLATE = (
    "You are a peer reviewer evaluating a model's response. "
    "Provide your verdict AND your confidence in that verdict.\n\n"
    "Score from 0.0 to 1.0. Confidence from 0.0 to 1.0 (0=completely uncertain, 1=fully certain).\n"
    "Output only a valid JSON object:\n"
    "{{\"score\": float, \"passed\": boolean, \"confidence\": float, \"reason\": \"explanation\"}}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}"
)


class PeerReviewJudge(BaseGrader):
    """Judge that aggregates confidence-weighted verdicts from multiple reviewers."""

    name: ClassVar[str] = "peer_review"

    def __init__(self, *, judge_runners: list, confidence_threshold: float = 0.5, threshold: float = 0.7, system_prompt: str | None = None, prompt_template: str | None = None) -> None:
        # Validates at least 2 runners; stores confidence threshold and pass threshold.
        if len(judge_runners) < 2:
            raise ValueError("PeerReviewJudge requires at least 2 judge_runners.")
        self.judge_runners = judge_runners
        self.confidence_threshold = confidence_threshold
        self.threshold = threshold
        self.system_prompt = system_prompt
        self.prompt_template = prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Collects confidence-scored reviews, filters low-confidence, computes weighted score.
        template = self._resolve_template()
        prompt_text = template.format(
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        reviews = await self._collect_reviews(prompt_text)
        return self._aggregate(reviews)

    def _resolve_template(self) -> str:
        # Returns user-supplied template, SDK catalog prompt, or inline default in that order.
        if self.prompt_template:
            return self.prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_PEER_REVIEW_USER)
        except Exception:
            return _DEFAULT_TEMPLATE

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
