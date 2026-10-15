from __future__ import annotations

import unittest
from unittest.mock import patch
from typing import Any

from tests.agent_test_support import build_test_agent
from tests.test_agent_fork_isolation import TwoToolMcpTransport
from vidbyte.agents import AgentForkSettings, AgentMessage, BaseAgent
from vidbyte.agents.runtimes.configs import ActorRuntime
from vidbyte.agents.settings import AgentLoopSettings, ToolErrorPolicy, ToolSettings
from vidbyte.context.handoff import EngineeringHandoff
from vidbyte.lib.config import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.fork import ForkConversationTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec, ToolStatus


class DoneRunner:
    """Runner that immediately terminates the agent loop."""

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> TextModelResponse:
        # Returns an isDone call so the agent can complete without a provider.
        del system
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="", raw={"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "child:{prompt}"}}'}]})


class NamedTool(BaseTool):
    """Minimal executable tool used for catalog and subset tests."""

    def __init__(self, name: str) -> None:
        # Stores the stable model-facing tool name.
        self._name = name

    def spec(self) -> ToolSpec:
        # Returns the tool declaration used by Tools.
        return ToolSpec(name=self._name, description=f"{self._name} tool")

    async def execute(self, call: ToolCall) -> ToolResult:
        # Returns a simple success result for completeness.
        return ToolResult.success(call.tool_name, "ok")


class StubChild:
    """Child agent returned by StubAgent.fork for fork tool unit tests."""

    def __init__(self) -> None:
        # Provides the fields ForkConversationTool includes in result metadata.
        self.name = "stub-child"
        self.runner_config = type("RunnerConfig", (), {"run_id": "child-run"})()
        self.metadata = {"forked_from": "parent-run", "fork_depth": 1}
        self.prompts: list[str] = []

    async def generate_reply(self, prompt: str) -> AgentMessage:
        # Records the prompt and returns a deterministic child answer.
        self.prompts.append(prompt)
        return AgentMessage(sender=self.name, recipient="parent", content=f"answer:{prompt}")


class StubAgent:
    """Parent-like object with the attributes ForkConversationTool needs."""

    def __init__(self) -> None:
        # Creates parent state and captures fork kwargs for assertions.
        self.history = [
            AgentMessage(sender="a", recipient="parent", content="one"),
            AgentMessage(sender="b", recipient="parent", content="two"),
            AgentMessage(sender="c", recipient="parent", content="three"),
        ]
        self.metadata = {"fork_depth": 0}
        self.agent_loop_settings = AgentLoopSettings(max_iterations=3)
        self.tools = Tools([NamedTool("alpha"), NamedTool("beta")])
        self.captured: AgentForkSettings | None = None
        self.child = StubChild()

    def fork(self, settings: AgentForkSettings) -> StubChild:
        # Captures the requested fork settings and returns a fake runnable child.
        self.captured = settings
        return self.child


def _call(**arguments: object) -> ToolCall:
    # Builds a fork_conversation ToolCall from keyword arguments.
    return ToolCall(tool_name="fork_conversation", arguments=dict(arguments))


class ToolsSubsetTests(unittest.TestCase):
    def test_subset_preserves_catalog_order_and_errors_on_unknown_names(self) -> None:
        # Tools.subset should return exactly requested known tools in existing catalog order.
        catalog = Tools([NamedTool("a"), NamedTool("b"), NamedTool("c")])
        self.assertEqual(catalog.subset(["c", "a"]).names(), ("a", "c"))
        with self.assertRaises(Exception) as ctx:
            catalog.subset(["missing"])
        self.assertIn("missing", str(ctx.exception))


class ForkConversationToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_runs_bound_agent_fork_successfully(self) -> None:
        # A real BaseAgent should bind the fork tool and return the child reply plus lineage metadata.
        tool = ForkConversationTool()
        agent = build_test_agent(name="parent", system_prompt="Work.", runner=DoneRunner(), tools=[tool], run_id="parent-run")
        agent.history.append(AgentMessage(sender="user", recipient="parent", content="context"))

        result = await tool.execute(_call(prompt="solve it", name="child", purpose="branch"))

        self.assertIs(tool._agent, agent)
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("child:solve it", result.output)
        self.assertEqual(result.metadata["forked_from"], "parent-run")
        self.assertEqual(result.metadata["fork_depth"], 1)
        self.assertEqual(result.metadata["name"], "child")

    async def test_model_chosen_provider_swap_does_not_pass_parent_api_key(self) -> None:
        # A model-requested provider swap must not carry the parent's vendor key to the new provider.
        tool = ForkConversationTool()
        agent = build_test_agent(name="parent", system_prompt="Work.", runner=DoneRunner(), tools=[tool], provider="deepseek", model_name="deepseek-v4-flash", api_key="sk-deepseek-SECRET")
        children: list[BaseAgent] = []
        real_fork = agent.fork

        def fork_with_fake_runner(settings: AgentForkSettings) -> BaseAgent:
            # Fork for real, then bind the offline runner so the child can answer without a provider.
            child = real_fork(settings)
            child._runner_cache.update(agent._runner_cache)
            children.append(child)
            return child

        with patch.object(agent, "fork", side_effect=fork_with_fake_runner):
            result = await tool.execute(_call(prompt="solve it", provider="openai"))

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(children[0].runner_config.provider, "openai")
        self.assertIsNone(children[0].runner_config.api_key)

    async def test_history_last_n_and_tool_names_translate_to_fork_kwargs(self) -> None:
        # The tool should slice history and resolve tool_names before calling parent.fork().
        agent = StubAgent()
        tool = ForkConversationTool(extra_toolsets={"extra": Tools([NamedTool("gamma")])})
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", history_mode="last_n", last_n=2, tool_names=["beta", "gamma"]))

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual([msg.content for msg in agent.captured.history], ["two", "three"])
        self.assertEqual(agent.captured.tools.names(), ("beta", "gamma"))

    async def test_drop_only_fork_does_not_grant_unnamed_extra_toolsets(self) -> None:
        # @intent fork-extras-are-opt-in
        # A drop-only fork pulled in every configured extra toolset although none was named.
        agent = StubAgent()
        tool = ForkConversationTool(extra_toolsets={"admin": Tools([NamedTool("delete_user")])})
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", drop_tool_names=["beta"]))

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(agent.captured.tools.names(), ("alpha",))

    async def test_null_history_mode_falls_back_to_default_chain(self) -> None:
        # A JSON-null history_mode means "not given": context_window's mode applies, else "full", never "none".
        cases = (
            ({"history_mode": None}, ["one", "two", "three"]),
            ({"history_mode": None, "context_window": {"history_mode": None}}, ["one", "two", "three"]),
            ({"history_mode": None, "context_window": {"history_mode": "none"}}, []),
            ({"history_mode": "none"}, []),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                agent = StubAgent()
                tool = ForkConversationTool()
                tool.bind_agent(agent)

                result = await tool.execute(_call(prompt="branch", **overrides))

                self.assertEqual(result.status, ToolStatus.SUCCESS)
                self.assertEqual([msg.content for msg in agent.captured.history], expected)

    async def test_null_last_n_falls_back_to_context_window_last_n(self) -> None:
        # Null top-level twins behave like omitted ones, so context_window's last_n slices history; explicit values still win.
        cases = (
            ({}, ["two", "three"]),
            ({"history_mode": None, "last_n": None}, ["two", "three"]),
            ({"last_n": 1}, ["three"]),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                agent = StubAgent()
                tool = ForkConversationTool()
                tool.bind_agent(agent)

                result = await tool.execute(_call(prompt="branch", context_window={"history_mode": "last_n", "last_n": 2}, **overrides))

                self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
                self.assertEqual([msg.content for msg in agent.captured.history], expected)

    def test_null_context_algorithm_falls_back_to_context_window_algorithm(self) -> None:
        # A null top-level context_algorithm must not drop context_window's algorithm; an explicit one still wins.
        tool = ForkConversationTool()
        tool.bind_agent(StubAgent())
        context_window = {"algorithm": "compact_tool_outputs"}

        omitted = tool._build_request({"prompt": "p", "context_window": context_window})
        null = tool._build_request({"prompt": "p", "context_window": context_window, "context_algorithm": None})
        explicit = tool._build_request({"prompt": "p", "context_window": context_window, "context_algorithm": "default"})

        self.assertEqual(omitted["algorithm"], "compact_tool_outputs")
        self.assertEqual(null["algorithm"], "compact_tool_outputs")
        self.assertEqual(explicit["algorithm"], "default")

    async def test_invalid_history_mode_still_returns_tool_error(self) -> None:
        # A real but unknown history_mode keeps its actionable validation error.
        agent = StubAgent()
        tool = ForkConversationTool()
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", history_mode="sideways"))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("history_mode must be one of: full, none, last_n.", result.output)

    async def test_sdk_native_fork_options_translate_to_fork_kwargs(self) -> None:
        # The model-facing tool should expose Vidbyte-native fork knobs, not only generic prompt/tools/model.
        agent = StubAgent()
        tool = ForkConversationTool(allowed_models=("gpt-4.1-mini",), extra_toolsets={"extra": Tools([NamedTool("gamma")])})
        tool.bind_agent(agent)

        result = await tool.execute(_call(
            prompt="branch",
            context_window={
                "history_mode": "none",
                "algorithm": "compact_tool_outputs",
                "budget_tokens": 1000,
                "compaction_trigger_tokens": 900,
                "compaction_target_tokens": 400,
            },
            extra_toolset_names=["extra"],
            drop_tool_names=["beta"],
            model="gpt-4.1-mini",
            provider="openai",
            temperature=0.4,
            runtime="linear",
            loop_settings={"max_tool_calls": 2, "allowed_tools": ["alpha"]},
            handoff={"preset": "engineering", "title": "Child Handoff"},
            output_schema={"type": "object"},
            include_run_state=True,
            mcp=False,
            metadata={"branch": "sdk-native"},
            run_id="child-run-explicit",
        ))

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(agent.captured.history, [])
        self.assertEqual(agent.captured.tools.names(), ("alpha", "gamma"))
        self.assertEqual(agent.captured.drop_tools, ("beta",))
        self.assertEqual(agent.captured.model_name, "gpt-4.1-mini")
        self.assertEqual(agent.captured.provider, "openai")
        self.assertEqual(agent.captured.temperature, 0.4)
        self.assertEqual(agent.captured.runtime, "linear")
        self.assertEqual(agent.captured.algorithm, "compact_tool_outputs")
        self.assertIsInstance(agent.captured.handoff, EngineeringHandoff)
        self.assertEqual(agent.captured.handoff.title, "Child Handoff")
        self.assertEqual(agent.captured.output_schema, {"type": "object"})
        self.assertTrue(agent.captured.include_run_state)
        self.assertFalse(agent.captured.mcp)
        self.assertEqual(agent.captured.metadata, {"branch": "sdk-native"})
        self.assertEqual(agent.captured.run_id, "child-run-explicit")
        settings = agent.captured.agent_loop_settings
        self.assertEqual(settings.max_iterations, 3)
        self.assertEqual(settings.max_tool_calls, 2)
        self.assertEqual(settings.allowed_tools, ("alpha",))
        self.assertEqual(settings.context_window_budget, 1000)
        self.assertEqual(settings.compaction_trigger_tokens, 900)
        self.assertEqual(settings.compaction_target_tokens, 400)

    async def test_unknown_context_algorithm_returns_tool_error(self) -> None:
        # SDK-native preset inputs should be constrained to names Vidbyte recognizes.
        agent = StubAgent()
        tool = ForkConversationTool()
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", context_algorithm="not-a-preset"))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("context_algorithm", result.output)

    async def test_disallowed_model_returns_tool_error(self) -> None:
        # Model overrides must be rejected unless explicitly allow-listed by the developer.
        agent = StubAgent()
        tool = ForkConversationTool(allowed_models=("allowed",))
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", model="blocked"))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("allowed_models", result.output)

    def test_bare_string_allowed_models_is_refused(self) -> None:
        # A bare string would split into characters and reject the one model the developer allowed.
        with self.assertRaisesRegex(ConfigurationError, "allowed_models must be a list of model names"):
            ForkConversationTool(allowed_models="deepseek-reasoner")
        self.assertEqual(ForkConversationTool(allowed_models=["deepseek-reasoner"])._allowed_models, ("deepseek-reasoner",))

    async def test_max_iterations_cannot_exceed_parent_cap(self) -> None:
        # The child loop budget must not exceed the parent's configured max_iterations.
        agent = StubAgent()
        tool = ForkConversationTool()
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", max_iterations=4))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("parent cap", result.output)

    async def test_loop_overrides_keep_parent_tool_guardrails(self) -> None:
        # Model-requested loop overrides must not drop the parent's denied tools or other guardrails.
        for overrides in ({"max_iterations": 2}, {"loop_settings": {"max_tokens": 5000}}):
            with self.subTest(overrides=overrides):
                agent = StubAgent()
                parent = AgentLoopSettings(max_iterations=3, tool_settings=ToolSettings(denied_tools={"beta"}), tool_error_policy=ToolErrorPolicy(), max_contract_rejections=5, max_queued_prompts=7)
                agent.agent_loop_settings = parent
                tool = ForkConversationTool()
                tool.bind_agent(agent)

                result = await tool.execute(_call(prompt="branch", **overrides))

                self.assertEqual(result.status, ToolStatus.SUCCESS)
                settings = agent.captured.agent_loop_settings
                self.assertIs(settings.tool_settings, parent.tool_settings)
                self.assertIsNotNone(settings.tool_settings.denial("beta", {}))
                self.assertIs(settings.tool_error_policy, parent.tool_error_policy)
                self.assertEqual(settings.output_contracts, parent.output_contracts)
                self.assertEqual(settings.max_contract_rejections, 5)
                self.assertEqual(settings.max_queued_prompts, 7)

    async def test_allowed_tools_override_cannot_widen_parent_gate(self) -> None:
        # @intent fork-tool-allowed-tools-cannot-widen-parent-gate
        # A gated parent forked a child whose allowed_tools named a gated-out tool, and the child ran it.
        agent = StubAgent()
        agent.agent_loop_settings = AgentLoopSettings(max_iterations=3, allowed_tools=("alpha",))
        tool = ForkConversationTool()
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", loop_settings={"allowed_tools": ["beta"]}))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("cannot widen the parent's allowed_tools gate", result.output)
        self.assertIn("'beta'", result.output)
        self.assertEqual(result.metadata["error_type"], "PermissionDeniedError")
        self.assertIsNone(agent.captured)
        self.assertEqual(agent.child.prompts, [])

    async def test_allowed_tools_override_may_narrow_parent_gate_or_pick_freely_without_one(self) -> None:
        # Narrowing within a parent gate is allowed; with no parent gate any catalog tool is still accepted.
        cases = ((("alpha", "beta"), ["alpha"]), (None, ["beta"]))
        for parent_gate, requested in cases:
            with self.subTest(parent_gate=parent_gate):
                agent = StubAgent()
                agent.agent_loop_settings = AgentLoopSettings(max_iterations=3, allowed_tools=parent_gate)
                tool = ForkConversationTool()
                tool.bind_agent(agent)

                result = await tool.execute(_call(prompt="branch", loop_settings={"allowed_tools": requested}))

                self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
                self.assertEqual(agent.captured.agent_loop_settings.allowed_tools, tuple(requested))

    async def test_null_loop_settings_fields_keep_parent_values(self) -> None:
        # @intent null-optional-arg-means-default
        # A null allowed_tools gave the child an empty gate that denied every tool, and a null max_tokens failed the fork.
        agent = StubAgent()
        agent.agent_loop_settings = AgentLoopSettings(max_iterations=3, max_tokens=4000, allowed_tools=("alpha",))
        tool = ForkConversationTool()
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", loop_settings={"max_iterations": 2, "allowed_tools": None, "max_tokens": None}))

        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        settings = agent.captured.agent_loop_settings
        self.assertEqual(settings.allowed_tools, ("alpha",))
        self.assertEqual(settings.max_tokens, 4000)
        self.assertEqual(settings.max_iterations, 2)

    async def test_null_actor_runtime_max_loop_uses_default(self) -> None:
        # @intent null-optional-arg-means-default
        # A null actor_runtime.max_loop failed the whole fork; it now means "not given", like an omitted key.
        for actor_runtime in ({"topology": "actor_model_p2p"}, {"topology": "actor_model_p2p", "max_loop": None}):
            with self.subTest(actor_runtime=actor_runtime):
                agent = StubAgent()
                tool = ForkConversationTool()
                tool.bind_agent(agent)

                result = await tool.execute(_call(prompt="branch", actor_runtime=actor_runtime))

                self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
                self.assertIsInstance(agent.captured.runtime, ActorRuntime)
                self.assertEqual(agent.captured.runtime.max_loop, 20)
        agent = StubAgent()
        tool = ForkConversationTool()
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", actor_runtime={"topology": "actor_model_p2p", "max_loop": 0}))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("actor_runtime.max_loop must be a positive integer.", result.output)

    async def test_depth_cap_prevents_recursive_fork_construction(self) -> None:
        # Depth cap should be checked before parent.fork is called.
        agent = StubAgent()
        agent.metadata["fork_depth"] = 2
        tool = ForkConversationTool(max_fork_depth=2)
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch"))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("depth cap", result.output)
        self.assertIsNone(agent.captured)

    async def test_missing_prompt_returns_tool_error(self) -> None:
        # Required-argument validation should return ToolResult.error instead of raising.
        agent = StubAgent()
        tool = ForkConversationTool()
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt=" "))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("prompt", result.output)


    async def test_child_mcp_servers_close_after_its_run_even_when_it_fails(self) -> None:
        # @intent internal-forks-close-their-mcp-servers
        # [Resource Leak] The child reconnected the parent's MCP servers and was discarded without closing them.
        class ClosingChild(StubChild):
            def __init__(self, fail: bool) -> None:
                super().__init__()
                self.fail = fail
                self.events: list[str] = []

            async def generate_reply(self, prompt: str) -> AgentMessage:
                self.events.append("run")
                if self.fail:
                    raise RuntimeError("child crashed")
                return await super().generate_reply(prompt)

            async def close_mcp_servers(self) -> None:
                self.events.append("close")

        for fail, status in ((False, ToolStatus.SUCCESS), (True, ToolStatus.ERROR)):
            agent = StubAgent()
            child = ClosingChild(fail)
            agent.child = child
            tool = ForkConversationTool()
            tool.bind_agent(agent)

            result = await tool.execute(_call(prompt="branch"))

            self.assertEqual(result.status, status)
            self.assertEqual(child.events, ["run", "close"])

    @patch("vidbyte.tools.mcp.attach.McpStdioTransport", TwoToolMcpTransport)
    async def test_drop_tool_names_removes_inherited_mcp_tool_from_child(self) -> None:
        # @intent fork-tool-drop-names-cover-inherited-mcp-tools
        # The child reconnects the parent's MCP servers, so a dropped MCP tool came back and was offered to the child.
        cases = (
            ({"drop_tool_names": ["remote_calc"]}, {"lookup", "fork_conversation", "spare_calc"}),
            ({}, {"lookup", "fork_conversation", "remote_calc", "spare_calc"}),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                tool = ForkConversationTool()
                agent = build_test_agent(name="parent", system_prompt="Work.", runner=DoneRunner(), tools=[NamedTool("lookup"), tool])
                await agent.attach_mcp_server(["calc"])
                offered: list[set[str]] = []
                real_fork = agent.fork

                def fork_recording_child_tools(settings: AgentForkSettings) -> BaseAgent:
                    # Fork for real, then record the child's tools once its MCP servers connect, before it answers.
                    child = real_fork(settings)
                    real_reply = child.generate_reply

                    async def reply_after_recording(prompt: str) -> AgentMessage:
                        await child._ensure_mcp_connected()
                        offered.append({item.name for item in child.tools})
                        return await real_reply(prompt)

                    child.generate_reply = reply_after_recording  # type: ignore[method-assign]
                    return child

                with patch.object(agent, "fork", side_effect=fork_recording_child_tools):
                    result = await tool.execute(_call(prompt="branch", **overrides))

                self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
                self.assertEqual(offered, [expected])
                self.assertEqual({item.name for item in agent.tools}, {"lookup", "fork_conversation", "remote_calc", "spare_calc"})


if __name__ == "__main__":
    unittest.main()
