"""FILE: lint/rules/s029_unnecessary_first_element_allocation.py

PURPOSE: Defines S029 for first-element access that allocates an unnecessary container.
ROLE IN CODEBASE: Keeps SDK selection paths direct and bounded.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not retain a full temporary collection for one value.
KNOWN EDGE CASES: Ruff owns the supported iterable and indexing patterns.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S029.
"""

from lint.core.ruff import RuffBackedRule


class UnnecessaryFirstElementAllocationRule(RuffBackedRule):
    """Requires first-element access to avoid building a complete temporary iterable."""

    id = "S029"
    name = "unnecessary-first-element-allocation"
    summary = (
        "Selecting the first item does not build a complete temporary list or tuple. "
        "Materializing an iterable before reading index zero spends memory and work on discarded values. "
        "This is especially costly for provider results and large SDK collections. "
        "Use an iterator-oriented first-item operation when that matches the intended empty behavior."
    )
    codes = frozenset({"RUF015"})
    impact = (
        "A collection path can consume an entire response merely to return its first element. "
        "That increases latency and memory pressure at a boundary where callers expect bounded selection. "
        "For generators or remote-backed iterables, the allocation can also change evaluation behavior. "
        "Keeping selection lazy preserves the SDK's resource and ownership contract."
    )
    repair = (
        "Use next(iterable) or the repository's established first-item helper, with an explicit default or exception policy. "
        "Preserve the current behavior for empty inputs rather than introducing a new silent fallback. "
        "Do not merely assign the materialized collection to a shorter variable. "
        "Run the focused rule and an empty/non-empty boundary check after the edit."
    )


RULE = UnnecessaryFirstElementAllocationRule()
