"""FILE: vidbyte/lib/configs/reasoning_effort.py

PURPOSE: Declares which reasoning efforts each provider and model documents, and the wire form each provider uses to send one, as fixed capability data checked against the vendors' own docs on REASONING_EFFORT_AS_OF.
ROLE IN CODEBASE: Read by ReasoningEffortRegistry (vidbyte/lib/registries/reasoning_effort.py), which looks rows up, words refusals, and attaches fragments to payloads. Provider adapters, TextModelConfig, JevAgentSettings and the agent guard never read these tables directly; they call the registry.
ARCHITECTURE NOTE: Dependency-light capability data: this module imports only vidbyte.lib.enums and typing, so importing it never starts a configuration loader or a registry. The tables are data, not logic. REASONING_EFFORT_FORMS holds one fragment per provider and value; REASONING_EFFORT_SUPPORT holds, per provider, the lower-cased model ids the vendor docs name and the values they document for each, in enum order.
FUNCTION INVENTORY: None; constants only (REASONING_EFFORT_AS_OF, GEMINI_THINKING_BUDGET_OFF, REASONING_EFFORT_FORMS, REASONING_EFFORT_SUPPORT).
COMMON MODIFICATION PATTERNS: Add or change a row only with a raw-doc quote recorded in the "Reasoning Effort Sources" section of vidbyte/lib/registries/README.md. Bump REASONING_EFFORT_AS_OF whenever the rows are re-checked against the vendor docs. A new provider adds its wire form to REASONING_EFFORT_FORMS and its rows to REASONING_EFFORT_SUPPORT together.
WHAT NOT TO DO IN THIS FILE: 1. Do not map a value to the nearest level the model accepts; an undocumented value has no row cell and is refused. 2. Do not add a row with an empty tuple; an empty result means "no row". 3. Do not add a row for an id outside the provider catalog's exact text ids (MODEL_PROVIDER_RUNNER_TYPE_MAP). 4. Do not import anything above vidbyte.lib.enums.
KNOWN EDGE CASES: A value the vendor silently remaps to another level (DeepSeek medium to high, GLM-5.2 low to high, Muse xhigh to high) has no cell, so it is refused rather than sent under a false name. Gemini accepts none only on 2.5 Flash and 2.5 Flash-Lite, through a thinking budget of GEMINI_THINKING_BUDGET_OFF; no 3.x model documents a thinking-off form. OpenAI's gpt-5.6 is an alias of gpt-5.6-sol and has no row of its own.
RELATED DOCS: vidbyte/lib/registries/README.md (section Reasoning Effort Sources); docs/spec/agent-reasoning-effort/spec.md (section 9.2)
TESTS: tests/features/agent_reasoning_effort
"""

from __future__ import annotations

from typing import Any

from vidbyte.lib.enums import ModelProvider, ReasoningEffort

REASONING_EFFORT_AS_OF = "2026-10-20"

# Gemini 2.5 turns thinking off with a thinking budget of zero tokens.
GEMINI_THINKING_BUDGET_OFF = 0

_NONE = ReasoningEffort.NONE
_MINIMAL = ReasoningEffort.MINIMAL
_LOW = ReasoningEffort.LOW
_MEDIUM = ReasoningEffort.MEDIUM
_HIGH = ReasoningEffort.HIGH
_XHIGH = ReasoningEffort.XHIGH

# @intent send-the-vendors-own-spelling
# Each fragment is the request shape the vendor documents for one
# value. The registry merges a copy into the payload, so a provider's
# spelling lives here once and no adapter builds it by hand.
REASONING_EFFORT_FORMS: dict[ModelProvider, dict[ReasoningEffort, dict[str, Any]]] = {
    ModelProvider.OPENAI: {
        effort: {"reasoning": {"effort": effort.value}}
        for effort in ReasoningEffort
    },
    ModelProvider.ANTHROPIC: {
        _NONE: {"thinking": {"type": "disabled"}},
        _LOW: {"output_config": {"effort": _LOW.value}},
        _MEDIUM: {"output_config": {"effort": _MEDIUM.value}},
        _HIGH: {"output_config": {"effort": _HIGH.value}},
        _XHIGH: {"output_config": {"effort": _XHIGH.value}},
    },
    ModelProvider.GEMINI: {
        _NONE: {
            "generationConfig": {
                "thinkingConfig": {"thinkingBudget": GEMINI_THINKING_BUDGET_OFF}
            }
        },
        _MINIMAL: {"generationConfig": {"thinkingConfig": {"thinkingLevel": "MINIMAL"}}},
        _LOW: {"generationConfig": {"thinkingConfig": {"thinkingLevel": "LOW"}}},
        _MEDIUM: {"generationConfig": {"thinkingConfig": {"thinkingLevel": "MEDIUM"}}},
        _HIGH: {"generationConfig": {"thinkingConfig": {"thinkingLevel": "HIGH"}}},
    },
    ModelProvider.DEEPSEEK: {
        effort: {"reasoning_effort": effort.value} for effort in (_NONE, _LOW, _HIGH)
    },
    ModelProvider.XAI: {
        effort: {"reasoning_effort": effort.value}
        for effort in (_NONE, _LOW, _MEDIUM, _HIGH, _XHIGH)
    },
    ModelProvider.GLM: {
        _NONE: {"thinking": {"type": "disabled"}},
        _LOW: {"thinking": {"type": "enabled"}, "reasoning_effort": _LOW.value},
        _HIGH: {"thinking": {"type": "enabled"}, "reasoning_effort": _HIGH.value},
    },
    ModelProvider.META: {
        effort: {"reasoning_effort": effort.value}
        for effort in (_MINIMAL, _LOW, _MEDIUM, _HIGH)
    },
}

