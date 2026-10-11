"""FILE: tests/features/jev_bulk_work/test_jev_bulk_work.py

PURPOSE: Verifies Jev bulk work without provider calls: the settings and records, the eight fixed questions, the gate's per-question threshold, the run_bulk_work tool, its parallel workers, and the runtime that offers the tool.
ROLE IN CODEBASE: Covers the contract in tests/features/jev_bulk_work/FEATURE.md with production settings, registry, gate, tool, ParallelPipeline, and JevRuntime paths.
ARCHITECTURE NOTE: Scripted decision and model runners replace only external boundaries; BaseAgent context building, tool execution, and runtime ordering stay real.
COMMON MODIFICATION PATTERNS: Add regression tests here and list their behavior in FEATURE.md when a public contract changes.
KNOWN EDGE CASES: Worker runners wait for each other, so a launch that ran the workers one after another times out instead of passing.
RELATED DOCS: `docs/design/jev-bulk-work.md` and `tests/features/jev_bulk_work/FEATURE.md`.
TESTS: Run `python scripts/test-jev-bulk-work.py`.
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
from vidbyte import (
    BaseAgent,
    JevAgent,
    JevAgentSettings,
    JevBulkHandoff,
    JevBulkSettings,
    JevBulkWorkResult,
    JevPreflightPreset,
    JevRuntimeSettings,
    JevSpecialist,
    tool,
)
from vidbyte.agents.jev.bulk_work import JevBulkWorker, JevBulkWorkTool
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.response import JevResponse
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.constants.jev import (
    JEV_BULK_WORK_AGENTS,
    JEV_BULK_WORK_MIN_AGENTS,
    JEV_BULK_WORK_THRESHOLD,
    JEV_BULK_WORK_TOOL_NAME,
)
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.dataclasses.tools import ToolCall
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.enums.jev import JevPreflightQuestionKey, JevQuestionType
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev import JevPreflightRegistry, JevPresets
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.preflight.bulk_work import BULK_WORK_QUESTIONS, BulkWorkMultipleItemsQuestion
from vidbyte.lib.jev.preflight.clarity import IGNORE_CLAIMS, JUDGE_MEANING
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.prompts import Prompts
from vidbyte.tools.agent_tool import AgentTool

_GATE_HELPER = "vidbyte.agents.jev.gate.gate.DecisionModelHelper"
_REQUEST = "Summarize these independent reports separately: alpha and beta. Keep their original names."
_TASKS = ["Summarize report alpha.", "Summarize report beta."]
_BULK_KEYS = tuple(key.value for key in (
    JevPreflightQuestionKey.BULK_WORK_MULTIPLE_ITEMS,
    JevPreflightQuestionKey.BULK_WORK_KNOWN_ITEMS,
    JevPreflightQuestionKey.BULK_WORK_SAME_OPERATION,
    JevPreflightQuestionKey.BULK_WORK_SEPARATE_RESULTS,
    JevPreflightQuestionKey.BULK_WORK_INDEPENDENT_ITEMS,
    JevPreflightQuestionKey.BULK_WORK_SEPARATE_CHANGES,
    JevPreflightQuestionKey.BULK_WORK_ANY_ORDER,
    JevPreflightQuestionKey.BULK_WORK_SUBSTANTIAL_ITEMS,
))


def _settings(**overrides: Any) -> JevAgentSettings:
    # Builds one valid generative settings object and applies only the requested test overrides.
    values: dict[str, Any] = {"name": "owner", "system_prompt": "Owner instruction.", "provider": "openai", "model_name": "gpt-4.1-mini"}
    values.update(overrides)
    return JevAgentSettings(**values)


def _answer(name: str, probability: float) -> JevAnswer:
    # Builds a normalized positive or negative fixed-question answer at the exact requested probability.
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if probability >= 0.5 else "false", probabilities={"true": probability, "false": 1.0 - probability}, noul=probability)


class ScriptedDecisionRunner:
    """Returns fixed Noul and Choice answers while retaining each batched request."""

    def __init__(self, probabilities: dict[str, float] | None = None, *, default: float = 0.9, omit: str | None = None, choice: str = "none") -> None:
        # Saves one answer map for each gate call.
        self.probabilities = probabilities or {}
        self.default = default
        self.omit = omit
        self.choice = choice
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> Any:
        # Answers every question unless the test deliberately omits one field.
        self.requests.append(request)
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
    """Scripted main-agent runner: one run_bulk_work call per task list, then isDone; it keeps every call's keyword arguments."""

    def __init__(self, *task_lists: object) -> None:
        self.responses: list[object] = [_call(JEV_BULK_WORK_TOOL_NAME, {"tasks": tasks}, f"b{index}") for index, tasks in enumerate(task_lists)]
        self.responses.append(_call("isDone", {"final_answer": "done"}, "end"))
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)

    def tool_names(self, index: int) -> set[str]:
        # Returns the tool names the model was offered on one call, whatever the provider schema shape.
        return {schema.get("name") or schema.get("function", {}).get("name") for schema in self.calls[index].get("tools", ())}

    def sent(self, index: int = -1) -> str:
        # Returns every message of one call as text, including tool outputs.
        return json.dumps(self.calls[index]["messages"], default=str)


