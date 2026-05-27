"""Context Protocol Header

Description:
    Implements the Meta-Judge (MetaJudge).
Purpose:
    Runs a primary judge first, then passes its verdict to a meta-judge that checks
    coherence, rationale-score consistency, and criteria coverage. Filters or flags
    low-quality verdicts before they are used.
Architecture:
    - MetaJudge: Inherits BaseGrader; calls primary_judge.agrade(), then invokes
      meta_runner to QA the verdict, applies filter_on_fail policy.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_DEFAULT_META_TEMPLATE = (
    "You are a meta-judge evaluating the quality of another judge's evaluation. "
    "Check whether the verdict below is coherent, whether the reason is consistent with the score, "
    "and whether important criteria were missed.\n\n"
    "Primary Judge's Verdict:\n"
    "Score: {primary_score}\n"
    "Reason: {primary_reason}\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}\n\n"
    "Output only a valid JSON object:\n"
    "{{\"quality_ok\": true or false, \"quality_reason\": \"explanation of why the verdict is or is not high quality\"}}"
)


class MetaJudge(BaseGrader):
    """Judge-of-judges that QA-checks a primary judge's verdict before returning it."""

    name: ClassVar[str] = "meta_judge"

    def __init__(self, *, primary_judge: BaseGrader, meta_runner: object, filter_on_fail: bool = True, system_prompt: str | None = None, meta_prompt_template: str | None = None) -> None:
        # Stores the primary judge instance, meta runner, and failure-handling policy.
        self.primary_judge = primary_judge
        self.meta_runner = meta_runner
        self.filter_on_fail = filter_on_fail
        self.system_prompt = system_prompt
        self.meta_prompt_template = meta_prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Runs primary judge, then meta QA check; applies filter_on_fail policy on bad verdicts.
        primary_result = await self.primary_judge.agrade(case, actual)
        meta_template = self._resolve_meta_template()
        meta_prompt = meta_template.format(
            primary_score=primary_result.score,
            primary_reason=primary_result.reason,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.meta_runner, meta_prompt)
        return self._apply_meta_verdict(raw, primary_result)

    def _resolve_meta_template(self) -> str:
        # Returns user-supplied meta template, SDK catalog prompt, or inline default.
        if self.meta_prompt_template:
            return self.meta_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_META_JUDGE_USER)
        except Exception:
            return _DEFAULT_META_TEMPLATE

    def _apply_meta_verdict(self, raw: str, primary_result: GraderResult) -> GraderResult:
        # Parses meta response and returns filtered/flagged/passed-through result.
        try:
            parsed = parse_json_block(raw)
            quality_ok = bool(parsed.get("quality_ok", True))
            quality_reason = str(parsed.get("quality_reason", ""))
        except ValueError:
            return primary_result
        if quality_ok:
            return primary_result
        if self.filter_on_fail:
            return GraderResult(score=0.0, passed=False, reason=f"Meta-judge flagged: {quality_reason}")
        flagged_reason = f"[Meta-judge flagged] {primary_result.reason}"
        return GraderResult(score=primary_result.score, passed=primary_result.passed, reason=flagged_reason)
