"""FILE: lint/rules/s033_mutable_dict_fromkeys.py

PURPOSE: Defines S033 for mutable values shared by dict.fromkeys.
ROLE IN CODEBASE: Prevents one SDK mapping mutation from changing every key.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not use a shared mutable sentinel when keys need ownership.
KNOWN EDGE CASES: Ruff owns the exact dict.fromkeys classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S033.
"""

from lint.core.ruff import RuffBackedRule


class MutableDictFromkeysRule(RuffBackedRule):
    """Requires dict.fromkeys values to be immutable or independently created."""

    id = "S033"
    name = "mutable-dict-fromkeys"
    summary = (
        "dict.fromkeys does not use one mutable object as the value for every key. "
        "The constructor intentionally shares its value reference across all entries. "
        "Mutating one entry can therefore mutate the apparent value of every sibling key. "
        "Build independent values when each key owns a collection."
    )
    codes = frozenset({"RUF024"})
    impact = (
        "Shared values can leak state between tools, providers, or request-specific buckets. "
        "The resulting corruption depends on which key is mutated first and can survive in a long-lived process. "
        "A shallow inspection of one key may hide the mutation already visible through the others. "
        "Mapping construction must preserve per-key ownership when values are mutable."
    )
    repair = (
        "Use a comprehension that creates a fresh list, set, or dictionary for each key. "
        "Keep an immutable shared value only when the mapping contract explicitly forbids mutation. "
        "Do not copy the mapping after construction because the inner values would remain aliased. "
        "Run the focused rule and mutate two keys independently to verify isolation."
    )


RULE = MutableDictFromkeysRule()
