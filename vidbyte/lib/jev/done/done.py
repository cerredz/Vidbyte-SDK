"""FILE: vidbyte/lib/jev/done/done.py

PURPOSE: Defines JevDoneRegistry, the registry over every done check's fixed question or question pair and threshold, plus validation of the done checks a user enables.
ROLE IN CODEBASE: JevContinualSettings calls JevDoneRegistry.validate at construction, and JevRunState (vidbyte/agents/jev/done/run_state.py) reads each enabled check's question and threshold from here when it asks Jev whether the main agent may finish.
ARCHITECTURE NOTE: Questions are dataclasses in this folder, the check vocabulary is JevDoneCheck in vidbyte/lib/enums/jev.py, and the records live in vidbyte/lib/dataclasses/jev.py; this lib module never imports the agents layer and never calls Jev.
COMMON MODIFICATION PATTERNS: Register a new done check by adding its one or more fixed questions to _questions and its threshold constant to _thresholds; checks that audit a generated list against source inputs also register a per-source question in _inventory_questions. Keep answer scoring in DecisionModelHelper and the actions taken on answers in JevRunState, not here. REQUIRED_ACTIONS contributes one question for each explicitly requested action; DISCOVERED_ITEM_COVERAGE asks one source-inventory question and one item-processing question.
KNOWN EDGE CASES: A bare string is rejected rather than iterated character by character, and enabling the same check twice is an error because it would ask Jev every question twice.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-output-count-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-completion-evidence.md, docs/design/jev-phase-progress.md, docs/design/jev-input-set-coverage.md, docs/design/jev-report-action-alignment.md, docs/design/jev-assumption-reconciliation-done-criteria.md, docs/design/jev-input-exhaustion-done-criteria.md, docs/design/jev-negative-coverage.md, docs/design/jev-mid-run-problem-repair-gate.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md, docs/design/jev-guaranteed-next-actions.md, docs/design/jev-required-actions-done-criteria.md, docs/design/jev-cumulative-obligations-done-check.md, docs/design/jev-discovered-item-coverage.md, docs/design/jev-expert-depth-done-criteria.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.lib.constants.jev import (
    JEV_ASSUMPTIONS_RECONCILED_THRESHOLD,
    JEV_CLAIMS_THRESHOLD,
    JEV_COMPLETION_EVIDENCE_THRESHOLD,
    JEV_CUMULATIVE_OBLIGATIONS_THRESHOLD,
    JEV_DISCOVERED_ITEM_COVERAGE_THRESHOLD,
    JEV_EXPERT_DEPTH_THRESHOLD,
    JEV_FAITHFUL_SCOPE_THRESHOLD,
    JEV_GUARANTEED_NEXT_ACTIONS_THRESHOLD,
    JEV_INPUT_EXHAUSTION_THRESHOLD,
    JEV_INPUT_SET_COVERAGE_THRESHOLD,
    JEV_MOTIVATING_CASE_THRESHOLD,
    JEV_MULTI_PART_THRESHOLD,
    JEV_NEGATIVE_COVERAGE_THRESHOLD,
    JEV_OUTPUT_COUNT_THRESHOLD,
    JEV_OUTPUT_EXTENT_THRESHOLD,
    JEV_PHASE_PROGRESS_THRESHOLD,
    JEV_PROBLEMS_RESOLVED_THRESHOLD,
    JEV_REPORT_ACTION_ALIGNMENT_THRESHOLD,
    JEV_REQUIRED_ACTIONS_THRESHOLD,
    JEV_SCOPE_COVERAGE_THRESHOLD,
    JEV_SELF_REVIEW_THRESHOLD,
    JEV_TARGET_OUTCOME_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import JevDoneQuestion
from vidbyte.lib.enums.jev import (
    JevDoneCheck,
    JevDoneQuestionKey,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.done.assumptions_reconciled import AssumptionsReconciledQuestion
from vidbyte.lib.jev.done.claims import ClaimsSupportedQuestion
from vidbyte.lib.jev.done.completion_evidence import CompletionEvidenceSupportedQuestion
from vidbyte.lib.jev.done.cumulative_obligations import (
    CumulativeObligationFulfilledQuestion,
    CumulativeUserTurnReconciledQuestion,
)
from vidbyte.lib.jev.done.discovered_item_coverage import (
    DiscoveredItemInventoryCompleteQuestion,
    DiscoveredItemProcessedQuestion,
)
from vidbyte.lib.jev.done.expert_depth import ExpertDepthHandledQuestion
from vidbyte.lib.jev.done.faithful_scope import FaithfulScopeQuestion
from vidbyte.lib.jev.done.guaranteed_next_actions import (
    GuaranteedActionNecessaryQuestion,
    GuaranteedActionUnfinishedQuestion,
)
from vidbyte.lib.jev.done.input_exhaustion import InputExhaustionTraversedQuestion
from vidbyte.lib.jev.done.input_set_coverage import InputSetCoverageQuestion
from vidbyte.lib.jev.done.motivating_case import MotivatingCaseExercisedQuestion
from vidbyte.lib.jev.done.multi_part import MultiPartDeliveredQuestion
from vidbyte.lib.jev.done.negative_coverage import NegativeCoverageSupportedQuestion
from vidbyte.lib.jev.done.output_count import OutputCountSatisfiedQuestion
from vidbyte.lib.jev.done.output_extent import OutputExtentSatisfiedQuestion
from vidbyte.lib.jev.done.phase_progress import PhaseProgressReachedQuestion
from vidbyte.lib.jev.done.problems_resolved import ProblemsResolvedQuestion
from vidbyte.lib.jev.done.report_action_alignment import ReportActionAlignmentQuestion
from vidbyte.lib.jev.done.required_actions import RequiredActionCompletedQuestion
from vidbyte.lib.jev.done.scope_coverage import ScopeCoverageAppliedQuestion
from vidbyte.lib.jev.done.self_review import (
    SelfReviewInScopeQuestion,
    SelfReviewResolvedQuestion,
)
from vidbyte.lib.jev.done.target_outcome import TargetOutcomeDemonstratedQuestion


class JevDoneRegistry:
    """Registry over every done check's fixed questions and the threshold its scorer applies to their answers."""

    _questions: Mapping[JevDoneCheck, tuple[JevDoneQuestion, ...]] = MappingProxyType({
        JevDoneCheck.MULTI_PART: (MultiPartDeliveredQuestion(),),
        JevDoneCheck.OUTPUT_COUNT: (OutputCountSatisfiedQuestion(),),
        JevDoneCheck.CLAIMS: (ClaimsSupportedQuestion(),),
        JevDoneCheck.REPORT_ACTION_ALIGNMENT: (ReportActionAlignmentQuestion(),),
        JevDoneCheck.ASSUMPTIONS_RECONCILED: (AssumptionsReconciledQuestion(),),
        JevDoneCheck.TARGET_OUTCOME: (TargetOutcomeDemonstratedQuestion(),),
        JevDoneCheck.MOTIVATING_CASE: (MotivatingCaseExercisedQuestion(),),
        JevDoneCheck.SCOPE_COVERAGE: (ScopeCoverageAppliedQuestion(),),
        JevDoneCheck.COMPLETION_EVIDENCE: (CompletionEvidenceSupportedQuestion(),),
        JevDoneCheck.INPUT_SET_COVERAGE: (InputSetCoverageQuestion(),),
        JevDoneCheck.INPUT_EXHAUSTION: (InputExhaustionTraversedQuestion(),),
        JevDoneCheck.NEGATIVE_COVERAGE: (NegativeCoverageSupportedQuestion(),),
        JevDoneCheck.GUARANTEED_NEXT_ACTIONS: (GuaranteedActionNecessaryQuestion(), GuaranteedActionUnfinishedQuestion()),
        JevDoneCheck.PROBLEMS_RESOLVED: (ProblemsResolvedQuestion(),),
        JevDoneCheck.PHASE_PROGRESS: (PhaseProgressReachedQuestion(),),
        JevDoneCheck.OUTPUT_EXTENT: (OutputExtentSatisfiedQuestion(),),
        JevDoneCheck.REQUIRED_ACTIONS: (RequiredActionCompletedQuestion(),),
        JevDoneCheck.CUMULATIVE_OBLIGATIONS: (CumulativeObligationFulfilledQuestion(),),
        JevDoneCheck.DISCOVERED_ITEM_COVERAGE: (DiscoveredItemProcessedQuestion(),),
        JevDoneCheck.FAITHFUL_SCOPE: (FaithfulScopeQuestion(),),
        JevDoneCheck.EXPERT_DEPTH: (ExpertDepthHandledQuestion(),),
        JevDoneCheck.SELF_REVIEW: (SelfReviewResolvedQuestion(), SelfReviewInScopeQuestion()),
    })
    _inventory_questions: Mapping[JevDoneCheck, JevDoneQuestion] = MappingProxyType({
        JevDoneCheck.CUMULATIVE_OBLIGATIONS: CumulativeUserTurnReconciledQuestion(),
        JevDoneCheck.DISCOVERED_ITEM_COVERAGE: DiscoveredItemInventoryCompleteQuestion(),
    })
    _thresholds: Mapping[JevDoneCheck, float] = MappingProxyType({
        JevDoneCheck.MULTI_PART: JEV_MULTI_PART_THRESHOLD,
        JevDoneCheck.OUTPUT_COUNT: JEV_OUTPUT_COUNT_THRESHOLD,
        JevDoneCheck.CLAIMS: JEV_CLAIMS_THRESHOLD,
        JevDoneCheck.REPORT_ACTION_ALIGNMENT: JEV_REPORT_ACTION_ALIGNMENT_THRESHOLD,
        JevDoneCheck.ASSUMPTIONS_RECONCILED: JEV_ASSUMPTIONS_RECONCILED_THRESHOLD,
        JevDoneCheck.TARGET_OUTCOME: JEV_TARGET_OUTCOME_THRESHOLD,
        JevDoneCheck.MOTIVATING_CASE: JEV_MOTIVATING_CASE_THRESHOLD,
        JevDoneCheck.SCOPE_COVERAGE: JEV_SCOPE_COVERAGE_THRESHOLD,
        JevDoneCheck.COMPLETION_EVIDENCE: JEV_COMPLETION_EVIDENCE_THRESHOLD,
        JevDoneCheck.INPUT_SET_COVERAGE: JEV_INPUT_SET_COVERAGE_THRESHOLD,
        JevDoneCheck.INPUT_EXHAUSTION: JEV_INPUT_EXHAUSTION_THRESHOLD,
        JevDoneCheck.NEGATIVE_COVERAGE: JEV_NEGATIVE_COVERAGE_THRESHOLD,
        JevDoneCheck.GUARANTEED_NEXT_ACTIONS: JEV_GUARANTEED_NEXT_ACTIONS_THRESHOLD,
        JevDoneCheck.PROBLEMS_RESOLVED: JEV_PROBLEMS_RESOLVED_THRESHOLD,
        JevDoneCheck.PHASE_PROGRESS: JEV_PHASE_PROGRESS_THRESHOLD,
        JevDoneCheck.OUTPUT_EXTENT: JEV_OUTPUT_EXTENT_THRESHOLD,
        JevDoneCheck.REQUIRED_ACTIONS: JEV_REQUIRED_ACTIONS_THRESHOLD,
        JevDoneCheck.CUMULATIVE_OBLIGATIONS: JEV_CUMULATIVE_OBLIGATIONS_THRESHOLD,
        JevDoneCheck.DISCOVERED_ITEM_COVERAGE: JEV_DISCOVERED_ITEM_COVERAGE_THRESHOLD,
        JevDoneCheck.FAITHFUL_SCOPE: JEV_FAITHFUL_SCOPE_THRESHOLD,
        JevDoneCheck.EXPERT_DEPTH: JEV_EXPERT_DEPTH_THRESHOLD,
        JevDoneCheck.SELF_REVIEW: JEV_SELF_REVIEW_THRESHOLD,
    })

    @classmethod
    def question(cls, check: JevDoneCheck) -> JevDoneQuestion:
        """Return the first fixed question a done check asks about each item it checks."""
        return cls.questions(check)[0]

    @classmethod
    def questions(cls, check: JevDoneCheck) -> tuple[JevDoneQuestion, ...]:
        """Return every fixed question a done check asks about each item."""
        found = cls._questions.get(check)
        if not found:
            raise ConfigurationError(f"Jev done check {check!r} has no registered question.", details={"check": str(check), "registered": [item.value for item in cls._questions]})
        return found

    @classmethod
    def question_for_key(cls, key: JevDoneQuestionKey) -> JevDoneQuestion:
        """Return the unique registered question with this answer key."""
        matches = tuple(
            question
            for question_group in cls._questions.values()
            for question in question_group
            if question.key == key
        ) + tuple(question for question in cls._inventory_questions.values() if question.key == key)
        if len(matches) != 1:
            registered = [question.key.value for group in cls._questions.values() for question in group]
            registered.extend(question.key.value for question in cls._inventory_questions.values())
            raise ConfigurationError(
                f"Jev done question key {key.value!r} has {len(matches)} registered questions.",
                details={"question_key": key.value, "matches": len(matches), "registered": registered},
            )
        return matches[0]

    @classmethod
    def threshold(cls, check: JevDoneCheck) -> float:
        """Return the threshold the check's scorer applies to its answers before the run may finish."""
        found = cls._thresholds.get(check)
        if found is None:
            raise ConfigurationError(
                f"Jev done check {check!r} has no registered threshold.",
                details={
                    "check": str(check),
                    "registered": [item.value for item in cls._thresholds],
                },
            )
        return found

    @classmethod
    def inventory_question(cls, check: JevDoneCheck) -> JevDoneQuestion:
        """Return the fixed per-source inventory question for a check that audits generated candidate completeness."""
        # @intent source-audit-questions-are-registered-beside-check-questions
        # A preset may need fixed questions over generated candidates and independent completeness questions
        # over their source messages; both are selected from one registry rather than assembled at runtime.
        found = cls._inventory_questions.get(check)
        if found is None:
            raise ConfigurationError(f"Jev done check {check!r} has no registered inventory question.", details={"check": str(check), "registered": [item.value for item in cls._inventory_questions]})
        return found

    @classmethod
    def resolve(cls, value: object) -> JevDoneCheck:
        """Convert one user-supplied check (enum member or its string value) to a JevDoneCheck."""
        try:
            return value if isinstance(value, JevDoneCheck) else JevDoneCheck(value)
        except ValueError as exc:
            raise ConfigurationError(
                f"Unsupported Jev done check: {value!r}.",
                details={
                    "received": repr(value),
                    "available": [item.value for item in JevDoneCheck],
                },
            ) from exc

    @classmethod
    def validate(cls, values: Iterable[object]) -> tuple[JevDoneCheck, ...]:
        """Convert the user's enabled done checks to a tuple of unique checks, each with a registered question and threshold."""
        # @intent done-checks-fail-before-any-jev-call
        # Settings construction calls this, so a typo, a bare string, or a repeated check fails when the
        # agent is built instead of silently asking Jev the wrong (or duplicated) questions at every finish.
        if isinstance(values, (str, bytes)):
            raise ConfigurationError(
                "JevContinualSettings.checks must be an iterable of Jev done checks, not a string.",
                details={"received": repr(values)},
            )
        try:
            checks = tuple(cls.resolve(value) for value in values)
        except TypeError as exc:
            raise ConfigurationError(
                "JevContinualSettings.checks must be an iterable of Jev done checks.",
                details={"received": type(values).__name__},
            ) from exc
        if len(set(checks)) != len(checks):
            raise ConfigurationError(
                "JevContinualSettings.checks cannot enable the same check twice.",
                details={"received": [check.value for check in checks]},
            )
        for check in checks:
            cls.questions(check)
            cls.threshold(check)
            if check in cls._inventory_questions:
                cls.inventory_question(check)
        return checks


__all__ = ["JevDoneRegistry"]
