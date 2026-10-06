"""FILE: lint/rules/c005_cost_arithmetic_site_parity.py

PURPOSE: Detect token/rate multiplication outside reviewed pricing boundaries.
ROLE IN CODEBASE: Keeps cost arithmetic owned by the agent and session pricing paths as C005.
ARCHITECTURE NOTE: Scans tracked source ASTs and uses two explicit, reviewed path boundaries.
FUNCTION INVENTORY: CostArithmeticSiteParityRule detects and explains out-of-bound arithmetic.
COMMON MODIFICATION PATTERNS: Re-verify ownership before changing the allowlist; rerun C005.
WHAT NOT TO DO: Do not add a third allowlisted site without a separately reviewed lifecycle.
KNOWN EDGE CASES: Only direct Name/Attribute multiplication operands are classified as price/rate math.
RELATED DOCS: docs/design/sdk-lint-contract-rules.md
TESTS: Exercised by python lint/run.py --rule C005.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

_ALLOWLISTED_DIRECTORY = ("vidbyte", "agents", "pricing")
_ALLOWLISTED_FILE = ("vidbyte", "sessions", "usage.py")
_PRICE_MARKERS = ("price", "rate")


class CostArithmeticSiteParityRule(Rule):
    """Reject price/rate multiplication outside reviewed pricing sites."""

    id = "C005"
    name = "cost-arithmetic-site-parity"
    severity = "blocking"
    summary = "Token-by-rate arithmetic stays in the reviewed pricing boundaries."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans parsed files while allowing the two deliberately separate pricing paths.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or self._is_allowlisted(source.rel):
                continue
            for node in ast.walk(source.tree):
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult) and self._looks_like_price_math(node):
                    findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=node.lineno, source_line=source.line_at(node.lineno), symbol="price/rate multiplication"))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Routes new calculations to the existing agent or session pricing owners.
        return Diagnostic(
            what_happened=f"{finding.location()} performs price/rate multiplication outside the reviewed pricing sites.",
            why_blocked="A third independent cost formula can drift from the agent UsageTracker or the session replay calculation and silently report a different bill.",
            how_to_fix="For live runs, route the calculation through vidbyte/agents/pricing/. For persisted-session replay, extend vidbyte/sessions/usage.py instead of adding another formula.",
            correct_examples=("vidbyte/agents/pricing/ - live provider token-cost formulas.", "vidbyte/sessions/usage.py - persisted usage reconstruction."),
            will_not_work=("Copying the formula into a feature-local helper.", "Adding a new allowlist entry without verifying its ownership and separate lifecycle."),
            verify=self.verify_command(),
        )

    @staticmethod
    def _is_allowlisted(rel_path: str) -> bool:
        # Keeps allowlist matching independent of Windows path separators.
        parts = tuple(rel_path.replace("\\", "/").split("/"))
        window = len(_ALLOWLISTED_DIRECTORY)
        return any(parts[index : index + window] == _ALLOWLISTED_DIRECTORY for index in range(len(parts) - window + 1)) or parts[-len(_ALLOWLISTED_FILE) :] == _ALLOWLISTED_FILE

    @classmethod
    def _looks_like_price_math(cls, node: ast.BinOp) -> bool:
        # Checks only direct Name/Attribute operands whose identity names price/rate.
        return cls._identity_looks_like_price(node.left) or cls._identity_looks_like_price(node.right)

    @staticmethod
    def _identity_looks_like_price(operand: ast.expr) -> bool:
        # Returns whether one operand's local identity contains a price marker.
        identity = operand.id if isinstance(operand, ast.Name) else operand.attr if isinstance(operand, ast.Attribute) else ""
        lowered = identity.lower()
        return any(marker in lowered for marker in _PRICE_MARKERS)


RULE = CostArithmeticSiteParityRule()
