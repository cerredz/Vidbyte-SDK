"""FILE: lint/rules/s063_no_assert_in_package_code.py

PURPOSE: Defines S063, which rejects assert statements in importable SDK package code.
ROLE IN CODEBASE: Keeps argument validation and invariant checks alive when the SDK runs under python -O.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter (bandit S101); Ruff scans only vidbyte/, so tests keep their asserts.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Type-narrowing asserts such as `assert x is not None` are counted too, because they vanish under -O as well; existing ones are count-ratcheted.
RELATED DOCS: PR #633 review comment 4233644411 (https://github.com/cerredz/Vidbyte-SDK/pull/633#discussion_r4233644411).
TESTS: Exercised by python lint/run.py --rule S063.
"""

from lint.core.ruff import RuffBackedRule


class NoAssertInPackageCodeRule(RuffBackedRule):
    """Requires SDK package code to validate with explicit raises rather than assert."""

    id = "S063"
    name = "no-assert-in-package-code"
    summary = "Importable SDK code checks arguments and invariants with an explicit if/raise, never with assert, which python -O removes."
    codes = frozenset({"S101"})
    impact = "Python strips every assert statement when it runs with -O or PYTHONOPTIMIZE, so a check written as assert silently stops existing in an optimized deployment. A tool argument bound such as `assert max_depth >= 0` then lets invalid input through to the logic it was meant to protect, and the failure surfaces later and elsewhere, or not at all. Review of PR #633 (comment 4233644411, https://github.com/cerredz/Vidbyte-SDK/pull/633#discussion_r4233644411) caught exactly this in TreeTool."
    repair = "Replace the assert with `if not <condition>: raise <SdkError>(...)`, using the SDK error type the surrounding code already raises, such as ToolExecutionError from vidbyte.lib.errors inside a tool. For a type-narrowing assert such as `assert x is not None`, raise a typed error that names the missing value, or restructure so the value cannot be None at that point. Do not wrap the assert in another helper, raise a bare AssertionError, or add a suppression; run `python lint/run.py --rule S063` afterwards."
    examples = ("vidbyte/tools/filesystem/tree.py - TreeTool.execute raises ToolExecutionError when max_depth or max_entries is out of range",)


RULE = NoAssertInPackageCodeRule()
