"""Context Protocol Header

Description:
    Exposes all consolidated registry layers from the Vidbyte SDK.
Purpose:
    Allows modular lookup of agents, models, prompts, tools, and concurrent actors.
Architecture:
    Package initializer.
Relations:
    Located in vidbyte/lib/registries/__init__.py. Imported across the SDK.
Similar Files:
    - vidbyte/agents/runtimes/__init__.py: Runtimes exports.
"""

from __future__ import annotations

from vidbyte.lib.registries.agents import AgentRegistry
from vidbyte.lib.registries.components import ComponentRegistry
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.registries.pricing import DEEPSEEK_TIME_OF_DAY_RATES, OPENAI_GPT56_TIER_RATES, OPENAI_GPT6_TIER_RATES, ModelPricing, ModelPricingRegistry, PRICING_AS_OF, PRICING_SOURCE_URL, PROVIDER_PRICING
from vidbyte.lib.registries.prompts import PromptRecord, Prompts
from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher
from vidbyte.lib.registries.runtimes import RuntimeRegistry
from vidbyte.lib.registries.structured_output import MODEL_SUPPORT, PROVIDER_SUPPORT, STRUCTURED_OUTPUT_AS_OF, STRUCTURED_OUTPUT_DESCRIPTIONS, StructuredOutputDescription, StructuredOutputRegistry
from vidbyte.lib.registries.tools import ToolRegistry
from vidbyte.lib.registries.actors import ActorRegistry, actor_registry

__all__ = [
    "AgentRegistry",
    "ComponentRegistry",
    "ProviderModelRegistry",
    "ProviderKeyMatcher",
    "ModelPricing",
    "ModelPricingRegistry",
    "PRICING_AS_OF",
    "PRICING_SOURCE_URL",
    "PROVIDER_PRICING",
    "OPENAI_GPT56_TIER_RATES",
    "OPENAI_GPT6_TIER_RATES",
    "DEEPSEEK_TIME_OF_DAY_RATES",
    "PromptRecord",
    "Prompts",
    "RuntimeRegistry",
    "StructuredOutputRegistry",
    "StructuredOutputDescription",
    "PROVIDER_SUPPORT",
    "MODEL_SUPPORT",
    "STRUCTURED_OUTPUT_AS_OF",
    "STRUCTURED_OUTPUT_DESCRIPTIONS",
    "ToolRegistry",
    "ActorRegistry",
    "actor_registry",
]
