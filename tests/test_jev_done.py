"""FILE: tests/test_jev_done.py

PURPOSE: Verifies JevAgent's done checks deterministically without live model calls: the run-state and handoff schemas and their field descriptions, the records built from them, the multi-part done question and its registry, the two generative prompts, the handoff's context window, and JevRuntime's finish-attempt behavior (pass, send back to work, bounded continuations, and fail-open paths).
ROLE IN CODEBASE: Pins the review of PR #452: records and enums live in vidbyte/lib, every structured-output field carries a 4-6 sentence description, JevRunState composes one schema from the enabled checks, JevHandoff reads the main agent's window through a ContextManager, and every enabled check's fixed questions go to Jev in one request (review of PR #470).
ARCHITECTURE NOTE: Scripted generative and decision runners replace only the external boundaries while production settings, registry, schemas, runtime hook, and response wiring stay active.
COMMON MODIFICATION PATTERNS: Add a case for every new done check, section, question, threshold boundary, and availability policy.
KNOWN EDGE CASES: No test may contact TypeSafe or a generative provider; the token-floor test needs tiktoken and is skipped without it.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-expert-depth-done-criteria.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
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
from lint.rules.s062_no_implicit_string_concatenation import ImplicitConcatenationScanner
from tests.agent_test_support import bind_test_runner
from vidbyte import (
    BaseAgent,
    JevAgent,
    JevAgentSettings,
    JevContinualSettings,
    JevDoneCheck,
    JevRuntimeSettings,
    JevSpecialist,
)
from vidbyte.agents.jev.continuation import JevContinuation, JevDoneContinuation
from vidbyte.agents.jev.done import JevHandoff, JevRunState
from vidbyte.context.primitives import ResponseContextItem, TextContextItem, ToolCallContextItem
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_DONE_COMPLETION_SIGNAL_FIELD,
    JEV_DONE_DELIVERABLE_FIELD,
    JEV_DONE_DELIVERABLES_FIELD,
    JEV_DONE_DETAIL_FIELD,
    JEV_DONE_DONE_WHEN_FIELD,
    JEV_DONE_EVIDENCE_FIELD,
    JEV_DONE_EXPERT_DETAILS_FIELD,
    JEV_DONE_MAX_CONTINUATIONS,
    JEV_DONE_REQUEST_FIELD,
    JEV_DONE_SHALLOW_VERSION_FIELD,
    JEV_EXPERT_DEPTH_FOCUS_LIMIT,
    JEV_EXPERT_DEPTH_MAX_DETAILS,
    JEV_EXPERT_DEPTH_MIN_DETAILS,
    JEV_EXPERT_DEPTH_THRESHOLD,
    JEV_MULTI_PART_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevBrief,
    JevCriterion,
    JevDecisionRequest,
    JevDeliverable,
    JevDeliverableEvidencePayload,
    JevDeliverablePayload,
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
    JevHandoffPayload,
    JevMultiPart,
    JevMultiPartEvidencePayload,
    JevMultiPartPayload,
    JevRunStatePayload,
    JevRunStateRecord,
    JevSectionPayload,
)
from vidbyte.lib.enums import JevDoneQuestionKey, JevQuestionType, ModelProvider
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.lib.jev import JevDoneRegistry
from vidbyte.lib.jev.done import DONE_STATE, ExpertDepthHandledQuestion, MultiPartDeliveredQuestion
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext, ToolCallState, ToolResult

_RUNNER_PATH = "vidbyte.agents.jev.done.run_state.DecisionModelRunner"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SENTENCE_END = re.compile(r"[.?](?=\s+[A-Z`]|$)")
_REQUEST = "Add a --dry-run flag to the deploy CLI and document it in the README."
_STATE = {
    "goal": "The deploy CLI can preview a deploy without changing anything, and users can read how.",
    "objective": "A working --dry-run flag in the deploy CLI and a README section that documents it.",
    "mission": "Change only the deploy CLI and its README, and keep every existing flag working.",
    "what_not_to_do": ["Do not change other commands."],
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
    """Records every decision request and answers each deliverable's question from a script of P(yes) values per finish attempt, keyed by deliverable id."""

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
            values = self.script[question.name.rsplit(".", 1)[-1]]
            yes = values.pop(0) if len(values) > 1 else values[0]
            answers[question.name] = _answer(question.name, yes)
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 100, "output_tokens": 10})


