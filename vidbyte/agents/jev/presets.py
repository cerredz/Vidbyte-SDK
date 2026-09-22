"""FILE: vidbyte/agents/jev/presets.py

PURPOSE: Defines JevAgent's closed set of opinionated preflight policies and their fixed classifier questions.
ROLE IN CODEBASE: JevAgentSettings validates public preset names through this registry and JevRuntime resolves their execution definitions.
ARCHITECTURE NOTE: Callers select named capabilities; question wording, scoring thresholds, and clarification prompts remain internal policy.
COMMON MODIFICATION PATTERNS: Add one enum value and one immutable definition, keeping question names globally unique across presets.
KNOWN EDGE CASES: All clarity questions use positive polarity so their true probabilities can be averaged without per-question inversion.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from vidbyte.lib.constants.jev import JEV_NOUL_FALSE, JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.jev import JevOption, JevQuestion
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.errors import ConfigurationError


class JevPreflightPreset(StrEnum):
    """Named Jev preflight policies supported by JevAgent."""

    CLARITY = "clarity"


@dataclass(frozen=True, slots=True)
class JevPreflightDefinition:
    """Internal immutable policy for one registered preflight preset."""

    preset: JevPreflightPreset
    questions: tuple[JevQuestion, ...]
    clarifications: Mapping[str, str]
    threshold: float


_NOUL_OPTIONS = (
    JevOption(name=JEV_NOUL_TRUE, description="The clarity statement is satisfied."),
    JevOption(name=JEV_NOUL_FALSE, description="The clarity statement is not satisfied."),
)


def _clarity_question(name: str, instructions: str) -> JevQuestion:
    return JevQuestion(
        name=f"clarity.{name}",
        question_type=JevQuestionType.NOUL,
        instructions=instructions,
        options=_NOUL_OPTIONS,
    )


CLARITY_QUESTIONS = (
    _clarity_question("goal", "Is the primary goal explicit enough to determine what the user ultimately wants accomplished?"),
    _clarity_question("outcome", "Is the intended real-world outcome clear enough to distinguish successful work from work that merely follows the literal wording?"),
    _clarity_question("deliverable", "Is it clear what concrete output, change, answer, artifact, or action the agent is expected to produce?"),
    _clarity_question("completion", "Is there enough information to determine when the request has been completed correctly?"),
    _clarity_question("scope", "Are the boundaries clear enough to avoid materially overdoing or underdoing the request?"),
    _clarity_question("target", "Is the specific object, codebase, environment, document, account, system, or subject identifiable?"),
    _clarity_question("references", "Can references such as this, that, it, previous, or current be resolved unambiguously?"),
    _clarity_question("language", "Are important words and instructions precise enough to avoid materially different interpretations?"),
    _clarity_question("information", "Does the request provide, identify, or make discoverable the information required to act correctly?"),
    _clarity_question("hidden_information", "Is it unlikely that correct action depends on important facts known to the user but absent from the request?"),
    _clarity_question("assumptions", "Can the request be completed correctly without inventing a material assumption about intent, circumstances, or the result?"),
    _clarity_question("judgment", "Are the remaining judgment calls constrained enough that the agent does not need to ask for a preference?"),
    _clarity_question("constraints", "Are all constraints that could materially alter the solution stated or safely inferable?"),
    _clarity_question("priorities", "When meaningful tradeoffs exist, is the user's priority clear?"),
    _clarity_question("dependencies", "Are prerequisites, dependencies, and ordering clear enough to begin correctly?"),
    _clarity_question("time_context", "Is the relevant deadline, time range, version, or recency clear when it could affect the result?"),
    _clarity_question("consistency", "Is the request internally consistent and compatible with the explicit instructions and context?"),
    _clarity_question("independent_agreement", "Would two capable agents independently agree on the work that should be performed?"),
)


_CLARIFICATIONS = MappingProxyType(
    {
        "clarity.goal": "What is the primary goal you want me to accomplish?",
        "clarity.outcome": "What outcome would make this useful or successful for you?",
        "clarity.deliverable": "What concrete output or change would you like me to produce?",
        "clarity.completion": "What should be true when this request is complete?",
        "clarity.scope": "What should I include, and what should I leave out?",
        "clarity.target": "Which specific object, codebase, environment, document, account, system, or subject should I work on?",
        "clarity.references": "What does the ambiguous reference in your request refer to?",
        "clarity.language": "Could you clarify the key term or instruction that has more than one possible meaning?",
        "clarity.information": "Where can I find the information required to complete this correctly?",
        "clarity.hidden_information": "Is there any important context I should know before I begin?",
        "clarity.assumptions": "Which interpretation or assumption should I use before proceeding?",
        "clarity.judgment": "What preference should guide the remaining judgment call?",
        "clarity.constraints": "What constraints or requirements must the solution respect?",
        "clarity.priorities": "Which tradeoff or priority matters most to you?",
        "clarity.dependencies": "Are there prerequisites, dependencies, or ordering requirements I should follow?",
        "clarity.time_context": "What deadline, time range, version, or recency requirement should I use?",
        "clarity.consistency": "Which of the conflicting instructions should take priority?",
        "clarity.independent_agreement": "Could you restate the request with the intended work and result more explicitly?",
    }
)


class JevPreflightRegistry:
    """Read-only registry for the preflight policies owned by JevAgent."""

    _definitions: Mapping[JevPreflightPreset, JevPreflightDefinition] = MappingProxyType(
        {
            JevPreflightPreset.CLARITY: JevPreflightDefinition(
                preset=JevPreflightPreset.CLARITY,
                questions=CLARITY_QUESTIONS,
                clarifications=_CLARIFICATIONS,
                threshold=0.75,
            )
        }
    )

    @classmethod
    def resolve(cls, preset: JevPreflightPreset) -> JevPreflightDefinition:
        """Return a registered definition or reject an unsupported preset."""
        found = cls._definitions.get(preset)
        if found is None:
            raise ConfigurationError(f"Unsupported Jev preflight preset: {preset!r}.")
        return found

    @classmethod
    def presets(cls) -> tuple[JevPreflightPreset, ...]:
        """Return every registered preset in stable declaration order."""
        return tuple(cls._definitions)


__all__ = ["CLARITY_QUESTIONS", "JevPreflightPreset", "JevPreflightRegistry"]
