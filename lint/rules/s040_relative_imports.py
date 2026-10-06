"""FILE: lint/rules/s040_relative_imports.py

PURPOSE: Defines S040 for relative imports inside the SDK package.
ROLE IN CODEBASE: Keeps module dependencies explicit and stable across packaging.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not hide a fragile module path behind a relative import.
KNOWN EDGE CASES: Ruff owns the exact import-level classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S040.
"""

from lint.core.ruff import RuffBackedRule


class RelativeImportsRule(RuffBackedRule):
    """Requires SDK imports to name their absolute package ownership."""

    id = "S040"
    name = "relative-imports"
    summary = (
        "SDK modules use absolute imports for package-owned dependencies. "
        "Relative paths hide the import's package identity and become fragile when modules move. "
        "They can also behave differently when a file is executed or packaged under another import root. "
        "Absolute imports make the dependency graph readable to humans, tools, and agents."
    )
    codes = frozenset({"TID252"})
    impact = (
        "A relative import can resolve to a different module after a package split or entry-point change. "
        "That may produce import failures or load a similarly named module from the wrong boundary. "
        "The defect often appears only in the built wheel rather than the repository checkout. "
        "Explicit package paths reduce deployment-sensitive behavior."
    )
    repair = (
        "Rewrite the import with the full vidbyte package path and preserve the existing symbol contract. "
        "Check for cycles before moving code to make the dependency direction explicit. "
        "Do not add a path hack, manipulate sys.path, or rename the import to avoid the policy. "
        "Run the focused rule and the package import/build gate after the edit."
    )


RULE = RelativeImportsRule()
