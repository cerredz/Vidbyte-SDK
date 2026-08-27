"""FILE: lint/rules/s002_exception_cause_chaining.py

PURPOSE: Defines S002 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps exception cause chaining findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S002.
"""

from lint.core.ruff import RuffBackedRule


class ExceptionCauseChainingRule(RuffBackedRule):
    """Enforces the exception-cause-chaining policy."""

    id = "S002"
    name = "exception-cause-chaining"
    summary = "Provider and protocol translations lose the originating failure without explicit chaining."
    codes = frozenset({"B904"})
    impact = "Provider and protocol translations lose the originating failure without explicit chaining."
    repair = "Raise the typed replacement from the caught exception; use from None only for an intentionally hidden implementation cause."


RULE = ExceptionCauseChainingRule()
