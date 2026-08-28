"""FILE: lint/rules/s037_blanket_type_ignore.py

PURPOSE: Defines S037 for blanket type-ignore comments.
ROLE IN CODEBASE: Keeps mypy exceptions tied to specific, reviewed diagnostics.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not turn a type problem into an unreviewable blanket ignore.
KNOWN EDGE CASES: Ruff owns the exact type-ignore comment classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S037.
"""

from lint.core.ruff import RuffBackedRule


class BlanketTypeIgnoreRule(RuffBackedRule):
    """Requires type-ignore comments to name the diagnostic they suppress."""

    id = "S037"
    name = "blanket-type-ignore"
    summary = (
        "Type-ignore comments name the specific type diagnostic they intentionally suppress. "
        "A blanket ignore can hide unrelated type errors introduced on the same line later. "
        "That weakens the staged mypy contract and makes refactors appear safer than they are. "
        "Keep exceptions narrow enough for reviewers and future agents to audit."
    )
    codes = frozenset({"PGH003"})
    impact = (
        "Unspecified ignores erase evidence about which type contract was difficult or intentionally deferred. "
        "A new incompatible value can then pass static checks without any visible policy decision. "
        "The runtime failure may occur only for a provider or model variant not covered by the local test. "
        "Diagnostic-specific ignores preserve the remaining type signal."
    )
    repair = (
        "Add the exact mypy error code after the type-ignore marker when a suppression is genuinely required. "
        "Prefer correcting the annotation or adapter boundary when the type mismatch reflects a real ownership problem. "
        "Do not widen the ignore to several codes for convenience. "
        "Run the focused rule and the staged mypy gate after the edit."
    )


RULE = BlanketTypeIgnoreRule()
