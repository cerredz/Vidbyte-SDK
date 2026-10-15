"""FILE: tests/features/system_prompt_presets/test_system_prompt_presets_propagation.py

PURPOSE: Proves that an agent's system-prompt presets reach the system string its model receives, and every agent its run starts, and that opted-out machinery, the fan-out paradigm, and the documented uncovered paths behave as designed.
ROLE IN CODEBASE: Covers the integration section of the design doc's testing plan through real BaseAgent, AgentTool, AgentForker, session serialization, JevAgent, JevRuntime, and ContextMinimalFanoutParadigm code.
ARCHITECTURE NOTE: Every model is a RecordingModel from fakes.py; OfflineAgentTest also refuses SDK HTTP sends and non-loopback sockets, so a test that drifts toward a real provider fails instead of spending money. Jev decisions use the scripted helper from tests/test_jev_compute_situations.py.
COMMON MODIFICATION PATTERNS: A new place that starts agents gets one test here: run it inside a preset-enabled parent and read the child's RecordingModel.systems.
KNOWN EDGE CASES: A child built inside a run but run after it, a raw thread, and a subclass that replaces generate_reply inherit nothing; UncoveredPathTests pins those limits so a change to them is deliberate.
RELATED DOCS: docs/design/working-principles-preset.md; tests/features/system_prompt_presets/FEATURE.md.
TESTS: python scripts/test-working-principles-preset.py, or python -m pytest tests/features/system_prompt_presets.
"""

from __future__ import annotations

import inspect
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.agent_test_support import bind_test_runner
from tests.features.system_prompt_presets.fakes import WORKING_PRINCIPLES, OfflineAgentTest, OfflineAsyncAgentTest, RecordingModel
from tests.test_jev_compute_situations import REQUEST, ScriptedJev, _helper, lookup
from tests.test_jev_preflight import ScriptedDecisionRunner, _runner_class
from vidbyte import tool
from vidbyte.agents.aggregation import AggregateAgent
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.continual_trace import ContinualTraceAgent
from vidbyte.agents.handoff import HandoffAgent
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevComputeSettings, JevRuntimeSettings
from vidbyte.agents.jev.brief.writer import JevRunBriefWriter
from vidbyte.agents.jev.bulk_work import JevBulkWorker
from vidbyte.agents.jev.compute.clone import JevCloneAgent
from vidbyte.agents.jev.compute.swarm import JevSwarmAgent
from vidbyte.agents.jev.continuation import JevFreshContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.gate.clarification import JevClarificationAgent
from vidbyte.agents.jev.settings import JevContinualSettings, JevRunBriefSettings
from vidbyte.agents.multi.agent import MultiAgent
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.agents import AgentForkSettings, AgentMetadata
from vidbyte.lib.constants.jev import JEV_SPECIALIST_NONE
from vidbyte.lib.dataclasses.jev import JevRunBriefAppendPayload, JevSpecialist, JevSwarmAssignment
from vidbyte.lib.enums import DecisionModelMode, JevContinuationGate, JevDoneCheck, JevDynamicComputeOption, SystemPromptPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.compute import JevComputeRegistry
from vidbyte.lib.system_prompt_presets import SystemPromptPresetScope
from vidbyte.paradigms.context_minimal_fanout.paradigm import ContextMinimalFanoutParadigm
from vidbyte.paradigms.context_minimal_fanout.types import AgentRoleSettings, ContextMinimalFanoutSettings, SplitPrompt
from vidbyte.prompts import Prompt, Prompts, SystemPromptPresetComposer
from vidbyte.sessions import Session
from vidbyte.sessions.serialization import SessionSerializer
from vidbyte.sessions.stores.memory import InMemorySessionStore
from vidbyte.tools.builtins import ForkConversationTool
from vidbyte.tools.builtins.output_schema import OutputSchemaBuilder

WP = SystemPromptPreset.WORKING_PRINCIPLES
MODEL = {"provider": "openai", "model_name": "gpt-4.1-mini"}
LOOP_NOTE = Prompts().get(Prompt.AGENTIC_LOOP_CONTEXT_PROMPT).strip()
_JEV_HELPER = "vidbyte.agents.jev.compute.recognizer.DecisionModelHelper"
_JEV_GATE_HELPER = "vidbyte.agents.jev.gate.gate.DecisionModelHelper"
CLONE_KEYS = {key.value for key in JevComputeRegistry.question_keys(JevDynamicComputeOption.CLONE)}


