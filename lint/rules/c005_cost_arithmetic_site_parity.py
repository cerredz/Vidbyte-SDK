"""FILE: lint/rules/c005_cost_arithmetic_site_parity.py

PURPOSE:
    Declares C005: a "<name> * <name>" multiplication where either operand's
    identity contains "price" or "rate" may only appear in the two known,
    deliberately separate sites that already do this arithmetic.
ROLE IN CODEBASE:
    Registered by lint/core/registry.py. Pure-AST rule (ruff_selectors is
    empty); parses every file except the two allowlisted locations.
ARCHITECTURE NOTE:
    Grounded in field-guide/vidbyte-sdk/runtime-boundaries.md: "Keep model
    usage accounting agent-owned." Verified against the live tree by
    grepping for *price*/*rate* multiplication: it exists in exactly three
    files, vidbyte/agents/pricing/base.py, vidbyte/agents/pricing/
    anthropic.py (both under the vidbyte/agents/pricing/ package -- provider
    token-cost formulas, the sanctioned live-run path), and
    vidbyte/sessions/usage.py (SessionUsageBuilder, read in full: it
    reconstructs a UsageRollup from a persisted session's stored message
    history with a caller-supplied price table, for session replay -- a
    deliberately separate, correctly-scoped subsystem, not a bug). This is
    therefore not a ban; it is a two-entry allowlist that fails only if a
    *third* independent site starts doing this arithmetic.
WHAT NOT TO DO IN THIS FILE:
    Do not add a third allowlisted location without re-verifying it is a
    deliberate, reviewed design the way SessionUsageBuilder was, not an
    accidental duplicate that should instead route through
    vidbyte/agents/pricing/.
RELATED DOCS:
    docs/design/sdk-lint-contract-rules.md
    field-guide/vidbyte-sdk/runtime-boundaries.md
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, ClassVar

from lint.core.diagnostic import Finding, RuleDiagnostic
from lint.core.parsing import PythonSourceParser

if TYPE_CHECKING:
    from pathlib import Path

    from lint.core.ruff import RuffFinding

_ALLOWLISTED_DIRECTORY = ("vidbyte", "agents", "pricing")
_ALLOWLISTED_FILE = ("vidbyte", "sessions", "usage.py")
_PRICE_MARKERS = ("price", "rate")


class CostArithmeticSiteParityRule:
    """C005: token/cost multiplication is confined to two known, allowlisted sites."""

    rule_id: ClassVar[str] = "C005"
    ruff_selectors: ClassVar[tuple[str, ...]] = ()

    @staticmethod
    def diagnostic() -> RuleDiagnostic:
        # Returns C005's fixed summary/impact/repair/verify-command text.
        return RuleDiagnostic(
            summary=(
                "A multiplication where one operand's name contains 'price' or 'rate' appears "
                "outside the two known, deliberately separate sites that already compute cost "
                "this way: `vidbyte/agents/pricing/**` (provider token-cost formulas -- the "
                "live-run pricing path `UsageTracker` and `BaseAgent.get_usage()` read from) "
                "and `vidbyte/sessions/usage.py`'s `SessionUsageBuilder` (reconstructs cost "
                "from a persisted session's stored history for replay, using a caller-supplied "
                "price table -- a separate, already-reviewed subsystem, not a duplicate)."
            ),
            impact=(
                "`runtime-boundaries.md` states the house rule directly: model usage "
                "accounting stays agent-owned, propagated through the one `UsageTracker` "
                "shared source of truth, specifically so the runtime and the agent's own "
                "usage API always expose the same rollup without duplicate, independently "
                "computed records. A third site computing cost from tokens and a rate "
                "independently is exactly the kind of silent-drift risk the field guide's "
                "'Operation Pricebook Rates' entry already describes happening once with a "
                "table value -- a second formula that always has to be kept in sync by hand "
                "with the first one is a formula that eventually is not."
            ),
            repair=(
                "Route the calculation through the existing pricing surface instead of adding "
                "a new one: for a live agent run, extend `vidbyte/agents/pricing/` (see "
                "`ProviderUsage.cost_usd` in `vidbyte/agents/pricing/base.py` for the pattern "
                "used per-provider); for reconstructing cost from persisted, already-completed "
                "history, extend `SessionUsageBuilder` in `vidbyte/sessions/usage.py` rather "
                "than writing a third independent formula. If this really is a legitimate third "
                "case neither of those two fits, add it to `_ALLOWLISTED_DIRECTORY`/"
                "`_ALLOWLISTED_FILE` in this rule module in the same PR that introduces it, with "
                "a comment explaining why it is deliberately separate -- the same way this "
                "rule's own header explains why `SessionUsageBuilder` is not a violation."
            ),
            verify_command="python lint/run.py --rule C005",
        )

    @staticmethod
    def find(files: tuple[Path, ...], ruff_findings: tuple[RuffFinding, ...]) -> tuple[Finding, ...]:
        # Parses every non-allowlisted file and flags each price/rate multiplication found.
        findings: list[Finding] = []
        for path in files:
            if CostArithmeticSiteParityRule._is_allowlisted(path):
                continue
            module = PythonSourceParser.parse(path)
            if module is None:
                continue
            for node in ast.walk(module):
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult) and CostArithmeticSiteParityRule._looks_like_price_math(node):
                    findings.append(
                        Finding(
                            rule_id="C005",
                            code="C005",
                            file=path,
                            line=node.lineno,
                            column=node.col_offset,
                            message="Price/rate multiplication outside the two allowlisted pricing sites; route through vidbyte/agents/pricing/ or vidbyte/sessions/usage.py.",
                        )
                    )
        return tuple(findings)

    @staticmethod
    def _is_allowlisted(path: Path) -> bool:
        # True when path is under the pricing package or is the sessions usage-rollup file.
        parts = path.parts
        window = len(_ALLOWLISTED_DIRECTORY)
        if any(tuple(parts[i : i + window]) == _ALLOWLISTED_DIRECTORY for i in range(len(parts) - window + 1)):
            return True
        return parts[-len(_ALLOWLISTED_FILE) :] == _ALLOWLISTED_FILE

    @staticmethod
    def _looks_like_price_math(node: ast.BinOp) -> bool:
        # True when either multiplication operand's identity contains "price" or "rate".
        return CostArithmeticSiteParityRule._identity_looks_like_price(node.left) or CostArithmeticSiteParityRule._identity_looks_like_price(node.right)

    @staticmethod
    def _identity_looks_like_price(operand: ast.expr) -> bool:
        # Returns whether a Name/Attribute operand's identity contains a price marker, case-insensitively.
        identity = None
        if isinstance(operand, ast.Name):
            identity = operand.id
        elif isinstance(operand, ast.Attribute):
            identity = operand.attr
        if identity is None:
            return False
        lowered = identity.lower()
        return any(marker in lowered for marker in _PRICE_MARKERS)


__all__ = ["CostArithmeticSiteParityRule"]