def _runner_class(scripted: ScriptedDecisionRunner) -> type:
    # Stands in for DecisionModelRunner: construction returns the scripted runner, while score_noul stays real.
    class ScriptedRunnerClass:
        score_noul = staticmethod(DecisionModelRunner.score_noul)

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedDecisionRunner:  # type: ignore[misc]
            return scripted

    return ScriptedRunnerClass


def _answer(name: str, yes: float) -> JevAnswer:
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if yes >= 0.5 else "false", probabilities={"true": yes, "false": 1.0 - yes}, noul=yes)


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {"name": "jev", "system_prompt": "Work carefully.", "provider": "openai", "model_name": "gpt-4.1-mini"}
    values.update(overrides)
    return JevAgentSettings(**values)


def _jev(done: tuple[Any, ...] = (JevDoneCheck.MULTI_PART,), **settings: Any) -> JevAgent:
    return JevAgent(_settings(**settings), JevRuntimeSettings(decision=DecisionModelConfig(api_key="test-key"), continual=JevContinualSettings(checks=done)))


def _sentences(text: str) -> int:
    return len(_SENTENCE_END.findall(text.strip()))


def _descriptions(model: type[BaseModel]) -> dict[str, str]:
    return {name: str(info.description) for name, info in model.model_fields.items()}


def _prompt_sections(prompt: Prompt) -> dict[str, str]:
    text = Prompts().get(prompt)
    sections = re.split(r"^# (\w+)\s*$", text, flags=re.M)[1:]
    return {sections[index]: sections[index + 1].strip() for index in range(0, len(sections), 2)}


class JevDoneRecordTests(unittest.TestCase):
    """Pin the lib records and structured-reply payloads the review moved out of vidbyte/agents/jev."""

    def test_records_and_enums_live_in_lib(self) -> None:
        # [Review 4116720422] dataclasses and enums belong in vidbyte/lib, per AGENTS.md.
        for cls in (JevDeliverable, JevMultiPart, JevRunStateRecord, JevDoneResult, JevRunStatePayload, JevMultiPartPayload, JevExpertDetail, JevExpertDepthDeliverable, JevExpertDepth, JevExpertDetailEvidence, JevExpertDepthEvidence, JevExpertDepthPayload, JevExpertDepthEvidencePayload):
            self.assertEqual(cls.__module__, "vidbyte.lib.dataclasses.jev")
        self.assertEqual(JevDoneCheck.__module__, "vidbyte.lib.enums.jev")
        self.assertFalse((_REPOSITORY_ROOT / "vidbyte/agents/jev/run_state.py").exists())
        self.assertFalse((_REPOSITORY_ROOT / "vidbyte/agents/jev/builders.py").exists())

    def test_every_structured_output_field_has_a_four_to_six_sentence_description(self) -> None:
        # [Review 4116725548] every field carries a pre-defined 4-6 sentence description used in the structured output.
        for model in (JevRunStatePayload, JevMultiPartPayload, JevDeliverablePayload, JevMultiPartEvidencePayload, JevDeliverableEvidencePayload, JevExpertDepthPayload, JevExpertDepthDeliverablePayload, JevExpertDetailPayload, JevExpertDepthEvidencePayload, JevExpertDetailEvidencePayload):
            for name, description in _descriptions(model).items():
                with self.subTest(model=model.__name__, field=name):
                    self.assertIn(_sentences(description), range(4, 7))
        for section in (JevMultiPartPayload, JevMultiPartEvidencePayload, JevExpertDepthPayload, JevExpertDepthEvidencePayload):
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
        for cls in (JevDeliverable, JevMultiPart, JevRunStateRecord, JevExpertDetail, JevExpertDepthDeliverable, JevExpertDepth, JevExpertDetailEvidence, JevExpertDepthEvidence):
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


