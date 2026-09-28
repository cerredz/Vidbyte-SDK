"""FILE: vidbyte/lib/enums/jev.py

PURPOSE: Defines the closed Jev vocabularies: the TypeSafe question types, the preflight presets and done checks a JevAgent user can enable, and the key of every preflight and done question.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates questions against these members, `vidbyte/providers/typesafe.py` serializes question types onto the wire, `vidbyte/lib/jev/presets.py` maps each fixed-question preset to its question keys, `vidbyte/lib/jev/preflight/` registers one question per key, `vidbyte/agents/jev/gate/` matches on the presets when it acts on Jev's answers, and `vidbyte/agents/jev/done/` builds JevRunState's schema and JevHandoff's evidence sections from the enabled done checks.
ARCHITECTURE NOTE: The vocabulary lives in `vidbyte.lib` because the provider layer, the record layer, and the tool layer all read it, and the lower two may not import the tool layer.
COMMON MODIFICATION PATTERNS: Add a question type only when TypeSafe documents one, then extend JevQuestion validation and TypeSafeProvider answer normalization in the same change. Add a preflight question key together with its question dataclass in `vidbyte/lib/jev/preflight/` and its preset's key list in `vidbyte/lib/jev/presets.py`. Add a done check together with its state section, its evidence section, and its question in `vidbyte/lib/jev/done/`.
KNOWN EDGE CASES: `noul` is TypeSafe's own spelling for a yes/no question; keep the serialized value exactly as the API expects it. A question key's value is the answer name Jev returns, so it must stay unique across every preset. TOOL_SELECTOR has no question keys because it asks one question per configured tool, built at run time.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, and https://docs.typesafe.ai/api.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, scripts/test-jev-agent-scaffold.py, and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from enum import Enum, StrEnum


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
    """The preflight flags a JevAgent user can enable; each one turns on a fixed policy that JevPreflightGate (fixed-question presets) or the tool selector acts on."""

    CLARITY = "clarity"
    TOOL_SELECTOR = "tool_selector"


# Load skills/jev-continuation/SKILL.md before adding a member here: it is the step-by-step checklist for adding
# a continuation done check (run-state and handoff sections, the batched Jev question, and the continuation message).
class JevDoneCheck(str, Enum):
    """The done checks a JevAgent user can enable; each adds its own section to JevRunState's state and JevHandoff's evidence, and asks its own Jev question before a run may finish."""

    MULTI_PART = "multi_part"


class JevDoneQuestionKey(str, Enum):
    """The key of every fixed done question, prefixed by the done check that asks it.

    The value is the question name sent to Jev and the key its answer comes back under.
    """

    MULTI_PART_DELIVERED = "multi_part.delivered"


class JevPreflightQuestionKey(str, Enum):
    """The key of every fixed preflight question, prefixed by the preset that asks it.

    The value is the question name sent to Jev and the key its answer comes back under.
    """

    CLARITY_ACTION = "clarity.action"
    CLARITY_OBJECT = "clarity.object"
    CLARITY_DELIVERABLE = "clarity.deliverable"
    CLARITY_TARGET = "clarity.target"
    CLARITY_REFERENCES = "clarity.references"
    CLARITY_SCOPE_PARTS = "clarity.scope_parts"
    CLARITY_SCOPE_SIZE = "clarity.scope_size"
    CLARITY_COMPLETION = "clarity.completion"
    CLARITY_INFORMATION = "clarity.information"
    CLARITY_CONSTRAINTS = "clarity.constraints"
    CLARITY_PRIORITIES = "clarity.priorities"
    CLARITY_CONSISTENCY = "clarity.consistency"
    CLARITY_TIME_CONTEXT = "clarity.time_context"
    CLARITY_SINGLE_READING = "clarity.single_reading"


class JevAlignmentQuestionKey(StrEnum):
    """Stable keys for the fixed self-alignment questions asked by JevAgent."""

    FIT_TASK_IN_SCOPE = "fit.task_in_scope"
    FIT_WITHIN_BOUNDARIES = "fit.within_boundaries"
    FIT_ROLE_KEPT = "fit.role_kept"
    FIT_SINGLE_TASK = "fit.single_task"
    SECTION_ROLE = "section.role"
    SECTION_SCOPE = "section.scope"
    SECTION_BOUNDARIES = "section.boundaries"
    SECTION_AUDIENCE = "section.audience"
    SECTION_TOOL_GUIDANCE = "section.tool_guidance"
    SECTION_METHOD = "section.method"
    SECTION_OUTPUT = "section.output"
    SECTION_EXCEPTIONS = "section.exceptions"
    SECTION_MIXED_REQUESTS = "section.mixed_requests"
    SECTION_PRIORITIES = "section.priorities"
    COVER_SCOPE_EXPLICIT = "cover.scope_explicit"
    COVER_TERMS = "cover.terms"
    COVER_FACTS = "cover.facts"
    COVER_METHOD = "cover.method"
    COVER_OUTPUT = "cover.output"
    COVER_PERMISSIONS = "cover.permissions"
    COVER_CONSISTENT = "cover.consistent"


class JevPromptSection(StrEnum):
    """Named system-prompt section considered by JevAgent self-alignment."""

    ROLE = "role"
    SCOPE = "scope"
    BOUNDARIES = "boundaries"
    AUDIENCE = "audience"
    KNOWLEDGE = "knowledge"
    PERMISSIONS = "permissions"
    TOOLS = "tools"
    METHOD = "method"
    OUTPUT = "output"
    EXCEPTIONS = "exceptions"
    PRIORITIES = "priorities"
    GLOSSARY = "glossary"

    @property
    def heading(self) -> str:
        """Return the markdown heading text used for this section."""
        return self.value.capitalize()


class JevAlignmentRole(StrEnum):
    """Code action taken when a fixed alignment question receives a no answer."""

    GATE = "gate"
    SIGNAL = "signal"
    OWNER = "owner"
    AGENT = "agent"


class JevAlignmentStateKind(StrEnum):
    """State fields available to one alignment question set."""

    STATIC = "static"
    DYNAMIC = "dynamic"


class JevAlignmentCondition(StrEnum):
    """Condition under which a fixed alignment question is applicable."""

    ALWAYS = "always"
    HAS_TOOLS = "has_tools"
    MULTI_TASK = "multi_task"


class JevAlignmentStatus(StrEnum):
    """Outcome of one alignment pass."""

    ALIGNED = "aligned"
    NO_GAPS = "no_gaps"
    OUT_OF_SCOPE = "out_of_scope"
    EDITS_REJECTED = "edits_rejected"
    UNAVAILABLE = "unavailable"
    SKIPPED = "skipped"


__all__ = [
    "JevAlignmentCondition",
    "JevAlignmentQuestionKey",
    "JevAlignmentRole",
    "JevAlignmentStateKind",
    "JevAlignmentStatus",
    "JevDoneCheck",
    "JevDoneQuestionKey",
    "JevPreflightPreset",
    "JevPreflightQuestionKey",
    "JevPromptSection",
    "JevQuestionType",
]
