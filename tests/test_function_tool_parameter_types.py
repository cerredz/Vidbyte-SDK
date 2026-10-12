"""Context Protocol Header

Description:
    Tests the type labels that @tool gives each parameter of a decorated function.
Purpose:
    Verifies the tool docs sent to the model name a type, never a Python repr of the JSON schema.
Architecture:
    - Color: Enum parameter that Pydantic emits as a $ref.
    - FunctionToolParameterTypeTests: Label checks on the spec and its rendered prompt text.
Relations:
    Related to vidbyte.tools.function_tool and vidbyte.lib.dataclasses.tools.
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
