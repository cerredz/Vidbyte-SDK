"""FILE: lint/rules/s035_unused_noqa.py

PURPOSE: Defines S035 for stale noqa directives.
ROLE IN CODEBASE: Keeps lint suppressions aligned with findings that actually exist.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not retain dead suppression comments as historical decoration.
KNOWN EDGE CASES: Ruff owns the active-directive and unused-code classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S035.
"""

from lint.core.ruff import RuffBackedRule


class UnusedNoqaRule(RuffBackedRule):
    """Requires noqa directives to suppress a finding that is still present."""

    id = "S035"
    name = "unused-noqa"
    summary = (
        "Every noqa directive corresponds to a current analyzer finding. "
        "A stale suppression hides the reason a line was once exceptional. "
        "It also makes future policy changes harder to review because the comment looks authoritative. "
        "Remove dead suppressions or replace them with a narrowly justified active one."
    )
    codes = frozenset({"RUF100"})
    impact = (
        "Dead suppressions create false confidence that a line has an intentional exception. "
        "They accumulate after refactors and can hide a new violation when a neighboring expression changes. "
        "Future agents may preserve the comment without understanding the original context. "
        "The lint surface should show only exceptions that still have an observable reason."
    )
    repair = (
        "Delete the unused noqa directive, or change it to the exact active code only when the exception is still necessary. "
        "Document a legitimate boundary in the owning rule or source convention rather than leaving a broad marker. "
        "Do not move the comment to another line to make Ruff accept it. "
        "Run the focused rule and the relevant source gate after the edit."
    )


RULE = UnusedNoqaRule()
