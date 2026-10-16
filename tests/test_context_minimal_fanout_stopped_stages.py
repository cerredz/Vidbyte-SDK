"""FILE: tests/test_context_minimal_fanout_stopped_stages.py

PURPOSE: Regression tests proving a fanout stage agent stopped by its own limit is reported as not having answered.
ROLE IN CODEBASE: Guards ContextMinimalFanoutParadigm's branch outcomes and environment overview against SDK stop notices.
ARCHITECTURE NOTE: Runs the real four-stage arun offline on scripted runners supplied through AgentRoleSettings.runner.
COMMON MODIFICATION PATTERNS: Add a case here when a stage starts reading its agent's reply content.
KNOWN EDGE CASES: A reply with no stop_reason counts as an answer, matching OutputShaping.is_deliverable.
RELATED DOCS: vidbyte/paradigms/context_minimal_fanout/README.md
TESTS: python -m pytest tests/test_context_minimal_fanout_stopped_stages.py
"""

from __future__ import annotations

import json
import unittest

from vidbyte.paradigms import AgentRoleSettings, ContextMinimalFanoutParadigm, ContextMinimalFanoutResult, ContextMinimalFanoutSettings
from vidbyte.tools import tool

NOTICE = "Agent runtime stopped after reaching max_iterations."
OVERVIEW = "Python service with an LRU cache"
PLAN_FIELDS = [{"name": "goal"}, {"name": "global_instructions"}, {"name": "non_overlap_requirements", "repeated": True}, {"name": "prompts", "repeated": True}]
PLAN_VALUES = [
    ("append_output", {"field": "goal", "value": "Bump versions"}),
    ("append_output", {"field": "global_instructions", "value": "Edit only owned files."}),
    ("append_output", {"field": "prompts", "value": json.dumps({"id": "p1", "title": "Cache", "prompt": "Bump cache.", "owned_paths": ["src/cache.py"]})}),
    ("append_output", {"field": "prompts", "value": json.dumps({"id": "p2", "title": "API", "prompt": "Bump api.", "owned_paths": ["src/api.py"]})}),
]
PEEK = [("peek", {})]


@tool
def peek() -> str:
    """Look at the repository without changing it."""
    return "nothing new"


class _Resp:
    def __init__(self, calls: list[tuple[str, dict[str, object]]]) -> None:
        self.text = ""
        self.raw = {"output": [{"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": f"fc_{index}"} for index, (name, args) in enumerate(calls)]}


def _done(answer: str) -> list[tuple[str, dict[str, object]]]:
    return [("isDone", {"final_answer": answer})]


class TurnRunner:
    """Replays one scripted turn per model call, then repeats its last turn forever."""

    def __init__(self, *turns: list[tuple[str, dict[str, object]]]) -> None:
        self.turns = list(turns)
        self.prompts: list[str] = []

    def run(self, prompt: str, **kwargs: object) -> _Resp:
        self.prompts.append(prompt)
        return _Resp(self.turns.pop(0) if len(self.turns) > 1 else self.turns[0])


class BranchRunner:
    """Answers every implementation branch at once, except the looping one, which only calls peek."""

    def __init__(self, looping_id: str | None = None) -> None:
        self.looping_id = looping_id

    def run(self, prompt: str, **kwargs: object) -> _Resp:
        for prompt_id in ("p1", "p2"):
            if f'<implementation_prompt id="{prompt_id}"' in prompt:
                return _Resp(PEEK if prompt_id == self.looping_id else _done(f"implemented {prompt_id}"))
        raise AssertionError("not an implementation prompt")


def _answering_context() -> TurnRunner:
    return TurnRunner([("declare_output_schema", {"fields": [{"name": "summary"}]})], [("append_output", {"field": "summary", "value": OVERVIEW})], _done("done"))


def _planner() -> TurnRunner:
    return TurnRunner([("declare_output_schema", {"fields": PLAN_FIELDS})], PLAN_VALUES, _done("planned"))


def _role(name: str, runner: object) -> AgentRoleSettings:
    # Small iteration caps so a looping agent stops on its own limit within a few scripted turns.
    return AgentRoleSettings(name=name, provider="deepseek", model_name="deepseek-v4-flash", api_keys=["sk-test"], runner=runner, tools=(peek,), agent_options={"max_iterations": 3})


class FanoutStoppedStageTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, context: TurnRunner, branches: BranchRunner, splitter: TurnRunner | None = None) -> ContextMinimalFanoutResult:
        settings = ContextMinimalFanoutSettings(
            context=_role("ctx", context),
            splitter=_role("split", splitter or _planner()),
            adversarial=_role("adv", _planner()),
            implementation=_role("impl", branches),
            include_minimal_toolset=False,
        )
        return await ContextMinimalFanoutParadigm(settings).arun("Bump the versions")

    async def test_branch_stopped_on_max_iterations_is_a_failed_branch(self) -> None:
        result = await self._run(_answering_context(), BranchRunner(looping_id="p1"))
        outputs = {output.prompt_id: output for output in result.outputs}
        self.assertEqual(outputs["p1"].metadata.get("stop_reason"), "max_iterations")
        self.assertEqual(outputs["p1"].content, NOTICE)
        self.assertEqual(outputs["p1"].error, "Branch stopped before answering: max_iterations")
        self.assertIsNone(outputs["p2"].error)
        self.assertEqual(outputs["p2"].content, "implemented p2")
        self.assertEqual(result.metadata["failed_count"], 1)

    async def test_context_agent_stopped_before_summary_leaves_no_overview(self) -> None:
        splitter = _planner()
        result = await self._run(TurnRunner(PEEK), BranchRunner(), splitter=splitter)
        self.assertEqual(result.environment.summary.overview, "")
        self.assertNotIn(NOTICE, splitter.prompts[0])
        self.assertIn("<overview>\nN/A\n</overview>", splitter.prompts[0])
        self.assertEqual(result.metadata["failed_count"], 0)

    async def test_answering_stages_are_unchanged(self) -> None:
        splitter = _planner()
        result = await self._run(_answering_context(), BranchRunner(), splitter=splitter)
        self.assertEqual([(output.content, output.error) for output in result.outputs], [("implemented p1", None), ("implemented p2", None)])
        self.assertEqual(result.metadata["failed_count"], 0)
        self.assertEqual(result.environment.summary.overview, OVERVIEW)
        self.assertIn(OVERVIEW, splitter.prompts[0])

    async def test_context_prose_answer_without_summary_is_still_the_overview(self) -> None:
        result = await self._run(TurnRunner(_done(OVERVIEW)), BranchRunner())
        self.assertEqual(result.environment.summary.overview, OVERVIEW)


if __name__ == "__main__":
    unittest.main()
