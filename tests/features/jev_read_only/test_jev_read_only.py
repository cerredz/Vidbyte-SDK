"""FILE: tests/features/jev_read_only/test_jev_read_only.py

PURPOSE: Verifies Jev read-only intent without provider calls: the PermissionCeiling scope, the eight READ_ONLY questions, the gate's per-question threshold, JevReadOnly's tool filter, and the runtime that limits a read-only run, and every agent it starts, to SAFE and READ tools.
ROLE IN CODEBASE: Covers the contract in tests/features/jev_read_only/FEATURE.md with production settings, registry, gate, PermissionPolicy, ToolExecutor, AgentRuntime tool execution, the run_bulk_work tool, specialist delegation, and JevRuntime.
ARCHITECTURE NOTE: Scripted decision and model runners replace only external boundaries; tool catalogs, permission checks, denials, and runtime ordering stay real, so a tool that should be refused is refused by the production code path.
COMMON MODIFICATION PATTERNS: Add regression tests here and list their behavior in FEATURE.md when a public contract changes.
KNOWN EDGE CASES: Write and execute tools record into _EFFECTS, so every test that expects a refusal checks that the list stayed empty rather than only reading the denial text.
RELATED DOCS: `docs/design/jev-read-only-intent.md` and `tests/features/jev_read_only/FEATURE.md`.
TESTS: Run `python scripts/test-jev-read-only.py`.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import inspect
import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tests.test_jev_compute_situations import _call
from vidbyte import BaseAgent, JevAgent, JevAgentSettings, JevPreflightPreset, JevRuntimeSettings, JevSpecialist, tool
from vidbyte.agents.jev.gate import JevPreflightGate, JevReadOnly
from vidbyte.agents.jev.response import JevResponse
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.constants.jev import JEV_BULK_WORK_TOOL_NAME, JEV_READ_ONLY_THRESHOLD
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.dataclasses.tools import ToolCall, ToolCallState, ToolPermission
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.enums.jev import JevPreflightQuestionKey, JevQuestionType
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev import JevPreflightRegistry, JevPresets
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.preflight import READ_ONLY_QUESTIONS
from vidbyte.lib.jev.preflight.clarity import IGNORE_CLAIMS, JUDGE_MEANING
from vidbyte.lib.jev.preflight.read_only import ReadOnlyAssessmentQuestion
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.tools.catalog import Tools
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.security import PermissionCeiling, PermissionDecision, PermissionPolicy

_GATE_HELPER = "vidbyte.agents.jev.gate.gate.DecisionModelHelper"
_SELECTOR_HELPER = "vidbyte.agents.jev.preflight.DecisionModelHelper"
_REQUEST = "Why does tests/test_x.py fail? Don't change anything."
_CEILING_NOTE = "; this run allows only read, safe tools"
_READ_ONLY_KEYS = tuple(key.value for key in (
    JevPreflightQuestionKey.READ_ONLY_ASSESSMENT,
    JevPreflightQuestionKey.READ_ONLY_SOLE_RESULT,
    JevPreflightQuestionKey.READ_ONLY_UNCHANGED,
    JevPreflightQuestionKey.READ_ONLY_DESCRIBED,
    JevPreflightQuestionKey.READ_ONLY_USER_DECIDES,
    JevPreflightQuestionKey.READ_ONLY_IN_REPLY,
    JevPreflightQuestionKey.READ_ONLY_READING,
    JevPreflightQuestionKey.READ_ONLY_ANSWER_MEETS_GOAL,
))

# Every write or execute tool records here, so a refused call is proven by an empty list, not only by its message.
_EFFECTS: list[str] = []


@tool
def lookup(topic: str) -> str:
    """Look up one topic in the project glossary."""
    return f"glossary entry for {topic}"


@tool(permission=ToolPermission.READ)
def read_notes(path: str) -> str:
    """Read one notes file."""
    return f"notes in {path}"


@tool(permission=ToolPermission.WRITE)
def write_notes(path: str, text: str) -> str:
    """Write text into one notes file."""
    _EFFECTS.append(f"write {path}")
    return "written"


@tool(permission=ToolPermission.EXECUTE)
def run_command(command: str) -> str:
    """Run one shell command."""
    _EFFECTS.append(f"run {command}")
    return "ran"


_ALL_TOOLS = (lookup, read_notes, write_notes, run_command)


def _settings(**overrides: Any) -> JevAgentSettings:
    # Builds one valid generative settings object with every test tool and an allow-all policy, so only the ceiling can refuse.
    values: dict[str, Any] = {"name": "owner", "system_prompt": "Owner instruction.", "provider": "openai", "model_name": "gpt-4.1-mini", "tools": _ALL_TOOLS, "permission_policy": PermissionPolicy.allow_all()}
    values.update(overrides)
    return JevAgentSettings(**values)


def _answer(name: str, probability: float) -> JevAnswer:
    # Builds a normalized positive or negative fixed-question answer at the exact requested probability.
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if probability >= 0.5 else "false", probabilities={"true": probability, "false": 1.0 - probability}, noul=probability)


def _done() -> object:
    # Returns the scripted model turn that finishes a run.
    return _call("isDone", {"final_answer": "done"}, "end")


def _write(call_id: str = "w1") -> object:
    # Returns the scripted model turn that calls the write tool.
    return _call("write_notes", {"path": "notes.md", "text": "changed"}, call_id)


class ScriptedDecisionRunner:
    """Returns fixed Noul and Choice answers while retaining each batched request; it can omit one answer or fail outright."""

    def __init__(self, probabilities: dict[str, float] | None = None, *, default: float = 0.9, omit: str | None = None, choice: str = "none", fail: bool = False) -> None:
        # Saves one answer map for each gate call.
        self.probabilities = probabilities or {}
        self.default = default
        self.omit = omit
        self.choice = choice
        self.fail = fail
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> Any:
        # Answers every question unless the test omits one field or scripts an outage.
        self.requests.append(request)
        if self.fail:
            raise VidbyteSdkError("TypeSafe is unreachable.")
        answers: dict[str, JevAnswer] = {}
        for question in request.questions:
            if question.name == self.omit:
                continue
            if question.question_type is JevQuestionType.CHOICE:
                selected = self.choice if self.choice in question.option_names() else question.option_names()[-1]
                distribution = {name: 1.0 if name == selected else 0.0 for name in question.option_names()}
                answers[question.name] = JevAnswer(question_name=question.name, question_type=JevQuestionType.CHOICE, choice=selected, probabilities=distribution, confidence=1.0)
            else:
                answers[question.name] = _answer(question.name, self.probabilities.get(question.name, self.default))
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 12, "output_tokens": 3})


def _decision_helper(script: ScriptedDecisionRunner) -> type:
    # Replaces the network helper while preserving production answer scoring methods.
    class ScriptedHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)
        noul_passes = staticmethod(DecisionModelHelper.noul_passes)

        def __new__(cls, *args: object, **kwargs: object) -> ScriptedDecisionRunner:
            # Returns the shared scripted decision transport for this patched boundary.
            return script

    return ScriptedHelper


class MainRunner:
    """Scripted model runner: returns each scripted turn in order and keeps every call's keyword arguments and the ceiling it ran under."""

    def __init__(self, *responses: object, fail: bool = False) -> None:
        # Saves the scripted turns, finishing with isDone when the test scripts none.
        self.responses = list(responses) or [_done()]
        self.fail = fail
        self.calls: list[dict[str, Any]] = []
        self.ceilings: list[frozenset[ToolPermission] | None] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        # Records the call and the active ceiling, then returns the next scripted turn or fails as scripted.
        self.calls.append(kwargs)
        self.ceilings.append(PermissionCeiling.current())
        if self.fail:
            raise RuntimeError("The model provider failed mid-run.")
        return self.responses.pop(0)

    def tool_names(self, index: int) -> set[str]:
        # Returns the tool names the model was offered on one call, whatever the provider schema shape.
        return {schema.get("name") or schema.get("function", {}).get("name") for schema in self.calls[index].get("tools", ())}

    def sent(self, index: int = -1) -> str:
        # Returns every message of one call as text, including tool outputs.
        return json.dumps(self.calls[index]["messages"], default=str)


