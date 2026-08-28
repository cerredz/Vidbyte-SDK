"""Context Protocol Header

Description:
    Implements a structural JSON schema checker (JSONSchemaGrader).
Purpose:
    Validates structured outputs (such as agent tool parameters or JSON schema formats)
    without relying on external third-party validator dependencies.
Architecture:
    - JSONSchemaGrader: Inherits from BaseGrader, performs recursive type and property checks.
Functions:
    - agrade: Root execution method parsing json and initiating verification.
    - _validate_node: Recursive matching algorithm checking types and nested items.
Relations:
    Related to vidbyte.evals.base (BaseGrader) and vidbyte.evals.types (EvalCase, GraderResult).
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


class JSONSchemaGrader(BaseGrader):
    """Grader that validates model output against a specified JSON Schema structure."""

    name: ClassVar[str] = "json_schema"

    def __init__(self, schema: dict[str, Any]) -> None:
        # Instantiates the JSONSchemaGrader with the expected schema definition.
        self.schema = schema

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Asynchronously parses the output as JSON and validates it against the schema.
        try:
            parsed = json.loads(actual)
        except json.JSONDecodeError as exc:
            return GraderResult(score=0.0, passed=False, reason=f"Output is not valid JSON: {str(exc)}")

        valid, error_msg = self._validate_node(parsed, self.schema)
        score = 1.0 if valid else 0.0
        reason = "Valid JSON conforming to schema." if valid else f"JSON mismatch: {error_msg}"
        return GraderResult(score=score, passed=valid, reason=reason)

    def _validate_node(self, data: object, schema: dict[str, Any]) -> tuple[bool, str]:
        # Recursively validates a JSON node against the structural rules of the schema.
        schema_type = schema.get("type")
        if not schema_type:
            return True, ""

        if schema_type == "object":
            if not isinstance(data, dict):
                return False, f"Expected object, got {type(data).__name__}"
            required = schema.get("required", [])
            for req in required:
                if req not in data:
                    return False, f"Missing required property '{req}'"
            properties = schema.get("properties", {})
            for key, prop_schema in properties.items():
                if key in data:
                    res, err = self._validate_node(data[key], prop_schema)
                    if not res:
                        return False, f"In property '{key}': {err}"
            return True, ""

        if schema_type == "array":
            if not isinstance(data, list):
                return False, f"Expected array, got {type(data).__name__}"
            items_schema = schema.get("items")
            if items_schema:
                for idx, item in enumerate(data):
                    res, err = self._validate_node(item, items_schema)
                    if not res:
                        return False, f"At index {idx}: {err}"
            return True, ""

        if schema_type == "string":
            if not isinstance(data, str):
                return False, f"Expected string, got {type(data).__name__}"
            return True, ""

        if schema_type == "integer":
            if not isinstance(data, int) or isinstance(data, bool):
                return False, f"Expected integer, got {type(data).__name__}"
            return True, ""

        if schema_type in ("number", "numeric"):
            if not isinstance(data, (int, float)) or isinstance(data, bool):
                return False, f"Expected number, got {type(data).__name__}"
            return True, ""

        if schema_type == "boolean":
            if not isinstance(data, bool):
                return False, f"Expected boolean, got {type(data).__name__}"
            return True, ""

        return True, ""
