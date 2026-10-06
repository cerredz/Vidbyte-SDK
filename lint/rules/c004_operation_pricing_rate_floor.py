"""FILE: lint/rules/c004_operation_pricing_rate_floor.py

PURPOSE: Detect nonzero operation pricebook rates below the established floor.
ROLE IN CODEBASE: Mirrors the runtime pricebook magnitude invariant as C004.
ARCHITECTURE NOTE: Parses only the literal operation table and never imports pricing code.
FUNCTION INVENTORY: OperationPricingRateFloorRule locates, scans, and explains rate findings.
COMMON MODIFICATION PATTERNS: Keep the table path, rate fields, and threshold synchronized; rerun C004.
WHAT NOT TO DO: Do not parse free-text source comments or replace unknown rates with tiny guesses.
KNOWN EDGE CASES: Zero, None, nonnumeric, and nonliteral rates are outside this numeric check.
RELATED DOCS: docs/design/sdk-lint-contract-rules.md
TESTS: Exercised by python lint/run.py --rule C004.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

_TABLE_REL_PATH = "vidbyte/lib/registries/operation_pricing.py"
_RATE_FIELDS = frozenset({"usd_fixed", "usd_per_unit"})
_MIN_PLAUSIBLE_RATE_USD = 1e-5


class OperationPricingRateFloorRule(Rule):
    """Reject nonzero operation rates below the known plausibility floor."""

    id = "C004"
    name = "operation-pricing-rate-floor"
    severity = "blocking"
    summary = "Nonzero operation pricebook rates are not implausibly small."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans only the source-of-truth operation pricing table.
        source = next((item for item in catalog.python_files() if item.rel == _TABLE_REL_PATH), None)
        if source is None or source.tree is None:
            return []
        table = self._find_table_dict(source.tree)
        return self._scan_table(source, table) if table is not None else []

    def explain(self, finding: Finding) -> Diagnostic:
        # Connects the static check to the existing pricing invariant and repair source.
        return Diagnostic(
            what_happened=f"{finding.location()} {finding.extra.get('key', '<unknown operation>')} {finding.extra.get('field', 'rate')}={finding.extra.get('rate', '<unknown>')} is below {_MIN_PLAUSIBLE_RATE_USD:g}.",
            why_blocked="A rate that is present but 1,000 times too small marks usage as completely priced while silently undercounting cost; this exact unit-conversion error has already recurred.",
            how_to_fix="Re-read the provider's pricing-page column header and convert its published basis exactly once. Keep genuinely unknowable rates as None rather than guessing a tiny value.",
            correct_examples=("tests/test_agent_pricing.py::OperationPricingTableTests::test_no_rate_is_implausibly_small - runtime invariant mirrored here.",),
            will_not_work=("Dividing a per-1,000 vendor value twice.", "Suppressing the finding or increasing the baseline."),
            verify=self.verify_command(),
        )

    @staticmethod
    def _find_table_dict(module: ast.Module) -> ast.Dict | None:
        # Finds the module-level OPERATION_PRICING dict literal.
        for node in module.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "OPERATION_PRICING":
                return node.value if isinstance(node.value, ast.Dict) else None
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "OPERATION_PRICING" for target in node.targets):
                return node.value if isinstance(node.value, ast.Dict) else None
        return None

    def _scan_table(self, source: SourceFile, table: ast.Dict) -> list[Finding]:
        # Checks literal OperationPricing keyword rates against the floor.
        findings: list[Finding] = []
        for key, value in zip(table.keys, table.values):
            if not isinstance(value, ast.Call):
                continue
            key_text = self._render_key(key)
            for keyword in value.keywords:
                rate = keyword.value.value if keyword.arg in _RATE_FIELDS and isinstance(keyword.value, ast.Constant) else None
                if keyword.arg not in _RATE_FIELDS or isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate == 0 or abs(rate) >= _MIN_PLAUSIBLE_RATE_USD:
                    continue
                findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=value.lineno, source_line=source.line_at(value.lineno), symbol=key_text, extra={"key": key_text, "field": keyword.arg, "rate": repr(rate)}))
        return findings

    @staticmethod
    def _render_key(key: ast.expr | None) -> str:
        # Renders tuple keys without evaluating arbitrary source expressions.
        if isinstance(key, ast.Tuple):
            return f"({', '.join(str(item.value) if isinstance(item, ast.Constant) else '?' for item in key.elts)})"
        return "<unknown key>"


RULE = OperationPricingRateFloorRule()
