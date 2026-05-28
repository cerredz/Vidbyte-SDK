"""Context Protocol Header

Description:
    Implements the Self-Evaluation LLM judge (SelfEvalJudge).
Purpose:
    Uses the same model as both generator and judge, framed in third-person to reduce
    self-preference bias. Cheapest possible setup — one runner, one API key.
Architecture:
    - SelfEvalJudge: Inherits BaseGrader; selects framing header based on framing param,
      formats prompt, invokes runner, parses JSON.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

from typing import ClassVar, Literal

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.dataclasses.llm_judge import SelfEvalJudgeConfig
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()

_FRAMING_HEADERS: dict[str, str] = {
    "third_person": "another assistant's response",
    "anonymous": "an AI assistant's response",
}


class SelfEvalJudge(BaseGrader):
    """Judge that uses third-person framing to reduce self-preference bias when the runner evaluates its own output."""

    name: ClassVar[str] = "self_eval"

    def __init__(self, config: SelfEvalJudgeConfig) -> None:
        # Unpacks config fields for runner, framing mode, and optional template overrides.
        self.judge_runner = config.judge_runner
        self.framing = config.framing
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
        # Selects framing header, formats prompt, invokes runner, parses JSON score.
        template = self._resolve_template("self_eval.user", self.prompt_template, Prompt.LLM_AS_A_JUDGE_SELF_EVAL_USER)
        framing_header = _FRAMING_HEADERS.get(self.framing, _FRAMING_HEADERS["third_person"])
        prompt_text = template.format(
            framing_header=framing_header,
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, prompt_text)
        return self._parse_response(raw)

    def _parse_response(self, text: str) -> GraderResult:
        # Parses JSON score/passed/reason from the judge response.
        try:
            parsed = parse_json_block(text)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            passed = bool(parsed.get("passed", score >= 0.7))
            reason = str(parsed.get("reason", "Evaluated by self-eval judge."))
            return GraderResult(score=score, passed=passed, reason=reason)
        except ValueError:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse self-eval response: {text[:200]}")
