"""Context Protocol Header

Description:
    Resolves SDK output schemas and validates model output against them.
Purpose:
    Keeps schema handling provider-agnostic in one place: each provider class owns its own wire
    format, so this class only resolves a schema, annotates the constraints a tier cannot enforce,
    and validates whatever text came back.
Architecture:
    - OutputSchemaFormatter: Resolves schemas, annotates unenforceable constraints, rewrites a
      schema into OpenAI's strict dialect, and validates output.
Relations:
    Used by vidbyte.agents.runtime when BaseAgent.output_schema or ToolSpec.output_schema is set,
    and by vidbyte.agents.contracts.schema.SchemaConformance to evaluate the final output.
Similar Files:
    - vidbyte/lib/registries/structured_output.py: Declares which tier each endpoint supports.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.errors import ConfigurationError

# Leading/trailing markdown fence around a JSON body, which several providers emit despite the schema.
_FENCED_JSON = re.compile(r"\A\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*\Z", re.DOTALL | re.IGNORECASE)

# JSON Schema constraint keys that no provider grammar reliably enforces, mapped to readable clauses.
_UNENFORCEABLE: Mapping[str, str] = {
    "minItems": "at least {value} items",
    "maxItems": "at most {value} items",
    "minLength": "at least {value} characters",
    "maxLength": "at most {value} characters",
    "minimum": "no less than {value}",
    "maximum": "no greater than {value}",
    "multipleOf": "a multiple of {value}",
    "pattern": "matching the pattern {value}",
}


class OutputSchemaFormatter:
    """Resolves output schemas, annotates unenforceable constraints, and validates model output."""

    def resolve_schema(self, schema: type | Mapping[str, Any]) -> dict[str, Any]:
        # Convert a Pydantic BaseModel subclass or a raw dict into a plain JSON schema dict.
        try:
            from pydantic import BaseModel
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                return dict(schema.model_json_schema())
        except ImportError:
            pass
        if isinstance(schema, Mapping):
            return dict(schema)
        raise ConfigurationError(
            f"output_schema must be a Pydantic BaseModel subclass or a dict, got {type(schema).__name__!r}."
        )

    def annotate(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        # Folds constraints no wire format enforces into each property's description instead.
        # @intent tell-the-model-what-the-grammar-cannot
        # Providers silently ignore minItems/minLength/pattern, so leaving them on the wire loses the
        # intent entirely. Moving them into the description keeps the model informed while Pydantic
        # still rejects violations on the way back - which now costs a repair turn, not an exception.
        annotated = copy.deepcopy(dict(schema))
        self._annotate_node(annotated)
        return annotated

    def strict(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        # Rewrites a schema into the dialect OpenAI's strict Structured Outputs mode accepts.
        # @intent strict-mode-closes-every-object
        # Strict mode rejects the whole request with 400 invalid_json_schema unless every object sets
        # additionalProperties:false and lists every property in required; Pydantic emits neither.
        # Optional fields stay expressible because Pydantic already types them as anyOf [X, null].
        strict = copy.deepcopy(dict(schema))
        self._strict_node(strict)
        return strict

    def validate(self, output: str, schema: type | Mapping[str, Any]) -> tuple[Any, str | None]:
        # Parse output as JSON and validate against the schema; returns (parsed, error_message).
        try:
            parsed = json.loads(self._unfenced(output))
        except (json.JSONDecodeError, ValueError) as exc:
            return None, f"output is not valid JSON: {exc}"
        try:
            from pydantic import BaseModel, ValidationError
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                try:
                    return schema.model_validate(parsed), None
                except ValidationError as exc:
                    return None, str(exc)
        except ImportError:
            pass
        return parsed, None

    def _unfenced(self, output: str) -> str:
        # Strips a markdown code fence some providers wrap JSON in even under a schema request.
        text = str(output or "").strip()
        match = _FENCED_JSON.match(text)
        return match.group(1) if match else text

    def _annotate_node(self, node: dict[str, Any]) -> None:
        # Rewrites one schema node's own constraints, then recurses into properties, items, defs,
        # and anyOf/oneOf/allOf branches (Pydantic emits Optional[X] as anyOf [X, null]).
        self._fold_constraints(node)
        for child in self._child_nodes(node):
            self._annotate_node(child)

    def _strict_node(self, node: dict[str, Any]) -> None:
        # Closes one object node and requires all its properties, then recurses like _annotate_node.
        # A node that already declares additionalProperties keeps the caller's explicit choice; an
        # explicitly closed node (extra="forbid") still needs every property listed in required.
        if isinstance(node.get("properties"), dict):
            node.setdefault("additionalProperties", False)
            if node["additionalProperties"] is False:
                node["required"] = list(node["properties"])
        for child in self._child_nodes(node):
            self._strict_node(child)

    @staticmethod
    def _child_nodes(node: Mapping[str, Any]) -> list[dict[str, Any]]:
        # Lists a node's direct subschemas: items, properties, defs, and anyOf/oneOf/allOf branches.
        children: list[Any] = [node.get("items")]
        for key in ("properties", "$defs", "definitions"):
            if isinstance(node.get(key), dict):
                children.extend(node[key].values())
        for key in ("anyOf", "oneOf", "allOf"):
            if isinstance(node.get(key), list):
                children.extend(node[key])
        return [child for child in children if isinstance(child, dict)]

    def _fold_constraints(self, node: dict[str, Any]) -> None:
        # Moves this node's unenforceable constraint keys into its description, in declaration order.
        clauses = [_UNENFORCEABLE[key].format(value=node.pop(key)) for key in list(node) if key in _UNENFORCEABLE]
        if not clauses:
            return
        description = str(node.get("description", "")).strip()
        node["description"] = f"{description} Must be {', '.join(clauses)}.".strip()


__all__ = ["OutputSchemaFormatter"]
