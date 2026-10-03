"""FILE: vidbyte/lib/jev/done/done.py

PURPOSE: Defines JevDoneRegistry, the registry over every done check's fixed question or question pair and threshold, plus validation of the done checks a user enables.
ROLE IN CODEBASE: JevContinualSettings calls JevDoneRegistry.validate at construction, and JevRunState (vidbyte/agents/jev/done/run_state.py) reads each enabled check's question and threshold from here when it asks Jev whether the main agent may finish.
ARCHITECTURE NOTE: Questions are dataclasses in this folder, the check vocabulary is JevDoneCheck in vidbyte/lib/enums/jev.py, and the records live in vidbyte/lib/dataclasses/jev.py; this lib module never imports the agents layer and never calls Jev.
COMMON MODIFICATION PATTERNS: Register a new done check by adding its one or more fixed questions to _questions and its threshold constant to _thresholds; checks that audit a generated list against source inputs also register a per-source question in _inventory_questions. Keep answer scoring in DecisionModelHelper and the actions taken on answers in JevRunState, not here. REQUIRED_ACTIONS contributes one question for each explicitly requested action; DISCOVERED_ITEM_COVERAGE asks one source-inventory question and one item-processing question.
KNOWN EDGE CASES: A bare string is rejected rather than iterated character by character, and enabling the same check twice is an error because it would ask Jev every question twice.
RELATED DOCS: docs/design/jev-can-simplify-done-criteria.md, docs/design/jev-multipart-done-criteria.md, docs/design/jev-output-count-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-completion-evidence.md, docs/design/jev-phase-progress.md, docs/design/jev-input-set-coverage.md, docs/design/jev-report-action-alignment.md, docs/design/jev-assumption-reconciliation-done-criteria.md, docs/design/jev-input-exhaustion-done-criteria.md, docs/design/jev-negative-coverage.md, docs/design/jev-mid-run-problem-repair-gate.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md, docs/design/jev-guaranteed-next-actions.md, docs/design/jev-required-actions-done-criteria.md, docs/design/jev-cumulative-obligations-done-check.md, docs/design/jev-discovered-item-coverage.md, docs/design/jev-expert-depth-done-criteria.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.lib.constants.jev import (
    JEV_ASSUMPTIONS_RECONCILED_THRESHOLD,
    JEV_CAN_SIMPLIFY_THRESHOLD,
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
    JEV_REQUIRED_SEQUENCE_THRESHOLD,
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
from vidbyte.lib.jev.done.can_simplify import CanSimplifyQuestion
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
from vidbyte.lib.jev.done.required_sequence import (
    RequiredSequencePreviousOutputQuestion,
    RequiredSequenceWorkShownQuestion,
)
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
        JevDoneCheck.CAN_SIMPLIFY: (CanSimplifyQuestion(),),
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
        JevDoneCheck.REQUIRED_SEQUENCE: (
            RequiredSequenceWorkShownQuestion(),
            RequiredSequencePreviousOutputQuestion(),
        ),
    })
    _inventory_questions: Mapping[JevDoneCheck, JevDoneQuestion] = MappingProxyType({
        JevDoneCheck.CUMULATIVE_OBLIGATIONS: CumulativeUserTurnReconciledQuestion(),
        JevDoneCheck.DISCOVERED_ITEM_COVERAGE: DiscoveredItemInventoryCompleteQuestion(),
    })
    _thresholds: Mapping[JevDoneCheck, float] = MappingProxyType({
        JevDoneCheck.MULTI_PART: JEV_MULTI_PART_THRESHOLD,
        JevDoneCheck.CAN_SIMPLIFY: JEV_CAN_SIMPLIFY_THRESHOLD,
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
        JevDoneCheck.REQUIRED_SEQUENCE: JEV_REQUIRED_SEQUENCE_THRESHOLD,
    })
    _descriptions: Mapping[JevDoneCheck, str] = MappingProxyType({
        JevDoneCheck.MULTI_PART: "This gate checks each separate output the request asks the agent to produce, including answer content and work left in files or command results. It asks whether the available run evidence shows every part of each named deliverable in its latest state.\n\nUse each failed question to locate its deliverable in the run state and handoff, then finish the missing parts and make the result visible. Failures commonly mean an output was omitted, only partly produced, replaced by a placeholder, or merely claimed in the final answer.",
        JevDoneCheck.CAN_SIMPLIFY: "This gate checks whether the implementation can be made simpler while preserving the user's stated requirements. It considers the proposed implementation and the requirements that a simplification must keep.\n\nUse a failed question to identify the candidate simplification and compare it with the original scope and preservation constraints before changing anything. Failures commonly mean a supported simpler design remains unapplied, or that a proposed reduction would remove required behavior.",
        JevDoneCheck.OUTPUT_COUNT: "This gate checks explicit quantities of requested outputs, using the requested unit, scope, distinctness rule, and completion criterion for each quantity. It verifies the visible candidates and evidence rather than trusting a reported total.\n\nUse each failed question to find which quantity or group is short, then produce and show enough distinct qualifying outputs. Failures commonly come from a missing item, duplicate items counted twice, candidates outside the requested scope, or a count with no visible supporting outputs.",
        JevDoneCheck.CLAIMS: "This gate checks whether each assertion in the agent's claims is supported by evidence from the run. It judges each assertion separately against the recorded tool activity and outputs.\n\nUse a failed question to locate the specific unsupported assertion, then either perform and verify the work or correct the account of what happened. Failures commonly occur when the final answer overstates completion, a tool call was attempted but failed, or evidence for one claim is used to support another.",
        JevDoneCheck.INPUT_EXHAUSTION: "This gate checks whether traversal of a requested or discovered input source reached its stated stopping condition. It considers the recorded positions, totals, continuation markers, and retrieval failures for each traversal.\n\nUse each failed question to resume from the last known position and continue until the recorded exhaustion condition is supported. Failures commonly mean a cursor remains open, retrieval failed, or the run stopped at a reported count without evidence that the source was fully traversed.",
        JevDoneCheck.NEGATIVE_COVERAGE: "This gate checks whether the agent accounted for explicit exclusions, negative conditions, and cases the request says must not be included or changed. It looks for evidence that the negative boundary was applied to the relevant work.\n\nUse a failed question to identify the missing exclusion or boundary, then apply it and show the corrected result. Failures commonly occur when the positive request is completed while excluded items are still included, or when the agent states a constraint without evidence it affected the output.",
        JevDoneCheck.GUARANTEED_NEXT_ACTIONS: "This gate checks candidate follow-up actions against both the user's request and a trigger observed during the run. An action matters only when the request and observed condition make it necessary and the evidence shows it remains unfinished.\n\nUse a failed question to inspect the named outcome, trigger, and action; complete the action only if it is still required and unfinished. Failures commonly mean a required next step was left open, or that an action was treated as necessary without a request-based reason.",
        JevDoneCheck.TARGET_OUTCOME: "This gate checks whether the requested outcome was demonstrated by direct evidence, rather than inferred from a proxy milestone or an activity that might lead to it. Each question concerns one target outcome and its completion criterion.\n\nUse a failed question to compare the observed result with the actual target and provide direct evidence for the criterion. Failures commonly mean the agent reports progress or an intermediate signal as though it proved the final outcome.",
        JevDoneCheck.MOTIVATING_CASE: "This gate checks whether the agent exercised the specific motivating scenario from the request, including the condition that distinguishes it from a nearby case that does not count. It evaluates the recorded scenario and its expected behavior.\n\nUse each failed question to reproduce the named condition in the permitted mode and show the expected behavior. Failures commonly mean only the ordinary path was tried, the boundary condition was missed, or a near-miss scenario was tested instead.",
        JevDoneCheck.SCOPE_COVERAGE: "This gate checks whether the requested scope was enumerated and the requested change was applied to every required member in that scope. It keeps source inventory completeness separate from evidence for each listed member.\n\nUse each failed question to identify either the missing inventory or the specific member without applied work, then enumerate or update it and show the result. Failures commonly mean some files, components, or members were never discovered or were listed but not changed.",
        JevDoneCheck.COMPLETION_EVIDENCE: "This gate checks whether the run evidence supports the agent's overall completion account against the outcomes in the original request. It compares requested outcomes with work shown and anything reported unfinished or blocked.\n\nUse a failed question to complete the unsupported requested outcome or accurately report its blocker and remaining state. Failures commonly mean the final response claims the whole task is done while evidence shows only partial work, an unresolved blocker, or no result for an outcome.",
        JevDoneCheck.INPUT_SET_COVERAGE: "This gate checks whether every explicit input the user asked the agent to engage was actually processed at the requested depth and scope. It distinguishes substantive use of content from merely locating or naming an input.\n\nUse each failed question to find the named target and perform the requested engagement, then leave evidence of that work. Failures commonly mean an input was skipped, only its title or metadata was inspected, or a small excerpt was used where the request called for broader review.",
        JevDoneCheck.OUTPUT_EXTENT: "This gate checks whether a requested output meets a measurable size or extent target, using the requested unit and comparator. The measurement is taken from the final visible output rather than an estimate or promise.\n\nUse each failed question to identify the output and extent still required, then produce enough content and make it visible. Failures commonly mean the answer is shorter than requested, the wrong unit was measured, or an estimate was reported without a complete output.",
        JevDoneCheck.REPORT_ACTION_ALIGNMENT: "This gate checks whether the final account accurately matches earlier plans or commitments with the work actually performed and whether any mismatch still affects the request. A plan alone is not a requirement to perform unnecessary work.\n\nUse a failed question to reconcile the specific plan, execution, and account: complete still-required work or correct the report. Failures commonly mean promised work is absent, reported execution is unsupported, or the final summary does not reflect a material result.",
        JevDoneCheck.ASSUMPTIONS_RECONCILED: "This gate checks whether assumptions that changed during the run were revisited and their dependent work was reconciled with later observations. It accounts for recovery or a scope change that may make earlier dependent work irrelevant.\n\nUse a failed question to inspect the changed premise and affected work, then verify, revise, or explicitly retire that work based on current evidence. Failures commonly mean a disproven assumption was left in place or changes to it never propagated to dependent decisions.",
        JevDoneCheck.PROBLEMS_RESOLVED: "This gate checks whether problems discovered during the run were repaired and the affected behavior was successfully revalidated. It also checks that original requested work resumes after a repair.\n\nUse each failed question to identify the problem and its verification gap, repair it, run the relevant validation, and return to remaining request items. Failures commonly mean a fix was only claimed, validation failed or was skipped, or the repair displaced unfinished requested work.",
        JevDoneCheck.PHASE_PROGRESS: "This gate checks whether the run entered and made substantive progress on every required phase or stage named by the request. It does not treat a plan to begin later as evidence of progress.\n\nUse each failed question to identify the required stage that has no observed work and perform the requested activity for it. Failures commonly mean the agent stopped after an initial phase, discussed later work without doing it, or skipped a stage in a multi-stage request.",
        JevDoneCheck.REQUIRED_ACTIONS: "This gate checks whether each explicit action the user asked the agent to take is completed, with order constraints applied when the request requires them. Each action has its own completion evidence.\n\nUse each failed question to locate the requested action and its missing result, then complete and show it while respecting its dependencies. Failures commonly mean an action was omitted, only promised, or attempted before a required predecessor was complete.",
        JevDoneCheck.CUMULATIVE_OBLIGATIONS: "This gate checks that active requirements across the supplied user turns remain accounted for, including later changes, cancellations, and incompatible replacements. It reconciles the current run against each turn rather than considering only the latest message.\n\nUse each failed question to recover the still-active instruction from its source turn and complete it unless the conversation supports its cancellation or replacement. Failures commonly mean an earlier requirement was forgotten or treated as canceled without evidence.",
        JevDoneCheck.DISCOVERED_ITEM_COVERAGE: "This gate checks that every in-scope item discovered from a source was inventoried and processed as requested. It separately checks whether the source output was completely reviewed for candidates.\n\nUse each failed question to complete the inventory or process the named item, then show the work. Failures commonly mean an item was omitted from the candidate list, or was identified but never actually handled.",
        JevDoneCheck.FAITHFUL_SCOPE: "This gate checks that the agent's work stays faithful to the user's requested scope, including required content, requested format, and explicit constraints. It focuses continuation effort on recognized scope gaps.\n\nUse each failed question to compare the output with the corresponding request requirement and complete the missing in-scope work. Failures commonly mean the result is narrower than requested, a requested format or constraint was ignored, or extra work displaced required work.",
        JevDoneCheck.EXPERT_DEPTH: "This gate checks whether the agent addressed the named hard parts, risks, and non-obvious requirements at the depth the task needs. Every named weak point is considered separately so strong coverage elsewhere cannot hide a gap.\n\nUse each failed question to return to the specific unresolved hard part and add the analysis, implementation, or validation it needs. Failures commonly mean the answer covers the easy path while leaving a risky boundary, core mechanism, or stated concern unhandled.",
        JevDoneCheck.SELF_REVIEW: "This gate checks whether objections raised during independent review are both resolved and relevant to the user's request. An objection is cleared by evidence of a repair or by a supported reason it is outside scope.\n\nUse each failed question to inspect the objection and its scope decision, then fix an in-scope issue or substantiate why it does not apply. Failures commonly mean an objection was acknowledged but not repaired, or dismissed without tying that decision to the request.",
        JevDoneCheck.REQUIRED_SEQUENCE: "This gate checks whether required stages have visible work and whether each stage used the previous stage's output in the order the request specified. It relies on run events to establish actual completion order.\n\nUse each failed question to identify the stage with missing work or missing predecessor evidence, then complete the stages in order and expose each result to the next. Failures commonly mean stages were skipped, performed out of order, or completed without using the required earlier output.",
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
    def question_for_answer_name(cls, name: str) -> tuple[JevDoneQuestion, str]:
        # Resolves the longest registered key prefix and retains the full item suffix.
        """Resolve a Jev answer name to its fixed question and complete checked-item suffix."""
        matches = tuple(
            (question, name.removeprefix(f"{question.key.value}."))
            for question_group in cls._questions.values()
            for question in question_group
            if name.startswith(f"{question.key.value}.")
        ) + tuple(
            (question, name.removeprefix(f"{question.key.value}."))
            for question in cls._inventory_questions.values()
            if name.startswith(f"{question.key.value}.")
        )
        if len(matches) != 1 or not matches[0][1]:
            raise ConfigurationError(
                f"Jev done answer name {name!r} has {len(matches)} registered questions.",
                details={"answer_name": name, "matches": len(matches)},
            )
        return matches[0]

    @classmethod
    def description(cls, check: JevDoneCheck) -> str:
        # Supplies stable gate-specific instructions to the fresh continuation prompt.
        """Return the fresh-agent guidance for one enabled continuation gate."""
        found = cls._descriptions.get(check)
        if found is None:
            raise ConfigurationError(
                f"Jev done check {check!r} has no registered fresh-continuation description.",
                details={"check": str(check), "registered": [item.value for item in cls._descriptions]},
            )
        return found

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
        missing_descriptions = set(JevDoneCheck) - set(cls._descriptions)
        extra_descriptions = set(cls._descriptions) - set(JevDoneCheck)
        malformed_descriptions = tuple(
            check.value
            for check, description in cls._descriptions.items()
            if len(description.split("\n\n")) != 2
        )
        if missing_descriptions or extra_descriptions or malformed_descriptions:
            raise ConfigurationError(
                "Jev done gate descriptions must cover every check with exactly two paragraphs.",
                details={
                    "missing": [check.value for check in missing_descriptions],
                    "extra": [check.value for check in extra_descriptions],
                    "malformed": malformed_descriptions,
                },
            )
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
