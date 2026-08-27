"""FILE: lint/rules/s005_immutable_class_defaults.py

PURPOSE: Defines S005 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps immutable class defaults findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S005.
"""

from lint.core.ruff import RuffBackedRule


class ImmutableClassDefaultsRule(RuffBackedRule):
    """Enforces the immutable-class-defaults policy."""

    id = "S005"
    name = "immutable-class-defaults"
    summary = "Mutable class defaults leak state across SDK instances and test order unless sharing is explicit."
    codes = frozenset({"RUF012"})
    impact = "Mutable class defaults leak state across SDK instances and test order unless sharing is explicit."
    repair = "Move per-instance state to initialization/default factories or annotate intentional immutable shared state with ClassVar."


RULE = ImmutableClassDefaultsRule()
