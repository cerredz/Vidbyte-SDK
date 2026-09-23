"""FILE: tests/test_jev_alignment.py

PURPOSE: Verifies JevAgent self-alignment without network access: the question set, gating, gap routing, additive edits, verification, fail-open behavior, and that only the main agent's current run sees the edited prompt.
ROLE IN CODEBASE: Covers docs/design/jev-agent-alignment.md; scripts/test-jev-agent-scaffold.py runs it alongside tests/test_jev_agent.py.
ARCHITECTURE NOTE: A scripted Jev runner replaces DecisionModelRunner and scripted generative runners replace the main and editor models; the production agent, runtime, draft, and tool stay under test.
COMMON MODIFICATION PATTERNS: Add a case whenever a question's gating, a draft rule, or a status branch changes.
KNOWN EDGE CASES: TYPESAFE_API_KEY is cleared where credential failure is tested, and no test may send a live provider request.
RELATED DOCS: docs/design/jev-agent-alignment.md and skills/jev-agent/SKILL.md.
TESTS: python -m pytest tests/test_jev_alignment.py and python scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import json
import os
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte.agents.jev import (
    JevAgent,
    JevAgentAlignment,
    JevAgentSettings,
    JevAlignmentStatus,
)
from vidbyte.agents.jev.alignment.draft import JevPromptDraft
from vidbyte.agents.jev.alignment.questions import (
    ALIGNMENT_QUESTIONS,
    EDITABLE_SECTIONS,
    JevAlignmentRole,
    JevPromptSection,
)
from vidbyte.agents.jev.alignment.result import JevAlignmentGap
from vidbyte.agents.jev.alignment.tool import (
    EditSystemPromptSectionTool,
    bind_prompt_draft,
)
from vidbyte.lib.constants.jev import JEV_NOUL_OPTIONS
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.tools.types import ToolCall

PROMPT = "You are the support agent for Acme invoicing. Help account admins with billing questions."
OUTPUT_GAP = "alignment.section.output"
RUNNER_PATH = "vidbyte.agents.jev.alignment.agent.DecisionModelRunner"


class ScriptedJev:
    """Stands in for DecisionModelRunner: answers every question from probability tables and records requests."""

    def __init__(self, assess: Mapping[str, float] | None = None, verify: Mapping[str, float] | None = None, *, fail: bool = False) -> None:
        # Answers 0.9 (yes) unless a table overrides a question; verify applies once the prompt differs from PROMPT.
        self.assess = dict(assess or {})
        self.verify = dict(verify or {})
        self.fail = fail
        self.requests: list[JevDecisionRequest] = []

    def __call__(self, config: object = None) -> ScriptedJev:
        # Acts as the runner class, so patching DecisionModelRunner with an instance returns the instance.
        return self

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Records the request and returns one noul answer per question.
        self.requests.append(request)
        if self.fail:
            raise ProviderRequestError("TypeSafe is unavailable.", provider="typesafe")
        table = self.verify if request.state["system_prompt"] != PROMPT else self.assess
        answers = {question.name: _noul(question.name, table.get(question.name, 0.9)) for question in request.questions}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 10, "output_tokens": 2})

    def asked(self) -> list[str]:
        # Returns every question name sent, in order.
        return [question.name for request in self.requests for question in request.questions]


class ScriptedRunner:
    """Minimal generative runner that returns scripted responses and records invocation kwargs."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        # Returns the next response, or raises it when it is an exception.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class RawResponse:
    """OpenAI-shaped raw response wrapper for scripted tool calls."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.text = ""
        self.raw = raw


def _noul(name: str, probability: float) -> JevAnswer:
    # Builds a normalized noul answer with P(true) = probability.
    choice = "true" if probability >= 0.5 else "false"
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice=choice, probabilities={"true": probability, "false": 1.0 - probability}, noul=probability)


def _settings(**overrides: Any) -> JevAgentSettings:
    # Builds valid self-aligning settings.
    values: dict[str, Any] = {"name": "support", "system_prompt": PROMPT, "provider": "openai", "model_name": "gpt-4.1-mini", "self_align": True}
    values.update(overrides)
    return JevAgentSettings(**values)


def _text(text: str) -> TextModelResponse:
    return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})


def _call(name: str, arguments: dict[str, Any], call_id: str) -> RawResponse:
    return RawResponse({"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]})


def _editor(*edits: dict[str, Any]) -> ScriptedRunner:
    # Scripts the editor: one edit tool call per edit, then isDone.
    calls = [_call("edit_system_prompt_section", edit, f"e{index}") for index, edit in enumerate(edits)]
    return ScriptedRunner(*calls, _call("isDone", {"final_answer": "edited"}, "done"))


def _agent(main: ScriptedRunner, editor: ScriptedRunner, **overrides: Any) -> JevAgent:
    agent = bind_test_runner(JevAgent(_settings(**overrides)), main)
    assert agent.alignment is not None
    bind_test_runner(agent.alignment, editor)
    return agent


OUTPUT_EDIT = {"section": "output", "content": "Answer in at most three short bullet points.", "fixes": [OUTPUT_GAP]}


class AlignmentQuestionTests(unittest.TestCase):
    """Pins the shape the asking-jev-questions skill requires."""

    def test_questions_are_unique_positive_nouls_with_criteria(self) -> None:
        # [Silent Failure] answers are keyed by name and every "true" must mean aligned.
        names = [question.name for question in ALIGNMENT_QUESTIONS]
        self.assertEqual(len(names), 21)
        self.assertEqual(len(set(names)), len(names))
        for question in ALIGNMENT_QUESTIONS:
            jev = question.to_jev_question()
            self.assertIs(jev.question_type, JevQuestionType.NOUL)
            self.assertEqual(jev.option_names(), JEV_NOUL_OPTIONS)
            self.assertTrue(all(option.description for option in jev.options))
            self.assertTrue(str(jev.instructions).rstrip().endswith("?"))

    def test_only_gates_and_signals_lack_a_section(self) -> None:
        # [Hidden Assumption] every gap needs a section to route to, and gates must never produce one.
        for question in ALIGNMENT_QUESTIONS:
            gate_like = question.role in (JevAlignmentRole.GATE, JevAlignmentRole.SIGNAL)
            self.assertEqual(question.section is None, gate_like, question.key)
            if question.role is JevAlignmentRole.AGENT:
                self.assertIn(question.section, EDITABLE_SECTIONS)
            if question.role is JevAlignmentRole.OWNER:
                self.assertNotIn(question.section, EDITABLE_SECTIONS)

    def test_settings_validate_self_align(self) -> None:
        with self.assertRaises(ConfigurationError):
            _settings(self_align="yes")
        self.assertIsNone(JevAgent(_settings(self_align=False)).alignment)


class PromptDraftTests(unittest.IsolatedAsyncioTestCase):
    """Pins additive-only editing and its validation."""

    def _draft(self, base: str = PROMPT) -> JevPromptDraft:
        gap = JevAlignmentGap(OUTPUT_GAP, JevPromptSection.OUTPUT, JevAlignmentRole.AGENT, 0.1, "Add an output section.")
        return JevPromptDraft(base, (gap,))

    def test_owner_sections_and_uncited_fixes_are_refused(self) -> None:
        # [Hidden Failure] a request-driven edit can never touch what the agent is for.
        draft = self._draft()
        with self.assertRaisesRegex(ValueError, "owner-only"):
            draft.add("scope", "Also do taxes.", [OUTPUT_GAP])
        with self.assertRaisesRegex(ValueError, "not open gaps"):
            draft.add("method", "Step one.", [OUTPUT_GAP])
        with self.assertRaisesRegex(ValueError, "at least one"):
            draft.add("output", "Be short.", [])
        self.assertEqual(draft.edits, ())

    def test_additions_go_under_an_existing_heading_and_keep_the_original(self) -> None:
        # [Edge Case] headings match case-insensitively and later sections stay after the addition.
        base = "# Agent\nYou help.\n\n## OUTPUT\nBe short.\n\n## Other\nKeep this."
        draft = self._draft(base)
        draft.add("output", "Use bullet points.", [OUTPUT_GAP])
        self.assertEqual(draft.render(), "# Agent\nYou help.\n\n## OUTPUT\nBe short.\n\nUse bullet points.\n\n## Other\nKeep this.")
        self.assertEqual(draft.render(()), base)

    def test_missing_heading_is_created_at_the_end(self) -> None:
        draft = self._draft()
        draft.add("output", "Use bullet points.", [OUTPUT_GAP])
        self.assertEqual(draft.render(), f"{PROMPT}\n\n## Output\nUse bullet points.")

    async def test_tool_edits_only_the_bound_draft(self) -> None:
        # [Silent Failure] outside a pass the tool refuses; inside it writes to that pass's draft only.
        tool = EditSystemPromptSectionTool()
        call = ToolCall(tool_name="edit_system_prompt_section", arguments=OUTPUT_EDIT, call_id="c1")
        unbound = await tool.execute(call)
        self.assertIn("No alignment pass", unbound.output)
        draft = self._draft()
        with bind_prompt_draft(draft):
            bound = await tool.execute(call)
        self.assertIn("Added", bound.output)
        self.assertEqual(draft.edits[0].section, JevPromptSection.OUTPUT)


class AlignmentRunTests(unittest.IsolatedAsyncioTestCase):
    """Pins the full pass through a real JevAgent run."""

    async def test_self_align_off_makes_no_jev_call(self) -> None:
        # [Edge Case] the default agent behaves exactly like the scaffold.
        jev = ScriptedJev()
        main = ScriptedRunner(_text("answer"))
        agent = bind_test_runner(JevAgent(_settings(self_align=False)), main)
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun("Why was I charged twice?")
        self.assertEqual(jev.requests, [])
        self.assertNotIn("jev_alignment", reply.metadata)

    async def test_agent_gap_is_edited_verified_and_used_only_for_this_run(self) -> None:
        # [Silent Failure] the main model sees the edited prompt; settings, agent, and editor keep theirs.
        jev = ScriptedJev(assess={OUTPUT_GAP: 0.1}, verify={OUTPUT_GAP: 0.9})
        main = ScriptedRunner(_text("answer"))
        agent = _agent(main, _editor(OUTPUT_EDIT))
        editor_prompt = agent.alignment.system_prompt
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun("Why was I charged twice?")
        result = reply.metadata["jev_alignment"]
        self.assertIs(result.status, JevAlignmentStatus.ALIGNED)
        self.assertEqual(result.system_prompt, f"{PROMPT}\n\n## Output\nAnswer in at most three short bullet points.")
        self.assertTrue(result.edits[0].kept)
        self.assertIn("## Output\nAnswer in at most three short bullet points.", main.calls[0]["kwargs"]["system"])
        self.assertEqual(agent.system_prompt, PROMPT)
        self.assertEqual(agent.settings.system_prompt, PROMPT)
        self.assertEqual(agent.alignment.system_prompt, editor_prompt)
        self.assertEqual(result.usage.input_tokens, 30)

    async def test_failed_gate_never_edits(self) -> None:
        # [Hidden Failure] an off-topic request must not widen the prompt, even when gaps exist.
        jev = ScriptedJev(assess={"alignment.fit.task_in_scope": 0.1, OUTPUT_GAP: 0.1})
        editor = _editor(OUTPUT_EDIT)
        main = ScriptedRunner(_text("I can only help with billing."))
        agent = _agent(main, editor)
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun("Help me file my taxes.")
        result = reply.metadata["jev_alignment"]
        self.assertIs(result.status, JevAlignmentStatus.OUT_OF_SCOPE)
        self.assertEqual(editor.calls, [])
        self.assertIn(PROMPT, main.calls[0]["kwargs"]["system"])
        self.assertNotIn("## Output", main.calls[0]["kwargs"]["system"])
        self.assertIn("outside its described scope", result.owner_actions[0])

    async def test_owner_gaps_are_reported_not_edited(self) -> None:
        # [Hidden Assumption] scope belongs to the developer, so the editor never runs for it.
        jev = ScriptedJev(assess={"alignment.section.scope": 0.2})
        editor = _editor()
        agent = _agent(ScriptedRunner(_text("answer")), editor)
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun("Why was I charged twice?")
        result = reply.metadata["jev_alignment"]
        self.assertIs(result.status, JevAlignmentStatus.NO_GAPS)
        self.assertEqual(editor.calls, [])
        self.assertEqual(len(result.owner_actions), 1)
        self.assertIn("scope section", result.owner_actions[0])

    async def test_unconfirmed_edit_is_reverted(self) -> None:
        # [Silent Failure] an edit Jev does not confirm never reaches the main model.
        jev = ScriptedJev(assess={OUTPUT_GAP: 0.1}, verify={OUTPUT_GAP: 0.2})
        main = ScriptedRunner(_text("answer"))
        agent = _agent(main, _editor(OUTPUT_EDIT))
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun("Why was I charged twice?")
        result = reply.metadata["jev_alignment"]
        self.assertIs(result.status, JevAlignmentStatus.EDITS_REJECTED)
        self.assertFalse(result.edits[0].kept)
        self.assertEqual(result.system_prompt, PROMPT)
        self.assertNotIn("## Output", main.calls[0]["kwargs"]["system"])

    async def test_new_conflict_reverts_every_edit(self) -> None:
        # [Hidden Failure] edits that add a contradiction are dropped even when their own gap closed.
        jev = ScriptedJev(assess={OUTPUT_GAP: 0.1}, verify={OUTPUT_GAP: 0.9, "alignment.cover.consistent": 0.1})
        agent = _agent(ScriptedRunner(_text("answer")), _editor(OUTPUT_EDIT))
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun("Why was I charged twice?")
        self.assertIs(reply.metadata["jev_alignment"].status, JevAlignmentStatus.EDITS_REJECTED)

    async def test_missing_credentials_fail_open(self) -> None:
        # [Hidden Failure] alignment is advisory; the main run continues with the original prompt.
        main = ScriptedRunner(_text("answer"))
        agent = _agent(main, _editor())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TYPESAFE_API_KEY", None)
            reply = await agent.arun("Why was I charged twice?")
        self.assertIs(reply.metadata["jev_alignment"].status, JevAlignmentStatus.UNAVAILABLE)
        self.assertEqual(reply.content, "answer")

    async def test_editor_failure_fails_open(self) -> None:
        jev = ScriptedJev(assess={OUTPUT_GAP: 0.1})
        editor = ScriptedRunner(ProviderRequestError("editor model down", provider="openai"))
        main = ScriptedRunner(_text("answer"))
        agent = _agent(main, editor)
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun("Why was I charged twice?")
        self.assertIs(reply.metadata["jev_alignment"].status, JevAlignmentStatus.UNAVAILABLE)
        self.assertEqual(reply.content, "answer")


class AlignmentAssessTests(unittest.IsolatedAsyncioTestCase):
    """Pins what is asked, and how often."""

    async def test_static_answers_are_cached_per_prompt(self) -> None:
        # [Silent Failure] a warm agent asks only the request-dependent questions.
        jev = ScriptedJev()
        alignment = JevAgentAlignment(_settings())
        with patch(RUNNER_PATH, jev):
            await alignment.align("first", PROMPT)
            self.assertEqual(len(jev.requests), 2)
            await alignment.align("second", PROMPT)
        self.assertEqual(len(jev.requests), 3)
        self.assertNotIn("request", jev.requests[1].state)
        self.assertIn("request", jev.requests[2].state)

    async def test_tool_questions_are_skipped_without_tools(self) -> None:
        jev = ScriptedJev()
        with patch(RUNNER_PATH, jev):
            await JevAgentAlignment(_settings()).align("question", PROMPT)
            without = jev.asked()
            jev.requests.clear()
            await JevAgentAlignment(_settings()).align("question", PROMPT, tools=("lookup: Look up an invoice.",))
        self.assertNotIn("alignment.section.tool_guidance", without)
        self.assertNotIn("alignment.cover.permissions", without)
        self.assertIn("alignment.section.tool_guidance", jev.asked())

    async def test_mixed_request_gap_only_counts_for_multi_task_requests(self) -> None:
        # [Edge Case] the mixed-request section is only a gap when the request asks for several tasks.
        single = ScriptedJev(assess={"alignment.section.mixed_requests": 0.1})
        with patch(RUNNER_PATH, single):
            result = await JevAgentAlignment(_settings()).align("question", PROMPT)
        self.assertEqual(result.gaps, ())
        multi = ScriptedJev(assess={"alignment.section.mixed_requests": 0.1, "alignment.fit.single_task": 0.1})
        editor = _editor({"section": "exceptions", "content": "Do the covered tasks and name the rest.", "fixes": ["alignment.section.mixed_requests"]})
        alignment = bind_test_runner(JevAgentAlignment(_settings()), editor)
        with patch(RUNNER_PATH, multi):
            result = await alignment.align("do A and also B", PROMPT)
        self.assertEqual([gap.question for gap in result.gaps], ["alignment.section.mixed_requests"])

    async def test_caller_context_prompt_skips_alignment(self) -> None:
        # [Edge Case] a caller-supplied prompt is not the agent's prompt, so no Jev call is made.
        jev = ScriptedJev()
        runtime = JevAgent(_settings())._runtime()
        with patch(RUNNER_PATH, jev):
            result, context = await runtime._align(runtime.alignment, "question", BaseAgentContext(system_prompt="A different prompt."))
        self.assertIs(result.status, JevAlignmentStatus.SKIPPED)
        self.assertEqual(context.system_prompt, "A different prompt.")
        self.assertEqual(jev.requests, [])


if __name__ == "__main__":
    unittest.main()
