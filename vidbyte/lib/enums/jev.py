"""FILE: vidbyte/lib/enums/jev.py

PURPOSE: Defines the closed Jev vocabularies: the TypeSafe question types, the preflight presets a JevAgent user can enable, the key of every preflight question, and the run-state done-check values (sections, section status, event kinds, and stage failures).
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates questions against these members, `vidbyte/providers/typesafe.py` serializes question types onto the wire, `vidbyte/lib/jev/presets.py` maps each fixed-question preset to its question keys, `vidbyte/lib/jev/preflight/` registers one question per key, `vidbyte/agents/jev/gate/` matches on the presets when it acts on Jev's answers, and `vidbyte/agents/jev/done/` keys run-state sections, event-log entries, and stage verdicts on the done-check members.
ARCHITECTURE NOTE: The vocabulary lives in `vidbyte.lib` because the provider layer, the record layer, and the tool layer all read it, and the lower two may not import the tool layer.
COMMON MODIFICATION PATTERNS: Add a question type only when TypeSafe documents one, then extend JevQuestion validation and TypeSafeProvider answer normalization in the same change. Add a preflight question key together with its question dataclass in `vidbyte/lib/jev/preflight/` and its preset's key list in `vidbyte/lib/jev/presets.py`. Add a JevRunSectionKey member together with its JevRunSection in `vidbyte/agents/jev/done/` and its JevAgentSettings flag.
KNOWN EDGE CASES: `noul` is TypeSafe's own spelling for a yes/no question; keep the serialized value exactly as the API expects it. A question key's value is the answer name Jev returns, so it must stay unique across every preset. TOOL_SELECTOR has no question keys because it asks one question per configured tool, built at run time. Done-check values appear in `JevAgent.response.run_report`, so renaming one is a breaking change for callers that read it.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, and https://docs.typesafe.ai/api.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_required_sequence.py, scripts/test-jev-agent-scaffold.py, and scripts/test-jev-preflight.py.
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
    """The preflight flags a JevAgent user can enable; each one turns on a fixed policy that JevPreflightGate (fixed-question presets) or the tool selector acts on."""

    CLARITY = "clarity"
    TOOL_SELECTOR = "tool_selector"


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


class JevRunSectionKey(str, Enum):
    """Named run-state sections (done checks) a JevAgent setting can enable."""

    REQUIRED_SEQUENCE = "required_sequence"


class JevSectionStatus(str, Enum):
    """Whether a run-state section gates this run."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    UNAVAILABLE = "unavailable"


class JevRunEventKind(str, Enum):
    """Source of one numbered event in the run's event log."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FINISH_REVIEW = "finish_review"


class JevStageFailure(str, Enum):
    """First reason a required stage failed its finish review."""

    NO_WORK = "no_work"
    OUT_OF_ORDER = "out_of_order"
    WORK_NOT_SHOWN = "work_not_shown"
    PREVIOUS_OUTPUT_NOT_USED = "previous_output_not_used"


__all__ = [
    "JevPreflightPreset",
    "JevPreflightQuestionKey",
    "JevQuestionType",
    "JevRunEventKind",
    "JevRunSectionKey",
    "JevSectionStatus",
    "JevStageFailure",
]
