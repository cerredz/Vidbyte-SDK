"""FILE: vidbyte/lib/enums/jev.py

PURPOSE: Defines the closed Jev vocabularies: the TypeSafe question types, the preflight presets and done checks a JevAgent user can enable, and the key of every preflight and done question, including both guaranteed-next-action judgments.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates questions against these members, `vidbyte/providers/typesafe.py` serializes question types onto the wire, `vidbyte/lib/jev/presets.py` maps each fixed-question preset to its question keys, `vidbyte/lib/jev/preflight/` registers one question per key, `vidbyte/agents/jev/gate/` matches on the presets when it acts on Jev's answers, and `vidbyte/agents/jev/done/` builds enabled done-check schemas and their questions.
ARCHITECTURE NOTE: The vocabulary lives in `vidbyte.lib` because the provider layer, the record layer, and the tool layer all read it, and the lower two may not import the tool layer.
COMMON MODIFICATION PATTERNS: Add a question type only when TypeSafe documents one, then extend JevQuestion validation and TypeSafeProvider answer normalization in the same change. Add a preflight question key together with its question dataclass in `vidbyte/lib/jev/preflight/` and its preset's key list in `vidbyte/lib/jev/presets.py`. Add a done check with the run-state and handoff sections its items require, and its question in `vidbyte/lib/jev/done/`; post-run-derived items belong in the handoff rather than the pre-run state.
KNOWN EDGE CASES: `noul` is TypeSafe's own spelling for a yes/no question; keep the serialized value exactly as the API expects it. A question key's value is the answer name Jev returns, so it must stay unique across every preset. TOOL_SELECTOR has no question keys because it asks one question per configured tool, built at run time.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-guaranteed-next-actions.md, skills/jev-continuation/SKILL.md, and https://docs.typesafe.ai/api.md.
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
    """The preflight flags a JevAgent user can enable; each one turns on a fixed policy that JevPreflightGate (fixed-question presets) or the tool selector acts on."""

    CLARITY = "clarity"
    TOOL_SELECTOR = "tool_selector"


# Load skills/jev-continuation/SKILL.md before adding a member here: it is the step-by-step checklist for adding
# a continuation done check (run-state and handoff sections, the batched Jev question, and the continuation message).
class JevDoneCheck(str, Enum):
    """The done checks a JevAgent user can enable; each assembles the items and evidence it needs and asks Jev before a run may finish."""

    MULTI_PART = "multi_part"
    CLAIMS = "claims"
    GUARANTEED_NEXT_ACTIONS = "guaranteed_next_actions"


class JevDoneQuestionKey(str, Enum):
    """The key of every fixed done question, prefixed by the done check that asks it.

    The value is the question name sent to Jev and the key its answer comes back under.
    """

    MULTI_PART_DELIVERED = "multi_part.delivered"
    CLAIMS_SUPPORTED = "claims.supported"
    GUARANTEED_NEXT_ACTIONS_NECESSARY = "guaranteed_next_actions.necessary"
    GUARANTEED_NEXT_ACTIONS_UNFINISHED = "guaranteed_next_actions.unfinished"


class JevClaimKind(str, Enum):
    """The closed categories of factual assertions the CLAIMS handoff can describe."""

    SOURCE_CONTENT = "source_content"
    ARTIFACT_CHANGE = "artifact_change"
    COMMAND_RESULT = "command_result"
    TEST_RESULT = "test_result"
    RUN_ACTIVITY = "run_activity"
    OTHER_FACT = "other_fact"


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


__all__ = ["JevClaimKind", "JevDoneCheck", "JevDoneQuestionKey", "JevPreflightPreset", "JevPreflightQuestionKey", "JevQuestionType"]
