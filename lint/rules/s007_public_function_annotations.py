"""FILE: lint/rules/s007_public_function_annotations.py

PURPOSE: Defines S007 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps public function annotations findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S007.
"""

from lint.core.ruff import RuffBackedRule


class PublicFunctionAnnotationsRule(RuffBackedRule):
    """Enforces the public-function-annotations policy."""

    id = "S007"
    name = "public-function-annotations"
    summary = "Untyped public seams hide provider, DTO, awaitability, and error contracts from callers and mypy."
    codes = frozenset({"ANN001", "ANN002", "ANN003", "ANN201", "ANN202", "ANN204", "ANN205", "ANN206"})
    impact = "Untyped public seams hide provider, DTO, awaitability, and error contracts from callers and mypy."
    repair = "Annotate public parameters/returns with the narrowest truthful type. Any remains allowed at dynamic boundaries."


RULE = PublicFunctionAnnotationsRule()
