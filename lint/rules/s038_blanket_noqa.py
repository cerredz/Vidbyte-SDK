"""FILE: lint/rules/s038_blanket_noqa.py

PURPOSE: Defines S038 for blanket noqa comments.
ROLE IN CODEBASE: Keeps Ruff exceptions specific and reviewable.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not suppress every analyzer family on a line.
KNOWN EDGE CASES: Ruff owns the exact blanket-noqa classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S038.
"""

from lint.core.ruff import RuffBackedRule


class BlanketNoqaRule(RuffBackedRule):
    """Requires noqa comments to identify the exact Ruff exception."""

    id = "S038"
    name = "blanket-noqa"
    summary = (
        "Ruff suppression comments identify the exact diagnostic they are allowed to silence. "
        "A blanket noqa can hide correctness, security, or maintainability findings added later. "
        "It turns a local exception into a permanent blind spot for the whole line. "
        "Specific suppressions keep the SDK's analyzer signal available."
    )
    codes = frozenset({"PGH004"})
    impact = (
        "A broad suppression can conceal a new issue that has nothing to do with the original exception. "
        "That is especially dangerous at public transport, parsing, and error boundaries. "
        "Reviewers cannot tell which contract the line intentionally violates. "
        "The code should either satisfy the analyzer or state one precise exception."
    )
    repair = (
        "Replace the blanket marker with the smallest exact Ruff code that remains necessary, including a nearby reason when convention requires it. "
        "Prefer repairing the source when a canonical alternative exists. "
        "Do not move the comment, disable a plugin, or raise the baseline to preserve broad silence. "
        "Run the focused rule and the complete source gate after the edit."
    )


RULE = BlanketNoqaRule()