class WorkerRunner:
    """Scripted runner for the bulk-work agents: answers each task, fails the chosen ones, and waits until `together` workers are running."""

    def __init__(self, *, together: int = 1, fail: tuple[str, ...] = (), delays: dict[str, float] | None = None) -> None:
        self.together = together
        self.fail = fail
        self.delays = delays or {}
        self.calls: list[dict[str, Any]] = []
        self.active = 0
        self.most_active = 0
        self.started = asyncio.Event()

    async def arun(self, prompt: str, *, system: str = "", **kwargs: Any) -> TextModelResponse:
        # A launch that runs workers one after another never reaches `together`, so the wait times out and the test fails.
        self.calls.append({"prompt": prompt, "system": system, **kwargs})
        task = prompt.rsplit("# Your task\n\n", 1)[-1]
        self.active += 1
        self.most_active = max(self.most_active, self.active)
        if self.active >= self.together:
            self.started.set()
        try:
            await asyncio.wait_for(self.started.wait(), timeout=2)
            await asyncio.sleep(self.delays.get(task, 0.0))
        finally:
            self.active -= 1
        if task in self.fail:
            raise VidbyteSdkError(f"provider failed on {task}")
        return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", text=f"result for {task}", raw={}, usage={"input_tokens": 10, "output_tokens": 2})

    def tasks(self) -> list[str]:
        # Returns the task each worker call received, in the order the workers called the model.
        return [call["prompt"].rsplit("# Your task\n\n", 1)[-1] for call in self.calls]


def _route(main: object, workers: object, *, specialist: tuple[BaseAgent, object] | None = None) -> Any:
    # Sends the bulk-work agents to the worker runner, a chosen specialist to its own runner, and every other agent to the main runner.
    def runner_for(agent: BaseAgent) -> tuple[object, str]:
        if specialist is not None and agent is specialist[0]:
            return specialist[1], RUNNER_TYPE_TEXT
        return (workers if "-bulk-" in agent.name else main), RUNNER_TYPE_TEXT

    return patch.object(BaseAgent, "_runner_for_model", new=runner_for)


def _bulk_agent(*, settings: JevAgentSettings | None = None, presets: tuple[JevPreflightPreset, ...] = (JevPreflightPreset.BULK_WORK,)) -> JevAgent:
    # Builds a JevAgent with fixed decision credentials and the requested preflight presets.
    return JevAgent(settings or _settings(), JevRuntimeSettings(decision=DecisionModelConfig.vidbyte_managed(), preflight=presets))


