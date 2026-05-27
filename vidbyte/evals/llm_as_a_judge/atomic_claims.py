"""Context Protocol Header

Description:
    Implements the Atomic Claims LLM judge (AtomicClaimsJudge).
Purpose:
    Two-call factuality evaluator: decomposes response into atomic factual claims,
    then verifies each claim independently in parallel. Score = fraction verified true.
Architecture:
    - AtomicClaimsJudge: Inherits BaseGrader; extracts claims via first LLM call,
      verifies each concurrently via second set of calls, aggregates pass rate.
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

_DEFAULT_DECOMPOSE_TEMPLATE = (
    "You are a careful fact-checker. Extract every distinct factual claim made in the response below. "
    "Each claim should be a single declarative sentence that can be independently verified.\n\n"
    "Response:\n{actual}\n\n"
    "Output only a valid JSON object:\n"
    "{{\"claims\": [\"claim 1\", \"claim 2\", ...]}}\n\n"
    "If there are no factual claims, return {{\"claims\": []}}"
)

_DEFAULT_VERIFY_TEMPLATE = (
    "You are a fact-checker. Determine whether the following claim is true based on your knowledge.\n\n"
    "Claim: {claim}\n\n"
    "Output only a valid JSON object:\n"
    "{{\"verified\": true or false, \"reason\": \"one sentence explanation\"}}"
)


class AtomicClaimsJudge(BaseGrader):
    """Judge that verifies factual accuracy by decomposing responses into atomic claims."""

    name: ClassVar[str] = "atomic_claims"

    def __init__(self, *, judge_runner: object, threshold: float = 0.8, system_prompt: str | None = None, decomposition_prompt_template: str | None = None, verification_prompt_template: str | None = None) -> None:
        # Stores runner, pass threshold, and optional prompt template overrides.
        self.judge_runner = judge_runner
        self.threshold = threshold
        self.system_prompt = system_prompt
        self.decomposition_prompt_template = decomposition_prompt_template
        self.verification_prompt_template = verification_prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Extracts claims from actual, verifies each concurrently, returns fractional score.
        claims = await self._extract_claims(actual)
        if not claims:
            return GraderResult(score=1.0, passed=True, reason="No factual claims found in response.")
        verdicts = await self._verify_claims(claims)
        verified_count = sum(1 for v in verdicts if v["verified"])
        score = min(1.0, max(0.0, verified_count / len(claims)))
        reason_parts = "; ".join(f"[{'✓' if v['verified'] else '✗'}] {v['claim']}: {v['reason']}" for v in verdicts)
        return GraderResult(score=score, passed=score >= self.threshold, reason=reason_parts)

    def _resolve_decompose_template(self) -> str:
        # Returns user-supplied decomposition template, SDK catalog prompt, or inline default.
        if self.decomposition_prompt_template:
            return self.decomposition_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_ATOMIC_CLAIMS_DECOMPOSE)
        except Exception:
            return _DEFAULT_DECOMPOSE_TEMPLATE

    def _resolve_verify_template(self) -> str:
        # Returns user-supplied verification template, SDK catalog prompt, or inline default.
        if self.verification_prompt_template:
            return self.verification_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_ATOMIC_CLAIMS_VERIFY)
        except Exception:
            return _DEFAULT_VERIFY_TEMPLATE

    async def _extract_claims(self, actual: str) -> list[str]:
        # Calls the judge to decompose actual into a list of atomic factual claims.
        template = self._resolve_decompose_template()
        decompose_prompt = template.format(actual=actual)
        raw = await invoke_runner(self.judge_runner, decompose_prompt)
        try:
            parsed = parse_json_block(raw)
            return [str(c) for c in parsed.get("claims", [])]
        except ValueError:
            return []

    async def _verify_claims(self, claims: list[str]) -> list[dict]:
        # Verifies each claim concurrently and returns list of verdict dicts.
        template = self._resolve_verify_template()

        async def verify_one(claim: str) -> dict:
            prompt = template.format(claim=claim)
            raw = await invoke_runner(self.judge_runner, prompt)
            try:
                parsed = parse_json_block(raw)
                return {"claim": claim, "verified": bool(parsed.get("verified", False)), "reason": str(parsed.get("reason", ""))}
            except ValueError:
                return {"claim": claim, "verified": False, "reason": "Parse error during verification."}

        return list(await asyncio.gather(*[verify_one(c) for c in claims]))
