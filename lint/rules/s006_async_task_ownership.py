"""FILE: lint/rules/s006_async_task_ownership.py

PURPOSE: Defines S006 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps async task ownership findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S006.
"""

from lint.core.ruff import RuffBackedRule


class AsyncTaskOwnershipRule(RuffBackedRule):
    """Enforces the async-task-ownership policy."""

    id = "S006"
    name = "async-task-ownership"
    summary = "Unowned tasks can be collected, lose exceptions, or outlive their agent/runtime lifecycle."
    codes = frozenset({"RUF006"})
    impact = "Unowned tasks can be collected, lose exceptions, or outlive their agent/runtime lifecycle."
    repair = "Retain the task in an owning registry/task group and await or cancel it during lifecycle teardown."


RULE = AsyncTaskOwnershipRule()
