"""FILE: lint/rules/s053_defensive_python_bugbear.py

PURPOSE: Defines S053 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Groups four related defensive-Python bugbear findings under one baseline.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S053.
"""

from lint.core.ruff import RuffBackedRule


class DefensivePythonBugbearRule(RuffBackedRule):
    """Enforces warning stacklevel, specific test exceptions, closure binding, and ContextVar defaults."""

    id = "S053"
    name = "defensive-python-bugbear"
    summary = "Warnings report the caller's frame, tests assert specific exceptions, loop closures bind their value, and ContextVars never default to a shared mutable object."
    codes = frozenset({"B017", "B023", "B028", "B039"})
    impact = "Each of these four patterns hides a real defect behind code that otherwise looks correct: a warning without stacklevel points at the wrong file, assertRaises(Exception) passes for any unrelated bug, a closure built inside a loop silently captures only the final iteration's value, and a mutable ContextVar default can leak state across concurrent contexts."
    repair = "Set warnings.warn(..., stacklevel=2) at the public call boundary; narrow the test assertion to the specific exception type the code under test actually raises; bind the loop variable as a default argument (lambda x=x: ...) or via functools.partial; give the ContextVar an immutable default (None or a frozen value) and construct fresh mutable state per use."


RULE = DefensivePythonBugbearRule()