class WorkerRunner:
    """Scripted runner for bulk-work agents: answers each task with text and keeps every call's keyword arguments."""

    def __init__(self) -> None:
        # Starts with no recorded worker calls.
        self.calls: list[dict[str, Any]] = []

    async def arun(self, prompt: str, *, system: str = "", **kwargs: Any) -> TextModelResponse:
        # Records the call, including the tools the worker was offered, and returns one plain reply.
        self.calls.append({"prompt": prompt, "system": system, **kwargs})
        return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", text="worker finding", raw={}, usage={"input_tokens": 10, "output_tokens": 2})

    def tool_names(self, index: int) -> set[str]:
        # Returns the tool names one worker call was offered.
        return {schema.get("name") or schema.get("function", {}).get("name") for schema in self.calls[index].get("tools", ())}


def _route(main: object, *, workers: object | None = None, specialist: tuple[BaseAgent, object] | None = None) -> Any:
    # Sends a chosen specialist to its own runner, bulk-work agents to the worker runner, and every other agent to the main runner.
    def runner_for(agent: BaseAgent) -> tuple[object, str]:
        # Picks the scripted runner for one agent by identity or by its bulk-work name.
        if specialist is not None and agent is specialist[0]:
            return specialist[1], RUNNER_TYPE_TEXT
        if workers is not None and "-bulk-" in agent.name:
            return workers, RUNNER_TYPE_TEXT
        return main, RUNNER_TYPE_TEXT

    return patch.object(BaseAgent, "_runner_for_model", new=runner_for)


