"""FILE: tests/test_jev_done.py

PURPOSE: Verifies JevAgent's done checks deterministically without live model calls: run-state and handoff schemas, request-derived and post-run claim records, fixed questions, shared state, trace evidence, batched Jev requests, continuation, and fail-open behavior.
ROLE IN CODEBASE: Pins the Jev done-check contracts: records live in vidbyte/lib, every structured-output field carries a 4-6 sentence description, the handoff reads the main agent's window through ContextManager, and every enabled check's questions share one Jev request.
ARCHITECTURE NOTE: Scripted generative and decision runners replace only the external boundaries while production settings, registry, schemas, runtime hook, and response wiring stay active.
COMMON MODIFICATION PATTERNS: Add cases for every new done check's schema, question, threshold boundary, dynamic or request-derived items, and availability policy.
KNOWN EDGE CASES: No test may contact TypeSafe or a generative provider; the token-floor test needs tiktoken and is skipped without it.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-input-exhaustion-done-criteria.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
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
from typing import Any
from unittest.mock import patch

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
    JevClaimAssertion,
    JevClaimContext,
    JevClaimEvidence,
    JevClaimIdentity,
    JevClaimKind,
    JevClaimScope,
    JevClaimsEvidence,
    JevContinualSettings,
    JevDoneCheck,
    JevInputExhaustion,
    JevInputExhaustionEvidence,
    JevInputExhaustionObligation,
    JevProblemResolutionItem,
    JevProblemsResolvedEvidence,
    JevRuntimeSettings,
    JevSpecialist,
)
from vidbyte.agents.jev.continuation import JevContinuation, JevDoneContinuation
from vidbyte.agents.jev.done import JevHandoff, JevRunState
from vidbyte.context.primitives import (
    ResponseContextItem,
    TextContextItem,
    ToolCallContextItem,
)
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_CLAIMS_THRESHOLD,
    JEV_DONE_CLAIM_FIELD,
    JEV_DONE_CLAIMS_FIELD,
    JEV_DONE_COMPLETION_SIGNAL_FIELD,
    JEV_DONE_DELIVERABLE_FIELD,
    JEV_DONE_DELIVERABLES_FIELD,
    JEV_DONE_EVIDENCE_FIELD,
    JEV_DONE_INPUT_EXHAUSTION_FIELD,
    JEV_DONE_MAX_CONTINUATIONS,
    JEV_DONE_PROBLEMS_RESOLVED_FIELD,
    JEV_DONE_REQUEST_FIELD,
    JEV_MULTI_PART_THRESHOLD,
    JEV_INPUT_EXHAUSTION_THRESHOLD,
    JEV_PROBLEMS_RESOLVED_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevBrief,
    JevClaimAssertionPayload,
    JevClaimContextPayload,
    JevClaimEvidencePayload,
    JevClaimIdentityPayload,
    JevClaimScopePayload,
    JevClaimsEvidencePayload,
    JevCriterion,
    JevDecisionRequest,
    JevDeliverable,
    JevDeliverableEvidencePayload,
    JevDeliverablePayload,
    JevDoneQuestion,
    JevDoneResult,
    JevHandoffPayload,
    JevInputExhaustionEvidencePayload,
    JevInputExhaustionEvidenceSection,
    JevInputExhaustionObligationPayload,
    JevInputExhaustionPayload,
    JevMultiPart,
    JevMultiPartEvidencePayload,
    JevMultiPartPayload,
    JevProblemEvidencePayload,
    JevProblemsResolvedEvidencePayload,
    JevRunStatePayload,
    JevRunStateRecord,
    JevSectionPayload,
    JevTargetOutcomeEvidenceItemPayload,
    JevTargetOutcomeEvidencePayload,
    JevTargetOutcomeItemPayload,
    JevTargetOutcomePayload,
)
from vidbyte.lib.enums import JevDoneQuestionKey, JevQuestionType, ModelProvider
from vidbyte.lib.enums.jev import JevProblemCheckItemType
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.lib.jev import JevDoneRegistry
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.done import (
    DONE_STATE,
    ClaimsSupportedQuestion,
    MultiPartDeliveredQuestion,
    InputExhaustionTraversedQuestion,
    ProblemsResolvedQuestion,
)
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
    "what_not_to_do": ["Do not change other commands."],
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
_INPUT_EXHAUSTION_STATE = {
    **_BASE_STATE,
    "input_exhaustion": {"collections": [{
        "id": "all_pages",
        "collection": "the report pages",
        "scope": "all 41 pages of the report",
        "unit": "page",
        "expected_total": 41,
        "exhaustion_condition": "The report's final page is reached and no page remains.",
    }]},
}


def _input_exhaustion_handoff(visited: tuple[str, ...] = tuple(f"page-{number}" for number in range(1, 11)), **overrides: Any) -> dict[str, Any]:
    """Return realistic handoff evidence for the 41-page request, with selected trace facts overridable by tests."""
    collection: dict[str, Any] = {
        "id": "all_pages",
        "evidence": f"Successful page fetches observed these identifiers: {', '.join(visited)}.",
        "unit_type": "page",
        "visited_unit_ids": list(visited),
        "source_reported_total": None,
        "last_position": "page 10" if visited else None,
        "outstanding_continuation": None,
        "terminal_evidence": None,
        "failed_retrievals": [],
        "missing": "The trace does not establish all 41 pages were visited.",
        "next_step": "Continue requesting report pages after page 10 and capture the final page response.",
    }
    collection.update(overrides)
    return {"input_exhaustion": {"collections": [collection]}}
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


def _jev(done: tuple[Any, ...] = (JevDoneCheck.MULTI_PART,), *, max_continuations: int = JEV_DONE_MAX_CONTINUATIONS, **settings: Any) -> JevAgent:
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
        for cls in (JevDeliverable, JevMultiPart, JevInputExhaustionObligation, JevInputExhaustion, JevInputExhaustionEvidence, JevRunStateRecord, JevDoneResult, JevRunStatePayload, JevMultiPartPayload):
            self.assertEqual(cls.__module__, "vidbyte.lib.dataclasses.jev")
        self.assertEqual(JevDoneCheck.__module__, "vidbyte.lib.enums.jev")
        self.assertFalse((_REPOSITORY_ROOT / "vidbyte/agents/jev/run_state.py").exists())
        self.assertFalse((_REPOSITORY_ROOT / "vidbyte/agents/jev/builders.py").exists())

    def test_every_structured_output_field_has_a_four_to_six_sentence_description(self) -> None:
        # [Review 4116725548] every field carries a pre-defined 4-6 sentence description used in the structured output.
        models = (JevRunStatePayload, JevMultiPartPayload, JevDeliverablePayload, JevMultiPartEvidencePayload, JevDeliverableEvidencePayload, JevInputExhaustionObligationPayload, JevInputExhaustionPayload, JevInputExhaustionEvidencePayload, JevInputExhaustionEvidenceSection, JevClaimIdentityPayload, JevClaimScopePayload, JevClaimAssertionPayload, JevClaimContextPayload, JevClaimEvidencePayload, JevClaimsEvidencePayload, JevProblemEvidencePayload, JevProblemsResolvedEvidencePayload, JevTargetOutcomeItemPayload, JevTargetOutcomePayload, JevTargetOutcomeEvidenceItemPayload, JevTargetOutcomeEvidencePayload)
        for model in models:
            for name, description in _descriptions(model).items():
                with self.subTest(model=model.__name__, field=name):
                    self.assertIn(_sentences(description), range(4, 7))
        for model in (JevClaimIdentityPayload, JevClaimScopePayload, JevClaimAssertionPayload, JevClaimContextPayload, JevClaimEvidencePayload):
            for name, description in _descriptions(model).items():
                with self.subTest(model=model.__name__, field=name):
                    self.assertEqual(_sentences(description), 5)
        for section in (JevMultiPartPayload, JevMultiPartEvidencePayload, JevInputExhaustionPayload, JevInputExhaustionEvidenceSection, JevClaimsEvidencePayload, JevProblemsResolvedEvidencePayload, JevTargetOutcomePayload, JevTargetOutcomeEvidencePayload):
            with self.subTest(section=section.__name__):
                self.assertIn(_sentences(section.SECTION), range(4, 7))

    def test_multi_part_is_its_own_dataclass_and_payload(self) -> None:
        # [Review 4116727218] the multi-part section is a separate dataclass, not a nested dict inside the state.
        self.assertTrue(issubclass(JevMultiPartPayload, JevSectionPayload))
        self.assertNotIn("multi_part", JevRunStatePayload.model_fields)
        record = JevRunStateRecord("goal", "objective", "mission", multi_part=JevMultiPart((JevDeliverable("a", "b", "c"),)))
        self.assertIsInstance(record.multi_part, JevMultiPart)

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
            JevRunStateRecord("goal", " ", "mission")

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

    def test_input_exhaustion_records_keep_request_totals_and_reject_duplicate_ids(self) -> None:
        obligation = JevInputExhaustionObligation("all_pages", "report pages", "all pages", "page", 41, "Reach the final page.")
        self.assertEqual(JevInputExhaustion((obligation,)).ids(), ("all_pages",))
        state = JevRunStateRecord("goal", "objective", "mission", input_exhaustion=JevInputExhaustion((obligation,)))
        self.assertEqual(state.input_exhaustion.collections[0].expected_total, 41)  # type: ignore[union-attr]
        with self.assertRaises(ConfigurationError):
            JevInputExhaustion((obligation, obligation))
        with self.assertRaises(ConfigurationError):
            JevInputExhaustionObligation("all_pages", "report pages", "all pages", "page", True, "Reach the final page.")
        evidence = JevInputExhaustionEvidence("all_pages", "Visited page 1.", "page", ("page-1",), None, "page 1", None, None, (), "More evidence is needed.", "Request the next page.")
        self.assertEqual(evidence.visited_unit_ids, ("page-1",))
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


class JevDoneSchemaTests(unittest.TestCase):
    """Pin that one JevRunState and one JevHandoff compose their schemas from the enabled checks."""

    def test_run_state_schema_contains_only_checks_with_request_derived_items(self) -> None:
        # CLAIMS are statements written after work, so the run-state model must not predict them from the request.
        self.assertEqual(set(JevRunState.schema(()).model_fields), {"goal", "objective", "mission", "what_not_to_do"})
        schema = JevRunState.schema((JevDoneCheck.MULTI_PART,))
        self.assertTrue(issubclass(schema, JevRunStatePayload))
        self.assertEqual(schema.model_fields["multi_part"].description, JevMultiPartPayload.SECTION)
        self.assertEqual(set(JevRunState.schema((JevDoneCheck.CLAIMS,)).model_fields), {"goal", "objective", "mission", "what_not_to_do"})
        exhaustion = JevRunState.schema((JevDoneCheck.INPUT_EXHAUSTION,))
        self.assertEqual(exhaustion.model_fields["input_exhaustion"].description, JevInputExhaustionPayload.SECTION)
        self.assertEqual(set(JevRunState._SECTIONS), {JevDoneCheck.MULTI_PART, JevDoneCheck.INPUT_EXHAUSTION, JevDoneCheck.TARGET_OUTCOME})
        self.assertEqual(set(JevRunState.schema((JevDoneCheck.CLAIMS, JevDoneCheck.PROBLEMS_RESOLVED)).model_fields), {"goal", "objective", "mission", "what_not_to_do"})
        self.assertEqual(set(JevRunState._SECTIONS), {JevDoneCheck.MULTI_PART, JevDoneCheck.INPUT_EXHAUSTION, JevDoneCheck.TARGET_OUTCOME})

    def test_handoff_schema_has_a_section_for_every_enabled_check(self) -> None:
        # Request-derived deliverables and post-run-derived claims both need evidence sections in the handoff.
        self.assertEqual(JevHandoff.schema(()).model_fields, {})
        schema = JevHandoff.schema((JevDoneCheck.MULTI_PART,))
        self.assertTrue(issubclass(schema, JevHandoffPayload))
        self.assertEqual(schema.model_fields["multi_part"].description, JevMultiPartEvidencePayload.SECTION)
        self.assertEqual(set(JevDeliverableEvidencePayload.model_fields), {"id", "evidence", "missing"})
        claim_schema = JevHandoff.schema((JevDoneCheck.CLAIMS,))
        self.assertEqual(claim_schema.model_fields["claims"].description, JevClaimsEvidencePayload.SECTION)
        exhaustion_schema = JevHandoff.schema((JevDoneCheck.INPUT_EXHAUSTION,))
        self.assertEqual(exhaustion_schema.model_fields["input_exhaustion"].description, JevInputExhaustionEvidenceSection.SECTION)
        self.assertEqual(set(exhaustion_schema.model_fields["input_exhaustion"].annotation.model_fields), {"collections"})
        problem_schema = JevHandoff.schema((JevDoneCheck.PROBLEMS_RESOLVED,))
        self.assertEqual(problem_schema.model_fields[JEV_DONE_PROBLEMS_RESOLVED_FIELD].description, JevProblemsResolvedEvidencePayload.SECTION)
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
        for field_name, bad in (("max_continuations", -1), ("max_continuations", True), ("run_state_max_tokens", 0), ("handoff_max_iterations", 2.5)):
            with self.subTest(field=field_name, bad=bad), self.assertRaises(ConfigurationError):
                JevContinualSettings(**{field_name: bad})


class JevDoneQuestionTests(unittest.TestCase):
    """Pin the multi-part question to the asking-jev-questions layout (review 4116786437)."""

    question = MultiPartDeliveredQuestion()

    def test_question_is_an_argument_free_registered_dataclass(self) -> None:
        self.assertIsInstance(self.question, JevDoneQuestion)
        self.assertEqual(MultiPartDeliveredQuestion(), self.question)
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.MULTI_PART), self.question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.MULTI_PART), JEV_MULTI_PART_THRESHOLD)
        rendered = self.question.to_question("readme_docs")
        self.assertEqual((rendered.name, rendered.question_type), (f"{JevDoneQuestionKey.MULTI_PART_DELIVERED.value}.readme_docs", JevQuestionType.NOUL))
        self.assertIn("with id `readme_docs`?", str(rendered.instructions))

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

        parts = [self.question.instructions.render(), self.question.gap]
        for criterion in (self.question.when_true, self.question.when_false):
            parts += [criterion.what, criterion.not_for, *criterion.easy, *criterion.boundary]
        self.assertGreaterEqual(len(tiktoken.get_encoding("cl100k_base").encode("\n".join(parts))), 2_000)

    def test_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/multi_part.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])

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

    def test_input_exhaustion_question_is_registered_and_scoped_to_one_collection(self) -> None:
        question = InputExhaustionTraversedQuestion()
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.INPUT_EXHAUSTION), question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.INPUT_EXHAUSTION), JEV_INPUT_EXHAUSTION_THRESHOLD)
        rendered = question.to_question("all_pages")
        self.assertEqual(rendered.name, f"{JevDoneQuestionKey.INPUT_EXHAUSTION_TRAVERSED.value}.all_pages")
        self.assertEqual(rendered.question_type, JevQuestionType.NOUL)
        self.assertEqual(question.instructions.state, DONE_STATE)
        self.assertIn("`expected_total`", question.instructions.definitions[0])
        self.assertIn("must contain affirmative terminal evidence", question.instructions.rules[1])
        self.assertIn("An absent next-page call", " ".join(question.instructions.rules))

    def test_input_exhaustion_criteria_mirror_the_completion_boundary(self) -> None:
        question = InputExhaustionTraversedQuestion()
        self.assertTrue(question.when_true.what.startswith("Choose true when `evidence` establishes"))
        self.assertTrue(question.when_true.not_for.endswith("belong to false."))
        self.assertTrue(question.when_false.what.startswith("Choose false when the readable trace evidence does not establish"))
        self.assertTrue(question.when_false.not_for.endswith("belong to true."))
        true_boundary = question.when_true.boundary[0]
        false_boundary = question.when_false.boundary[0]
        self.assertEqual(true_boundary.replace("41 distinct", "40 distinct"), false_boundary)
        self.assertIn("Easy:", question.when_true.easy[0])
        self.assertIn("Easy:", question.when_false.easy[0])

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_input_exhaustion_question_carries_at_least_two_thousand_tokens(self) -> None:
        import tiktoken

        question = InputExhaustionTraversedQuestion()
        parts = [question.instructions.render(), question.gap]
        for criterion in (question.when_true, question.when_false):
            parts += [criterion.what, criterion.not_for, *criterion.easy, *criterion.boundary]
        self.assertGreaterEqual(len(tiktoken.get_encoding("cl100k_base").encode("\n".join(parts))), 2_000)

    def test_input_exhaustion_question_has_no_implicit_string_concatenation(self) -> None:
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/done/input_exhaustion.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])

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

    def test_continuation_prompt_repairs_then_returns_to_original_request(self) -> None:
        prompt = Prompts().get(Prompt.JEV_CONTINUATION_CONTINUE_PROMPT)
        self.assertIn("fully repair it and successfully revalidate", prompt)
        self.assertIn("return to the original request and complete every remaining part", prompt)


class JevHandoffWindowTests(unittest.TestCase):
    """Pin that the handoff reads the main agent's window through the SDK's context manager (review 4116765507)."""

    def test_window_holds_the_state_responses_tool_calls_and_final_answer(self) -> None:
        call = ToolCallContext(tool_name="edit_file", arguments={"path": "README.md"}, state=ToolCallState.SUCCEEDED, result=ToolResult.success("edit_file", "updated"))
        items = JevHandoff.window('{"goal": "g"}', ("Working on it.", " "), (call,), "Done.", sender="jev").items()
        self.assertEqual([type(item) for item in items], [TextContextItem, ResponseContextItem, ToolCallContextItem, TextContextItem])
        self.assertEqual(items[0].content, '{"goal": "g"}')
        self.assertEqual((items[1].content, items[1].sender), ("Working on it.", "jev"))
        self.assertEqual((items[2].name, items[2].output), ("edit_file", "updated"))
        self.assertEqual(items[3].content, "Done.")


class JevDoneRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verify the finish-attempt check, continuation, cap, and fail-open behavior through JevAgent."""

    def _agent(
        self,
        *,
        done: tuple[Any, ...] = (JevDoneCheck.MULTI_PART,),
        final_answer: str = "All done.",
        state: str = json.dumps(_STATE),
        handoff: str = json.dumps(_HANDOFF),
        state_error: Exception | None = None,
        max_continuations: int = JEV_DONE_MAX_CONTINUATIONS,
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

    async def test_input_exhaustion_matches_the_users_requested_total(self) -> None:
        pages = tuple(f"page-{number}" for number in range(1, 42))
        handoff = _input_exhaustion_handoff(pages, last_position="page 41", missing="Nothing is missing.", next_step="No next traversal step is indicated.")
        decision = ScriptedDecisionRunner({"all_pages": [0.95]})
        agent, main, _, _ = self._agent(
            done=(JevDoneCheck.INPUT_EXHAUSTION,),
            state=json.dumps(_INPUT_EXHAUSTION_STATE),
            handoff=json.dumps(handoff),
            final_answer="All done.",
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertTrue(result.passed and result.available)
        self.assertEqual(result.incomplete, ())
        self.assertEqual((len(decision.requests), len(decision.requests[0].questions), len(main.calls)), (1, 1, 1))
        state = decision.requests[0].state[JEV_DONE_INPUT_EXHAUSTION_FIELD]
        self.assertEqual(state["all_pages"]["expected_total"], 41)
        self.assertEqual(state["all_pages"]["deterministic_assessment"], "Code compared 41 distinct visited page identifiers with the user's requested total of 41; the counts match.")
        self.assertNotIn("missing", state["all_pages"])

    async def test_zero_expected_units_need_affirmative_empty_source_evidence(self) -> None:
        state = json.loads(json.dumps(_INPUT_EXHAUSTION_STATE))
        state["input_exhaustion"]["collections"][0].update({"unit": "record", "expected_total": 0})
        handoff = _input_exhaustion_handoff((), unit_type="record", source_reported_total=None, terminal_evidence=None)
        decision = ScriptedDecisionRunner({"all_pages": [0.99]})
        agent, main, _, _ = self._agent(
            done=(JevDoneCheck.INPUT_EXHAUSTION,),
            state=json.dumps(state),
            handoff=json.dumps(handoff),
            max_continuations=0,
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertTrue(result.available)
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("all_pages",))
        self.assertEqual((len(main.calls), len(decision.requests)), (1, 1))

    async def test_ten_of_forty_one_pages_without_a_final_answer_claim_continues(self) -> None:
        # A generic final answer and a readable partial trace cannot substitute for the user's explicit 41-page scope.
        handoff = _input_exhaustion_handoff()
        decision = ScriptedDecisionRunner({"all_pages": [0.99]})
        agent, main, _, _ = self._agent(
            done=(JevDoneCheck.INPUT_EXHAUSTION,),
            state=json.dumps(_INPUT_EXHAUSTION_STATE),
            handoff=json.dumps(handoff),
            final_answer="All done.",
            max_continuations=1,
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertTrue(result.available)
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("all_pages",))
        self.assertEqual((len(decision.requests), len(main.calls), agent.response.continuations), (2, 2, 1))
        feedback = main.messages[1][0]["content"]
        self.assertIn("Collection: the report pages", feedback)
        self.assertIn("Last known position: page 10.", feedback)
        self.assertIn("Continue requesting report pages after page 10", feedback)
        self.assertIn("all 41 pages of the report", feedback)

    async def test_unknown_total_without_terminal_signal_is_incomplete_not_unavailable(self) -> None:
        state = json.loads(json.dumps(_INPUT_EXHAUSTION_STATE))
        state["input_exhaustion"]["collections"][0]["expected_total"] = None
        state["input_exhaustion"]["collections"][0]["exhaustion_condition"] = "The source explicitly reports that no results remain."
        handoff = _input_exhaustion_handoff(("page-1",), last_position="page 1")
        decision = ScriptedDecisionRunner({"all_pages": [0.99]})
        agent, _, _, _ = self._agent(
            done=(JevDoneCheck.INPUT_EXHAUSTION,),
            state=json.dumps(state),
            handoff=json.dumps(handoff),
            final_answer="The requested review is finished.",
            max_continuations=1,
        )
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertTrue(result.available)
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("all_pages",))
        self.assertIn("no comparable source total or affirmative terminal signal", decision.requests[0].state[JEV_DONE_INPUT_EXHAUSTION_FIELD]["all_pages"]["deterministic_assessment"])

    async def test_distinct_id_count_does_not_count_duplicate_pages_twice(self) -> None:
        state = json.loads(json.dumps(_INPUT_EXHAUSTION_STATE))
        obligation = state["input_exhaustion"]["collections"][0]
        obligation["expected_total"] = None
        handoff = _input_exhaustion_handoff(("page-1", "page-1"), source_reported_total=2, unit_type="page", last_position="page 1")
        decision = ScriptedDecisionRunner({"all_pages": [0.99]})
        agent, _, _, _ = self._agent(done=(JevDoneCheck.INPUT_EXHAUSTION,), state=json.dumps(state), handoff=json.dumps(handoff), max_continuations=1)
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("all_pages",))
        self.assertIn("1 distinct visited page identifiers", decision.requests[0].state[JEV_DONE_INPUT_EXHAUSTION_FIELD]["all_pages"]["deterministic_assessment"])

    async def test_unknown_total_with_affirmative_terminal_evidence_can_pass(self) -> None:
        state = json.loads(json.dumps(_INPUT_EXHAUSTION_STATE))
        state["input_exhaustion"]["collections"][0]["expected_total"] = None
        handoff = _input_exhaustion_handoff(("page-1",), terminal_evidence="Tool output for the last cursor: end-of-results; no further pages.", last_position="page 1", missing="Nothing is missing.", next_step="No next traversal step is indicated.")
        decision = ScriptedDecisionRunner({"all_pages": [0.95]})
        agent, *_ = self._agent(done=(JevDoneCheck.INPUT_EXHAUSTION,), state=json.dumps(state), handoff=json.dumps(handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        result = agent.response.done[JevDoneCheck.INPUT_EXHAUSTION]
        self.assertTrue(result.passed and result.available)
        self.assertEqual(result.incomplete, ())

    async def test_input_exhaustion_batches_with_multi_part_questions(self) -> None:
        state = {**_STATE, **_INPUT_EXHAUSTION_STATE}
        handoff = {**_HANDOFF, **_input_exhaustion_handoff(tuple(f"page-{number}" for number in range(1, 42)))}
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.95], "readme_docs": [0.95], "all_pages": [0.95]})
        agent, *_ = self._agent(done=(JevDoneCheck.MULTI_PART, JevDoneCheck.INPUT_EXHAUSTION), state=json.dumps(state), handoff=json.dumps(handoff))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
        request = decision.requests[0]
        self.assertEqual(set(request.state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_INPUT_EXHAUSTION_FIELD})
        self.assertEqual(len(request.questions), 3)
        self.assertEqual(sum(question.name.startswith(f"{JevDoneQuestionKey.INPUT_EXHAUSTION_TRAVERSED.value}.") for question in request.questions), 1)
        self.assertTrue(all(result.passed for result in agent.response.done.values()))

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


if __name__ == "__main__":
    unittest.main()
