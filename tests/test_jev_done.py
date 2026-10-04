"""FILE: tests/test_jev_done.py

PURPOSE: Verifies JevAgent's done checks deterministically without live model calls: request-derived and post-run records, fixed questions, shared state and handoff schemas, one-time request reviews, batched Jev requests, expert-depth ranking, trace-backed required actions, and continuation and fail-open behavior.
ROLE IN CODEBASE: Pins the Jev done-check contracts: records live in vidbyte/lib, every structured-output field carries a 4-6 sentence description, the handoff reads the main agent's window through ContextManager, and every enabled check's questions share one Jev request.
ARCHITECTURE NOTE: Scripted generative and decision runners replace only the external boundaries while production settings, registry, schemas, runtime hook, and response wiring stay active.
COMMON MODIFICATION PATTERNS: Add cases for every new done check's schema, question, threshold boundary, dynamic or request-derived items, and availability policy.
KNOWN EDGE CASES: No test may contact TypeSafe or a generative provider; the token-floor test needs tiktoken and is skipped without it.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-expert-depth-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-completion-evidence.md, docs/design/jev-assumption-reconciliation-done-criteria.md, docs/design/jev-required-actions-done-criteria.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: python -m unittest tests.test_jev_done and python scripts/test-jev-multipart-done-criteria.py.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel

from lint.core.discovery import SourceFile
from lint.rules.s062_no_implicit_string_concatenation import (
    ImplicitConcatenationScanner,
)
from tests.agent_test_support import bind_test_runner
from vidbyte import (
    BaseAgent,
    JevAgent,
    JevAgentSettings,
    JevAssumptionEvidence,
    JevAssumptionsReconciledEvidence,
    JevCanSimplify,
    JevCanSimplifyEvidence,
    JevClaimAssertion,
    JevClaimContext,
    JevClaimEvidence,
    JevClaimIdentity,
    JevClaimKind,
    JevClaimScope,
    JevClaimsEvidence,
    JevContinualSettings,
    JevCumulativeObligation,
    JevCumulativeObligationEvidence,
    JevCumulativeObligations,
    JevCumulativeObligationsEvidence,
    JevDeliverableEvidence,
    JevDiscoveredItem,
    JevDiscoveredItemBatch,
    JevDiscoveredItemEvidence,
    JevDoneCheck,
    JevInputSetCoverage,
    JevInputTarget,
    JevNegativeCoverage,
    JevNegativeCoverageEvidence,
    JevNegativeCoverageEvidenceItem,
    JevNegativeCoverageTarget,
    JevOutputCount,
    JevOutputCountEntry,
    JevOutputCountEvidence,
    JevOutputCountEvidenceItem,
    JevOutputCountObligation,
    JevOutputExtent,
    JevProblemResolutionItem,
    JevProblemsResolvedEvidence,
    JevReportActionAlignment,
    JevReportActionAlignmentItem,
    JevRequiredAction,
    JevRequiredActionEvidence,
    JevRequiredActions,
    JevRequiredActionsEvidence,
    JevRuntimeSettings,
    JevSpecialist,
)
from vidbyte.agents.jev.continuation import JevContinuation, JevDoneContinuation
from vidbyte.agents.jev.done import JevHandoff, JevRunState
from vidbyte.agents.jev.runtime import JevRuntime
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context.primitives import (
    ResponseContextItem,
    TextContextItem,
    ToolCallContextItem,
)
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_ASSUMPTIONS_RECONCILED_THRESHOLD,
    JEV_CAN_SIMPLIFY_THRESHOLD,
    JEV_CLAIMS_THRESHOLD,
    JEV_CUMULATIVE_OBLIGATIONS_THRESHOLD,
    JEV_DISCOVERED_ITEM_COVERAGE_THRESHOLD,
    JEV_DONE_ASSUMPTIONS_RECONCILED_FIELD,
    JEV_DONE_CLAIM_FIELD,
    JEV_DONE_CLAIMS_FIELD,
    JEV_DONE_COMPLETION_EVIDENCE_FIELD,
    JEV_DONE_COMPLETION_ITEM_ID,
    JEV_DONE_COMPLETION_SIGNAL_FIELD,
    JEV_DONE_DELIVERABLE_FIELD,
    JEV_DONE_DELIVERABLES_FIELD,
    JEV_DONE_EVIDENCE_FIELD,
    JEV_DONE_GUARANTEED_NEXT_ACTIONS_FIELD,
    JEV_DONE_HARD_PART_FIELD,
    JEV_DONE_IMPLEMENTATION_FIELD,
    JEV_DONE_INPUT_ACTION_FIELD,
    JEV_DONE_INPUT_ENGAGEMENT_SIGNAL_FIELD,
    JEV_DONE_INPUT_EXHAUSTION_FIELD,
    JEV_DONE_INPUT_IDENTITY_FIELD,
    JEV_DONE_INPUT_SCOPE_FIELD,
    JEV_DONE_INPUT_SET_COVERAGE_FIELD,
    JEV_DONE_MAX_CONTINUATIONS,
    JEV_DONE_NEGATIVE_COVERAGE_FIELD,
    JEV_DONE_OUTPUT_COUNTS_FIELD,
    JEV_DONE_PHASE_PROGRESS_FIELD,
    JEV_DONE_PRESERVATION_FIELD,
    JEV_DONE_PROBLEMS_RESOLVED_FIELD,
    JEV_DONE_REPORT_ACTION_ALIGNMENT_FIELD,
    JEV_DONE_REQUEST_FIELD,
    JEV_DONE_REQUIRED_ACTIONS_FIELD,
    JEV_DONE_SCOPE_COVERAGE_FIELD,
    JEV_EXPERT_DEPTH_FOCUS_LIMIT,
    JEV_EXPERT_DEPTH_THRESHOLD,
    JEV_GUARANTEED_NEXT_ACTIONS_THRESHOLD,
    JEV_INPUT_SET_COVERAGE_THRESHOLD,
    JEV_MULTI_PART_THRESHOLD,
    JEV_NEGATIVE_COVERAGE_THRESHOLD,
    JEV_OUTPUT_COUNT_THRESHOLD,
    JEV_OUTPUT_EXTENT_THRESHOLD,
    JEV_PROBLEMS_RESOLVED_THRESHOLD,
    JEV_REPORT_ACTION_ALIGNMENT_THRESHOLD,
    JEV_REQUIRED_ACTIONS_THRESHOLD,
    JEV_SELF_REVIEW_THRESHOLD,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevAssumptionEvidencePayload,
    JevAssumptionsReconciledPayload,
    JevBrief,
    JevCanSimplifyEvidencePayload,
    JevCanSimplifyPayload,
    JevClaimAssertionPayload,
    JevClaimContextPayload,
    JevClaimEvidencePayload,
    JevClaimIdentityPayload,
    JevClaimScopePayload,
    JevClaimsEvidencePayload,
    JevCompletionEvidenceSectionPayload,
    JevCriterion,
    JevCumulativeObligationEvidenceEntryPayload,
    JevCumulativeObligationEvidencePayload,
    JevCumulativeObligationPayload,
    JevCumulativeObligationsPayload,
    JevCumulativeUserTurnEvidence,
    JevCumulativeUserTurnEvidenceEntryPayload,
    JevDecisionRequest,
    JevDeliverable,
    JevDeliverableEvidencePayload,
    JevDeliverablePayload,
    JevDiscoveredItemBatchEntryPayload,
    JevDiscoveredItemBatchPayload,
    JevDiscoveredItemPayload,
    JevDoneGateDescription,
    JevDoneQuestion,
    JevDoneResult,
    JevExpertDepth,
    JevExpertDepthDeliverable,
    JevExpertDepthDeliverablePayload,
    JevExpertDepthEvidence,
    JevExpertDepthEvidencePayload,
    JevExpertDepthPayload,
    JevExpertDetail,
    JevExpertDetailEvidence,
    JevExpertDetailEvidencePayload,
    JevExpertDetailPayload,
    JevFaithfulScopeEvidence,
    JevFaithfulScopeEvidencePayload,
    JevHandoffPayload,
    JevHandoffRecord,
    JevInputSetCoverageEvidencePayload,
    JevInputSetCoveragePayload,
    JevInputTargetEvidencePayload,
    JevInputTargetPayload,
    JevMotivatingCasePayload,
    JevMultiPart,
    JevMultiPartEvidence,
    JevMultiPartEvidencePayload,
    JevMultiPartPayload,
    JevNegativeCoverageEvidenceItemPayload,
    JevNegativeCoverageEvidencePayload,
    JevNegativeCoveragePayload,
    JevNegativeCoverageTargetPayload,
    JevObjection,
    JevObjectionEvidence,
    JevObjectionEvidencePayload,
    JevObjectionPayload,
    JevOutputCountEntryPayload,
    JevOutputCountEvidencePayload,
    JevOutputCountEvidencePayloadItem,
    JevOutputCountObligationPayload,
    JevOutputCountPayload,
    JevOutputExtentEvidence,
    JevOutputExtentEvidenceItem,
    JevOutputExtentEvidenceItemPayload,
    JevOutputExtentEvidencePayload,
    JevOutputExtentItem,
    JevOutputExtentItemPayload,
    JevOutputExtentPayload,
    JevPhaseProgressEvidencePayload,
    JevPhaseProgressPayload,
    JevPhaseStageEvidencePayload,
    JevPhaseStagePayload,
    JevProblemEvidencePayload,
    JevProblemsResolvedEvidencePayload,
    JevReportActionAlignmentEvidencePayload,
    JevReportActionAlignmentEvidenceSectionPayload,
    JevRequiredActionEvidencePayload,
    JevRequiredActionPayload,
    JevRequiredActionsEvidencePayload,
    JevRequiredActionsPayload,
    JevReviewPayload,
    JevReviewRecord,
    JevRunStatePayload,
    JevRunStateRecord,
    JevScopeCoverageEvidencePayload,
    JevScopeCoveragePayload,
    JevSectionPayload,
    JevSelfReviewEvidence,
    JevSelfReviewEvidencePayload,
)
from vidbyte.lib.enums import (
    JevDoneQuestionKey,
    JevOutputExtentComparator,
    JevOutputExtentUnit,
    JevQuestionType,
    ModelProvider,
)
from vidbyte.lib.enums.jev import JevProblemCheckItemType, JevScopeBreadth
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.lib.jev import JevDoneRegistry
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.done import (
    AssumptionsReconciledQuestion,
    CanSimplifyQuestion,
    ClaimsSupportedQuestion,
    FaithfulScopeQuestion,
    InputSetCoverageQuestion,
    MultiPartDeliveredQuestion,
    NegativeCoverageSupportedQuestion,
    OutputCountSatisfiedQuestion,
    OutputExtentSatisfiedQuestion,
    ProblemsResolvedQuestion,
    ReportActionAlignmentQuestion,
)
from vidbyte.lib.jev.done.expert_depth import ExpertDepthHandledQuestion
from vidbyte.lib.jev.done.guaranteed_next_actions import (
    GuaranteedActionNecessaryQuestion,
    GuaranteedActionUnfinishedQuestion,
)
from vidbyte.lib.jev.done.multi_part import DONE_STATE as MULTI_PART_DONE_STATE
from vidbyte.lib.jev.done.required_actions import RequiredActionCompletedQuestion
from vidbyte.lib.jev.done.state import DONE_STATE
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext, ToolCallState, ToolResult

_RUNNER_PATH = "vidbyte.agents.jev.done.run_state.DecisionModelHelper"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SENTENCE_END = re.compile(r"[.?](?=\s+[A-Z`]|$)")
_REQUEST = "Add a --dry-run flag to the deploy CLI and document it in the README."
_CLAIMED_FINAL_ANSWER = "I updated README.md to document --dry-run and added a test for the deploy command."
_BASE_STATE = {
    "goal": "The deploy CLI can preview a deploy without changing anything, and users can read how.",
    "objective": "A working --dry-run flag in the deploy CLI and a README section that documents it.",
    "mission": "Change only the deploy CLI and its README, and keep every existing flag working.",
    "hard_part": "A working --dry-run flag that prints planned changes without applying them.",
    "what_not_to_do": ["Do not change other commands."],
}
_FAITHFUL_HANDOFF = {
    "faithful_scope": {
        "evidence": "The final answer says --dry-run is implemented, but the run contains no test showing it prints planned changes without applying them.",
        "missing": "No direct evidence shows the deploy command's behavior when --dry-run is used.",
    }
}
_STATE = {
    **_BASE_STATE,
    "multi_part": {
        "deliverables": [
            {"id": "dry_run_flag", "description": "A --dry-run flag on the deploy CLI.", "completion_signal": "The deploy CLI accepts --dry-run and prints the planned changes without applying them."},
            {"id": "readme_docs", "description": "README documentation for the --dry-run flag.", "completion_signal": "The README has a section that explains what --dry-run does."},
        ]
    },
}
_HANDOFF = {
    "multi_part": {
        "deliverables": [
            {"id": "dry_run_flag", "evidence": "Tool call edit_file(path='cli/deploy.py') output: updated; it adds --dry-run.", "missing": "Nothing is missing."},
            {"id": "readme_docs", "evidence": "No part of the run concerns the README.", "missing": "The README section for --dry-run."},
        ]
    }
}
_CAN_SIMPLIFY_STATE = {
    **_BASE_STATE,
    "can_simplify": {
        "scope": "Change the deploy implementation without changing its command contract.",
        "preserve": "Keep all existing deploy flags and preview behavior.",
    },
}
_CAN_SIMPLIFY_HANDOFF = {
    "can_simplify": {
        "implementation": "The deploy implementation repeats the same validation in two branches. A single shared validation path keeps all flags and preview behavior.",
        "missing": "Replace the duplicate validation branches in cli/deploy.py with one shared validation path, retaining every existing flag and preview behavior.",
    }
}
_STATE_BOTH = {**_STATE, **_CAN_SIMPLIFY_STATE}
_HANDOFF_BOTH = {**_HANDOFF, **_CAN_SIMPLIFY_HANDOFF}
_INPUT_STATE = {
    **_BASE_STATE,
    "input_set_coverage": {
        "targets": [{
            "id": "incident_pages",
            "identity": "incident report pages 1 through 3",
            "scope": "all three pages in the named incident report",
            "action": "review",
            "engagement_signal": "content from each of pages 1, 2, and 3 was returned and examined",
        }]
    },
}
_INPUT_HANDOFF = {
    "input_set_coverage": {
        "targets": [{
            "id": "incident_pages",
            "evidence": "Tool call fetch_pages(start=1, end=3) succeeded; output contains the full text of pages 1, 2, and 3 from the incident report.",
            "missing": "Nothing is missing.",
        }]
    }
}
_INPUT_EXHAUSTION_STATE = {
    **_BASE_STATE,
    "input_exhaustion": {"collections": [{
        "id": "all_pages",
        "collection": "the report pages",
        "scope": "all 41 pages of the report",
        "unit": "page",
        "expected_total": 41,
        "exhaustion_condition": "The report has no pages after page 41.",
    }]},
}

_NEGATIVE_COVERAGE_REQUEST = "Inspect all cache invalidation modules for unsafe behavior."
_NEGATIVE_COVERAGE_STATE = {
    **_BASE_STATE,
    "negative_coverage": {"inspections": [{
        "id": "cache_modules",
        "target": "all cache invalidation modules",
        "inspection_signal": "Read each requested module and examine its invalidation behavior.",
    }]},
}


def _negative_coverage_handoff(**overrides: Any) -> dict[str, Any]:
    inspection: dict[str, Any] = {
        "id": "cache_modules",
        "inspection": "No source-reading or relevant test evidence appears in the recorded run.",
        "negative_conclusion": "",
        "incomplete_report": "",
        "missing": "The requested cache invalidation modules have no visible inspection evidence.",
    }
    inspection.update(overrides)
    return {"negative_coverage": {"inspections": [inspection]}}


def _guaranteed_next_actions_handoff(actions: list[dict[str, str]]) -> dict[str, Any]:
    return {"guaranteed_next_actions": {"actions": actions}}


def _guaranteed_next_action(identifier: str) -> dict[str, str]:
    return {
        "id": identifier,
        "outcome": "The requested test passes.",
        "trigger": "The test command failed on the requested function.",
        "action": "Correct the function so the test passes.",
        "necessity_basis": "The requested behavior fails and no alternative authorized route is evident.",
        "evidence": "The recorded test command fails with the expected assertion, and no later edit or successful rerun appears.",
        "missing": "The function correction and successful rerun are not shown.",
    }


def _input_exhaustion_handoff(
    visited: tuple[str, ...] = tuple(f"page-{number}" for number in range(1, 11)),
    **overrides: Any,
) -> dict[str, Any]:
    """Build one trace-backed traversal observation with replaceable boundary facts."""
    collection: dict[str, Any] = {
        "id": "all_pages",
        "evidence": "Tool calls opened and read the listed report pages in order.",
        "unit_type": "page",
        "visited_unit_ids": list(visited),
        "source_reported_total": None,
        "last_position": "page 10",
        "outstanding_continuation": "cursor page-11",
        "terminal_evidence": None,
        "failed_retrievals": [],
        "missing": "Pages 11 through 41 and a terminal boundary remain unobserved.",
        "next_step": "Continue requesting report pages after page 10.",
    }
    collection.update(overrides)
    return {"input_exhaustion": {"collections": [collection]}}
_OUTPUT_REQUEST = "Give me 25 distinct examples of useful cache invalidation strategies, and write one file per strategy."
_OUTPUT_STATE = {
    **_BASE_STATE,
    "output_count": {"obligations": [{
        "id": "cache_examples", "description": "25 distinct cache invalidation strategy examples.",
        "target_count": 25, "distinct": True, "unit": "examples", "scope": "cache invalidation strategies",
        "distinctness": "Each example describes a different strategy, not a paraphrase of another.",
        "completion_criteria": "The output shows 25 different strategies with a visible example for each.",
    }]},
}
_OUTPUT_HANDOFF = {"output_count": {"obligations": [{
    "id": "cache_examples", "entries": [
        {"id": f"example_{index}", "value": f"Cache strategy {index}: distinct technique {index}.", "distinct_key": f"strategy_{index}", "evidence": f"Final answer includes strategy {index}."}
        for index in range(1, 11)
    ], "missing": "Only ten of the requested twenty-five distinct strategies are visible; fifteen remain."}]
}}
_OUTPUT_COMPLETE_HANDOFF = {"output_count": {"obligations": [{
    "id": "cache_examples", "entries": [
        {"id": f"example_{index}", "value": f"Cache strategy {index}: distinct technique {index}.", "distinct_key": f"strategy_{index}", "evidence": f"Final answer includes strategy {index}."}
        for index in range(1, 26)
    ], "missing": "Nothing is missing."}]
}}
_CLAIMS = {
    "claims": [
        {
            "id": "readme_updated",
            "claim": {
                "identity": {"title": "README updated", "description": "The final answer says README.md was updated to document --dry-run.", "intent": None},
                "scope": {"scope": "README.md's --dry-run documentation", "qualifications": []},
                "kind": "artifact_change",
                "output": "README.md documentation for --dry-run",
                "assertions": [{"id": "doc_added", "statement": "README.md was updated to document --dry-run.", "completion_criteria": "A successful recorded edit to README.md contains an explanation of --dry-run."}],
            },
            "evidence": "Tool call edit_file(path='README.md', content='--dry-run previews a deploy') state=succeeded; output='README.md updated with that explanation'.",
            "missing": "Nothing is missing.",
        },
        {
            "id": "deploy_test_added",
            "claim": {
                "identity": {"title": "Deploy test added", "description": "The final answer says a test was added for the deploy command.", "intent": None},
                "scope": {"scope": "A test for the deploy command", "qualifications": []},
                "kind": "artifact_change",
                "output": "A deploy command test",
                "assertions": [{"id": "doc_added", "statement": "A test was added for the deploy command.", "completion_criteria": "A successful recorded edit writes a test for the deploy command."}],
            },
            "evidence": "No supporting tool call was found.",
            "missing": "No tool call shows a test file being written or edited.",
        },
    ]
}
_CLAIMS_HANDOFF = {"claims": _CLAIMS}
_COMBINED_HANDOFF = {**_HANDOFF, **_CLAIMS_HANDOFF}
_PROBLEM_ITEM = {
    "id": "format_failure",
    "kind": "problem",
    "title": "Formatter failure",
    "description": "The formatter failed while validating the requested change.",
    "scope": "Formatting for src/deploy.py",
    "qualifications": "Only the current requested change.",
    "repair": "A formatting edit was applied and the formatter was rerun.",
    "verification": "The formatter completed successfully after the edit with exit status 0.",
    "evidence": "Tool call format(src/deploy.py) failed; edit succeeded; later format(src/deploy.py) succeeded with exit status 0.",
    "missing": "Nothing is missing.",
}
_REQUEST_ITEM = {
    "id": "original_request_completion",
    "kind": "request_completion",
    "title": "Original request complete",
    "description": "Add the dry-run flag and document it in the README after resolving the formatter failure.",
    "scope": "Both the CLI flag and README explanation.",
    "qualifications": "Complete both requested outputs.",
    "repair": "After repairing the formatter failure, the CLI and README edits were completed.",
    "verification": "The run evidence shows the flag and README documentation in the final work.",
    "evidence": "Tool calls show the CLI edit and README edit succeeded after the formatter repair.",
    "missing": "Nothing is missing.",
}
_PROBLEMS_HANDOFF = {"problems_resolved": {"items": [_PROBLEM_ITEM, _REQUEST_ITEM]}}
_COMPLETION_EVIDENCE_HANDOFF = {
    "completion_evidence": {
        "items": [{
            "id": "task_completion",
            "completion_status": "complete",
            "requested_outcomes": ["Add the dry-run flag", "Document the flag in the README"],
            "completed_work": ["The CLI accepts --dry-run."],
            "unfinished_or_blocked": ["The README update is not shown."],
            "evidence": "Tool output shows the CLI edit; no README edit appears in the run.",
            "missing": "The requested README explanation is unsupported by run evidence.",
        }]
    }
}
_PHASE_STAGE = {
    "id": "research",
    "stage": "Research and compare deployment options",
    "required_result": "Compare three deployment options for the requested release.",
    "request_scope": "Three options for the requested release.",
    "output_criterion": "The run contains a comparison of three options.",
}
_PHASE_STATE = {**_BASE_STATE, "phase_progress": {"stages": [_PHASE_STAGE]}}
_PHASE_HANDOFF = {
    "phase_progress": {
        "stages": [{
            "id": "research",
            "evidence": "The run only searched for background information and made no comparison.",
            "missing": "No comparison of three deployment options is shown.",
        }]
    }
}
_REPORT_ACTION_ITEM = {
    "id": "manifest_update",
    "plan": "I will update the manifest with the new field.",
    "execution": "edit_file for manifest.json succeeded and the new field is present.",
    "final_account": "I updated the manifest with the new field.",
    "request_relevance": "The user explicitly requested the manifest update.",
    "evidence": "Earlier response named the manifest update; edit_file succeeded; final response says it was updated.",
    "missing": "Nothing remains to reconcile.",
}
_REPORT_ACTION_HANDOFF = {"report_action_alignment": {"items": [_REPORT_ACTION_ITEM]}}
_CHANGED_ASSUMPTION = {
    "id": "changed_limit",
    "original_assumption": "The endpoint accepts page_size=500.",
    "original_basis": "An early response said the endpoint permits page_size=500.",
    "later_observation": "A returned endpoint result reports a maximum of 100.",
    "affected_work": "The generated client uses 500 as its default page size.",
    "revision": "A later edit changes the default to 100, and a command result uses the new value.",
    "evidence": "The early response names 500; the endpoint result says 100; the edit and later command result show the client now uses 100.",
    "missing": "Nothing remains to reconcile.",
}
_ASSUMPTIONS_HANDOFF = {"assumptions_reconciled": {"items": [_CHANGED_ASSUMPTION]}}


class ScriptedGenerativeRunner:
    """Small runner that records every prompt, system prompt, and message list it receives, or raises when told to."""

    def __init__(self, text: str = "completed", *, error: Exception | None = None) -> None:
        self.response = TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})
        self.error = error
        self.calls: list[str] = []
        self.systems: list[str] = []
        self.messages: list[Any] = []

    def run(self, prompt: str, system: str = "", **kwargs: Any) -> TextModelResponse:
        self.calls.append(prompt)
        self.systems.append(system)
        self.messages.append(kwargs.get("messages"))
        if self.error is not None:
            raise self.error
        return self.response


class ScriptedDecisionRunner:
    """Records each decision request and answers every done-item question from scripted P(yes) values keyed by item id."""

    def __init__(self, script: Mapping[str, list[float]], *, error: Exception | None = None) -> None:
        self.script = {key: list(values) for key, values in script.items()}
        self.error = error
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        answers = {}
        for question in request.questions:
            values = self.script[question.name.split(".", 2)[-1]]
            yes = values.pop(0) if len(values) > 1 else values[0]
            answers[question.name] = _answer(question.name, yes)
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 100, "output_tokens": 10})


def _runner_class(scripted: ScriptedDecisionRunner) -> type:
    # Stands in for DecisionModelHelper: construction returns the scripted runner, while score_noul stays real.
    class ScriptedRunnerClass:
        score_noul = staticmethod(DecisionModelHelper.score_noul)
        noul_passes = staticmethod(DecisionModelHelper.noul_passes)

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedDecisionRunner:  # type: ignore[misc]
            return scripted

    return ScriptedRunnerClass


def _answer(name: str, yes: float) -> JevAnswer:
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if yes >= 0.5 else "false", probabilities={"true": yes, "false": 1.0 - yes}, noul=yes)


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {"name": "jev", "system_prompt": "Work carefully.", "provider": "openai", "model_name": "gpt-4.1-mini"}
    values.update(overrides)
    return JevAgentSettings(**values)


def _jev(
    done: tuple[Any, ...] = (JevDoneCheck.MULTI_PART,),
    *,
    max_continuations: int = JEV_DONE_MAX_CONTINUATIONS,
    **settings: Any,
) -> JevAgent:
    continual = JevContinualSettings(checks=done, max_continuations=max_continuations)
    return JevAgent(_settings(**settings), JevRuntimeSettings(decision=DecisionModelConfig(api_key="test-key"), continual=continual))


def _sentences(text: str) -> int:
    return len(_SENTENCE_END.findall(text.strip()))


def _descriptions(model: type[BaseModel]) -> dict[str, str]:
    return {name: str(info.description) for name, info in model.model_fields.items()}


def _prompt_sections(prompt: Prompt) -> dict[str, str]:
    text = Prompts().get(prompt)
    sections = re.split(r"^# (\w+)\s*$", text, flags=re.MULTILINE)[1:]
    return {sections[index]: sections[index + 1].strip() for index in range(0, len(sections), 2)}


class JevDoneRecordTests(unittest.TestCase):
    """Pin the lib records and structured-reply payloads the review moved out of vidbyte/agents/jev."""

    def test_records_and_enums_live_in_lib(self) -> None:
        # [Review 4116720422] dataclasses and enums belong in vidbyte/lib, per AGENTS.md.
        for cls in (JevDeliverable, JevMultiPart, JevCanSimplify, JevCanSimplifyEvidence, JevExpertDetail, JevExpertDepthDeliverable, JevExpertDepth, JevExpertDetailEvidence, JevExpertDepthEvidence, JevInputTarget, JevInputSetCoverage, JevOutputCountObligation, JevOutputCount, JevOutputCountEntry, JevOutputCountEvidenceItem, JevOutputCountEvidence, JevOutputExtentItem, JevOutputExtent, JevOutputExtentEvidenceItem, JevOutputExtentEvidence, JevNegativeCoverageTarget, JevNegativeCoverage, JevNegativeCoverageEvidenceItem, JevNegativeCoverageEvidence, JevReportActionAlignmentItem, JevReportActionAlignment, JevRequiredAction, JevRequiredActionEvidence, JevRequiredActions, JevRequiredActionsEvidence, JevCumulativeObligation, JevCumulativeObligationEvidence, JevCumulativeObligations, JevCumulativeObligationsEvidence, JevCumulativeUserTurnEvidence, JevDiscoveredItem, JevDiscoveredItemBatch, JevDiscoveredItemEvidence, JevFaithfulScopeEvidence, JevRunStateRecord, JevDoneResult, JevRunStatePayload, JevMultiPartPayload, JevCanSimplifyPayload, JevCanSimplifyEvidencePayload, JevExpertDepthPayload, JevExpertDepthEvidencePayload):
            self.assertEqual(cls.__module__, "vidbyte.lib.dataclasses.jev")
        for cls in (JevObjection, JevReviewRecord, JevObjectionEvidence, JevSelfReviewEvidence):
            self.assertEqual(cls.__module__, "vidbyte.lib.dataclasses.jev")
        self.assertEqual(JevDoneCheck.__module__, "vidbyte.lib.enums.jev")
        self.assertFalse((_REPOSITORY_ROOT / "vidbyte/agents/jev/run_state.py").exists())
        self.assertFalse((_REPOSITORY_ROOT / "vidbyte/agents/jev/builders.py").exists())

    def test_every_structured_output_field_has_a_four_to_six_sentence_description(self) -> None:
        # [Review 4116725548] every field carries a pre-defined 4-6 sentence description used in the structured output.
        models = (JevRunStatePayload, JevMultiPartPayload, JevCanSimplifyPayload, JevDeliverablePayload, JevMultiPartEvidencePayload, JevCanSimplifyEvidencePayload, JevDeliverableEvidencePayload, JevExpertDepthPayload, JevExpertDepthDeliverablePayload, JevExpertDetailPayload, JevExpertDepthEvidencePayload, JevExpertDetailEvidencePayload, JevInputSetCoveragePayload, JevInputTargetPayload, JevInputSetCoverageEvidencePayload, JevInputTargetEvidencePayload, JevOutputCountPayload, JevOutputCountObligationPayload, JevOutputCountEvidencePayload, JevOutputCountEvidencePayloadItem, JevOutputCountEntryPayload, JevOutputExtentPayload, JevOutputExtentItemPayload, JevOutputExtentEvidencePayload, JevOutputExtentEvidenceItemPayload, JevNegativeCoveragePayload, JevNegativeCoverageTargetPayload, JevNegativeCoverageEvidencePayload, JevNegativeCoverageEvidenceItemPayload, JevReportActionAlignmentEvidencePayload, JevReportActionAlignmentEvidenceSectionPayload, JevAssumptionEvidencePayload, JevAssumptionsReconciledPayload, JevClaimIdentityPayload, JevClaimScopePayload, JevClaimAssertionPayload, JevClaimContextPayload, JevClaimEvidencePayload, JevClaimsEvidencePayload, JevProblemEvidencePayload, JevProblemsResolvedEvidencePayload, JevPhaseStagePayload, JevPhaseProgressPayload, JevPhaseStageEvidencePayload, JevPhaseProgressEvidencePayload, JevCumulativeObligationPayload, JevCumulativeObligationsPayload, JevCumulativeObligationEvidenceEntryPayload, JevCumulativeUserTurnEvidenceEntryPayload, JevCumulativeObligationEvidencePayload, JevDiscoveredItemPayload, JevDiscoveredItemBatchEntryPayload, JevDiscoveredItemBatchPayload, JevFaithfulScopeEvidencePayload, JevObjectionPayload, JevReviewPayload, JevObjectionEvidencePayload, JevSelfReviewEvidencePayload)
        for model in models:
            for name, description in _descriptions(model).items():
                with self.subTest(model=model.__name__, field=name):
                    self.assertIn(_sentences(description), range(4, 7))
        for model in (JevClaimIdentityPayload, JevClaimScopePayload, JevClaimAssertionPayload, JevClaimContextPayload, JevClaimEvidencePayload):
            for name, description in _descriptions(model).items():
                with self.subTest(model=model.__name__, field=name):
                    self.assertEqual(_sentences(description), 5)
        for section in (JevMultiPartPayload, JevCanSimplifyPayload, JevMultiPartEvidencePayload, JevCanSimplifyEvidencePayload, JevExpertDepthPayload, JevExpertDepthEvidencePayload, JevInputSetCoveragePayload, JevInputSetCoverageEvidencePayload, JevOutputCountPayload, JevOutputCountEvidencePayload, JevOutputExtentPayload, JevOutputExtentEvidencePayload, JevNegativeCoveragePayload, JevNegativeCoverageEvidencePayload, JevReportActionAlignmentEvidenceSectionPayload, JevAssumptionsReconciledPayload, JevClaimsEvidencePayload, JevProblemsResolvedEvidencePayload, JevPhaseProgressPayload, JevPhaseProgressEvidencePayload, JevCumulativeObligationsPayload, JevCumulativeObligationEvidencePayload, JevDiscoveredItemBatchPayload, JevFaithfulScopeEvidencePayload, JevSelfReviewEvidencePayload):
            with self.subTest(section=section.__name__):
                self.assertIn(_sentences(section.SECTION), range(4, 7))

    def test_multi_part_is_its_own_dataclass_and_payload(self) -> None:
        # [Review 4116727218] the multi-part section is a separate dataclass, not a nested dict inside the state.
        self.assertTrue(issubclass(JevMultiPartPayload, JevSectionPayload))
        self.assertNotIn("multi_part", JevRunStatePayload.model_fields)
        record = JevRunStateRecord("goal", "objective", "mission", hard_part="hard", multi_part=JevMultiPart((JevDeliverable("a", "b", "c"),)))
        self.assertIsInstance(record.multi_part, JevMultiPart)

    def test_can_simplify_records_are_typed_and_appended_after_legacy_positions(self) -> None:
        request_state = JevCanSimplify("one implementation", "keep its public behavior")
        handoff = JevCanSimplifyEvidence("reviewed implementation", "No change is needed.")
        usage_marker = object()
        run_state = JevRunStateRecord("goal", "objective", "mission", (), None, None, usage_marker, hard_part="hard", can_simplify=request_state)
        handoff_record = JevHandoffRecord(None, None, None, None, usage_marker, can_simplify=handoff)
        self.assertIs(run_state.usage, usage_marker)
        self.assertIs(run_state.can_simplify, request_state)
        self.assertIs(handoff_record.usage, usage_marker)
        self.assertIs(handoff_record.can_simplify, handoff)

    def test_hard_part_is_required_without_shifting_prior_positional_fields(self) -> None:
        with self.assertRaises(TypeError):
            JevRunStateRecord("goal", "objective", "mission")
        record = JevRunStateRecord("goal", "objective", "mission", hard_part="the hard part")
        self.assertEqual((record.goal, record.objective, record.mission, record.hard_part, record.what_not_to_do), ("goal", "objective", "mission", "the hard part", ()))

    def test_records_hold_no_parsing_or_schema_code(self) -> None:
        # [Review 4116752796] from_payload and output_schema do not belong on the record dataclasses.
        for cls in (JevDeliverable, JevMultiPart, JevRunStateRecord):
            for name in ("from_payload", "output_schema", "to_payload"):
                self.assertFalse(hasattr(cls, name), f"{cls.__name__}.{name}")

    def test_records_reject_bad_ids_and_duplicates(self) -> None:
        for bad in ("Readme", "1_readme", "read me", ""):
            with self.subTest(bad=bad), self.assertRaises(ConfigurationError):
                JevDeliverable(bad, "description", "signal")
        with self.assertRaises(ConfigurationError):
            JevMultiPart((JevDeliverable("a", "b", "c"), JevDeliverable("a", "d", "e")))
        with self.assertRaises(ConfigurationError):
            JevRunStateRecord("goal", " ", "mission", hard_part="hard")

    def test_output_count_records_reject_invalid_targets_and_duplicate_ids(self) -> None:
        obligation = JevOutputCountObligation("examples", "Requested examples", 25, True, "examples", "cache strategies", "distinct strategies", "Show 25 distinct strategies.")
        self.assertEqual(JevOutputCount((obligation,)).ids(), ("examples",))
        first = JevOutputCountEntry("first", "same result", "same-key", "final answer line")
        duplicate = JevOutputCountEntry("second", "same result", "same-key", "final answer line")
        evidence = JevOutputCountEvidenceItem("examples", (first, duplicate), "Only one distinct item.")
        self.assertEqual(evidence.entries, (first, duplicate))
        self.assertEqual(evidence.entries[0].evidence, "final answer line")
        with self.assertRaises(ConfigurationError):
            JevOutputCountObligation("bad", "bad target", 0, True, "items", "scope", "distinct", "criterion")
        with self.assertRaises(ConfigurationError):
            JevOutputCount((obligation, obligation))

    def test_output_extent_records_preserve_comparator_and_reject_ambiguous_values(self) -> None:
        item = JevOutputExtentItem("answer_length", "the final answer", 25, JevOutputExtentUnit.WORDS, JevOutputExtentComparator.MINIMUM)
        state = JevOutputExtent((item,))
        self.assertEqual(state.ids(), ("answer_length",))
        self.assertEqual(JevRunStateRecord("goal", "objective", "mission", hard_part="hard", output_extent=state).output_extent, state)
        evidence = JevOutputExtentEvidence((JevOutputExtentEvidenceItem("answer_length", "final answer text", "no gap"),))
        self.assertEqual(JevHandoffRecord(output_extent=evidence).output_extent, evidence)
        for invalid in ((0, "words", "minimum"), (3, "tokens", "minimum"), (3, "words", "at_least")):
            with self.subTest(invalid=invalid), self.assertRaises(ConfigurationError):
                JevOutputExtentItem(
                    "answer_length",
                    "the final answer",
                    invalid[0],
                    JevOutputExtentUnit.WORDS if invalid[1] == "words" else invalid[1],
                    JevOutputExtentComparator.MINIMUM if invalid[2] == "minimum" else invalid[2],
                )

    def test_required_action_records_preserve_only_explicit_prior_dependencies(self) -> None:
        collect = JevRequiredAction("collect", "Collect each named input.", "All named inputs are recorded.")
        classify = JevRequiredAction("classify", "Classify the collected inputs.", "Each input has a classification.", ("collect",))
        state = JevRequiredActions((collect, classify))
        self.assertEqual(state.ids(), ("collect", "classify"))
        self.assertEqual(state.actions[1].predecessors, ("collect",))
        self.assertEqual(JevRunStateRecord("goal", "objective", "mission", hard_part="hard", required_actions=state).required_actions, state)
        evidence = JevRequiredActionEvidence("collect", "The inputs were returned.", (0,), 0, "Nothing is missing.")
        self.assertEqual(JevHandoffRecord(required_actions=JevRequiredActionsEvidence((evidence,))).required_actions.ids(), ("collect",))
        with self.assertRaises(ConfigurationError):
            JevRequiredActions((classify, collect))
        with self.assertRaises(ConfigurationError):
            JevRequiredActions((collect, JevRequiredAction("classify", "Classify inputs.", "Every input has a class.", ("unknown",))))
        with self.assertRaises(ConfigurationError):
            JevRequiredActionEvidence("collect", "evidence", (1, 0), 0, "missing")

    def test_report_action_alignment_records_preserve_candidates_and_reject_duplicates(self) -> None:
        item = JevReportActionAlignmentItem(
            "manifest_update",
            "I will update the manifest.",
            "edit_file succeeded for manifest.json.",
            "I updated the manifest.",
            "The user requested the manifest update.",
            "The earlier response, edit result, and final account are visible.",
            "Nothing remains to reconcile.",
        )
        alignment = JevReportActionAlignment((item,))
        self.assertEqual(alignment.ids(), ("manifest_update",))
        self.assertEqual(JevHandoffRecord(report_action_alignment=alignment).report_action_alignment, alignment)
        with self.assertRaises(ConfigurationError):
            JevReportActionAlignment((item, item))

    def test_changed_assumption_records_preserve_candidates_and_reject_duplicates(self) -> None:
        item = JevAssumptionEvidence(**_CHANGED_ASSUMPTION)
        evidence = JevAssumptionsReconciledEvidence((item,))
        self.assertEqual(evidence.ids(), ("changed_limit",))
        self.assertEqual(JevHandoffRecord(assumptions_reconciled=evidence).assumptions_reconciled, evidence)
        self.assertEqual(JevAssumptionsReconciledEvidence().ids(), ())
        with self.assertRaises(ConfigurationError):
            JevAssumptionsReconciledEvidence((item, item))

    def test_claim_evidence_requires_unique_claim_ids_and_preserves_an_empty_list(self) -> None:
        context = JevClaimContext(
            identity=JevClaimIdentity("README updated", "README.md documents --dry-run."),
            scope=JevClaimScope("README.md's --dry-run documentation"),
            kind=JevClaimKind.ARTIFACT_CHANGE,
            output="README.md section",
            assertions=(JevClaimAssertion("docs_added", "README.md documents --dry-run.", "The recorded README content explains --dry-run."),),
        )
        claim = JevClaimEvidence("readme_updated", context, "edit_file succeeded for README.md", "Nothing is missing.")
        self.assertEqual(JevClaimsEvidence((claim,)).ids(), ("readme_updated",))
        self.assertEqual(JevClaimsEvidence((claim,)).assertion_ids(), ("readme_updated.docs_added",))
        self.assertEqual(JevClaimsEvidence().ids(), ())
        with self.assertRaises(ConfigurationError):
            JevClaimsEvidence((claim, claim))
        with self.assertRaises(ConfigurationError):
            JevClaimEvidence("Readme", "claim", "evidence", "missing")
        with self.assertRaises(ConfigurationError):
            JevClaimContext(context.identity, context.scope, context.kind, context.output, (context.assertions[0], context.assertions[0]))
        with self.assertRaises(ConfigurationError):
            JevClaimAssertion("bad.id", "statement", "criterion")

    def test_problem_evidence_requires_exactly_one_reserved_request_item(self) -> None:
        problem = JevProblemResolutionItem(**{**_PROBLEM_ITEM, "kind": JevProblemCheckItemType.PROBLEM})
        completion = JevProblemResolutionItem(**{**_REQUEST_ITEM, "kind": JevProblemCheckItemType.REQUEST_COMPLETION})
        record = JevProblemsResolvedEvidence((problem, completion))
        self.assertEqual(record.problem_ids(), ("format_failure",))
        self.assertEqual(record.ids(), ("format_failure", "original_request_completion"))
        with self.assertRaises(ConfigurationError):
            JevProblemsResolvedEvidence((problem,))
        with self.assertRaises(ConfigurationError):
            JevProblemsResolvedEvidence((problem, completion, completion))
        with self.assertRaises(ConfigurationError):
            JevProblemsResolvedEvidence((JevProblemResolutionItem(**{**_PROBLEM_ITEM, "id": "original_request_completion", "kind": JevProblemCheckItemType.PROBLEM}), completion))


class JevScopeCoverageMergeTests(unittest.IsolatedAsyncioTestCase):
    """Pin that scope breadth review receives the latest run state after motivating-case recall."""

    async def test_scope_breadth_review_uses_the_accepted_recall_payload(self) -> None:
        request = "Update all North, South, and West adapters."
        agent = _jev(done=(JevDoneCheck.MOTIVATING_CASE, JevDoneCheck.SCOPE_COVERAGE))
        assert agent.run_state is not None
        run_state = agent.run_state

        def payload(request_quote: str, requested_change: str) -> BaseModel:
            return run_state.payload(
                goal="Update every adapter.",
                objective="All requested adapters show the change.",
                mission="Change only the requested adapters.",
                hard_part="Update every requested adapter.",
                what_not_to_do=[],
                motivating_case={"ordinary_flow": "all adapters work", "testing_restriction_quote": "", "scenarios": []},
                scope_coverage={"dimensions": [{
                    "id": "adapter_set",
                    "request_quote": request_quote,
                    "requested_change": requested_change,
                    "unit_noun": "adapter",
                    "membership_rule": "one named adapter",
                    "breadth": "one_example",
                    "universe": "named_in_request",
                    "named_units": ["North", "South", "West"],
                    "excluded_units": [],
                }]},
            )

        initial = payload("North, South, and West", "change the North adapter")
        revised = payload("all North, South, and West adapters", "change every named adapter")
        generated = AsyncMock(side_effect=(SimpleNamespace(structured=initial), SimpleNamespace(structured=revised)))
        decision_requests: list[JevDecisionRequest] = []
        responses = [
            SimpleNamespace(answers={"motivating_case.recall": SimpleNamespace(probabilities={"true": 0.9})}),
            SimpleNamespace(answers={"scope_coverage.breadth.adapter_set": SimpleNamespace(probabilities={"every_member": 0.2, "named_list": 0.55})}),
        ]

        async def decide(_helper: object, decision_request: JevDecisionRequest) -> SimpleNamespace:
            decision_requests.append(decision_request)
            return responses.pop(0)

        with (
            patch.object(run_state, "arun", new=generated),
            patch("vidbyte.agents.jev.done.run_state.DecisionModelHelper.arun", new=decide),
        ):
            await run_state.begin(request)

        assert run_state.record is not None
        assert run_state.record.scope_coverage is not None
        assert run_state.record.motivating_case is not None
        self.assertEqual(generated.await_count, 2)
        self.assertEqual(len(decision_requests), 2)
        self.assertEqual(decision_requests[1].state["dimensions"]["adapter_set"]["request_quote"], "all North, South, and West adapters")
        self.assertEqual(run_state.record.scope_coverage.dimensions[0].requested_change, "change every named adapter")
        self.assertIs(run_state.record.scope_coverage.dimensions[0].breadth, JevScopeBreadth.NAMED_LIST)
        self.assertTrue(run_state.record.scope_coverage.dimensions[0].breadth_upgraded)
        self.assertTrue(run_state.record.motivating_case.builder_disagreement)
        rendered = json.loads(run_state.rendered)
        self.assertEqual(rendered["scope_coverage"]["dimensions"][0]["request_quote"], "all North, South, and West adapters")
        self.assertEqual(rendered["scope_coverage"]["dimensions"][0]["breadth"], "named_list")


class JevScopeCoverageResultTests(unittest.TestCase):
    """Pin per-member questions and automatic gaps for work and workspace coverage."""

    def test_missing_member_work_and_inventory_are_continuation_gaps(self) -> None:
        agent = _jev(done=(JevDoneCheck.SCOPE_COVERAGE,))
        assert agent.run_state is not None
        run_state = agent.run_state
        run_state.record = SimpleNamespace(scope_coverage=object())
        dimension = SimpleNamespace(
            request_quote="all adapters",
            requested_change="enable the flag",
            unit_noun="adapter",
            membership_rule="one named adapter",
        )
        units = (
            SimpleNamespace(unit="North", work="The flag is enabled for North."),
            SimpleNamespace(unit="South", work=""),
        )
        evidence = SimpleNamespace(
            question_items=lambda _state: tuple((f"adapters.{index}", dimension, unit) for index, unit in enumerate(units)),
            inventory_gaps=lambda _state: ("adapters",),
        )
        handoff = SimpleNamespace(scope_coverage=evidence)

        section, questions = run_state._section(JevDoneCheck.SCOPE_COVERAGE, handoff)
        question = JevDoneRegistry.question(JevDoneCheck.SCOPE_COVERAGE)
        self.assertEqual(tuple(item.name for item in questions), (question.name("adapters.0"),))
        self.assertEqual(set(section[JEV_DONE_SCOPE_COVERAGE_FIELD]), {"adapters.0", "adapters.1"})

        decision = SimpleNamespace(answers={question.name("adapters.0"): _answer(question.name("adapters.0"), 0.9)}, usage={})
        result = run_state._scope_coverage(handoff, decision)
        self.assertTrue(result.available)
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("adapters.1", "adapters.inventory"))


class JevDoneSchemaTests(unittest.TestCase):
    """Pin that one JevRunState and one JevHandoff compose their schemas from the enabled checks."""

    def test_run_state_schema_contains_only_checks_with_request_derived_items(self) -> None:
        # CLAIMS are statements written after work, so the run-state model must not predict them from the request.
        self.assertEqual(set(JevRunState.schema(()).model_fields), {"goal", "objective", "mission", "hard_part", "what_not_to_do"})
        schema = JevRunState.schema((JevDoneCheck.MULTI_PART,))
        self.assertTrue(issubclass(schema, JevRunStatePayload))
        self.assertEqual(schema.model_fields["multi_part"].description, JevMultiPartPayload.SECTION)
        simplify_schema = JevRunState.schema((JevDoneCheck.CAN_SIMPLIFY,))
        self.assertEqual(simplify_schema.model_fields[JevDoneCheck.CAN_SIMPLIFY.value].description, JevCanSimplifyPayload.SECTION)
        both = JevRunState.schema((JevDoneCheck.MULTI_PART, JevDoneCheck.CAN_SIMPLIFY))
        self.assertEqual(set(both.model_fields), {"goal", "objective", "mission", "hard_part", "what_not_to_do", "multi_part", "can_simplify"})
        self.assertEqual(set(JevRunState.schema((JevDoneCheck.CLAIMS, JevDoneCheck.PROBLEMS_RESOLVED)).model_fields), {"goal", "objective", "mission", "hard_part", "what_not_to_do"})
        motivating_schema = JevRunState.schema((JevDoneCheck.MOTIVATING_CASE,))
        self.assertEqual(motivating_schema.model_fields["motivating_case"].description, JevMotivatingCasePayload.SECTION)
        scope_schema = JevRunState.schema((JevDoneCheck.SCOPE_COVERAGE,))
        self.assertEqual(scope_schema.model_fields["scope_coverage"].description, JevScopeCoveragePayload.SECTION)
        phase_schema = JevRunState.schema((JevDoneCheck.PHASE_PROGRESS,))
        self.assertEqual(phase_schema.model_fields[JEV_DONE_PHASE_PROGRESS_FIELD].description, JevPhaseProgressPayload.SECTION)
        input_schema = JevRunState.schema((JevDoneCheck.INPUT_SET_COVERAGE,))
        self.assertEqual(input_schema.model_fields[JEV_DONE_INPUT_SET_COVERAGE_FIELD].description, JevInputSetCoveragePayload.SECTION)
        output_schema = JevRunState.schema((JevDoneCheck.OUTPUT_COUNT,))
        self.assertEqual(output_schema.model_fields["output_count"].description, JevOutputCountPayload.SECTION)
        extent_schema = JevRunState.schema((JevDoneCheck.OUTPUT_EXTENT,))
        self.assertEqual(extent_schema.model_fields["output_extent"].description, JevOutputExtentPayload.SECTION)
        negative_schema = JevRunState.schema((JevDoneCheck.NEGATIVE_COVERAGE,))
        self.assertEqual(negative_schema.model_fields[JEV_DONE_NEGATIVE_COVERAGE_FIELD].description, JevNegativeCoveragePayload.SECTION)
        required_schema = JevRunState.schema((JevDoneCheck.REQUIRED_ACTIONS,))
        self.assertEqual(required_schema.model_fields[JEV_DONE_REQUIRED_ACTIONS_FIELD].description, JevRequiredActionsPayload.SECTION)
        cumulative_schema = JevRunState.schema((JevDoneCheck.CUMULATIVE_OBLIGATIONS,))
        self.assertEqual(cumulative_schema.model_fields["cumulative_obligations"].description, JevCumulativeObligationsPayload.SECTION)
        expert_schema = JevRunState.schema((JevDoneCheck.EXPERT_DEPTH,))
        self.assertEqual(expert_schema.model_fields["expert_depth"].description, JevExpertDepthPayload.SECTION)
        self.assertNotIn("discovered_item_coverage", JevRunState.schema(tuple(JevDoneCheck)).model_fields)
        completion_schema = JevRunState.schema((JevDoneCheck.COMPLETION_EVIDENCE,))
        self.assertEqual(set(completion_schema.model_fields), {"goal", "objective", "mission", "hard_part", "what_not_to_do"})
        self.assertNotIn(JEV_DONE_REQUIRED_ACTIONS_FIELD, JevRunState.schema((JevDoneCheck.CLAIMS,)).model_fields)
        self.assertEqual(set(JevRunState._SECTIONS), {JevDoneCheck.MULTI_PART, JevDoneCheck.CAN_SIMPLIFY, JevDoneCheck.MOTIVATING_CASE, JevDoneCheck.SCOPE_COVERAGE, JevDoneCheck.TARGET_OUTCOME, JevDoneCheck.PHASE_PROGRESS, JevDoneCheck.INPUT_SET_COVERAGE, JevDoneCheck.OUTPUT_COUNT, JevDoneCheck.OUTPUT_EXTENT, JevDoneCheck.INPUT_EXHAUSTION, JevDoneCheck.NEGATIVE_COVERAGE, JevDoneCheck.REQUIRED_ACTIONS, JevDoneCheck.CUMULATIVE_OBLIGATIONS, JevDoneCheck.EXPERT_DEPTH, JevDoneCheck.REQUIRED_SEQUENCE})
        request_derived_fields = {"goal", "objective", "mission", "hard_part", "what_not_to_do", "multi_part", "can_simplify", "target_outcome", "motivating_case", "scope_coverage", JEV_DONE_PHASE_PROGRESS_FIELD, JEV_DONE_INPUT_SET_COVERAGE_FIELD, "output_count", "output_extent", "input_exhaustion", JEV_DONE_NEGATIVE_COVERAGE_FIELD, JEV_DONE_REQUIRED_ACTIONS_FIELD, "cumulative_obligations", "expert_depth", "required_sequence"}
        self.assertEqual(set(JevRunState.schema(tuple(JevDoneCheck)).model_fields), request_derived_fields)

    def test_faithful_scope_uses_the_central_hard_part_and_handoff_only_evidence(self) -> None:
        schema = JevRunState.schema((JevDoneCheck.FAITHFUL_SCOPE,))
        self.assertIn(JEV_DONE_HARD_PART_FIELD, schema.model_fields)
        self.assertTrue(schema.model_fields[JEV_DONE_HARD_PART_FIELD].is_required())
        self.assertNotIn(JevDoneCheck.FAITHFUL_SCOPE.value, schema.model_fields)
        handoff = JevHandoff.schema((JevDoneCheck.FAITHFUL_SCOPE,))
        self.assertEqual(handoff.model_fields[JevDoneCheck.FAITHFUL_SCOPE.value].annotation, JevFaithfulScopeEvidencePayload)
        self.assertNotIn(JevDoneCheck.FAITHFUL_SCOPE, JevRunState._SECTIONS)

    def test_handoff_schema_has_a_section_for_every_enabled_check(self) -> None:
        # Request-derived deliverables and post-run-derived claims both need evidence sections in the handoff.
        self.assertEqual(JevHandoff.schema(()).model_fields, {})
        schema = JevHandoff.schema((JevDoneCheck.MULTI_PART,))
        self.assertTrue(issubclass(schema, JevHandoffPayload))
        self.assertEqual(schema.model_fields["multi_part"].description, JevMultiPartEvidencePayload.SECTION)
        simplify_schema = JevHandoff.schema((JevDoneCheck.CAN_SIMPLIFY,))
        self.assertEqual(simplify_schema.model_fields[JevDoneCheck.CAN_SIMPLIFY.value].description, JevCanSimplifyEvidencePayload.SECTION)
        self.assertEqual(set(JevHandoff.schema((JevDoneCheck.MULTI_PART, JevDoneCheck.CAN_SIMPLIFY)).model_fields), {"multi_part", "can_simplify"})
        self.assertEqual(set(JevDeliverableEvidencePayload.model_fields), {"id", "evidence", "missing"})
        claim_schema = JevHandoff.schema((JevDoneCheck.CLAIMS,))
        self.assertEqual(claim_schema.model_fields["claims"].description, JevClaimsEvidencePayload.SECTION)
        problem_schema = JevHandoff.schema((JevDoneCheck.PROBLEMS_RESOLVED,))
        self.assertEqual(problem_schema.model_fields[JEV_DONE_PROBLEMS_RESOLVED_FIELD].description, JevProblemsResolvedEvidencePayload.SECTION)
        scope_schema = JevHandoff.schema((JevDoneCheck.SCOPE_COVERAGE,))
        self.assertEqual(scope_schema.model_fields["scope_coverage"].description, JevScopeCoverageEvidencePayload.SECTION)
        completion_schema = JevHandoff.schema((JevDoneCheck.COMPLETION_EVIDENCE,))
        self.assertEqual(completion_schema.model_fields[JEV_DONE_COMPLETION_EVIDENCE_FIELD].description, JevCompletionEvidenceSectionPayload.SECTION)
        phase_schema = JevHandoff.schema((JevDoneCheck.PHASE_PROGRESS,))
        self.assertEqual(phase_schema.model_fields[JEV_DONE_PHASE_PROGRESS_FIELD].description, JevPhaseProgressEvidencePayload.SECTION)
        input_schema = JevHandoff.schema((JevDoneCheck.INPUT_SET_COVERAGE,))
        self.assertEqual(input_schema.model_fields[JEV_DONE_INPUT_SET_COVERAGE_FIELD].description, JevInputSetCoverageEvidencePayload.SECTION)
        output_schema = JevHandoff.schema((JevDoneCheck.OUTPUT_COUNT,))
        self.assertEqual(output_schema.model_fields["output_count"].description, JevOutputCountEvidencePayload.SECTION)
        extent_schema = JevHandoff.schema((JevDoneCheck.OUTPUT_EXTENT,))
        self.assertEqual(extent_schema.model_fields["output_extent"].description, JevOutputExtentEvidencePayload.SECTION)
        negative_schema = JevHandoff.schema((JevDoneCheck.NEGATIVE_COVERAGE,))
        self.assertEqual(negative_schema.model_fields[JEV_DONE_NEGATIVE_COVERAGE_FIELD].description, JevNegativeCoverageEvidencePayload.SECTION)
        alignment_schema = JevHandoff.schema((JevDoneCheck.REPORT_ACTION_ALIGNMENT,))
        self.assertEqual(alignment_schema.model_fields[JEV_DONE_REPORT_ACTION_ALIGNMENT_FIELD].description, JevReportActionAlignmentEvidenceSectionPayload.SECTION)
        self.assertNotIn(JEV_DONE_REPORT_ACTION_ALIGNMENT_FIELD, JevRunState.schema(tuple(JevDoneCheck)).model_fields)
        assumptions_schema = JevHandoff.schema((JevDoneCheck.ASSUMPTIONS_RECONCILED,))
        self.assertEqual(assumptions_schema.model_fields[JEV_DONE_ASSUMPTIONS_RECONCILED_FIELD].description, JevAssumptionsReconciledPayload.SECTION)
        self.assertNotIn(JEV_DONE_ASSUMPTIONS_RECONCILED_FIELD, JevRunState.schema(tuple(JevDoneCheck)).model_fields)
        required_schema = JevHandoff.schema((JevDoneCheck.REQUIRED_ACTIONS,))
        self.assertEqual(required_schema.model_fields[JEV_DONE_REQUIRED_ACTIONS_FIELD].description, JevRequiredActionsEvidencePayload.SECTION)
        discovered_schema = JevHandoff.schema((JevDoneCheck.DISCOVERED_ITEM_COVERAGE,))
        self.assertEqual(discovered_schema.model_fields["discovered_item_coverage"].description, JevDiscoveredItemBatchPayload.SECTION)
        expert_schema = JevHandoff.schema((JevDoneCheck.EXPERT_DEPTH,))
        self.assertEqual(expert_schema.model_fields["expert_depth"].description, JevExpertDepthEvidencePayload.SECTION)
        review_schema = JevHandoff.schema((JevDoneCheck.SELF_REVIEW,))
        self.assertEqual(review_schema.model_fields["self_review"].annotation, JevSelfReviewEvidencePayload)
        self.assertNotIn(JevDoneCheck.SELF_REVIEW.value, JevRunState.schema((JevDoneCheck.SELF_REVIEW,)).model_fields)
        self.assertEqual(set(JevProblemEvidencePayload.model_fields), {"id", "kind", "title", "description", "scope", "qualifications", "repair", "verification", "evidence", "missing"})
        self.assertNotIn("claims", JevRunState.schema(tuple(JevDoneCheck)).model_fields)
        self.assertEqual(set(JevHandoff._SECTIONS), set(JevDoneCheck))

    def test_agents_are_built_once_in_the_jev_agent_constructor(self) -> None:
        agent = _jev()
        assert agent.run_state is not None
        self.assertIsInstance(agent.run_state, BaseAgent)
        self.assertIsInstance(agent.run_state.handoff_writer, JevHandoff)
        self.assertEqual(agent.run_state.tools.names(), agent.run_state.handoff_writer.tools.names())
        self.assertIsNone(_jev(done=()).run_state)

    def test_reviewer_is_built_only_for_self_review_and_uses_its_limits(self) -> None:
        continual = JevContinualSettings(checks=(JevDoneCheck.SELF_REVIEW,), review_max_iterations=2, review_max_tokens=7_000)
        agent = JevAgent(_settings(), JevRuntimeSettings(continual=continual))
        assert agent.run_state is not None and agent.run_state.reviewer is not None
        reviewer = agent.run_state.reviewer
        self.assertEqual((reviewer.agent_loop_settings.max_iterations, reviewer.agent_loop_settings.max_tokens), (2, 7_000))
        self.assertIsNone(_jev().run_state.reviewer)

    def test_the_continuation_is_a_jev_continuation_subclass_built_once(self) -> None:
        # [Review 4117849112] the runtime calls a JevContinuation subclass instead of holding continuation logic.
        agent = _jev()
        self.assertIsInstance(agent.continuation, JevDoneContinuation)
        self.assertIsInstance(agent.continuation, JevContinuation)
        assert agent.continuation is not None
        self.assertIs(agent.continuation.run_state, agent.run_state)
        self.assertIsNone(_jev(done=()).continuation)

    def test_done_checks_are_runtime_settings_validated_by_the_registry(self) -> None:
        # The #469 split: a setting that configures Jev's own decisions belongs on JevRuntimeSettings.
        self.assertEqual(JevContinualSettings(checks=("multi_part",)).checks, (JevDoneCheck.MULTI_PART,))
        self.assertNotIn("done", JevAgentSettings.__dataclass_fields__)
        for bad in ("multi_part", ("multi_part", "multi_part"), ("everything",), 3):
            with self.subTest(bad=bad), self.assertRaises(ConfigurationError):
                JevContinualSettings(checks=bad)
        with self.assertRaises(ConfigurationError):
            JevRuntimeSettings(continual=(JevDoneCheck.MULTI_PART,))  # type: ignore[arg-type]

    def test_continual_settings_expose_the_continuation_limits(self) -> None:
        # [Review 4117820116] the settings key is "continual", and the user sets the continuation and token limits.
        self.assertIn("continual", JevRuntimeSettings.__dataclass_fields__)
        self.assertNotIn("done", JevRuntimeSettings.__dataclass_fields__)
        defaults = JevContinualSettings()
        self.assertEqual((defaults.checks, defaults.max_continuations), ((), JEV_DONE_MAX_CONTINUATIONS))
        continual = JevContinualSettings(checks=(JevDoneCheck.MULTI_PART,), max_continuations=0, run_state_max_iterations=3, run_state_max_tokens=5_000, handoff_max_iterations=4, handoff_max_tokens=9_000)
        agent = JevAgent(_settings(), JevRuntimeSettings(continual=continual))
        assert agent.run_state is not None
        assert agent.continuation is not None
        self.assertEqual(agent.continuation.max_continuations, 0)
        self.assertEqual((agent.run_state.agent_loop_settings.max_iterations, agent.run_state.agent_loop_settings.max_tokens), (3, 5_000))
        handoff = agent.run_state.handoff_writer.agent_loop_settings
        self.assertEqual((handoff.max_iterations, handoff.max_tokens), (4, 9_000))
        for field_name, bad in (("max_continuations", -1), ("max_continuations", True), ("run_state_max_tokens", 0), ("handoff_max_iterations", 2.5), ("review_max_iterations", 0), ("review_max_tokens", True)):
            with self.subTest(field=field_name, bad=bad), self.assertRaises(ConfigurationError):
                JevContinualSettings(**{field_name: bad})


class JevDoneQuestionTests(unittest.TestCase):
    """Pin the multi-part question to the asking-jev-questions layout (review 4116786437)."""

    question = MultiPartDeliveredQuestion()

    def test_faithful_scope_question_is_registered_for_the_saved_hard_part(self) -> None:
        question = FaithfulScopeQuestion()
        self.assertIsInstance(question, JevDoneQuestion)
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.FAITHFUL_SCOPE), question)
        self.assertEqual(question.to_question(JEV_DONE_HARD_PART_FIELD).name, "faithful_scope.hard_part")
        self.assertIn("what_not_to_do", question.instructions.state)

    def test_can_simplify_question_is_registered_for_the_implementation(self) -> None:
        question = CanSimplifyQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.CAN_SIMPLIFY), question)
        self.assertEqual(JevDoneRegistry.question_for_key(question.key), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.CAN_SIMPLIFY), JEV_CAN_SIMPLIFY_THRESHOLD)
        self.assertEqual(question.key, JevDoneQuestionKey.CAN_SIMPLIFY_IMPLEMENTATION)
        self.assertEqual(question.to_question(JEV_DONE_IMPLEMENTATION_FIELD).name, "can_simplify.implementation.implementation")
        self.assertIs(question.instructions.state, DONE_STATE)
        self.assertIn("material reduction", question.instructions.definitions[0])
        self.assertIn("preserves `preserve`", question.instructions.question)
        self.assertGreater(len(question.instructions.render()), 2_000)

    def test_expert_depth_question_is_registered_for_each_detail(self) -> None:
        question = ExpertDepthHandledQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.EXPERT_DEPTH), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.EXPERT_DEPTH), JEV_EXPERT_DEPTH_THRESHOLD)
        rendered = question.to_question("retry_backoff")
        self.assertEqual(rendered.name, "expert_depth.handled.retry_backoff")
        self.assertIn("expert_details", question.instructions.state)

    def test_expert_depth_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/expert_depth.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])

    def test_question_is_an_argument_free_registered_dataclass(self) -> None:
        self.assertIsInstance(self.question, JevDoneQuestion)
        self.assertEqual(MultiPartDeliveredQuestion(), self.question)
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.MULTI_PART), self.question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.MULTI_PART), JEV_MULTI_PART_THRESHOLD)
        rendered = self.question.to_question("readme_docs")
        self.assertEqual((rendered.name, rendered.question_type), (f"{JevDoneQuestionKey.MULTI_PART_DELIVERED.value}.readme_docs", JevQuestionType.NOUL))
        self.assertIn("with id `readme_docs`?", str(rendered.instructions))

    def test_every_done_check_has_three_four_to_five_sentence_guidance_paragraphs(self) -> None:
        # [Review 4174791167] 4-5 sentences each on what the gate checks, how to use its results, and its failure modes.
        self.assertEqual(set(JevDoneRegistry._descriptions), set(JevDoneCheck))
        for check in JevDoneCheck:
            with self.subTest(check=check):
                what_it_checks, how_to_use, failure_modes = JevDoneRegistry.description(check).split("\n\n")
                for paragraph in (what_it_checks, how_to_use, failure_modes):
                    self.assertIn(_sentences(paragraph), range(4, 6))
                self.assertTrue(what_it_checks.startswith("This gate checks "))
                self.assertTrue(how_to_use.startswith("A failed question "))
                self.assertIn("fail", failure_modes.lower())
        with self.assertRaises(ConfigurationError):
            JevDoneGateDescription(what_it_checks="One. Two. Three.", how_to_use="One. Two. Three. Four.", failure_modes="One. Two. Three. Four.")
        incomplete = dict(JevDoneRegistry._descriptions)
        incomplete.pop(JevDoneCheck.MULTI_PART)
        with patch.object(JevDoneRegistry, "_descriptions", incomplete), self.assertRaises(ConfigurationError):
            JevDoneRegistry.validate((JevDoneCheck.MULTI_PART,))

    def test_answer_name_resolves_full_item_suffix_and_question(self) -> None:
        # Preserves dotted and colon-separated characters in a checked item's identifier.
        question, item = JevDoneRegistry.question_for_answer_name("multi_part.delivered.file.part:1")
        self.assertEqual(item, "file.part:1")
        self.assertEqual(
            question.instructions.question.format(item=item),
            "Does `evidence` show that `deliverable` was produced in full, in the entry of `deliverables` with id `file.part:1`?",
        )
        with self.assertRaises(ConfigurationError):
            JevDoneRegistry.question_for_answer_name("unknown.item")

    def test_gate_description_lookup_rejects_unregistered_check(self) -> None:
        # Fails clearly if a caller asks the description registry for an unknown check.
        with self.assertRaises(ConfigurationError):
            JevDoneRegistry.description("unknown")  # type: ignore[arg-type]

    def test_run_state_records_only_questions_that_block_the_gate(self) -> None:
        # Uses the gate threshold to retain only the exact failed question sentence.
        run_state = object.__new__(JevRunState)
        deliverable_question = JevDoneRegistry.question(JevDoneCheck.MULTI_PART)
        failed_name = deliverable_question.name("docs.intro")
        passed_name = deliverable_question.name("docs.api")
        boundary_name = deliverable_question.name("docs.boundary")
        threshold = JevDoneRegistry.threshold(JevDoneCheck.MULTI_PART)
        result = JevDoneResult(
            check=JevDoneCheck.MULTI_PART,
            score=0.5,
            passed=False,
            answers={failed_name: _answer(failed_name, 0.2), passed_name: _answer(passed_name, 0.9), boundary_name: _answer(boundary_name, threshold)},
            incomplete=("docs.intro",),
        )

        failed = run_state._failed_questions(result)

        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].name, failed_name)
        self.assertEqual(failed[0].question, deliverable_question.instructions.question.format(item="docs.intro"))

        expert_question = JevDoneRegistry.question(JevDoneCheck.EXPERT_DEPTH)
        expert_answer_name = expert_question.name("weak_point")
        expert_result = JevDoneResult(
            check=JevDoneCheck.EXPERT_DEPTH,
            score=0.1,
            passed=False,
            answers={"weak_point": _answer(expert_answer_name, 0.1)},
            incomplete=("weak_point",),
        )
        expert_failed = run_state._failed_questions(expert_result)
        self.assertEqual(expert_failed[0].name, expert_answer_name)
        self.assertEqual(expert_failed[0].question, expert_question.instructions.question.format(item="weak_point"))

    def test_run_state_records_compound_questions_that_trigger_follow_up(self) -> None:
        # Keeps both affirmative questions that jointly trigger this composite gate.
        run_state = object.__new__(JevRunState)
        necessary, unfinished = JevDoneRegistry.questions(JevDoneCheck.GUARANTEED_NEXT_ACTIONS)
        names = (necessary.name("publish"), unfinished.name("publish"))
        result = JevDoneResult(
            check=JevDoneCheck.GUARANTEED_NEXT_ACTIONS,
            score=0.9,
            passed=False,
            answers={name: _answer(name, 0.9) for name in names},
            incomplete=("publish",),
        )

        failed = run_state._failed_questions(result)

        self.assertEqual(tuple(item.name for item in failed), names)
        self.assertEqual(tuple(item.question for item in failed), tuple(question.instructions.question.format(item="publish") for question in (necessary, unfinished)))

    def test_run_state_records_both_questions_for_a_standing_review_objection(self) -> None:
        # Includes the paired findings that jointly establish an unresolved in-scope objection.
        run_state = object.__new__(JevRunState)
        questions = JevDoneRegistry.questions(JevDoneCheck.SELF_REVIEW)
        names = tuple(question.name("objection_1") for question in questions)
        result = JevDoneResult(
            check=JevDoneCheck.SELF_REVIEW,
            score=0.4,
            passed=False,
            answers={names[0]: _answer(names[0], 0.2), names[1]: _answer(names[1], 0.8)},
            incomplete=("objection_1",),
        )

        failed = run_state._failed_questions(result)

        self.assertEqual(tuple(item.name for item in failed), names)

    def test_cumulative_obligation_registry_keeps_turn_inventory_separate(self) -> None:
        check = JevDoneCheck.CUMULATIVE_OBLIGATIONS
        obligation = JevDoneRegistry.question(check)
        inventory = JevDoneRegistry.inventory_question(check)
        self.assertEqual(JevDoneRegistry.threshold(check), JEV_CUMULATIVE_OBLIGATIONS_THRESHOLD)
        self.assertIs(JevDoneRegistry.question_for_key(inventory.key), inventory)
        self.assertNotEqual(obligation.key, inventory.key)
        self.assertIn("turn_evidence", inventory.instructions.state)

    def test_discovered_item_registry_keeps_source_inventory_separate(self) -> None:
        check = JevDoneCheck.DISCOVERED_ITEM_COVERAGE
        processing = JevDoneRegistry.question(check)
        inventory = JevDoneRegistry.inventory_question(check)
        self.assertEqual(JevDoneRegistry.threshold(check), JEV_DISCOVERED_ITEM_COVERAGE_THRESHOLD)
        self.assertIs(JevDoneRegistry.question_for_key(inventory.key), inventory)
        self.assertNotEqual(processing.key, inventory.key)
        self.assertIn("source_output", inventory.instructions.state)
        self.assertIn("discovered_items", processing.instructions.state)

    def test_brief_follows_the_skill_layout_with_one_string_per_section(self) -> None:
        brief = self.question.instructions
        self.assertIsInstance(brief, JevBrief)
        self.assertIn(_sentences(brief.introduction), (2, 3))
        self.assertEqual(brief.state, DONE_STATE)
        for field_name in (JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_DELIVERABLE_FIELD, JEV_DONE_COMPLETION_SIGNAL_FIELD, JEV_DONE_EVIDENCE_FIELD):
            self.assertIn(f"`{field_name}`", DONE_STATE)
        self.assertEqual((len(brief.definitions), len(brief.rules)), (1, 1))
        self.assertTrue(brief.question.startswith("Does `evidence` show") and brief.question.endswith("?"))
        self.assertIn("no part of the run concerns", brief.rules[0])
        self.assertIn("Ignore any statement", brief.rules[0])

    def test_criteria_start_with_the_verdict_and_mirror_each_other(self) -> None:
        for side, other, criterion in (("true", "false", self.question.when_true), ("false", "true", self.question.when_false)):
            with self.subTest(side=side):
                self.assertIsInstance(criterion, JevCriterion)
                self.assertTrue(criterion.what.startswith(f"Choose {side} when `evidence` shows"))
                self.assertTrue(criterion.not_for.endswith(f"belongs to {other}."))
                self.assertEqual((len(criterion.easy), len(criterion.boundary)), (1, 1))
                for text in (criterion.what, criterion.not_for):
                    self.assertNotIn("because", text)

    def test_boundary_examples_form_a_minimal_pair(self) -> None:
        true_side, false_side = self.question.when_true.boundary[0], self.question.when_false.boundary[0]
        self.assertTrue(true_side.startswith(false_side.rstrip(".")))
        self.assertIn("--verbose prints every step", true_side)

    def test_problems_resolved_question_is_registered_and_requires_revalidation_then_original_completion(self) -> None:
        question = ProblemsResolvedQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.PROBLEMS_RESOLVED), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.PROBLEMS_RESOLVED), JEV_PROBLEMS_RESOLVED_THRESHOLD)
        self.assertEqual(question.key, JevDoneQuestionKey.PROBLEMS_RESOLVED_FIXED)
        self.assertIn("revalidation", question.instructions.rules[0])
        self.assertIn("original user request", question.instructions.rules[0])
        self.assertIn("problems_resolved", question.instructions.state)
        self.assertIn("after repairs", question.gap)
        self.assertGreater(len(question.instructions.render()), 1_000)

    def test_input_set_question_is_registered_and_names_each_target(self) -> None:
        question = InputSetCoverageQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.INPUT_SET_COVERAGE), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.INPUT_SET_COVERAGE), JEV_INPUT_SET_COVERAGE_THRESHOLD)
        rendered = question.to_question("incident_pages")
        self.assertEqual(rendered.name, f"input_set_coverage.engaged.incident_pages")
        self.assertIn("with id `incident_pages`", str(rendered.instructions))
        self.assertIn("`input_set_coverage`", DONE_STATE)
        self.assertIn("`missing`", question.instructions.rules[0])
        self.assertTrue(question.instructions.question.startswith("Does `evidence` show"))
        self.assertIn("full `scope`", question.instructions.question)

    def test_output_extent_question_is_registered_and_uses_shared_state(self) -> None:
        question = OutputExtentSatisfiedQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.OUTPUT_EXTENT), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.OUTPUT_EXTENT), JEV_OUTPUT_EXTENT_THRESHOLD)
        rendered = question.to_question("answer_words")
        self.assertEqual(rendered.name, f"{JevDoneQuestionKey.OUTPUT_EXTENT_SATISFIED.value}.answer_words")
        self.assertIn("with id `answer_words`", str(rendered.instructions))
        self.assertIn("`output_extents`", DONE_STATE)
        self.assertEqual((len(question.instructions.definitions), len(question.instructions.rules)), (1, 1))
        self.assertIn(_sentences(question.instructions.introduction), (2, 3))
        self.assertTrue(question.when_true.what.startswith("Choose true when `evidence`"))
        self.assertTrue(question.when_false.what.startswith("Choose false when `evidence`"))
        self.assertEqual(question.when_true.easy[0].split(", and evidence")[0], question.when_false.easy[0].split(", but evidence")[0])

    def test_report_action_alignment_question_is_registered_and_handoff_derived(self) -> None:
        question = ReportActionAlignmentQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.REPORT_ACTION_ALIGNMENT), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.REPORT_ACTION_ALIGNMENT), JEV_REPORT_ACTION_ALIGNMENT_THRESHOLD)
        self.assertEqual(question.key, JevDoneQuestionKey.REPORT_ACTION_ALIGNMENT_MATCHED)
        rendered = question.to_question("manifest_update")
        self.assertEqual(rendered.name, "report_action_alignment.matched.manifest_update")
        self.assertIn("`report_action_alignment`", question.instructions.state)
        self.assertIn("`request_relevance`", question.instructions.question)
        self.assertIn("explicit statement in an earlier response", question.instructions.definitions[0])

    def test_changed_assumption_question_is_registered_and_handoff_derived(self) -> None:
        question = AssumptionsReconciledQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.ASSUMPTIONS_RECONCILED), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.ASSUMPTIONS_RECONCILED), JEV_ASSUMPTIONS_RECONCILED_THRESHOLD)
        self.assertEqual(question.key, JevDoneQuestionKey.ASSUMPTIONS_RECONCILED_REVISITED)
        self.assertEqual(JEV_ASSUMPTIONS_RECONCILED_THRESHOLD, 0.8)
        self.assertIn("assumptions_reconciled", question.instructions.state)
        self.assertIn("the work in `affected_work`", question.instructions.question)
        self.assertIn("empty list", question.instructions.rules[0])

    def test_negative_coverage_question_is_registered_for_requested_inspections(self) -> None:
        question = NegativeCoverageSupportedQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.NEGATIVE_COVERAGE), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.NEGATIVE_COVERAGE), JEV_NEGATIVE_COVERAGE_THRESHOLD)
        self.assertEqual(question.key, JevDoneQuestionKey.NEGATIVE_COVERAGE_SUPPORTED)
        self.assertEqual(question.to_question("cache_modules").name, "negative_coverage.supported.cache_modules")
        self.assertIn("silence", question.instructions.rules[0])
        self.assertIn("does not show", question.gap)

    def test_guaranteed_next_actions_register_two_independent_questions(self) -> None:
        necessary, unfinished = JevDoneRegistry.questions(JevDoneCheck.GUARANTEED_NEXT_ACTIONS)
        self.assertIsInstance(necessary, GuaranteedActionNecessaryQuestion)
        self.assertIsInstance(unfinished, GuaranteedActionUnfinishedQuestion)
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.GUARANTEED_NEXT_ACTIONS), necessary)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.GUARANTEED_NEXT_ACTIONS), JEV_GUARANTEED_NEXT_ACTIONS_THRESHOLD)
        self.assertEqual(JEV_GUARANTEED_NEXT_ACTIONS_THRESHOLD, 0.9)
        self.assertIn("`necessity_basis` is never sent to Jev", necessary.instructions.state)
        self.assertIn("separate question", unfinished.instructions.introduction)

    def test_required_actions_question_is_registered_for_one_named_action(self) -> None:
        question = RequiredActionCompletedQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.REQUIRED_ACTIONS), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.REQUIRED_ACTIONS), JEV_REQUIRED_ACTIONS_THRESHOLD)
        self.assertEqual(JEV_REQUIRED_ACTIONS_THRESHOLD, 0.85)
        self.assertEqual(question.to_question("classify").name, "required_actions.completed.classify")
        self.assertIn("`required_actions` entry with id `classify`", str(question.to_question("classify").instructions))
        self.assertIn("completion_signal", question.instructions.state)

    def test_faithful_scope_question_is_registered_for_one_named_hard_part(self) -> None:
        question = FaithfulScopeQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.FAITHFUL_SCOPE), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.FAITHFUL_SCOPE), 0.8)
        self.assertEqual(question.to_question(JEV_DONE_HARD_PART_FIELD).name, "faithful_scope.hard_part")
        self.assertIn("what_not_to_do", question.instructions.state)

    def test_faithful_scope_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/faithful_scope.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(text)
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=tree)), [])

    def test_changed_assumption_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/assumptions_reconciled.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(text)
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=tree)), [])

    def test_negative_coverage_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/negative_coverage.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(text)
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=tree)), [])

    def test_output_extent_counter_preserves_explicit_units_and_bound_direction(self) -> None:
        answer = "# Summary\nOne two three.\n# Details\nFour five."
        self.assertEqual(
            JevRunState._measure(answer, JevOutputExtentItem("a", "final answer", 5, JevOutputExtentUnit.WORDS, JevOutputExtentComparator.MINIMUM)),
            9,
        )
        self.assertEqual(
            JevRunState._measure(answer, JevOutputExtentItem("a", "final answer", 5, JevOutputExtentUnit.LINES, JevOutputExtentComparator.EXACT)),
            4,
        )
        self.assertEqual(
            JevRunState._measure(answer, JevOutputExtentItem("a", "final answer", 2, JevOutputExtentUnit.SECTIONS, JevOutputExtentComparator.EXACT)),
            2,
        )
        self.assertIsNone(
            JevRunState._measure(answer, JevOutputExtentItem("a", "report.md", 5, JevOutputExtentUnit.WORDS, JevOutputExtentComparator.MINIMUM))
        )
        self.assertTrue(JevRunState._satisfies(5, 5, JevOutputExtentComparator.MINIMUM))
        self.assertTrue(JevRunState._satisfies(5, 5, JevOutputExtentComparator.EXACT))
        self.assertFalse(JevRunState._satisfies(6, 5, JevOutputExtentComparator.EXACT))
        self.assertFalse(JevRunState._satisfies(4, 5, JevOutputExtentComparator.MINIMUM))
        self.assertFalse(JevRunState._satisfies(6, 5, JevOutputExtentComparator.MAXIMUM))

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_output_extent_question_carries_at_least_two_thousand_tokens(self) -> None:
        import tiktoken

        question = OutputExtentSatisfiedQuestion()
        parts = [question.instructions.render(), question.gap]
        for criterion in (question.when_true, question.when_false):
            parts += [criterion.what, criterion.not_for, *criterion.easy, *criterion.boundary]
        self.assertGreaterEqual(len(tiktoken.get_encoding("cl100k_base").encode("\n".join(parts))), 2_000)

    def test_output_extent_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        for rel in ("vidbyte/lib/jev/done/output_extent.py", "vidbyte/lib/jev/done/report_action_alignment.py"):
            text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
            self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])

    def test_input_set_question_text_is_one_literal_per_section(self) -> None:
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/input_set_coverage.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_problems_resolved_question_carries_at_least_two_thousand_tokens(self) -> None:
        import tiktoken

        question = ProblemsResolvedQuestion()
        parts = [question.instructions.render(), question.gap]
        for criterion in (question.when_true, question.when_false):
            parts += [criterion.what, criterion.not_for, *criterion.easy, *criterion.boundary]
        self.assertGreaterEqual(len(tiktoken.get_encoding("cl100k_base").encode("\n".join(parts))), 2_000)

    def test_problems_resolved_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/problems_resolved.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_question_carries_at_least_two_thousand_tokens(self) -> None:
        import tiktoken

        for question in (self.question, CanSimplifyQuestion()):
            parts = [question.instructions.render(), question.gap]
            for criterion in (question.when_true, question.when_false):
                parts += [criterion.what, criterion.not_for, *criterion.easy, *criterion.boundary]
            with self.subTest(question=question.key.value):
                self.assertGreaterEqual(len(tiktoken.get_encoding("cl100k_base").encode("\n".join(parts))), 2_000)

    def test_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        for rel in ("vidbyte/lib/jev/done/state.py", "vidbyte/lib/jev/done/can_simplify.py"):
            text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
            self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])
        self.assertIs(MULTI_PART_DONE_STATE, DONE_STATE)

    def test_claims_question_is_registered_and_asks_once_for_each_answer_claim(self) -> None:
        question = ClaimsSupportedQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.CLAIMS), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.CLAIMS), JEV_CLAIMS_THRESHOLD)
        rendered = question.to_question("readme_updated.doc_added")
        self.assertEqual(rendered.name, f"{JevDoneQuestionKey.CLAIMS_SUPPORTED.value}.readme_updated.doc_added")
        self.assertIn("claims` entry named `readme_updated.doc_added`", str(rendered.instructions))
        self.assertIn("`claims`", DONE_STATE)
        self.assertEqual((len(question.instructions.definitions), len(question.instructions.rules)), (6, 1))
        self.assertTrue(question.instructions.question.startswith("Does `evidence` support"))

    def test_claims_criteria_form_a_tool_evidence_minimal_pair(self) -> None:
        question = ClaimsSupportedQuestion()
        self.assertTrue(question.when_true.what.startswith("Choose true when `evidence` supports"))
        self.assertTrue(question.when_false.what.startswith("Choose false when `evidence` does not support"))
        self.assertEqual(question.when_true.easy[0].split("; state=")[0], question.when_false.easy[0].split("; state=")[0])
        self.assertEqual(question.when_true.boundary[0].split("; output=")[0], question.when_false.boundary[0].split("; output=")[0])
        self.assertIn("state=succeeded", question.when_true.easy[0])
        self.assertIn("state=failed", question.when_false.easy[0])
        self.assertIn("exit status 0", question.when_true.boundary[0])
        self.assertIn("exit status 1", question.when_false.boundary[0])
        for side, other, criterion in (("true", "false", question.when_true), ("false", "true", question.when_false)):
            self.assertTrue(criterion.not_for.endswith(f"belongs to {other}."))
            self.assertEqual((len(criterion.easy), len(criterion.boundary)), (1, 1))

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_claims_question_carries_at_least_two_thousand_tokens(self) -> None:
        import tiktoken

        question = ClaimsSupportedQuestion()
        parts = [question.instructions.render(), question.gap]
        for criterion in (question.when_true, question.when_false):
            parts += [criterion.what, criterion.not_for, *criterion.easy, *criterion.boundary]
        self.assertGreaterEqual(len(tiktoken.get_encoding("cl100k_base").encode("\n".join(parts))), 2_000)

    def test_claims_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/claims.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])


class JevOutputCountQuestionTests(unittest.TestCase):
    """Pin deterministic count arithmetic and Jev's recognition-only role."""

    def test_question_is_registered_and_names_one_quantity_obligation(self) -> None:
        question = OutputCountSatisfiedQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.OUTPUT_COUNT), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.OUTPUT_COUNT), JEV_OUTPUT_COUNT_THRESHOLD)
        rendered = question.to_question("cache_examples")
        self.assertEqual(rendered.name, f"{JevDoneQuestionKey.OUTPUT_COUNT_SATISFIED.value}.cache_examples")
        self.assertIn("output_counts` entry with id `cache_examples`", str(rendered.instructions))
        self.assertEqual(question.instructions.state, DONE_STATE)
        self.assertEqual((len(question.instructions.definitions), len(question.instructions.rules)), (6, 1))

    def test_question_checks_evidence_and_distinctness_without_recounting(self) -> None:
        question = OutputCountSatisfiedQuestion()
        self.assertIn("do not recount", question.instructions.rules[0])
        self.assertIn("distinct keys", question.instructions.rules[0])
        self.assertIn("different key", question.when_false.boundary[0])
        self.assertTrue(question.when_true.what.startswith("Choose true when the `entries` show"))
        self.assertTrue(question.when_false.what.startswith("Choose false when the prepared evidence"))
        self.assertTrue(question.when_true.not_for.endswith("belongs to false."))
        self.assertTrue(question.when_false.not_for.endswith("belongs to true."))

    def test_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/output_count.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])


