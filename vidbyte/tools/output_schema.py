"""Context Protocol Header

Description:
    Provides schema resolution and structured output validation for tool and agent output contracts.
Purpose:
    Centralizes JSON Schema resolution, Pydantic-backed validation, and system prompt hint generation
    so that both ToolExecutor and AgentRuntime enforce output schemas consistently.
Architecture:
    - OutputSchemaValidator: Stateless utility class with three static methods.
Relations:
    Used by vidbyte.tools.executor and vidbyte.agents.runtime when output_schema is set on a spec.
"""

from __future__ import annotations

import json
from typing import Any, Mapping


class OutputSchemaValidator:
    """Stateless utility for resolving, validating, and describing output schemas."""

    @staticmethod
    def resolve(schema: type | Mapping[str, Any]) -> Mapping[str, Any]:
        """Return a JSON Schema dict from a Pydantic model type or a raw dict schema."""
        if isinstance(schema, type) and hasattr(schema, "model_json_schema"):
            return schema.model_json_schema()
        return dict(schema)

    @staticmethod
    def validate(output: str, schema: type | Mapping[str, Any]) -> tuple[Any, str | None]:
        """Parse JSON output and validate against the schema. Returns (value, None) or (None, error)."""
        try:
            parsed = json.loads(output)
        except (json.JSONDecodeError, ValueError) as exc:
            return None, f"Output is not valid JSON: {exc}"

        if isinstance(schema, type) and hasattr(schema, "model_validate"):
            try:
                validated = schema.model_validate(parsed)
                return validated, None
            except Exception as exc:
                return None, f"Output does not match schema: {exc}"

        return parsed, None

    @staticmethod
    def schema_prompt_hint(schema: type | Mapping[str, Any]) -> str:
        """Return a system prompt fragment instructing the model to produce schema-conformant JSON."""
        resolved = OutputSchemaValidator.resolve(schema)
        schema_str = json.dumps(resolved, indent=2)
        return (
            "Your final response MUST be valid JSON conforming to this schema:\n"
            f"```json\n{schema_str}\n```"
        )


__all__ = ["OutputSchemaValidator"]