class JevDoneSchemaTests(unittest.TestCase):
    """Pin that one JevRunState and one JevHandoff compose their schemas from the enabled checks."""

    def test_run_state_schema_adds_one_described_section_per_enabled_check(self) -> None:
        # [Review 4116740515, 4116749760] one class, no class per shape: enabling an enum option adds its section.
        self.assertEqual(set(JevRunState.schema(()).model_fields), {"goal", "objective", "mission", "what_not_to_do"})
        schema = JevRunState.schema((JevDoneCheck.MULTI_PART,))
        self.assertTrue(issubclass(schema, JevRunStatePayload))
        self.assertEqual(schema.model_fields["multi_part"].description, JevMultiPartPayload.SECTION)
        self.assertEqual(set(JevRunState._SECTIONS), set(JevDoneCheck))

    def test_handoff_schema_is_general_with_a_tailored_section_per_check(self) -> None:
        # [Review 4116760518, 4116773073] the handoff is general; the multi-part evidence shape is tailored to its check.
        self.assertEqual(JevHandoff.schema(()).model_fields, {})
        schema = JevHandoff.schema((JevDoneCheck.MULTI_PART,))
        self.assertTrue(issubclass(schema, JevHandoffPayload))
        self.assertEqual(schema.model_fields["multi_part"].description, JevMultiPartEvidencePayload.SECTION)
        self.assertEqual(set(JevDeliverableEvidencePayload.model_fields), {"id", "evidence", "missing"})
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

    def _agent(self, *, state: str = json.dumps(_STATE), handoff: str = json.dumps(_HANDOFF), state_error: Exception | None = None, **settings: Any) -> tuple[JevAgent, ScriptedGenerativeRunner, ScriptedGenerativeRunner, ScriptedGenerativeRunner]:
        main, state_runner, handoff_runner = ScriptedGenerativeRunner("All done."), ScriptedGenerativeRunner(state, error=state_error), ScriptedGenerativeRunner(handoff)
        agent = bind_test_runner(_jev(**settings), main)
        assert agent.run_state is not None
        bind_test_runner(agent.run_state, state_runner)
        bind_test_runner(agent.run_state.handoff_writer, handoff_runner)
        return agent, main, state_runner, handoff_runner

    @staticmethod
    def _decision(readme: list[float], flag: float = 0.95, **kwargs: Any) -> ScriptedDecisionRunner:
        return ScriptedDecisionRunner({"dry_run_flag": [flag], "readme_docs": readme}, **kwargs)

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

    async def test_one_jev_request_holds_every_enabled_checks_questions(self) -> None:
        # [Review 4117808663] the enabled checks' questions are combined and sent to Jev at once with the handoff.
        decision = self._decision([0.9])
        agent, *_ = self._agent()
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual(len(decision.requests), 1)
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
        self.assertEqual([question.name for question in request.questions], [f"{prefix}.dry_run_flag", f"{prefix}.readme_docs"])

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

        with patch("vidbyte.agents.jev.gate.gate.DecisionModelRunner", new=_runner_class(ChoosingRunner({}))):
            reply = await agent.arun("Add a migration for the email column.")

        self.assertEqual(reply.content, "migration written")
        self.assertEqual((len(main.calls), len(state_runner.calls)), (0, 0))