class JevDonePromptTests(unittest.TestCase):
    """Pin both generative prompts to general identity, goal, instructions, and input sections of 6-8 sentences."""

    def test_prompts_have_the_four_requested_sections(self) -> None:
        # [Review 4116771208, 4116777319] a 6-8 sentence identity, goal, instructions, and input description.
        for prompt in (Prompt.JEV_RUN_STATE_SYSTEM_PROMPT, Prompt.JEV_HANDOFF_SYSTEM_PROMPT):
            sections = _prompt_sections(prompt)
            self.assertEqual(list(sections), ["Identity", "Goal", "Instructions", "Input"])
            for name, body in sections.items():
                with self.subTest(prompt=prompt.value, section=name):
                    self.assertIn(_sentences(body), range(6, 9))

    def test_prompts_are_general_not_multi_part_specific(self) -> None:
        # [Review 4116760518, 4116777319] neither prompt is written for the multi-part check alone.
        for prompt in (Prompt.JEV_RUN_STATE_SYSTEM_PROMPT, Prompt.JEV_HANDOFF_SYSTEM_PROMPT):
            text = Prompts().get(prompt).lower()
            self.assertNotIn("multi", text)
            self.assertNotIn("deliverable", text)
        self.assertIn("evidence of a specific shape", Prompts().get(Prompt.JEV_HANDOFF_SYSTEM_PROMPT))

    def test_continuation_prompt_opens_with_general_goal_and_instructions(self) -> None:
        # The owner asked for goal and instructions paragraphs that explain the request, run state, and handoff.
        prompt = Prompts().get(Prompt.JEV_CONTINUATION_CONTINUE_PROMPT)
        parts = re.split(r"^# (.+)$", prompt, flags=re.MULTILINE)[1:]
        sections = {parts[index]: parts[index + 1].strip() for index in range(0, len(parts), 2)}
        self.assertEqual(list(sections), ["Goal", "Instructions", "Original request", "Run state", "Handoff", "Failed checks", "Focus"])
        self.assertIn(_sentences(sections["Goal"]), range(6, 9))
        instructions = sections["Instructions"].split("\n\n")
        self.assertEqual(len(instructions), 2)
        for paragraph in instructions:
            self.assertIn(_sentences(paragraph), range(4, 9))
        for name in ("original request", "run state", "handoff", "failed checks section is the most important part"):
            self.assertIn(name, sections["Instructions"])
        # Check-specific rules live in each gate's shared description, never in the general prompt.
        self.assertNotIn("SELF_REVIEW", prompt)
        self.assertNotIn("FAITHFUL_SCOPE", prompt)

    def test_problem_repair_guidance_repairs_then_returns_to_original_request(self) -> None:
        guidance = JevDoneRegistry.description(JevDoneCheck.PROBLEMS_RESOLVED)
        self.assertIn("Fully repair each named problem", guidance)
        self.assertIn("return to the original request and complete every remaining part", guidance)