def _tool(settings: JevAgentSettings | None = None) -> tuple[JevBulkWorkTool, JevResponse]:
    # Builds one run's tool the way JevRuntime does, with no selected tools, and the response it records into.
    response = JevResponse()
    build = JevBulkWorkTool.for_agent(settings or _settings(), response)
    return build(_REQUEST, ()), response


def _launch(tasks: object) -> ToolCall:
    # Builds the main agent's run_bulk_work call with the given tasks argument.
    return ToolCall(tool_name=JEV_BULK_WORK_TOOL_NAME, arguments={"tasks": tasks}, call_id="launch")


class JevBulkSettingsTests(unittest.TestCase):
    """Pins the two public settings, their validation, the result records, and the API exports."""

    def test_defaults_are_the_named_constants(self) -> None:
        # [Edge Case] The owner gets four agents and one 0.75 threshold unless they set otherwise.
        defaults = JevBulkSettings()
        self.assertEqual((defaults.agents, defaults.threshold), (JEV_BULK_WORK_AGENTS, JEV_BULK_WORK_THRESHOLD))
        self.assertEqual(JevBulkSettings(agents=JEV_BULK_WORK_MIN_AGENTS, threshold=1).threshold, 1.0)

    def test_rejects_a_team_too_small_to_split_and_a_threshold_that_is_not_a_probability(self) -> None:
        # [Hidden Failure] bool, non-integers, and fewer than two agents fail at construction, as does any threshold outside [0, 1].
        for value in (True, 1.5, "4", None, 1, 0, -1):
            with self.subTest(agents=value), self.assertRaises(ConfigurationError):
                JevBulkSettings(agents=value)  # type: ignore[arg-type]
        for value in (True, 1.5, -0.1, "0.75", None, float("nan")):
            with self.subTest(threshold=value), self.assertRaises(ConfigurationError):
                JevBulkSettings(threshold=value)  # type: ignore[arg-type]

    def test_rejects_a_wrong_nested_settings_type_and_exports_the_public_api(self) -> None:
        # [Hidden Assumption] The nested API accepts only JevBulkSettings and the root exports are the defining types.
        import vidbyte
        from vidbyte.lib.dataclasses import jev as records
        self.assertIs(vidbyte.JevBulkSettings, JevBulkSettings)
        self.assertIs(vidbyte.JevBulkHandoff, records.JevBulkHandoff)
        self.assertIs(vidbyte.JevBulkWorkResult, records.JevBulkWorkResult)
        with self.assertRaises(ConfigurationError):
            _settings(bulk_work=object())

    def test_records_derive_completion_from_the_reply_and_reject_a_launch_of_one(self) -> None:
        # [Silent Failure] Completion is read from the reply itself, so no record can claim success without one; a launch always has at least two agents.
        done = JevBulkHandoff(task="Summarize report alpha.", output="alpha summary")
        failed = JevBulkHandoff(task="Summarize report beta.", output="")
        self.assertEqual((done.completed, failed.completed), (True, False))
        self.assertEqual(JevBulkWorkResult(handoffs=(done, failed)).handoffs, (done, failed))
        for task, output in (("t", "  "), ("t", " reply"), ("t", None), (" ", "reply")):
            with self.subTest(task=task, output=output), self.assertRaises(ConfigurationError):
                JevBulkHandoff(task=task, output=output)  # type: ignore[arg-type]
        for handoffs in ((done,), [done, failed], (done, "failed")):
            with self.subTest(handoffs=handoffs), self.assertRaises(ConfigurationError):
                JevBulkWorkResult(handoffs=handoffs)  # type: ignore[arg-type]


