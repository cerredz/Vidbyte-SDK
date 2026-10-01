"""FILE: vidbyte/lib/jev/done/__init__.py

PURPOSE: Exposes JevDoneRegistry and every fixed done question dataclass, including member-level scope-coverage, request-required phase-progress, bounded-input coverage, required-actions, and cumulative-obligation questions, from the canonical done question folder.
ROLE IN CODEBASE: JevRuntimeSettings and JevRunState (vidbyte/agents/jev/done/) import JevDoneRegistry from here; tests import the question dataclasses to pin their contract.
ARCHITECTURE NOTE: This folder is the one home for fixed done questions and their registry; the check vocabulary lives in vidbyte/lib/enums/jev.py, records and structured-reply payloads in vidbyte/lib/dataclasses/jev.py, and the logic that asks and acts on the questions in vidbyte/agents/jev/done/.
COMMON MODIFICATION PATTERNS: Load skills/asking-jev-questions/SKILL.md before writing or changing any question (see README.md in this folder), then export each new check's question module here beside multi_part.
KNOWN EDGE CASES: Importing this package builds the question registry but never resolves credentials or constructs a decision runner.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-completion-evidence.md, docs/design/jev-phase-progress.md, docs/design/jev-input-set-coverage.md, docs/design/jev-report-action-alignment.md, docs/design/jev-assumption-reconciliation-done-criteria.md, docs/design/jev-negative-coverage.md, docs/design/jev-mid-run-problem-repair-gate.md, skills/jev-agent/SKILL.md, and skills/jev-continuation/SKILL.md, docs/design/jev-guaranteed-next-actions.md, docs/design/jev-required-actions-done-criteria.md, docs/design/jev-cumulative-obligations-done-check.md.
TESTS: tests/test_jev_done.py.
"""

from vidbyte.lib.jev.done.assumptions_reconciled import AssumptionsReconciledQuestion
from vidbyte.lib.jev.done.claims import ClaimsSupportedQuestion
from vidbyte.lib.jev.done.completion_evidence import CompletionEvidenceSupportedQuestion
from vidbyte.lib.jev.done.cumulative_obligations import (
    CumulativeObligationFulfilledQuestion,
    CumulativeUserTurnReconciledQuestion,
)
from vidbyte.lib.jev.done.done import JevDoneRegistry
from vidbyte.lib.jev.done.guaranteed_next_actions import (
    GuaranteedActionNecessaryQuestion,
    GuaranteedActionUnfinishedQuestion,
)
from vidbyte.lib.jev.done.input_exhaustion import InputExhaustionTraversedQuestion
from vidbyte.lib.jev.done.input_set_coverage import InputSetCoverageQuestion
from vidbyte.lib.jev.done.motivating_case import MotivatingCaseExercisedQuestion
from vidbyte.lib.jev.done.multi_part import DONE_STATE, MultiPartDeliveredQuestion
from vidbyte.lib.jev.done.negative_coverage import NegativeCoverageSupportedQuestion
from vidbyte.lib.jev.done.output_count import OutputCountSatisfiedQuestion
from vidbyte.lib.jev.done.output_extent import OutputExtentSatisfiedQuestion
from vidbyte.lib.jev.done.phase_progress import PhaseProgressReachedQuestion
from vidbyte.lib.jev.done.problems_resolved import ProblemsResolvedQuestion
from vidbyte.lib.jev.done.report_action_alignment import ReportActionAlignmentQuestion
from vidbyte.lib.jev.done.required_actions import RequiredActionCompletedQuestion
from vidbyte.lib.jev.done.scope_coverage import ScopeCoverageAppliedQuestion
from vidbyte.lib.jev.done.target_outcome import TargetOutcomeDemonstratedQuestion

__all__ = [
    "DONE_STATE",
    "AssumptionsReconciledQuestion",
    "ClaimsSupportedQuestion",
    "CompletionEvidenceSupportedQuestion",
    "CumulativeObligationFulfilledQuestion",
    "CumulativeUserTurnReconciledQuestion",
    "GuaranteedActionNecessaryQuestion",
    "GuaranteedActionUnfinishedQuestion",
    "InputExhaustionTraversedQuestion",
    "InputSetCoverageQuestion",
    "JevDoneRegistry",
    "MotivatingCaseExercisedQuestion",
    "MultiPartDeliveredQuestion",
    "NegativeCoverageSupportedQuestion",
    "OutputCountSatisfiedQuestion",
    "OutputExtentSatisfiedQuestion",
    "PhaseProgressReachedQuestion",
    "ProblemsResolvedQuestion",
    "ReportActionAlignmentQuestion",
    "RequiredActionCompletedQuestion",
    "ScopeCoverageAppliedQuestion",
    "TargetOutcomeDemonstratedQuestion",
]
