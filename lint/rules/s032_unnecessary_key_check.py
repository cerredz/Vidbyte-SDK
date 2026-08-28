"""FILE: lint/rules/s032_unnecessary_key_check.py

PURPOSE: Defines S032 for redundant dictionary key existence checks.
ROLE IN CODEBASE: Keeps SDK mapping access direct and semantically clear.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not preserve redundant membership work as defensive noise.
KNOWN EDGE CASES: Ruff owns the exact dictionary-key pattern classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S032.
"""

from lint.core.ruff import RuffBackedRule


class UnnecessaryKeyCheckRule(RuffBackedRule):
    """Requires dictionary access to express whether a missing key is allowed."""

    id = "S032"
    name = "unnecessary-key-check"
    summary = (
        "Dictionary code does not check a key redundantly before immediately indexing it. "
        "The membership test duplicates the lookup and can obscure the actual missing-key policy. "
        "It may also create a check-then-use gap when the mapping is not an ordinary local dict. "
        "Use direct access, get, or an explicit exception branch for the intended behavior."
    )
    codes = frozenset({"RUF019"})
    impact = (
        "Redundant checks make callers harder to audit because the meaningful missing-key behavior is split across two operations. "
        "They add work on hot mapping paths and invite inconsistent handling when the access changes later. "
        "A caller may think absence is handled when the following index still raises. "
        "One operation should state the ownership and error contract."
    )
    repair = (
        "Replace the membership-plus-index shape with mapping.get, direct indexing inside a deliberate try branch, or a clear conditional value path. "
        "Preserve the existing result for present and absent keys. "
        "Do not simply delete the membership test if the code then loses a required fallback. "
        "Run the focused rule and both key-presence cases after the edit."
    )


RULE = UnnecessaryKeyCheckRule()