class JevBulkQuestionTests(unittest.TestCase):
    """Verifies the eight fixed questions stay separate, registered, short, and written in the house layout."""

    def test_preset_registers_eight_ordered_questions_with_one_threshold(self) -> None:
        # [Edge Case] Each piece of evidence has its own key, the preset asks them in order, and its threshold is also its veto.
        self.assertEqual(tuple(question.key.value for question in BULK_WORK_QUESTIONS), _BULK_KEYS)
        definition = JevPresets.definition(JevPreflightPreset.BULK_WORK)
        self.assertEqual((definition.threshold, definition.veto), (JEV_BULK_WORK_THRESHOLD, JEV_BULK_WORK_THRESHOLD))
        questions = JevPreflightRegistry.questions(JevPreflightPreset.BULK_WORK)
        self.assertEqual(tuple(question.name for question in questions), _BULK_KEYS)
        self.assertTrue(all(question.question_type is JevQuestionType.NOUL for question in questions))

    def test_each_question_asks_one_positive_question_in_the_house_layout(self) -> None:
        # [Hidden Assumption] Every brief defines an item first, ends with the shared judgment rules, and asks one question about `request`.
        for question in BULK_WORK_QUESTIONS:
            with self.subTest(question=question.key.value):
                self.assertTrue(question.instructions.definitions[0].startswith("An item is one separate thing the user wants worked on"))
                self.assertTrue(question.instructions.rules[0].endswith(f"{JUDGE_MEANING} {IGNORE_CLAIMS}"))
                self.assertTrue(question.instructions.question.startswith("Does `request` "))
                self.assertEqual(question.instructions.question.count("?"), 1)
        self.assertEqual(len({question.instructions.question for question in BULK_WORK_QUESTIONS}), len(BULK_WORK_QUESTIONS))

    def test_every_section_is_one_standalone_literal(self) -> None:
        # [Hidden Assumption] The skill writes each brief and criterion section as one big string literal, never several elements or adjacent literals.
        tree = ast.parse(Path(inspect.getsourcefile(BulkWorkMultipleItemsQuestion) or "").read_text(encoding="utf-8"))
        sections = [node.value for node in ast.walk(tree) if isinstance(node, ast.keyword) and node.arg in {"definitions", "rules", "easy", "boundary"}]
        self.assertEqual(len(sections), len(BULK_WORK_QUESTIONS) * 6)
        for section in sections:
            with self.subTest(line=section.lineno):
                self.assertIsInstance(section, ast.Tuple)
                self.assertEqual(len(section.elts), 1)
                self.assertIsInstance(section.elts[0], ast.Constant)
                self.assertIsInstance(section.elts[0].value, str)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_each_full_question_stays_near_five_hundred_cl100k_tokens(self) -> None:
        # [Edge Case] Count the rendered brief, both criteria with their examples, and the gap, against the house length.
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
        for question in BULK_WORK_QUESTIONS:
            parts = (question.instructions.render(), question.when_true.what, question.when_true.not_for, *question.when_true.easy, *question.when_true.boundary, question.when_false.what, question.when_false.not_for, *question.when_false.easy, *question.when_false.boundary, question.gap)
            with self.subTest(question=question.key.value):
                self.assertTrue(500 <= len(encoder.encode("\n".join(parts))) <= 700)


