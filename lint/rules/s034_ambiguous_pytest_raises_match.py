"""FILE: lint/rules/s034_ambiguous_pytest_raises_match.py

PURPOSE: Defines S034 for ambiguous pytest.raises match patterns.
ROLE IN CODEBASE: Keeps SDK exception tests precise about the public error text.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not weaken a test regex merely to silence the rule.
KNOWN EDGE CASES: Ruff owns the regex ambiguity classification in tests.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S034.
"""

from lint.core.ruff import RuffBackedRule


class AmbiguousPytestRaisesMatchRule(RuffBackedRule):
    """Requires pytest.raises match patterns to express their intended text precisely."""

    id = "S034"
    name = "ambiguous-pytest-raises-match"
    summary = (
        "pytest.raises match patterns do not accidentally mean something broader than the test author intended. "
        "Ambiguous regular-expression syntax can let the wrong error message satisfy a test. "
        "That weakens evidence for the SDK's typed and redacted exception contract. "
        "Make punctuation and grouping explicit in the expected pattern."
    )
    codes = frozenset({"RUF043"})
    impact = (
        "A permissive or ambiguous match can pass after an unrelated message change. "
        "The test then stops protecting callers from unstable error text or accidental disclosure. "
        "Failures may only surface when a downstream consumer relies on the documented wording. "
        "Exception tests should fail for the exact contract change they are meant to catch."
    )
    repair = (
        "Escape literal punctuation or add grouping so the regular expression matches the intended message shape. "
        "Prefer a stable typed error field when the repository exposes one instead of matching incidental prose. "
        "Do not replace the pattern with a broad wildcard or delete the match assertion. "
        "Run the focused rule and the affected pytest module after the edit."
    )


RULE = AmbiguousPytestRaisesMatchRule()
