"""FILE: vidbyte/agents/jev/presets.py

PURPOSE: Defines JevAgent's preflight configuration: the closed registry of opinionated presets, caller-written custom questions, and the JevPreflight container that combines them.
ROLE IN CODEBASE: JevAgentSettings holds one JevPreflight; JevRuntime evaluates the definitions it returns in a single Jev request.
ARCHITECTURE NOTE: Presets keep their question wording, thresholds, and clarification prompts internal. Custom questions become one extra definition with a zero threshold, so the runtime records their answers without acting on them.
COMMON MODIFICATION PATTERNS: Add one enum value and one registered definition per preset, keeping question names globally unique across presets.
KNOWN EDGE CASES: All clarity questions use positive polarity so their true probabilities can be averaged without per-question inversion. CUSTOM is a result key, never a registered preset.
RELATED DOCS: docs/design/jev-preflight-clarity.md, docs/design/jev-preflight-custom-questions.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from vidbyte.lib.constants.jev import JEV_MAX_QUESTIONS, JEV_NOUL_FALSE, JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.jev import JevOption, JevQuestion
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.errors import ConfigurationError


class JevPreflightPreset(StrEnum):
    """Named Jev preflight policies supported by JevAgent."""

    CLARITY = "clarity"
    CUSTOM = "custom"  # results key for caller-written questions; never registered, so it cannot be selected


@dataclass(frozen=True, slots=True)
class JevPreflightDefinition:
    """Internal immutable policy for one preflight group: a registered preset or the caller's custom questions."""

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


@dataclass(frozen=True, slots=True)
class JevCustomQuestion:
    """One caller-written yes/no question that Jev answers in the same request as the preset questions."""

    name: str
    question: str

    def __post_init__(self) -> None:
        # Checks the name here because the "custom." prefix would make a blank name look valid to JevQuestion.
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConfigurationError("JevCustomQuestion.name must be a non-blank string.")
        if not isinstance(self.question, str):
            raise ConfigurationError("JevCustomQuestion.question must be a string.")
        self.to_jev_question()

    def to_jev_question(self) -> JevQuestion:
        """Return the noul question sent to Jev, namespaced so it cannot collide with preset questions."""
        return JevQuestion(
            name=f"{JevPreflightPreset.CUSTOM.value}.{self.name}",
            question_type=JevQuestionType.NOUL,
            instructions=self.question,
        )


@dataclass(frozen=True, slots=True)
class JevPreflight:
    """Everything JevAgent asks Jev before its main loop: registered presets plus caller-written questions."""

    preset: tuple[JevPreflightPreset, ...] = ()
    custom: tuple[JevCustomQuestion, ...] = ()

    def __post_init__(self) -> None:
        # Validates the whole preflight up front because the runtime's fail-open handler would hide a bad request.
        object.__setattr__(self, "preset", self._validated_presets())
        object.__setattr__(self, "custom", self._validated_custom())
        self._require_question_budget()

    def definitions(self) -> tuple[JevPreflightDefinition, ...]:
        """Return every definition the runtime evaluates in its single Jev request, presets first."""
        registered = tuple(JevPreflightRegistry.resolve(preset) for preset in self.preset)
        if not self.custom:
            return registered
        return (*registered, self._custom_definition())

    def _custom_definition(self) -> JevPreflightDefinition:
        # A zero threshold means custom answers are recorded but can never trigger clarification.
        return JevPreflightDefinition(
            preset=JevPreflightPreset.CUSTOM,
            questions=tuple(question.to_jev_question() for question in self.custom),
            clarifications=MappingProxyType({}),
            threshold=0.0,
        )

    def _validated_presets(self) -> tuple[JevPreflightPreset, ...]:
        # Accepts members or their string values; resolve() rejects CUSTOM and anything unregistered.
        if isinstance(self.preset, (str, bytes)):
            raise ConfigurationError("JevPreflight.preset must be a tuple of presets, not a single string.")
        try:
            presets = tuple(JevPreflightPreset(preset) for preset in self.preset)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("JevPreflight.preset contains an unknown preset.") from exc
        if len(set(presets)) != len(presets):
            raise ConfigurationError("JevPreflight.preset cannot repeat a preset.")
        for preset in presets:
            JevPreflightRegistry.resolve(preset)
        return presets

    def _validated_custom(self) -> tuple[JevCustomQuestion, ...]:
        # Requires JevCustomQuestion values with unique names, since answers come back keyed by name.
        try:
            custom = tuple(self.custom)
        except TypeError as exc:
            raise ConfigurationError("JevPreflight.custom must be a tuple of JevCustomQuestion values.") from exc
        if not all(isinstance(question, JevCustomQuestion) for question in custom):
            raise ConfigurationError("JevPreflight.custom must contain only JevCustomQuestion values.")
        names = [question.name for question in custom]
        if len(set(names)) != len(names):
            raise ConfigurationError("JevPreflight.custom cannot repeat a question name.")
        return custom

    def _require_question_budget(self) -> None:
        # Presets and custom questions share one request, so their combined count must fit its limit.
        total = sum(len(definition.questions) for definition in self.definitions())
        if total > JEV_MAX_QUESTIONS:
            raise ConfigurationError(
                f"JevPreflight asks {total} Jev questions; one request allows at most {JEV_MAX_QUESTIONS}."
            )


__all__ = [
    "CLARITY_QUESTIONS",
    "JevCustomQuestion",
    "JevPreflight",
    "JevPreflightPreset",
    "JevPreflightRegistry",
]
