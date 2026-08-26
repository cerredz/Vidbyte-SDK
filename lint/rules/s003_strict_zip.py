"""FILE: lint/rules/s003_strict_zip.py

PURPOSE: Defines S003 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps strict zip findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S003.
"""

from lint.core.ruff import RuffBackedRule


class StrictZipRule(RuffBackedRule):
    """Enforces the strict-zip policy."""

    id = "S003"
    name = "strict-zip"
    summary = (
        "This rule makes the length contract of paired iteration visible at every zip call. "
        "It protects model metadata, tool results, trace records, pricing entries, and other sequences whose positions carry meaning together. "
        "The finding asks the author to decide whether unequal inputs are an error or an intentional truncation policy. "
        "That decision prevents Python's default silent truncation from becoming an invisible data-loss path."
    )
    codes = frozenset({"B905"})
    impact = (
        "When two sequences differ in length, an implicit zip stops at the shorter sequence without reporting which records were discarded. "
        "A dropped model, tool, trace, or billing item can leave downstream state apparently valid while silently omitting work. "
        "The resulting mismatch may surface much later as missing usage, incomplete context, or a wrong association between records. "
        "Because the loss is silent, a baseline-clean lint result is the cheapest place to force the contract into the code."
    )
    repair = (
        "Determine whether the paired inputs must have equal cardinality by reading the surrounding contract and the producer of each sequence. "
        "Use strict=True when a mismatch indicates corrupted or incomplete state, and add a typed validation path if the caller needs a custom error. "
        "Use explicit strict=False only when dropping the tail is deliberate, bounded, and explained beside the call. "
        "Run the focused rule and the relevant result or accounting checks to confirm the chosen length behavior is observable."
    )
    examples = (
        "zip(models, results, strict=True) when each model must have one result",
        "zip(optional_items, fallback_items, strict=False) only with a documented truncation contract",
    )
    will_not_work = (
        "Leaving the default zip behavior and relying on callers to notice a shorter result.",
        "Adding a length check elsewhere while keeping an unannotated zip at the data boundary.",
    )


RULE = StrictZipRule()
