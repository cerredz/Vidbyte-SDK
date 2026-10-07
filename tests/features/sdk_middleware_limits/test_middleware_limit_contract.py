"""FILE: tests/features/sdk_middleware_limits/test_middleware_limit_contract.py

PURPOSE: Reject unusable built-in middleware budgets at construction, before any run begins.
ROLE IN CODEBASE: Exercises public constructors of cost, runtime, token-budget and rate-limit middleware; complements tests/test_middleware_builtins.py.
ARCHITECTURE NOTE: No provider or runner is involved, so a failure identifies numeric validation rather than asynchronous hook behavior.
FUNCTION INVENTORY: test_invalid_count_limit tests every count field; test_invalid_real_limit tests every duration or cost field; test_valid_limits_remain_unchanged tests constructor persistence.
COMMON MODIFICATION PATTERNS: Add a field to the field tables when a new public numeric middleware guardrail is introduced.
WHAT NOT TO DO IN THIS FILE: 1. Do not implement validation here; vidbyte/middleware/builtins/ owns it. 2. Do not make provider calls; this boundary needs no network.
KNOWN EDGE CASES: Boolean subclasses integer; NaN bypasses ordered comparisons; numeric strings can leak TypeError.
RELATED DOCS: tests/features/sdk_middleware_limits/FEATURE.md defines the contract.
TESTS: This module and the full source gate in scripts/run_ci.py.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest

from vidbyte.middleware.builtins import (
    CostBudgetMiddleware,
    RuntimeLimitMiddleware,
    TokenBudgetMiddleware,
    TokenRateLimitMiddleware,
)

COUNT_FIELDS = (
    (lambda value: RuntimeLimitMiddleware(max_model_calls=value), "max_model_calls"),
    (lambda value: RuntimeLimitMiddleware(max_tool_calls=value), "max_tool_calls"),
    (lambda value: TokenBudgetMiddleware(max_tokens=value), "max_tokens"),
    (lambda value: TokenRateLimitMiddleware(max_tokens=value, per_seconds=1), "max_tokens"),
)
REAL_FIELDS = (
    (lambda value: RuntimeLimitMiddleware(max_elapsed_seconds=value), "max_elapsed_seconds"),
    (lambda value: CostBudgetMiddleware(max_spend_usd=value, cost_per_million_tokens=1), "max_spend_usd"),
    (lambda value: CostBudgetMiddleware(max_spend_usd=1, cost_per_million_tokens=value), "cost_per_million_tokens"),
    (lambda value: TokenRateLimitMiddleware(max_tokens=1, per_seconds=value), "per_seconds"),
)


@pytest.mark.parametrize("construct,field", COUNT_FIELDS)
@pytest.mark.parametrize("value", [True, 1.5, "4", 0, -1])
def test_invalid_count_limit(construct: Callable[[object], object], field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        construct(value)


@pytest.mark.parametrize("construct,field", REAL_FIELDS)
@pytest.mark.parametrize("value", [True, "1", math.nan, math.inf, -math.inf, 0, -1])
def test_invalid_real_limit(construct: Callable[[object], object], field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        construct(value)


def test_valid_limits_remain_unchanged() -> None:
    assert RuntimeLimitMiddleware(max_model_calls=1, max_elapsed_seconds=0.25).max_elapsed_seconds == 0.25
    assert CostBudgetMiddleware(max_spend_usd=0.25, cost_per_million_tokens=1).max_spend_usd == 0.25
    assert TokenBudgetMiddleware(max_tokens=1).max_tokens == 1
    assert TokenRateLimitMiddleware(max_tokens=1, per_seconds=0.25).per_seconds == 0.25
