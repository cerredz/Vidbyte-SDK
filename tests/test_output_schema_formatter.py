"""FILE: tests/test_output_schema_formatter.py

PURPOSE: Regression tests for OutputSchemaFormatter constraint annotation.
ROLE IN CODEBASE: Keeps unenforceable constraints out of native wire schemas at every depth.
ARCHITECTURE NOTE: Resolves a Pydantic model, annotates it, and inspects the resulting dict.
FUNCTION INVENTORY: OutputSchemaAnnotateTests covers anyOf branches emitted for Optional fields.
COMMON MODIFICATION PATTERNS: Add a model per new schema shape that annotate() must traverse.
WHAT NOT TO DO: Do not assert exact description wording; assert keys left the schema.
KNOWN EDGE CASES: Pydantic emits Optional[X] and X | None as anyOf [X, null].
RELATED DOCS: docs/design/core-schema-yaml-deepseek-fixes.md
TESTS: Run with python -m pytest -q tests/test_output_schema_formatter.py.
"""

from __future__ import annotations

import json
import unittest

from pydantic import BaseModel, Field

from vidbyte.providers.output_schema import OutputSchemaFormatter


class Invoice(BaseModel):
    number: str = Field(pattern=r"^INV-\d+$")
    notes: list[str] | None = Field(default=None, min_length=1, max_length=3)
    discount: float | None = Field(default=None, ge=0, le=1)


class OutputSchemaAnnotateTests(unittest.TestCase):
    """Verify annotate() folds constraints at every schema depth."""

    def test_folds_constraints_inside_optional_any_of_branches(self) -> None:
        """Constraints on Optional fields leave the wire schema and reach the description."""
        formatter = OutputSchemaFormatter()
        annotated = formatter.annotate(formatter.resolve_schema(Invoice))
        notes = annotated["properties"]["notes"]["anyOf"][0]
        discount = annotated["properties"]["discount"]["anyOf"][0]

        for key in ("minItems", "maxItems", "minimum", "maximum", "pattern"):
            self.assertNotIn(f'"{key}"', json.dumps(annotated))
        self.assertIn("Must be", notes["description"])
        self.assertIn("Must be", discount["description"])


if __name__ == "__main__":
    unittest.main()
