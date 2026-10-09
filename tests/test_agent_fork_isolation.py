from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel

from tests.agent_test_support import build_test_agent
from vidbyte.agents import AgentForkSettings, AgentLoopSettings, AgentMessage, BaseAgent, MinToolCalls, ToolErrorPolicy, ToolSettings
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.dataclasses.trace import TraceOption
from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.tools.agent_tool import AgentTool
from vidbyte.tools.builtins.handoff import CreateHandoffTool
from vidbyte.sessions import InMemorySessionStore
from vidbyte.tools.builtins.mcp import AttachMcpServerTool
from vidbyte.tools.builtins.run_prompts_sequentially import RunPromptsSequentiallyTool
from vidbyte.tools.builtins.sessions import CheckpointTool
from vidbyte.tools.base import _ToolWrapper, _unwrap_tool
from vidbyte.tools.types import ToolActivity, ToolCall, ToolStatus
from vidbyte.trace.continual import ActionTrace


class _QueueActivity(BaseModel):
    """Activity annotation used to wrap a bound builtin in a with_activity() view."""

    reason: str


class DoneRunner:
    """Runner that immediately terminates the agent loop."""

    async def arun(self, prompt: str, **_: object) -> object:
        # Returns an isDone tool call so tests do not need a real provider.
        class _Resp:
            text = ""
            raw = {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "reply:{prompt}"}}'}]}
        return _Resp()


class MockMcpStdioTransport:
    """Mock MCP transport with deterministic tool discovery."""

    instances: list[MockMcpStdioTransport] = []

    def __init__(
        self,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        request_timeout: float = 30.0,
        shutdown_timeout: float = 5.0,
        stderr_max_bytes: int = 64 * 1024,
        **_: object,
    ) -> None:
        # Captures launch arguments and tracks close calls for handle-sharing tests.
        self.command = command
        self.env = env
        self.request_timeout = request_timeout
        self.shutdown_timeout = shutdown_timeout
        self.stderr_max_bytes = stderr_max_bytes
        self.closed = False
        MockMcpStdioTransport.instances.append(self)

    async def start(self) -> None:
        # Simulates successful subprocess startup.
        return None

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        # Returns the minimal MCP initialize and tools/list responses used by attach_mcp_server.
        del params
        if method == "initialize":
            return {"ok": True}
        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": f"remote_{self.command[0]}",
                        "description": f"Mock tool for {self.command[0]}.",
                        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
                    }
                ]
            }
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "mocked_response"}]}
        raise ValueError(f"Unknown method {method}")

    async def close(self) -> None:
        # Marks this fake transport closed.
        self.closed = True


class RecordingTracer(TracerBase):
    """Minimal tracer that records root trace attributes."""

    def __init__(self) -> None:
        # Stores attributes supplied to start_trace.
        self.started: list[dict[str, Any]] = []
        self.spans: list[dict[str, Any]] = []

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        # Records root trace attributes and returns a dummy context.
        self.started.append({"name": name, **attributes})
        return SpanContext()

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Ignores trace closure details for these focused tests.
        return None

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        # Records child span attributes and returns a dummy span context.
        self.spans.append({"name": name, **attributes})
        return SpanContext()

    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Ignores child span closure details for these focused tests.
        return None


def _call(tool_name: str, **arguments: object) -> ToolCall:
    # Builds a ToolCall with keyword arguments for concise tests.
    return ToolCall(tool_name=tool_name, arguments=dict(arguments))


def _tool_of_type(agent: BaseAgent, tool_type: type) -> object:
    # Finds a tool instance by concrete type in the agent's raw tool tuple.
    return next(tool for tool in agent._agent_tool_items if isinstance(tool, tool_type))


