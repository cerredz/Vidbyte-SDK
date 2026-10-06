"""FILE: lint/rules/s026_pairwise_zip.py

PURPOSE: Defines S026 for explicit paired-iteration length behavior.
ROLE IN CODEBASE: Prevents zip from silently truncating SDK data streams.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not suppress a length contract with noqa.
KNOWN EDGE CASES: Ruff owns the exact pairwise syntax classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S026.
"""

from lint.core.ruff import RuffBackedRule


class PairwiseZipRule(RuffBackedRule):
    """Requires zip calls to state how unequal inputs should behave."""

    id = "S026"
    name = "pairwise-zip"
    summary = (
        "Paired iteration declares its behavior when input lengths differ. "
        "Plain zip silently stops at the shortest input. "
        "That truncation can drop SDK records without an exception. "
        "Use an explicit strict or otherwise intentional length policy."
    )
    codes = frozenset({"RUF007"})
    impact = (
        "A short response, mismatched batch, or provider drift can make plain zip discard trailing values. "
        "The caller then receives incomplete work while believing every item was paired. "
        "Because the loss is silent, retries and logs may not reveal the original mismatch. "
        "An explicit length policy turns that hidden data loss into a deliberate contract."
    )
    repair = (
        "Use zip(..., strict=True) when unequal lengths are invalid, or write an explicit branch when truncation is intentional. "
        "Keep the choice next to the pairing operation so a future caller can see the contract. "
        "Do not merely rename the iterable or add a comment while leaving silent truncation. "
        "Run the focused rule and the affected pairing test after the edit."
    )


RULE = PairwiseZipRule()
