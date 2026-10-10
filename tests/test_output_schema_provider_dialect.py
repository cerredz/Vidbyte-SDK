"""FILE: tests/test_output_schema_provider_dialect.py

PURPOSE: Regression tests for the schema dialect each provider receives for an agent output_schema.
ROLE IN CODEBASE: Keeps strict OpenAI requests and Gemini responseSchema payloads acceptable to the real APIs.
ARCHITECTURE NOTE: Builds each provider's request payload directly from a TextModelConfig carrying the
    annotated Pydantic schema the agent runtime would send, then inspects the payload dict.
FUNCTION INVENTORY: OpenAIStrictDialectTests checks both strict-mode rules at every object node for the
    OpenAI Responses adapter and the compatible NATIVE_SCHEMA tier; GeminiResponseSchemaTests checks refs
    are expanded; StrictFormatterTests checks explicit additionalProperties choices are kept.
COMMON MODIFICATION PATTERNS: Add a model per schema shape a provider dialect must accept.
WHAT NOT TO DO: Do not call real provider endpoints or require API keys from the environment.
KNOWN EDGE CASES: Pydantic emits Optional[X] as anyOf [X, null] and puts nested models and Enums in $defs.
RELATED DOCS: docs/design/output-schema-provider-dialect.md
TESTS: Run with python -m pytest -q tests/test_output_schema_provider_dialect.py.
"""

from __future__ import annotations

import json
import unittest
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.providers.compatible import MistralProvider
from vidbyte.providers.gemini import GeminiProvider
from vidbyte.providers.openai import OpenAIProvider
from vidbyte.providers.output_schema import OutputSchemaFormatter


class Priority(str, Enum):
    LOW = "low"
    HIGH = "high"


class Tag(BaseModel):
    label: str


class Ticket(BaseModel):
    title: str
    priority: Priority
    assignee: Optional[str] = None
    estimate_hours: int = 1
    tags: list[Tag]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    note: str | None = None


def _wire_schema(model: type[BaseModel]) -> dict[str, Any]:
    # Mirrors the agent runtime: resolve the Pydantic schema, then annotate it.
    formatter = OutputSchemaFormatter()
    return formatter.annotate(formatter.resolve_schema(model))


def _object_nodes(node: Any) -> list[dict[str, Any]]:
    # Collects every schema node that declares properties, at any depth, including inside $defs.
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            found.append(node)
        for value in node.values():
            found.extend(_object_nodes(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_object_nodes(value))
    return found


class OpenAIStrictDialectTests(unittest.TestCase):
    """Verify strict json_schema payloads satisfy OpenAI's strict-mode rules at every object node."""

    def assert_strict(self, schema: dict[str, Any]) -> None:
        nodes = _object_nodes(schema)
        self.assertGreaterEqual(len(nodes), 2, "expected the root object and the nested Tag object")
        for node in nodes:
            self.assertIs(node.get("additionalProperties"), False, node)
            self.assertEqual(node.get("required"), list(node["properties"]), node)

    def test_openai_responses_payload_closes_every_object(self) -> None:
        """Optional and defaulted fields become required and every object, nested or not, is closed."""
        # @intent strict-mode-closes-every-object
        # OpenAI rejects strict json_schema with 400 invalid_json_schema unless both rules hold everywhere.
        config = TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", response_format=_wire_schema(Ticket))
        payload = OpenAIProvider(model="gpt-5.4-mini", api_key="k")._create_text_payload(config, "triage", None, None)
        fmt = payload["text"]["format"]

        self.assertIs(fmt["strict"], True)
        self.assert_strict(fmt["schema"])
        self.assertIn("Tag", fmt["schema"]["$defs"])
        self.assertEqual(fmt["schema"]["properties"]["assignee"]["anyOf"][1], {"type": "null"})

    def test_compatible_native_schema_payload_closes_every_object(self) -> None:
        """The compatible adapter's NATIVE_SCHEMA tier sends the same strict dialect."""
        config = TextModelConfig(provider=ModelProvider.MISTRAL, model="mistral-large-latest", response_format=_wire_schema(Ticket))
        payload = MistralProvider(model="mistral-large-latest", api_key="k")._create_payload(config, "triage", None, None)
        json_schema = payload["response_format"]["json_schema"]

        self.assertIs(json_schema["strict"], True)
        self.assert_strict(json_schema["schema"])

    def test_strict_does_not_mutate_the_runtime_schema(self) -> None:
        """The runtime's schema is reused for validation and prompts, so strict() works on a copy."""
        schema = _wire_schema(Ticket)
        before = json.dumps(schema, sort_keys=True)
        OutputSchemaFormatter().strict(schema)
        self.assertEqual(json.dumps(schema, sort_keys=True), before)


class StrictFormatterTests(unittest.TestCase):
    """Verify strict() respects an explicit additionalProperties choice."""

    def test_explicit_open_object_is_left_alone(self) -> None:
        """A caller's additionalProperties:true is their explicit choice and is not overridden."""
        schema = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": True}
        self.assertEqual(OutputSchemaFormatter().strict(schema), schema)

    def test_forbid_extra_model_still_requires_every_property(self) -> None:
        """extra="forbid" already closes the object, but optional fields must still be required."""
        strict = OutputSchemaFormatter().strict(_wire_schema(Closed))
        self.assertIs(strict["additionalProperties"], False)
        self.assertEqual(strict["required"], ["name", "note"])


class GeminiResponseSchemaTests(unittest.TestCase):
    """Verify Gemini's responseSchema is reduced to its OpenAPI subset."""

    def test_nested_model_response_schema_has_no_refs(self) -> None:
        """Nested models and Enums are inlined instead of sent as $defs/$ref, which Gemini rejects."""
        # @intent response-schema-speaks-gemini-openapi-subset
        config = TextModelConfig(provider=ModelProvider.GEMINI, model="gemini-3.5-flash", response_format=_wire_schema(Ticket))
        payload = GeminiProvider(model="gemini-3.5-flash", api_key="k")._create_payload(config, "triage", None, None)
        schema = payload["generationConfig"]["responseSchema"]
        wire = json.dumps(schema)

        self.assertNotIn("$defs", wire)
        self.assertNotIn("$ref", wire)
        self.assertEqual(schema["properties"]["tags"]["items"]["properties"]["label"]["type"], "string")
        self.assertEqual(schema["properties"]["priority"]["enum"], ["low", "high"])


if __name__ == "__main__":
    unittest.main()
