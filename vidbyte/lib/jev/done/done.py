"""FILE: vidbyte/lib/jev/done/done.py

PURPOSE: Defines JevDoneRegistry, the registry over every done check's fixed question or question pair and threshold, plus validation of the done checks a user enables.
ROLE IN CODEBASE: JevContinuationGateSettings calls JevDoneRegistry.validate at construction, and JevRunState (vidbyte/agents/jev/done/run_state.py) reads each enabled check's question and threshold from here when it asks Jev whether the main agent may finish.
ARCHITECTURE NOTE: Questions are dataclasses in this folder, the check vocabulary is JevContinuationGate in vidbyte/lib/enums/jev.py, and the records live in vidbyte/lib/dataclasses/jev.py; this lib module never imports the agents layer and never calls Jev.
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
from vidbyte.lib.dataclasses.jev import JevDoneGateDescription, JevDoneQuestion
from vidbyte.lib.enums.jev import (
    JevContinuationGate,
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

    _questions: Mapping[JevContinuationGate, tuple[JevDoneQuestion, ...]] = MappingProxyType({
        JevContinuationGate.MULTI_PART: (MultiPartDeliveredQuestion(),),
        JevContinuationGate.CAN_SIMPLIFY: (CanSimplifyQuestion(),),
        JevContinuationGate.OUTPUT_COUNT: (OutputCountSatisfiedQuestion(),),
        JevContinuationGate.CLAIMS: (ClaimsSupportedQuestion(),),
        JevContinuationGate.REPORT_ACTION_ALIGNMENT: (ReportActionAlignmentQuestion(),),
        JevContinuationGate.ASSUMPTIONS_RECONCILED: (AssumptionsReconciledQuestion(),),
        JevContinuationGate.TARGET_OUTCOME: (TargetOutcomeDemonstratedQuestion(),),
        JevContinuationGate.MOTIVATING_CASE: (MotivatingCaseExercisedQuestion(),),
        JevContinuationGate.SCOPE_COVERAGE: (ScopeCoverageAppliedQuestion(),),
        JevContinuationGate.COMPLETION_EVIDENCE: (CompletionEvidenceSupportedQuestion(),),
        JevContinuationGate.INPUT_SET_COVERAGE: (InputSetCoverageQuestion(),),
        JevContinuationGate.INPUT_EXHAUSTION: (InputExhaustionTraversedQuestion(),),
        JevContinuationGate.NEGATIVE_COVERAGE: (NegativeCoverageSupportedQuestion(),),
        JevContinuationGate.GUARANTEED_NEXT_ACTIONS: (GuaranteedActionNecessaryQuestion(), GuaranteedActionUnfinishedQuestion()),
        JevContinuationGate.PROBLEMS_RESOLVED: (ProblemsResolvedQuestion(),),
        JevContinuationGate.PHASE_PROGRESS: (PhaseProgressReachedQuestion(),),
        JevContinuationGate.OUTPUT_EXTENT: (OutputExtentSatisfiedQuestion(),),
        JevContinuationGate.REQUIRED_ACTIONS: (RequiredActionCompletedQuestion(),),
        JevContinuationGate.CUMULATIVE_OBLIGATIONS: (CumulativeObligationFulfilledQuestion(),),
        JevContinuationGate.DISCOVERED_ITEM_COVERAGE: (DiscoveredItemProcessedQuestion(),),
        JevContinuationGate.FAITHFUL_SCOPE: (FaithfulScopeQuestion(),),
        JevContinuationGate.EXPERT_DEPTH: (ExpertDepthHandledQuestion(),),
        JevContinuationGate.SELF_REVIEW: (SelfReviewResolvedQuestion(), SelfReviewInScopeQuestion()),
        JevContinuationGate.REQUIRED_SEQUENCE: (
            RequiredSequenceWorkShownQuestion(),
            RequiredSequencePreviousOutputQuestion(),
        ),
    })
    _inventory_questions: Mapping[JevContinuationGate, JevDoneQuestion] = MappingProxyType({
        JevContinuationGate.CUMULATIVE_OBLIGATIONS: CumulativeUserTurnReconciledQuestion(),
        JevContinuationGate.DISCOVERED_ITEM_COVERAGE: DiscoveredItemInventoryCompleteQuestion(),
    })
    _thresholds: Mapping[JevContinuationGate, float] = MappingProxyType({
        JevContinuationGate.MULTI_PART: JEV_MULTI_PART_THRESHOLD,
        JevContinuationGate.CAN_SIMPLIFY: JEV_CAN_SIMPLIFY_THRESHOLD,
        JevContinuationGate.OUTPUT_COUNT: JEV_OUTPUT_COUNT_THRESHOLD,
        JevContinuationGate.CLAIMS: JEV_CLAIMS_THRESHOLD,
        JevContinuationGate.REPORT_ACTION_ALIGNMENT: JEV_REPORT_ACTION_ALIGNMENT_THRESHOLD,
        JevContinuationGate.ASSUMPTIONS_RECONCILED: JEV_ASSUMPTIONS_RECONCILED_THRESHOLD,
        JevContinuationGate.TARGET_OUTCOME: JEV_TARGET_OUTCOME_THRESHOLD,
        JevContinuationGate.MOTIVATING_CASE: JEV_MOTIVATING_CASE_THRESHOLD,
        JevContinuationGate.SCOPE_COVERAGE: JEV_SCOPE_COVERAGE_THRESHOLD,
        JevContinuationGate.COMPLETION_EVIDENCE: JEV_COMPLETION_EVIDENCE_THRESHOLD,
        JevContinuationGate.INPUT_SET_COVERAGE: JEV_INPUT_SET_COVERAGE_THRESHOLD,
        JevContinuationGate.INPUT_EXHAUSTION: JEV_INPUT_EXHAUSTION_THRESHOLD,
        JevContinuationGate.NEGATIVE_COVERAGE: JEV_NEGATIVE_COVERAGE_THRESHOLD,
        JevContinuationGate.GUARANTEED_NEXT_ACTIONS: JEV_GUARANTEED_NEXT_ACTIONS_THRESHOLD,
        JevContinuationGate.PROBLEMS_RESOLVED: JEV_PROBLEMS_RESOLVED_THRESHOLD,
        JevContinuationGate.PHASE_PROGRESS: JEV_PHASE_PROGRESS_THRESHOLD,
        JevContinuationGate.OUTPUT_EXTENT: JEV_OUTPUT_EXTENT_THRESHOLD,
        JevContinuationGate.REQUIRED_ACTIONS: JEV_REQUIRED_ACTIONS_THRESHOLD,
        JevContinuationGate.CUMULATIVE_OBLIGATIONS: JEV_CUMULATIVE_OBLIGATIONS_THRESHOLD,
        JevContinuationGate.DISCOVERED_ITEM_COVERAGE: JEV_DISCOVERED_ITEM_COVERAGE_THRESHOLD,
        JevContinuationGate.FAITHFUL_SCOPE: JEV_FAITHFUL_SCOPE_THRESHOLD,
        JevContinuationGate.EXPERT_DEPTH: JEV_EXPERT_DEPTH_THRESHOLD,
        JevContinuationGate.SELF_REVIEW: JEV_SELF_REVIEW_THRESHOLD,
        JevContinuationGate.REQUIRED_SEQUENCE: JEV_REQUIRED_SEQUENCE_THRESHOLD,
    })
    # @intent gate-guidance-covers-purpose-use-and-failure-modes
    # Review on PR #506 asked for four to five sentences on each of three topics for every gate: what it checks,
    # how to use its failed questions, and its common failure modes. Every continuation renders this same text.
    _descriptions: Mapping[JevContinuationGate, JevDoneGateDescription] = MappingProxyType({
        JevContinuationGate.MULTI_PART: JevDoneGateDescription(
            what_it_checks="This gate checks that every separate output the request asks for was actually produced, including outputs the user mentioned only in passing. Before work began, the run state listed each requested deliverable with an id, a description, and a signal that shows it is complete. After the finish attempt, the handoff quoted the run evidence for each deliverable, such as written files, command results, or passages of the final answer. Jev then answered one yes/no question per deliverable about whether the evidence shows that deliverable produced in full.",
            how_to_use="A failed question names one deliverable whose evidence did not show it complete, and every deliverable not listed has already passed. Find that deliverable by its id in the run state, read its completion signal, and compare it with what the handoff says is still missing. Produce the missing parts in full and leave them visible in the run, because the gate only sees what the run shows. Do not rework deliverables that passed, and do not add outputs the request does not ask for.",
            failure_modes="The most common failure is finishing the prominent deliverable and forgetting a secondary one, such as documentation, a test, or a summary the user asked for in passing. Another is producing a partial version of a deliverable, such as a stub, a placeholder, or a section left unfinished. A third is describing a deliverable in the final answer without the run containing the deliverable itself. Deliverables split across several messages or files can also be missed when a later edit to one part overwrote another.",
        ),
        JevContinuationGate.CAN_SIMPLIFY: JevDoneGateDescription(
            what_it_checks="This gate checks whether the implementation the run produced can stay as it is, or whether a smaller implementation would preserve everything the request requires. Before work began, the run state recorded the implementation's scope and the behaviors, interfaces, and constraints any change must preserve. After the finish attempt, the handoff compared the work against that scope and named a concrete, behavior-preserving simplification if one is supported. Jev then answered whether the implementation can remain as it is without that simplification.",
            how_to_use="A failed question means the handoff identified a specific simplification, and Jev judged that the current implementation should not stay as it is. Read the named simplification and the preservation requirements together before changing any code. Apply the smallest concrete change that achieves the simplification while keeping every behavior, interface, constraint, and quality condition in the run state and the original request. If the simplification would remove required behavior, keep the current design and show the requirement that blocks the change.",
            failure_modes="The common failure is leaving duplicated logic, an unnecessary abstraction, or an extra layer in place when a smaller design does the same job. Another is applying a simplification that silently drops a required behavior, an edge case, or a public interface. A third is rewriting far more than the named simplification calls for, which widens the change beyond the request. Simplifications that are asserted but never shown in the code also leave this gate failing.",
        ),
        JevContinuationGate.OUTPUT_COUNT: JevDoneGateDescription(
            what_it_checks="This gate checks explicit quantities of requested outputs, such as ten examples or three options, against the unit, scope, and distinctness rule the request sets. Before work began, the run state recorded each quantity with its target count, unit, scope, distinctness rule, and completion criterion. After the finish attempt, the handoff listed each visible candidate output with its evidence and a distinctness key, and code counted the distinct qualifying candidates. Jev then checked each quantity's candidates for relevance, evidence, and key fidelity without recounting them.",
            how_to_use="A failed question names one quantity that is short or whose candidates do not qualify. Compare the observed count with the target, and read which candidates did not qualify and why. Produce enough additional distinct outputs that meet the scope and qualification rule, and make each one visible. Do not fill the gap with duplicates, near duplicates, or items from outside the requested scope.",
            failure_modes="The most common failure is producing fewer items than requested and stating the requested number anyway. Another is padding the count with items that repeat one another under different wording. A third is counting items that fall outside the requested scope or unit. A count stated in the final answer without the items themselves being visible also fails this gate.",
        ),
        JevContinuationGate.CLAIMS: JevDoneGateDescription(
            what_it_checks="This gate checks whether each assertion the final answer makes about the run is supported by evidence from the run itself. After the finish attempt, the handoff extracted the claims in the final answer and split each one into individual assertions with completion criteria. It also quoted the tool calls and outputs that bear on each claim and noted what evidence is missing. Jev then answered one yes/no question per assertion about whether the recorded evidence supports it.",
            how_to_use="A failed question names one assertion that the recorded tool activity does not support, together with its parent claim. For each one, either do the work that makes the assertion true and leave its evidence in the run, or correct the final answer so it claims only what the run shows. Running the test, reading the file, or repeating the call are typical ways to produce the missing evidence. Never keep an unsupported assertion in the final answer, and do not let evidence for one claim stand in for another.",
            failure_modes="The most common failure is a final answer that reports tests passing, files updated, or behavior verified when no such result appears in the run. Another is a tool call that was attempted but failed, while the final answer describes it as successful. A third is a broad claim that everything works when the run supports it only for one narrow case. Claims about the user's environment or external systems that were never inspected also fail this gate.",
        ),
        JevContinuationGate.INPUT_EXHAUSTION: JevDoneGateDescription(
            what_it_checks="This gate checks whether a traversal of a collection the request asked for, such as all pages of results or every record in a source, reached its stopping condition. Before work began, the run state recorded each collection with its scope and the condition that shows it is exhausted. After the finish attempt, the handoff recorded the last successful position for each traversal, the next step, and what is still missing. Jev then answered one yes/no question per collection about whether the evidence shows it traversed to exhaustion.",
            how_to_use="A failed question names one collection whose traversal stopped before its exhaustion condition was shown. Resume from the last known position the handoff records, not from the beginning. Continue until the source returns its true end marker, an empty page, or whatever the exhaustion condition names. Treat a retrieval error as a reason to retry or report, never as the end of the collection.",
            failure_modes="The most common failure is stopping after the first page or batch of results when more remain. Another is treating a timeout, rate limit, or error response as if the collection had ended. A third is trusting a reported total instead of reaching the actual end. Cursors or continuation tokens left unused at the end of the run also fail this gate.",
        ),
        JevContinuationGate.NEGATIVE_COVERAGE: JevDoneGateDescription(
            what_it_checks="This gate checks requested inspections whose conclusion may be negative, such as confirming that no file uses a deprecated call or that a log contains no errors. Before work began, the run state recorded each inspection target with the signal that shows it was actually inspected. After the finish attempt, the handoff quoted the run evidence for each target and noted what is still missing. Jev then answered one yes/no question per target about whether the evidence shows the inspection performed over the requested target.",
            how_to_use="A failed question names one inspection target whose conclusion lacks evidence of the inspection itself. Perform the inspection over the whole target, such as running the search across every file or reading the entire log. Leave the command, its scope, and its output visible, so a reader can see how the negative conclusion was reached. If the inspection finds something, report it instead of the expected negative.",
            failure_modes="The most common failure is stating that nothing was found without showing any search or inspection. Another is searching only part of the target, such as one directory, and drawing a conclusion about the whole. A third is a search pattern too narrow to catch the forms the request cares about. Conclusions drawn from memory or general knowledge, rather than from the target itself, also fail this gate.",
        ),
        JevContinuationGate.GUARANTEED_NEXT_ACTIONS: JevDoneGateDescription(
            what_it_checks="This gate checks follow-up actions that the request and an observation from the run together make necessary, such as rerunning a test after a fix the user asked for. After the finish attempt, the handoff listed candidate actions, each with the requested outcome, the trigger observed in the run, the action, and what evidence is missing. Jev answered two questions per candidate: whether the request and trigger require the action, and whether the action is still unfinished. Only candidates that are both necessary and unfinished fail the gate.",
            how_to_use="A failed question names one action that Jev judged both necessary and unfinished. Read the requested outcome and the observed trigger to confirm why the action follows from the request. Complete the action and leave its result visible in the run. Do not take other optional follow-up steps that the request and an observed trigger do not jointly require.",
            failure_modes="The most common failure is making a change and not running the check that the change obviously calls for, such as rebuilding or retesting. Another is noticing a trigger, such as a failing dependency, and leaving the required response to it undone. A third is treating a necessary action as optional because the request did not spell it out. Starting the action without finishing it also fails this gate.",
        ),
        JevContinuationGate.TARGET_OUTCOME: JevDoneGateDescription(
            what_it_checks="This gate checks whether each outcome the request targets was demonstrated by direct evidence, rather than inferred from a proxy milestone. Before work began, the run state recorded each target outcome with its actual target, its scope, and the criterion that shows it is complete. After the finish attempt, the handoff recorded the proxy milestone the run reached, the direct evidence for the target itself, and what is still missing. Jev then answered one yes/no question per outcome about whether direct evidence shows the target met.",
            how_to_use="A failed question names one target outcome whose direct evidence is missing, even if a related milestone was reached. Compare the observed proxy milestone with the actual target and its completion criterion. Produce direct evidence for the target itself, such as running the behavior, measuring the result, or showing the end state. If the target cannot be reached, say so in the final answer instead of presenting the proxy as the outcome.",
            failure_modes="The most common failure is treating a successful build, a merged change, or a written script as proof that the behavior the user wanted now works. Another is reporting a metric that moved in the right direction as if it met the target. A third is measuring a nearby target, such as a test environment, when the request named a different one. Reporting effort or likely future effects in place of the end state also fails this gate.",
        ),
        JevContinuationGate.MOTIVATING_CASE: JevDoneGateDescription(
            what_it_checks="This gate checks whether the run exercised the specific scenario that motivated the request, including the condition that sets it apart from a nearby case that does not count. Before work began, the run state recorded each scenario with its target, its condition, its near miss, any expected behavior, and the mode in which it may be exercised. After the finish attempt, the handoff quoted the run evidence for each scenario and noted what is still missing. Jev then answered one yes/no question per scenario about whether the evidence shows it exercised.",
            how_to_use="A failed question names one motivating scenario the run did not exercise. Read its condition and its near miss together, so you reproduce the case the user cares about and not the easier neighbor. Exercise it in the allowed mode, such as a test, a script, or a manual run, and show the observed behavior. When the scenario has an expected behavior, show the result next to it.",
            failure_modes="The most common failure is testing only the ordinary path while the user's problem lives on a boundary or an unusual input. Another is exercising the near miss, which looks similar but lacks the condition that made the user ask. A third is describing how the scenario would behave without running it. Using a mode the request ruled out, such as a mock where a real run was required, also fails this gate.",
        ),
        JevContinuationGate.SCOPE_COVERAGE: JevDoneGateDescription(
            what_it_checks="This gate checks whether the requested change was applied to every member of the scope the request names, such as all files, all components, or every instance of a pattern. Before work began, the run state recorded each scope dimension with the user's own wording, the kind of member it covers, and the change to apply. After the finish attempt, the handoff listed the members the run found and quoted the evidence for each. Jev answered whether the workspace enumeration is complete and, for each member, whether the evidence shows the change applied.",
            how_to_use="A failed question names either a missing inventory or one member without applied work. For an inventory failure, enumerate every member of that kind in the workspace before changing anything else. For a member failure, apply the requested change to that member and leave the result visible in the run. Track which members are discovered and which are processed, so a listed member is never mistaken for a finished one.",
            failure_modes="The most common failure is applying the change to the files the agent happened to open and missing others of the same kind. Another is never enumerating the scope at all, so there is no way to tell how many members exist. A third is listing every member but changing only some of them. Members in unusual locations, such as tests, configuration, or generated code, are frequently missed.",
        ),
        JevContinuationGate.COMPLETION_EVIDENCE: JevDoneGateDescription(
            what_it_checks="This gate checks whether the final answer's overall completion status matches what the run evidence shows against the outcomes the original request asked for. After the finish attempt, the handoff listed the requested outcomes, the work the run shows for each, and anything unfinished or blocked. It also recorded the completion status the final answer communicates, such as complete, partial, or blocked. Jev then answered one yes/no question about whether the run evidence supports that status.",
            how_to_use="A failed question means the final answer's account of completion is stronger than, or different from, what the evidence supports. Compare the requested outcomes with the work shown and with the unfinished or blocked items the handoff names. Either finish the outcomes that remain, or rewrite the final answer so its status is accurate and each unresolved blocker is stated plainly. Tie every outcome you report as done to an observable result in the run.",
            failure_modes="The common failure is a final answer that says the task is done while the run shows only part of the requested outcomes. Another is a blocker the run hit, such as a missing credential or a failing dependency, that the final answer never mentions. A third is reporting an outcome as complete because the work was started, not because a result was shown. Vague summaries that hide which outcomes are unfinished also fail this gate.",
        ),
        JevContinuationGate.INPUT_SET_COVERAGE: JevDoneGateDescription(
            what_it_checks="This gate checks whether every input the user explicitly asked the agent to engage was actually processed at the requested depth and scope. Before work began, the run state recorded each target input or bounded group with its identity, its scope, the requested action, and a signal that shows engagement. After the finish attempt, the handoff quoted the tool-call evidence for each target, separating content actually read or processed from a path, title, listing, or excerpt. Jev then answered one yes/no question per target about whether the evidence shows the requested action over its full scope.",
            how_to_use="A failed question names one input the run did not engage as requested. Find the target in the run state and read its scope and engagement signal. Open or process the input to the requested depth, such as reading the whole document or every page in a date range, and leave that work visible. Base any conclusion about the input on its content, not on its name or metadata.",
            failure_modes="The most common failure is reading only the first part of a long input when the request asked for all of it. Another is inspecting a file listing, title, or summary and treating that as having read the input. A third is skipping one input in a named set because the others seemed sufficient. Exclusions and date bounds in the request are also easy to drop, which leaves the wrong part of the input processed.",
        ),
        JevContinuationGate.OUTPUT_EXTENT: JevDoneGateDescription(
            what_it_checks="This gate checks whether a requested output meets a measurable size target, such as a minimum word count or a maximum number of pages. Before work began, the run state recorded each output target with its unit, its comparator, and the amount the request sets. After the finish attempt, code measured the final visible output in that unit, and the handoff noted what is still missing. Jev then answered one yes/no question per target about whether the output meets the requested extent.",
            how_to_use="A failed question names one output whose measured extent does not satisfy the request, and it shows the observed amount next to the required amount. Produce or trim the output until it meets the target in the requested unit, then make the final version visible. Add substantive content rather than filler when an output is too short. Measure the final material, not a draft or an estimate.",
            failure_modes="The most common failure is an answer that is noticeably shorter than the length the user asked for. Another is measuring the wrong unit, such as counting characters when the request named words. A third is reporting an estimated length without producing the complete output. Exceeding a maximum, or padding to reach a minimum with repetition, also fails this gate.",
        ),
        JevContinuationGate.REPORT_ACTION_ALIGNMENT: JevDoneGateDescription(
            what_it_checks="This gate checks whether the final account of the run matches what the run actually did, compared against plans or commitments the agent made along the way. After the finish attempt, the handoff listed each earlier plan or commitment with its recorded execution, the final account of it, and its relevance to the original request. It also quoted the evidence and noted any mismatch still to reconcile. Jev then answered one yes/no question per item about whether the final account aligns with the recorded execution.",
            how_to_use="A failed question names one plan item whose execution and final account disagree. Decide whether the planned work is still required by the original request. If it is, complete it and show the result, and if it is not, correct the final account so it describes what was actually done. A plan alone never obliges you to do work the user did not ask for.",
            failure_modes="The most common failure is a final summary that lists steps the agent planned but never carried out. Another is a summary that omits a material change the run did make. A third is a plan that was silently abandoned, leaving a required result undone with no mention in the final answer. Reports that describe intended behavior as if it were verified also fail this gate.",
        ),
        JevContinuationGate.ASSUMPTIONS_RECONCILED: JevDoneGateDescription(
            what_it_checks="This gate checks whether assumptions that changed during the run were revisited, and whether the work that depended on them was reconciled with what the run later observed. After the finish attempt, the handoff listed each changed premise with its original basis, the later observation that changed it, the work it affected, and what the run did afterward. It also quoted the run evidence and noted what is still unreconciled. Jev then answered one yes/no question per premise about whether the evidence shows its dependent work reconciled.",
            how_to_use="A failed question names one changed assumption whose dependent work was not revisited. Read the original assumption, the later observation, and the affected work together. Verify, revise, or explicitly retire each piece of affected work based on the current evidence. Recheck only the work that depends on the changed premise, and carry forward results it does not affect.",
            failure_modes="The most common failure is discovering that an early assumption was wrong and continuing to build on the work that relied on it. Another is fixing the assumption in one place while other dependent code, text, or conclusions still use the old premise. A third is noticing the change but never recording whether the affected work still holds. Final answers that still state the disproven premise also fail this gate.",
        ),
        JevContinuationGate.PROBLEMS_RESOLVED: JevDoneGateDescription(
            what_it_checks="This gate checks whether problems the run discovered along the way were repaired and the affected behavior was successfully revalidated. After the finish attempt, the handoff listed each problem the run encountered, along with items from the original request that the repairs may have displaced. For each item it recorded the repair reported, the verification performed, the run evidence, and what is still missing. Jev then answered one yes/no question per item about whether the evidence shows it resolved.",
            how_to_use="A failed question names one problem whose repair or revalidation is not shown, or one original request item that is still incomplete. Fully repair each named problem, then run the validation that exercises the affected behavior and show it passing. After the repairs, return to the original request and complete every remaining part. A fix that was not rerun does not count, and neither does a repair that left requested work unfinished.",
            failure_modes="The most common failure is claiming a fix without running the test or command that originally failed. Another is a validation run that failed or was skipped, while the final answer reports the problem solved. A third is spending the run on a repair and never returning to the requested work it interrupted. Fixes that hide the symptom, such as disabling a check or silently catching an error, also fail this gate.",
        ),
        JevContinuationGate.PHASE_PROGRESS: JevDoneGateDescription(
            what_it_checks="This gate checks whether the run entered and made substantive progress on every stage or phase the request requires. Before work began, the run state listed each required stage with its required result, its scope in the request, and a criterion for its output. After the finish attempt, the handoff quoted the run evidence for each stage and noted what is still missing. Jev then answered one yes/no question per stage about whether the evidence shows substantive requested work in it.",
            how_to_use="A failed question names one required stage with no evidence of substantive work, and stages not listed have passed. Find the stage in the run state, read its required result and output criterion, and do the requested activity for it. Show concrete work or results for the stage, because a plan to do it later or a mention in the final answer is not progress. This gate does not require each stage to be fully finished, but it does require real work in every one.",
            failure_modes="The most common failure is stopping after the first phase, such as research or planning, and never starting the implementation or write-up the request also asked for. Another is discussing a later stage in the final answer without doing any of its work. A third is skipping a middle stage in a multi-stage request and jumping to the end. Treating an outline of a stage as progress on the stage also fails this gate.",
        ),
        JevContinuationGate.REQUIRED_ACTIONS: JevDoneGateDescription(
            what_it_checks="This gate checks whether each action the user explicitly asked for was completed, and in the requested order when the request sets one. Before work began, the run state recorded each required action with its completion signal and any actions that must come before it. After the finish attempt, the handoff quoted the evidence for each action, including where in the run it was completed, and noted what is still missing. Jev then answered one yes/no question per action about whether the evidence shows it completed.",
            how_to_use="A failed question names one required action that is incomplete or completed out of order. Find the action in the run state, read its completion signal, and check whether its predecessors are complete. Complete the predecessors first when the request requires an order, then complete the action and show its result. Leave separate evidence for each action instead of grouping several into one claim.",
            failure_modes="The most common failure is leaving one explicitly requested step undone, such as committing, notifying, or cleaning up. Another is promising the action in the final answer without performing it. A third is performing the action before a step the user said must come first. Attempts that failed but were reported as completed also fail this gate.",
        ),
        JevContinuationGate.CUMULATIVE_OBLIGATIONS: JevDoneGateDescription(
            what_it_checks="This gate checks that requirements from every supplied user turn remain accounted for, not only those in the latest message. Before work began, the run state recorded each obligation with its source turn, its instruction, its completion signal, and whether a later turn cancelled or replaced it. After the finish attempt, the handoff quoted the evidence for each obligation and noted what is still missing. Jev answered whether each turn's inventory of obligations is complete, and whether the evidence shows each active obligation done.",
            how_to_use="A failed question names either an incomplete inventory for one user turn or one obligation whose completion is not shown. For an inventory failure, reread that turn and restore every requirement and explicit change it contains. For an obligation failure, complete the instruction unless the conversation clearly cancels or replaces it. Follow later explicit changes, but keep earlier requirements that remain compatible with them.",
            failure_modes="The most common failure is completing the latest request while forgetting a requirement from an earlier turn. Another is treating an earlier requirement as cancelled when no later turn actually cancelled it. A third is applying a later change partially, so parts of the work follow the old instruction and parts follow the new one. Constraints stated early in the conversation, such as style or scope limits, are especially easy to drop.",
        ),
        JevContinuationGate.DISCOVERED_ITEM_COVERAGE: JevDoneGateDescription(
            what_it_checks="This gate checks that every in-scope item discovered from a source during the run, such as each failing test in a report or each issue in a list, was inventoried and processed as requested. After the finish attempt, the handoff recorded each source's output, the candidate items it contains, and the evidence and missing work for each item. Jev answered whether each source's candidate inventory is complete, and whether each item was processed as requested. An item fails when it is missing from the inventory or listed without the requested processing.",
            how_to_use="A failed question names either an incomplete inventory for one source or one item without the requested processing. For an inventory failure, reread the complete source output, add every omitted in-scope item, and process each one. For an item failure, apply the requested processing to that item and leave the result visible. Compare the full inventory with the processed items before finishing, so no item is dropped between discovery and handling.",
            failure_modes="The most common failure is processing the first few items of a long list and stopping. Another is an inventory built from a truncated or partial view of the source output. A third is identifying an item and then never returning to handle it. Items that look similar to ones already processed are often skipped as duplicates when they are distinct.",
        ),
        JevContinuationGate.FAITHFUL_SCOPE: JevDoneGateDescription(
            what_it_checks="This gate checks whether the run did the hard part of the request in the user's intended scope, rather than a narrower, easier, or redefined version. Before work began, the run state named the single requirement most likely to be avoided, along with the limits the user stated. After the finish attempt, the handoff quoted the evidence that the hard part was done and noted what is still missing. Jev then answered one yes/no question about whether the evidence shows the saved hard part completed in the user's scope.",
            how_to_use="A failed question means the hard part recorded in the run state is not shown done in the scope the user asked for. Give that hard part your first attention, and keep every limit the user stated. Extra iterations, tokens, and tool calls may be granted for this continuation, so spend them on the hard part. Do not substitute a narrower, mocked, skipped, hard-coded, or redefined version.",
            failure_modes="The most common failure is solving an easier version of the problem and presenting it as the requested one. Another is replacing real behavior with a mock, a stub, or a hard-coded value. A third is quietly narrowing the scope, such as handling one case when the user asked for the general one. Redefining the goal in the final answer so the easier work looks complete also fails this gate.",
        ),
        JevContinuationGate.EXPERT_DEPTH: JevDoneGateDescription(
            what_it_checks="This gate checks whether the run handled the details a domain expert would treat as essential, at the depth the task needs. Before work began, the run state listed each deliverable's expert details, each with a shallow version to move past, the risk it carries, and a condition that shows it is done. After the finish attempt, the handoff quoted the evidence for each detail and noted what depth is still missing. Jev then answered one yes/no question per detail about whether the evidence shows it handled at expert depth.",
            how_to_use="A failed question names one detail handled only at a shallow depth, and the list is ordered from weakest to strongest. Focus first on the weakest few details, because the next check will re-rank the rest after more work. For each one, read its shallow version, its risk, and its done condition, then add the analysis, implementation, or validation the condition requires. Keep added depth relevant to the named risk instead of expanding unrelated parts of the work.",
            failure_modes="The most common failure is covering the easy path while leaving a risky boundary or edge case unhandled. Another is naming a hard detail in the final answer without addressing it in the work. A third is generic advice where the task needs specific values, mechanisms, or tests. Depth spent on details the request does not need, while the named ones stay shallow, also fails this gate.",
        ),
        JevContinuationGate.SELF_REVIEW: JevDoneGateDescription(
            what_it_checks="This gate checks objections that a strict independent reviewer raised against the run's work. After the finish attempt, the reviewer listed each objection in order of severity with the condition that would resolve it, and the handoff recorded what each objection still lacks. Jev answered two questions per objection: whether the work shows it resolved, and whether fixing it is within the user's request. An objection fails the gate only when it is unresolved and within scope.",
            how_to_use="A failed question names one standing objection that Jev judged both unresolved and in scope. Treat the objection as a claim to investigate, not as proof that the weakness exists. If it holds, make the change and show the objection's acceptance condition in the work. If it does not apply to the request, show the evidence or the request wording that puts it out of scope.",
            failure_modes="The most common failure is acknowledging an objection in the final answer without changing the work. Another is dismissing an objection as out of scope without tying that decision to the request. A third is a fix that addresses the objection's wording but not its acceptance condition. Expanding the work to satisfy objections that fall outside the request is also a failure, because it adds unrequested work.",
        ),
        JevContinuationGate.REQUIRED_SEQUENCE: JevDoneGateDescription(
            what_it_checks="This gate checks whether the stages the request requires were completed in order, each with visible work and each using the previous stage's output. Before work began, the run state recorded each stage with its position and completion criterion. After the finish attempt, the handoff recorded the run events that show each stage's work, where each stage started and finished, and what is still missing. Jev answered whether each stage's work is shown and whether it uses the previous stage's output, and code checked that no stage began before the previous one finished.",
            how_to_use="A failed question names one stage with missing work, missing use of the previous output, or a start before the previous stage finished. Finish that stage's work before moving to any later stage. When an earlier stage's output changes, redo every stage after it so each one reflects the current upstream result. Leave each stage's output visible, so the next stage's use of it can be seen.",
            failure_modes="The most common failure is skipping a stage or merging two stages into one step. Another is starting a later stage before the earlier one is finished, then going back to patch the earlier stage. A third is a stage that ignores the previous stage's output and works from the original input instead. Changing an early stage without redoing the stages after it also fails this gate.",
        ),
    })

    @classmethod
    def question(cls, check: JevContinuationGate) -> JevDoneQuestion:
        """Return the first fixed question a done check asks about each item it checks."""
        return cls.questions(check)[0]

    @classmethod
    def questions(cls, check: JevContinuationGate) -> tuple[JevDoneQuestion, ...]:
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
    def description(cls, check: JevContinuationGate) -> str:
        # Supplies the same gate-specific guidance to every continuation that explains failed questions.
        """Return one gate's continuation guidance: what it checks, how to use it, and its failure modes, one paragraph each."""
        found = cls._descriptions.get(check)
        if found is None:
            raise ConfigurationError(
                f"Jev done check {check!r} has no registered continuation description.",
                details={"check": str(check), "registered": [item.value for item in cls._descriptions]},
            )
        return "\n\n".join((found.what_it_checks, found.how_to_use, found.failure_modes))

    @classmethod
    def threshold(cls, check: JevContinuationGate) -> float:
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
    def inventory_question(cls, check: JevContinuationGate) -> JevDoneQuestion:
        """Return the fixed per-source inventory question for a check that audits generated candidate completeness."""
        # @intent source-audit-questions-are-registered-beside-check-questions
        # A preset may need fixed questions over generated candidates and independent completeness questions
        # over their source messages; both are selected from one registry rather than assembled at runtime.
        found = cls._inventory_questions.get(check)
        if found is None:
            raise ConfigurationError(f"Jev done check {check!r} has no registered inventory question.", details={"check": str(check), "registered": [item.value for item in cls._inventory_questions]})
        return found

    @classmethod
    def resolve(cls, value: object) -> JevContinuationGate:
        """Convert one user-supplied check (enum member or its string value) to a JevContinuationGate."""
        try:
            return value if isinstance(value, JevContinuationGate) else JevContinuationGate(value)
        except ValueError as exc:
            raise ConfigurationError(
                f"Unsupported Jev done check: {value!r}.",
                details={
                    "received": repr(value),
                    "available": [item.value for item in JevContinuationGate],
                },
            ) from exc

    @classmethod
    def validate(cls, values: Iterable[object]) -> tuple[JevContinuationGate, ...]:
        """Convert the user's enabled done checks to a tuple of unique checks, each with a registered question and threshold."""
        # @intent done-checks-fail-before-any-jev-call
        # Settings construction calls this, so a typo, a bare string, or a repeated check fails when the
        # agent is built instead of silently asking Jev the wrong (or duplicated) questions at every finish.
        missing_descriptions = set(JevContinuationGate) - set(cls._descriptions)
        extra_descriptions = set(cls._descriptions) - set(JevContinuationGate)
        if missing_descriptions or extra_descriptions:
            # Each JevDoneGateDescription validates its own paragraph lengths; this guards coverage.
            raise ConfigurationError(
                "Jev done gate descriptions must cover every check exactly once.",
                details={
                    "missing": [check.value for check in missing_descriptions],
                    "extra": [check.value for check in extra_descriptions],
                },
            )
        if isinstance(values, (str, bytes)):
            raise ConfigurationError(
                "JevContinuationGateSettings.enabled must be an iterable of Jev done checks, not a string.",
                details={"received": repr(values)},
            )
        try:
            checks = tuple(cls.resolve(value) for value in values)
        except TypeError as exc:
            raise ConfigurationError(
                "JevContinuationGateSettings.enabled must be an iterable of Jev done checks.",
                details={"received": type(values).__name__},
            ) from exc
        if len(set(checks)) != len(checks):
            raise ConfigurationError(
                "JevContinuationGateSettings.enabled cannot enable the same check twice.",
                details={"received": [check.value for check in checks]},
            )
        for check in checks:
            cls.questions(check)
            cls.threshold(check)
            if check in cls._inventory_questions:
                cls.inventory_question(check)
        return checks


__all__ = ["JevDoneRegistry"]
