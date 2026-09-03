"""FILE: lint/rules/s051_modernized_import_and_syntax_hygiene.py

PURPOSE: Defines S051 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps import ordering and deprecated-typing-syntax findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S051.
"""

from lint.core.ruff import RuffBackedRule


class ModernizedImportAndSyntaxHygieneRule(RuffBackedRule):
    """Enforces sorted imports and non-deprecated typing syntax."""

    id = "S051"
    name = "modernized-import-and-syntax-hygiene"
    summary = "Imports are sorted and typing syntax avoids deprecated stdlib generics and typing_extensions shims."
    codes = frozenset({"I001", "UP006", "UP007", "UP035", "UP045"})
    impact = "Unsorted imports and deprecated typing syntax (typing.List/Optional, typing_extensions re-imports of stdlib names) make a module harder for an agent to diff and increase the chance of a stale compatibility import surviving past the SDK's minimum Python 3.11 floor."
    repair = "Let Ruff's import sort ordering stand and replace the deprecated typing construct with its modern equivalent (list[...], X | None, the stdlib name instead of typing_extensions)."


RULE = ModernizedImportAndSyntaxHygieneRule()
