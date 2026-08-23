"""FILE: lint/rules/s003_strict_zip.py

PURPOSE: Defines S003 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps strict zip findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S003.
"""

from lint.core.ruff import RuffBackedRule


class StrictZipRule(RuffBackedRule):
    """Enforces the strict-zip policy."""

    id = "S003"
    name = "strict-zip"
    summary = "Implicit zip truncation silently drops paired model, tool, trace, or pricing entries."
    codes = frozenset({"B905"})
    impact = "Implicit zip truncation silently drops paired model, tool, trace, or pricing entries."
    repair = "Use strict=True when lengths must match; use explicit strict=False only when truncation is the documented contract."


RULE = StrictZipRule()