_DEPTH_REQUEST = "Add retries to the HTTP client in client/http.py."
_DEPTH_DETAILS = [
    {"id": "retry_idempotent_only", "detail": "Retries only calls that are safe to repeat.", "shallow_version": "Every failed request is retried, including POST.", "done_when": "The retry wrapper retries only GET, HEAD, PUT, and DELETE, and sends a POST once.", "risk": "A retried POST can charge a customer twice."},
    {"id": "retry_backoff", "detail": "Exponential backoff between retries.", "shallow_version": "Retries fire immediately, one after another.", "done_when": "The delay before each retry doubles with every attempt.", "risk": "Immediate retries hammer a server that is already struggling."},
    {"id": "retry_cap", "detail": "A cap on the number of attempts.", "shallow_version": "A failed request is retried until it succeeds.", "done_when": "Retries stop after a fixed maximum number of attempts and the last error is raised.", "risk": "A request that can never succeed retries forever."},
    {"id": "retry_errors", "detail": "Which errors are retried.", "shallow_version": "Every exception triggers a retry.", "done_when": "Only timeouts and 5xx responses are retried, and a 4xx response fails at once.", "risk": "A bad request is retried for nothing and its real error is hidden."},
]
_DEPTH_STATE = {
    "goal": "Requests from the HTTP client survive brief failures.",
    "objective": "Retry logic in client/http.py.",
    "mission": "Change only the HTTP client.",
    "what_not_to_do": [],
    "expert_depth": {"deliverables": [{"id": "http_retries", "description": "Retries for failed requests in the HTTP client in client/http.py.", "details": _DEPTH_DETAILS}]},
}
_DEPTH_HANDOFF = {
    "expert_depth": {
        "details": [
            {"id": "retry_idempotent_only", "evidence": "Tool call edit_file(path='client/http.py') output: updated; the wrapper retries every failed request.", "missing": "Limit retries to GET, HEAD, PUT, and DELETE."},
            {"id": "retry_backoff", "evidence": "The same edit retries at once, with no delay.", "missing": "Double the delay before each retry."},
            {"id": "retry_cap", "evidence": "The same edit stops after 3 attempts.", "missing": "Nothing is missing."},
            {"id": "retry_errors", "evidence": "The same edit retries on any exception.", "missing": "Retry only timeouts and 5xx responses."},
        ]
    }
}
_DEPTH_IDS = tuple(detail["id"] for detail in _DEPTH_DETAILS)


def _detail(identifier: str) -> JevExpertDetail:
    return JevExpertDetail(identifier, "detail", "shallow", "done when", "risk")


