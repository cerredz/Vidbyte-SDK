"""Context Protocol Header

Description:
    Declares the structured-output enforcement tiers a model endpoint can offer.
Purpose:
    Names how strongly a provider can be made to honor an agent's output_schema, so the runtime
    can pick the strongest available request shape instead of guessing from a provider's name.
Architecture:
    - StructuredOutputSupport: Ordered tiers from grammar-constrained decoding down to prompt-only.
Relations:
    Resolved per (provider, model) by vidbyte.lib.registries.structured_output and consumed by
    vidbyte.agents.runtime when building a model call.
Similar Files:
    - vidbyte/lib/enums/model_provider.py: The provider identities these tiers are declared against.
"""

from __future__ import annotations

from enum import Enum


class StructuredOutputSupport(str, Enum):
    """How strongly one model endpoint can enforce a declared output schema."""

    # Provider compiles the schema into a grammar and masks invalid tokens; shape is guaranteed.
    NATIVE_SCHEMA = "native_schema"
    # Provider validates a forced tool call's arguments against the schema.
    STRICT_TOOLS = "strict_tools"
    # Provider guarantees syntactically valid JSON but enforces none of the declared fields.
    JSON_MODE = "json_mode"
    # Provider offers no enforcement; the schema is described in the prompt and repaired on failure.
    PROMPT_ONLY = "prompt_only"


__all__ = ["StructuredOutputSupport"]