class AgentForkIsolationTests(unittest.IsolatedAsyncioTestCase):
    """Regression coverage for BaseAgent.fork isolation semantics."""

    def _agent(self, *, tools: list[object] | None = None, run_id: str | None = None, tracer: TracerBase | None = None) -> BaseAgent:
        # Constructs a simple runnable agent for fork tests.
        return build_test_agent(name="parent", system_prompt="Work.", runner=DoneRunner(), tools=tools or [], run_id=run_id, tracer=tracer)

    async def test_fork_clones_create_handoff_tool_binding(self) -> None:
        # Parent and child create_handoff tools must record on their own owning agents.
        parent_tool = CreateHandoffTool()
        parent = self._agent(tools=[parent_tool])
        child = parent.fork(AgentForkSettings(name="child"))
        child_tool = _tool_of_type(child, CreateHandoffTool)

        self.assertIsNot(parent_tool, child_tool)
        await parent_tool.execute(_call("create_handoff", title="Parent", sections={"Summary": "p"}))
        self.assertEqual(len(parent.handoffs), 1)
        self.assertEqual(len(child.handoffs), 0)

        await child_tool.execute(_call("create_handoff", title="Child", sections={"Summary": "c"}))
        self.assertEqual(len(parent.handoffs), 1)
        self.assertEqual(len(child.handoffs), 1)

    async def test_fork_clones_attach_mcp_server_tool_binding(self) -> None:
        # Parent and child attach_mcp_server tools must call attach_mcp_server on their own agents.
        parent_tool = AttachMcpServerTool()
        parent = self._agent(tools=[parent_tool])
        child = parent.fork(AgentForkSettings(name="child"))
        child_tool = _tool_of_type(child, AttachMcpServerTool)
        parent.attach_mcp_server = AsyncMock(return_value=parent)  # type: ignore[method-assign]
        child.attach_mcp_server = AsyncMock(return_value=child)  # type: ignore[method-assign]

        self.assertIsNot(parent_tool, child_tool)
        await parent_tool.execute(_call("attach_mcp_server", command='["parent-server"]'))
        await child_tool.execute(_call("attach_mcp_server", command='["child-server"]'))

        parent.attach_mcp_server.assert_awaited_once()
        child.attach_mcp_server.assert_awaited_once()
        self.assertEqual(parent.attach_mcp_server.await_args.kwargs["command"], ["parent-server"])
        self.assertEqual(child.attach_mcp_server.await_args.kwargs["command"], ["child-server"])

    def test_fork_clones_agent_tool_context_getter(self) -> None:
        # AgentTool wrappers must keep parent and child context getters separate after fork.
        delegate = build_test_agent(
            name="delegate",
            system_prompt="Delegate.",
            runner=DoneRunner(),
            agent_metadata=AgentMetadata(name="delegate", description="Delegate work.", use_cases="Testing delegation."),
        )
        parent_tool = delegate.as_tool()
        parent = self._agent(tools=[parent_tool])
        child = parent.fork(AgentForkSettings(name="child"))
        child_tool = _tool_of_type(child, AgentTool)
        parent._active_prompt = "parent prompt"
        child._active_prompt = "child prompt"
        parent.history.append(AgentMessage(sender="user", recipient="parent", content="parent history"))
        child.history.append(AgentMessage(sender="user", recipient="child", content="child history"))

        self.assertIsNot(parent_tool, child_tool)
        parent_prompt, parent_history = parent_tool._context_getter()
        child_prompt, child_history = child_tool._context_getter()

        self.assertEqual(parent_prompt, "parent prompt")
        self.assertEqual(child_prompt, "child prompt")
        self.assertEqual(parent_history[0].content, "parent history")
        self.assertEqual(child_history[0].content, "child history")

    async def test_fork_clones_run_prompts_sequentially_binding(self) -> None:
        # @intent fork-keeps-parent-prompt-queue
        # The parent's run_prompts_sequentially tool must keep queuing on the parent after a fork.
        parent_tool = RunPromptsSequentiallyTool()
        parent = self._agent(tools=[parent_tool])
        child = parent.fork(AgentForkSettings(name="child"))
        child_tool = _tool_of_type(child, RunPromptsSequentiallyTool)

        self.assertIsNot(parent_tool, child_tool)
        await parent_tool.execute(_call("run_prompts_sequentially", prompts=["parent next"]))
        await child_tool.execute(_call("run_prompts_sequentially", prompts=["child next"]))

        self.assertEqual(parent._queued_prompts, ["parent next"])
        self.assertEqual(child._queued_prompts, ["child next"])

    async def test_customized_run_prompts_sequentially_is_bound(self) -> None:
        # @intent wrapped-builtin-binds-to-owner
        # A customize() view must not hide the wrapped builtin from the owning agent's binding.
        wrapped = RunPromptsSequentiallyTool().customize(description="Queue follow-up prompts (localized).")
        agent = self._agent(tools=[wrapped])

        result = await wrapped.execute(_call("run_prompts_sequentially", prompts=["next"]))

        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        self.assertEqual(agent._queued_prompts, ["next"])

    async def test_fork_clones_customized_bound_tool(self) -> None:
        # @intent fork-clones-wrapped-builtin
        # A fork must clone the tool inside a customize()/with_activity() view and bind the copy to the child.
        description = "Queue follow-up prompts (localized)."
        parent_tool = RunPromptsSequentiallyTool().customize(description=description).with_activity(
            ToolActivity(schema=_QueueActivity, description="Why you are queuing.")
        )
        parent = self._agent(tools=[parent_tool])
        child = parent.fork(AgentForkSettings(name="child"))
        child_tool = _tool_of_type(child, _ToolWrapper)

        self.assertIsNot(child_tool, parent_tool)
        self.assertIsNot(_unwrap_tool(child_tool), _unwrap_tool(parent_tool))
        self.assertEqual(child_tool.spec().description, description)
        self.assertEqual(child_tool.spec().activity, parent_tool.spec().activity)
        await _unwrap_tool(parent_tool).execute(_call("run_prompts_sequentially", prompts=["parent next"]))
        await _unwrap_tool(child_tool).execute(_call("run_prompts_sequentially", prompts=["child next"]))
        self.assertEqual(parent._queued_prompts, ["parent next"])
        self.assertEqual(child._queued_prompts, ["child next"])

    async def test_fork_clones_session_tool_binding_and_scope(self) -> None:
        # @intent fork-keeps-parent-session-tool-binding
        # After fork + child.persist(), the parent's session tool must stay on the parent's session and scope.
        store = InMemorySessionStore()
        parent_tool = CheckpointTool(store)
        parent = self._agent(tools=[parent_tool])
        parent_session = parent.persist(store=store)
        child = parent.fork(AgentForkSettings(name="child"))
        child_session = child.persist(store=store)
        child_tool = _tool_of_type(child, CheckpointTool)

        self.assertIsNot(parent_tool, child_tool)
        self.assertIsNot(parent_tool._scope, child_tool._scope)
        self.assertIs(parent_tool._session, parent_session)
        self.assertIs(child_tool._session, child_session)
        self.assertFalse(parent_tool._scope.permits(child_session.id))
        result = await parent_tool.execute(_call("checkpoint", label="parent"))
        self.assertEqual(store.get(result.output.strip()).session_id, parent_session.id)

    def test_fork_preserves_pending_mcp_configs(self) -> None:
        # Lazy MCP configs should be copied to child pending configs without live handles.
        parent = self._agent()
        parent.with_mcp_server(["lazyserver"], name="lazy")
        child = parent.fork(AgentForkSettings(name="child"))

        self.assertEqual(len(parent._pending_mcp_configs), 1)
        self.assertEqual(len(child._pending_mcp_configs), 1)
        self.assertEqual(child._pending_mcp_configs[0].command, ("lazyserver",))
        self.assertEqual(child.mcp_servers(), ())

    def test_fork_can_disable_mcp_inheritance(self) -> None:
        # inherit_mcp=False should leave child pending configs empty.
        parent = self._agent()
        parent.with_mcp_server(["lazyserver"], name="lazy")
        child = parent.fork(AgentForkSettings(name="child", inherit_mcp=False))

        self.assertEqual(len(parent._pending_mcp_configs), 1)
        self.assertEqual(child._pending_mcp_configs, [])

    @patch("vidbyte.tools.mcp.attach.McpStdioTransport", MockMcpStdioTransport)
    async def test_fork_replays_live_mcp_configs_without_sharing_handles(self) -> None:
        # A child should reconnect inherited MCP configs and own distinct handles/tools.
        MockMcpStdioTransport.instances.clear()
        parent = self._agent()
        await parent.attach_mcp_server(["server1"])
        parent_bridged_tool = parent.mcp_servers()[0].bridged_tools[0]
        child = parent.fork(AgentForkSettings(name="child"))

        self.assertEqual(child.mcp_servers(), ())
        self.assertNotIn(parent_bridged_tool, child._agent_tool_items)
        self.assertEqual(child._pending_mcp_configs[0].command, ("server1",))

        await child.generate_reply("task")

        self.assertEqual(len(parent.mcp_servers()), 1)
        self.assertEqual(len(child.mcp_servers()), 1)
        self.assertIsNot(parent.mcp_servers()[0], child.mcp_servers()[0])
        self.assertIsNot(parent.mcp_servers()[0].bridged_tools[0], child.mcp_servers()[0].bridged_tools[0])

    def test_fork_run_id_is_distinct_and_records_lineage(self) -> None:
        # Default fork run ids should differ from the parent and record lineage metadata.
        parent = self._agent(run_id="run-123")
        child = parent.fork(AgentForkSettings(name="child"))

        self.assertNotEqual(child.runner_config.run_id, parent.runner_config.run_id)
        self.assertTrue(str(child.runner_config.run_id).startswith("run-123:fork:"))
        self.assertEqual(child.metadata["fork_parent_agent_name"], "parent")
        self.assertEqual(child.metadata["fork_parent_run_id"], "run-123")
        self.assertEqual(child.metadata["fork_child_run_id"], child.runner_config.run_id)

    def test_fork_explicit_run_id_is_used(self) -> None:
        # Explicit child run ids should be preserved exactly.
        parent = self._agent(run_id="run-123")
        child = parent.fork(AgentForkSettings(name="child", run_id="child-run"))

        self.assertEqual(child.runner_config.run_id, "child-run")
        self.assertEqual(child.metadata["fork_child_run_id"], "child-run")

    def test_fork_max_iterations_override_inherits_remaining_parent_config(self) -> None:
        # A max_iterations delta must keep every other parent loop guardrail and the parent model-call timeout.
        tool_settings = ToolSettings(denied_tools={"delete_file"})
        error_policy = ToolErrorPolicy(max_retries_per_tool_call=1)
        contract = MinToolCalls(1)
        loop = AgentLoopSettings(max_iterations=10, max_queued_prompts=2, tool_settings=tool_settings, tool_error_policy=error_policy, output_contracts=[contract], max_contract_rejections=5)
        parent = build_test_agent(name="parent", system_prompt="Work.", runner=DoneRunner(), agent_loop_settings=loop, timeout_seconds=12.5)

        child = parent.fork(AgentForkSettings(max_iterations=3))
        child_loop = child.agent_loop_settings

        self.assertEqual(child_loop.max_iterations, 3)
        self.assertIs(child_loop.tool_settings, tool_settings)
        self.assertIs(child_loop.tool_error_policy, error_policy)
        self.assertEqual(child_loop.output_contracts, (contract,))
        self.assertEqual(child_loop.max_queued_prompts, 2)
        self.assertEqual(child_loop.max_contract_rejections, 5)
        self.assertEqual(child.runner_config.timeout_seconds, 12.5)
        self.assertEqual(parent.fork().runner_config.timeout_seconds, 12.5)

    def test_fork_trace_option_override_matches_docs(self) -> None:
        # fork(trace_option=...) should set the child continual trace option as documented.
        parent = self._agent()
        option = TraceOption.continual(ActionTrace)
        child = parent.fork(AgentForkSettings(name="child", trace_option=option))

        self.assertIs(child._trace_option, option)

    async def test_trace_attributes_include_run_id(self) -> None:
        # Root trace attributes should include the forked child run id.
        tracer = RecordingTracer()
        parent = self._agent(run_id="run-123", tracer=tracer)
        child = parent.fork(AgentForkSettings(name="child"))

        await child.generate_reply("task")

        self.assertEqual(tracer.started[0]["run_id"], child.runner_config.run_id)
        self.assertEqual(tracer.spans[0]["run_id"], child.runner_config.run_id)


if __name__ == "__main__":
    unittest.main()