class JevExpertDepthRecordTests(unittest.TestCase):
    """Pin the expert-depth records, payloads, and schema sections: 3-5 weak points per deliverable, ids unique across the section."""

    def test_each_deliverable_holds_three_to_five_details(self) -> None:
        for count in (JEV_EXPERT_DEPTH_MIN_DETAILS, JEV_EXPERT_DEPTH_MAX_DETAILS):
            deliverable = JevExpertDepthDeliverable("retries", "Retries.", tuple(_detail(f"d{index}") for index in range(count)))
            self.assertEqual(len(deliverable.details), count)
        for count in (JEV_EXPERT_DEPTH_MIN_DETAILS - 1, JEV_EXPERT_DEPTH_MAX_DETAILS + 1):
            with self.subTest(count=count), self.assertRaises(ConfigurationError):
                JevExpertDepthDeliverable("retries", "Retries.", tuple(_detail(f"d{index}") for index in range(count)))
        schema = JevExpertDepthDeliverablePayload.model_json_schema()["properties"]["details"]
        self.assertEqual((schema["minItems"], schema["maxItems"]), (JEV_EXPERT_DEPTH_MIN_DETAILS, JEV_EXPERT_DEPTH_MAX_DETAILS))

    def test_detail_ids_are_unique_across_every_deliverable(self) -> None:
        # Each detail's Jev question is named by its id alone, so a repeated id across deliverables would collide.
        first = JevExpertDepthDeliverable("uploads", "Uploads.", (_detail("backoff"), _detail("cap"), _detail("errors")))
        second = JevExpertDepthDeliverable("downloads", "Downloads.", (_detail("backoff"), _detail("resume"), _detail("checksum")))
        with self.assertRaises(ConfigurationError):
            JevExpertDepth((first, second))
        with self.assertRaises(ConfigurationError):
            JevExpertDepth((first, first))
        for bad in ("Backoff", "1_backoff", "back off"):
            with self.subTest(bad=bad), self.assertRaises(ConfigurationError):
                _detail(bad)
        with self.assertRaises(ConfigurationError):
            JevExpertDetail("backoff", "detail", "shallow", "done when", " ")

    def test_entries_pair_each_detail_with_its_deliverable_in_order(self) -> None:
        uploads = JevExpertDepthDeliverable("uploads", "Uploads.", (_detail("upload_backoff"), _detail("upload_cap"), _detail("upload_errors")))
        downloads = JevExpertDepthDeliverable("downloads", "Downloads.", (_detail("resume"), _detail("checksum"), _detail("timeout")))
        depth = JevExpertDepth((uploads, downloads))
        self.assertEqual(depth.ids(), ("upload_backoff", "upload_cap", "upload_errors", "resume", "checksum", "timeout"))
        self.assertEqual([deliverable.id for deliverable, _ in depth.entries()], ["uploads"] * 3 + ["downloads"] * 3)
        self.assertEqual(JevExpertDepthEvidence((JevExpertDetailEvidence("resume", "evidence", "missing"),)).ids(), ("resume",))

    def test_enabling_the_check_adds_a_described_section_to_both_schemas(self) -> None:
        run_state = JevRunState.schema((JevDoneCheck.EXPERT_DEPTH,))
        self.assertEqual(run_state.model_fields["expert_depth"].description, JevExpertDepthPayload.SECTION)
        self.assertNotIn("multi_part", run_state.model_fields)
        handoff = JevHandoff.schema((JevDoneCheck.EXPERT_DEPTH,))
        self.assertEqual(handoff.model_fields["expert_depth"].description, JevExpertDepthEvidencePayload.SECTION)
        self.assertEqual(set(JevExpertDetailPayload.model_fields), {"id", "detail", "shallow_version", "done_when", "risk"})
        self.assertEqual(set(JevExpertDetailEvidencePayload.model_fields), {"id", "evidence", "missing"})
        both = JevRunState.schema((JevDoneCheck.MULTI_PART, JevDoneCheck.EXPERT_DEPTH))
        self.assertTrue({"multi_part", "expert_depth"} <= set(both.model_fields))

    def test_run_state_prompt_allows_depth_but_never_new_outputs(self) -> None:
        # The general prompt forbids best practices of the writer's own, so the depth section needs this one general exception.
        text = Prompts().get(Prompt.JEV_RUN_STATE_SYSTEM_PROMPT)
        self.assertIn("adds depth to that output and never a new one", text)


