"""FILE: vidbyte/middleware/builtins/limit_validation.py

PURPOSE: Validate numeric middleware limits before they become unenforceable run-time guardrails.
ROLE IN CODEBASE: Shared by built-in cost, token, rate, and runtime limit middleware constructors; does not depend on agent execution.
ARCHITECTURE NOTE: This private module validates configuration only and returns the original number without coercion so policy hooks own enforcement.
FUNCTION INVENTORY: positive_integer(value, name) -> int rejects non-integral or non-positive counts; positive_real(value, name) -> float rejects non-finite or non-positive numeric limits. Both raise ValueError naming the setting.
COMMON MODIFICATION PATTERNS: Add a validation rule here only if all numeric middleware guardrails must share it; keep policy-specific rules in their middleware.
WHAT NOT TO DO IN THIS FILE: 1. Do not access a runner or provider. 2. Do not silently coerce strings or booleans into numeric limits.
KNOWN EDGE CASES: bool inherits int; NaN bypasses ordered comparisons; infinity is positive but cannot be a useful limit.
RELATED DOCS: tests/features/sdk_middleware_limits/FEATURE.md describes the observable configuration boundary.
TESTS: tests/features/sdk_middleware_limits/test_middleware_limit_contract.py; full source gate scripts/run_ci.py.
"""

from __future__ import annotations

import math


def positive_integer(value: int, name: str) -> int:
    # @intent reject-invalid-numeric-guardrails
    # Boolean and fractional budgets can silently turn a bounded policy into an unexpected one.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def positive_real(value: float, name: str) -> float:
    # NaN and infinity cannot enforce time or cost ceilings even though a positive-only comparison permits them.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number.")
    return value