class JevBulkGateTests(unittest.IsolatedAsyncioTestCase):
    """Checks the per-question threshold, the owner's configured threshold, missing answers, and same-gate reset."""

    def _gate(self, settings: JevAgentSettings | None = None) -> tuple[JevPreflightGate, JevResponse]:
        # Creates one configured gate whose flag can be observed over repeated passes.
        response = JevResponse()
        runtime = JevRuntimeSettings(decision=DecisionModelConfig.vidbyte_managed(), preflight=(JevPreflightPreset.BULK_WORK,))
        return JevPreflightGate(settings or _settings(), runtime, response), response

    async def _requested(self, gate: JevPreflightGate, script: ScriptedDecisionRunner) -> bool:
        # Runs one gate pass, which never blocks the run, and returns whether it approved bulk work.
        with patch(_GATE_HELPER, new=_decision_helper(script)):
            self.assertTrue(await gate.pass_(_REQUEST))
        return gate.bulk_work_requested

    async def test_every_question_at_the_threshold_approves_bulk_work(self) -> None:
        # [Edge Case] An answer exactly at the threshold passes, and all eight answers are recorded in order.
        gate, response = self._gate()
        self.assertTrue(await self._requested(gate, ScriptedDecisionRunner(default=JEV_BULK_WORK_THRESHOLD)))
        self.assertEqual(tuple(response.state.results[JevPreflightPreset.BULK_WORK].answers), tuple(JevPreflightQuestionKey(value) for value in _BULK_KEYS))

    async def test_one_answer_below_the_threshold_vetoes_a_high_mean(self) -> None:
        # [Hidden Failure] Seven nearly certain yes answers cannot hide one answer just under the threshold.
        for key in _BULK_KEYS:
            gate, _ = self._gate()
            with self.subTest(question=key):
                self.assertFalse(await self._requested(gate, ScriptedDecisionRunner({key: JEV_BULK_WORK_THRESHOLD - 0.01}, default=0.99)))

    async def test_the_owner_threshold_replaces_the_preset_default(self) -> None:
        # [Hidden Assumption] JevBulkSettings.threshold is the bar every question must reach, in both directions.
        answers = ScriptedDecisionRunner(default=0.8)
        strict, _ = self._gate(_settings(bulk_work=JevBulkSettings(threshold=0.85)))
        self.assertFalse(await self._requested(strict, answers))
        lenient, _ = self._gate(_settings(bulk_work=JevBulkSettings(threshold=0.6)))
        self.assertTrue(await self._requested(lenient, ScriptedDecisionRunner(default=0.65)))
        self.assertEqual(JevPresets.definition(JevPreflightPreset.BULK_WORK).threshold, JEV_BULK_WORK_THRESHOLD)

    async def test_a_missing_answer_fails_open_without_approving_bulk_work(self) -> None:
        # [Silent Failure] An unavailable question leaves ordinary execution open while bulk work stays off.
        gate, response = self._gate()
        self.assertFalse(await self._requested(gate, ScriptedDecisionRunner(omit=_BULK_KEYS[4])))
        self.assertFalse(response.state.results[JevPreflightPreset.BULK_WORK].available)

    async def test_the_gate_resets_its_flag_between_passes(self) -> None:
        # [Hidden Assumption] A prior approval cannot survive an unavailable answer on the same gate instance.
        gate, _ = self._gate()
        self.assertTrue(await self._requested(gate, ScriptedDecisionRunner()))
        self.assertFalse(await self._requested(gate, ScriptedDecisionRunner(omit=_BULK_KEYS[1])))