_OPENAI_ALL_BUT_MINIMAL = (_NONE, _LOW, _MEDIUM, _HIGH, _XHIGH)
_LOW_UP = (_LOW, _MEDIUM, _HIGH, _XHIGH)
_GEMINI_LEVELS = (_MINIMAL, _LOW, _MEDIUM, _HIGH)
_GEMINI_LOW_UP = (_LOW, _MEDIUM, _HIGH)
_DEEPSEEK = (_NONE, _LOW, _HIGH)
_GLM_5_3 = (_LOW, _HIGH)
_MUSE = (_MINIMAL, _LOW, _MEDIUM, _HIGH)

# @intent a-cell-is-sent-only-when-the-vendor-names-it
# A value appears in a row only when a raw vendor page names it for
# that model. Remapped and unverified values stay out, so the SDK
# refuses them instead of sending a level the model will not honor.
REASONING_EFFORT_SUPPORT: dict[ModelProvider, dict[str, tuple[ReasoningEffort, ...]]] = {
    # https://developers.openai.com/api/docs/guides/reasoning.md
    ModelProvider.OPENAI: {
        "gpt-5.6-sol": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.6-terra": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.6-luna": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-6-sol": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-6-luna": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-6.1-sol": _LOW_UP,
        "gpt-6-astra": _LOW_UP,
        "gpt-5.5": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.5-pro": (_MEDIUM, _HIGH, _XHIGH),
        "gpt-5.4": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.4-mini": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.4-nano": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.4-pro": (_MEDIUM, _HIGH, _XHIGH),
        "gpt-5.3-codex": _LOW_UP,
        "gpt-5": (_MINIMAL, _LOW, _MEDIUM, _HIGH),
    },
    # https://platform.claude.com/docs/en/build-with-claude/effort.md
    ModelProvider.ANTHROPIC: {
        "claude-opus-5-5": _LOW_UP,
        "claude-sonnet-5-5": _LOW_UP,
        "claude-fable-5-1": _LOW_UP,
        "claude-mythos-5-1": _LOW_UP,
        "claude-fable-5": _LOW_UP,
        "claude-mythos-5": _LOW_UP,
        "claude-opus-5": (_NONE, *_LOW_UP),
        "claude-haiku-5-5": (_NONE, *_LOW_UP),
        "claude-sonnet-5": (_NONE, *_LOW_UP),
        "claude-opus-4-8": (_NONE, *_LOW_UP),
        "claude-haiku-4-5": (_NONE,),
        "claude-haiku-4-5-20251001": (_NONE,),
    },
    # https://ai.google.dev/api/generate-content.md.txt
    ModelProvider.GEMINI: {
        "gemini-3.8-flash": _GEMINI_LOW_UP,
        "gemini-3.6-flash": _GEMINI_LEVELS,
        "gemini-3.5-flash": _GEMINI_LEVELS,
        "gemini-3.5-flash-lite": _GEMINI_LEVELS,
        "gemini-3.1-flash-lite": _GEMINI_LEVELS,
        "gemini-3-flash-preview": _GEMINI_LEVELS,
        "gemini-3.1-pro-preview": _GEMINI_LOW_UP,
        "gemini-2.5-flash": (_NONE,),
        "gemini-2.5-flash-lite": (_NONE,),
    },
    # https://api-docs.deepseek.com/api/create-chat-completion/
    ModelProvider.DEEPSEEK: {
        "deepseek-v4-pro": _DEEPSEEK,
        "deepseek-flash": _DEEPSEEK,
        "deepseek-v4-flash": _DEEPSEEK,
    },
    # https://docs.x.ai/developers/model-capabilities/text/reasoning.md
    ModelProvider.XAI: {
        "grok-4.7": _LOW_UP,
        "grok-4.6": _LOW_UP,
        "grok-4.5": (_LOW, _MEDIUM, _HIGH),
        "grok-4.3": (_NONE, _LOW, _MEDIUM, _HIGH),
    },
    # https://docs.z.ai/guides/capabilities/thinking.md
    ModelProvider.GLM: {
        "glm-5.2": (_NONE, _HIGH),
        "glm-5.3": _GLM_5_3,
        "glm-5.3-flash": _GLM_5_3,
        "glm-5.3-flashx": _GLM_5_3,
    },
    # https://dev.meta.ai/docs/reasoning.md
    ModelProvider.META: {
        "muse-spark-1.1": _MUSE,
        "muse-spark-1.2": _MUSE,
        "muse-spark-1.2-contributor": _MUSE,
        "muse-spark-1.3": _MUSE,
        "muse-spark-1.3-contributor": _MUSE,
    },
}

__all__ = [
    "GEMINI_THINKING_BUDGET_OFF",
    "REASONING_EFFORT_AS_OF",
    "REASONING_EFFORT_FORMS",
    "REASONING_EFFORT_SUPPORT",
]
