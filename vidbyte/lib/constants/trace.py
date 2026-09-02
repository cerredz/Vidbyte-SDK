"""FILE: vidbyte/lib/constants/trace.py

PURPOSE: Owns the maximum nesting depth allowed for a TraceField's declared subfield shape.
ROLE IN CODEBASE: Imported by vidbyte/lib/dataclasses/trace.py, which enforces the bound on every constructed TraceField regardless of how it was built.
ARCHITECTURE NOTE: A single named constant only; this module performs no validation itself.
COMMON MODIFICATION PATTERNS: Change the bound here, then re-run every prebuilt trace schema construction to confirm none of them now exceed it.
KNOWN EDGE CASES: A TraceField with no fields/items always has depth 1, so the bound only ever constrains schemas that opt into nested object/array shapes.
RELATED DOCS: docs/design/nested-continual-trace-shapes.md, field-guide/vidbyte-sdk/tracing-shape-contracts.md
TESTS: Exercised indirectly by scripts/test-continual-trace.py's nested-schema cases.
"""

from __future__ import annotations

MAX_TRACE_FIELD_NESTING_DEPTH = 5

__all__ = ["MAX_TRACE_FIELD_NESTING_DEPTH"]