class JevBulkToolTests(unittest.IsolatedAsyncioTestCase):
    """Exercises the run_bulk_work tool and its JevBulkWorker stages directly."""

    def test_spec_bounds_the_task_count_by_the_configured_agents(self) -> None:
        # [Edge Case] The schema the model sees allows from two tasks up to the owner's agent count, and nothing else.
        built, _ = _tool(_settings(bulk_work=JevBulkSettings(agents=3)))
        spec = built.spec()
        tasks = spec.input_schema["properties"]["tasks"]
        self.assertEqual(spec.name, JEV_BULK_WORK_TOOL_NAME)
        self.assertEqual((tasks["minItems"], tasks["maxItems"], tasks["items"]), (JEV_BULK_WORK_MIN_AGENTS, 3, {"type": "string"}))
        self.assertFalse(spec.input_schema["additionalProperties"])
        self.assertTrue(spec.metadata["internal"])
        self.assertIn("at least 2 and no more than 3", tasks["description"])

    def test_a_caller_tool_with_the_reserved_name_fails_when_the_agent_is_built(self) -> None:
        # [Hidden Failure] The tool joins the catalog mid-run, so a name clash must surface at construction instead.
        @tool(name=JEV_BULK_WORK_TOOL_NAME)
        def run_bulk_work(tasks: str) -> str:
            """A caller tool that happens to use the reserved name."""
            return tasks

        with self.assertRaises(ConfigurationError):
            _bulk_agent(settings=_settings(tools=(run_bulk_work,)))
        self.assertIsNotNone(_bulk_agent(settings=_settings(tools=(run_bulk_work,)), presets=()))

    async def test_tasks_the_agents_cannot_run_are_rejected_and_the_tool_stays_open(self) -> None:
        # [Silent Failure] A malformed, blank, too-small, or too-large task list starts no agent and says what to fix.
        built, response = _tool()
        workers = WorkerRunner()
        too_many = [f"Summarize report {index}." for index in range(JEV_BULK_WORK_AGENTS + 1)]
        with _route(None, workers):
            for tasks in ("Summarize both.", ["Summarize alpha.", "  "], ["Summarize alpha."], too_many, None):
                with self.subTest(tasks=tasks):
                    result = await built.execute(_launch(tasks))
                    self.assertEqual(result.status.value, "error")
                    self.assertIn("The agents were not started because the tasks need a change", result.output)
            self.assertIn(f"received {JEV_BULK_WORK_AGENTS + 1}", (await built.execute(_launch(too_many))).output)
        self.assertFalse(built.closed)
        self.assertEqual(workers.calls, [])
        self.assertIsNone(response.state.bulk_work)

    async def test_workers_run_at_the_same_time_and_hand_back_in_task_order(self) -> None:
        # [Hidden Assumption] Every worker starts before any finishes, and the slowest first task still comes back first.
        built, response = _tool()
        tasks = ["Summarize report alpha.", "Summarize report beta.", "Summarize report gamma."]
        workers = WorkerRunner(together=3, delays={tasks[0]: 0.05})
        with _route(None, workers):
            result = await built.execute(_launch([f"  {task}  " for task in tasks]))
        self.assertEqual(result.status.value, "success")
        self.assertEqual(workers.most_active, 3)
        self.assertEqual(response.state.bulk_work, JevBulkWorkResult(handoffs=tuple(JevBulkHandoff(task=task, output=f"result for {task}") for task in tasks)))
        self.assertLess(result.output.index("## Task 1 (completed)"), result.output.index("## Task 3 (completed)"))
        self.assertIn("result for Summarize report gamma.", result.output)
        self.assertIn("Treat each handoff as a report to check", result.output)

    async def test_a_failed_worker_is_marked_failed_while_the_others_hand_back(self) -> None:
        # [Hidden Failure] One provider error neither cancels its siblings nor leaks its message into the main agent's view.
        built, response = _tool()
        workers = WorkerRunner(together=2, fail=(_TASKS[1],))
        with _route(None, workers):
            result = await built.execute(_launch(_TASKS))
        self.assertEqual(result.status.value, "success")
        self.assertIn(f"## Task 2 (failed)\n\n{_TASKS[1]}", result.output)
        self.assertIn(f"result for {_TASKS[0]}", result.output)
        self.assertNotIn("provider failed", result.output)
        self.assertEqual([handoff.completed for handoff in response.state.bulk_work.handoffs], [True, False])

    async def test_the_tool_launches_once_per_run(self) -> None:
        # [Edge Case] After one launch every call, valid or not, returns the closed message and starts nothing.
        built, _ = _tool()
        workers = WorkerRunner(together=2)
        with _route(None, workers):
            await built.execute(_launch(_TASKS))
            again = await built.execute(_launch(_TASKS))
        self.assertEqual(again.status.value, "error")
        self.assertEqual(again.output, Prompts().get(Prompt.JEV_BULK_WORK_CLOSED_PROMPT))
        self.assertEqual(len(workers.calls), 2)

    async def test_a_worker_gets_the_owner_prompt_its_task_and_its_own_copy_of_the_selected_tools(self) -> None:
        # [Silent Failure] Agent-bound tools are cloned so they bind to the worker, plain tools are shared, and the owner's limits carry over.
        delegate = BaseAgent(name="delegate", system_prompt="Delegate prompt.", provider="openai", model_name="gpt-4.1-mini", agent_metadata=AgentMetadata(name="delegate", description="Delegate work.", use_cases="Testing delegation."))
        original_agent_tool = AgentTool(delegate)

        @tool
        def selected_lookup(query: str) -> str:
            """Look up one selected record."""
            return query

        settings = _settings(tools=(original_agent_tool, selected_lookup))
        worker = JevBulkWorker(settings, (original_agent_tool, selected_lookup), 2, _TASKS[1])
        self.assertEqual(worker.agent.name, "owner-bulk-2")
        self.assertEqual(worker.agent.tools.names()[:2], (original_agent_tool.name, selected_lookup.name))
        self.assertIsNot(worker.agent.tools[0], original_agent_tool)
        self.assertIs(worker.agent.tools[1], selected_lookup)
        self.assertIs(worker.agent.permission_policy, settings.permission_policy)
        self.assertTrue(worker.agent.system_prompt.startswith("Owner instruction.\n\n"))
        self.assertIn(Prompts().get(Prompt.JEV_BULK_WORK_WORKER_SYSTEM_PROMPT), worker.agent.system_prompt)
        workers = WorkerRunner()
        with _route(None, workers):
            section = await worker.run(_REQUEST)
        self.assertEqual(workers.calls[0]["prompt"], f"# Original request\n\n{_REQUEST}\n\n# Your task\n\n{_TASKS[1]}")
        self.assertEqual(section, f"## Task 2 (completed)\n\n{_TASKS[1]}\n\n### Handoff\n\nresult for {_TASKS[1]}")


class JevBulkRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Runs the real JevRuntime: the gate, the tool offer, a scripted main agent that calls the tool, and its workers."""

    async def _run(self, agent: JevAgent, main: MainRunner, workers: WorkerRunner, decision: ScriptedDecisionRunner, **options: Any) -> Any:
        # Runs one request with every model and decision call scripted, and returns the reply.
        with _route(main, workers), patch(_GATE_HELPER, new=_decision_helper(decision)):
            return await agent.arun(_REQUEST, **options)

    async def test_an_approved_request_offers_the_tool_and_the_handoffs_return_as_its_result(self) -> None:
        # [Silent Failure] The main agent writes the tasks, the workers get the request and their task, and the handoffs come back as the tool result.
        main = MainRunner(_TASKS)
        workers = WorkerRunner(together=2)
        agent = _bulk_agent()
        original_names = agent.tools.names()
        reply = await self._run(agent, main, workers, ScriptedDecisionRunner())
        self.assertEqual(reply.content, "done")
        self.assertIn(JEV_BULK_WORK_TOOL_NAME, main.tool_names(0))
        self.assertEqual(sorted(workers.tasks()), sorted(_TASKS))
        self.assertTrue(all(call["prompt"].startswith(f"# Original request\n\n{_REQUEST}") for call in workers.calls))
        self.assertTrue(all("Owner instruction." in call["system"] for call in workers.calls))
        self.assertIn("Handoffs from the bulk-work agents", main.sent())
        self.assertIn(f"result for {_TASKS[1]}", main.sent())
        self.assertEqual(agent.response.bulk_work.handoffs, tuple(JevBulkHandoff(task=task, output=f"result for {task}") for task in _TASKS))
        self.assertEqual(agent.response.input, _REQUEST)
        # The JevAgent usage ledger counts the main agent's two calls and each worker's one call exactly once.
        self.assertEqual(agent.get_usage().model_call_count, 4)
        self.assertEqual(agent.tools.names(), original_names)

    async def test_a_request_the_gate_does_not_approve_never_sees_the_tool(self) -> None:
        # [Hidden Failure] One clear no keeps the work on the main agent: no tool, no worker, and no result.
        main = MainRunner()
        workers = WorkerRunner()
        agent = _bulk_agent()
        await self._run(agent, main, workers, ScriptedDecisionRunner({_BULK_KEYS[5]: 0.2}))
        self.assertNotIn(JEV_BULK_WORK_TOOL_NAME, main.tool_names(0))
        self.assertEqual(workers.calls, [])
        self.assertIsNone(agent.response.bulk_work)

    async def test_without_the_preset_there_is_no_tool_and_no_gate_question(self) -> None:
        # [Edge Case] Bulk work is opt-in, so its absence adds no constructor, no tool, and no decision call.
        main = MainRunner()
        decision = ScriptedDecisionRunner()
        agent = _bulk_agent(presets=())
        await self._run(agent, main, WorkerRunner(), decision)
        self.assertIsNone(agent.bulk_work)
        self.assertNotIn(JEV_BULK_WORK_TOOL_NAME, main.tool_names(0))
        self.assertEqual(len(main.calls), 1)
        self.assertEqual(decision.requests, [])

    async def test_rejected_tasks_return_what_to_fix_and_corrected_tasks_launch(self) -> None:
        # [Hidden Assumption] A task list the agents cannot run reaches the main agent as an error it can correct on the next call.
        main = MainRunner(_TASKS[:1], _TASKS)
        workers = WorkerRunner(together=2)
        agent = _bulk_agent()
        await self._run(agent, main, workers, ScriptedDecisionRunner())
        self.assertIn("tasks must hold from 2 through 4 tasks; received 1.", main.sent(1))
        self.assertIn(JEV_BULK_WORK_TOOL_NAME, main.tool_names(1))
        self.assertEqual(len(workers.calls), 2)
        self.assertEqual(len(agent.response.bulk_work.handoffs), 2)

    async def test_a_chosen_specialist_answers_before_bulk_work_is_offered(self) -> None:
        # [Hidden Assumption] A specialist receives the request and the main agent never runs, so no tool is offered.
        specialist_runner = WorkerRunner()
        specialist_agent = BaseAgent(name="specialist", system_prompt="Specialist prompt.", provider="openai", model_name="gpt-4.1-mini")
        agent = _bulk_agent(settings=_settings(agents=(JevSpecialist("review", "Reviews these documents.", specialist_agent),)))
        main = MainRunner()
        with _route(main, WorkerRunner(), specialist=(specialist_agent, specialist_runner)), patch(_GATE_HELPER, new=_decision_helper(ScriptedDecisionRunner(choice="review"))):
            await agent.arun(_REQUEST)
        self.assertEqual(agent.response.specialist, "review")
        self.assertEqual(len(specialist_runner.calls), 1)
        self.assertEqual(main.calls, [])
        self.assertIsNone(agent.response.bulk_work)

    async def test_a_repeated_run_clears_the_earlier_launch(self) -> None:
        # [Hidden Assumption] The same agent's next run starts with a fresh tool and no earlier result.
        agent = _bulk_agent()
        await self._run(agent, MainRunner(_TASKS), WorkerRunner(together=2), ScriptedDecisionRunner())
        self.assertIsNotNone(agent.response.bulk_work)
        main = MainRunner()
        workers = WorkerRunner()
        await self._run(agent, main, workers, ScriptedDecisionRunner(omit=_BULK_KEYS[0]))
        self.assertIsNone(agent.response.bulk_work)
        self.assertNotIn(JEV_BULK_WORK_TOOL_NAME, main.tool_names(0))
        self.assertEqual(workers.calls, [])

    def test_the_response_writer_resets_the_bulk_record(self) -> None:
        # [Silent Failure] JevResponse alone writes the launch, and start replaces rather than carries an old result.
        response = JevResponse()
        response.bulk_work(JevBulkWorkResult(handoffs=(JevBulkHandoff("a", "A"), JevBulkHandoff("b", ""))))
        old_state = response.state
        response.start(_REQUEST)
        self.assertIsNot(response.state, old_state)
        self.assertIsNone(response.state.bulk_work)


if __name__ == "__main__":
    unittest.main()
