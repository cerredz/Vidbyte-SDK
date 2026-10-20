"""FILE: vidbyte/lib/dataclasses/native_ensemble.py

PURPOSE: Defines the validated records of run_ensemble: EnsembleRoster, the four caller-chosen roles; EnsembleRole, EnsemblePlan, EnsembleRound and EnsembleSelection, the structured answers of the planner and the selector; and EnsembleResult, what the run returns as far as it got.
ROLE IN CODEBASE: EnsembleRoster is built by the caller and read by ThreadEnsembles in vidbyte/harnesses/native/compose/ensemble.py; AnswerDecoders in answers.py builds the answer records from decoded JSON, and EnsembleSelector in selection.py and ThreadEnsembles build EnsembleResult. All six are re-exported from vidbyte.harnesses.native.compose.
ARCHITECTURE NOTE: Every check lives in __post_init__, with bounds from vidbyte/lib/constants/native_compose.py, so an oversized or malformed model answer is a refusal (and so a repair turn), never a record. Each field's own type, size and item count goes through RecordFieldValidator and RecordFieldConverter; only the rules that relate a field's items to each other (every role its own name, different kept numbers of at least ENSEMBLE_MIN_PROPOSAL_NUMBER) are written here. The rules that relate records to each other (exactly one role per proposer, numbers that were offered, fork roles, one workspace) are compose policy in AnswerDecoders and StepRoles, not record validation.
FUNCTION INVENTORY: EnsembleResult.failed_stage; the other records have only __post_init__.
COMMON MODIFICATION PATTERNS: A new member of a planner or selector answer is one field here, one validator call, and the matching text in the schema prompt file; the decoders read member names from dataclasses.fields, so they follow without change.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.harnesses; vidbyte/lib is the bottom layer. 2. Do not check offered numbers or the role count here; they depend on the run, which only compose knows. 3. Do not store a failed-stage flag; it is derived from the stored answers.
KNOWN EDGE CASES: A role name is at most ENSEMBLE_ROLE_NAME_MAX_CHARS characters and holds no NUL, because it is spliced into several prompts. EnsemblePlan.roles and EnsembleRound.kept come from decoded JSON lists and are stored as tuples. A round keeps unique positive numbers; whether they were offered is checked by the decoder. A refused role name or proposal number is named by its type only (quote=False): a step's answer can echo a key into either, and the refusal is kept as that answer's problem (INV-4).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_ensemble.py, tests/features/harness_compose/test_harness_compose_answers.py
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from vidbyte.lib.constants.native_compose import (
    COMPOSE_ANSWER_TEXT_MAX_CHARS,
    ENSEMBLE_MAX_PROPOSERS,
    ENSEMBLE_MIN_PROPOSAL_NUMBER,
    ENSEMBLE_MIN_PROPOSERS,
    ENSEMBLE_ROLE_NAME_MAX_CHARS,
)
from vidbyte.lib.constants.native_threads import NATIVE_PROMPT_PATTERN
from vidbyte.lib.dataclasses.native_compose import (
    JsonAnswer,
    StepOutcome,
    ThreadStep,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_compose import EnsembleStage
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class EnsembleRoster:
    """The four roles of run_ensemble, each a caller-chosen step: the planner, one to ten proposers, the selector and the implementer."""

    planner: ThreadStep
    proposers: Sequence[ThreadStep]
    selector: ThreadStep
    implementer: ThreadStep

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.planner, "EnsembleRoster.planner", ThreadStep)
        proposers = RecordFieldConverter.to_tuple(self.proposers, "EnsembleRoster.proposers", item_type=ThreadStep, min_items=ENSEMBLE_MIN_PROPOSERS, max_items=ENSEMBLE_MAX_PROPOSERS)
        object.__setattr__(self, "proposers", proposers)
        RecordFieldConverter.require_instance(self.selector, "EnsembleRoster.selector", ThreadStep)
        RecordFieldConverter.require_instance(self.implementer, "EnsembleRoster.implementer", ThreadStep)


@dataclass(frozen=True, slots=True)
class EnsembleRole:
    """One proposer role from the plan: its name and the six descriptions role_system splices."""

    name: str
    identity: str
    personality: str
    expertise: str
    knowledge: str
    skills: str
    goal: str

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.name, "EnsembleRole.name", max_chars=ENSEMBLE_ROLE_NAME_MAX_CHARS, pattern=NATIVE_PROMPT_PATTERN, quote=False)
        RecordFieldValidator.require_text(self.identity, "EnsembleRole.identity", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        RecordFieldValidator.require_text(self.personality, "EnsembleRole.personality", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        RecordFieldValidator.require_text(self.expertise, "EnsembleRole.expertise", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        RecordFieldValidator.require_text(self.knowledge, "EnsembleRole.knowledge", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        RecordFieldValidator.require_text(self.skills, "EnsembleRole.skills", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        RecordFieldValidator.require_text(self.goal, "EnsembleRole.goal", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)


@dataclass(frozen=True, slots=True)
class EnsemblePlan:
    """The planner's answer: its reading of the task, its roster strategy, a coverage summary, and one role per proposer."""

    task_analysis: str
    roster_strategy: str
    coverage_summary: str
    roles: tuple[EnsembleRole, ...]

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.task_analysis, "EnsemblePlan.task_analysis", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        RecordFieldValidator.require_text(self.roster_strategy, "EnsemblePlan.roster_strategy", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        RecordFieldValidator.require_text(self.coverage_summary, "EnsemblePlan.coverage_summary", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        roles = RecordFieldConverter.to_tuple(self.roles, "EnsemblePlan.roles", item_type=EnsembleRole, min_items=ENSEMBLE_MIN_PROPOSERS, max_items=ENSEMBLE_MAX_PROPOSERS)
        if len({role.name for role in roles}) != len(roles):
            raise ConfigurationError("EnsemblePlan.roles must give every role its own name.", details={"field": "EnsemblePlan.roles"})
        object.__setattr__(self, "roles", roles)


@dataclass(frozen=True, slots=True)
class EnsembleRound:
    """One narrowing round of the selector: the proposal numbers it kept and a summary of why."""

    kept: tuple[int, ...]
    summary: str

    def __post_init__(self) -> None:
        kept = RecordFieldConverter.to_tuple(self.kept, "EnsembleRound.kept", item_type=int, min_items=ENSEMBLE_MIN_PROPOSERS, max_items=ENSEMBLE_MAX_PROPOSERS)
        if len(set(kept)) != len(kept) or min(kept) < ENSEMBLE_MIN_PROPOSAL_NUMBER:
            raise ConfigurationError(f"EnsembleRound.kept must hold different proposal numbers of at least {ENSEMBLE_MIN_PROPOSAL_NUMBER}.", details={"field": "EnsembleRound.kept"})
        object.__setattr__(self, "kept", kept)
        RecordFieldValidator.require_text(self.summary, "EnsembleRound.summary", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)


@dataclass(frozen=True, slots=True)
class EnsembleSelection:
    """The selector's final choice: the proposal number, the approach to build, why, and guidance for the implementer."""

    proposal: int
    approach: str
    rationale: str
    guidance: str

    def __post_init__(self) -> None:
        RecordFieldValidator.require_int(self.proposal, "EnsembleSelection.proposal", minimum=ENSEMBLE_MIN_PROPOSAL_NUMBER, maximum=ENSEMBLE_MAX_PROPOSERS, quote=False)
        RecordFieldValidator.require_text(self.approach, "EnsembleSelection.approach", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        RecordFieldValidator.require_text(self.rationale, "EnsembleSelection.rationale", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)
        RecordFieldValidator.require_text(self.guidance, "EnsembleSelection.guidance", max_chars=COMPOSE_ANSWER_TEXT_MAX_CHARS)


@dataclass(frozen=True, slots=True)
class EnsembleResult:
    """What run_ensemble returns: the plan, each proposal, the narrowing rounds, the selection and the implementation, as far as the run got."""

    plan: JsonAnswer[EnsemblePlan]
    proposals: tuple[StepOutcome, ...] = ()
    rounds: tuple[JsonAnswer[EnsembleRound], ...] = ()
    selection: JsonAnswer[EnsembleSelection] | None = None
    implementation: StepOutcome | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.plan, "EnsembleResult.plan", JsonAnswer)
        object.__setattr__(self, "proposals", RecordFieldConverter.to_tuple(self.proposals, "EnsembleResult.proposals", item_type=StepOutcome, max_items=ENSEMBLE_MAX_PROPOSERS))
        object.__setattr__(self, "rounds", RecordFieldConverter.to_tuple(self.rounds, "EnsembleResult.rounds", item_type=JsonAnswer, max_items=ENSEMBLE_MAX_PROPOSERS))
        RecordFieldConverter.require_instance(self.selection, "EnsembleResult.selection", JsonAnswer, optional=True)
        RecordFieldConverter.require_instance(self.implementation, "EnsembleResult.implementation", StepOutcome, optional=True)

    @property
    def failed_stage(self) -> EnsembleStage | None:
        """The stage at which the run stopped, or None when the implementer succeeded."""
        if not self.plan.ok:
            return EnsembleStage.PLAN
        if not any(proposal.ok for proposal in self.proposals):
            return EnsembleStage.PROPOSE
        if not all(answer.ok for answer in self.rounds) or self.selection is None or not self.selection.ok:
            return EnsembleStage.SELECT
        if self.implementation is None or not self.implementation.ok:
            return EnsembleStage.IMPLEMENT
        return None


__all__ = ["EnsemblePlan", "EnsembleResult", "EnsembleRole", "EnsembleRoster", "EnsembleRound", "EnsembleSelection"]
