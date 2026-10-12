"""FILE: tests/test_gemini_schema_definitions.py

PURPOSE: Regression tests that Gemini's schema reducer expands draft-07 `definitions` refs like `$defs` refs.
ROLE IN CODEBASE: Keeps a tool argument typed through `#/definitions/...` from reaching Gemini as an empty schema.
ARCHITECTURE NOTE: Calls ToolsFormatter.to_gemini_tool on a ToolSpec with a raw input_schema; no provider or network.
FUNCTION INVENTORY: _gemini_parameters builds the declaration; GeminiDraft07DefinitionsTests checks expansion and precedence.
COMMON MODIFICATION PATTERNS: Add a schema per ref-block shape a JSON Schema producer emits.
WHAT NOT TO DO: Do not call real provider endpoints or require API keys from the environment.
KNOWN EDGE CASES: A name defined in both `$defs` and `definitions` resolves to the `$defs` entry.
RELATED DOCS: vidbyte/lib/README.md
TESTS: Run with python -m pytest -q tests/test_gemini_schema_definitions.py.
"""

from __future__ import annotations

import json
import unittest

from vidbyte.lib.dataclasses.tools import ToolSpec
from vidbyte.lib.tools import ToolsFormatter

_ADDRESS = {
    "type": "object",
    "properties": {"street": {"type": "string"}, "city": {"type": "string"}},
    "required": ["street", "city"],
}


def _gemini_parameters(schema: dict) -> dict:
    spec = ToolSpec(name="shipParcel", description="Ship a parcel.", input_schema=schema)
    return ToolsFormatter.to_gemini_tool(spec)["function_declarations"][0]["parameters"]


class GeminiDraft07DefinitionsTests(unittest.TestCase):
    """Pydantic v1, zod-to-json-schema and hand-written schemas keep shared models under `definitions`."""

    def test_definitions_ref_is_expanded_in_place(self) -> None:
        # Before the fix the ref found no target, so `addr` reached Gemini as an empty schema.
        parameters = _gemini_parameters(
            {
                "type": "object",
                "properties": {"addr": {"$ref": "#/definitions/Addr"}, "kg": {"type": "number"}},
                "required": ["addr"],
                "definitions": {"Addr": _ADDRESS},
            }
        )
        self.assertEqual(parameters["properties"]["addr"], _ADDRESS)
        self.assertEqual(parameters["properties"]["kg"], {"type": "number"})
        blob = json.dumps(parameters)
        self.assertNotIn("$ref", blob)
        self.assertNotIn("definitions", blob)

    def test_defs_wins_when_a_name_is_in_both_blocks(self) -> None:
        parameters = _gemini_parameters(
            {
                "type": "object",
                "properties": {"addr": {"$ref": "#/$defs/Addr"}},
                "definitions": {"Addr": {"type": "string"}},
                "$defs": {"Addr": _ADDRESS},
            }
        )
        self.assertEqual(parameters["properties"]["addr"], _ADDRESS)
        self.assertNotIn("$defs", parameters)
        self.assertNotIn("definitions", parameters)


if __name__ == "__main__":
    unittest.main()
