"""FILE: lint/rules/s004_timezone_aware_datetime.py

PURPOSE: Defines S004 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps timezone aware datetime findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S004.
"""

from lint.core.ruff import RuffBackedRule


class TimezoneAwareDatetimeRule(RuffBackedRule):
    """Enforces the timezone-aware-datetime policy."""

    id = "S004"
    name = "timezone-aware-datetime"
    summary = "Naive timestamps drift across trace, retry, evaluation, and persistence boundaries."
    prefixes = ("DTZ",)
    impact = "Naive timestamps drift across trace, retry, evaluation, and persistence boundaries."
    repair = "Use timezone-aware UTC construction and retain explicit zones while parsing/converting timestamps."


RULE = TimezoneAwareDatetimeRule()
