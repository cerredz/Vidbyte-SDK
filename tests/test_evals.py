"""Context Protocol Header

Description:
    Exposes full unit and integration test coverage for the Vidbyte SDK evaluation module.
Purpose:
    Validates correctness, edge cases, failure states, state isolation, and registry deltas
    under the pytest execution environment.
Architecture:
    - MockRunner: Simple dummy executor acting as mock LLM judge.
    - MockAgent: Custom BaseAgent child tracking clone fork invocations.
    - EvalTests: IsolatedAsyncioTestCase collection mapping all grader, suite, runner, and comparison behaviors.
Relations:
    Validates code in vidbyte/evals/ and runs under the scripts/test-sdk-evals.py test harness.
"""

from __future__ import annotations

import os
import tempfile
import json
import unittest
from datetime import datetime
from typing import Any
from vidbyte.agents.types import AgentInput
from vidbyte.agents.base import BaseAgent
from vidbyte.evals import (
    ContainsGrader,
    EvalCase,
    EvalClient,
    ExactMatchGrader,
    JSONSchemaGrader,
    LLMJudgeGrader,
    RegexMatchGrader,
    RubricGrader,
    EvalSuite,
    EvalRunner,
    EvalRegistry,
    GraderResult,
    EvalResult,
    EvalSuiteResult,
)


class MockRunner:
    """Mock runner that returns pre-configured strings to test LLM judge and rubric grading."""

    def __init__(self, response_text: str) -> None:
        # Instantiates the mock runner with a fixed response text payload.
        self.response_text = response_text
        self.last_prompt = ""

    def run(self, prompt: str, **kwargs: Any) -> str:
        # Synchronously stores the prompt and returns the fixed response payload.
        self.last_prompt = prompt
        return self.response_text


class MockAgent(BaseAgent):
    """Mock agent designed to count fork calls and verify isolated test execution."""

    def __init__(self) -> None:
        # Standard initializer creating a dummy worker agent.
        super().__init__(
            name="mock_agent",
            system_prompt="Test.",
            runner=object()
        )
        self.fork_count = 0
        self.last_name = ""
        self.last_options: dict[str, Any] = {}

    def fork(self, **kwargs: Any) -> MockAgent:
        # Custom fork that counts clone invocations and returns self for simplified testing.
        self.fork_count += 1
        self.last_name = kwargs.get("name", "")
        return self

    async def arun(self, message: str | AgentInput, **options: Any) -> Any:
        # Simulates a replies payload for the agent run.
        self.last_options = dict(options)
        prompt = message.prompt if isinstance(message, AgentInput) else message

        class Reply:
            content = f"processed:{prompt}"
            metadata = {"mock": True}
        return Reply()


