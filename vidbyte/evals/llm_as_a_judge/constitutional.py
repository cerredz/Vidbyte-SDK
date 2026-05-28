"""Context Protocol Header

Description:
    Implements the Constitutional LLM judge (ConstitutionalJudge).
Purpose:
    Checks the response against a fixed list of named principles, running one binary
    check per principle in parallel. Final score = fraction of principles satisfied.
Architecture:
    - ConstitutionalJudge: Inherits BaseGrader; runs N concurrent principle checks,
      aggregates satisfied count into fractional score against threshold.
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
from vidbyte.lib.dataclasses.llm_judge import ConstitutionalJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class ConstitutionalJudge(BaseGrader):
    """Judge that verifies compliance with a fixed set of named principles."""

    name: ClassVar[str] = "constitutional"

    def __init__(self, config: ConstitutionalJudgeConfig) -> None:
        # Unpacks config fields for principles list, threshold, and template overrides.
        self.judge_runner = config.judge_runner
        self.principles = config.principles
        self.threshold = config.threshold
        self.system_prompt = config.system_prompt
        self.check_prompt_template = config.check_prompt_template

    def _resolve_template(self, slot: str, override: str | None, prompt_key: Prompt) -> str:
        # Returns override, SDK catalog prompt, or registry default in priority order.
        if override:
            return override
        try:
            return Prompts().get(prompt_key)
        except Exception:
            return _registry.get(slot)

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Runs all principle checks concurrently and aggregates satisfied fraction.
        checks = await self._run_checks(case, actual)
        violated = [c for c in checks if c["violated"]]
        satisfied_count = len(self.principles) - len(violated)
        score = min(1.0, max(0.0, satisfied_count / len(self.principles)))
        if violated:
            reason = f"Violated {len(violated)}/{len(self.principles)} principles: " + "; ".join(f"{c['principle']}: {c['reason']}" for c in violated)
        else:
            reason = f"All {len(self.principles)} principles satisfied."
        return GraderResult(score=score, passed=score >= self.threshold, reason=reason)

    async def _run_checks(self, case: EvalCase, actual: str) -> list[dict]:
        # Fires one check per principle concurrently, returns list of verdict dicts.
        template = self._resolve_template(
            "constitutional.check",
            self.check_prompt_template,
            Prompt.LLM_AS_A_JUDGE_CONSTITUTIONAL_CHECK,
        )

        async def check_one(principle: str) -> dict:
            prompt = template.format(principle=principle, prompt=case.prompt, actual=actual)
            raw = await invoke_runner(self.judge_runner, prompt)
            try:
                parsed = parse_json_block(raw)
                return {"principle": principle, "violated": bool(parsed.get("violated", False)), "reason": str(parsed.get("reason", ""))}
            except ValueError:
                return {"principle": principle, "violated": True, "reason": "Parse error — treated as violation."}

        return list(await asyncio.gather(*[check_one(p) for p in self.principles]))
