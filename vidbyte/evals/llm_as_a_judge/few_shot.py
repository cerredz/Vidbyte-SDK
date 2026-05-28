"""Context Protocol Header

Description:
    Implements the Few-Shot LLM judge (FewShotJudge).
Purpose:
    Prepends calibrated worked examples to the evaluation prompt so the judge's
    scale is anchored to developer intent and stays consistent across runs.
Architecture:
    - FewShotJudge: Inherits BaseGrader; validates and serialises examples, formats
      prompt with examples block, invokes runner, parses JSON score.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.dataclasses.llm_judge import FewShotJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()


class FewShotJudge(BaseGrader):
    """Judge that uses calibrated worked examples to anchor scale consistency."""

    name: ClassVar[str] = "few_shot"

    def __init__(self, config: FewShotJudgeConfig) -> None:
        # Unpacks config fields for examples list, runner, and optional prompt overrides.
        self.judge_runner = config.judge_runner
        self.examples = config.examples
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
        # Serialises examples, formats prompt with examples block, invokes judge, parses JSON.
        template = self._resolve_template("few_shot.user", self.prompt_template, Prompt.LLM_AS_A_JUDGE_FEW_SHOT_USER)
        examples_block = self._serialise_examples()
        prompt_text = template.format(
            examples_block=examples_block,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, prompt_text)
        return self._parse_response(raw)

    def _serialise_examples(self) -> str:
        # Formats each example dict into a numbered readable block for the prompt.
        lines: list[str] = []
        for i, ex in enumerate(self.examples, 1):
            lines.append(f"Example {i}:")
            lines.append(f"  Prompt: {ex['prompt']}")
            lines.append(f"  Response: {ex['actual']}")
            lines.append(f"  Expected: {ex['expected']}")
            lines.append(f"  Score: {ex['score']}")
            lines.append(f"  Reason: {ex['reason']}")
            lines.append("")
        return "\n".join(lines).strip()

    def _parse_response(self, text: str) -> GraderResult:
        # Parses JSON score/passed/reason from the judge response.
        try:
            parsed = parse_json_block(text)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            passed = bool(parsed.get("passed", score >= 0.7))
            reason = str(parsed.get("reason", "Evaluated by few-shot judge."))
            return GraderResult(score=score, passed=passed, reason=reason)
        except ValueError:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse few-shot judge response: {text[:200]}")
