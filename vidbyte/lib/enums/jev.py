"""FILE: vidbyte/lib/enums/jev.py

PURPOSE: Defines the closed Jev vocabularies: the TypeSafe question types, the preflight presets a JevAgent user can enable, and the key of every preflight question.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates questions against these members, `vidbyte/providers/typesafe.py` serializes question types onto the wire, `vidbyte/lib/jev/presets.py` maps each fixed-question preset to its question keys, `vidbyte/lib/jev/preflight/` registers one question per key, and `vidbyte/agents/jev/preflight/` matches on the presets when it acts on Jev's answers.
ARCHITECTURE NOTE: The vocabulary lives in `vidbyte.lib` because the provider layer, the record layer, and the tool layer all read it, and the lower two may not import the tool layer.
COMMON MODIFICATION PATTERNS: Add a question type only when TypeSafe documents one, then extend JevQuestion validation and TypeSafeProvider answer normalization in the same change. Add a preflight question key together with its question dataclass in `vidbyte/lib/jev/preflight/` and its preset's key list in `vidbyte/lib/jev/presets.py`.
KNOWN EDGE CASES: `noul` is TypeSafe's own spelling for a yes/no question; keep the serialized value exactly as the API expects it. A question key's value is the answer name Jev returns, so it must stay unique across every preset. TOOL_SELECTOR has no question keys because it asks one question per configured tool, built at run time.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, and https://docs.typesafe.ai/api.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, scripts/test-jev-agent-scaffold.py, and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from enum import Enum


class JevQuestionType(str, Enum):
    """TypeSafe System One question types."""

    NOUL = "noul"
    CHOICE = "choice"
    SCORE = "score"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return the serialized values in declaration order."""
        return tuple(member.value for member in cls)


class JevPreflightPreset(str, Enum):
    """The preflight flags a JevAgent user can enable; each one turns on a fixed policy that JevPreflight acts on."""

    CLARITY = "clarity"
    TOOL_SELECTOR = "tool_selector"


class JevPreflightQuestionKey(str, Enum):
    """The key of every fixed preflight question, prefixed by the preset that asks it.

    The value is the question name sent to Jev and the key its answer comes back under.
    """

    CLARITY_GOAL = "clarity.goal"
    CLARITY_DELIVERABLE = "clarity.deliverable"
    CLARITY_TARGET = "clarity.target"
    CLARITY_REFERENCES = "clarity.references"
    CLARITY_SCOPE = "clarity.scope"
    CLARITY_COMPLETION = "clarity.completion"
    CLARITY_INFORMATION = "clarity.information"
    CLARITY_CONSTRAINTS = "clarity.constraints"
    CLARITY_PRIORITIES = "clarity.priorities"
    CLARITY_CONSISTENCY = "clarity.consistency"
    CLARITY_TIME_CONTEXT = "clarity.time_context"
    CLARITY_SINGLE_READING = "clarity.single_reading"


__all__ = ["JevPreflightPreset", "JevPreflightQuestionKey", "JevQuestionType"]
