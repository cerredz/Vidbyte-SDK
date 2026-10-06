"""FILE: lint/rules/s027_mutable_dataclass_default.py

PURPOSE: Defines S027 for mutable dataclass field defaults.
ROLE IN CODEBASE: Keeps per-instance SDK state from being shared accidentally.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not hide shared state behind a suppression.
KNOWN EDGE CASES: Ruff identifies mutable defaults in dataclass declarations.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S027.
"""

from lint.core.ruff import RuffBackedRule


class MutableDataclassDefaultRule(RuffBackedRule):
    """Requires mutable dataclass fields to create owned values per instance."""

    id = "S027"
    name = "mutable-dataclass-default"
    summary = (
        "Dataclass fields do not share mutable defaults across instances. "
        "A list, dictionary, or set written directly as a default is allocated once. "
        "One SDK object can therefore mutate another object's state unexpectedly. "
        "Use a factory when each instance owns a fresh container."
    )
    codes = frozenset({"RUF008"})
    impact = (
        "Shared mutable defaults create cross-request state leakage and order-dependent behavior. "
        "A mutation performed by one tool, transport, or workflow can appear in a later independent instance. "
        "Tests may pass in isolation while a long-lived process accumulates stale values. "
        "Per-instance ownership is required for predictable SDK state."
    )
    repair = (
        "Replace the mutable literal with dataclasses.field(default_factory=...). "
        "Choose a factory that returns the intended empty or initial value for every instance. "
        "If sharing is deliberate, model that ownership explicitly outside the dataclass field default. "
        "Run the focused rule and an instance-isolation test after the edit."
    )


RULE = MutableDataclassDefaultRule()