def _agent(name: str, prompt: str, *calls: tuple[str, dict[str, object]], **options: Any) -> tuple[BaseAgent, RecordingModel]:
    # Builds an offline agent with its own RecordingModel that requests `calls` before finishing.
    model = RecordingModel(name, calls)
    return bind_test_runner(BaseAgent(name=name, system_prompt=prompt, **MODEL, **options), model), model


def _jev_settings(**options: Any) -> JevAgentSettings:
    # The main Jev agent used across the Jev tests; options add fields such as system_prompt_presets.
    return JevAgentSettings(name="researcher", system_prompt="Research.", provider="openai", model_name="gpt-4.1", api_key="main-key", tools=(lookup,), **options)


def _managed(**options: Any) -> JevRuntimeSettings:
    # Jev runtime settings whose decisions the scripted helper answers in-process.
    return JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED), **options)


def _composed(agent: BaseAgent) -> str:
    # The system prompt the agent's runtime would send right now, under whatever scope is active.
    return str(agent._runtime().system_prompt)


class BaseAgentPresetTests(OfflineAsyncAgentTest):
    async def test_an_enabled_agent_sends_the_paragraph_once_between_its_prompt_and_the_loop_note(self) -> None:
        agent, model = _agent("writer", "You write release notes.", system_prompt_presets=[WP])
        reply = await agent.arun("Summarize the release.")
        system = model.systems[0]
        self.assertEqual(system.count(WORKING_PRINCIPLES), 1)
        self.assertLess(system.index("You write release notes."), system.index(WORKING_PRINCIPLES))
        self.assertLess(system.index(WORKING_PRINCIPLES), system.index(LOOP_NOTE))
        self.assertIn(f"You write release notes.\n\n{WORKING_PRINCIPLES}\n\n", system)
        self.assertEqual(reply.metadata["system_prompt_presets"], ["working_principles"])
        self.assertEqual(agent.system_prompt, "You write release notes.")

    async def test_a_disabled_agent_sends_exactly_what_it_sent_before(self) -> None:
        plain, plain_model = _agent("writer", "  You write release notes.\n", run_id="run-1")
        empty, empty_model = _agent("writer", "  You write release notes.\n", run_id="run-1", system_prompt_presets=())
        plain_reply = await plain.arun("Summarize the release.")
        await empty.arun("Summarize the release.")
        self.assertEqual(_composed(plain), "  You write release notes.\n")
        self.assertNotIn(WORKING_PRINCIPLES, plain_model.systems[0])
        self.assertEqual(plain_model.systems, empty_model.systems)
        self.assertNotIn("system_prompt_presets", plain_reply.metadata)
        self.assertIsNone(plain.system_prompt_presets)

    async def test_string_values_work_like_members(self) -> None:
        agent, model = _agent("writer", "Write.", system_prompt_presets=["working_principles"])
        reply = await agent.arun("Go.")
        self.assertEqual(agent.system_prompt_presets, (WP,))
        self.assertEqual(model.systems[0].count(WORKING_PRINCIPLES), 1)
        self.assertEqual(reply.metadata["system_prompt_presets"], ["working_principles"])

    async def test_an_explicit_per_call_system_option_still_replaces_the_whole_prompt(self) -> None:
        agent, model = _agent("writer", "Write.", system_prompt_presets=[WP])
        await agent.arun("Go.", system="Caller override.")
        self.assertEqual(model.systems[0], "Caller override.")

    def test_invalid_values_fail_at_construction(self) -> None:
        for value in ("working_principles", ["unknown"], [WP, WP], 7):
            with self.assertRaises(ConfigurationError):
                BaseAgent(name="writer", system_prompt="Write.", **MODEL, system_prompt_presets=value)

    async def test_every_model_call_in_a_multi_turn_run_carries_the_paragraph(self) -> None:
        agent, model = _agent("writer", "Write.", ("lookup", {"topic": "a"}), ("lookup", {"topic": "b"}), tools=[lookup], system_prompt_presets=[WP])
        await agent.arun("Go.")
        self.assertEqual(len(model.systems), 3)
        self.assertTrue(all(system.count(WORKING_PRINCIPLES) == 1 for system in model.systems))

    async def test_the_scope_ends_with_the_run(self) -> None:
        enabled, _ = _agent("writer", "Write.", system_prompt_presets=[WP])
        await enabled.arun("Go.")
        self.assertEqual(SystemPromptPresetScope.active(), ())
        later, later_model = _agent("later", "Later.")
        await later.arun("Go.")
        self.assertNotIn(WORKING_PRINCIPLES, later_model.systems[0])

    async def test_a_run_that_raises_still_ends_the_scope(self) -> None:
        class Broken:
            def run(self, prompt: str, **_: object) -> object:
                raise RuntimeError("provider down")

        agent = bind_test_runner(BaseAgent(name="writer", system_prompt="Write.", **MODEL, system_prompt_presets=[WP]), Broken())
        with self.assertRaises(Exception):
            await agent.arun("Go.")
        self.assertEqual(SystemPromptPresetScope.active(), ())

    def test_the_search_and_actor_runtimes_get_the_composed_prompt_too(self) -> None:
        for runtime in ("mcts_search", "actor_model_p2p", "actor_model_broadcast"):
            agent, _ = _agent("searcher", "Search.", runtime=runtime, system_prompt_presets=[WP])
            self.assertEqual(_composed(agent), f"Search.\n\n{WORKING_PRINCIPLES}", runtime)