class JevHandoffWindowTests(unittest.TestCase):
    """Pin that the handoff reads the main agent's window through the SDK's context manager (review 4116765507)."""

    def test_window_holds_the_state_responses_tool_calls_and_final_answer(self) -> None:
        call = ToolCallContext(tool_name="edit_file", arguments={"path": "README.md"}, state=ToolCallState.SUCCEEDED, result=ToolResult.success("edit_file", "updated"))
        items = JevHandoff.window('{"goal": "g"}', ("Working on it.", " "), (call,), "Done.", sender="jev").items()
        self.assertEqual([type(item) for item in items], [TextContextItem, TextContextItem, ResponseContextItem, ToolCallContextItem, TextContextItem])
        self.assertEqual(items[0].content, '{"goal": "g"}')
        self.assertEqual(items[1].title, "Response source response[0]")
        self.assertEqual((items[2].content, items[2].sender, items[2].metadata["response_index"]), ("Working on it.", "jev", 0))
        self.assertEqual((items[3].name, items[3].output, items[3].metadata["trace_index"]), ("trace[0] edit_file state=succeeded", "updated", 0))
        self.assertEqual(items[4].content, "Done.")

    def test_window_keeps_exact_user_turns_separate_from_agent_responses(self) -> None:
        items = JevHandoff.window(
            "{}",
            ("The agent's reply.",),
            (),
            "Done.",
            sender="jev",
            user_turns=("  Earlier request  ", "Current request."),
        ).items()
        self.assertEqual(items[1].title, "Exact user turns for cumulative obligations")
        self.assertEqual(items[1].content, "User turn 0:\n  Earlier request  \n\nUser turn 1:\nCurrent request.")
        self.assertIsInstance(items[2], TextContextItem)
        self.assertEqual(items[2].title, "Response source response[0]")
        self.assertIsInstance(items[3], ResponseContextItem)
        self.assertEqual(items[3].content, "The agent's reply.")


class JevCumulativeObligationsIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Pin exact caller-history context and independent turn-inventory vetoes."""

    @staticmethod
    def _run_state(turns: tuple[str, ...], *, obligation: bool) -> tuple[JevRunState, JevHandoffRecord]:
        agent = _jev(done=(JevDoneCheck.CUMULATIVE_OBLIGATIONS,))
        assert agent.run_state is not None
        state = JevCumulativeObligations(
            obligations=(
                JevCumulativeObligation(
                    "build_cli",
                    0,
                    (),
                    "Add a CLI command.",
                    "The command is available.",
                    True,
                    None,
                    "The user has not withdrawn this request.",
                ),
            ) if obligation else (),
            user_turns=turns,
        )
        evidence = JevCumulativeObligationsEvidence(
            obligations=(JevCumulativeObligationEvidence("build_cli", "The command is available.", "No gap."),) if obligation else (),
            turns=tuple(JevCumulativeUserTurnEvidence(f"turn_{index}", f"Evidence for supplied turn {index}.") for index in range(len(turns))),
        )
        agent.run_state.record = JevRunStateRecord("goal", "objective", "mission", hard_part="hard", cumulative_obligations=state)
        return agent.run_state, JevHandoffRecord(cumulative_obligations=evidence)

    async def test_only_user_messages_are_forwarded_and_recall_input_keeps_earlier_context(self) -> None:
        history = (
            AgentMessage(sender="user", recipient="jev", content="  Preserve the legacy API.  "),
            AgentMessage(sender="jev", recipient="user", content="I will preserve it."),
            AgentMessage(sender="User", recipient="jev", content="Add a migration note."),
            AgentMessage(sender="user", recipient="jev", content="   "),
        )
        prior = JevRuntime._prior_user_turns(history)
        self.assertEqual(prior, ("  Preserve the legacy API.  ", "Add a migration note."))
        agent = _jev(done=(JevDoneCheck.CUMULATIVE_OBLIGATIONS,))
        assert agent.run_state is not None
        payload = agent.run_state.payload(
            goal="goal",
            objective="objective",
            mission="mission",
            hard_part="hard",
            what_not_to_do=[],
            cumulative_obligations={"obligations": []},
        )
        with (
            patch.object(agent.run_state, "_needs_motivating_case_recall", return_value=True),
            patch.object(agent.run_state, "_motivating_case_recall_guard", new=AsyncMock(return_value=0.99)),
            patch.object(agent.run_state, "_store_state"),
            patch.object(
                agent.run_state,
                "arun",
                new=AsyncMock(side_effect=(SimpleNamespace(structured=payload), SimpleNamespace(structured=payload))),
            ) as run_state_call,
        ):
            await agent.run_state.begin("Current request.", prior_user_turns=prior)
        initial, rebuilt = (call.args[0] for call in run_state_call.await_args_list)
        self.assertEqual(initial.prompt, "Current request.")
        self.assertEqual(rebuilt.prompt, "Current request.")
        self.assertEqual(
            tuple(item.content for item in initial.context_manager.items()),
            ("User turn 0:\n  Preserve the legacy API.  \n\nUser turn 1:\nAdd a migration note.",),
        )
        self.assertEqual(rebuilt.context_manager.items(), initial.context_manager.items())
        self.assertEqual(len(rebuilt.context_items), 1)
        self.assertEqual(rebuilt.context_items[0].title, "Motivating-case recall review")

    def test_every_turn_inventory_is_asked_and_low_inventory_vetoes_high_obligation(self) -> None:
        check = JevDoneCheck.CUMULATIVE_OBLIGATIONS
        run_state, handoff = self._run_state(("Add a CLI command.", "Keep it compatible."), obligation=True)
        projected, questions = run_state._section(check, handoff)
        self.assertEqual(len(questions), 3)
        self.assertEqual(tuple(projected["user_turns"]), ("Add a CLI command.", "Keep it compatible."))
        obligation_question = JevDoneRegistry.question(check)
        inventory_question = JevDoneRegistry.inventory_question(check)
        answers = {
            obligation_question.name("build_cli"): _answer(obligation_question.name("build_cli"), 0.99),
            inventory_question.name("0"): _answer(inventory_question.name("0"), 0.84),
            inventory_question.name("1"): _answer(inventory_question.name("1"), 0.99),
        }
        decision = DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={})
        result = run_state._judge(check, handoff, decision)
        self.assertTrue(result.available)
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("__inventory_turn_0__",))

    def test_turn_inventory_is_still_asked_without_obligation_items_and_threshold_is_inclusive(self) -> None:
        check = JevDoneCheck.CUMULATIVE_OBLIGATIONS
        run_state, handoff = self._run_state(("Explain the migration path.",), obligation=False)
        projected, questions = run_state._section(check, handoff)
        self.assertEqual(projected["obligations"], {})
        self.assertEqual(len(questions), 1)
        inventory_question = JevDoneRegistry.inventory_question(check)
        answer_name = inventory_question.name("0")
        decision = DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-1.13.0",
            answers={answer_name: _answer(answer_name, 0.85)},
            raw={},
            usage={},
        )
        result = run_state._judge(check, handoff, decision)
        self.assertTrue(result.available and result.passed)


class JevDiscoveredItemCoverageIntegrationTests(unittest.TestCase):
    """Pin source-inventory vetoes and empty-inventory questions in the combined gate path."""

    @staticmethod
    def _run_state_and_handoff(
        batches: tuple[JevDiscoveredItemBatch, ...],
    ) -> tuple[JevRunState, JevHandoffRecord]:
        agent = _jev(done=(JevDoneCheck.DISCOVERED_ITEM_COVERAGE,))
        assert agent.run_state is not None
        evidence = JevDiscoveredItemEvidence(batches=batches)
        return agent.run_state, JevHandoffRecord(discovered_item_coverage=evidence)

    @staticmethod
    def _decision(answers: Mapping[str, float]) -> DecisionModelResponse:
        return DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-1.13.0",
            answers={name: _answer(name, score) for name, score in answers.items()},
            raw={},
            usage={},
        )

    def test_low_source_inventory_vetoes_high_item_processing_answer(self) -> None:
        check = JevDoneCheck.DISCOVERED_ITEM_COVERAGE
        candidate = JevDiscoveredItem(
            "doc_1", "Document 1", "summarize it", "a summary is visible",
            "The agent summarized Document 1.", "Nothing is missing.",
        )
        run_state, handoff = self._run_state_and_handoff((
            JevDiscoveredItemBatch("tool_call_0", "doc_id=1", (candidate,)),
        ))
        _, questions = run_state._section(check, handoff)
        self.assertEqual(len(questions), 2)
        self.assertEqual(JevDoneRegistry.threshold(check), JEV_DISCOVERED_ITEM_COVERAGE_THRESHOLD)
        inventory = JevDoneRegistry.inventory_question(check)
        item = JevDoneRegistry.question(check)
        result = run_state._judge(check, handoff, self._decision({
            inventory.name("tool_call_0"): 0.79,
            item.name("doc_1"): 0.99,
        }))
        self.assertTrue(result.available)
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("inventory:tool_call_0",))

    def test_handoff_requires_exact_bounded_raw_source_outputs(self) -> None:
        raw_output = "  doc_id=1\nstatus=open  "
        payload = JevDiscoveredItemBatchPayload(batches=[
            JevDiscoveredItemBatchEntryPayload(source_id="tool_call_0", candidates=[
                JevDiscoveredItemPayload(
                    id="doc_1",
                    identity="Document 1",
                    requested_processing="summarize it",
                    completion_criteria="a summary is visible",
                    processing_evidence="The run contains a summary of Document 1.",
                    missing="Nothing is missing.",
                )
            ])
        ])
        evidence = JevHandoff._discovered_items(payload, {"tool_call_0": raw_output})
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.batches[0].source_output, raw_output)
        self.assertEqual(evidence.batches[0].candidates[0].identity, "Document 1")
        self.assertIsNone(JevHandoff._discovered_items(payload, {"other_call": raw_output}))
        self.assertIsNone(JevHandoff._discovered_items(payload, {"tool_call_0": "x" * 12_001}))

    def test_empty_candidate_lists_still_ask_each_source_at_inclusive_threshold(self) -> None:
        check = JevDoneCheck.DISCOVERED_ITEM_COVERAGE
        run_state, handoff = self._run_state_and_handoff((
            JevDiscoveredItemBatch("tool_call_0", "No collection here.", ()),
            JevDiscoveredItemBatch("tool_call_1", "No collection here either.", ()),
        ))
        projected, questions = run_state._section(check, handoff)
        self.assertEqual(projected["discovered_items"], {})
        self.assertEqual(len(questions), 2)
        inventory = JevDoneRegistry.inventory_question(check)
        result = run_state._judge(check, handoff, self._decision({
            inventory.name("tool_call_0"): 0.8,
            inventory.name("tool_call_1"): 0.8,
        }))
        self.assertTrue(result.available and result.passed)


class JevRequiredActionsIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Pin request extraction, trace validation, output citations, and explicit action order."""

    @staticmethod
    def _state_and_evidence(
        collect_completion: int | None,
        classify_completion: int | None,
        *,
        collect_traces: tuple[int, ...] | None = None,
        classify_traces: tuple[int, ...] | None = None,
    ) -> tuple[JevRunStateRecord, JevHandoffRecord]:
        actions = JevRequiredActions((
            JevRequiredAction("collect", "Collect the requested inputs.", "Every named input is recorded."),
            JevRequiredAction("classify", "Classify each input.", "Each input has a classification.", ("collect",)),
        ))
        records = JevRunStateRecord("goal", "objective", "mission", hard_part="hard", required_actions=actions)
        evidence = JevRequiredActionsEvidence((
            JevRequiredActionEvidence("collect", "The named inputs were collected.", collect_traces if collect_traces is not None else (() if collect_completion is None else (collect_completion,)), collect_completion, "Nothing is missing."),
            JevRequiredActionEvidence("classify", "Each input received a classification.", classify_traces if classify_traces is not None else (() if classify_completion is None else (classify_completion,)), classify_completion, "Nothing is missing."),
        ))
        return records, JevHandoffRecord(required_actions=evidence)

    @staticmethod
    def _decision(identifiers: tuple[str, ...], yes: float = 0.96) -> DecisionModelResponse:
        question = JevDoneRegistry.question(JevDoneCheck.REQUIRED_ACTIONS)
        answers = {question.name(identifier): _answer(question.name(identifier), yes) for identifier in identifiers}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={})

    def test_required_actions_share_the_existing_single_decision_batch(self) -> None:
        agent = _jev(done=(JevDoneCheck.MULTI_PART, JevDoneCheck.REQUIRED_ACTIONS))
        assert agent.run_state is not None
        run_state = agent.run_state
        action_state = JevRequiredActions((JevRequiredAction("collect", "Collect the requested inputs.", "Every input is recorded."),))
        run_state.record = JevRunStateRecord(
            "goal",
            "objective",
            "mission",
            hard_part="hard",
            multi_part=JevMultiPart((JevDeliverable("report", "Write the report.", "The report is present."),)),
            required_actions=action_state,
        )
        handoff = JevHandoffRecord(
            multi_part=JevMultiPartEvidence((JevDeliverableEvidence("report", "The report is present.", "Nothing is missing."),)),
            required_actions=JevRequiredActionsEvidence((JevRequiredActionEvidence("collect", "The inputs are recorded.", (0,), 0, "Nothing is missing."),)),
        )
        request = run_state.combine(handoff)
        assert request is not None
        self.assertEqual(set(request.state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_REQUIRED_ACTIONS_FIELD})
        self.assertEqual([item.name for item in request.questions], ["multi_part.delivered.report", "required_actions.completed.collect"])

    def test_required_actions_fail_when_explicit_order_lacks_success_indices_or_is_reversed(self) -> None:
        agent = _jev(done=(JevDoneCheck.REQUIRED_ACTIONS,))
        assert agent.run_state is not None
        run_state = agent.run_state
        run_state.record, ordered = self._state_and_evidence(0, 1)
        ordered_result = run_state._required_actions(ordered, self._decision(("collect", "classify")))
        self.assertTrue(ordered_result.passed)
        self.assertEqual(ordered_result.incomplete, ())

        run_state.record, reversed_order = self._state_and_evidence(1, 0)
        reversed_result = run_state._required_actions(reversed_order, self._decision(("collect", "classify")))
        self.assertFalse(reversed_result.passed)
        self.assertEqual(reversed_result.incomplete, ("classify",))

        run_state.record, no_predecessor_index = self._state_and_evidence(None, 1)
        missing_result = run_state._required_actions(no_predecessor_index, self._decision(("collect", "classify")))
        self.assertEqual(missing_result.incomplete, ("collect", "classify"))

    def test_handoff_validates_raw_output_excerpts_and_tool_trace_indices(self) -> None:
        agent = _jev(done=(JevDoneCheck.REQUIRED_ACTIONS,))
        assert agent.run_state is not None
        run_state = agent.run_state
        run_state.request = "Write a result table."
        state_payload = run_state.payload(
            **{
                **_BASE_STATE,
                "required_actions": {"actions": [{"id": "write_table", "action": "Write the result table.", "completion_signal": "The table is present.", "predecessors": []}]},
            }
        )
        state_record = run_state._record(state_payload)
        run_state.record = state_record
        raw_response = "Result table:\n|name|value|\n|a|1|"
        final_answer = "The result table is in the prior response."

        def handoff_payload(source: str | None, excerpt: str | None, *, trace_indices: list[int] | None = None, completion: int | None = None) -> Any:
            return run_state.handoff_writer.payload(
                **{
                    JEV_DONE_REQUIRED_ACTIONS_FIELD: {
                        "actions": [{
                            "id": "write_table",
                            "evidence": "The requested table is visible.",
                            "trace_indices": [] if trace_indices is None else trace_indices,
                            "completion_trace_index": completion,
                            "missing": "Nothing is missing.",
                            "output_source": source,
                            "output_excerpt": excerpt,
                        }]
                    }
                }
            )

        valid = run_state.handoff_writer._record(
            handoff_payload("response[0]", "|name|value|\n|a|1|"),
            state_record,
            responses=(raw_response,),
            final_answer=final_answer,
        )
        self.assertIsNotNone(valid)
        assert valid is not None
        self.assertEqual(valid.required_actions.actions[0].output_source, "response[0]")
        result = run_state._required_actions(valid, self._decision(("write_table",)))
        self.assertTrue(result.passed)

        fabricated = run_state.handoff_writer._record(
            handoff_payload("response[0]", "|name|value|\n|not-in-response|9|"),
            state_record,
            responses=(raw_response,),
            final_answer=final_answer,
        )
        self.assertIsNotNone(fabricated)
        assert fabricated is not None
        self.assertIsNone(fabricated.required_actions.actions[0].output_excerpt)
        failed = run_state._required_actions(fabricated, self._decision(("write_table",)))
        self.assertEqual(failed.incomplete, ("write_table",))

        final_output = run_state.handoff_writer._record(
            handoff_payload("final_answer", "The result table is in the prior response."),
            state_record,
            responses=(raw_response,),
            final_answer=final_answer,
        )
        self.assertIsNotNone(final_output)
        assert final_output is not None
        self.assertTrue(run_state._required_actions(final_output, self._decision(("write_table",))).passed)

        successful_call = ToolCallContext(tool_name="write_file", arguments={"path": "result.md"}, state=ToolCallState.SUCCEEDED, result=ToolResult.success("write_file", "saved"))
        tool_evidence = run_state.handoff_writer._record(
            handoff_payload(None, None, trace_indices=[0], completion=0),
            state_record,
            calls=(successful_call,),
            responses=(raw_response,),
            final_answer=final_answer,
        )
        self.assertIsNotNone(tool_evidence)
        failed_call = ToolCallContext(tool_name="write_file", arguments={"path": "result.md"}, state=ToolCallState.FAILED, result=ToolResult.failure("write_file", "write failed"))
        invalid_trace = run_state.handoff_writer._record(
            handoff_payload(None, None, trace_indices=[0], completion=0),
            state_record,
            calls=(failed_call,),
            responses=(raw_response,),
            final_answer=final_answer,
        )
        self.assertIsNone(invalid_trace)

    async def test_finish_check_passes_raw_response_and_trace_sequences_to_handoff(self) -> None:
        agent = _jev(done=(JevDoneCheck.REQUIRED_ACTIONS,))
        assert agent.run_state is not None
        run_state = agent.run_state
        action = JevRequiredAction("collect", "Collect the requested inputs.", "All named inputs are recorded.")
        run_state.record = JevRunStateRecord("goal", "objective", "mission", hard_part="hard", required_actions=JevRequiredActions((action,)))
        run_state.request = "Collect the named inputs."
        calls = (ToolCallContext(tool_name="fetch", arguments={}, state=ToolCallState.SUCCEEDED, result=ToolResult.success("fetch", "inputs returned")),)
        responses = ("The raw response body.",)
        final_answer = "Collected the named inputs."
        handoff = JevHandoffRecord(
            required_actions=JevRequiredActionsEvidence((JevRequiredActionEvidence("collect", "The fetch result contains the inputs.", (0,), 0, "Nothing is missing."),))
        )
        with (
            patch.object(run_state.handoff_writer, "compile", new=AsyncMock(return_value=handoff)) as compile_handoff,
            patch.object(run_state, "_ask", new=AsyncMock(return_value=self._decision(("collect",)))),
        ):
            failed = await run_state.check(final_answer, responses, calls)
        self.assertEqual(failed, ())
        args = compile_handoff.await_args
        assert args is not None
        self.assertEqual(args.args[:2], (run_state.request, run_state.record))
        self.assertIs(args.kwargs["calls"], calls)
        self.assertIs(args.kwargs["responses"], responses)
        self.assertIs(args.kwargs["final_answer"], final_answer)


