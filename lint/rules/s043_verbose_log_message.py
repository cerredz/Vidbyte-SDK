"""FILE: lint/rules/s043_verbose_log_message.py

PURPOSE: Defines S043 for logging caught exceptions with redundant verbose text.
ROLE IN CODEBASE: Keeps SDK logs structured and avoids duplicate exception payloads.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not stringify a caught exception into a log message unnecessarily.
KNOWN EDGE CASES: Ruff owns the exception-logging classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S043.
"""

from lint.core.ruff import RuffBackedRule


class VerboseLogMessageRule(RuffBackedRule):
    """Requires exception logs to retain structured exception information without duplication."""

    id = "S043"
    name = "verbose-log-message"
    summary = (
        "Caught exceptions are logged through the logger's structured exception support. "
        "Including the same exception text in the message duplicates output and can fragment searchable fields. "
        "It can also accidentally expose more raw detail than the SDK's public error policy allows. "
        "Keep the message stable and let the logging mechanism carry exception context."
    )
    codes = frozenset({"TRY401"})
    impact = (
        "Duplicated exception text makes logs noisy and harder to aggregate across providers and retries. "
        "Raw details may contain URLs, payload fragments, or credentials that should remain internal. "
        "Operators then lose a clean distinction between stable event context and exception diagnostics. "
        "Structured logging supports both safe redaction and reliable investigation."
    )
    repair = (
        "Use logger.exception or the repository's structured exception field with a stable event message. "
        "Redact sensitive values before they reach the logger and keep public error text separate from internal traces. "
        "Do not simply shorten the f-string while still embedding the caught exception. "
        "Run the focused rule and the relevant logging/error-path test after the edit."
    )


RULE = VerboseLogMessageRule()
