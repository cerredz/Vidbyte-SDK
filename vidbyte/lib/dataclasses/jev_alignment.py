"""FILE: vidbyte/lib/dataclasses/jev_alignment.py

PURPOSE: Defines the immutable records and structural contracts for JevAgent self-alignment; it owns inputs, fixed-question descriptors, edit evidence, usage shape, and results, not policy decisions.
ROLE IN CODEBASE: JevAgentAlignment creates and returns these records; JevPromptDraft stores edits in ContextManager; JevResponse and JevAgent.response expose the final alignment result.
ARCHITECTURE NOTE: This module is in the shared dataclass layer to keep the records below the Jev agent and tool implementations. Enums live in vidbyte/lib/enums/jev.py.
COMMON MODIFICATION PATTERNS: Add or change a record here alongside its validation, the owning runtime behavior, and tests/test_jev_alignment.py; update exports only for supported public records.
WHAT NOT TO DO IN THIS FILE: Do not call Jev, edit prompts, write runtime policy, define enums, or import from vidbyte/agents or vidbyte/tools.
KNOWN EDGE CASES: JevAlignmentInput accepts SDK tool objects and freezes the collection to a tuple; empty tool lists are valid and omit tool-specific questions.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/jev-agent-alignment.md and https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_alignment.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from vidbyte.lib.constants.jev import (
    JEV_ALIGNMENT_MAX_ADDED_CHARS as JEV_ALIGNMENT_MAX_ADDED_CHARS,
)
from vidbyte.lib.constants.jev import (
    JEV_ALIGNMENT_MAX_EDIT_CHARS as JEV_ALIGNMENT_MAX_EDIT_CHARS,
)
from vidbyte.lib.constants.jev import (
    JEV_ALIGNMENT_QUESTION_PREFIX as JEV_ALIGNMENT_QUESTION_PREFIX,
)
from vidbyte.lib.constants.jev import (
    JEV_DYNAMIC_ALIGNMENT_PREAMBLE as DYNAMIC_ALIGNMENT_PREAMBLE,
)
from vidbyte.lib.constants.jev import (
    JEV_STATIC_ALIGNMENT_PREAMBLE as STATIC_ALIGNMENT_PREAMBLE,
)
from vidbyte.lib.dataclasses.jev import (
    JevAlignmentCondition,
    JevAlignmentGap,
    JevAlignmentInput,
    JevAlignmentQuestion,
    JevAlignmentResult,
    JevAlignmentRole,
    JevAlignmentStateKind,
    JevOption,
    JevPromptEdit,
    JevPromptEditContextItem,
    JevPromptSection,
    JevQuestion,
    JevToolSelectorResponse,
)
from vidbyte.lib.enums.jev import (
    JevAlignmentCondition,
    JevAlignmentRole,
    JevAlignmentStateKind,
    JevAlignmentStatus,
    JevPromptSection,
    JevQuestionType,
)
from vidbyte.lib.registries.pricing import ModelPricing


class JevAlignmentToolSpec(Protocol):
    """Minimum SDK tool schema fields Jev needs to assess tool guidance."""

    name: str
    description: str


class JevAlignmentTool(Protocol):
    """Structural contract for an SDK tool passed to Jev alignment."""

    def spec(self) -> JevAlignmentToolSpec:
        """Return the SDK tool's public model-facing specification."""


class JevUsageRecord(Protocol):
    """Read-only usage contract for Jev calls, implemented by the provider usage record."""

    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    raw: Mapping[str, Any]

    @property
    def cached_input_tokens(self) -> int | None:
        """Return cached input tokens when the provider reports them."""

    @property
    def total_prompt_tokens(self) -> int | None:
        """Return all tokens counted as prompt input."""

    @property
    def cache_hit_rate(self) -> float | None:
        """Return the reported prompt cache hit ratio, if available."""

    def cost_usd(self, pricing: ModelPricing | None) -> float | None:
        """Return usage cost for the supplied pricing record, if calculable."""


JEV_ALIGNMENT_EDITABLE_SECTIONS = frozenset({JevPromptSection.TOOLS, JevPromptSection.METHOD, JevPromptSection.OUTPUT, JevPromptSection.EXCEPTIONS, JevPromptSection.PRIORITIES, JevPromptSection.GLOSSARY})
















__all__ = [
    "DYNAMIC_ALIGNMENT_PREAMBLE",
    "JEV_ALIGNMENT_EDITABLE_SECTIONS",
    "JEV_ALIGNMENT_MAX_ADDED_CHARS",
    "JEV_ALIGNMENT_MAX_EDIT_CHARS",
    "JEV_ALIGNMENT_QUESTION_PREFIX",
    "STATIC_ALIGNMENT_PREAMBLE",
    "JevAlignmentCondition",
    "JevAlignmentGap",
    "JevAlignmentInput",
    "JevAlignmentQuestion",
    "JevAlignmentResult",
    "JevAlignmentRole",
    "JevAlignmentStateKind",
    "JevAlignmentStatus",
    "JevAlignmentTool",
    "JevAlignmentToolSpec",
    "JevPromptEdit",
    "JevPromptEditContextItem",
    "JevPromptSection",
    "JevToolSelectorResponse",
    "JevUsageRecord",
]