def _agent(settings: JevAgentSettings | None = None, presets: tuple[JevPreflightPreset, ...] = (JevPreflightPreset.READ_ONLY,)) -> JevAgent:
    # Builds a JevAgent with fixed decision credentials and the requested preflight presets.
    return JevAgent(settings or _settings(), JevRuntimeSettings(decision=DecisionModelConfig.vidbyte_managed(), preflight=presets))


def _veto() -> ScriptedDecisionRunner:
    # Answers every read-only question yes except one clear no, so the run keeps its full catalog.
    return ScriptedDecisionRunner({JevPreflightQuestionKey.READ_ONLY_UNCHANGED.value: 0.2})


class PermissionCeilingTests(unittest.IsolatedAsyncioTestCase):
    """Pins the run-scoped ceiling: it only narrows, it restores, it reaches tasks, and every policy and executor honors it."""

    def setUp(self) -> None:
        _EFFECTS.clear()

    def test_no_scope_allows_every_permission(self) -> None:
        # [Edge Case] Outside any scope the ceiling is absent, allows everything, and adds nothing to a denial.
        self.assertIsNone(PermissionCeiling.current())
        for permission in ToolPermission:
            with self.subTest(permission=permission.value):
                self.assertTrue(PermissionCeiling.allows(permission))
                self.assertEqual(PermissionCeiling.denial_note(permission), "")

    def test_scope_denies_write_and_execute_and_restores_on_exit(self) -> None:
        # [Hidden Failure] Inside the scope only SAFE and READ pass, and the exit removes the ceiling completely.
        with PermissionCeiling.scope(PermissionCeiling.READ_ONLY) as ceiling:
            self.assertEqual(ceiling, frozenset({ToolPermission.SAFE, ToolPermission.READ}))
            self.assertEqual([permission for permission in ToolPermission if PermissionCeiling.allows(permission)], [ToolPermission.SAFE, ToolPermission.READ])
            self.assertEqual(PermissionCeiling.denial_note(ToolPermission.WRITE), _CEILING_NOTE)
        self.assertIsNone(PermissionCeiling.current())
        self.assertTrue(PermissionCeiling.allows(ToolPermission.EXECUTE))

    def test_scope_restores_after_an_exception(self) -> None:
        # [Hidden Failure] An error inside the block cannot leave a ceiling behind for unrelated later work.
        with self.assertRaises(RuntimeError), PermissionCeiling.scope(PermissionCeiling.READ_ONLY):
            raise RuntimeError("boom")
        self.assertIsNone(PermissionCeiling.current())

    def test_a_nested_scope_cannot_widen_the_ceiling(self) -> None:
        # [Silent Failure] A spawned agent that opens its own wide scope still runs under the outer read-only ceiling.
        with PermissionCeiling.scope(PermissionCeiling.READ_ONLY):
            with PermissionCeiling.scope(ToolPermission) as widened:
                self.assertEqual(widened, PermissionCeiling.READ_ONLY)
                self.assertFalse(PermissionCeiling.allows(ToolPermission.WRITE))
            with PermissionCeiling.scope({"read"}) as narrowed:
                self.assertEqual(narrowed, frozenset({ToolPermission.READ}))
                self.assertFalse(PermissionCeiling.allows(ToolPermission.SAFE))
            with PermissionCeiling.scope({ToolPermission.WRITE}) as disjoint:
                self.assertEqual(disjoint, frozenset())
                self.assertEqual(PermissionCeiling.denial_note(ToolPermission.SAFE), "; this run allows no tools")
            self.assertEqual(PermissionCeiling.current(), PermissionCeiling.READ_ONLY)

    def test_rejects_a_bare_string_an_empty_set_and_an_unknown_value(self) -> None:
        # [Hidden Assumption] "read" would iterate as letters, an empty ceiling would refuse isDone, and a typo would refuse silently.
        for allowed in ("read", b"read", (), {"admin"}, {None}, 7):
            with self.subTest(allowed=allowed), self.assertRaises(ConfigurationError):
                with PermissionCeiling.scope(allowed):  # type: ignore[arg-type]
                    pass
        self.assertIsNone(PermissionCeiling.current())

    async def test_tasks_created_inside_inherit_and_concurrent_runs_stay_isolated(self) -> None:
        # [Hidden Failure] A task started inside a scope inherits it, while a run in a sibling task never sees it.
        entered = asyncio.Event()
        release = asyncio.Event()
        seen: dict[str, object] = {}

        async def read_only_run() -> None:
            # Holds a read-only scope open while the sibling run looks, after recording what a child task saw.
            with PermissionCeiling.scope(PermissionCeiling.READ_ONLY):
                seen["child"] = await asyncio.create_task(asyncio.sleep(0, result=PermissionCeiling.current()))
                entered.set()
                await release.wait()

        async def ordinary_run() -> None:
            # Reads the ceiling from a sibling task while the other run's scope is open.
            await entered.wait()
            seen["sibling"] = PermissionCeiling.current()
            release.set()

        await asyncio.gather(read_only_run(), ordinary_run())
        self.assertEqual(seen, {"child": PermissionCeiling.READ_ONLY, "sibling": None})

    async def test_allow_all_policy_and_tool_executor_are_capped_with_a_named_reason(self) -> None:
        # [Silent Failure] An allow-all policy and a ToolExecutor both refuse WRITE under the ceiling and say why, and the tool never runs.
        policy = PermissionPolicy.allow_all()
        call = ToolCall(tool_name="write_notes", arguments={"path": "notes.md", "text": "x"}, call_id="c1")
        executor = ToolExecutor(Tools(_ALL_TOOLS), permission_policy=policy)
        with PermissionCeiling.scope(PermissionCeiling.READ_ONLY):
            self.assertIs(policy.check(write_notes.spec(), call), PermissionDecision.DENY)
            self.assertIs(policy.check(read_notes.spec(), call), PermissionDecision.ALLOW)
            result = await executor.execute_call(call)
        self.assertEqual(result.status.value, "error")
        self.assertEqual(result.output, f"Permission denied for tool 'write_notes' requiring write{_CEILING_NOTE}")
        self.assertEqual(dict(result.metadata)["error"], "permission_denied")
        self.assertEqual(_EFFECTS, [])
        self.assertEqual((await executor.execute_call(call)).status.value, "success")
        self.assertEqual(_EFFECTS, ["write notes.md"])

    def test_the_ceiling_never_widens_a_narrower_caller_policy(self) -> None:
        # [Hidden Assumption] A SAFE-only policy still refuses READ inside a SAFE/READ ceiling, and the denial names only the policy.
        policy = PermissionPolicy(allowed=frozenset({ToolPermission.SAFE}))
        call = ToolCall(tool_name="read_notes", arguments={"path": "notes.md"}, call_id="c1")
        with PermissionCeiling.scope(PermissionCeiling.READ_ONLY):
            self.assertIs(policy.check(read_notes.spec(), call), PermissionDecision.DENY)
            self.assertEqual(PermissionCeiling.denial_note(ToolPermission.READ), "")


