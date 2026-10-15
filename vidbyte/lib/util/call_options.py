"""FILE: vidbyte/lib/util/call_options.py

PURPOSE:
    Narrows a set of optional keyword arguments to the ones a callable's
    signature actually accepts, so a caller can offer a hint such as
    temperature=0.0 without crashing a callable that has no such parameter.

ROLE IN CODEBASE:
    Called by the eval judge graders, LLMJudgeGrader
    (vidbyte/evals/graders/llm_judge.py) and RubricGrader
    (vidbyte/evals/graders/rubric.py), before they call a duck-typed judge
    runner such as TextModelRunner. Calls only inspect.signature.

ARCHITECTURE NOTE:
    A static-method-only class with no SDK dependencies. It returns the
    filtered keyword mapping instead of making the call itself, so sync and
    async callables are both served by the caller's own call or await.

FUNCTION INVENTORY:
    SupportedKwargs.filter(target, options) -> dict[str, Any]: the options
    the target accepts by keyword.

COMMON MODIFICATION PATTERNS:
    Add another signature-driven call helper as a @staticmethod here.

WHAT NOT TO DO IN THIS FILE:
    1. Do not import any SDK feature package.
    2. Do not count positional-only parameters; they cannot take a keyword.

KNOWN EDGE CASES:
    A callable that accepts **kwargs gets every option. A callable whose
    signature cannot be read (some builtins and C extensions) also gets every
    option, so its behavior is unchanged from passing them directly.

RELATED DOCS:
    vidbyte/agents/base.py (BaseAgent._call_with_supported_kwargs) applies the
    same rule to agent runners.

TESTS:
    tests/test_evals.py (test_judge_graders_accept_runner_without_temperature)
    covers it through both judge graders.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

KEYWORD_KINDS = frozenset({inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD})


class SupportedKwargs:
    """Static-method home for narrowing keyword options to a callable's signature."""

    @staticmethod
    def filter(target: Callable[..., object], options: Mapping[str, Any]) -> dict[str, Any]:
        """Return the options target accepts by keyword; every option when it takes **kwargs or has no readable signature."""
        # @intent optional-call-hints-match-the-callee-signature
        # An optional hint must never crash a callee that does not declare it, so drop what it cannot accept.
        try:
            parameters = inspect.signature(target).parameters.values()
        except (TypeError, ValueError):
            return dict(options)
        if any(param.kind is inspect.Parameter.VAR_KEYWORD for param in parameters):
            return dict(options)
        accepted = {param.name for param in parameters if param.kind in KEYWORD_KINDS}
        return {key: value for key, value in options.items() if key in accepted}


__all__ = ["SupportedKwargs"]
