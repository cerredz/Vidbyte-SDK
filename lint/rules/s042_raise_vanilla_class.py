"""FILE: lint/rules/s042_raise_vanilla_class.py

PURPOSE: Defines S042 for raising generic builtin exception classes.
ROLE IN CODEBASE: Keeps public SDK failures typed and interpretable by callers.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not replace a boundary error with a bare Exception.
KNOWN EDGE CASES: Review whether an internal low-level raise needs a typed SDK error.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S042.
"""

from lint.core.ruff import RuffBackedRule


class RaiseVanillaClassRule(RuffBackedRule):
    """Requires runtime failures to use an intentional exception type."""

    id = "S042"
    name = "raise-vanilla-class"
    summary = (
        "SDK runtime boundaries do not raise vague builtin exception classes as their public contract. "
        "A generic class hides whether the caller should retry, fix input, reauthenticate, or report a provider failure. "
        "It also prevents stable error fields from crossing the SDK boundary. "
        "Raise a repository-owned or precisely typed exception that names the failure semantics."
    )
    codes = frozenset({"TRY002"})
    impact = (
        "Callers receiving Exception or another vague class cannot reliably branch on a stable SDK failure category. "
        "They may retry a permanent input error or expose an internal implementation detail to a user. "
        "The ambiguity spreads into agent behavior, telemetry, and support diagnostics. "
        "Typed errors make the recovery contract explicit."
    )
    repair = (
        "Raise the closest existing SDK error class and populate its stable context fields, or define a narrowly named error at the owning boundary. "
        "Preserve the original cause when translating an underlying exception. "
        "Do not evade the rule by raising through a helper or changing only the class spelling. "
        "Run the focused rule and the affected error-contract tests after the edit."
    )


RULE = RaiseVanillaClassRule()