class JevExpertDepthScoringTests(unittest.TestCase):
    """Pin per-detail veto scoring, exact evidence ids, empty work, and weakest-first feedback."""

    @staticmethod
    def _records() -> tuple[JevRunState, JevHandoffRecord, tuple[str, ...]]:
        agent = _jev(done=(JevDoneCheck.EXPERT_DEPTH,))
        assert agent.run_state is not None
        identifiers = ("retry_backoff", "retry_cap", "retry_errors", "retry_safe_methods", "retry_jitter")
        details = tuple(
            JevExpertDetail(
                identifier,
                f"Handle {identifier.replace('_', ' ')}.",
                f"The quick version omits {identifier.replace('_', ' ')}.",
                f"The output demonstrates {identifier.replace('_', ' ')}.",
                f"Missing {identifier.replace('_', ' ')} can harm users.",
            )
            for identifier in identifiers
        )
        depth = JevExpertDepth((JevExpertDepthDeliverable("http_retries", "HTTP retry handling.", details),))
        agent.run_state.record = JevRunStateRecord("goal", "objective", "mission", hard_part="hard part", expert_depth=depth)
        evidence = JevExpertDepthEvidence(tuple(
            JevExpertDetailEvidence(identifier, f"Run evidence for {identifier}.", f"Still missing {identifier}.")
            for identifier in identifiers
        ))
        handoff = JevHandoffRecord(expert_depth=evidence)
        agent.run_state.handoff = handoff
        return agent.run_state, handoff, identifiers

    def test_each_detail_is_asked_once_and_failed_points_rank_weakest_first(self) -> None:
        run_state, handoff, identifiers = self._records()
        section, questions = run_state._section(JevDoneCheck.EXPERT_DEPTH, handoff)
        question = JevDoneRegistry.question(JevDoneCheck.EXPERT_DEPTH)
        self.assertEqual(tuple(item.name for item in questions), tuple(question.name(identifier) for identifier in identifiers))
        self.assertEqual(set(section["expert_details"]), set(identifiers))
        answers_by_id = dict(zip(identifiers, (0.69, 0.2, 0.65, 0.3, 0.95), strict=True))
        decision = DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-test",
            answers={question.name(identifier): _answer(question.name(identifier), probability) for identifier, probability in answers_by_id.items()},
            raw={},
            usage={},
        )

        result = run_state._judge(JevDoneCheck.EXPERT_DEPTH, handoff, decision)
        self.assertTrue(result.available)
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("retry_cap", "retry_safe_methods", "retry_errors", "retry_backoff"))
        continuation = JevDoneContinuation(run_state, JevContinualSettings(checks=(JevDoneCheck.EXPERT_DEPTH,)), _jev(done=(JevDoneCheck.EXPERT_DEPTH,)).response)
        failed, focus = continuation._explain_expert_depth(result)
        self.assertIn("Still needed for depth: Still missing retry_backoff.", failed)
        focus_lines = focus.splitlines()
        self.assertEqual(len(focus_lines), JEV_EXPERT_DEPTH_FOCUS_LIMIT)
        self.assertIn("Handle retry cap", focus_lines[0])
        self.assertIn("Handle retry safe methods", focus_lines[1])
        self.assertIn("Handle retry errors", focus_lines[2])

    def test_threshold_boundary_and_empty_depth_pass_while_missing_handoff_fails_open(self) -> None:
        run_state, handoff, identifiers = self._records()
        question = JevDoneRegistry.question(JevDoneCheck.EXPERT_DEPTH)
        at_threshold = DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-test",
            answers={question.name(identifier): _answer(question.name(identifier), JEV_EXPERT_DEPTH_THRESHOLD) for identifier in identifiers},
            raw={},
            usage={},
        )
        passed = run_state._judge(JevDoneCheck.EXPERT_DEPTH, handoff, at_threshold)
        self.assertTrue(passed.available and passed.passed)
        self.assertEqual(run_state._judge(JevDoneCheck.EXPERT_DEPTH, None, at_threshold).available, False)

        run_state.record = JevRunStateRecord("goal", "objective", "mission", hard_part="hard part", expert_depth=JevExpertDepth())
        empty_handoff = JevHandoffRecord(expert_depth=JevExpertDepthEvidence())
        projected, questions = run_state._section(JevDoneCheck.EXPERT_DEPTH, empty_handoff)
        self.assertEqual(projected, {"expert_details": {}})
        self.assertEqual(questions, ())
        empty_result = run_state._judge(JevDoneCheck.EXPERT_DEPTH, empty_handoff, None)
        self.assertTrue(empty_result.available and empty_result.passed)

    def test_handoff_rejects_missing_or_invented_detail_evidence_ids(self) -> None:
        run_state, _, identifiers = self._records()
        assert run_state.record is not None
        schema = JevHandoff.schema((JevDoneCheck.EXPERT_DEPTH,))
        handoff_agent = run_state.handoff_writer
        good_items = [{"id": identifier, "evidence": "The output shows the detail.", "missing": "Nothing is missing."} for identifier in identifiers]
        good = schema(expert_depth={"details": good_items})
        valid, evidence = handoff_agent._expert_depth_evidence_record(good, run_state.record)
        self.assertTrue(valid)
        self.assertEqual(evidence.ids(), identifiers)
        bad = schema(expert_depth={"details": [{**item, "id": "invented_detail"} if index == 0 else item for index, item in enumerate(good_items)]})
        valid, evidence = handoff_agent._expert_depth_evidence_record(bad, run_state.record)
        self.assertFalse(valid)
        self.assertIsNone(evidence)


class JevDoneRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verify the finish-attempt check, continuation, cap, and fail-open behavior through JevAgent."""

    def _agent(
        self,
        *,
        done: tuple[Any, ...] = (JevDoneCheck.MULTI_PART,),
        max_continuations: int = JEV_DONE_MAX_CONTINUATIONS,
        final_answer: str = "All done.",
        state: str = json.dumps(_STATE),
        handoff: str = json.dumps(_HANDOFF),
        state_error: Exception | None = None,
        **settings: Any,
    ) -> tuple[JevAgent, ScriptedGenerativeRunner, ScriptedGenerativeRunner, ScriptedGenerativeRunner]:
        main, state_runner, handoff_runner = ScriptedGenerativeRunner(final_answer), ScriptedGenerativeRunner(state, error=state_error), ScriptedGenerativeRunner(handoff)
        agent = bind_test_runner(_jev(done=done, max_continuations=max_continuations, **settings), main)
        assert agent.run_state is not None
        bind_test_runner(agent.run_state, state_runner)
        bind_test_runner(agent.run_state.handoff_writer, handoff_runner)
        return agent, main, state_runner, handoff_runner

    @staticmethod
    def _decision(readme: list[float], flag: float = 0.95, **kwargs: Any) -> ScriptedDecisionRunner:
        return ScriptedDecisionRunner({"dry_run_flag": [flag], "readme_docs": readme}, **kwargs)

    @staticmethod
    def _claims_decision(readme: list[float], deploy_test: list[float], **kwargs: Any) -> ScriptedDecisionRunner:
        return ScriptedDecisionRunner({"readme_updated.doc_added": readme, "deploy_test_added.doc_added": deploy_test}, **kwargs)

    async def test_self_review_runs_before_handoff_and_continues_a_standing_objection(self) -> None:
        review = {"objections": [{"id": "upload_guard", "objection": "upload() still runs during dry-run.", "resolved_when": "The dry-run test proves upload() is skipped."}]}
        handoff = {"self_review": {"objections": [{"id": "upload_guard", "evidence": "The test output shows upload() was skipped.", "missing": "Nothing is missing."}]}}
        decision = ScriptedDecisionRunner({"upload_guard": [0.1, 0.9]})
        agent, main, _, handoff_runner = self._agent(
            done=(JevDoneCheck.SELF_REVIEW,),
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(handoff),
        )
        assert agent.run_state is not None and agent.run_state.reviewer is not None
        review_runner = ScriptedGenerativeRunner(json.dumps(review))
        bind_test_runner(agent.run_state.reviewer, review_runner)
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual((len(review_runner.calls), len(handoff_runner.calls), len(main.calls)), (2, 2, 2))
        self.assertIn("upload_guard", handoff_runner.systems[0])
        result = agent.response.done[JevDoneCheck.SELF_REVIEW]
        self.assertTrue(result.passed and result.available)
        self.assertEqual(result.score, 0.9)
        self.assertEqual(agent.response.continuations, 1)
        feedback = main.messages[1][0]["content"]
        self.assertIn("upload() still runs during dry-run.", feedback)
        self.assertIn("Accept when: The dry-run test proves upload() is skipped.", feedback)

    async def test_reviewer_failure_leaves_other_checks_available(self) -> None:
        decision = self._decision([0.95])
        agent, main, _, handoff_runner = self._agent(
            done=(JevDoneCheck.MULTI_PART, JevDoneCheck.SELF_REVIEW),
            handoff=json.dumps({**_HANDOFF, "self_review": {"objections": []}}),
        )
        assert agent.run_state is not None and agent.run_state.reviewer is not None
        bind_test_runner(agent.run_state.reviewer, ScriptedGenerativeRunner(error=ProviderRequestError("review down", provider="openai")))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual((len(main.calls), len(handoff_runner.calls), len(decision.requests)), (1, 1, 1))
        self.assertIsNone(agent.response.review)
        self.assertIsNotNone(agent.response.handoff)
        self.assertTrue(agent.response.done[JevDoneCheck.MULTI_PART].passed)
        self.assertTrue(agent.response.done[JevDoneCheck.MULTI_PART].available)
        self.assertFalse(agent.response.done[JevDoneCheck.SELF_REVIEW].available)

    async def test_complete_run_finishes_after_one_check(self) -> None:
        decision = self._decision([0.9])
        agent, main, state_runner, handoff_runner = self._agent()
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            reply = await agent.arun(_REQUEST)

        self.assertEqual(reply.content, "All done.")
        self.assertEqual((len(main.calls), len(state_runner.calls), len(handoff_runner.calls)), (1, 1, 1))
        self.assertEqual(state_runner.calls[0], _REQUEST)
        response = agent.response
        assert response.run_state is not None and response.run_state.multi_part is not None
        self.assertEqual(response.run_state.multi_part.ids(), ("dry_run_flag", "readme_docs"))
        result = response.done[JevDoneCheck.MULTI_PART]
        self.assertTrue(result.passed and result.available)
        self.assertEqual(result.incomplete, ())
        self.assertEqual(response.continuations, 0)
        self.assertEqual((result.usage.input_tokens, result.usage.output_tokens), (100, 10))
        self.assertNotIn("done", reply.metadata)

    async def test_can_simplify_batches_with_multi_part_in_one_shared_request(self) -> None:
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.95], "readme_docs": [0.95], "implementation": [0.95]})
        agent, *_ = self._agent(
            done=(JevDoneCheck.MULTI_PART, JevDoneCheck.CAN_SIMPLIFY),
            state=json.dumps(_STATE_BOTH),
            handoff=json.dumps(_HANDOFF_BOTH),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        request = decision.requests[0]
        self.assertEqual(
            set(request.state),
            {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_IMPLEMENTATION_FIELD},
        )
        implementation = request.state[JEV_DONE_IMPLEMENTATION_FIELD][JEV_DONE_IMPLEMENTATION_FIELD]
        self.assertEqual(implementation["scope"], _CAN_SIMPLIFY_STATE["can_simplify"]["scope"])
        self.assertEqual(implementation[JEV_DONE_PRESERVATION_FIELD], _CAN_SIMPLIFY_STATE["can_simplify"]["preserve"])
        self.assertEqual(implementation[JEV_DONE_EVIDENCE_FIELD], _CAN_SIMPLIFY_HANDOFF["can_simplify"]["implementation"])
        self.assertEqual(sum(question.name.startswith("can_simplify.") for question in request.questions), 1)
        self.assertTrue(all(result.available and result.passed for result in agent.response.done.values()))

    async def test_can_simplify_failure_continues_with_candidate_and_preservation_requirements(self) -> None:
        decision = ScriptedDecisionRunner({"implementation": [0.2, 0.95]})
        agent, main, state_runner, handoff_runner = self._agent(
            done=(JevDoneCheck.CAN_SIMPLIFY,),
            state=json.dumps(_CAN_SIMPLIFY_STATE),
            handoff=json.dumps(_CAN_SIMPLIFY_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual((len(main.calls), len(state_runner.calls), len(handoff_runner.calls), len(decision.requests)), (2, 1, 2, 2))
        feedback = main.messages[1][0]["content"]
        self.assertIn(_CAN_SIMPLIFY_HANDOFF["can_simplify"]["missing"], feedback)
        self.assertIn(_CAN_SIMPLIFY_STATE["can_simplify"]["preserve"], feedback)
        self.assertIn("Apply this smaller approach", feedback)
        self.assertTrue(agent.response.done[JevDoneCheck.CAN_SIMPLIFY].available)
        self.assertTrue(agent.response.done[JevDoneCheck.CAN_SIMPLIFY].passed)

    async def test_can_simplify_passes_when_handoff_finds_no_supported_candidate(self) -> None:
        no_candidate = {
            "can_simplify": {
                "implementation": "The implementation was reviewed. The apparent alternatives would add branches or change the public contract; no supported material simplification was found.",
                "missing": "No change is needed for this check.",
            }
        }
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.CAN_SIMPLIFY,),
            state=json.dumps(_CAN_SIMPLIFY_STATE),
            handoff=json.dumps(no_candidate),
        )
        with patch(_RUNNER_PATH, new=_runner_class(ScriptedDecisionRunner({"implementation": [0.95]}))):
            await agent.arun(_REQUEST)

        self.assertEqual(len(main.calls), 1)
        result = agent.response.done[JevDoneCheck.CAN_SIMPLIFY]
        self.assertTrue(result.available and result.passed)
        self.assertEqual(result.incomplete, ())

    async def test_can_simplify_threshold_is_inclusive_and_provider_failure_fails_open(self) -> None:
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.CAN_SIMPLIFY,),
            state=json.dumps(_CAN_SIMPLIFY_STATE),
            handoff=json.dumps(_CAN_SIMPLIFY_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(ScriptedDecisionRunner({"implementation": [JEV_CAN_SIMPLIFY_THRESHOLD]}))):
            await agent.arun(_REQUEST)
        self.assertEqual(len(main.calls), 1)
        self.assertTrue(agent.response.done[JevDoneCheck.CAN_SIMPLIFY].passed)

        agent, main, *_ = self._agent(
            done=(JevDoneCheck.CAN_SIMPLIFY,),
            state=json.dumps(_CAN_SIMPLIFY_STATE),
            handoff=json.dumps(_CAN_SIMPLIFY_HANDOFF),
        )
        decision = ScriptedDecisionRunner(
            {"implementation": [0.1]},
            error=ProviderRequestError("down", provider="typesafe"),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)
        result = agent.response.done[JevDoneCheck.CAN_SIMPLIFY]
        self.assertEqual(len(main.calls), 1)
        self.assertFalse(result.available)
        self.assertTrue(result.passed)

    async def test_faithful_scope_uses_one_batched_answer_and_extends_configured_loop_after_failure(self) -> None:
        decision = ScriptedDecisionRunner({JEV_DONE_HARD_PART_FIELD: [0.79, 0.8], "dry_run_flag": [0.95], "readme_docs": [0.95]})
        loop = AgentLoopSettings(max_iterations=3, max_tokens=5_000)
        agent, main, state_runner, handoff_runner = self._agent(
            done=(JevDoneCheck.MULTI_PART, JevDoneCheck.FAITHFUL_SCOPE),
            state=json.dumps(_STATE),
            handoff=json.dumps({**_HANDOFF, **_FAITHFUL_HANDOFF}),
            loop=loop,
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual((len(main.calls), len(state_runner.calls), len(handoff_runner.calls)), (2, 1, 2))
        self.assertEqual(len(decision.requests), 2)
        first_request = decision.requests[0]
        assert isinstance(first_request.state, Mapping)
        self.assertEqual(first_request.state[JEV_DONE_HARD_PART_FIELD], _BASE_STATE[JEV_DONE_HARD_PART_FIELD])
        self.assertEqual(tuple(question.name for question in first_request.questions), ("multi_part.delivered.dry_run_flag", "multi_part.delivered.readme_docs", "faithful_scope.hard_part"))
        result = agent.response.done[JevDoneCheck.FAITHFUL_SCOPE]
        self.assertTrue(result.available and result.passed)
        self.assertEqual(agent.response.continuations, 1)
        self.assertEqual(agent.response.continuation_budget, {"max_iterations": 2, "max_tokens": 16_000})
        feedback = main.messages[1][0]["content"]
        self.assertIn(_BASE_STATE[JEV_DONE_HARD_PART_FIELD], feedback)
        self.assertIn(_FAITHFUL_HANDOFF["faithful_scope"]["missing"], feedback)

    async def test_faithful_scope_failure_at_continuation_cap_does_not_grant_budget(self) -> None:
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.FAITHFUL_SCOPE,),
            max_continuations=0,
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(_FAITHFUL_HANDOFF),
            loop=AgentLoopSettings(max_iterations=3, max_tokens=5_000, max_tool_calls=2),
        )
        with patch(_RUNNER_PATH, new=_runner_class(ScriptedDecisionRunner({JEV_DONE_HARD_PART_FIELD: [0.79]}))):
            await agent.arun(_REQUEST)

        self.assertEqual(len(main.calls), 1)
        self.assertEqual(agent.response.continuations, 0)
        self.assertEqual(agent.response.continuation_budget, {})
        self.assertFalse(agent.response.done[JevDoneCheck.FAITHFUL_SCOPE].passed)

    async def test_problem_repair_check_rechecks_after_handoff_and_returns_to_original_request(self) -> None:
        # The first finish fails an observed problem; the same loop receives focused repair guidance and checks again.
        decision = ScriptedDecisionRunner({"format_failure": [0.2, 0.97], "original_request_completion": [0.96, 0.98]})
        agent, main, state_runner, handoff_runner = self._agent(
            done=(JevDoneCheck.PROBLEMS_RESOLVED,),
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(_PROBLEMS_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual((len(main.calls), len(state_runner.calls), len(handoff_runner.calls), len(decision.requests)), (2, 1, 2, 2))
        assert agent.response.handoff is not None and agent.response.handoff.problems_resolved is not None
        self.assertEqual(agent.response.handoff.problems_resolved.problem_ids(), ("format_failure",))
        result = agent.response.done[JevDoneCheck.PROBLEMS_RESOLVED]
        self.assertTrue(result.available and result.passed)
        feedback = main.messages[1][0]["content"]
        self.assertIn(ProblemsResolvedQuestion().gap, feedback)
        self.assertIn("revalidate", feedback)
        self.assertIn(_REQUEST, feedback)
        self.assertIn("original request", feedback.lower())
        request_state = decision.requests[0].state
        assert isinstance(request_state, Mapping)
        items = request_state[JEV_DONE_PROBLEMS_RESOLVED_FIELD]["items"]
        self.assertEqual(set(items), {"format_failure", "original_request_completion"})
        self.assertEqual(set(items["format_failure"]), {"identity", "scope", "kind", "repair", "assertion", "evidence"})
        self.assertNotIn("missing", str(request_state))
        self.assertEqual(len(decision.requests[0].questions), 2)
        self.assertEqual(len(decision.requests[1].questions), 2)

    async def test_completion_evidence_is_handoff_only_and_judges_the_stable_task_item(self) -> None:
        decision = ScriptedDecisionRunner({JEV_DONE_COMPLETION_ITEM_ID: [0.9]})
        agent, *_ = self._agent(
            done=(JevDoneCheck.COMPLETION_EVIDENCE,),
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(_COMPLETION_EVIDENCE_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        request = decision.requests[0]
        question = JevDoneRegistry.question(JevDoneCheck.COMPLETION_EVIDENCE)
        self.assertEqual(tuple(item.name for item in request.questions), (question.name(JEV_DONE_COMPLETION_ITEM_ID),))
        self.assertEqual(set(request.state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_COMPLETION_EVIDENCE_FIELD})
        entry = request.state[JEV_DONE_COMPLETION_EVIDENCE_FIELD][JEV_DONE_COMPLETION_ITEM_ID]
        self.assertEqual(
            set(entry),
            {"completion_status", "requested_outcomes", "completed_work", "unfinished_or_blocked", "evidence"},
        )
        self.assertNotIn("missing", entry)
        result = agent.response.done[JevDoneCheck.COMPLETION_EVIDENCE]
        self.assertTrue(result.available and result.passed)
        self.assertEqual(result.incomplete, ())

    async def test_completion_evidence_continuation_names_the_status_and_run_gap(self) -> None:
        decision = ScriptedDecisionRunner({JEV_DONE_COMPLETION_ITEM_ID: [0.2, 0.98]})
        agent, main, state_runner, handoff_runner = self._agent(
            done=(JevDoneCheck.COMPLETION_EVIDENCE,),
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(_COMPLETION_EVIDENCE_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual((len(main.calls), len(decision.requests)), (2, 2))
        feedback = main.messages[1][0]["content"]
        self.assertIn("Requested outcomes: Add the dry-run flag; Document the flag in the README", feedback)
        self.assertIn("Work shown: The CLI accepts --dry-run.", feedback)
        self.assertIn("Unfinished or blocked: The README update is not shown.", feedback)
        self.assertIn("Evidence gap: The requested README explanation is unsupported by run evidence.", feedback)
        self.assertTrue(agent.response.done[JevDoneCheck.COMPLETION_EVIDENCE].passed)

    async def test_phase_progress_asks_for_request_stages_and_continues_only_for_the_failed_stage(self) -> None:
        decision = ScriptedDecisionRunner({"research": [0.2, 0.98]})
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.PHASE_PROGRESS,),
            state=json.dumps(_PHASE_STATE),
            handoff=json.dumps(_PHASE_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        question = JevDoneRegistry.question(JevDoneCheck.PHASE_PROGRESS)
        self.assertEqual(len(decision.requests), 2)
        request = decision.requests[0]
        self.assertEqual(tuple(item.name for item in request.questions), (question.name("research"),))
        self.assertEqual(set(request.state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_PHASE_PROGRESS_FIELD})
        self.assertEqual(
            set(request.state[JEV_DONE_PHASE_PROGRESS_FIELD]["research"]),
            {"stage", "required_result", "request_scope", "output_criterion", "evidence"},
        )
        feedback = main.messages[1][0]["content"]
        self.assertIn("Still missing: No comparison of three deployment options is shown.", feedback)
        self.assertIn("Requested stage: Research and compare deployment options.", feedback)
        self.assertNotIn("dry_run_flag", feedback)
        result = agent.response.done[JevDoneCheck.PHASE_PROGRESS]
        self.assertTrue(result.available and result.passed)
        self.assertEqual(result.incomplete, ())

    async def test_empty_phase_progress_skips_jev_and_passes(self) -> None:
        empty_state = {**_BASE_STATE, "phase_progress": {"stages": []}}
        empty_handoff = {"phase_progress": {"stages": []}}
        decision = ScriptedDecisionRunner({})
        agent, *_ = self._agent(
            done=(JevDoneCheck.PHASE_PROGRESS,),
            state=json.dumps(empty_state),
            handoff=json.dumps(empty_handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(decision.requests, [])
        result = agent.response.done[JevDoneCheck.PHASE_PROGRESS]
        self.assertTrue(result.available and result.passed)
        self.assertEqual(result.incomplete, ())

    async def test_problem_check_batches_with_other_enabled_checks(self) -> None:
        decision = ScriptedDecisionRunner({
            "dry_run_flag": [0.97],
            "readme_docs": [0.97],
            "format_failure": [0.97],
            "original_request_completion": [0.97],
        })
        combined = {**_HANDOFF, **_PROBLEMS_HANDOFF}
        agent, *_ = self._agent(done=(JevDoneCheck.MULTI_PART, JevDoneCheck.PROBLEMS_RESOLVED), handoff=json.dumps(combined))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        self.assertEqual(len(decision.requests[0].questions), 4)
        self.assertTrue(all(item.passed for item in agent.response.done.values()))
        self.assertEqual(set(decision.requests[0].state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_PROBLEMS_RESOLVED_FIELD})

    async def test_problem_check_focuses_failed_original_request_item(self) -> None:
        decision = ScriptedDecisionRunner({"format_failure": [0.97], "original_request_completion": [0.2, 0.97]})
        agent, main, *_ = self._agent(done=(JevDoneCheck.PROBLEMS_RESOLVED,), state=json.dumps(_BASE_STATE), handoff=json.dumps(_PROBLEMS_HANDOFF))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        focus = main.messages[1][0]["content"].split("# Focus", 1)[1]
        self.assertIn("request_completion", focus)
        self.assertIn("complete every remaining requested part after any repairs", focus)
        self.assertNotIn("Fully repair this problem", focus)
        self.assertTrue(agent.response.done[JevDoneCheck.PROBLEMS_RESOLVED].passed)

    async def test_no_observed_problem_still_requires_original_request_completion(self) -> None:
        completion_only = {"problems_resolved": {"items": [_REQUEST_ITEM]}}
        decision = ScriptedDecisionRunner({"original_request_completion": [0.98]})
        agent, *_ = self._agent(done=(JevDoneCheck.PROBLEMS_RESOLVED,), state=json.dumps(_BASE_STATE), handoff=json.dumps(completion_only))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        self.assertEqual(len(decision.requests[0].questions), 1)
        self.assertTrue(agent.response.done[JevDoneCheck.PROBLEMS_RESOLVED].passed)

    async def test_problem_handoff_without_required_completion_item_fails_open(self) -> None:
        malformed = {"problems_resolved": {"items": [_PROBLEM_ITEM]}}
        decision = ScriptedDecisionRunner({"format_failure": [0.98]})
        agent, main, _, handoff_runner = self._agent(done=(JevDoneCheck.PROBLEMS_RESOLVED,), state=json.dumps(_BASE_STATE), handoff=json.dumps(malformed))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual((len(main.calls), len(handoff_runner.calls), len(decision.requests)), (1, 1, 0))
        self.assertIsNone(agent.response.handoff)
        result = agent.response.done[JevDoneCheck.PROBLEMS_RESOLVED]
        self.assertFalse(result.available)
        self.assertTrue(result.passed)

    async def test_input_set_coverage_checks_tool_evidence_per_bounded_target(self) -> None:
        decision = ScriptedDecisionRunner({"incident_pages": [0.95]})
        agent, main, state_runner, handoff_runner = self._agent(
            done=(JevDoneCheck.INPUT_SET_COVERAGE,),
            state=json.dumps(_INPUT_STATE),
            handoff=json.dumps(_INPUT_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("Review pages 1 through 3 of the incident report.")

        self.assertEqual((len(main.calls), len(state_runner.calls), len(handoff_runner.calls)), (1, 1, 1))
        self.assertEqual(agent.response.done[JevDoneCheck.INPUT_SET_COVERAGE].incomplete, ())
        request = decision.requests[0]
        self.assertEqual(set(request.state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_INPUT_SET_COVERAGE_FIELD})
        entry = request.state[JEV_DONE_INPUT_SET_COVERAGE_FIELD]["incident_pages"]
        self.assertEqual(set(entry), {JEV_DONE_INPUT_IDENTITY_FIELD, JEV_DONE_INPUT_SCOPE_FIELD, JEV_DONE_INPUT_ACTION_FIELD, JEV_DONE_INPUT_ENGAGEMENT_SIGNAL_FIELD, JEV_DONE_EVIDENCE_FIELD})
        self.assertEqual(entry[JEV_DONE_EVIDENCE_FIELD], _INPUT_HANDOFF["input_set_coverage"]["targets"][0]["evidence"])
        self.assertNotIn("missing", entry)
        self.assertEqual([question.name for question in request.questions], ["input_set_coverage.engaged.incident_pages"])

    async def test_input_set_threshold_is_inclusive(self) -> None:
        decision = ScriptedDecisionRunner({"incident_pages": [JEV_INPUT_SET_COVERAGE_THRESHOLD]})
        agent, main, *_ = self._agent(done=(JevDoneCheck.INPUT_SET_COVERAGE,), state=json.dumps(_INPUT_STATE), handoff=json.dumps(_INPUT_HANDOFF))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("Review pages 1 through 3 of the incident report.")

        self.assertEqual(len(main.calls), 1)
        self.assertTrue(agent.response.done[JevDoneCheck.INPUT_SET_COVERAGE].passed)

    async def test_incomplete_input_target_continues_with_only_that_target_in_focus(self) -> None:
        incomplete_handoff = json.loads(json.dumps(_INPUT_HANDOFF))
        incomplete_handoff["input_set_coverage"]["targets"][0].update(
            evidence="Tool call list_pages() succeeded and returned page names 1, 2, and 3; no page content was returned.",
            missing="The full content of pages 1, 2, and 3 was not read or reviewed.",
        )
        decision = ScriptedDecisionRunner({"incident_pages": [0.1]})
        agent, main, *_ = self._agent(done=(JevDoneCheck.INPUT_SET_COVERAGE,), state=json.dumps(_INPUT_STATE), handoff=json.dumps(incomplete_handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("Review pages 1 through 3 of the incident report.")

        feedback = main.messages[1][0]["content"]
        self.assertIn(InputSetCoverageQuestion().gap, feedback)
        self.assertIn("The full content of pages 1, 2, and 3 was not read or reviewed.", feedback)
        self.assertIn("review incident report pages 1 through 3", feedback.split("# Focus", 1)[1])
        self.assertEqual(agent.response.done[JevDoneCheck.INPUT_SET_COVERAGE].incomplete, ("incident_pages",))
        self.assertEqual(agent.response.continuations, JEV_DONE_MAX_CONTINUATIONS)

    async def test_input_set_coverage_batches_with_other_enabled_checks(self) -> None:
        state = {**_STATE, "input_set_coverage": _INPUT_STATE["input_set_coverage"]}
        handoff = {**_HANDOFF, **_INPUT_HANDOFF}
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.95], "readme_docs": [0.95], "incident_pages": [0.95]})
        agent, *_ = self._agent(done=(JevDoneCheck.MULTI_PART, JevDoneCheck.INPUT_SET_COVERAGE), state=json.dumps(state), handoff=json.dumps(handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        request = decision.requests[0]
        self.assertEqual(set(request.state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_INPUT_SET_COVERAGE_FIELD})
        self.assertEqual(len(request.questions), 3)
        self.assertEqual(set(agent.response.done), {JevDoneCheck.MULTI_PART, JevDoneCheck.INPUT_SET_COVERAGE})
        self.assertTrue(all(result.passed for result in agent.response.done.values()))

    async def test_empty_input_set_passes_without_a_jev_question(self) -> None:
        empty_state = {**_BASE_STATE, "input_set_coverage": {"targets": []}}
        empty_handoff = {"input_set_coverage": {"targets": []}}
        decision = ScriptedDecisionRunner({})
        agent, main, *_ = self._agent(done=(JevDoneCheck.INPUT_SET_COVERAGE,), state=json.dumps(empty_state), handoff=json.dumps(empty_handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("What is an incident report?")

        self.assertEqual((len(main.calls), len(decision.requests)), (1, 0))
        self.assertTrue(agent.response.done[JevDoneCheck.INPUT_SET_COVERAGE].passed)

    async def test_input_handoff_with_missing_or_extra_ids_is_unavailable(self) -> None:
        wrong_handoff = {"input_set_coverage": {"targets": [{**_INPUT_HANDOFF["input_set_coverage"]["targets"][0], "id": "another_target"}]}}
        decision = ScriptedDecisionRunner({"incident_pages": [0.1]})
        agent, main, *_ = self._agent(done=(JevDoneCheck.INPUT_SET_COVERAGE,), state=json.dumps(_INPUT_STATE), handoff=json.dumps(wrong_handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("Review pages 1 through 3 of the incident report.")

        result = agent.response.done[JevDoneCheck.INPUT_SET_COVERAGE]
        self.assertEqual(len(main.calls), 1)
        self.assertFalse(result.available)
        self.assertTrue(result.passed)
        self.assertEqual(decision.requests, [])

    async def test_input_exhaustion_matches_the_requested_distinct_total(self) -> None:
        pages = tuple(f"page-{number}" for number in range(1, 42))
        handoff = _input_exhaustion_handoff(
            pages,
            last_position="page 41",
            outstanding_continuation=None,
            missing="Nothing is missing.",
            next_step="No next traversal step is indicated.",
        )
        decision = ScriptedDecisionRunner({"all_pages": [0.85]})
        agent, *_ = self._agent(done=(JevDoneCheck.INPUT_EXHAUSTION,), state=json.dumps(_INPUT_EXHAUSTION_STATE), handoff=json.dumps(handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertTrue(result.available and result.passed)
        self.assertEqual(result.incomplete, ())
        entry = decision.requests[0].state[JEV_DONE_INPUT_EXHAUSTION_FIELD]["all_pages"]
        self.assertEqual(entry["deterministic_assessment"], "Code compared 41 distinct visited page identifiers with the user's requested total of 41; the counts match.")
        self.assertNotIn("missing", entry)

    async def test_empty_collection_requires_affirmative_source_boundary(self) -> None:
        state = json.loads(json.dumps(_INPUT_EXHAUSTION_STATE))
        state["input_exhaustion"]["collections"][0].update({"unit": "record", "expected_total": 0})
        handoff = _input_exhaustion_handoff((), unit_type="record", outstanding_continuation=None)
        decision = ScriptedDecisionRunner({"all_pages": [0.99]})
        agent, *_ = self._agent(done=(JevDoneCheck.INPUT_EXHAUSTION,), state=json.dumps(state), handoff=json.dumps(handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertTrue(result.available)
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("all_pages",))

    async def test_duplicate_visited_ids_do_not_meet_source_total(self) -> None:
        state = json.loads(json.dumps(_INPUT_EXHAUSTION_STATE))
        state["input_exhaustion"]["collections"][0]["expected_total"] = None
        handoff = _input_exhaustion_handoff(("page-1", "page-1"), source_reported_total=2, outstanding_continuation=None)
        decision = ScriptedDecisionRunner({"all_pages": [0.99]})
        agent, *_ = self._agent(done=(JevDoneCheck.INPUT_EXHAUSTION,), state=json.dumps(state), handoff=json.dumps(handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("all_pages",))
        assessment = decision.requests[0].state[JEV_DONE_INPUT_EXHAUSTION_FIELD]["all_pages"]["deterministic_assessment"]
        self.assertIn("1 distinct visited page identifiers", assessment)

    async def test_terminal_evidence_can_establish_unknown_total(self) -> None:
        state = json.loads(json.dumps(_INPUT_EXHAUSTION_STATE))
        state["input_exhaustion"]["collections"][0]["expected_total"] = None
        handoff = _input_exhaustion_handoff(
            ("page-1",),
            outstanding_continuation=None,
            terminal_evidence="Tool output for the last cursor: end-of-results; no further pages.",
            missing="Nothing is missing.",
            next_step="No next traversal step is indicated.",
        )
        decision = ScriptedDecisionRunner({"all_pages": [0.95]})
        agent, *_ = self._agent(done=(JevDoneCheck.INPUT_EXHAUSTION,), state=json.dumps(state), handoff=json.dumps(handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertTrue(result.available and result.passed)
        self.assertEqual(result.incomplete, ())

    async def test_input_exhaustion_batches_with_multi_part_questions(self) -> None:
        pages = tuple(f"page-{number}" for number in range(1, 42))
        state = {**_STATE, **_INPUT_EXHAUSTION_STATE}
        handoff = {**_HANDOFF, **_input_exhaustion_handoff(pages, outstanding_continuation=None)}
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.95], "readme_docs": [0.95], "all_pages": [0.95]})
        agent, *_ = self._agent(done=(JevDoneCheck.MULTI_PART, JevDoneCheck.INPUT_EXHAUSTION), state=json.dumps(state), handoff=json.dumps(handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        request = decision.requests[0]
        self.assertEqual(len(request.questions), 3)
        self.assertEqual(set(request.state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_INPUT_EXHAUSTION_FIELD})
        self.assertTrue(all(result.passed for result in agent.response.done.values()))

    async def test_invalid_input_exhaustion_handoff_fails_open(self) -> None:
        malformed = {"input_exhaustion": {"collections": []}}
        decision = ScriptedDecisionRunner({"all_pages": [0.1]})
        agent, main, _, handoff_runner = self._agent(done=(JevDoneCheck.INPUT_EXHAUSTION,), state=json.dumps(_INPUT_EXHAUSTION_STATE), handoff=json.dumps(malformed))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertTrue(result.passed)
        self.assertFalse(result.available)
        self.assertEqual((len(main.calls), len(handoff_runner.calls), len(decision.requests)), (1, 1, 0))

    async def test_negative_coverage_accepts_an_evidence_backed_clean_inspection_in_one_batch(self) -> None:
        handoff = {
            **_HANDOFF,
            **_negative_coverage_handoff(
                inspection="Tool calls opened each requested cache invalidation module and the relevant tests; all were examined.",
                negative_conclusion="No unsafe invalidation behavior was found in the reviewed modules.",
                missing="Nothing is missing.",
            ),
        }
        state = {**_STATE, **_NEGATIVE_COVERAGE_STATE}
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.95], "readme_docs": [0.95], "cache_modules": [0.85]})
        agent, *_ = self._agent(
            done=(JevDoneCheck.MULTI_PART, JevDoneCheck.NEGATIVE_COVERAGE),
            state=json.dumps(state),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_NEGATIVE_COVERAGE_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        request = decision.requests[0]
        self.assertEqual(len(request.questions), 3)
        self.assertEqual(
            set(request.state),
            {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_NEGATIVE_COVERAGE_FIELD},
        )
        entry = request.state[JEV_DONE_NEGATIVE_COVERAGE_FIELD]["cache_modules"]
        self.assertEqual(entry["target"], "all cache invalidation modules")
        self.assertEqual(entry["inspection"], handoff["negative_coverage"]["inspections"][0]["inspection"])
        self.assertEqual(entry["negative_conclusion"], handoff["negative_coverage"]["inspections"][0]["negative_conclusion"])
        self.assertNotIn("missing", entry)
        result = agent.response.done[JevDoneCheck.NEGATIVE_COVERAGE]
        self.assertTrue(result.available and result.passed)

    async def test_negative_coverage_continues_for_an_unsupported_all_clear_report(self) -> None:
        handoff = _negative_coverage_handoff(negative_conclusion="No issues were found; all cache invalidation modules are clear.")
        decision = ScriptedDecisionRunner({"cache_modules": [0.84, 0.95]})
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.NEGATIVE_COVERAGE,),
            state=json.dumps(_NEGATIVE_COVERAGE_STATE),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_NEGATIVE_COVERAGE_REQUEST)

        self.assertEqual(agent.response.continuations, 1)
        feedback = main.messages[1][0]["content"]
        self.assertIn("all cache invalidation modules", feedback)
        self.assertIn("Read each requested module", feedback)
        self.assertIn("no visible inspection evidence", feedback)

    async def test_negative_coverage_continues_for_an_explicit_incomplete_inspection(self) -> None:
        handoff = _negative_coverage_handoff(incomplete_report="I did not inspect the legacy cache module.")
        decision = ScriptedDecisionRunner({"cache_modules": [0.8, 0.95]})
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.NEGATIVE_COVERAGE,),
            state=json.dumps(_NEGATIVE_COVERAGE_STATE),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_NEGATIVE_COVERAGE_REQUEST)

        self.assertEqual(agent.response.continuations, 1)
        self.assertIn("all cache invalidation modules", main.messages[1][0]["content"])
        self.assertIn("Read each requested module", main.messages[1][0]["content"])

    async def test_missing_inspection_alone_does_not_fail_negative_coverage(self) -> None:
        decision = ScriptedDecisionRunner({"cache_modules": [0.95]})
        agent, *_ = self._agent(
            done=(JevDoneCheck.NEGATIVE_COVERAGE,),
            state=json.dumps(_NEGATIVE_COVERAGE_STATE),
            handoff=json.dumps(_negative_coverage_handoff()),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_NEGATIVE_COVERAGE_REQUEST)

        result = agent.response.done[JevDoneCheck.NEGATIVE_COVERAGE]
        self.assertTrue(result.available and result.passed)

    async def test_empty_negative_coverage_passes_without_a_question(self) -> None:
        state = {**_BASE_STATE, "negative_coverage": {"inspections": []}}
        handoff = {"negative_coverage": {"inspections": []}}
        decision = ScriptedDecisionRunner({})
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.NEGATIVE_COVERAGE,),
            state=json.dumps(state),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("What is cache invalidation?")

        result = agent.response.done[JevDoneCheck.NEGATIVE_COVERAGE]
        self.assertEqual((len(main.calls), len(decision.requests)), (1, 0))
        self.assertTrue(result.available and result.passed)

    async def test_negative_coverage_handoff_with_wrong_target_id_fails_open(self) -> None:
        handoff = _negative_coverage_handoff(id="unrequested_target")
        decision = ScriptedDecisionRunner({"cache_modules": [0.1]})
        agent, main, _, handoff_runner = self._agent(
            done=(JevDoneCheck.NEGATIVE_COVERAGE,),
            state=json.dumps(_NEGATIVE_COVERAGE_STATE),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_NEGATIVE_COVERAGE_REQUEST)

        result = agent.response.done[JevDoneCheck.NEGATIVE_COVERAGE]
        self.assertTrue(result.passed)
        self.assertFalse(result.available)
        self.assertEqual((len(main.calls), len(handoff_runner.calls), len(decision.requests)), (1, 1, 0))

    async def test_guaranteed_actions_require_necessity_and_unfinished_and_batch_with_other_checks(self) -> None:
        handoff = {
            **_HANDOFF,
            **_guaranteed_next_actions_handoff([
                _guaranteed_next_action("unnecessary"),
                _guaranteed_next_action("already_done"),
                _guaranteed_next_action("still_needed"),
            ]),
        }
        decision = ScriptedDecisionRunner({
            "dry_run_flag": [0.95],
            "readme_docs": [0.95],
            "unnecessary": [0.89, 0.99, 0.1, 0.1],
            "already_done": [0.99, 0.899, 0.1, 0.1],
            "still_needed": [0.9, 0.9, 0.1, 0.1],
        })
        agent, main, _, handoff_runner = self._agent(
            done=(JevDoneCheck.MULTI_PART, JevDoneCheck.GUARANTEED_NEXT_ACTIONS),
            max_continuations=1,
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual((len(decision.requests), len(main.calls), len(handoff_runner.calls)), (2, 2, 2))
        request = decision.requests[0]
        self.assertEqual(len(request.questions), 8)
        self.assertEqual(
            set(request.state),
            {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_GUARANTEED_NEXT_ACTIONS_FIELD},
        )
        entries = request.state[JEV_DONE_GUARANTEED_NEXT_ACTIONS_FIELD]
        self.assertEqual(set(entries), {"unnecessary", "already_done", "still_needed"})
        self.assertNotIn("necessity_basis", str(request.state))
        necessary, unfinished = JevDoneRegistry.questions(JevDoneCheck.GUARANTEED_NEXT_ACTIONS)
        names = {question.name for question in request.questions}
        for identifier in entries:
            self.assertIn(necessary.name(identifier), names)
            self.assertIn(unfinished.name(identifier), names)

        feedback = main.messages[1][0]["content"]
        failed_feedback = feedback.split("# Failed checks", 1)[1].split("# Focus", 1)[0]
        self.assertIn("still_needed", failed_feedback)
        self.assertNotIn("unnecessary", failed_feedback)
        self.assertNotIn("already_done", failed_feedback)
        assert agent.response.handoff is not None and agent.response.run_state is not None
        assert agent.response.handoff.guaranteed_next_actions is not None
        self.assertFalse(hasattr(agent.response.handoff.guaranteed_next_actions.actions[0], "necessity_basis"))

        question_name = unfinished.name("still_needed")
        missing_answer = DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-1.13.0",
            answers={necessary.name("still_needed"): _answer(necessary.name("still_needed"), 0.99)},
            raw={},
        )
        unavailable = agent.run_state._guaranteed_next_actions(agent.response.handoff, missing_answer)
        self.assertFalse(unavailable.available)
        self.assertTrue(unavailable.passed)
        self.assertNotIn(question_name, unavailable.answers)

    async def test_empty_guaranteed_actions_add_no_questions(self) -> None:
        decision = ScriptedDecisionRunner({})
        agent, main, _, _ = self._agent(
            done=(JevDoneCheck.GUARANTEED_NEXT_ACTIONS,),
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(_guaranteed_next_actions_handoff([])),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("Run the requested test.")

        result = agent.response.done[JevDoneCheck.GUARANTEED_NEXT_ACTIONS]
        self.assertEqual((len(main.calls), len(decision.requests)), (1, 0))
        self.assertTrue(result.available and result.passed)

    async def test_request_quantity_is_checked_even_when_final_answer_omits_a_count(self) -> None:
        decision = ScriptedDecisionRunner({"cache_examples": [0.2]})
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.OUTPUT_COUNT,), final_answer="Done.",
            state=json.dumps(_OUTPUT_STATE), handoff=json.dumps(_OUTPUT_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_OUTPUT_REQUEST)

        request = decision.requests[0]
        entry = request.state[JEV_DONE_OUTPUT_COUNTS_FIELD]["cache_examples"]
        self.assertEqual((entry["observed_count"], entry["target_met"]), (10, False))
        self.assertEqual(len(entry["entries"]), 10)
        self.assertEqual(entry["obligation"]["target_count"], 25)
        self.assertEqual(request.questions[0].name, "output_count.satisfied.cache_examples")
        result = agent.response.done[JevDoneCheck.OUTPUT_COUNT]
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("cache_examples",))
        self.assertGreater(len(main.calls), 1)
        feedback = main.messages[1][0]["content"]
        self.assertIn("Only ten of the requested twenty-five", feedback)
        self.assertIn("Target: 25 examples", feedback)

    async def test_semantic_duplicate_keys_reduce_the_deterministic_count(self) -> None:
        handoff = json.loads(json.dumps(_OUTPUT_HANDOFF))
        entries = handoff["output_count"]["obligations"][0]["entries"]
        entries.extend({"id": f"extra_{index}", "value": f"A variation of cache strategy {index}.", "distinct_key": f"strategy_{(index - 1) % 10 + 1}", "evidence": f"Final answer paraphrase {index}."} for index in range(1, 16))
        decision = ScriptedDecisionRunner({"cache_examples": [0.2]})
        agent, *_ = self._agent(done=(JevDoneCheck.OUTPUT_COUNT,), state=json.dumps(_OUTPUT_STATE), handoff=json.dumps(handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_OUTPUT_REQUEST)

        entry = decision.requests[0].state[JEV_DONE_OUTPUT_COUNTS_FIELD]["cache_examples"]
        self.assertEqual(len(entry["entries"]), 25)
        self.assertEqual(entry["observed_count"], 10)
        self.assertFalse(entry["target_met"])
        self.assertFalse(agent.response.done[JevDoneCheck.OUTPUT_COUNT].passed)

    async def test_output_count_questions_are_batched_with_other_enabled_checks(self) -> None:
        handoff = {**_HANDOFF, **_OUTPUT_HANDOFF}
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.95], "readme_docs": [0.95], "cache_examples": [0.95]})
        state = {**_STATE, **_OUTPUT_STATE}
        agent, *_ = self._agent(done=(JevDoneCheck.MULTI_PART, JevDoneCheck.OUTPUT_COUNT), handoff=json.dumps(handoff), state=json.dumps(state))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_OUTPUT_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        names = [question.name for question in decision.requests[0].questions]
        self.assertEqual(len(names), 3)
        self.assertEqual(sum(name.startswith("output_count.satisfied.") for name in names), 1)
        self.assertIn(JEV_DONE_OUTPUT_COUNTS_FIELD, decision.requests[0].state)
        self.assertIn("deliverables", decision.requests[0].state)

    async def test_each_requested_group_gets_an_independent_quantity_obligation(self) -> None:
        grouped_state = json.loads(json.dumps(_OUTPUT_STATE))
        grouped_state["output_count"]["obligations"] = [
            {**_OUTPUT_STATE["output_count"]["obligations"][0], "id": "backend_examples", "target_count": 2, "scope": "backend cache strategies"},
            {**_OUTPUT_STATE["output_count"]["obligations"][0], "id": "frontend_examples", "target_count": 2, "scope": "frontend cache strategies"},
        ]
        grouped_handoff = {"output_count": {"obligations": [
            {"id": "backend_examples", "entries": [{"id": "backend_one", "value": "Invalidate by tag", "distinct_key": "tag", "evidence": "Final answer backend group."}], "missing": "One backend example is missing."},
            {"id": "frontend_examples", "entries": [{"id": "frontend_one", "value": "Invalidate on navigation", "distinct_key": "navigation", "evidence": "Final answer frontend group."}], "missing": "One frontend example is missing."},
        ]}}
        decision = ScriptedDecisionRunner({"backend_examples": [0.2], "frontend_examples": [0.2]})
        agent, *_ = self._agent(done=(JevDoneCheck.OUTPUT_COUNT,), state=json.dumps(grouped_state), handoff=json.dumps(grouped_handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_OUTPUT_REQUEST)

        state = decision.requests[0].state[JEV_DONE_OUTPUT_COUNTS_FIELD]
        self.assertEqual([question.name for question in decision.requests[0].questions], ["output_count.satisfied.backend_examples", "output_count.satisfied.frontend_examples"])
        self.assertEqual((state["backend_examples"]["target_met"], state["frontend_examples"]["target_met"]), (False, False))
        self.assertEqual(agent.response.done[JevDoneCheck.OUTPUT_COUNT].incomplete, ("backend_examples", "frontend_examples"))

    async def test_empty_output_quantity_obligations_pass_without_asking_jev(self) -> None:
        empty_state = {**_BASE_STATE, "output_count": {"obligations": []}}
        empty_handoff = {"output_count": {"obligations": []}}
        decision = ScriptedDecisionRunner({"unused": [0.1]})
        agent, _, *_ = self._agent(done=(JevDoneCheck.OUTPUT_COUNT,), state=json.dumps(empty_state), handoff=json.dumps(empty_handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("Explain what a cache is.")

        self.assertEqual(len(decision.requests), 0)
        self.assertTrue(agent.response.done[JevDoneCheck.OUTPUT_COUNT].passed)

    async def test_output_count_threshold_boundary_and_missing_handoff_fail_open(self) -> None:
        agent, *_ = self._agent(done=(JevDoneCheck.OUTPUT_COUNT,), state=json.dumps(_OUTPUT_STATE), handoff=json.dumps(_OUTPUT_COMPLETE_HANDOFF))
        with patch(_RUNNER_PATH, new=_runner_class(ScriptedDecisionRunner({"cache_examples": [JEV_OUTPUT_COUNT_THRESHOLD]}))):
            await agent.arun(_OUTPUT_REQUEST)
        self.assertTrue(agent.response.done[JevDoneCheck.OUTPUT_COUNT].passed)

        agent, *_ = self._agent(done=(JevDoneCheck.OUTPUT_COUNT,), state=json.dumps(_OUTPUT_STATE), handoff=json.dumps({}))
        with patch(_RUNNER_PATH, new=_runner_class(ScriptedDecisionRunner({"cache_examples": [0.1]}))):
            await agent.arun(_OUTPUT_REQUEST)
        self.assertFalse(agent.response.done[JevDoneCheck.OUTPUT_COUNT].available)
        self.assertTrue(agent.response.done[JevDoneCheck.OUTPUT_COUNT].passed)

    async def test_final_answer_under_minimum_fails_even_when_final_answer_omits_the_quota(self) -> None:
        state = {
            **_BASE_STATE,
            "output_extent": {"items": [{
                "id": "answer_words",
                "target": "the final answer",
                "amount": 25,
                "unit": "words",
                "comparator": "minimum",
            }]},
        }
        handoff = {"output_extent": {"items": [{
            "id": "answer_words",
            "evidence": "Final answer: All done.",
            "missing": "The final answer contains fewer than 25 words.",
        }]}}
        decision = ScriptedDecisionRunner({"answer_words": [0.99]})
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.OUTPUT_EXTENT,),
            final_answer="All done.",
            state=json.dumps(state),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.OUTPUT_EXTENT]
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("answer_words",))
        self.assertGreater(agent.response.continuations, 0)
        self.assertIn("requested minimum 25 words", main.messages[1][0]["content"])
        sent_state = decision.requests[0].state
        self.assertEqual(sent_state["output_extents"]["answer_words"]["observed"], 2)
        self.assertNotIn("missing", sent_state["output_extents"]["answer_words"])
        self.assertIn("Code measured the raw final answer directly", sent_state["output_extents"]["answer_words"]["evidence"])

    async def test_output_extent_questions_batch_with_existing_request_derived_checks(self) -> None:
        state = {
            **_STATE,
            "output_extent": {"items": [{
                "id": "answer_words",
                "target": "the final answer",
                "amount": 2,
                "unit": "words",
                "comparator": "minimum",
            }]},
        }
        handoff = {
            **_HANDOFF,
            "output_extent": {"items": [{
                "id": "answer_words",
                "evidence": "Final answer: All done.",
                "missing": "Nothing is missing.",
            }]},
        }
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.99], "readme_docs": [0.99], "answer_words": [0.99]})
        agent, *_ = self._agent(
            done=(JevDoneCheck.MULTI_PART, JevDoneCheck.OUTPUT_EXTENT),
            final_answer="All done.",
            state=json.dumps(state),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        request = decision.requests[0]
        self.assertEqual(len(request.questions), 3)
        self.assertEqual(
            set(request.state),
            {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, "output_extents"},
        )
        self.assertTrue(all(result.passed for result in agent.response.done.values()))

    async def test_report_action_alignment_batches_with_other_checks_and_uses_handoff_only_state(self) -> None:
        handoff = {**_HANDOFF, **_REPORT_ACTION_HANDOFF}
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.99], "readme_docs": [0.99], "manifest_update": [0.85]})
        agent, *_ = self._agent(
            done=(JevDoneCheck.MULTI_PART, JevDoneCheck.REPORT_ACTION_ALIGNMENT),
            state=json.dumps(_STATE),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        request = decision.requests[0]
        self.assertEqual(len(request.questions), 3)
        self.assertEqual(
            set(request.state),
            {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_REPORT_ACTION_ALIGNMENT_FIELD},
        )
        self.assertTrue(all(result.passed for result in agent.response.done.values()))

    async def test_report_action_alignment_continues_only_for_a_low_scored_candidate(self) -> None:
        missing = "Correct the inaccurate completion account for the still-required manifest field."
        handoff = json.loads(json.dumps(_REPORT_ACTION_HANDOFF))
        handoff["report_action_alignment"]["items"][0]["missing"] = missing
        decision = ScriptedDecisionRunner({"manifest_update": [0.84, 0.84]})
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.REPORT_ACTION_ALIGNMENT,),
            final_answer="I updated the manifest with the new field.",
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertGreaterEqual(len(decision.requests), 2)
        self.assertEqual(decision.requests[0].questions[0].name, "report_action_alignment.matched.manifest_update")
        self.assertEqual(agent.response.done[JevDoneCheck.REPORT_ACTION_ALIGNMENT].incomplete, ("manifest_update",))
        self.assertGreater(agent.response.continuations, 0)
        feedback = main.messages[1][0]["content"]
        self.assertIn("Earlier plan or commitment", feedback)
        self.assertIn("Recorded execution", feedback)
        self.assertIn("Relevance to the original request", feedback)
        self.assertIn(missing, feedback)

    async def test_empty_report_action_alignment_passes_without_a_question(self) -> None:
        handoff = {"report_action_alignment": {"items": []}}
        decision = ScriptedDecisionRunner({})
        agent, *_ = self._agent(
            done=(JevDoneCheck.REPORT_ACTION_ALIGNMENT,),
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 0)
        result = agent.response.done[JevDoneCheck.REPORT_ACTION_ALIGNMENT]
        self.assertTrue(result.passed)
        self.assertTrue(result.available)

    async def test_changed_assumptions_batch_with_request_check_at_inclusive_threshold(self) -> None:
        handoff = {**_HANDOFF, **_ASSUMPTIONS_HANDOFF}
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.99], "readme_docs": [0.99], "changed_limit": [0.8]})
        agent, *_ = self._agent(
            done=(JevDoneCheck.MULTI_PART, JevDoneCheck.ASSUMPTIONS_RECONCILED),
            state=json.dumps(_STATE),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        request = decision.requests[0]
        self.assertEqual(len(request.questions), 3)
        self.assertEqual(
            set(request.state),
            {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_ASSUMPTIONS_RECONCILED_FIELD},
        )
        item = request.state[JEV_DONE_ASSUMPTIONS_RECONCILED_FIELD]["items"]["changed_limit"]
        self.assertEqual(
            set(item),
            {"original_assumption", "original_basis", "later_observation", "affected_work", "revision", "evidence"},
        )
        self.assertNotIn("missing", str(request.state))
        self.assertTrue(all(result.passed for result in agent.response.done.values()))
        assert agent.response.handoff is not None
        self.assertEqual(agent.response.handoff.assumptions_reconciled.ids(), ("changed_limit",))

    async def test_changed_assumption_failure_focuses_only_failed_premise(self) -> None:
        handoff = json.loads(json.dumps(_ASSUMPTIONS_HANDOFF))
        handoff["assumptions_reconciled"]["items"][0]["missing"] = "The dependent client default is still 500."
        decision = ScriptedDecisionRunner({"changed_limit": [0.79]})
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.ASSUMPTIONS_RECONCILED,),
            final_answer="The client was updated.",
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.ASSUMPTIONS_RECONCILED]
        self.assertEqual(result.incomplete, ("changed_limit",))
        self.assertFalse(result.passed)
        self.assertGreater(agent.response.continuations, 0)
        feedback = main.messages[1][0]["content"]
        self.assertIn("Original assumption: The endpoint accepts page_size=500.", feedback)
        self.assertIn("Original basis:", feedback)
        self.assertIn("Later observation:", feedback)
        self.assertIn("Affected work:", feedback)
        self.assertIn("Later actions or results:", feedback)
        self.assertIn("The dependent client default is still 500.", feedback)

    async def test_empty_changed_assumptions_pass_without_a_question(self) -> None:
        handoff = {"assumptions_reconciled": {"items": []}}
        decision = ScriptedDecisionRunner({})
        agent, *_ = self._agent(
            done=(JevDoneCheck.ASSUMPTIONS_RECONCILED,),
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(decision.requests, [])
        result = agent.response.done[JevDoneCheck.ASSUMPTIONS_RECONCILED]
        self.assertTrue(result.available and result.passed)

    async def test_one_jev_request_holds_every_enabled_checks_questions(self) -> None:
        # [Review 4117808663] the enabled checks' questions are combined and sent to Jev at once with the handoff.
        decision = self._decision([0.9])
        agent, *_ = self._agent()
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        actual_batches = [tuple(question.name for question in request.questions) for request in decision.requests]
        self.assertEqual(
            len(actual_batches),
            1,
            msg=f"Jev continuation must send all enabled done-check questions for a finish attempt in one request; observed {len(actual_batches)} requests with question names {actual_batches!r}.",
        )
        if not actual_batches:
            return
        request = decision.requests[0]
        state = request.state
        assert isinstance(state, Mapping)
        self.assertEqual(set(state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD})
        self.assertEqual(state[JEV_DONE_REQUEST_FIELD], _REQUEST)
        entries = state[JEV_DONE_DELIVERABLES_FIELD]
        for entry, evidence in zip(_STATE["multi_part"]["deliverables"], _HANDOFF["multi_part"]["deliverables"], strict=True):  # type: ignore[index]
            self.assertEqual(set(entries[entry["id"]]), {JEV_DONE_DELIVERABLE_FIELD, JEV_DONE_COMPLETION_SIGNAL_FIELD, JEV_DONE_EVIDENCE_FIELD})
            self.assertEqual(entries[entry["id"]][JEV_DONE_DELIVERABLE_FIELD], entry["description"])
            self.assertEqual(entries[entry["id"]][JEV_DONE_EVIDENCE_FIELD], evidence["evidence"])
        prefix = JevDoneQuestionKey.MULTI_PART_DELIVERED.value
        expected_names = (f"{prefix}.dry_run_flag", f"{prefix}.readme_docs")
        self.assertEqual(
            actual_batches[0],
            expected_names,
            msg=f"The single Jev continuation request must contain one question for every required deliverable exactly once; expected {expected_names!r}, observed {actual_batches[0]!r}.",
        )

    async def test_claims_check_uses_final_answer_claims_and_tool_evidence(self) -> None:
        decision = self._claims_decision([0.95], [0.92])
        agent, main, state_runner, handoff_runner = self._agent(
            done=(JevDoneCheck.CLAIMS,),
            final_answer=_CLAIMED_FINAL_ANSWER,
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(_CLAIMS_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            reply = await agent.arun(_REQUEST)

        self.assertEqual(reply.content, _CLAIMED_FINAL_ANSWER)
        self.assertEqual((len(main.calls), len(state_runner.calls), len(handoff_runner.calls), len(decision.requests)), (1, 1, 1, 1))
        assert agent.response.run_state is not None
        assert agent.response.handoff is not None and agent.response.handoff.claims is not None
        self.assertIsNone(agent.response.run_state.multi_part)
        self.assertEqual(agent.response.handoff.claims.ids(), ("readme_updated", "deploy_test_added"))
        request = decision.requests[0]
        self.assertEqual(set(request.state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_CLAIMS_FIELD})
        claim_entries = request.state[JEV_DONE_CLAIMS_FIELD]
        self.assertEqual(set(claim_entries), {"readme_updated.doc_added", "deploy_test_added.doc_added"})
        self.assertEqual(set(claim_entries["readme_updated.doc_added"][JEV_DONE_CLAIM_FIELD]), {"identity", "scope", "kind", "output", "assertion"})
        self.assertEqual(claim_entries["readme_updated.doc_added"][JEV_DONE_CLAIM_FIELD]["identity"]["title"], "README updated")
        self.assertEqual(claim_entries["readme_updated.doc_added"][JEV_DONE_CLAIM_FIELD]["assertion"]["completion_criteria"], "A successful recorded edit to README.md contains an explanation of --dry-run.")
        self.assertEqual(claim_entries["readme_updated.doc_added"][JEV_DONE_EVIDENCE_FIELD], _CLAIMS["claims"][0]["evidence"])
        prefix = JevDoneQuestionKey.CLAIMS_SUPPORTED.value
        self.assertEqual([question.name for question in request.questions], [f"{prefix}.readme_updated.doc_added", f"{prefix}.deploy_test_added.doc_added"])
        result = agent.response.done[JevDoneCheck.CLAIMS]
        self.assertTrue(result.passed and result.available)
        self.assertEqual(result.incomplete, ())

    async def test_claims_failure_focuses_only_the_unsupported_claims(self) -> None:
        decision = self._claims_decision([0.99], [0.2])
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.CLAIMS,),
            final_answer=_CLAIMED_FINAL_ANSWER,
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(_CLAIMS_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertGreater(len(main.calls), 1)
        feedback = main.messages[1][0]["content"]
        self.assertIn(ClaimsSupportedQuestion().gap, feedback)
        self.assertIn("Unsupported assertion (doc_added): A test was added for the deploy command.", feedback)
        self.assertIn("No tool call shows a test file being written or edited.", feedback)
        self.assertNotIn("README updated", feedback.split("# Focus", 1)[1])
        result = agent.response.done[JevDoneCheck.CLAIMS]
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("deploy_test_added",))

    async def test_claims_score_assertions_separately_and_focus_only_the_failed_sibling(self) -> None:
        handoff = json.loads(json.dumps(_CLAIMS_HANDOFF))
        first_claim = handoff["claims"]["claims"][0]["claim"]
        first_claim["assertions"].append({
            "id": "content_visible",
            "statement": "The updated README content is visible in the final file.",
            "completion_criteria": "A recorded read of README.md shows the updated content.",
        })
        decision = ScriptedDecisionRunner({
            "readme_updated.doc_added": [0.99],
            "readme_updated.content_visible": [0.2],
            "deploy_test_added.doc_added": [0.99],
        })
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.CLAIMS,),
            final_answer=_CLAIMED_FINAL_ANSWER,
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.CLAIMS]
        self.assertEqual(set(result.answers), {"readme_updated.doc_added", "readme_updated.content_visible", "deploy_test_added.doc_added"})
        self.assertEqual(result.incomplete, ("readme_updated",))
        focus = main.messages[1][0]["content"].split("# Focus", 1)[1]
        self.assertIn("Unsupported assertion (content_visible)", focus)
        self.assertNotIn("Unsupported assertion (doc_added)", focus)

    async def test_empty_claim_list_passes_without_a_decision_request(self) -> None:
        empty_claims_handoff = {"claims": {"claims": []}}
        decision = self._claims_decision([0.1], [0.1])
        agent, main, *_ = self._agent(
            done=(JevDoneCheck.CLAIMS,),
            state=json.dumps(_BASE_STATE),
            handoff=json.dumps(empty_claims_handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("Explain what --dry-run means.")

        self.assertEqual((len(main.calls), len(decision.requests)), (1, 0))
        self.assertTrue(agent.response.done[JevDoneCheck.CLAIMS].passed)
        assert agent.response.handoff is not None and agent.response.handoff.claims is not None
        self.assertEqual(agent.response.handoff.claims.ids(), ())

    async def test_empty_claims_add_no_questions_when_another_check_is_enabled(self) -> None:
        empty_claims_handoff = {**_HANDOFF, "claims": {"claims": []}}
        decision = self._decision([0.96])
        agent, *_ = self._agent(
            done=(JevDoneCheck.MULTI_PART, JevDoneCheck.CLAIMS),
            handoff=json.dumps(empty_claims_handoff),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        self.assertTrue(all(question.name.startswith(f"{JevDoneQuestionKey.MULTI_PART_DELIVERED.value}.") for question in decision.requests[0].questions))
        self.assertTrue(agent.response.done[JevDoneCheck.CLAIMS].passed)

    async def test_claims_and_multi_part_questions_share_one_jev_request(self) -> None:
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.95], "readme_docs": [0.92], "readme_updated.doc_added": [0.97], "deploy_test_added.doc_added": [0.91]})
        agent, *_ = self._agent(
            done=(JevDoneCheck.MULTI_PART, JevDoneCheck.CLAIMS),
            final_answer=_CLAIMED_FINAL_ANSWER,
            handoff=json.dumps(_COMBINED_HANDOFF),
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        request = decision.requests[0]
        self.assertEqual(set(request.state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_CLAIMS_FIELD})
        self.assertEqual(len(request.questions), 4)
        self.assertTrue(all(result.passed for result in agent.response.done.values()))

    async def test_handoff_receives_the_request_state_and_main_agent_window(self) -> None:
        agent, _, _, handoff_runner = self._agent()
        with patch(_RUNNER_PATH, new=_runner_class(self._decision([0.9]))):
            await agent.arun(_REQUEST)

        self.assertEqual(handoff_runner.calls[0], _REQUEST)
        self.assertIn("dry_run_flag", handoff_runner.systems[0])
        self.assertIn("All done.", handoff_runner.systems[0])

    async def test_incomplete_deliverable_sends_the_main_agent_back_in_the_same_loop(self) -> None:
        decision = self._decision([0.2, 0.9])
        agent, main, _, handoff_runner = self._agent()
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            reply = await agent.arun(_REQUEST)

        self.assertEqual(reply.content, "All done.")
        self.assertEqual((len(main.calls), len(handoff_runner.calls)), (2, 2))
        prefix = JevDoneQuestionKey.MULTI_PART_DELIVERED.value
        expected_names = (f"{prefix}.dry_run_flag", f"{prefix}.readme_docs")
        actual_batches = [tuple(question.name for question in request.questions) for request in decision.requests]
        self.assertEqual(
            actual_batches,
            [expected_names, expected_names],
            msg=f"Each Jev continuation finish attempt must issue exactly one complete batch; expected {[expected_names, expected_names]!r}, observed {actual_batches!r}.",
        )
        feedback = main.messages[1][0]["content"]
        # [Review 4117856441] the original prompt, the run state, the handoff, and the failed Jev questions, with focus on what is missing.
        for section in ("# Original request", "# Run state", "# Handoff", "# Failed checks", "# Focus"):
            self.assertIn(section, feedback)
        self.assertIn(_REQUEST, feedback)
        self.assertIn('"objective":', feedback)
        self.assertIn("No part of the run concerns the README.", feedback)
        self.assertIn(MultiPartDeliveredQuestion().gap, feedback)
        self.assertIn("with id `readme_docs`? Jev's answer: no", feedback)
        self.assertIn("The README section for --dry-run.", feedback)
        # Each failed check opens with its shared gate description, and its failed Jev questions follow it.
        failed = feedback.split("# Failed checks", 1)[1].split("# Focus", 1)[0]
        description = JevDoneRegistry.description(JevDoneCheck.MULTI_PART)
        self.assertTrue(failed.strip().startswith(f"## Multi Part\n\n{description}\n\nWhat the check found:\n"))
        self.assertLess(failed.index(description), failed.index("with id `readme_docs`? Jev's answer: no"))
        for other in set(JevDoneCheck) - {JevDoneCheck.MULTI_PART}:
            self.assertNotIn(JevDoneRegistry.description(other), feedback)
        self.assertLess(feedback.index("# Goal"), feedback.index("# Original request"))
        focus = feedback.split("# Focus", 1)[1]
        self.assertIn("README documentation for the --dry-run flag.", focus)
        self.assertNotIn("A --dry-run flag on the deploy CLI.", focus)
        self.assertEqual(agent.response.continuations, 1)
        self.assertTrue(agent.response.done[JevDoneCheck.MULTI_PART].passed)

    async def test_continuations_are_capped_and_the_latest_failure_is_recorded(self) -> None:
        agent, main, *_ = self._agent()
        with patch(_RUNNER_PATH, new=_runner_class(self._decision([0.1]))):
            await agent.arun(_REQUEST)

        self.assertEqual(len(main.calls), JEV_DONE_MAX_CONTINUATIONS + 1)
        self.assertEqual(agent.response.continuations, JEV_DONE_MAX_CONTINUATIONS)
        result = agent.response.done[JevDoneCheck.MULTI_PART]
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("readme_docs",))
        self.assertEqual(agent.response.continuation_budget, {})

    async def test_threshold_is_inclusive_and_one_clear_no_fails_a_passing_mean(self) -> None:
        agent, main, *_ = self._agent()
        with patch(_RUNNER_PATH, new=_runner_class(self._decision([JEV_MULTI_PART_THRESHOLD], flag=JEV_MULTI_PART_THRESHOLD))):
            await agent.arun(_REQUEST)
        self.assertEqual(len(main.calls), 1)

        agent, main, *_ = self._agent()
        with patch(_RUNNER_PATH, new=_runner_class(self._decision([0.7, 0.9], flag=1.0))):
            await agent.arun(_REQUEST)
        self.assertEqual(len(main.calls), 2)

    async def test_run_state_failure_fails_open_with_no_check(self) -> None:
        decision = self._decision([0.1])
        agent, main, _, handoff_runner = self._agent(state_error=ProviderRequestError("down", provider="openai"))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            reply = await agent.arun(_REQUEST)

        self.assertEqual(reply.content, "All done.")
        self.assertEqual((len(main.calls), len(handoff_runner.calls), len(decision.requests)), (1, 0, 0))
        self.assertIsNone(agent.response.run_state)
        self.assertEqual(agent.response.done, {})

    async def test_handoff_that_misses_a_deliverable_is_unavailable(self) -> None:
        partial = {"multi_part": {"deliverables": _HANDOFF["multi_part"]["deliverables"][:1]}}  # type: ignore[index]
        decision = self._decision([0.1])
        agent, main, *_ = self._agent(handoff=json.dumps(partial))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual((len(main.calls), len(decision.requests)), (1, 0))
        self.assertIsNone(agent.response.handoff)
        result = agent.response.done[JevDoneCheck.MULTI_PART]
        self.assertFalse(result.available)
        self.assertTrue(result.passed)

    async def test_jev_failure_fails_open(self) -> None:
        agent, main, *_ = self._agent()
        with patch(_RUNNER_PATH, new=_runner_class(self._decision([0.1], error=ProviderRequestError("down", provider="typesafe")))):
            await agent.arun(_REQUEST)

        self.assertEqual(len(main.calls), 1)
        self.assertFalse(agent.response.done[JevDoneCheck.MULTI_PART].available)

    async def test_missing_decision_credentials_fail_open(self) -> None:
        main = ScriptedGenerativeRunner("All done.")
        agent = bind_test_runner(JevAgent(_settings(), JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.MULTI_PART,)))), main)
        assert agent.run_state is not None
        bind_test_runner(agent.run_state, ScriptedGenerativeRunner(json.dumps(_STATE)))
        bind_test_runner(agent.run_state.handoff_writer, ScriptedGenerativeRunner(json.dumps(_HANDOFF)))
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": ""}, clear=False):
            await agent.arun(_REQUEST)

        self.assertEqual(len(main.calls), 1)
        self.assertFalse(agent.response.done[JevDoneCheck.MULTI_PART].available)

    async def test_request_with_no_deliverables_passes_without_asking_jev(self) -> None:
        empty = {**_STATE, "multi_part": {"deliverables": []}}
        decision = self._decision([0.1])
        agent, main, *_ = self._agent(state=json.dumps(empty), handoff=json.dumps({"multi_part": {"deliverables": []}}))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("Hello!")

        self.assertEqual((len(main.calls), len(decision.requests)), (1, 0))
        self.assertTrue(agent.response.done[JevDoneCheck.MULTI_PART].passed)

    async def test_disabled_done_checks_make_no_extra_calls(self) -> None:
        main = ScriptedGenerativeRunner("All done.")
        agent = bind_test_runner(_jev(done=()), main)
        reply = await agent.arun(_REQUEST)

        self.assertEqual((reply.content, len(main.calls)), ("All done.", 1))
        self.assertIsNone(agent.response.run_state)
        self.assertEqual(agent.response.done, {})

    async def test_a_chosen_specialist_runs_without_done_checks(self) -> None:
        specialist_runner = ScriptedGenerativeRunner("migration written")
        specialist = JevSpecialist("database", "Changes to the database schema and its migrations.", bind_test_runner(BaseAgent(name="database", system_prompt="Change the schema.", provider="openai", model_name="gpt-4.1-mini"), specialist_runner))
        agent, main, state_runner, _ = self._agent(agents=(specialist,))

        class ChoosingRunner(ScriptedDecisionRunner):
            async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
                question = request.questions[0]
                answer = JevAnswer(question_name=question.name, question_type=JevQuestionType.CHOICE, choice="database", probabilities={"database": 1.0, "none": 0.0}, confidence=1.0)
                return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers={question.name: answer}, raw={})

        with patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_runner_class(ChoosingRunner({}))):
            reply = await agent.arun("Add a migration for the email column.")

        self.assertEqual(reply.content, "migration written")
        self.assertEqual((len(main.calls), len(state_runner.calls)), (0, 0))


class JevSelfReviewIntegrationTests(unittest.TestCase):
    """Pin objection batching, the resolved-or-out-of-scope clearance rule, and fail-open distinctions."""

    @staticmethod
    def _review() -> JevReviewRecord:
        return JevReviewRecord((
            JevObjection("out_of_scope", "The reviewer found an optional improvement.", "The request does not ask for this work."),
            JevObjection("standing_gap", "A requested path still fails.", "The requested path passes its regression test."),
        ))

    @staticmethod
    def _evidence(review: JevReviewRecord) -> JevHandoffRecord:
        return JevHandoffRecord(self_review=JevSelfReviewEvidence(tuple(
            JevObjectionEvidence(item.id, "The run evidence for this objection.", "The acceptance condition is not shown.")
            for item in review.objections
        )))

    @staticmethod
    def _decision(review: JevReviewRecord) -> DecisionModelResponse:
        resolved, in_scope = JevDoneRegistry.questions(JevDoneCheck.SELF_REVIEW)
        probabilities = {
            "out_of_scope": (0.1, 0.2),
            "standing_gap": (0.1, 0.9),
        }
        answers = {}
        for identifier, (resolved_yes, in_scope_yes) in probabilities.items():
            for question, yes in ((resolved, resolved_yes), (in_scope, in_scope_yes)):
                name = question.name(identifier)
                answers[name] = _answer(name, yes)
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={})

    def test_two_answers_batch_per_objection_and_clearance_uses_out_of_scope_probability(self) -> None:
        agent = _jev(done=(JevDoneCheck.SELF_REVIEW,))
        assert agent.run_state is not None
        run_state = agent.run_state
        review = self._review()
        handoff = self._evidence(review)
        run_state.request = _REQUEST
        run_state.review = review

        section, questions = run_state._self_review_section(handoff)
        resolved, in_scope = JevDoneRegistry.questions(JevDoneCheck.SELF_REVIEW)
        self.assertEqual(tuple(question.name for question in questions), tuple(
            question.name(identifier)
            for identifier in review.ids()
            for question in (resolved, in_scope)
        ))
        request = run_state.combine(handoff)
        assert request is not None
        self.assertEqual(request.state["objections"], section["objections"])
        self.assertEqual(len(request.questions), 4)

        result = run_state._self_review(handoff, self._decision(review))
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.SELF_REVIEW), JEV_SELF_REVIEW_THRESHOLD)
        self.assertEqual(result.score, (JEV_SELF_REVIEW_THRESHOLD + 0.1) / 2)
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("standing_gap",))

    def test_valid_empty_review_passes_but_missing_review_or_evidence_is_unavailable(self) -> None:
        agent = _jev(done=(JevDoneCheck.SELF_REVIEW,))
        assert agent.run_state is not None
        run_state = agent.run_state
        empty = JevReviewRecord()
        empty_handoff = JevHandoffRecord(self_review=JevSelfReviewEvidence())
        run_state.review = empty
        result = run_state._self_review(empty_handoff, None)
        self.assertTrue(result.passed and result.available)
        self.assertIsNone(result.score)
        self.assertFalse(run_state._self_review(None, None).available)
        run_state.review = None
        self.assertFalse(run_state._self_review(empty_handoff, None).available)

    def test_handoff_requires_exact_review_objection_ids(self) -> None:
        agent = _jev(done=(JevDoneCheck.SELF_REVIEW,))
        assert agent.run_state is not None
        review = self._review()
        payload = agent.run_state.handoff_writer.payload(
            self_review={
                "objections": [{
                    "id": "invented_objection",
                    "evidence": "The run evidence is present.",
                    "missing": "Nothing is missing.",
                }]
            }
        )

        valid, evidence = agent.run_state.handoff_writer._self_review_evidence(payload, review)
        self.assertFalse(valid)
        self.assertEqual(evidence.ids(), ("invented_objection",))

    def test_question_pair_is_registered_and_uses_one_literal_module_text(self) -> None:
        questions = JevDoneRegistry.questions(JevDoneCheck.SELF_REVIEW)
        self.assertEqual(len(questions), 2)
        self.assertIs(JevDoneRegistry.question(JevDoneCheck.SELF_REVIEW), questions[0])
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.SELF_REVIEW), JEV_SELF_REVIEW_THRESHOLD)
        self.assertEqual(tuple(JevDoneRegistry.question_for_key(question.key) for question in questions), questions)
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/self_review.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])


if __name__ == "__main__":
    unittest.main()
