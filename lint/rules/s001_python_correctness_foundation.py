"""FILE: lint/rules/s001_python_correctness_foundation.py

PURPOSE: Defines S001 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps python correctness foundation findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S001.
"""

from lint.core.ruff import RuffBackedRule


class PythonCorrectnessFoundationRule(RuffBackedRule):
    """Enforces the python-correctness-foundation policy."""

    id = "S001"
    name = "python-correctness-foundation"
    summary = (
        "This rule is the SDK's first correctness gate for production Python. "
        "It groups undefined names, invalid imports, malformed syntax-adjacent constructs, and high-signal parser failures that can prevent a module from loading. "
        "A finding identifies a concrete source location before provider, tool, or agent behavior can be trusted. "
        "The rule stays narrow about style so its failures point to executable defects rather than preferences."
    )
    prefixes = ("F", "E4", "E7", "E9")
    impact = (
        "An undefined name or invalid import can stop package startup before a caller reaches its requested operation. "
        "A malformed control-flow or expression construct can make an otherwise unrelated provider, tool, or runner unavailable. "
        "Because these failures occur at import or execution boundaries, downstream tests may report secondary errors that hide the root cause. "
        "Leaving the finding in place therefore blocks both local diagnosis and safe release of the SDK."
    )
    repair = (
        "Read Ruff's exact code and source line before editing so the repair addresses the actual name-resolution or syntax defect. "
        "Define or import the intended symbol, remove stale imports, or rewrite the invalid construct in the smallest coherent change. "
        "Preserve the module's public contract and do not silence a real error with a noqa, an ignore, or a baseline increase. "
        "Re-run the focused rule and then the import and source gates to prove the fix holds."
    )
    examples = (
        "vidbyte/lib/http/transport.py - a correctly resolved production module",
        "The Ruff record's path, code, and source line identify the repair target",
    )
    will_not_work = (
        "Adding noqa or a per-file ignore without proving that the finding is a false positive.",
        "Moving a missing-name failure to a later dynamic lookup so package import appears to succeed.",
    )


RULE = PythonCorrectnessFoundationRule()
