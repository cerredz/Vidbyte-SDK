"""FILE: lint/rules/c004_operation_pricing_rate_floor.py

PURPOSE:
    Declares C004: every non-zero usd_fixed/usd_per_unit rate in
    OPERATION_PRICING must clear an implausibility floor, statically.
ROLE IN CODEBASE:
    Registered by lint/core/registry.py. Pure-AST rule (ruff_selectors is
    empty); scans exactly one file,
    vidbyte/lib/registries/operation_pricing.py.
ARCHITECTURE NOTE:
    Promotes an existing runtime test,
    tests/test_agent_pricing.py::OperationPricingTableTests::
    test_no_rate_is_implausibly_small, into a static, edit-time diagnostic
    over the same OPERATION_PRICING dict literal. _MIN_PLAUSIBLE_RATE_USD
    below is deliberately duplicated from tests/test_agent_pricing.py's own
    module-level constant of the same name and value (1e-5) rather than
    imported, because this rule must not import vidbyte or its test suite;
    it is a static mirror of a runtime invariant, not shared application
    config, so the usual "twice-declared constants belong in shared config"
    rule does not apply here.
WHAT NOT TO DO IN THIS FILE:
    Do not attempt to parse the file's "Sources:" comment block to verify
    every provider has a cited source -- that block is free-text prose
    above the dict, not structured data tied to individual entries, and a
    text-parsing check here would be fragile relative to the value it adds
    over this numeric floor, which is the part that has actually caused a
    real, repeated incident (PR #325 reverted, wrong rate shipped twice).
RELATED DOCS:
    docs/design/sdk-lint-contract-rules.md
    field-guide/vidbyte-sdk/operation-pricebook-rates.md
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, ClassVar

from lint.core.diagnostic import Finding, RuleDiagnostic
from lint.core.parsing import PythonSourceParser

if TYPE_CHECKING:
    from pathlib import Path

    from lint.core.ruff import RuffFinding

_TABLE_NAME = "OPERATION_PRICING"
_TABLE_FILE_SUFFIX = ("vidbyte", "lib", "registries", "operation_pricing.py")
_RATE_FIELDS = ("usd_fixed", "usd_per_unit")
_MIN_PLAUSIBLE_RATE_USD = 1e-5


class OperationPricingRateFloorRule:
    """C004: no OPERATION_PRICING rate may be a nonzero value below the plausibility floor."""

    rule_id: ClassVar[str] = "C004"
    ruff_selectors: ClassVar[tuple[str, ...]] = ()

    @staticmethod
    def diagnostic() -> RuleDiagnostic:
        # Returns C004's fixed summary/impact/repair/verify-command text.
        return RuleDiagnostic(
            summary=(
                f"A nonzero `usd_fixed` or `usd_per_unit` rate in `OPERATION_PRICING` "
                f"(`vidbyte/lib/registries/operation_pricing.py`) is below "
                f"{_MIN_PLAUSIBLE_RATE_USD:g}, the same floor "
                "`tests/test_agent_pricing.py::OperationPricingTableTests::"
                "test_no_rate_is_implausibly_small` already enforces at runtime."
            ),
            impact=(
                "This exact mistake has shipped twice: all six Parallel search/extract "
                "entries sat 1000x low on `main` because two design docs read the vendor's "
                "'Cost ($/1000)' column value as dollars-per-unit and divided by 1,000 again, "
                "and that reasoning reverted PR #325's correct fix once already. A wrong-but-"
                "present rate is strictly worse than the `None` the registry already uses for "
                "genuinely unknowable rates, because a present rate keeps "
                "`UsageRollup.cost_complete` silently `True` -- nothing downstream can tell "
                "the cost is wrong."
            ),
            repair=(
                "Re-read the vendor's own pricing page and its column header exactly (Parallel's "
                "is 'Cost ($/1000)', so a table value of `1` is $0.001 per unit -- divide by "
                "1,000 exactly once). Cross-check against another row from the same provider "
                "that already converts correctly (the Task/Chat/Response/Monitor rows for "
                "Parallel encode the same column and are already right). Never re-derive a rate "
                "from a prior design doc; read the vendor page directly. After fixing the "
                "number, also check whether the file's 'Sources:' comment block above the "
                "table needs a new or corrected URL for that provider -- this rule only checks "
                "the number, not the citation."
            ),
            verify_command="python lint/run.py --rule C004",
        )

    @staticmethod
    def find(files: tuple[Path, ...], ruff_findings: tuple[RuffFinding, ...]) -> tuple[Finding, ...]:
        # Locates the one pricing table file, parses it, and flags every rate below the floor.
        for path in files:
            if path.parts[-len(_TABLE_FILE_SUFFIX):] == _TABLE_FILE_SUFFIX:
                return OperationPricingRateFloorRule._scan_table_file(path)
        return ()

    @staticmethod
    def _scan_table_file(path: Path) -> tuple[Finding, ...]:
        # Parses the table file and delegates to the dict-literal scanner, degrading to no findings on failure.
        module = PythonSourceParser.parse(path)
        if module is None:
            return ()
        table = OperationPricingRateFloorRule._find_table_dict(module)
        if table is None:
            return ()
        return tuple(OperationPricingRateFloorRule._scan_table_dict(path, table))

    @staticmethod
    def _find_table_dict(module: ast.Module) -> ast.Dict | None:
        # Finds the module-level OPERATION_PRICING assignment (plain or annotated) and returns its dict literal.
        for node in module.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == _TABLE_NAME:
                return node.value if isinstance(node.value, ast.Dict) else None
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == _TABLE_NAME for t in node.targets):
                return node.value if isinstance(node.value, ast.Dict) else None
        return None

    @staticmethod
    def _scan_table_dict(path: Path, table: ast.Dict) -> list[Finding]:
        # Checks every (key, value) pair's rate keywords against the plausibility floor.
        findings: list[Finding] = []
        for key, value in zip(table.keys, table.values):
            if not isinstance(value, ast.Call):
                continue
            key_text = OperationPricingRateFloorRule._render_key(key)
            findings.extend(OperationPricingRateFloorRule._check_call(path, key_text, value))
        return findings

    @staticmethod
    def _render_key(key: ast.expr | None) -> str:
        # Renders a (operation, provider, mode) tuple key literal as readable text for the message.
        if isinstance(key, ast.Tuple):
            parts = [str(elt.value) if isinstance(elt, ast.Constant) else "?" for elt in key.elts]
            return f"({', '.join(parts)})"
        return "<unknown key>"

    @staticmethod
    def _check_call(path: Path, key_text: str, call: ast.Call) -> list[Finding]:
        # Checks each rate keyword argument on one OperationPricing(...) call.
        findings: list[Finding] = []
        for keyword in call.keywords:
            if keyword.arg not in _RATE_FIELDS or not isinstance(keyword.value, ast.Constant):
                continue
            rate = keyword.value.value
            if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate == 0:
                continue
            if abs(rate) < _MIN_PLAUSIBLE_RATE_USD:
                findings.append(
                    Finding(
                        rule_id="C004",
                        code="C004",
                        file=path,
                        line=call.lineno,
                        column=call.col_offset,
                        message=f"{key_text} {keyword.arg}={rate!r} is below the {_MIN_PLAUSIBLE_RATE_USD:g} plausibility floor; looks off by a per-1,000 factor.",
                    )
                )
        return findings


__all__ = ["OperationPricingRateFloorRule"]
