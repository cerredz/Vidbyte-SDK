"""FILE: tests/test_context_minimal_fanout_agents.py

PURPOSE: Regression tests proving ContextMinimalFanoutParadigm can build and run its stage agents.
ROLE IN CODEBASE: Guards the paradigm against passing removed BaseAgent arguments such as runner=.
ARCHITECTURE NOTE: Builds stage agents offline and drives the context stage on a scripted runner supplied through AgentRoleSettings.runner.
COMMON MODIFICATION PATTERNS: Add a case here when a stage builder changes how it constructs BaseAgent.
KNOWN EDGE CASES: BaseAgent resolves the runner type from provider/model first, so roles keep a real text model name.
RELATED DOCS: docs/design/paradigm-stale-runner-kwarg.md
TESTS: python -m pytest tests/test_context_minimal_fanout_agents.py
"""

from __future__ import annotations

import unittest

from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.paradigms import AgentRoleSettings, ContextMinimalFanoutParadigm, ContextMinimalFanoutSettings
from vidbyte.paradigms.context_minimal_fanout.types import SplitPrompt
from vidbyte.tools.builtins.output_schema import OutputSchemaBuilder


class _Resp:
    def __init__(self, raw: dict) -> None:
        self.text = ""
        self.raw = raw


class ScriptedRunner:
    """Finishes every run at once with a fixed final answer."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def run(self, prompt: str, **kwargs: object) -> _Resp:
        self.prompts.append(prompt)
        call = {"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "%s"}' % self.answer, "call_id": "c1"}
        return _Resp({"output": [call]})


def _settings(runner: object | None = None) -> ContextMinimalFanoutSettings:
    role = AgentRoleSettings(name="role", provider="deepseek", model_name="deepseek-v4-flash", api_key="sk-test", runner=runner)
    return ContextMinimalFanoutSettings(context=role, splitter=role, adversarial=role, implementation=role, include_minimal_toolset=False)


class ContextMinimalFanoutAgentTests(unittest.IsolatedAsyncioTestCase):
    def test_stage_agents_build_without_a_runner(self) -> None:
        paradigm = ContextMinimalFanoutParadigm(_settings())
        settings = paradigm.settings
        split = SplitPrompt(id="p1", title="Part one", prompt="Do part one.")
        planner = paradigm._build_planning_agent(settings.splitter, "splitter", OutputSchemaBuilder(), settings)
        implementer = paradigm._build_implementation_agent(split, settings)
        self.assertEqual(planner._runner_cache, {})
        self.assertEqual(implementer._runner_cache, {})

    def test_supplied_role_runner_is_used_by_each_stage_agent(self) -> None:
        runner = ScriptedRunner("unused")
        paradigm = ContextMinimalFanoutParadigm(_settings(runner))
        settings = paradigm.settings
        split = SplitPrompt(id="p1", title="Part one", prompt="Do part one.")
        planner = paradigm._build_planning_agent(settings.adversarial, "adversarial", OutputSchemaBuilder(), settings)
        implementer = paradigm._build_implementation_agent(split, settings)
        self.assertIs(planner._runner_cache[RUNNER_TYPE_TEXT], runner)
        self.assertIs(implementer._runner_cache[RUNNER_TYPE_TEXT], runner)

    async def test_context_stage_runs_on_the_supplied_runner(self) -> None:
        runner = ScriptedRunner("repo uses pytest")
        paradigm = ContextMinimalFanoutParadigm(_settings(runner))
        environment = await paradigm._run_context_agent("Add a feature.", paradigm.settings)
        self.assertEqual(len(runner.prompts), 1)
        self.assertIn("Add a feature.", runner.prompts[0])
        self.assertIn("repo uses pytest", environment.to_prompt_block())


if __name__ == "__main__":
    unittest.main()
