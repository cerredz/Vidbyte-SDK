"""Context Protocol Header

Description:
    Implements the Binary LLM judge (BinaryJudge).
Purpose:
    Asks the judge a single yes/no question defined by a user-supplied criterion.
    Suited for safety checks, hallucination flags, and format compliance tests.
Architecture:
    - BinaryJudge: Inherits BaseGrader; validates criterion, formats prompt,
      parses yes/no keywords or JSON fallback, returns binary GraderResult.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

import re
from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.dataclasses.llm_judge import BinaryJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()

_YES_PATTERN = re.compile(r"\b(yes|pass|true)\b", re.IGNORECASE)
_NO_PATTERN = re.compile(r"\b(no|fail|false)\b", re.IGNORECASE)


class BinaryJudge(BaseGrader):
    """Judge that answers a single yes/no criterion question about a response."""

    name: ClassVar[str] = "binary"

    def __init__(self, config: BinaryJudgeConfig) -> None:
        # Unpacks config fields for runner, criterion, and optional prompt overrides.
        self.judge_runner = config.judge_runner
        self.criterion = config.criterion
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
        # Formats the binary criterion prompt, invokes the judge, and parses pass/fail.
        template = self._resolve_template("binary.user", self.prompt_template, Prompt.LLM_AS_A_JUDGE_BINARY_USER)
        prompt_text = template.format(
            criterion=self.criterion,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, prompt_text)
        return self._parse_response(raw)

    def _parse_response(self, text: str) -> GraderResult:
        # Scans first 100 chars for yes/no keywords; falls back to JSON {"passed": bool}.
        snippet = text[:100]
        if _YES_PATTERN.search(snippet):
            return GraderResult(score=1.0, passed=True, reason=text.strip())
        if _NO_PATTERN.search(snippet):
            return GraderResult(score=0.0, passed=False, reason=text.strip())
        try:
            parsed = parse_json_block(text)
            passed = bool(parsed.get("passed", False))
            reason = str(parsed.get("reason", "Binary judge verdict."))
            return GraderResult(score=1.0 if passed else 0.0, passed=passed, reason=reason)
        except ValueError:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse binary judge response: {text[:200]}")