class ChildPropagationTests(OfflineAsyncAgentTest):
    async def test_an_as_tool_specialist_gets_the_parents_presets(self) -> None:
        specialist, _ = _agent("analyst", "Analyze data.", agent_metadata=AgentMetadata(name="analyst", description="Analyzes data.", use_cases="Any analysis."))
        parent, parent_model = _agent("lead", "Lead the work.", ("analyst", {}), tools=[specialist.as_tool()], system_prompt_presets=[WP])
        await parent.arun("Analyze the numbers.")
        self.assertIsNone(specialist.system_prompt_presets)
        self.assertEqual(self.models.systems("analyst")[0].count(WORKING_PRINCIPLES), 1)
        self.assertIn("Analyze data.", self.models.systems("analyst")[0])
        self.assertEqual(parent_model.systems[0].count(WORKING_PRINCIPLES), 1)

    async def test_an_agent_started_inside_a_custom_tool_gets_them(self) -> None:
        @tool
        async def research(topic: str) -> str:
            """Research one topic with a helper agent."""
            helper = BaseAgent(name="helper", system_prompt="Research topics.", **MODEL)
            reply = await helper.arun(topic)
            return reply.content

        parent, _ = _agent("lead", "Lead.", ("research", {"topic": "caching"}), tools=[research], system_prompt_presets=[WP])
        await parent.arun("Go.")
        self.assertEqual(self.models.systems("helper")[0].count(WORKING_PRINCIPLES), 1)

    async def test_a_child_that_opts_out_does_not_get_them_nor_do_its_children(self) -> None:
        @tool
        async def grandchild_task(topic: str) -> str:
            """Run the grandchild."""
            grandchild = BaseAgent(name="grandchild", system_prompt="Grandchild.", **MODEL)
            return (await grandchild.arun(topic)).content

        @tool
        async def child_task(topic: str) -> str:
            """Run the opted-out child, which starts the grandchild."""
            child = BaseAgent(name="child", system_prompt="Format JSON.", tools=[grandchild_task], system_prompt_presets=(), **MODEL)
            return (await child.arun(topic)).content

        self.models.script("child", ("grandchild_task", {"topic": "x"}))
        parent, _ = _agent("lead", "Lead.", ("child_task", {"topic": "x"}), tools=[child_task], system_prompt_presets=[WP])
        await parent.arun("Go.")
        self.assertNotIn(WORKING_PRINCIPLES, self.models.systems("child")[0])
        self.assertTrue(self.models.systems("grandchild"))
        self.assertNotIn(WORKING_PRINCIPLES, self.models.systems("grandchild")[0])

    async def test_a_child_whose_prompt_already_holds_the_paragraph_gets_no_second_copy(self) -> None:
        @tool
        async def delegate(topic: str) -> str:
            """Run a child whose prompt a parent model already extended."""
            child = BaseAgent(name="child", system_prompt=f"Do the slice.\n\n{WORKING_PRINCIPLES}", **MODEL)
            return (await child.arun(topic)).content

        parent, _ = _agent("lead", "Lead.", ("delegate", {"topic": "x"}), tools=[delegate], system_prompt_presets=[WP])
        await parent.arun("Go.")
        self.assertEqual(self.models.systems("child")[0].count(WORKING_PRINCIPLES), 1)

    async def test_a_fork_conversation_child_with_its_own_prompt_gets_them(self) -> None:
        call = ("fork_conversation", {"prompt": "Format the findings.", "name": "formatter", "system_prompt": "Only format the output."})
        parent, _ = _agent("lead", "Lead.", call, tools=[ForkConversationTool()], system_prompt_presets=[WP])
        await parent.arun("Go.")
        system = self.models.systems("formatter")[0]
        self.assertIn(f"Only format the output.\n\n{WORKING_PRINCIPLES}", system)
        self.assertEqual(system.count(WORKING_PRINCIPLES), 1)

    def test_a_fork_keeps_the_field_even_with_a_replaced_prompt(self) -> None:
        parent, _ = _agent("lead", "Lead.", system_prompt_presets=[WP])
        child = parent.fork(AgentForkSettings(system_prompt="Only format the output."))
        self.assertEqual(child.system_prompt_presets, (WP,))
        self.assertEqual(_composed(child), f"Only format the output.\n\n{WORKING_PRINCIPLES}")
        opted_out, _ = _agent("plain", "Plain.", system_prompt_presets=())
        self.assertEqual(opted_out.fork().system_prompt_presets, ())
        inheriting, _ = _agent("inherit", "Inherit.")
        self.assertIsNone(inheriting.fork().system_prompt_presets)


