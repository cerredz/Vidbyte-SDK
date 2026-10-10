"""FILE: tests/features/jev_bulk_work/test_jev_bulk_work.py

PURPOSE: Verifies Jev bulk-work eligibility, complete planning, bounded execution, safe failures, tool isolation, usage, and final synthesis without provider calls.
ROLE IN CODEBASE: Covers the contract in tests/features/jev_bulk_work/FEATURE.md with production settings, registry, JevBulkWork, and JevRuntime paths.
ARCHITECTURE NOTE: Stub decision/model runners replace only external boundaries; BaseAgent context construction and runtime ordering remain real.
COMMON MODIFICATION PATTERNS: Add regression tests here and list their behavior in FEATURE.md when a public contract changes.
KNOWN EDGE CASES: Tests assert no user request, tool schema, or caller-owned context object is truncated or mutated.
RELATED DOCS: `docs/design/jev-bulk-work.md` and `tests/features/jev_bulk_work/FEATURE.md`.
TESTS: Run `python scripts/test-jev-bulk-work.py`.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import (
    BaseAgent,
    JevAgent,
    JevAgentSettings,
    JevBulkItemError,
    JevBulkPlanningError,
    JevBulkSettings,
    JevPreflightPreset,
    JevRuntimeSettings,
    JevSpecialist,
    tool,
)
from vidbyte.agents.jev.bulk_work import JevBulkWork
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.response import JevResponse
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.constants.jev import (
    JEV_BULK_DEFAULT_MAX_ITEMS,
    JEV_BULK_DEFAULT_MAX_PARALLEL_AGENTS,
    JEV_BULK_DEFAULT_PLANNER_MAX_ITERATIONS,
    JEV_BULK_DEFAULT_PLANNER_MAX_TOKENS,
    JEV_BULK_MIN_ITEMS,
    JEV_BULK_MIN_PARALLEL_AGENTS,
    JEV_BULK_MIN_PLANNER_MAX_ITERATIONS,
    JEV_BULK_MIN_PLANNER_MAX_TOKENS,
    JEV_BULK_WORK_THRESHOLD,
    JEV_BULK_WORK_VETO_THRESHOLD,
)
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.dataclasses.context import (
    BaseAgentContext,
    ContextArtifact,
    ContextResponse,
    ContextToolCall,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevBulkItemResult,
    JevBulkPlan,
    JevBulkPlanItem,
    JevBulkWorkResult,
    JevDecisionRequest,
)
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.enums.jev import (
    JevBulkItemError,
    JevBulkPlanningError,
    JevPreflightQuestionKey,
    JevQuestionType,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev import JevPreflightRegistry, JevPresets
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.preflight.bulk_work import BULK_WORK_QUESTIONS
from vidbyte.lib.jev.preflight.clarity import IGNORE_CLAIMS, JUDGE_MEANING
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.prompts import Prompts
from vidbyte.tools.agent_tool import AgentTool

_ROOT = Path(__file__).resolve().parents[3]
_REQUEST = "Summarize these independent reports separately: alpha and beta. Keep their original names."
_BULK_KEYS = tuple(key.value for key in (
    JevPreflightQuestionKey.BULK_WORK_MULTIPLE_ITEMS,
    JevPreflightQuestionKey.BULK_WORK_SAME_OPERATION,
    JevPreflightQuestionKey.BULK_WORK_INDEPENDENT_ITEMS,
))


def _plan_payload(count: int) -> dict[str, Any]:
    # Creates an ordered plan with one stable id, title, and self-contained prompt per item.
    return {"items": [{"identifier": f"item_{index}", "title": f"Item {index}", "prompt": f"Summarize report {index}."} for index in range(count)]}


def _settings(**overrides: Any) -> JevAgentSettings:
    # Builds one valid generative settings object and applies only the requested test overrides.
    values: dict[str, Any] = {"name": "bulk-test", "system_prompt": "Owner instruction.", "provider": "openai", "model_name": "gpt-4.1-mini"}
    values.update(overrides)
    return JevAgentSettings(**values)


def _answer(name: str, probability: float) -> JevAnswer:
    # Builds a normalized positive or negative fixed-question answer at the exact requested probability.
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if probability >= 0.5 else "false", probabilities={"true": probability, "false": 1.0 - probability}, noul=probability)


class ScriptedDecisionRunner:
    """Returns fixed Noul and Choice answers while retaining each batched request."""

    def __init__(self, probabilities: dict[str, float] | None = None, *, omit: str | None = None, choice: str = "none") -> None:
        # Saves one answer map for each gate or selector call.
        self.probabilities = probabilities or {}
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
                answers[question.name] = _answer(question.name, self.probabilities.get(question.name, 0.9))
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


class ScriptedModelRunner:
    """Responds as planner, worker, or main agent based on the actual assembled system context."""

    def __init__(self, *, plan: dict[str, Any] | None = None, failures: tuple[str, ...] = (), delays: dict[str, float] | None = None, block_workers: bool = False) -> None:
        # Configures offline responses and observable worker scheduling.
        self.plan = _plan_payload(2) if plan is None else plan
        self.failures = failures
        self.delays = delays or {}
        self.block_workers = block_workers
        self.calls: list[dict[str, Any]] = []
        self.worker_started = asyncio.Event()
        self.release_workers = asyncio.Event()
        self.active_workers = 0
        self.max_active_workers = 0
        self.cancelled_workers = 0
        self.completed_items: list[str] = []

    async def arun(self, prompt: str, *, system: str = "", **kwargs: Any) -> TextModelResponse:
        # Captures the provider-facing prompt and returns one fake text response without network access.
        call = {"prompt": prompt, "system": system, **kwargs}
        self.calls.append(call)
        if "You are JevBulkWorkPlanner" in system:
            text = json.dumps(self.plan)
        elif "You are an isolated worker handling one item" in system:
            text = await self._worker_response(prompt)
        else:
            text = "main synthesis"
        return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", text=text, raw={}, usage={"input_tokens": 10, "output_tokens": 2})

    async def _worker_response(self, prompt: str) -> str:
        # Tracks active work, optionally blocks for cancellation tests, and may raise a private error.
        item = json.loads(prompt)["work_item"]
        identifier = item["identifier"]
        self.active_workers += 1
        self.max_active_workers = max(self.max_active_workers, self.active_workers)
        if self.active_workers >= 2:
            self.worker_started.set()
        try:
            if self.block_workers:
                await self.release_workers.wait()
            else:
                await asyncio.sleep(self.delays.get(identifier, 0.0))
            if identifier in self.failures:
                raise RuntimeError(f"secret worker detail for {identifier}")
            self.completed_items.append(identifier)
            return f"result for {identifier}"
        except asyncio.CancelledError:
            self.cancelled_workers += 1
            raise
        finally:
            self.active_workers -= 1


def _patch_model_runners(runner: ScriptedModelRunner) -> Any:
    # Routes every fresh BaseAgent through the same offline provider runner while keeping its real runtime.
    return patch.object(BaseAgent, "_runner_for_model", new=lambda _agent: (runner, RUNNER_TYPE_TEXT))


def _bulk_agent(*, settings: JevAgentSettings | None = None, presets: tuple[JevPreflightPreset, ...] = (JevPreflightPreset.BULK_WORK,)) -> JevAgent:
    # Builds a JevAgent with fixed decision credentials and opt-in settings for runtime integration tests.
    return JevAgent(settings or _settings(), JevRuntimeSettings(decision=DecisionModelConfig.vidbyte_managed(), preflight=presets))


class JevBulkSettingsTests(unittest.TestCase):
    """Pins public defaults, validation, and API exports."""

    def test_defaults_and_minimums_are_named_and_stable(self) -> None:
        # [Edge Case] Default bounds are finite and every documented minimum remains constructible.
        defaults = JevBulkSettings()
        self.assertEqual((defaults.max_parallel_agents, defaults.max_items, defaults.planner_max_iterations, defaults.planner_max_tokens), (JEV_BULK_DEFAULT_MAX_PARALLEL_AGENTS, JEV_BULK_DEFAULT_MAX_ITEMS, JEV_BULK_DEFAULT_PLANNER_MAX_ITERATIONS, JEV_BULK_DEFAULT_PLANNER_MAX_TOKENS))
        minimums = JevBulkSettings(max_parallel_agents=JEV_BULK_MIN_PARALLEL_AGENTS, max_items=JEV_BULK_MIN_ITEMS, planner_max_iterations=JEV_BULK_MIN_PLANNER_MAX_ITERATIONS, planner_max_tokens=JEV_BULK_MIN_PLANNER_MAX_TOKENS)
        self.assertEqual(minimums.max_items, JEV_BULK_MIN_ITEMS)

    def test_rejects_invalid_values_for_every_resource_limit(self) -> None:
        # [Hidden Failure] bool, non-integers, absent values, and values below each field's floor must fail at construction.
        for field_name in ("max_parallel_agents", "max_items", "planner_max_iterations", "planner_max_tokens"):
            for value in (True, 1.5, "4", None, 0, -1):
                with self.subTest(field=field_name, value=value), self.assertRaises(ConfigurationError):
                    JevBulkSettings(**{field_name: value})

    def test_rejects_wrong_nested_settings_type_and_exports_public_api(self) -> None:
        # [Hidden Assumption] The nested API accepts only JevBulkSettings and root exports match the public types.
        from vidbyte import JevBulkItemError as RootItemError
        from vidbyte import JevBulkPlanningError as RootPlanningError
        from vidbyte import JevBulkSettings as RootSettings
        self.assertIs(RootSettings, JevBulkSettings)
        self.assertIs(RootItemError, JevBulkItemError)
        self.assertIs(RootPlanningError, JevBulkPlanningError)
        with self.assertRaises(ConfigurationError):
            _settings(bulk_work=object())


class JevBulkQuestionTests(unittest.TestCase):
    """Verifies the three fixed questions remain separate, registered, and complete."""

    def test_preset_registers_three_ordered_positive_questions(self) -> None:
        # [Edge Case] The three independent judgments have unique keys and are returned in preset order.
        keys = tuple(question.key for question in BULK_WORK_QUESTIONS)
        self.assertEqual(keys, tuple(JevPreflightQuestionKey(value) for value in _BULK_KEYS))
        self.assertEqual(len(set(keys)), 3)
        self.assertEqual(JevPresets.definition(JevPreflightPreset.BULK_WORK).threshold, JEV_BULK_WORK_THRESHOLD)
        self.assertEqual(JevPresets.definition(JevPreflightPreset.BULK_WORK).veto, JEV_BULK_WORK_VETO_THRESHOLD)
        questions = JevPreflightRegistry.questions(JevPreflightPreset.BULK_WORK)
        self.assertEqual(tuple(question.name for question in questions), _BULK_KEYS)
        self.assertTrue(all(question.question_type is JevQuestionType.NOUL for question in questions))

    def test_each_question_judges_only_its_own_condition(self) -> None:
        # [Silent Failure] Similar wording cannot collapse target count, shared operation, and independence into one answer.
        rendered = tuple(question.instructions.question for question in BULK_WORK_QUESTIONS)
        self.assertIn("multiple distinct work targets", rendered[0])
        self.assertIn("same operation", rendered[1])
        self.assertIn("independently executable", rendered[2])
        self.assertIn("other questions", BULK_WORK_QUESTIONS[0].when_true.not_for)
        self.assertIn("independent-execution question", BULK_WORK_QUESTIONS[1].instructions.rules[0])
        self.assertIn("missing or vague independence evidence", BULK_WORK_QUESTIONS[2].when_false.what)

    def test_question_fields_are_single_literals_and_share_house_rules(self) -> None:
        # [Hidden Assumption] Definitions and rules each remain one standalone literal with the house judgment rules at the end.
        source_path = _ROOT / "vidbyte/lib/jev/preflight/bulk_work.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for question in BULK_WORK_QUESTIONS:
            cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == type(question).__name__)
            assignment = next(node for node in cls.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "instructions")
            brief = next(keyword.value.body for keyword in assignment.value.keywords if keyword.arg == "default_factory")
            for field_name in ("definitions", "rules"):
                node = next(keyword.value for keyword in brief.keywords if keyword.arg == field_name)
                self.assertIsInstance(node, ast.Tuple)
                self.assertEqual(len(node.elts), 1)
                self.assertIsInstance(node.elts[0], ast.Constant)
                self.assertIsInstance(node.elts[0].value, str)
            rules = " ".join(question.instructions.rules[0].split())
            self.assertTrue(rules.endswith(" ".join(IGNORE_CLAIMS.split())))
            self.assertIn(" ".join(JUDGE_MEANING.split()), rules)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_each_full_fixed_question_exceeds_two_thousand_cl100k_tokens(self) -> None:
        # [Edge Case] Count the complete rendered judgment, including criteria and examples, against the house token floor.
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
        for question in BULK_WORK_QUESTIONS:
            text = "\n".join((*question.instructions.definitions, *question.instructions.rules, question.when_true.what, question.when_true.not_for, *question.when_true.easy, *question.when_true.boundary, question.when_false.what, question.when_false.not_for, *question.when_false.easy, *question.when_false.boundary, question.gap))
            with self.subTest(question=question.key.value):
                self.assertGreaterEqual(len(encoder.encode(text)), 2_000)


class JevBulkGateTests(unittest.IsolatedAsyncioTestCase):
    """Checks clear positives, vetoes, missing answers, and same-gate reset behavior."""

    def _gate(self) -> tuple[JevPreflightGate, JevResponse]:
        # Creates one configured gate whose flag can be observed over repeated passes.
        response = JevResponse()
        runtime = JevRuntimeSettings(decision=DecisionModelConfig.vidbyte_managed(), preflight=(JevPreflightPreset.BULK_WORK,))
        return JevPreflightGate(_settings(), runtime, response), response

    async def test_clear_positives_and_exact_per_answer_boundary_enable_bulk(self) -> None:
        # [Edge Case] Every fixed question meets both the score and per-answer veto at the configured boundary.
        gate, response = self._gate()
        script = ScriptedDecisionRunner({name: JEV_BULK_WORK_THRESHOLD for name in _BULK_KEYS})
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(script)):
            self.assertTrue(await gate.pass_(_REQUEST))
        self.assertTrue(gate.bulk_work_requested)
        self.assertEqual(tuple(response.state.results[JevPreflightPreset.BULK_WORK].answers), tuple(JevPreflightQuestionKey(value) for value in _BULK_KEYS))

    async def test_one_clear_negative_vetoes_a_high_mean(self) -> None:
        # [Hidden Failure] Two nearly certain yes answers cannot hide one answer below the veto cutoff.
        gate, _ = self._gate()
        script = ScriptedDecisionRunner({_BULK_KEYS[0]: 0.99, _BULK_KEYS[1]: 0.99, _BULK_KEYS[2]: 0.74})
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(script)):
            self.assertTrue(await gate.pass_(_REQUEST))
        self.assertFalse(gate.bulk_work_requested)

    async def test_missing_answer_fails_open_without_enabling_bulk(self) -> None:
        # [Silent Failure] An unavailable question leaves ordinary execution open while fan-out stays disabled.
        gate, response = self._gate()
        script = ScriptedDecisionRunner(omit=_BULK_KEYS[2])
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(script)):
            self.assertTrue(await gate.pass_(_REQUEST))
        self.assertFalse(gate.bulk_work_requested)
        self.assertFalse(response.state.results[JevPreflightPreset.BULK_WORK].available)

    async def test_gate_resets_bulk_flag_between_passes(self) -> None:
        # [Hidden Assumption] A prior positive pass cannot survive an unavailable answer on the same gate instance.
        gate, _ = self._gate()
        positive = ScriptedDecisionRunner()
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(positive)):
            self.assertTrue(await gate.pass_(_REQUEST))
        self.assertTrue(gate.bulk_work_requested)
        missing = ScriptedDecisionRunner(omit=_BULK_KEYS[1])
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(missing)):
            self.assertTrue(await gate.pass_(_REQUEST))
        self.assertFalse(gate.bulk_work_requested)


class JevBulkPlannerTests(unittest.IsolatedAsyncioTestCase):
    """Exercises complete-plan validation and the actual BaseAgent prompt path."""

    async def test_accepts_two_items_and_exact_item_limit(self) -> None:
        # [Edge Case] Both the two-item floor and an exact custom maximum are accepted without dropping items.
        runner = ScriptedModelRunner(plan=_plan_payload(3))
        settings = _settings(bulk_work=JevBulkSettings(max_items=3, max_parallel_agents=2))
        coordinator = JevBulkWork(settings)
        with _patch_model_runners(runner):
            result = await coordinator.plan_and_run(_REQUEST, BaseAgentContext(), ())
        self.assertTrue(result.plan_valid)
        self.assertEqual(tuple(item.identifier for item in result.items), ("item_0", "item_1", "item_2"))
        self.assertEqual(result.planner_usage.model_call_count, 1)

    async def test_rejects_oversized_plan_whole_without_workers(self) -> None:
        # [Silent Failure] The coordinator rejects rather than truncating a plan above max_items.
        runner = ScriptedModelRunner(plan=_plan_payload(3))
        coordinator = JevBulkWork(_settings(bulk_work=JevBulkSettings(max_items=2)))
        with _patch_model_runners(runner):
            result = await coordinator.plan_and_run(_REQUEST, BaseAgentContext(), ())
        self.assertFalse(result.plan_valid)
        self.assertEqual(result.items, ())
        self.assertIs(result.planning_error, JevBulkPlanningError.TOO_MANY_ITEMS)
        self.assertEqual(result.planner_usage.model_call_count, 1)
        self.assertFalse(any("isolated worker handling one item" in call["system"] for call in runner.calls))

    async def test_rejects_malformed_blank_duplicate_and_wrong_count_plans(self) -> None:
        # [Hidden Failure] Every structural defect is rejected before any item worker is created.
        coordinator = JevBulkWork(_settings(bulk_work=JevBulkSettings(max_items=3)))
        candidates: tuple[tuple[object, JevBulkPlanningError], ...] = (
            (None, JevBulkPlanningError.MALFORMED_OUTPUT),
            ({"items": []}, JevBulkPlanningError.TOO_FEW_ITEMS),
            ({"items": [{"identifier": "only", "title": "Only", "prompt": "Run."}]}, JevBulkPlanningError.TOO_FEW_ITEMS),
            ({"items": [{"identifier": "same", "title": "A", "prompt": "Run."}, {"identifier": "same", "title": "B", "prompt": "Run."}]}, JevBulkPlanningError.DUPLICATE_IDENTIFIERS),
            ({"items": [{"identifier": "a", "title": " ", "prompt": "Run."}, {"identifier": "b", "title": "B", "prompt": "Run."}]}, JevBulkPlanningError.MALFORMED_OUTPUT),
            ({"items": [{"identifier": "a", "title": "A", "prompt": " "}, {"identifier": "b", "title": "B", "prompt": "Run."}]}, JevBulkPlanningError.MALFORMED_OUTPUT),
        )
        for value, expected in candidates:
            with self.subTest(value=value):
                assessment = coordinator._assess_plan(value)
                self.assertIsNone(assessment.plan)
                self.assertIs(assessment.failure, expected)

    async def test_real_context_builder_uses_planner_prompt_and_scoped_worker_prompt(self) -> None:
        # [Hidden Failure] BaseAgent would prefer caller.system_prompt; assert the actual provider context uses the planner asset and an isolated worker scope.
        runner = ScriptedModelRunner()
        coordinator = JevBulkWork(_settings())
        context = BaseAgentContext(
            system_prompt="Caller selected-skill prompt.",
            history=("STALE PARENT HISTORY",),
            artifacts=(ContextArtifact("external source", "preserve this evidence"),),
            responses=(ContextResponse("STALE PARENT RESPONSE"),),
            tool_calls=(ContextToolCall("STALE", output="STALE PARENT TOOL"),),
        )
        original = (context.system_prompt, context.history, context.artifacts, context.responses, context.tool_calls)
        with _patch_model_runners(runner):
            await coordinator.plan_and_run(_REQUEST, context, ())
        planner_call = next(call for call in runner.calls if "You are JevBulkWorkPlanner" in call["system"])
        worker_calls = [call for call in runner.calls if "You are an isolated worker handling one item" in call["system"]]
        self.assertEqual(planner_call["prompt"], _REQUEST)
        self.assertIn(Prompts().get(Prompt.JEV_BULK_WORK_SYSTEM_PROMPT), planner_call["system"])
        self.assertNotIn("Caller selected-skill prompt", planner_call["system"])
        self.assertIn("external source", planner_call["system"])
        self.assertNotIn("STALE PARENT", planner_call["system"])
        self.assertEqual(len(worker_calls), 2)
        for worker_call in worker_calls:
            task = json.loads(worker_call["prompt"])
            self.assertEqual(task["original_user_request"], _REQUEST)
            self.assertIn("Caller selected-skill prompt.", worker_call["system"])
            self.assertIn(Prompts().get(Prompt.JEV_BULK_WORK_WORKER_SYSTEM_PROMPT), worker_call["system"])
            self.assertIn("external source", worker_call["system"])
            self.assertNotIn("STALE PARENT", worker_call["system"])
        self.assertEqual((context.system_prompt, context.history, context.artifacts, context.responses, context.tool_calls), original)


class JevBulkExecutionTests(unittest.IsolatedAsyncioTestCase):
    """Checks bounded scheduling, ordering, failures, cancellation, and fork-compatible tool binding."""

    async def test_queue_bounds_concurrency_and_preserves_plan_order(self) -> None:
        # [Edge Case] More items than workers finish out of order but are returned in original plan order.
        runner = ScriptedModelRunner(plan=_plan_payload(4), delays={"item_0": 0.06, "item_1": 0.01, "item_2": 0.02, "item_3": 0.0})
        coordinator = JevBulkWork(_settings(bulk_work=JevBulkSettings(max_parallel_agents=2, max_items=4)))
        with _patch_model_runners(runner):
            result = await coordinator.plan_and_run(_REQUEST, BaseAgentContext(), ())
        self.assertEqual(runner.max_active_workers, 2)
        self.assertNotEqual(runner.completed_items, [f"item_{index}" for index in range(4)])
        self.assertEqual(tuple(item.identifier for item in result.items), tuple(f"item_{index}" for index in range(4)))

    async def test_worker_exception_is_safe_failure_and_does_not_cancel_siblings(self) -> None:
        # [Hidden Assumption] One ordinary exception remains a typed item failure while all other queued work completes.
        runner = ScriptedModelRunner(plan=_plan_payload(4), failures=("item_1",), delays={"item_0": 0.02, "item_2": 0.01})
        coordinator = JevBulkWork(_settings(bulk_work=JevBulkSettings(max_parallel_agents=2, max_items=4)))
        with _patch_model_runners(runner):
            result = await coordinator.plan_and_run(_REQUEST, BaseAgentContext(), ())
        self.assertEqual(result.items[1].error, JevBulkItemError.WORKER_FAILURE)
        self.assertIsNone(result.items[1].output)
        self.assertIsNotNone(result.items[1].usage)
        self.assertEqual(set(runner.completed_items), {"item_0", "item_2", "item_3"})
        self.assertNotIn("secret worker detail", repr(result))
        artifact = coordinator.result_artifact(result)
        self.assertIn('"status": "failed"', artifact.content)
        self.assertNotIn("secret worker detail", artifact.content)

    async def test_cancellation_cleans_workers_and_propagates(self) -> None:
        # [Hidden Failure] Cancelling active work cancels and gathers all fixed worker tasks without converting cancellation to a result.
        runner = ScriptedModelRunner(plan=_plan_payload(5), block_workers=True)
        coordinator = JevBulkWork(_settings(bulk_work=JevBulkSettings(max_parallel_agents=2, max_items=5)))
        with _patch_model_runners(runner):
            task = asyncio.create_task(coordinator.plan_and_run(_REQUEST, BaseAgentContext(), ()))
            await asyncio.wait_for(runner.worker_started.wait(), timeout=2.0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(runner.cancelled_workers, 2)
        self.assertEqual(runner.active_workers, 0)

    async def test_worker_tools_clone_agent_context_and_keep_selected_catalog_exact(self) -> None:
        # [Silent Failure] The selected AgentTool clone binds to its worker while the parent's wrapper remains bound to the owner.
        @tool
        def selected_lookup(query: str) -> str:
            """Look up one selected record."""
            return query

        @tool
        def discarded_write(value: str) -> str:
            """Write one record, but this tool is intentionally discarded."""
            return value

        delegate = BaseAgent(name="delegate", system_prompt="Delegate prompt.", provider="openai", model_name="gpt-4.1-mini", agent_metadata=AgentMetadata(name="delegate", description="Delegate work.", use_cases="Testing delegation."))
        original_agent_tool = AgentTool(delegate)
        settings = _settings(tools=(original_agent_tool, selected_lookup, discarded_write))
        owner = JevAgent(settings)
        owner._active_prompt = "owner active prompt"
        original_getter = original_agent_tool._context_getter
        self.assertIsNotNone(original_getter)
        item = JevBulkPlanItem(identifier="item_0", title="Item 0", prompt="Look it up.")
        worker = owner.bulk_work._build_worker(item, (original_agent_tool, selected_lookup))
        self.assertEqual(worker.tools.names(), (original_agent_tool.name, selected_lookup.name))
        self.assertIs(worker.tools[1], selected_lookup)
        self.assertIsNot(worker.tools[0], original_agent_tool)
        self.assertIsNotNone(worker.tools[0]._context_getter)
        worker._active_prompt = "worker active prompt"
        self.assertEqual(original_agent_tool._context_getter()[0], "owner active prompt")
        self.assertEqual(worker.tools[0]._context_getter()[0], "worker active prompt")
        self.assertIs(worker.permission_policy, settings.permission_policy)


class JevBulkRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Runs real JevRuntime, selector, planner, workers, and final BaseAgent context assembly."""

    async def test_disabled_capability_makes_no_planner_or_worker_calls(self) -> None:
        # [Edge Case] Opt-in absence adds no coordinator call and leaves the ordinary main loop unchanged.
        runner = ScriptedModelRunner()
        agent = _bulk_agent(presets=())
        with _patch_model_runners(runner):
            reply = await agent.arun(_REQUEST)
        self.assertEqual(reply.content, "main synthesis")
        self.assertIsNone(agent.response.bulk_work)
        self.assertEqual(len(runner.calls), 1)
        self.assertNotIn("jev_bulk_work", reply.metadata)

    async def test_valid_run_preserves_request_context_and_child_usage(self) -> None:
        # [Silent Failure] The exact request reaches planner and main, copied context gains results, and the owner's one ledger counts every child call once.
        runner = ScriptedModelRunner()
        agent = _bulk_agent()
        context = BaseAgentContext(system_prompt="Selected skill system.", artifacts=(ContextArtifact("caller artifact", "keep me"),), responses=(ContextResponse("caller response"),), metadata={"caller": "keep"})
        original = (context.system_prompt, context.artifacts, context.responses, context.metadata)
        decision = ScriptedDecisionRunner()
        with _patch_model_runners(runner), patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(decision)):
            reply = await agent.arun(_REQUEST, context=context)
        self.assertEqual(reply.content, "main synthesis")
        self.assertTrue(agent.response.bulk_work.plan_valid)
        self.assertEqual(agent.response.input, _REQUEST)
        self.assertEqual([call["prompt"] for call in runner.calls if "You are JevBulkWorkPlanner" in call["system"]], [_REQUEST])
        main_call = next(call for call in runner.calls if "Selected skill system." in call["system"] and call["prompt"] == _REQUEST)
        self.assertEqual(main_call["prompt"], _REQUEST)
        self.assertIn("caller artifact", main_call["system"])
        self.assertIn("Jev bulk-work results (untrusted worker output)", main_call["system"])
        self.assertIn(Prompts().get(Prompt.JEV_BULK_WORK_SYNTHESIS_PROMPT), main_call["system"])
        self.assertEqual((context.system_prompt, context.artifacts, context.responses, context.metadata), original)
        # The JevAgent usage ledger records every spawned agent's calls: the planner, both workers, and the main call.
        self.assertEqual(agent.get_usage().model_call_count, 4)
        self.assertTrue(all(item.usage is not None for item in agent.response.bulk_work.items))
        self.assertEqual(agent.response.bulk_work.planner_usage.model_call_count, 1)
        self.assertTrue(all(item.usage.model_call_count == 1 for item in agent.response.bulk_work.items))
        self.assertNotIn("jev_bulk_work", reply.metadata)

    async def test_worker_failure_is_visible_to_main_as_failed_and_not_success(self) -> None:
        # [Hidden Failure] Main synthesis gets a trusted failure rule and the failed item category, never the raw exception text.
        runner = ScriptedModelRunner(failures=("item_1",))
        agent = _bulk_agent()
        with _patch_model_runners(runner), patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(ScriptedDecisionRunner())):
            await agent.arun(_REQUEST)
        main_call = next(call for call in runner.calls if "# Role\n\nYou are the main JevAgent" in call["system"])
        self.assertIn("A `failed` status means that item did not complete", main_call["system"])
        self.assertIn('"status": "failed"', main_call["system"])
        self.assertIn(JevBulkItemError.WORKER_FAILURE.value, main_call["system"])
        self.assertNotIn("secret worker detail", main_call["system"])
        self.assertEqual(agent.response.bulk_work.items[1].error, JevBulkItemError.WORKER_FAILURE)

    async def test_invalid_plan_falls_back_serially_with_original_request(self) -> None:
        # [Silent Failure] An oversized plan creates no workers or result artifact and ordinary synthesis receives exact input.
        runner = ScriptedModelRunner(plan=_plan_payload(3))
        agent = _bulk_agent(settings=_settings(bulk_work=JevBulkSettings(max_items=2)))
        with _patch_model_runners(runner), patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(ScriptedDecisionRunner())):
            await agent.arun(_REQUEST)
        self.assertFalse(agent.response.bulk_work.plan_valid)
        self.assertIs(agent.response.bulk_work.planning_error, JevBulkPlanningError.TOO_MANY_ITEMS)
        self.assertEqual(agent.response.bulk_work.items, ())
        self.assertFalse(any("You are an isolated worker" in call["system"] for call in runner.calls))
        main_call = next(call for call in runner.calls if "Owner instruction." in call["system"])
        self.assertEqual(main_call["prompt"], _REQUEST)
        self.assertNotIn("Jev bulk-work results", main_call["system"])
        self.assertNotIn(Prompts().get(Prompt.JEV_BULK_WORK_SYNTHESIS_PROMPT), main_call["system"])

    async def test_selector_runs_before_workers_and_runtime_restores_owner_tools(self) -> None:
        # [Hidden Assumption] Worker tools equal the selector result and the owner's original catalogs return after the run.
        @tool
        def keep_search(query: str) -> str:
            """Search selected records."""
            return query

        @tool
        def discard_calendar(day: str) -> str:
            """Read an unrelated calendar."""
            return day

        runner = ScriptedModelRunner()
        agent = _bulk_agent(settings=_settings(tools=(keep_search, discard_calendar)), presets=(JevPreflightPreset.BULK_WORK, JevPreflightPreset.TOOL_SELECTOR))
        original_names = agent.tools.names()
        bulk_answers = ScriptedDecisionRunner()
        selector_answers = ScriptedDecisionRunner({"tool_selector.0": 0.9, "tool_selector.1": 0.0})
        with (
            _patch_model_runners(runner),
            patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(bulk_answers)),
            patch("vidbyte.agents.jev.preflight.DecisionModelHelper", new=_decision_helper(selector_answers)),
        ):
            await agent.arun(_REQUEST)
        workers = [call for call in runner.calls if "You are an isolated worker" in call["system"]]
        self.assertEqual(len(workers), 2)
        for worker_call in workers:
            names = {row.get("function", {}).get("name") for row in worker_call.get("tools", ())}
            self.assertIn("keep_search", names)
            self.assertNotIn("discard_calendar", names)
        self.assertEqual(selector_answers.requests[0].questions[0].name, "tool_selector.0")
        self.assertEqual(agent.tools.names(), original_names)

    async def test_specialist_precedes_bulk_planning(self) -> None:
        # [Hidden Assumption] A chosen specialist receives the request before the main coordinator can plan workers.
        runner = ScriptedModelRunner()
        specialist_runner = ScriptedModelRunner()
        specialist_agent = bind_test_runner(BaseAgent(name="specialist", system_prompt="Specialist prompt.", provider="openai", model_name="gpt-4.1-mini"), specialist_runner)
        specialist = JevSpecialist("review", "Reviews these documents.", specialist_agent)
        agent = _bulk_agent(settings=_settings(agents=(specialist,)))
        decision = ScriptedDecisionRunner(choice="review")
        with (
            _patch_model_runners(runner),
            patch.object(BaseAgent, "_runner_for_model", new=lambda current: (specialist_runner if current is specialist_agent else runner, RUNNER_TYPE_TEXT)),
            patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(decision)),
        ):
            reply = await agent.arun(_REQUEST)
        self.assertEqual(reply.content, "main synthesis")
        self.assertEqual(agent.response.specialist, "review")
        self.assertIsNone(agent.response.bulk_work)
        self.assertEqual(len(specialist_runner.calls), 1)
        self.assertFalse(any("You are JevBulkWorkPlanner" in call["system"] for call in runner.calls))

    async def test_missing_gate_answer_keeps_serial_path_and_repeated_run_clears_result(self) -> None:
        # [Hidden Assumption] Fail-open gate behavior and same-agent reruns cannot retain an earlier bulk outcome.
        runner = ScriptedModelRunner()
        agent = _bulk_agent()
        first = ScriptedDecisionRunner()
        with _patch_model_runners(runner), patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(first)):
            await agent.arun(_REQUEST)
        self.assertIsNotNone(agent.response.bulk_work)
        second = ScriptedDecisionRunner(omit=_BULK_KEYS[0])
        call_count = len(runner.calls)
        with _patch_model_runners(runner), patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(second)):
            await agent.arun(_REQUEST)
        self.assertIsNone(agent.response.bulk_work)
        self.assertFalse(any("You are an isolated worker" in call["system"] for call in runner.calls[call_count:]))

    async def test_explicit_system_option_is_preserved_and_augmented_for_main(self) -> None:
        # [Edge Case] A per-run system override remains the base of the trusted synthesis system prompt.
        runner = ScriptedModelRunner()
        agent = _bulk_agent()
        with _patch_model_runners(runner), patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(ScriptedDecisionRunner())):
            await agent.arun(_REQUEST, system="Per-run system override.")
        main_call = next(call for call in runner.calls if "main JevAgent preparing" in call["system"])
        self.assertIn("Per-run system override.", main_call["system"])
        self.assertIn(Prompts().get(Prompt.JEV_BULK_WORK_SYNTHESIS_PROMPT), main_call["system"])

    def test_response_writer_resets_bulk_record_and_result_never_uses_metadata(self) -> None:
        # [Silent Failure] JevResponse alone writes bulk state, and start replaces rather than carries an old result.
        response = JevResponse()
        valid = JevBulkWorkResult(plan_valid=True, items=(
            JevBulkItemResult("a", "A", "ok", None),
            JevBulkItemResult("b", "B", "ok", None),
        ), planner_usage=None, planning_error=None)
        response.bulk_work(valid)
        old_state = response.state
        response.start(_REQUEST)
        self.assertIsNot(response.state, old_state)
        self.assertIsNone(response.state.bulk_work)


if __name__ == "__main__":
    unittest.main()