class ReadOnlyQuestionTests(unittest.TestCase):
    """Verifies the eight fixed questions stay separate, registered, short, and written in the house layout."""

    def test_preset_registers_eight_ordered_questions_with_threshold_as_veto(self) -> None:
        # [Edge Case] Each piece of evidence has its own key, the preset asks them in order, and its threshold is also its veto.
        self.assertEqual(tuple(question.key.value for question in READ_ONLY_QUESTIONS), _READ_ONLY_KEYS)
        definition = JevPresets.definition(JevPreflightPreset.READ_ONLY)
        self.assertEqual((definition.threshold, definition.veto, definition.gate), (JEV_READ_ONLY_THRESHOLD, JEV_READ_ONLY_THRESHOLD, None))
        questions = JevPreflightRegistry.questions(JevPreflightPreset.READ_ONLY)
        self.assertEqual(tuple(question.name for question in questions), _READ_ONLY_KEYS)
        self.assertTrue(all(question.question_type is JevQuestionType.NOUL for question in questions))
        self.assertIn(JevPreflightPreset.READ_ONLY, JevPresets.available())

    def test_each_question_asks_one_positive_question_in_the_house_layout(self) -> None:
        # [Hidden Assumption] Every brief ends with the shared judgment rules, puts no-task requests on false, and asks one question about `request`.
        for question in READ_ONLY_QUESTIONS:
            with self.subTest(question=question.key.value):
                self.assertTrue(question.instructions.introduction.endswith("It is one of several checks on whether a request only asks for an assessment."))
                self.assertTrue(question.instructions.rules[0].endswith(f"{JUDGE_MEANING} {IGNORE_CLAIMS}"))
                self.assertIn("A request with no task at all", question.instructions.rules[0])
                self.assertIn("no task at all", question.when_false.what)
                self.assertTrue(question.when_true.what.startswith("Choose true when `request` "))
                self.assertTrue(question.when_false.what.startswith("Choose false when `request` "))
                self.assertTrue(question.instructions.question.startswith("Does `request` "))
                self.assertEqual(question.instructions.question.count("?"), 1)
        self.assertEqual(len({question.instructions.question for question in READ_ONLY_QUESTIONS}), len(READ_ONLY_QUESTIONS))

    def test_every_section_is_one_standalone_literal(self) -> None:
        # [Hidden Assumption] Each brief and criterion section is one big string literal, never several elements or adjacent literals.
        tree = ast.parse(Path(inspect.getsourcefile(ReadOnlyAssessmentQuestion) or "").read_text(encoding="utf-8"))
        sections = [node.value for node in ast.walk(tree) if isinstance(node, ast.keyword) and node.arg in {"definitions", "rules", "easy", "boundary"}]
        self.assertEqual(len(sections), len(READ_ONLY_QUESTIONS) * 6)
        for section in sections:
            with self.subTest(line=section.lineno):
                self.assertIsInstance(section, ast.Tuple)
                self.assertEqual(len(section.elts), 1)
                self.assertIsInstance(section.elts[0], ast.Constant)
                self.assertIsInstance(section.elts[0].value, str)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_each_full_question_stays_between_500_and_700_tokens(self) -> None:
        # [Edge Case] Count the rendered brief, both criteria with their examples, and the gap, against the house length.
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
        for question in READ_ONLY_QUESTIONS:
            parts = (question.instructions.render(), question.when_true.what, question.when_true.not_for, *question.when_true.easy, *question.when_true.boundary, question.when_false.what, question.when_false.not_for, *question.when_false.easy, *question.when_false.boundary, question.gap)
            with self.subTest(question=question.key.value):
                self.assertTrue(500 <= len(encoder.encode("\n".join(parts))) <= 700)

    def test_the_request_signals_map_to_their_questions(self) -> None:
        # [Silent Failure] The four requested signals each own a question, and "asks for a change" is asked positively, so a yes always means read-only.
        by_key = {question.key: question for question in READ_ONLY_QUESTIONS}
        assessment = by_key[JevPreflightQuestionKey.READ_ONLY_ASSESSMENT]
        unchanged = by_key[JevPreflightQuestionKey.READ_ONLY_UNCHANGED]
        user_decides = by_key[JevPreflightQuestionKey.READ_ONLY_USER_DECIDES]
        described = by_key[JevPreflightQuestionKey.READ_ONLY_DESCRIBED]
        for word in ("explains", "diagnoses", "judges"):
            self.assertIn(word, assessment.instructions.definitions[0])
        self.assertEqual(unchanged.instructions.question, "Does `request` ask only for work that leaves everything as it is?")
        self.assertIn("Rename", unchanged.when_false.easy[0])
        self.assertIn("do not change anything", user_decides.when_true.easy[0])
        self.assertIn("to change nothing, to only report", user_decides.instructions.rules[0])
        self.assertIn("handle it", user_decides.when_false.easy[0])
        self.assertIn("a recommendation or a plan", described.when_true.what)
        self.assertIn("best way to", described.when_true.boundary[0])