class PersistenceTests(OfflineAgentTest):
    def test_export_and_restore_round_trip_every_value(self) -> None:
        for value, expected in ((None, None), ((), ()), ([WP], (WP,))):
            agent, _ = _agent("writer", "Write.", system_prompt_presets=value)
            state = agent.export_state()
            self.assertEqual(state.system_prompt_presets, None if expected is None else tuple(preset.value for preset in expected))
            self.assertEqual(BaseAgent.restore(state).system_prompt_presets, expected)

    def test_a_resumed_and_a_forked_session_keep_the_presets(self) -> None:
        store = InMemorySessionStore()
        agent, _ = _agent("writer", "Write.", system_prompt_presets=[WP])
        session = agent.persist(store=store)
        agent.run("Go.")
        resumed = Session.resume(store, session.id)
        self.assertEqual(resumed.agent.system_prompt_presets, (WP,))
        self.assertEqual(_composed(resumed.agent).count(WORKING_PRINCIPLES), 1)
        self.assertEqual(session.fork().agent.system_prompt_presets, (WP,))

    def test_the_serializer_round_trips_the_field_and_reads_old_states_as_inherit(self) -> None:
        serializer = SessionSerializer()
        agent, _ = _agent("writer", "Write.", system_prompt_presets=[WP])
        data = serializer._run_state_to_dict(agent.export_state())
        self.assertEqual(data["system_prompt_presets"], ["working_principles"])
        self.assertEqual(serializer._run_state_from_dict(data).system_prompt_presets, ("working_principles",))
        old = {key: value for key, value in data.items() if key != "system_prompt_presets"}
        restored = BaseAgent.restore(serializer._run_state_from_dict(old))
        self.assertIsNone(restored.system_prompt_presets)


