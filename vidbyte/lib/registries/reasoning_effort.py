"""FILE: vidbyte/lib/registries/reasoning_effort.py

PURPOSE: Defines ReasoningEffortRegistry, which answers which reasoning efforts a provider and model document, explains in one sentence why a requested effort cannot be sent, and merges the provider's wire form for a supported effort into a request payload.
ROLE IN CODEBASE: Called by TextModelConfig and JevAgentSettings (construction refusals), by AgentReasoningEffortGuard (vidbyte/agents/reasoning_effort.py, the refusal across the fallback chain), and by the four payload builders in vidbyte/providers (openai.py, anthropic.py, gemini.py and compatible.py), which attach the fragment just before extra_body.
ARCHITECTURE NOTE: Lib layer. This module imports only vidbyte.lib.configs.reasoning_effort, vidbyte.lib.enums, vidbyte.lib.errors and vidbyte.lib.registries.models. Lookup uses the id ProviderModelRegistry.normalize_model returns (the provider's own prefix dropped, MODEL_ALIASES applied), stripped and lower-cased. An id with no row supports nothing, and the refusal for it says only that the SDK's table, as checked on REASONING_EFFORT_AS_OF, has no row, so a model the vendor added later is not called incapable. A gateway mode is refused before any table lookup, because only TextModelMode.DIRECT sends an effort.
FUNCTION INVENTORY: ReasoningEffortRegistry.supported (the documented values for a provider and model, or () when the table has no row); ReasoningEffortRegistry.refusal (the mode, capability or no-row reason, or None); ReasoningEffortRegistry.attach (merges a private copy of the fragment into a payload, or raises the refusal text); _mode_refusal words the gateway-mode reason; _capability_refusal words the capability or no-row reason; _merge merges nested dictionaries key by key.
COMMON MODIFICATION PATTERNS: Table rows and wire forms change in vidbyte/lib/configs/reasoning_effort.py, never here, each with a raw-doc source in the registries README. A new refusal reason is one more leaf helper called from refusal, after the existing ones, so the order callers rely on stays the same.
WHAT NOT TO DO IN THIS FILE: 1. Do not map a value to the nearest level a model accepts; an undocumented value is refused. 2. Do not mutate or alias the tables; attach merges a deep copy, so no two payloads share an object. 3. Do not put table data here. 4. Do not quote keys or prompts in a reason; it names the provider, model, value and modes only.
KNOWN EDGE CASES: The runner's prefix map builds ids, such as dated snapshots, that have no row; they get the no-row reason. A vendor that silently remaps a value (DeepSeek medium, GLM-5.2 low, Muse xhigh) has no cell for it, so it is refused. A reason quotes the caller's model id stripped, not normalized, so the caller can find it in their own code.
RELATED DOCS: vidbyte/lib/registries/README.md (section Reasoning Effort Sources); docs/spec/agent-reasoning-effort/spec.md (sections 8.5 and 9.2)
TESTS: tests/features/agent_reasoning_effort
"""

from __future__ import annotations

import copy
from typing import Any

from vidbyte.lib.configs.reasoning_effort import (
    REASONING_EFFORT_AS_OF,
    REASONING_EFFORT_FORMS,
    REASONING_EFFORT_SUPPORT,
)
from vidbyte.lib.enums import ModelProvider, ReasoningEffort, TextModelMode
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry


