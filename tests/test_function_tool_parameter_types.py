"""FILE: tests/test_function_tool_parameter_types.py

PURPOSE: Regression tests for the type labels @tool gives each parameter of a decorated function.
ROLE IN CODEBASE: Keeps the tool docs sent to the model naming a type, never a Python repr of the JSON schema.
ARCHITECTURE NOTE: Builds a @tool spec, reads its ToolParameter labels, and renders to_prompt_str.
FUNCTION INVENTORY: Color is an enum parameter Pydantic emits as a $ref; FunctionToolParameterTypeTests checks labels and prompt text.
COMMON MODIFICATION PATTERNS: Add a parameter per new schema shape whose label _parameter_type_label must produce.
WHAT NOT TO DO: Do not assert the provider input_schema here; @tool still sends Pydantic's schema unchanged.
KNOWN EDGE CASES: Pydantic emits Optional[X] and X | None as anyOf [X, null] with no top-level type.
RELATED DOCS: vidbyte/tools/README.md
TESTS: Run with python -m pytest -q tests/test_function_tool_parameter_types.py.
"""

from __future__ import annotations

import unittest
from enum import Enum
from typing import Optional

from vidbyte import tool


class Color(Enum):
    RED = "red"
    BLUE = "blue"


@tool
def paint(color: Color, note: Optional[str] = None, count: int = 1, tags: list[str] | None = None) -> str:
    """Paint something."""
    return f"{color.value} {note} {count} {tags}"


class FunctionToolParameterTypeTests(unittest.TestCase):
    def test_optional_parameters_read_as_joined_type_names(self) -> None:
        spec = paint.spec()

        labels = [(parameter.name, parameter.type) for parameter in spec.parameters]

        self.assertEqual(
            labels,
            [("color", "any"), ("note", "string | null"), ("count", "integer"), ("tags", "array | null")],
        )
        prompt = spec.to_prompt_str()
        self.assertIn("- note (string | null, optional): ", prompt)
        self.assertNotIn("{'type'", prompt)


if __name__ == "__main__":
    unittest.main()