class ReadOnlyGateTests(unittest.IsolatedAsyncioTestCase):
    """Checks the per-question threshold, missing answers, outages, same-gate reset, opt-in absence, and the shared request."""

    def _gate(self, presets: tuple[JevPreflightPreset, ...] = (JevPreflightPreset.READ_ONLY,)) -> tuple[JevPreflightGate, JevResponse]:
        # Creates one configured gate whose flag can be observed over repeated passes.
        response = JevResponse()
        runtime = JevRuntimeSettings(decision=DecisionModelConfig.vidbyte_managed(), preflight=presets)
        return JevPreflightGate(_settings(), runtime, response), response

    async def _requested(self, gate: JevPreflightGate, script: ScriptedDecisionRunner) -> bool:
        # Runs one gate pass, which never blocks the run, and returns whether it limited the run to read-only tools.
        with patch(_GATE_HELPER, new=_decision_helper(script)):
            self.assertTrue(await gate.pass_(_REQUEST))
        return gate.read_only_requested

    async def test_every_answer_at_the_threshold_requests_read_only(self) -> None:
        # [Edge Case] An answer exactly at the threshold passes, all eight answers are recorded in order, and the response reports it.
        gate, response = self._gate()
        self.assertTrue(await self._requested(gate, ScriptedDecisionRunner(default=JEV_READ_ONLY_THRESHOLD)))
        self.assertEqual(tuple(response.state.results[JevPreflightPreset.READ_ONLY].answers), tuple(JevPreflightQuestionKey(value) for value in _READ_ONLY_KEYS))
        self.assertTrue(response.state.read_only)

    async def test_one_answer_below_the_threshold_vetoes_a_high_mean(self) -> None:
        # [Hidden Failure] Seven nearly certain yes answers cannot hide one answer just under the threshold.
        for key in _READ_ONLY_KEYS:
            gate, response = self._gate()
            with self.subTest(question=key):
                self.assertFalse(await self._requested(gate, ScriptedDecisionRunner({key: JEV_READ_ONLY_THRESHOLD - 0.01}, default=0.99)))
                self.assertFalse(response.state.read_only)

    async def test_a_missing_answer_fails_open(self) -> None:
        # [Silent Failure] An unavailable question leaves the run open with its full catalog, never read-only by accident.
        gate, response = self._gate()
        self.assertFalse(await self._requested(gate, ScriptedDecisionRunner(omit=_READ_ONLY_KEYS[3])))
        self.assertFalse(response.state.results[JevPreflightPreset.READ_ONLY].available)
        self.assertFalse(response.state.read_only)

    async def test_a_jev_outage_fails_open(self) -> None:
        # [Hidden Failure] A transient TypeSafe failure marks the preset unavailable and keeps the run exactly as configured.
        gate, response = self._gate()
        self.assertFalse(await self._requested(gate, ScriptedDecisionRunner(fail=True)))
        self.assertFalse(response.state.results[JevPreflightPreset.READ_ONLY].available)

    async def test_the_gate_resets_its_flag_between_passes(self) -> None:
        # [Hidden Assumption] A prior read-only verdict cannot survive an unavailable answer on the same gate instance.
        gate, _ = self._gate()
        self.assertTrue(await self._requested(gate, ScriptedDecisionRunner()))
        self.assertFalse(await self._requested(gate, ScriptedDecisionRunner(omit=_READ_ONLY_KEYS[0])))

    async def test_disabled_preset_asks_no_read_only_question(self) -> None:
        # [Edge Case] Read-only is opt-in, so another preset's request carries none of its questions and the flag stays off.
        gate, response = self._gate((JevPreflightPreset.BULK_WORK,))
        script = ScriptedDecisionRunner()
        self.assertFalse(await self._requested(gate, script))
        names = {question.name for question in script.requests[0].questions}
        self.assertFalse(names & set(_READ_ONLY_KEYS))
        self.assertNotIn(JevPreflightPreset.READ_ONLY, response.state.results)

    async def test_read_only_and_bulk_work_share_one_request(self) -> None:
        # [Hidden Assumption] Both presets ride in one Jev call and each sets only its own flag.
        gate, _ = self._gate((JevPreflightPreset.BULK_WORK, JevPreflightPreset.READ_ONLY))
        script = ScriptedDecisionRunner()
        self.assertTrue(await self._requested(gate, script))
        self.assertTrue(gate.bulk_work_requested)
        self.assertEqual(len(script.requests), 1)
        self.assertEqual(len(script.requests[0].questions), 16)
        vetoed, _ = self._gate((JevPreflightPreset.BULK_WORK, JevPreflightPreset.READ_ONLY))
        self.assertFalse(await self._requested(vetoed, _veto()))
        self.assertTrue(vetoed.bulk_work_requested)


