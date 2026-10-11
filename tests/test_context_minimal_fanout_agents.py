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
from vidbyte.lib.errors import ConfigurationError
from vidbyte.paradigms import AgentRoleSettings, ContextMinimalFanoutParadigm, ContextMinimalFanoutSettings
from vidbyte.paradigms.context_minimal_fanout.types import ContextFile, EnvironmentContext, PromptSplitPlan, SplitPrompt
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


class SnapshotNullTextTests(unittest.TestCase):
    """A null snapshot value reads like a missing key, never as the literal text "None"."""

    def test_null_environment_keys_map_like_omitted_keys(self) -> None:
        nulled = EnvironmentContext.from_snapshot({"values": {
            "summary": {"overview": None, "summary": "Python service with an LRU cache", "objective": None, "domain": None},
            "files": [{"path": "src/cache.py", "notes": None, "content": None}],
        }})
        omitted = EnvironmentContext.from_snapshot({"values": {
            "summary": {"summary": "Python service with an LRU cache"},
            "files": [{"path": "src/cache.py"}],
        }})
        self.assertEqual(nulled, omitted)
        self.assertEqual(nulled.summary.overview, "Python service with an LRU cache")
        self.assertEqual((nulled.summary.objective, nulled.summary.domain), ("", ""))
        self.assertEqual((nulled.files[0].notes, nulled.files[0].content), ("", ""))
        self.assertNotIn("None", nulled.to_prompt_block())

    def test_null_file_path_is_skipped_and_null_falls_through_to_next_key(self) -> None:
        environment = EnvironmentContext.from_snapshot({"values": {"files": [
            {"path": None, "notes": "dropped"},
            {"path": "src/api.py", "notes": None, "excerpt": "routes", "content": None, "full_text": "def route(): ..."},
        ]}})
        self.assertEqual([f.path for f in environment.files], ["src/api.py"])
        self.assertEqual((environment.files[0].notes, environment.files[0].content), ("routes", "def route(): ..."))

    def test_null_model_comments_falls_through_to_comments_alias(self) -> None:
        nulled = ContextFile.from_value({"path": "a.py", "model_comments": None, "comments": ["x"]})
        omitted = ContextFile.from_value({"path": "a.py", "comments": ["x"]})
        self.assertEqual(nulled, omitted)
        assert nulled is not None
        self.assertEqual(nulled.model_comments, ("x",))
        canonical = ContextFile.from_value({"path": "a.py", "model_comments": ["kept"], "comments": ["x"]})
        assert canonical is not None
        self.assertEqual(canonical.model_comments, ("kept",))

    def test_unfilled_declared_plan_field_reads_as_omitted(self) -> None:
        prompt = {"id": "p1", "title": "Cache core", "prompt": "Refactor the cache."}
        for values in ({"goal": "Split", "global_instructions": None, "prompts": [prompt]}, {"goal": "Split", "prompts": [prompt]}):
            with self.assertRaisesRegex(ConfigurationError, "global_instructions cannot be empty"):
                PromptSplitPlan.from_snapshot({"values": values})
        with self.assertRaisesRegex(ConfigurationError, "title cannot be empty"):
            SplitPrompt.from_mapping({"id": "p1", "title": None, "prompt": "Refactor the cache."})

    def test_real_values_are_unchanged(self) -> None:
        plan = PromptSplitPlan.from_snapshot({"values": {
            "goal": " Split ", "global_instructions": "Keep the API stable.",
            "prompts": [{"id": 7, "title": "Cache core", "prompt": " Refactor the cache. "}],
        }})
        self.assertEqual((plan.goal, plan.global_instructions), ("Split", "Keep the API stable."))
        self.assertEqual((plan.prompts[0].id, plan.prompts[0].prompt), ("7", "Refactor the cache."))
        environment = EnvironmentContext.from_snapshot({"values": {
            "summary": {"overview": "Cache service", "summary": "ignored", "objective": 0},
            "files": [{"path": "src/cache.py", "notes": "LRU impl", "content": "class Cache: ..."}],
        }})
        self.assertEqual((environment.summary.overview, environment.summary.objective), ("Cache service", "0"))
        self.assertEqual((environment.files[0].notes, environment.files[0].content), ("LRU impl", "class Cache: ..."))


if __name__ == "__main__":
    unittest.main()