class ReasoningEffortRegistry:
    """Resolves, explains and attaches the reasoning effort a provider and model document."""

    @classmethod
    def supported(cls, provider: ModelProvider | str, model: str) -> tuple[ReasoningEffort, ...]:
        """Return the documented values for a provider and model, or () when the table has no row."""
        # @intent no-row-supports-nothing
        # No row is ever empty, so () always means the table does not
        # list the model and every value is refused. An unknown provider
        # or a blank model raises the catalog's own ConfigurationError.
        provider_member = ProviderModelRegistry._require_provider(provider)
        # Look the model up the way the catalog names it: without the
        # provider's own prefix, with aliases applied, in lower case.
        lookup = ProviderModelRegistry.normalize_model(provider_member, model).strip().lower()
        return REASONING_EFFORT_SUPPORT.get(provider_member, {}).get(lookup, ())

    @classmethod
    def refusal(cls, *, provider: ModelProvider | str, model: str, effort: ReasoningEffort, mode: TextModelMode) -> str | None:
        """Return why the effort cannot be sent on this call, or None when it can."""
        # @intent mode-is-refused-before-the-model
        # The gateway does not accept an effort, so a gateway mode is
        # refused whatever the model; only then does the table decide.
        mode_reason = cls._mode_refusal(mode)
        if mode_reason is not None:
            return mode_reason
        # Check the value against the model's row; a listed value sends.
        values = cls.supported(provider, model)
        if effort in values:
            return None
        provider_member = ProviderModelRegistry._require_provider(provider)
        return cls._capability_refusal(provider_member, model, effort, values)

    @classmethod
    def attach(cls, payload: dict[str, Any], *, provider: ModelProvider | str, model: str, effort: ReasoningEffort | None) -> None:
        """Merge the provider's wire form for the effort into the payload, or raise the refusal text."""
        # @intent attach-never-sends-an-unsupported-value
        # Construction already refused unsupported cells, but a payload
        # builder must still never send one, so it raises the same text.
        # Nothing is added when the effort is unset.
        if effort is None:
            return
        # Refuse a value the model's row does not list.
        values = cls.supported(provider, model)
        provider_member = ProviderModelRegistry._require_provider(provider)
        if effort not in values:
            raise ConfigurationError(
                cls._capability_refusal(provider_member, model, effort, values),
                details={"field": "reasoning_effort", "provider": provider_member.value, "model": model.strip(), "reasoning_effort": effort.value},
            )
        # Merge a private copy, so nested keys the builder already set
        # survive and no payload ever shares an object with the table.
        fragment = copy.deepcopy(REASONING_EFFORT_FORMS[provider_member][effort])
        cls._merge(payload, fragment)

    @staticmethod
    def _mode_refusal(mode: TextModelMode) -> str | None:
        # Words the reason a gateway mode cannot carry an effort.
        if mode is TextModelMode.DIRECT:
            return None
        return f"TextModelMode.{mode.name} sends calls through the Vidbyte gateway, which does not accept a reasoning effort; only TextModelMode.DIRECT sends it"

    @staticmethod
    def _capability_refusal(provider_member: ModelProvider, model: str, effort: ReasoningEffort, supported: tuple[ReasoningEffort, ...]) -> str:
        # @intent no-row-is-not-called-incapable
        # A model with a row gets the values it does support; one with
        # no row gets the table's check date, as the vendor may have
        # added the model after the SDK's table was last checked.
        if not supported:
            return f"{provider_member.value}:{model.strip()} is not in the SDK's reasoning-effort table, so reasoning effort '{effort.value}' cannot be sent to it; the table was checked against vendor docs on {REASONING_EFFORT_AS_OF} (see \"Reasoning Effort Sources\" in vidbyte/lib/registries/README.md)"
        return f"{provider_member.value}:{model.strip()} has no documented form for reasoning effort '{effort.value}' (it supports {', '.join(value.value for value in supported)})"

    @staticmethod
    def _merge(target: dict[str, Any], fragment: dict[str, Any]) -> None:
        # Merges nested dictionaries key by key; other values replace.
        for key, value in fragment.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                ReasoningEffortRegistry._merge(target[key], value)
            else:
                target[key] = value


__all__ = [
    "REASONING_EFFORT_AS_OF",
    "REASONING_EFFORT_FORMS",
    "REASONING_EFFORT_SUPPORT",
    "ReasoningEffortRegistry",
]
