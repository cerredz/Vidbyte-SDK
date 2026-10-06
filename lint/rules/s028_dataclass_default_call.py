"""FILE: lint/rules/s028_dataclass_default_call.py

PURPOSE: Defines S028 for calls evaluated while a dataclass class is created.
ROLE IN CODEBASE: Keeps dataclass defaults deterministic and instance-owned.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not silence eager default evaluation with noqa.
KNOWN EDGE CASES: Ruff owns the exact call-in-default classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S028.
"""

from lint.core.ruff import RuffBackedRule


class DataclassDefaultCallRule(RuffBackedRule):
    """Requires dataclass defaults to avoid eager function calls."""

    id = "S028"
    name = "dataclass-default-call"
    summary = (
        "Dataclass field defaults do not call functions during class definition. "
        "An eager call runs once when the module is imported rather than when an instance is built. "
        "That can freeze time, consume resources, or share a value across instances. "
        "Use a default factory when construction-time evaluation is intended."
    )
    codes = frozenset({"RUF009"})
    impact = (
        "Import-time evaluation can make SDK configuration stale before the first request. "
        "It can also perform I/O or create one object that every instance reuses. "
        "The resulting lifetime mismatch is difficult to diagnose from a constructor call site. "
        "Dataclass defaults should describe ownership and evaluation timing explicitly."
    )
    repair = (
        "Move the call into dataclasses.field(default_factory=...) when a fresh value is required per instance. "
        "Use a literal only for immutable values whose import-time identity is harmless. "
        "Do not wrap the same eager call in another helper just to change its spelling. "
        "Run the focused rule and construct multiple instances to verify their ownership."
    )


RULE = DataclassDefaultCallRule()