class JevPresetTests(OfflineAsyncAgentTest):
    def test_jev_settings_validate_and_coerce_the_field(self) -> None:
        self.assertIsNone(_jev_settings().system_prompt_presets)
        self.assertEqual(_jev_settings(system_prompt_presets=["working_principles"]).system_prompt_presets, (WP,))
        with self.assertRaises(ConfigurationError):
            _jev_settings(system_prompt_presets="working_principles")
        with self.assertRaises(ConfigurationError):
            _jev_settings(system_prompt_presets=["unknown"])

    async def test_jev_agents_own_model_calls_carry_the_paragraph(self) -> None:
        model = RecordingModel("researcher")
        agent = bind_test_runner(JevAgent(_jev_settings(system_prompt_presets=[WP])), model)
        reply = await agent.arun("Look into caching.")
        self.assertEqual(agent.system_prompt_presets, (WP,))
        self.assertEqual(model.systems[0].count(WORKING_PRINCIPLES), 1)
        self.assertEqual(reply.metadata["system_prompt_presets"], ["working_principles"])

    async def test_a_specialist_the_gate_chooses_gets_the_presets(self) -> None:
        specialist_model = RecordingModel("database")
        specialist = bind_test_runner(BaseAgent(name="database", system_prompt="Change the schema.", **MODEL), specialist_model)
        main = RecordingModel("researcher")
        settings = _jev_settings(system_prompt_presets=[WP], agents=(JevSpecialist("database", "Changes to the database schema and its migrations.", specialist),))
        agent = bind_test_runner(JevAgent(settings, _managed()), main)
        decision = ScriptedDecisionRunner({}, choice={"database": 0.8, JEV_SPECIALIST_NONE: 0.2})
        with patch(_JEV_GATE_HELPER, new=_runner_class(decision)):
            await agent.arun("Add a migration that adds an email column to the users table.")
        self.assertEqual(agent.response.specialist, "database")
        self.assertEqual(main.systems, [])
        self.assertIsNone(specialist.system_prompt_presets)
        self.assertEqual(specialist_model.systems[0].count(WORKING_PRINCIPLES), 1)

    def test_clones_helpers_bulk_workers_and_fresh_agents_inherit_inside_a_run(self) -> None:
        settings = _jev_settings()
        assignment = JevSwarmAssignment(id="A1", name="Audit", objective="Audit one file.", inputs="src/a.py", deliverable="Findings.", boundaries="Only src/a.py.", verification="Cite lines.")
        fresh_owner = JevAgent(settings, _managed(continual=JevContinualSettings(checks=(JevDoneCheck.MULTI_PART,), gate=JevContinuationGate.FRESH)))
        assert isinstance(fresh_owner.continuation, JevFreshContinuation)
        children = (
            JevCloneAgent(settings, 1),
            JevSwarmAgent(settings, assignment),
            JevBulkWorker(settings, settings.tools, 1, "Audit src/a.py.").agent,
            fresh_owner.continuation.fresh_agent_factory(),
        )
        for child in children:
            self.assertIsNone(child.system_prompt_presets, child.name)
            self.assertNotIn(WORKING_PRINCIPLES, _composed(child), child.name)
            with SystemPromptPresetScope.scope((WP,)):
                self.assertEqual(_composed(child).count(WORKING_PRINCIPLES), 1, child.name)

    async def test_a_clone_launch_through_the_jev_loop_reaches_the_clones_models(self) -> None:
        main = RecordingModel("researcher", [("lookup", {"topic": f"t{index}"}) for index in range(4)])
        compute = JevComputeSettings(brief=JevRunBriefSettings(every_iterations=3), dynamic_compute=tuple(JevDynamicComputeOption), clones=2)
        agent = bind_test_runner(JevAgent(_jev_settings(system_prompt_presets=[WP]), _managed(compute=compute)), main)
        scripted = ScriptedJev({key: 0.95 for key in CLONE_KEYS}, default=0.1)
        payload = JevRunBriefAppendPayload.model_validate({"notes": []})
        assert agent.compute is not None
        with patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=payload))), patch(_JEV_HELPER, new=_helper(scripted)):
            await agent.arun(REQUEST)
        assert agent.response.clone is not None
        self.assertEqual(agent.response.clone.outputs, ("researcher-clone-1 done", "researcher-clone-2 done"))
        for name in ("researcher-clone-1", "researcher-clone-2"):
            self.assertEqual(self.models.systems(name)[0].count(WORKING_PRINCIPLES), 1, name)
        self.assertTrue(all(system.count(WORKING_PRINCIPLES) == 1 for system in main.systems))


class MachineryOptOutTests(OfflineAgentTest):
    def test_fixed_prompt_machinery_never_takes_the_runs_presets(self) -> None:
        settings = _jev_settings(system_prompt_presets=[WP])
        continual = JevContinualSettings(checks=(JevDoneCheck.MULTI_PART, JevDoneCheck.SELF_REVIEW))
        owner = JevAgent(settings, _managed(continual=continual))
        assert isinstance(owner.run_state, JevRunState) and owner.run_state.reviewer is not None
        source, _ = _agent("source", "Source.", system_prompt_presets=[WP])
        machinery = (
            owner.run_state,
            owner.run_state.handoff_writer,
            owner.run_state.reviewer,
            JevRunBriefWriter(settings, JevRunBriefSettings()),
            JevClarificationAgent(settings),
            ContinualTraceAgent.from_source_agent(source, {"note": "One short note."}),
            ContinualTraceAgent({"note": "One short note."}, system_prompt_presets=[WP], **MODEL),
            HandoffAgent.from_source_agent(source, HandoffAgent(**MODEL).spec),
            HandoffAgent(system_prompt_presets=[WP], **MODEL),
        )
        for agent in machinery:
            self.assertEqual(agent.system_prompt_presets, (), agent.name)
            with SystemPromptPresetScope.scope((WP,)):
                self.assertNotIn(WORKING_PRINCIPLES, _composed(agent), agent.name)