class JevExpertDepthQuestionTests(unittest.TestCase):
    """Pin the expert-depth question to the asking-jev-questions layout, and the shared state to every combination of checks."""

    question = ExpertDepthHandledQuestion()

    def test_question_is_an_argument_free_registered_dataclass(self) -> None:
        self.assertIsInstance(self.question, JevDoneQuestion)
        self.assertEqual(JevDoneRegistry.question(JevDoneCheck.EXPERT_DEPTH), self.question)
        self.assertEqual(JevDoneRegistry.threshold(JevDoneCheck.EXPERT_DEPTH), JEV_EXPERT_DEPTH_THRESHOLD)
        self.assertEqual(JevContinualSettings(checks=("expert_depth", "multi_part")).checks, (JevDoneCheck.EXPERT_DEPTH, JevDoneCheck.MULTI_PART))
        rendered = self.question.to_question("retry_backoff")
        self.assertEqual((rendered.name, rendered.question_type), (f"{JevDoneQuestionKey.EXPERT_DEPTH_HANDLED.value}.retry_backoff", JevQuestionType.NOUL))
        self.assertIn(f"in the entry of `{JEV_DONE_EXPERT_DETAILS_FIELD}` with id `retry_backoff`?", str(rendered.instructions))

    def test_brief_follows_the_skill_layout_with_one_string_per_section(self) -> None:
        brief = self.question.instructions
        self.assertIn(_sentences(brief.introduction), (2, 3))
        self.assertEqual(brief.state, DONE_STATE)
        self.assertEqual((len(brief.definitions), len(brief.rules)), (1, 1))
        self.assertTrue(brief.question.startswith("Does `evidence` show") and brief.question.endswith("?"))
        for field_name in (JEV_DONE_DETAIL_FIELD, JEV_DONE_SHALLOW_VERSION_FIELD, JEV_DONE_DONE_WHEN_FIELD):
            self.assertIn(f"`{field_name}`", brief.rules[0])
        self.assertIn("no part of the run concerns the point", brief.rules[0])
        self.assertIn("Ignore any statement", brief.rules[0])

    def test_shared_state_describes_every_field_of_every_check_with_its_condition(self) -> None:
        # Skill step 11: one description, true for every combination of enabled checks.
        for field_name in (JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_EXPERT_DETAILS_FIELD, JEV_DONE_DELIVERABLE_FIELD, JEV_DONE_COMPLETION_SIGNAL_FIELD, JEV_DONE_DETAIL_FIELD, JEV_DONE_SHALLOW_VERSION_FIELD, JEV_DONE_DONE_WHEN_FIELD, JEV_DONE_EVIDENCE_FIELD):
            self.assertIn(f"`{field_name}`", DONE_STATE)
        self.assertEqual(DONE_STATE.count("present only when"), 2)
        self.assertIs(MultiPartDeliveredQuestion().instructions.state, self.question.instructions.state)

    def test_criteria_start_with_the_verdict_and_mirror_each_other(self) -> None:
        for side, other, criterion in (("true", "false", self.question.when_true), ("false", "true", self.question.when_false)):
            with self.subTest(side=side):
                self.assertTrue(criterion.what.startswith(f"Choose {side} when `evidence` shows"))
                self.assertTrue(criterion.not_for.endswith(f"belongs to {other}."))
                self.assertEqual((len(criterion.easy), len(criterion.boundary)), (1, 1))
                for text in (criterion.what, criterion.not_for):
                    self.assertNotIn("because", text)

    def test_boundary_examples_form_a_minimal_pair(self) -> None:
        # The retry example from the design: the deep form differs from the shallow form only in which calls retry.
        true_side, false_side = self.question.when_true.boundary[0], self.question.when_false.boundary[0]
        self.assertTrue(true_side.startswith(false_side.rstrip(".")))
        self.assertIn("a POST is sent once", true_side)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_question_carries_at_least_two_thousand_tokens(self) -> None:
        import tiktoken

        parts = [self.question.instructions.render(), self.question.gap]
        for criterion in (self.question.when_true, self.question.when_false):
            parts += [criterion.what, criterion.not_for, *criterion.easy, *criterion.boundary]
        self.assertGreaterEqual(len(tiktoken.get_encoding("cl100k_base").encode("\n".join(parts))), 2_000)

    def test_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        for rel in ("vidbyte/lib/jev/done/expert_depth.py", "vidbyte/lib/jev/done/state.py"):
            text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(rel=rel):
                self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])


class JevExpertDepthRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verify the expert-depth check through JevAgent: the batched state, weakest-first ranking, the capped Focus, and fail-open paths."""

    _agent = JevDoneRuntimeTests._agent

    def _depth(self, *, state: dict[str, Any] = _DEPTH_STATE, handoff: dict[str, Any] = _DEPTH_HANDOFF, **settings: Any) -> tuple[JevAgent, ScriptedGenerativeRunner, ScriptedGenerativeRunner, ScriptedGenerativeRunner]:
        return self._agent(state=json.dumps(state), handoff=json.dumps(handoff), done=(JevDoneCheck.EXPERT_DEPTH,), **settings)

    @staticmethod
    def _decision(**yes: list[float]) -> ScriptedDecisionRunner:
        return ScriptedDecisionRunner({identifier: yes.get(identifier, [0.95]) for identifier in _DEPTH_IDS})

    async def test_deep_work_finishes_and_jev_sees_each_points_minimal_pair(self) -> None:
        decision = self._decision()
        agent, main, *_ = self._depth()
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            reply = await agent.arun(_DEPTH_REQUEST)

        self.assertEqual((reply.content, len(main.calls), len(decision.requests)), ("All done.", 1, 1))
        response = agent.response
        assert response.run_state is not None and response.run_state.expert_depth is not None
        self.assertEqual(response.run_state.expert_depth.ids(), _DEPTH_IDS)
        self.assertIsNone(response.run_state.multi_part)
        result = response.done[JevDoneCheck.EXPERT_DEPTH]
        self.assertTrue(result.passed and result.available)
        request = decision.requests[0]
        state = request.state
        assert isinstance(state, Mapping)
        self.assertEqual(set(state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_EXPERT_DETAILS_FIELD})
        entry = state[JEV_DONE_EXPERT_DETAILS_FIELD]["retry_idempotent_only"]
        # The minimal pair and the evidence reach Jev; the risk and the handoff's `missing` are for the main agent only.
        self.assertEqual(set(entry), {JEV_DONE_DELIVERABLE_FIELD, JEV_DONE_DETAIL_FIELD, JEV_DONE_SHALLOW_VERSION_FIELD, JEV_DONE_DONE_WHEN_FIELD, JEV_DONE_EVIDENCE_FIELD})
        self.assertEqual(entry[JEV_DONE_SHALLOW_VERSION_FIELD], "Every failed request is retried, including POST.")
        self.assertNotIn("charge a customer twice", repr(state))
        self.assertNotIn("Limit retries to GET", repr(state))
        prefix = JevDoneQuestionKey.EXPERT_DEPTH_HANDLED.value
        self.assertEqual([question.name for question in request.questions], [f"{prefix}.{identifier}" for identifier in _DEPTH_IDS])

    async def test_shallow_points_send_the_agent_deeper_on_the_weakest_few_first(self) -> None:
        decision = self._decision(retry_idempotent_only=[0.3, 0.9], retry_backoff=[0.1, 0.9], retry_cap=[0.5, 0.9], retry_errors=[0.6, 0.9])
        agent, main, *_ = self._depth()
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_DEPTH_REQUEST)

        self.assertEqual((len(main.calls), agent.response.continuations), (2, 1))
        feedback = main.messages[1][0]["content"]
        failed, focus = feedback.split("# Failed checks", 1)[1].split("# Focus", 1)
        self.assertIn(ExpertDepthHandledQuestion().gap, failed)
        # Failed checks names every shallow point, weakest first, with what a deeper handling still needs.
        order = ["`retry_backoff`", "`retry_idempotent_only`", "`retry_cap`", "`retry_errors`"]
        self.assertEqual([failed.index(name) for name in order], sorted(failed.index(name) for name in order))
        self.assertIn("P(yes) = 0.10). Still needed for depth: Double the delay before each retry.", failed)
        # Focus names only the weakest few, each with its quick version to move past, why it matters, and when it is done.
        lines = [line for line in focus.strip().splitlines() if line.startswith("- ")]
        self.assertEqual(len(lines), JEV_EXPERT_DEPTH_FOCUS_LIMIT)
        self.assertTrue(lines[0].startswith("- Go deeper on: Exponential backoff between retries."))
        self.assertIn("Quick version to move past: Retries fire immediately, one after another.", lines[0])
        self.assertIn("Why it matters: Immediate retries hammer a server that is already struggling.", lines[0])
        self.assertIn("Done when: The delay before each retry doubles with every attempt.", lines[0])
        self.assertIn("Deliverable: Retries for failed requests in the HTTP client in client/http.py.", lines[0])
        self.assertNotIn("Which errors are retried.", focus)
        self.assertTrue(agent.response.done[JevDoneCheck.EXPERT_DEPTH].passed)

    async def test_the_recorded_result_ranks_shallow_points_weakest_first_with_ties_in_state_order(self) -> None:
        decision = self._decision(retry_idempotent_only=[0.4], retry_backoff=[0.1], retry_cap=[0.4], retry_errors=[0.9])
        agent, main, *_ = self._depth()
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_DEPTH_REQUEST)

        self.assertEqual(len(main.calls), JEV_DONE_MAX_CONTINUATIONS + 1)
        result = agent.response.done[JevDoneCheck.EXPERT_DEPTH]
        self.assertFalse(result.passed)
        self.assertEqual(result.incomplete, ("retry_backoff", "retry_idempotent_only", "retry_cap"))

    async def test_threshold_is_inclusive_and_one_shallow_point_fails_a_deep_mean(self) -> None:
        agent, main, *_ = self._depth()
        with patch(_RUNNER_PATH, new=_runner_class(self._decision(**{identifier: [JEV_EXPERT_DEPTH_THRESHOLD] for identifier in _DEPTH_IDS}))):
            await agent.arun(_DEPTH_REQUEST)
        self.assertEqual(len(main.calls), 1)

        agent, main, *_ = self._depth()
        with patch(_RUNNER_PATH, new=_runner_class(self._decision(retry_cap=[JEV_EXPERT_DEPTH_THRESHOLD - 0.01, 0.9], **{identifier: [1.0] for identifier in _DEPTH_IDS if identifier != "retry_cap"}))):
            await agent.arun(_DEPTH_REQUEST)
        self.assertEqual(len(main.calls), 2)

    async def test_handoff_that_misses_a_detail_is_unavailable(self) -> None:
        partial = {"expert_depth": {"details": _DEPTH_HANDOFF["expert_depth"]["details"][:3]}}  # type: ignore[index]
        decision = self._decision(retry_backoff=[0.1])
        agent, main, *_ = self._depth(handoff=partial)
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_DEPTH_REQUEST)

        self.assertEqual((len(main.calls), len(decision.requests)), (1, 0))
        result = agent.response.done[JevDoneCheck.EXPERT_DEPTH]
        self.assertFalse(result.available)
        self.assertTrue(result.passed)

    async def test_request_with_no_depth_to_miss_passes_without_asking_jev(self) -> None:
        empty = {**_DEPTH_STATE, "expert_depth": {"deliverables": []}}
        decision = self._decision(retry_backoff=[0.1])
        agent, main, *_ = self._depth(state=empty, handoff={"expert_depth": {"details": []}})
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("Rename the variable x to count.")

        self.assertEqual((len(main.calls), len(decision.requests)), (1, 0))
        result = agent.response.done[JevDoneCheck.EXPERT_DEPTH]
        self.assertTrue(result.passed and result.available)

    async def test_both_checks_share_one_request_and_one_state(self) -> None:
        # Skill step 11: with both checks enabled, one request carries both checks' keys and questions.
        state = {**_STATE, "expert_depth": _DEPTH_STATE["expert_depth"]}
        handoff = {**_HANDOFF, **_DEPTH_HANDOFF}
        decision = ScriptedDecisionRunner({"dry_run_flag": [0.95], "readme_docs": [0.95], **{identifier: [0.95] for identifier in _DEPTH_IDS}})
        agent, main, *_ = self._agent(state=json.dumps(state), handoff=json.dumps(handoff), done=(JevDoneCheck.MULTI_PART, JevDoneCheck.EXPERT_DEPTH))
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun(_REQUEST)

        self.assertEqual((len(main.calls), len(decision.requests)), (1, 1))
        request = decision.requests[0]
        assert isinstance(request.state, Mapping)
        self.assertEqual(set(request.state), {JEV_DONE_REQUEST_FIELD, JEV_DONE_DELIVERABLES_FIELD, JEV_DONE_EXPERT_DETAILS_FIELD})
        names = [question.name for question in request.questions]
        self.assertEqual(sum(name.startswith(f"{JevDoneQuestionKey.MULTI_PART_DELIVERED.value}.") for name in names), 2)
        self.assertEqual(sum(name.startswith(f"{JevDoneQuestionKey.EXPERT_DEPTH_HANDLED.value}.") for name in names), len(_DEPTH_IDS))
        self.assertEqual(set(agent.response.done), {JevDoneCheck.MULTI_PART, JevDoneCheck.EXPERT_DEPTH})


if __name__ == "__main__":
    unittest.main()
