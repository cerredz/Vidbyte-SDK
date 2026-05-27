"""Context Protocol Header

Description:
    Implements the Mixture-of-Prompts judge (MixtureOfPromptsJudge).
Purpose:
    Dynamically routes each evaluation to the most appropriate prompt template based
    on input characteristics. Router can be an LLM call or a user-provided callable.
Architecture:
    - MixtureOfPromptsJudge: Inherits BaseGrader; routes via router_fn or router_runner,
      selects template from prompt_library, invokes judge, parses JSON.
Relations:
    Related to vidbyte.evals.base (BaseGrader), vidbyte.evals.types (EvalCase, GraderResult),
    vidbyte.evals.llm_as_a_judge._utils (invoke_runner, parse_json_block).
"""

from __future__ import annotations

import re
from typing import Callable, ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.llm_as_a_judge._utils import invoke_runner, parse_json_block
from vidbyte.evals.types import EvalCase, GraderResult
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_DEFAULT_ROUTER_TEMPLATE = (
    "You are a task classifier. Given a prompt, identify which task type it belongs to from the list below.\n\n"
    "Available task types:\n{task_types}\n\n"
    "Output only the exact task type name that best matches. No explanation, no punctuation — just the name.\n\n"
    "Prompt to classify:\n{prompt}"
)


class MixtureOfPromptsJudge(BaseGrader):
    """Judge that routes each evaluation to a specialised prompt template based on task type."""

    name: ClassVar[str] = "mixture_of_prompts"

    def __init__(self, *, judge_runner: object, prompt_library: dict[str, str], router_runner: object | None = None, router_fn: Callable[[str], str] | None = None, fallback_key: str | None = None, system_prompt: str | None = None, router_prompt_template: str | None = None) -> None:
        # Validates prompt_library is non-empty; stores routing configuration.
        if not prompt_library:
            raise ValueError("MixtureOfPromptsJudge requires a non-empty prompt_library.")
        self.judge_runner = judge_runner
        self.prompt_library = prompt_library
        self.router_runner = router_runner
        self.router_fn = router_fn
        self.fallback_key = fallback_key
        self.system_prompt = system_prompt
        self.router_prompt_template = router_prompt_template

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Routes case to best template, formats it, invokes judge, parses JSON.
        selected_key = await self._route(case.prompt)
        template = self._select_template(selected_key)
        prompt_text = template.format(
            prompt=case.prompt,
            actual=actual,
            expected=case.expected if case.expected is not None else "None specified.",
        )
        raw = await invoke_runner(self.judge_runner, prompt_text)
        return self._parse_response(raw, selected_key)

    def _resolve_router_template(self) -> str:
        # Returns user-supplied router template, SDK catalog prompt, or inline default.
        if self.router_prompt_template:
            return self.router_prompt_template
        try:
            return Prompts().get(Prompt.LLM_AS_A_JUDGE_MIXTURE_OF_PROMPTS_ROUTER)
        except Exception:
            return _DEFAULT_ROUTER_TEMPLATE

    async def _route(self, prompt: str) -> str:
        # Determines the task type key via router_fn, router_runner, or fallback_key.
        if self.router_fn is not None:
            return self.router_fn(prompt)
        if self.router_runner is not None:
            task_types_str = "\n".join(f"- {k}" for k in self.prompt_library.keys())
            router_template = self._resolve_router_template()
            router_prompt = router_template.format(task_types=task_types_str, prompt=prompt)
            raw = await invoke_runner(self.router_runner, router_prompt)
            return self._extract_key_from_router_response(raw)
        if self.fallback_key is not None:
            return self.fallback_key
        return next(iter(self.prompt_library))

    def _extract_key_from_router_response(self, raw: str) -> str:
        # Extracts the task type key from router response via JSON or first-word heuristic.
        try:
            parsed = parse_json_block(raw)
            for candidate in parsed.values():
                if isinstance(candidate, str) and candidate in self.prompt_library:
                    return candidate
        except ValueError:
            pass
        first_word = re.split(r"[\s\n.,!?]", raw.strip())[0].strip()
        if first_word in self.prompt_library:
            return first_word
        if self.fallback_key is not None:
            return self.fallback_key
        return next(iter(self.prompt_library))

    def _select_template(self, key: str) -> str:
        # Looks up key in prompt_library; falls back to fallback_key or raises KeyError.
        if key in self.prompt_library:
            return self.prompt_library[key]
        if self.fallback_key and self.fallback_key in self.prompt_library:
            return self.prompt_library[self.fallback_key]
        raise KeyError(f"Key '{key}' not found in prompt_library and no valid fallback_key set.")

    def _parse_response(self, text: str, selected_key: str) -> GraderResult:
        # Parses JSON score/passed/reason from the judge response.
        try:
            parsed = parse_json_block(text)
            score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
            passed = bool(parsed.get("passed", score >= 0.7))
            reason = str(parsed.get("reason", f"Evaluated using '{selected_key}' template."))
            return GraderResult(score=score, passed=passed, reason=reason)
        except ValueError:
            return GraderResult(score=0.0, passed=False, reason=f"Could not parse MoPs judge response: {text[:200]}")