class ParadigmTests(OfflineAsyncAgentTest):
    def _settings(self, implementation_options: dict[str, object] | None = None, context_options: dict[str, object] | None = None) -> ContextMinimalFanoutSettings:
        # Fan-out settings whose roles all name an offline-capable model; options opt single roles in.
        return ContextMinimalFanoutSettings(
            context=AgentRoleSettings(name="fanout-context", **MODEL, agent_options=context_options or {}),
            splitter=AgentRoleSettings(name="fanout-splitter", **MODEL),
            adversarial=AgentRoleSettings(name="fanout-adversarial", **MODEL),
            implementation=AgentRoleSettings(name="fanout-implementation", **MODEL, agent_options=implementation_options or {}),
            include_minimal_toolset=False,
        )

    async def test_fanout_agents_get_nothing_by_default_even_inside_a_preset_run(self) -> None:
        settings = self._settings()
        paradigm = ContextMinimalFanoutParadigm(settings)
        with SystemPromptPresetScope.scope((WP,)):
            await paradigm._run_context_agent("Build the feature.", settings)
            planner = paradigm._build_planning_agent(settings.splitter, "splitter", OutputSchemaBuilder(), settings)
            worker = paradigm._build_implementation_agent(SplitPrompt(id="p1", title="Slice", prompt="Do the slice."), settings)
            self.assertNotIn(WORKING_PRINCIPLES, _composed(planner))
            self.assertNotIn(WORKING_PRINCIPLES, _composed(worker))
        self.assertNotIn(WORKING_PRINCIPLES, self.models.systems("fanout-context")[0])

    async def test_a_role_opts_in_through_agent_options(self) -> None:
        options: dict[str, object] = {"system_prompt_presets": [WP]}
        settings = self._settings(implementation_options=options, context_options=options)
        paradigm = ContextMinimalFanoutParadigm(settings)
        await paradigm._run_context_agent("Build the feature.", settings)
        worker = paradigm._build_implementation_agent(SplitPrompt(id="p1", title="Slice", prompt="Do the slice."), settings)
        self.assertEqual(worker.system_prompt_presets, (WP,))
        self.assertEqual(_composed(worker).count(WORKING_PRINCIPLES), 1)
        self.assertEqual(self.models.systems("fanout-context")[0].count(WORKING_PRINCIPLES), 1)


class UncoveredPathTests(OfflineAsyncAgentTest):
    def test_team_facades_take_no_preset_keyword(self) -> None:
        # Documented: MultiAgent and AggregateAgent replace generate_reply and take no
        # BaseAgent keywords; set the field on their members or run them inside a preset run.
        self.assertNotIn("system_prompt_presets", inspect.signature(MultiAgent.__init__).parameters)
        self.assertNotIn("system_prompt_presets", inspect.signature(AggregateAgent.__init__).parameters)
        self.assertIsNot(MultiAgent.generate_reply, BaseAgent.generate_reply)
        self.assertIsNot(AggregateAgent.generate_reply, BaseAgent.generate_reply)

    def test_the_codex_harness_is_not_a_base_agent_so_its_prompt_is_composed_by_hand(self) -> None:
        # Documented: CodexHarnessAgent takes no preset keyword; pass the composed text as its
        # system_prompt, and Codex's own subagents only see the preset through sentence 8.
        self.assertFalse(issubclass(CodexHarnessAgent, BaseAgent))
        self.assertNotIn("system_prompt_presets", inspect.signature(CodexHarnessAgent.__init__).parameters)
        self.assertEqual(SystemPromptPresetComposer.compose("Review the diff.", [WP]), f"Review the diff.\n\n{WORKING_PRINCIPLES}")

    async def test_a_child_built_in_a_run_but_run_after_it_inherits_nothing(self) -> None:
        built: list[BaseAgent] = []

        @tool
        async def build_later(topic: str) -> str:
            """Build a child but leave it for later."""
            built.append(BaseAgent(name="late", system_prompt="Late.", **MODEL))
            return "built"

        parent, _ = _agent("lead", "Lead.", ("build_later", {"topic": "x"}), tools=[build_later], system_prompt_presets=[WP])
        await parent.arun("Go.")
        await built[0].arun("Now.")
        self.assertNotIn(WORKING_PRINCIPLES, self.models.systems("late")[0])

    def test_a_raw_thread_does_not_inherit_the_scope(self) -> None:
        seen: list[tuple[SystemPromptPreset, ...]] = []
        with SystemPromptPresetScope.scope((WP,)):
            thread = threading.Thread(target=lambda: seen.append(SystemPromptPresetScope.active()))
            thread.start()
            thread.join()
        self.assertEqual(seen, [()])
