"""Context Protocol Header

Description:
    Declares structured-output capability data and developer-facing tier descriptions.
Purpose:
    Keeps endpoint capability policy and its explanations in a dependency-light configuration
    package, where registry lookups can use them without initializing the YAML configuration loader.
    Registries consume this data for lookup; provider adapters must not duplicate it or infer
    capability from provider names.
Architecture:
    - PROVIDER_SUPPORT and MODEL_SUPPORT: Fixed endpoint capability declarations.
    - StructuredOutputDescription: Explains one enforcement tier and its safe fallback path.
    - STRUCTURED_OUTPUT_DESCRIPTIONS: Complete tier catalog for developer-facing discovery.
Key Functions:
    - StructuredOutputDescription.schema_instruction: Renders a schema prompt for non-native tiers.
Relations:
    Imported by vidbyte.lib.registries.structured_output and exposed through that registry API.
Similar Files:
    - vidbyte/lib/config/constants.py: Configuration values delegated to a registry layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from vidbyte.lib.enums import ModelProvider, StructuredOutputSupport

STRUCTURED_OUTPUT_AS_OF = "2026-07-28"

# @intent declare-support-never-infer-it
# A provider-name heuristic previously sent DeepSeek a rejected payload while Mistral happened to
# accept it. These declarations make the supported request shape reviewable and ensure unknown
# endpoints degrade to prompt-only behavior instead of receiving an invalid native-schema payload.
PROVIDER_SUPPORT: dict[ModelProvider, StructuredOutputSupport] = {
    ModelProvider.OPENAI: StructuredOutputSupport.NATIVE_SCHEMA,
    ModelProvider.GEMINI: StructuredOutputSupport.NATIVE_SCHEMA,
    ModelProvider.MISTRAL: StructuredOutputSupport.NATIVE_SCHEMA,
    ModelProvider.ANTHROPIC: StructuredOutputSupport.NATIVE_SCHEMA,
    ModelProvider.DEEPSEEK: StructuredOutputSupport.JSON_MODE,
    ModelProvider.XAI: StructuredOutputSupport.JSON_MODE,
    ModelProvider.GLM: StructuredOutputSupport.JSON_MODE,
    ModelProvider.KIMI: StructuredOutputSupport.JSON_MODE,
    ModelProvider.MINIMAX: StructuredOutputSupport.JSON_MODE,
    ModelProvider.META: StructuredOutputSupport.PROMPT_ONLY,
    ModelProvider.OPENROUTER: StructuredOutputSupport.PROMPT_ONLY,
}

MODEL_SUPPORT: dict[ModelProvider, dict[str, StructuredOutputSupport]] = {
    ModelProvider.ANTHROPIC: {
        "claude-3": StructuredOutputSupport.STRICT_TOOLS,
        "claude-4-opus": StructuredOutputSupport.STRICT_TOOLS,
        "claude-4-sonnet": StructuredOutputSupport.STRICT_TOOLS,
        "claude-4-haiku": StructuredOutputSupport.STRICT_TOOLS,
    },
}


@dataclass(frozen=True)
class StructuredOutputDescription:
    """Developer-facing explanation of one structured-output enforcement tier."""

    support: StructuredOutputSupport
    title: str
    description: str
    fallback: StructuredOutputSupport | None

    def schema_instruction(self, schema: Mapping[str, Any]) -> str:
        # Render the schema context required when the endpoint cannot enforce its fields natively.
        return (
            "\n\nYou MUST respond with ONLY a valid JSON object matching this exact schema. "
            "Use these exact field names and types:\n"
            f"```json\n{json.dumps(schema, indent=2, ensure_ascii=False)}\n```"
        )


STRUCTURED_OUTPUT_DESCRIPTIONS: dict[StructuredOutputSupport, StructuredOutputDescription] = {
    StructuredOutputSupport.NATIVE_SCHEMA: StructuredOutputDescription(
        support=StructuredOutputSupport.NATIVE_SCHEMA,
        title="Native JSON Schema",
        description=(
            "The provider compiles the declared JSON Schema into its response format and constrains "
            "generation to that shape. This is the strongest mode because invalid field structure is "
            "prevented before text reaches the SDK. The SDK still validates the response so application "
            "code receives the declared Pydantic instance. If a model-specific override lacks this mode, "
            "the registry selects its declared lower tier instead of assuming native support."
        ),
        fallback=StructuredOutputSupport.STRICT_TOOLS,
    ),
    StructuredOutputSupport.STRICT_TOOLS: StructuredOutputDescription(
        support=StructuredOutputSupport.STRICT_TOOLS,
        title="Strict tool arguments",
        description=(
            "The provider validates arguments for a required tool call against the declared schema. "
            "It provides a schema-shaped result but is weaker than native response decoding because the "
            "response is represented as a tool interaction. The SDK validates the final value and uses "
            "its repair loop if the endpoint still returns an invalid result. Providers without strict "
            "tools may safely degrade to JSON mode or prompt-only output."
        ),
        fallback=StructuredOutputSupport.JSON_MODE,
    ),
    StructuredOutputSupport.JSON_MODE: StructuredOutputDescription(
        support=StructuredOutputSupport.JSON_MODE,
        title="JSON mode",
        description=(
            "The provider guarantees syntactically valid JSON but does not enforce the schema's field "
            "names, types, or constraints. The SDK supplies the full schema in system guidance and then "
            "validates the returned JSON against the requested Pydantic model. Invalid values are repaired "
            "within the normal contract budget. A provider that cannot guarantee JSON can still use the "
            "prompt-only tier without changing application code."
        ),
        fallback=StructuredOutputSupport.PROMPT_ONLY,
    ),
    StructuredOutputSupport.PROMPT_ONLY: StructuredOutputDescription(
        support=StructuredOutputSupport.PROMPT_ONLY,
        title="Prompt-only schema guidance",
        description=(
            "The provider has no declared structured-output transport, so the SDK includes the schema in "
            "the system guidance and parses the response after generation. Pydantic validation and the "
            "output-contract repair loop preserve the public output_schema guarantee even though the provider "
            "does not enforce it natively. This is the conservative default for unknown providers because "
            "it remains functional without sending a provider-specific payload that may be rejected."
        ),
        fallback=None,
    ),
}


__all__ = [
    "MODEL_SUPPORT",
    "PROVIDER_SUPPORT",
    "STRUCTURED_OUTPUT_AS_OF",
    "STRUCTURED_OUTPUT_DESCRIPTIONS",
    "StructuredOutputDescription",
]