class EvalTests(unittest.IsolatedAsyncioTestCase):
    """Main unit and integration test suite validating all evaluation components."""

    async def test_exact_match_grader(self) -> None:
        # Tests ExactMatchGrader matching logic, case options, and stripping parameters.
        grader = ExactMatchGrader(strip=True, case_sensitive=False)
        case = EvalCase(prompt="test", expected=" Hello ")
        
        # [Edge Case] Exact match with formatting delta
        res = await grader.agrade(case, "hello")
        self.assertTrue(res.passed)
        self.assertEqual(res.score, 1.0)

        # [Silent Failure] Test false match on casing difference when case_sensitive=True
        grader_sensitive = ExactMatchGrader(strip=True, case_sensitive=True)
        res_sensitive = await grader_sensitive.agrade(case, "hello")
        self.assertFalse(res_sensitive.passed)
        self.assertEqual(res_sensitive.score, 0.0)

        # [Edge Case] Empty/whitespace inputs
        res_empty = await grader.agrade(EvalCase(prompt="t", expected=""), "   ")
        self.assertTrue(res_empty.passed)

    async def test_contains_grader(self) -> None:
        # Tests ContainsGrader keyword verification and case-sensitivity toggles.
        grader = ContainsGrader(case_sensitive=False)
        case = EvalCase(prompt="t", expected="apple")

        # Basic inclusion
        res = await grader.agrade(case, "I ate a green APPLE today")
        self.assertTrue(res.passed)
        self.assertEqual(res.score, 1.0)

        # Basic exclusion
        res_fail = await grader.agrade(case, "I ate a green banana today")
        self.assertFalse(res_fail.passed)

        # [Edge Case] Empty expected substring behaves properly
        res_empty = await grader.agrade(EvalCase(prompt="t", expected=""), "banana")
        self.assertTrue(res_empty.passed)

    async def test_regex_match_grader(self) -> None:
        # Tests RegexMatchGrader pattern scanning and error handling.
        grader = RegexMatchGrader(pattern=r"\d{3}-\d{2}")
        case = EvalCase(prompt="t")

        # Correct pattern match
        res = await grader.agrade(case, "My id is 123-45!")
        self.assertTrue(res.passed)

        # Incorrect pattern match
        res_fail = await grader.agrade(case, "My id is 12-345")
        self.assertFalse(res_fail.passed)

        # [Edge Case] Invalid regex compilation handling
        with self.assertRaises(Exception):
            RegexMatchGrader(pattern="[invalid")

    async def test_json_schema_grader(self) -> None:
        # Tests JSONSchemaGrader structural data validation across multiple datatypes.
        schema = {
            "type": "object",
            "required": ["name", "scores"],
            "properties": {
                "name": {"type": "string"},
                "scores": {
                    "type": "array",
                    "items": {"type": "integer"}
                },
                "active": {"type": "boolean"}
            }
        }
        grader = JSONSchemaGrader(schema)
        case = EvalCase(prompt="t")

        # Correct JSON conforming to schema
        valid_json = '{"name": "Alice", "scores": [90, 80], "active": true}'
        res = await grader.agrade(case, valid_json)
        self.assertTrue(res.passed)

        # Missing required keys
        missing_required = '{"name": "Alice"}'
        res_fail = await grader.agrade(case, missing_required)
        self.assertFalse(res_fail.passed)

        # Malformed type in list
        bad_type = '{"name": "Alice", "scores": [90, "eighty"]}'
        res_bad = await grader.agrade(case, bad_type)
        self.assertFalse(res_bad.passed)

        # [Hidden Failure] Test malformed raw JSON strings
        res_malformed = await grader.agrade(case, "not a json string")
        self.assertFalse(res_malformed.passed)
        self.assertEqual(res_malformed.score, 0.0)

    async def test_llm_judge_grader(self) -> None:
        # Tests LLMJudgeGrader dynamic JSON parsing, grader templates, and failure states.
        runner = MockRunner('{"score": 0.8, "passed": true, "reason": "Accurate details."}')
        grader = LLMJudgeGrader(judge_runner=runner)
        case = EvalCase(prompt="Write about space.", expected="Astronomy rules.")

        res = await grader.agrade(case, "Space is huge.")
        self.assertTrue(res.passed)
        self.assertEqual(res.score, 0.8)
        self.assertIn("Task Prompt:", runner.last_prompt)

        # [Hidden Failure] Judge runner returns invalid/unparsable JSON
        bad_runner = MockRunner("bad output")
        bad_grader = LLMJudgeGrader(judge_runner=bad_runner)
        res_bad = await bad_grader.agrade(case, "Space is huge.")
        self.assertFalse(res_bad.passed)
        self.assertEqual(res_bad.score, 0.0)

    async def test_rubric_grader(self) -> None:
        # Tests RubricGrader weighted dimensional score computation and pass metrics.
        judge_output = {
            "scores": {
                "accuracy": 0.9,
                "conciseness": 0.5
            },
            "reasons": {
                "accuracy": "Correct.",
                "conciseness": "Too verbose."
            }
        }
        runner = MockRunner(json.dumps(judge_output))
        
        # [Silent Failure] Scored weighted average math check: accuracy=0.9 (weight 0.6), conciseness=0.5 (weight 0.4)
        # Expected score: (0.9*0.6) + (0.5*0.4) = 0.54 + 0.20 = 0.74. Passed threshold 0.7 = True.
        rubric = {"accuracy": 0.6, "conciseness": 0.4}
        grader = RubricGrader(judge_runner=runner, rubric=rubric, threshold=0.7)
        case = EvalCase(prompt="t")

        res = await grader.agrade(case, "Verbose correct answer.")
        self.assertTrue(res.passed)
        self.assertAlmostEqual(res.score, 0.74)

        # Verify failure when average score drops below threshold
        grader_strict = RubricGrader(judge_runner=runner, rubric=rubric, threshold=0.8)
        res_strict = await grader_strict.agrade(case, "Verbose correct answer.")
        self.assertFalse(res_strict.passed)

    async def test_eval_suite(self) -> None:
        # Tests EvalSuite loading, tagging, and tag filtering features.
        case_a = EvalCase(prompt="A", tags=("math",))
        case_b = EvalCase(prompt="B", tags=("coding",))
        suite = EvalSuite("my_suite", [case_a, case_b])

        self.assertEqual(len(suite), 2)
        filtered = suite.filter(["coding"])
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.cases[0].prompt, "B")

        # [Edge Case] Filtering with empty tags sequence returns empty suite
        empty_filter = suite.filter([])
        self.assertEqual(len(empty_filter), 0)

    async def test_eval_runner_with_agent_fork(self) -> None:
        # Tests EvalRunner executing suites and ensures state isolation using clone forks.
        agent = MockAgent()
        suite = EvalSuite("suite", [EvalCase(prompt="q1"), EvalCase(prompt="q2")])
        runner = EvalRunner(agent, default_grader=ExactMatchGrader(), concurrency=1)

        result = await runner.arun(suite)
        self.assertEqual(len(result.results), 2)
        
        # Verify isolations
        self.assertEqual(agent.fork_count, 2)
        self.assertEqual(agent.last_name, "mock_agent_eval")
        self.assertEqual(result.results[0].actual, "processed:q1")
        self.assertEqual(agent.last_options["trace_metadata"]["eval_suite"], "suite")
        self.assertEqual(agent.last_options["trace_metadata"]["eval_case_index"], 1)

    async def test_eval_runner_graceful_exception_handling(self) -> None:
        # Tests EvalRunner resilient case execution when targets raise errors.
        class CrashingRunner:
            def run(self, prompt: str) -> str:
                raise RuntimeError("Runner crashed!")

        suite = EvalSuite("suite", [EvalCase(prompt="q1")])
        runner = EvalRunner(CrashingRunner(), default_grader=ExactMatchGrader())
        result = await runner.arun(suite)

        self.assertEqual(len(result.results), 1)
        res = result.results[0]
        self.assertFalse(res.grader_result.passed)
        self.assertIsNotNone(res.error)
        self.assertIn("Runner crashed!", res.error)

    async def test_eval_registry_and_comparison(self) -> None:
        # Tests EvalRegistry persistence loop and ComparisonReport metric generation.
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_evals.db")
        
        try:
            registry = EvalRegistry(db_path)
            case_1 = EvalCase(prompt="1+1", expected="2")
            case_2 = EvalCase(prompt="2+2", expected="4")
            
            # Record run 1 for model_a (pass rate 0.5)
            res_1 = EvalResult(case_1, "2", GraderResult(1.0, True), 10.0)
            res_2 = EvalResult(case_2, "5", GraderResult(0.0, False), 12.0)
            run_a = EvalSuiteResult("math_suite", "model_a", (res_1, res_2), datetime.utcnow())
            registry.record(run_a)

            # Record run 2 for model_b (pass rate 1.0)
            res_b1 = EvalResult(case_1, "2", GraderResult(1.0, True), 8.0)
            res_b2 = EvalResult(case_2, "4", GraderResult(1.0, True), 9.0)
            run_b = EvalSuiteResult("math_suite", "model_b", (res_b1, res_b2), datetime.utcnow())
            registry.record(run_b)

            # Retrieve latest and verify persistence
            latest_a = registry.latest("math_suite", "model_a")
            self.assertIsNotNone(latest_a)
            self.assertEqual(latest_a.pass_rate, 0.5)

            # Run delta report comparison
            report = registry.compare("math_suite", "model_a", "model_b")
            self.assertEqual(report.suite_name, "math_suite")
            self.assertEqual(report.pass_rate_a, 0.5)
            self.assertEqual(report.pass_rate_b, 1.0)
            
            # [Silent Failure] Check pass rate delta math
            self.assertEqual(report.pass_rate_delta, 0.5)
            self.assertEqual(report.improved_cases, ("2+2",))
            self.assertEqual(len(report.regressed_cases), 0)

        finally:
            if os.path.exists(db_path):
                os.remove(db_path)
            os.rmdir(temp_dir)
