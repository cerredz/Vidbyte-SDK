"""FILE: lint/rules/s008_bounded_function_complexity.py

PURPOSE: Defines S008 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps bounded function complexity findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S008.
"""

from lint.core.ruff import RuffBackedRule


class BoundedFunctionComplexityRule(RuffBackedRule):
    """Enforces the bounded-function-complexity policy."""

    id = "S008"
    name = "bounded-function-complexity"
    summary = "High branch/statement complexity makes retries, errors, and lifecycle transitions impossible to verify locally."
    codes = frozenset({"C901", "PLR0912", "PLR0915"})
    impact = "High branch/statement complexity makes retries, errors, and lifecycle transitions impossible to verify locally."
    repair = "Keep orchestration on the owning class and extract coherent private leaf methods with typed inputs/outputs."


RULE = BoundedFunctionComplexityRule()
