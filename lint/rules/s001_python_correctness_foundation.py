"""FILE: lint/rules/s001_python_correctness_foundation.py

PURPOSE: Defines S001 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps python correctness foundation findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S001.
"""

from lint.core.ruff import RuffBackedRule


class PythonCorrectnessFoundationRule(RuffBackedRule):
    """Enforces the python-correctness-foundation policy."""

    id = "S001"
    name = "python-correctness-foundation"
    summary = "Undefined names, broken imports, and syntax-class failures make package imports or runtime paths fail."
    prefixes = ("F", "E4", "E7", "E9")
    impact = "Undefined names, broken imports, and syntax-class failures make package imports or runtime paths fail."
    repair = "Apply the exact Ruff correction: define/import required names, remove stale imports, and repair syntax without blanket ignores."


RULE = PythonCorrectnessFoundationRule()
