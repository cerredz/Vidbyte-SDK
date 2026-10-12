"""Gemini's schema reducer expands draft-07 `definitions` refs the same way it expands `$defs`."""

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
