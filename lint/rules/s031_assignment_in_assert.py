"""FILE: lint/rules/s031_assignment_in_assert.py

PURPOSE: Defines S031 for assignments hidden inside assert expressions.
ROLE IN CODEBASE: Keeps validation logic active under optimized Python execution.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not use assert as a production assignment mechanism.
KNOWN EDGE CASES: Ruff owns the exact walrus-in-assert classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S031.
"""

from lint.core.ruff import RuffBackedRule


class AssignmentInAssertRule(RuffBackedRule):
    """Requires assignments used by validation to be separate from assert."""

    id = "S031"
    name = "assignment-in-assert"
    summary = (
        "Assertions do not hide assignments that production logic depends on. "
        "Python can remove assert statements when optimized, removing the assignment with them. "
        "The same code can therefore validate correctly in development and skip work in deployment. "
        "Compute the value explicitly before making a validation decision."
    )
    codes = frozenset({"RUF018"})
    impact = (
        "An assignment inside assert may disappear under -O and leave a later variable undefined or stale. "
        "That creates environment-dependent behavior at exactly the boundary where input safety should be stable. "
        "A test runner may not use the same optimization mode as an installed SDK consumer. "
        "Validation and computation need independent, always-executed statements."
    )
    repair = (
        "Move the assignment to a normal statement, then assert or raise based on the computed value. "
        "Use a typed exception when the condition is part of a public runtime contract. "
        "Do not turn off optimization assumptions or wrap the assignment in another assertion. "
        "Run the focused rule and the boundary test under the intended interpreter settings."
    )


RULE = AssignmentInAssertRule()