class ReadOnlyToolsTests(unittest.TestCase):
    """Exercises JevReadOnly's catalog filter and ceiling switch directly."""

    def test_keeps_only_safe_and_read_tools_in_order(self) -> None:
        # [Edge Case] WRITE and EXECUTE tools are dropped, and the kept tools keep their catalog order.
        self.assertEqual(JevReadOnly.tools(Tools(_ALL_TOOLS)).names(), ("lookup", "read_notes"))
        self.assertEqual(JevReadOnly.tools(Tools((read_notes, write_notes, lookup))).names(), ("read_notes", "lookup"))

    def test_an_empty_catalog_stays_empty(self) -> None:
        # [Edge Case] A catalog with nothing to keep, or nothing at all, becomes empty rather than failing.
        self.assertEqual(len(JevReadOnly.tools(Tools(()))), 0)
        self.assertEqual(len(JevReadOnly.tools(Tools((write_notes, run_command)))), 0)

    def test_the_ceiling_switch_opens_a_scope_only_for_a_read_only_run(self) -> None:
        # [Silent Failure] A run that is not read-only gets no ceiling at all, not an empty or permissive one.
        with JevReadOnly.ceiling(False):
            self.assertIsNone(PermissionCeiling.current())
        with JevReadOnly.ceiling(True):
            self.assertEqual(PermissionCeiling.current(), PermissionCeiling.READ_ONLY)
        self.assertIsNone(PermissionCeiling.current())


class ReadOnlyRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Runs the real JevRuntime: the gate, the narrowed catalog, the ceiling over tool execution, a specialist, and bulk-work agents."""

    def setUp(self) -> None:
        _EFFECTS.clear()

    async def _run(self, agent: JevAgent, main: MainRunner, decision: ScriptedDecisionRunner, *, options: dict[str, Any] | None = None, **routes: Any) -> Any:
        # Runs one request with every model and decision call scripted, and returns the reply.
        with _route(main, **routes), patch(_GATE_HELPER, new=_decision_helper(decision)):
            return await agent.arun(_REQUEST, **(options or {}))

    async def test_a_read_only_run_offers_only_safe_and_read_tools(self) -> None:
        # [Silent Failure] The model is offered SAFE and READ tools plus isDone, every model call runs under the ceiling, and the agent keeps its catalog.
        agent = _agent()
        main = MainRunner(_call("read_notes", {"path": "notes.md"}, "r1"), _done())
        reply = await self._run(agent, main, ScriptedDecisionRunner())
        self.assertEqual(reply.content, "done")
        for index in range(2):
            self.assertTrue({"lookup", "read_notes", "isDone"} <= main.tool_names(index))
            self.assertFalse({"write_notes", "run_command"} & main.tool_names(index))
        self.assertIn("notes in notes.md", main.sent(1))
        self.assertEqual(main.ceilings, [PermissionCeiling.READ_ONLY, PermissionCeiling.READ_ONLY])
        self.assertEqual(agent.tools.names(), tuple(item.name for item in _ALL_TOOLS))
        self.assertIsNone(PermissionCeiling.current())

    async def test_a_provider_tools_override_is_dropped_on_a_read_only_run(self) -> None:
        # [Silent Failure] A caller's tools override would re-offer every write tool, so a read-only run drops it, as the selector does; a vetoed run keeps it.
        override = [{"type": "function", "name": "write_notes", "description": "Override.", "parameters": {"type": "object", "properties": {}}}]
        main = MainRunner()
        await self._run(_agent(), main, ScriptedDecisionRunner(), options={"tools": override})
        self.assertEqual(main.tool_names(0), {"lookup", "read_notes", "isDone"})
        vetoed = MainRunner()
        await self._run(_agent(), vetoed, _veto(), options={"tools": override})
        self.assertEqual(vetoed.tool_names(0), {"write_notes"})

    async def test_a_hidden_tool_named_by_the_model_never_executes(self) -> None:
        # [Hidden Failure] A model that names a tool it was not offered gets an error result and nothing is written.
        main = MainRunner(_write(), _done())
        await self._run(_agent(), main, ScriptedDecisionRunner())
        self.assertIn("[tool_error kind=unknown_tool]", main.sent(1))
        self.assertIn("Tool 'write_notes' is not registered.", main.sent(1))
        self.assertEqual(_EFFECTS, [])

    async def test_a_write_tool_added_mid_run_is_denied_by_the_ceiling(self) -> None:
        # [Hidden Failure] A tool the agent gains mid-run reaches the catalog, and the ceiling, not the allow-all policy, refuses it.
        holder: list[JevAgent] = []

        @tool
        def enable_writing(reason: str) -> str:
            """Give the agent a tool that writes notes."""
            # Adds the write tool to the agent's own catalog mid-run, as attach_mcp_server would.
            holder[0].add_tool(write_notes)
            return f"enabled for {reason}"

        agent = _agent(_settings(tools=(read_notes, enable_writing)))
        holder.append(agent)
        main = MainRunner(_call("enable_writing", {"reason": "fix"}, "e1"), _write(), _done())
        reply = await self._run(agent, main, ScriptedDecisionRunner())
        denied = [context for context in reply.metadata["tool_calls"] if context.tool_name == "write_notes"]
        self.assertEqual([context.state for context in denied], [ToolCallState.DENIED])
        self.assertEqual((denied[0].result.metadata["error"], denied[0].result.metadata["permission"]), ("permission_denied", "write"))
        self.assertNotIn("write_notes", main.tool_names(0))
        self.assertIn("write_notes", main.tool_names(1))
        self.assertIn(f"Permission denied for tool 'write_notes' requiring write{_CEILING_NOTE}", main.sent(2))
        self.assertEqual(_EFFECTS, [])

    async def test_a_vetoed_request_keeps_the_full_catalog_and_writes(self) -> None:
        # [Edge Case] One clear no leaves the run exactly as configured: every tool offered, no ceiling, and the write happens.
        agent = _agent()
        main = MainRunner(_write(), _done())
        await self._run(agent, main, _veto())
        self.assertTrue({"write_notes", "run_command"} <= main.tool_names(0))
        self.assertEqual(main.ceilings, [None, None])
        self.assertEqual(_EFFECTS, ["write notes.md"])
        self.assertFalse(agent.response.read_only)

    async def test_the_next_run_gets_the_full_catalog_and_no_ceiling(self) -> None:
        # [Hidden Assumption] A read-only run narrows only its own run, so the same agent's next request can write again.
        agent = _agent()
        await self._run(agent, MainRunner(), ScriptedDecisionRunner())
        self.assertTrue(agent.response.read_only)
        main = MainRunner(_write(), _done())
        await self._run(agent, main, _veto())
        self.assertIn("write_notes", main.tool_names(0))
        self.assertEqual(main.ceilings[0], None)
        self.assertEqual(_EFFECTS, ["write notes.md"])

    async def test_a_chosen_specialist_cannot_write(self) -> None:
        # [Hidden Failure] A specialist carries its own allow-all policy and write tool, and the ceiling still refuses its write; without read-only it writes.
        specialist_agent = BaseAgent(name="specialist", system_prompt="Specialist prompt.", provider="openai", model_name="gpt-4.1-mini", tools=[write_notes], permission_policy=PermissionPolicy.allow_all())
        settings = _settings(agents=(JevSpecialist("notes", "Answers questions about the notes.", specialist_agent),))
        refused = MainRunner(_write(), _done())
        main = MainRunner()
        agent = _agent(settings)
        await self._run(agent, main, ScriptedDecisionRunner(choice="notes"), specialist=(specialist_agent, refused))
        self.assertEqual(agent.response.specialist, "notes")
        self.assertTrue(agent.response.read_only)
        self.assertEqual(main.calls, [])
        self.assertIn(f"Permission denied for tool 'write_notes' requiring write{_CEILING_NOTE}", refused.sent(1))
        self.assertEqual(refused.ceilings, [PermissionCeiling.READ_ONLY, PermissionCeiling.READ_ONLY])
        self.assertEqual(_EFFECTS, [])
        allowed = MainRunner(_write(), _done())
        veto = ScriptedDecisionRunner({JevPreflightQuestionKey.READ_ONLY_UNCHANGED.value: 0.2}, choice="notes")
        await self._run(agent, MainRunner(), veto, specialist=(specialist_agent, allowed))
        self.assertEqual(_EFFECTS, ["write notes.md"])

    async def test_bulk_work_agents_receive_only_read_tools(self) -> None:
        # [Hidden Failure] Bulk-work agents are built from the narrowed catalog and run under the ceiling, so none is offered a write tool.
        main = MainRunner(_call(JEV_BULK_WORK_TOOL_NAME, {"tasks": ["Explain test a.", "Explain test b."]}, "b1"), _done())
        workers = WorkerRunner()
        agent = _agent(presets=(JevPreflightPreset.BULK_WORK, JevPreflightPreset.READ_ONLY))
        await self._run(agent, main, ScriptedDecisionRunner(), workers=workers)
        self.assertIn(JEV_BULK_WORK_TOOL_NAME, main.tool_names(0))
        self.assertEqual(len(workers.calls), 2)
        for index in range(2):
            self.assertIn("read_notes", workers.tool_names(index))
            self.assertFalse({"write_notes", "run_command"} & workers.tool_names(index))
        self.assertEqual(len(agent.response.bulk_work.handoffs), 2)

    async def test_the_tool_selector_is_asked_only_about_read_tools(self) -> None:
        # [Silent Failure] The selector runs after the narrowing, so Jev is never asked about, or billed for, a tool the run cannot use.
        selector = ScriptedDecisionRunner()
        main = MainRunner()
        agent = _agent(presets=(JevPreflightPreset.READ_ONLY, JevPreflightPreset.TOOL_SELECTOR))
        with patch(_SELECTOR_HELPER, new=_decision_helper(selector)):
            await self._run(agent, main, ScriptedDecisionRunner())
        asked = json.dumps([question.instructions for question in selector.requests[0].questions])
        self.assertEqual(len(selector.requests[0].questions), 2)
        self.assertIn("read_notes", asked)
        self.assertNotIn("write_notes", asked)
        self.assertNotIn("run_command", asked)
        self.assertFalse({"write_notes", "run_command"} & main.tool_names(0))

    async def test_the_ceiling_is_gone_after_a_run_raises(self) -> None:
        # [Hidden Failure] A provider failure mid-run still closes the scope, so the caller's later work is not read-only.
        main = MainRunner(fail=True)
        with self.assertRaises(Exception):
            await self._run(_agent(), main, ScriptedDecisionRunner())
        self.assertEqual(main.ceilings, [PermissionCeiling.READ_ONLY])
        self.assertIsNone(PermissionCeiling.current())

    async def test_response_reports_read_only_and_resets_each_run(self) -> None:
        # [Silent Failure] JevResponse alone records the decision, and each run's start replaces rather than carries it.
        agent = _agent()
        await self._run(agent, MainRunner(), ScriptedDecisionRunner())
        self.assertTrue(agent.response.read_only)
        self.assertTrue(agent.response.results[JevPreflightPreset.READ_ONLY].passed)
        await self._run(agent, MainRunner(), ScriptedDecisionRunner(omit=_READ_ONLY_KEYS[2]))
        self.assertFalse(agent.response.read_only)
        response = JevResponse()
        response.read_only(True)
        response.start(_REQUEST)
        self.assertFalse(response.state.read_only)


if __name__ == "__main__":
    unittest.main()
