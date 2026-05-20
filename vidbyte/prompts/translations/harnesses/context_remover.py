from __future__ import annotations

CONTEXT_REMOVER_PURIFY_KEY = "harnesses.context_remover.purify"

CONTEXT_REMOVER_PURIFY_TEMPLATE = """You are purifying a noisy execution trace.

Immutable anchor:
{immutable_anchor}

Raw execution ledger:
{raw_execution_ledger}

Target extraction contract:
{target_extraction_contract}

Return only core semantic facts, definitive tool values used downstream, verified state changes, open blockers, and next required actions.
Remove redundant formatting, failed attempts unless relevant, filler, and unreferenced data arrays.
Keep the result under {max_summary_chars} characters.
"""

__all__ = [
    "CONTEXT_REMOVER_PURIFY_KEY",
    "CONTEXT_REMOVER_PURIFY_TEMPLATE",
]
