"""FILE: lint/rules/s044_logging_f_string.py

PURPOSE: Defines S044 for f-strings passed directly to logging calls.
ROLE IN CODEBASE: Keeps SDK logs parameterized, structured, and lazily formatted.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not format sensitive or expensive values before the logger filters them.
KNOWN EDGE CASES: Ruff owns the supported logging-call classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S044.
"""

from lint.core.ruff import RuffBackedRule


class LoggingFStringRule(RuffBackedRule):
    """Requires logging calls to use the logger's parameterized message API."""

    id = "S044"
    name = "logging-f-string"
    summary = (
        "SDK logging calls pass a format string and separate values instead of an eagerly built f-string. "
        "Parameterized logging avoids formatting work when the level is disabled. "
        "It also preserves structured values for handlers, filters, and redaction. "
        "Use the logger as the owner of message formatting."
    )
    codes = frozenset({"G004"})
    impact = (
        "An f-string formats every value before the logger decides whether the event is enabled. "
        "That wastes work on hot paths and can invoke surprising string conversions. "
        "The formatted text also removes structure that observability tooling could have filtered safely. "
        "Parameterized messages keep performance and operational context intact."
    )
    repair = (
        "Change logger.info(f'...') to logger.info('...', value) using the logging API's placeholder convention. "
        "Keep secrets and large payloads out of the arguments unless the owning logging policy explicitly permits them. "
        "Do not pre-format through a helper or concatenate strings before the logger call. "
        "Run the focused rule and the affected observability test after the edit."
    )


RULE = LoggingFStringRule()
