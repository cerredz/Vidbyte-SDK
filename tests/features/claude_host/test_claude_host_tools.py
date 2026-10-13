"""FILE: tests/features/claude_host/test_claude_host_tools.py

PURPOSE: Proves the model-facing side of the host: each of the 15 Claude tools has the spec's name, permission and closed input schema, turns a ClaudeOperationError into the INV-13 error result without raising, rejects wrong JSON types and treats null as omitted, renders success as JSON, and ClaudeTools bundles the tools in the section 9.2 order so the default PermissionPolicy runs READ tools and refuses WRITE tools.
ROLE IN CODEBASE: Tool layer of tests/features/claude_host/ (spec AC-12, AC-13, AC-26, AC-29, INV-13, INV-14, D-13, D-14, section 9.2 "Model-facing tools"). Exercises vidbyte/tools/builtins/claude/ and vidbyte/tools/toolsets/claude.py over a real ClaudeHost.
ARCHITECTURE NOTE: The tools run against a real host over the fake SDK. A closed host makes every star call and get_handle raise action.precondition_failed, which gives every tool the same ClaudeOperationError to translate. ToolExecutor, Tools, PermissionPolicy, ToolsFormatter and McpStudioServer run unmocked.
COMMON MODIFICATION PATTERNS: When a tool gains a parameter, update TOOL_TABLE (type and whether it is required) and valid_arguments. When the rendering of a record changes, update the matching JSON assertion in RenderingTests.
WHAT NOT TO DO IN THIS FILE: 1. Do not call execute through ToolExecutor for the wrong-type cases; the executor's own required-parameter check would answer first. 2. Do not compare a reason with exact text. 3. Do not import feature symbols at module level.
KNOWN EDGE CASES: check_claude_ready and list_claude_models construct a probe client, so tests that count clients count turn clients (those that sent a prompt) when READ tools ran. ToolsFormatter.input_schema returns the explicit input_schema when a spec sets one, otherwise the schema built from its parameters, so the assertions hold for either way of declaring it.
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 6.1 (INV-13, INV-14), 6.2 and 9.2.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_tools.py
"""

from __future__ import annotations

import json
import re
import unittest
import uuid
from pathlib import Path
from typing import Any

from vidbyte.lib.dataclasses.tools import ToolCall, ToolStatus

from tests.features.claude_host.claude_host_fixtures import (
    CLAUDE_NEXT_STEPS,
    DEFAULT_PROMPT,
    FAKE_CLI_PATH,
    FAKE_CLI_VERSION,
    HANG_GUARD_SECONDS,
    INVALID_ARGUMENT,
    INVALID_ARGUMENT_NEXT_STEP,
    PRECONDITION_FAILED,
    PRECONDITION_NEXT_STEP,
    SHORT_TIMEOUT_SECONDS,
    WORK_DIR,
    ClaudeHostCase,
    answer_for,
    eventually,
    init_message,
    result_message,
)

# Section 9.2 "Model-facing tools", in ClaudeTools order: class, tool name, permission, parameter JSON types, required names.
TOOL_TABLE: tuple[tuple[str, str, str, dict[str, str], frozenset[str]], ...] = (
    ("CheckClaudeReadyTool", "check_claude_ready", "read", {}, frozenset()),
    ("ListClaudeModelsTool", "list_claude_models", "read", {}, frozenset()),
    ("GetClaudeRateLimitsTool", "get_claude_rate_limits", "read", {}, frozenset()),
    ("SpawnClaudeSessionTool", "spawn_claude_session", "write", {"prompt": "string"}, frozenset({"prompt"})),
    ("ContinueClaudeSessionTool", "continue_claude_session", "write", {"session_id": "string", "prompt": "string"}, frozenset({"session_id", "prompt"})),
    ("ForkClaudeSessionTool", "fork_claude_session", "write", {"session_id": "string", "up_to_message_id": "string", "title": "string"}, frozenset({"session_id"})),
    ("LaunchClaudeSubagentsTool", "launch_claude_subagents", "write", {"prompts": "array", "limit": "integer"}, frozenset({"prompts", "limit"})),
    ("ListClaudeSessionsTool", "list_claude_sessions", "read", {"directory": "string", "limit": "integer", "offset": "integer", "include_worktrees": "boolean"}, frozenset()),
    ("GetClaudeSessionInfoTool", "get_claude_session_info", "read", {"session_id": "string"}, frozenset({"session_id"})),
    ("GetClaudeSessionMessagesTool", "get_claude_session_messages", "read", {"session_id": "string", "limit": "integer", "offset": "integer"}, frozenset({"session_id"})),
    ("WaitClaudeTurnTool", "wait_claude_turn", "read", {"handle_id": "string", "timeout_seconds": "number"}, frozenset({"handle_id", "timeout_seconds"})),
    ("GetClaudeTurnResultTool", "get_claude_turn_result", "read", {"handle_id": "string"}, frozenset({"handle_id"})),
    ("SteerClaudeSessionTool", "steer_claude_session", "write", {"handle_id": "string", "message": "string"}, frozenset({"handle_id", "message"})),
    ("InterruptClaudeTurnTool", "interrupt_claude_turn", "write", {"handle_id": "string"}, frozenset({"handle_id"})),
    ("TrackClaudeSessionUsageTool", "track_claude_session_usage", "read", {"handle_id": "string"}, frozenset({"handle_id"})),
)
TOOL_NAMES = tuple(row[1] for row in TOOL_TABLE)
ERROR_METADATA_TYPE = "ClaudeOperationError"


def valid_arguments(tool_name: str, handle_id: str, session_id: str) -> dict[str, Any]:
    """Return well-typed arguments for one tool, so only the host's own answer decides the result."""
    arguments: dict[str, dict[str, Any]] = {
        "spawn_claude_session": {"prompt": "Review src/ for bugs."},
        "continue_claude_session": {"session_id": session_id, "prompt": "Now fix the first bug."},
        "fork_claude_session": {"session_id": session_id},
        "launch_claude_subagents": {"prompts": ["Review src/ for bugs."], "limit": 1},
        "get_claude_session_info": {"session_id": session_id},
        "get_claude_session_messages": {"session_id": session_id},
        "wait_claude_turn": {"handle_id": handle_id, "timeout_seconds": 5},
        "get_claude_turn_result": {"handle_id": handle_id},
        "steer_claude_session": {"handle_id": handle_id, "message": "focus on tests"},
        "interrupt_claude_turn": {"handle_id": handle_id},
        "track_claude_session_usage": {"handle_id": handle_id},
    }
    return dict(arguments.get(tool_name, {}))


def error_output_pattern(code: str, next_step: str) -> re.Pattern[str]:
    """Match INV-13's "<code>: <reason> Next step: <next_step>" with a non-empty reason."""
    return re.compile(rf"{re.escape(code)}: (?P<reason>.+) Next step: {re.escape(next_step)}", re.DOTALL)


class ToolCase(ClaudeHostCase):
    """Adds helpers that build the toolset over a host and run one tool call."""

    def toolset(self, host: Any) -> dict[str, Any]:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
        from vidbyte.tools.toolsets.claude import ClaudeTools

        return {tool.spec().name: tool for tool in ClaudeTools(host, ClaudeSpawnRequest(cwd=WORK_DIR))}

    async def call(self, tool: Any, arguments: dict[str, Any]) -> Any:
        import asyncio

        return await asyncio.wait_for(tool.execute(ToolCall(tool_name=tool.spec().name, arguments=arguments)), HANG_GUARD_SECONDS)

    async def finished_turn(self, host: Any) -> Any:
        handle = await self.spawn(host)
        await self.finished(host, handle)
        self.fake.history.add_session(handle.session_id, cwd=WORK_DIR)
        return handle


class ToolContractTests(ToolCase):
    """AC-12, INV-13, INV-14 and D-14: name, permission, closed schema, and an error result instead of a raise."""

    async def test_every_tool_turns_a_host_error_into_an_error_result(self) -> None:
        import vidbyte.tools.builtins.claude as claude_builtins
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
        from vidbyte.lib.tools.formatter import ToolsFormatter

        host = await self.open_host()
        handle = await self.finished_turn(host)
        # A closed host raises action.precondition_failed from every star call and from get_handle.
        await self.close_host(host)
        request = ClaudeSpawnRequest(cwd=WORK_DIR)
        pattern = error_output_pattern(PRECONDITION_FAILED, PRECONDITION_NEXT_STEP)
        for class_name, tool_name, permission, parameters, required in TOOL_TABLE:
            with self.subTest(tool=tool_name):
                tool = getattr(claude_builtins, class_name)(host, request)
                spec = tool.spec()
                self.assertEqual(spec.name, tool_name)
                self.assertEqual(spec.permission.value, permission)
                self.assertTrue(spec.description.strip())
                # D-14 and section 12.3 row 16: the agent never binds a Session or itself to these tools.
                self.assertFalse(hasattr(tool, "bind_session"))
                self.assertFalse(hasattr(tool, "bind_agent"))
                schema = ToolsFormatter.input_schema(spec)
                self.assertEqual(schema.get("type"), "object")
                self.assertIs(schema.get("additionalProperties"), False)
                properties = schema.get("properties") or {}
                self.assertEqual(set(properties), set(parameters))
                for name, json_type in parameters.items():
                    self.assertEqual(properties[name].get("type"), json_type, name)
                if "items" in properties.get("prompts", {}):
                    self.assertEqual(properties["prompts"]["items"].get("type"), "string")
                self.assertEqual(set(schema.get("required") or ()), required)
                result = await self.call(tool, valid_arguments(tool_name, handle.handle_id, handle.session_id))
                self.assertIs(result.status, ToolStatus.ERROR)
                self.assertRegex(result.output, pattern)
                self.assertEqual(dict(result.metadata), {"error": PRECONDITION_FAILED, "error_type": ERROR_METADATA_TYPE})

    async def test_a_host_error_keeps_its_own_code_and_next_step(self) -> None:
        host = await self.open_host()
        tools = self.toolset(host)
        unknown = str(uuid.uuid4())
        result = await self.call(tools["get_claude_session_info"], {"session_id": unknown})
        self.assertIs(result.status, ToolStatus.ERROR)
        self.assertRegex(result.output, error_output_pattern("claude.session_not_found", CLAUDE_NEXT_STEPS["claude.session_not_found"]))
        self.assertEqual(dict(result.metadata), {"error": "claude.session_not_found", "error_type": ERROR_METADATA_TYPE})
        # EC-48: a handle id this host never issued.
        result = await self.call(tools["get_claude_turn_result"], {"handle_id": str(uuid.uuid4())})
        self.assertEqual(dict(result.metadata), {"error": "claude.session_not_found", "error_type": ERROR_METADATA_TYPE})


class ToolsetTests(ToolCase):
    """AC-13 and INV-14: ClaudeTools holds the 15 tools in order; the default policy runs READ and refuses WRITE."""

    async def test_the_toolset_holds_the_fifteen_tools_in_order(self) -> None:
        from vidbyte.tools.catalog import Tools
        from vidbyte.tools.toolsets.claude import ClaudeTools

        host = await self.open_host()
        for label, toolset in (("with a request", ClaudeTools(host, None)), ("without a request", ClaudeTools(host))):
            with self.subTest(toolset=label):
                self.assertIsInstance(toolset, Tools)
                self.assertEqual(tuple(toolset.names()), TOOL_NAMES)

    async def test_the_default_policy_runs_read_tools_and_refuses_write_tools(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
        from vidbyte.tools.executor import ToolExecutor
        from vidbyte.tools.toolsets.claude import ClaudeTools

        host = await self.open_host()
        handle = await self.finished_turn(host)
        executor = ToolExecutor(ClaudeTools(host, ClaudeSpawnRequest(cwd=WORK_DIR)))
        turn_clients_before = len(self.fake.turn_clients())
        for _, tool_name, permission, _, _ in TOOL_TABLE:
            with self.subTest(tool=tool_name):
                result = await executor.execute_call(ToolCall(tool_name=tool_name, arguments=valid_arguments(tool_name, handle.handle_id, handle.session_id)))
                if permission == "write":
                    self.assertIs(result.status, ToolStatus.ERROR)
                    self.assertEqual(dict(result.metadata), {"error": "permission_denied", "permission": "write"})
                else:
                    self.assertIs(result.status, ToolStatus.SUCCESS, result.output)
        # No refused WRITE tool reached the host: no new turn, no fork, no interrupt.
        self.assertEqual(len(self.fake.turn_clients()), turn_clients_before)
        self.assertEqual(self.fake.history.calls_to("fork_session"), [])
        self.assertEqual(sum(client.interrupt_calls for client in self.fake.clients), 0)


class ArgumentTypeTests(ToolCase):
    """AC-26 and D-13: a wrong JSON type is configuration.invalid_argument and starts nothing; JSON null means omitted."""

    async def test_wrong_json_types_are_invalid_arguments_and_start_nothing(self) -> None:
        host = await self.open_host()
        handle = await self.finished_turn(host)
        tools = self.toolset(host)
        clients_before = len(self.fake.clients)
        history_before = len(self.fake.history.calls)
        cases = (
            ("launch_claude_subagents", {"prompts": ["Review src/."], "limit": "2"}, "limit"),
            ("launch_claude_subagents", {"prompts": ["Review src/."], "limit": True}, "limit"),
            ("launch_claude_subagents", {"prompts": "Review src/.", "limit": 1}, "prompts"),
            ("launch_claude_subagents", {"prompts": ["Review src/.", 7], "limit": 1}, "prompts"),
            ("wait_claude_turn", {"handle_id": 12345, "timeout_seconds": 5}, "handle_id"),
            ("wait_claude_turn", {"handle_id": handle.handle_id, "timeout_seconds": "5"}, "timeout_seconds"),
            ("get_claude_turn_result", {"handle_id": ["not", "an", "id"]}, "handle_id"),
            ("track_claude_session_usage", {"handle_id": True}, "handle_id"),
            ("list_claude_sessions", {"limit": "2"}, "limit"),
            ("list_claude_sessions", {"include_worktrees": "false"}, "include_worktrees"),
            ("get_claude_session_messages", {"session_id": handle.session_id, "offset": 1.5}, "offset"),
            ("spawn_claude_session", {"prompt": 42}, "prompt"),
            ("continue_claude_session", {"session_id": 42, "prompt": "Now fix it."}, "session_id"),
            ("steer_claude_session", {"handle_id": handle.handle_id, "message": ["focus"]}, "message"),
        )
        pattern = error_output_pattern(INVALID_ARGUMENT, INVALID_ARGUMENT_NEXT_STEP)
        for tool_name, arguments, argument in cases:
            with self.subTest(tool=tool_name, arguments=arguments):
                result = await self.call(tools[tool_name], arguments)
                self.assertIs(result.status, ToolStatus.ERROR)
                self.assertEqual(dict(result.metadata), {"error": INVALID_ARGUMENT, "error_type": ERROR_METADATA_TYPE})
                match = pattern.fullmatch(result.output)
                self.assertIsNotNone(match, result.output)
                self.assertIn(argument, match.group("reason"))
        self.assertEqual(len(self.fake.clients), clients_before)
        self.assertEqual(len(self.fake.history.calls), history_before)

    async def test_json_null_means_the_argument_was_omitted(self) -> None:
        host = await self.open_host()
        handle = await self.finished_turn(host)
        tools = self.toolset(host)
        session = handle.session_id
        cases = (
            ("list_claude_sessions", {"directory": None, "limit": None, "offset": None, "include_worktrees": None}, "list_sessions", {"directory": None, "limit": None, "offset": 0, "include_worktrees": True}),
            ("get_claude_session_messages", {"session_id": session, "limit": None, "offset": None}, "get_session_messages", {"session_id": session, "limit": None, "offset": 0}),
            ("fork_claude_session", {"session_id": session, "up_to_message_id": None, "title": None}, "fork_session", {"session_id": session, "up_to_message_id": None, "title": None}),
        )
        for tool_name, arguments, function, expected in cases:
            with self.subTest(tool=tool_name):
                result = await self.call(tools[tool_name], arguments)
                self.assertIs(result.status, ToolStatus.SUCCESS, result.output)
                recorded = self.fake.history.calls_to(function)[-1].arguments
                self.assertEqual({key: recorded[key] for key in expected}, expected)


class McpListingTests(ToolCase):
    """AC-29: McpStudioServer lists the 15 Claude tools without any client connection."""

    async def test_mcp_studio_server_lists_the_fifteen_tools(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
        from vidbyte.mcp_server import McpStudioServer
        from vidbyte.tools.toolsets.claude import ClaudeTools

        host = await self.open_host()
        server = McpStudioServer(tools=ClaudeTools(host, ClaudeSpawnRequest(cwd=WORK_DIR)))
        response = await server._dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        listed = {tool["name"]: tool for tool in response["result"]["tools"]}
        self.assertTrue(set(TOOL_NAMES) <= set(listed), sorted(set(TOOL_NAMES) - set(listed)))
        self.assertEqual(self.fake.clients, [])


class RenderingTests(ToolCase):
    """Section 9.2 "How the tools respond": success is the JSON of the record, with enums as their values."""

    async def test_turn_tools_render_handles_results_and_usage(self) -> None:
        host = await self.open_host()
        tools = self.toolset(host)
        spawned = await self.call(tools["spawn_claude_session"], {"prompt": DEFAULT_PROMPT})
        self.assertIs(spawned.status, ToolStatus.SUCCESS, spawned.output)
        handle_json = json.loads(spawned.output)
        self.assertEqual(set(handle_json), {"handle_id", "session_id"})
        waited = await self.call(tools["wait_claude_turn"], {"handle_id": handle_json["handle_id"], "timeout_seconds": HANG_GUARD_SECONDS})
        result_json = json.loads(waited.output)
        self.assertEqual((result_json["handle_id"], result_json["session_id"]), (handle_json["handle_id"], handle_json["session_id"]))
        self.assertEqual((result_json["status"], result_json["result_text"], result_json["failure"]), ("completed", answer_for(DEFAULT_PROMPT), None))
        self.assertEqual((result_json["total_cost_usd"], result_json["duration_ms"], result_json["permission_denials"]), (0.0123, 4200, []))
        got = await self.call(tools["get_claude_turn_result"], {"handle_id": handle_json["handle_id"]})
        self.assertEqual(json.loads(got.output), result_json)
        usage = json.loads((await self.call(tools["track_claude_session_usage"], {"handle_id": handle_json["handle_id"]})).output)
        self.assertEqual(usage["total_cost_usd"], 0.0123)
        self.assertEqual([model["model"] for model in usage["models"]], ["claude-sonnet-4-5"])
        self.assertEqual(usage["tasks"], [])
        launched = json.loads((await self.call(tools["launch_claude_subagents"], {"prompts": ["Review src/.", "Review tests/."], "limit": 2})).output)
        self.assertEqual([set(item) for item in launched], [{"handle_id", "session_id"}] * 2)

    async def test_a_failed_turn_renders_its_failure(self) -> None:
        self.fake.reply(DEFAULT_PROMPT, init_message(), result_message(result=None, subtype="error_max_turns", is_error=True, terminal_reason="max_turns", stop_reason=None))
        host = await self.open_host()
        tools = self.toolset(host)
        handle_json = json.loads((await self.call(tools["spawn_claude_session"], {"prompt": DEFAULT_PROMPT})).output)
        result_json = json.loads((await self.call(tools["wait_claude_turn"], {"handle_id": handle_json["handle_id"], "timeout_seconds": HANG_GUARD_SECONDS})).output)
        self.assertEqual(result_json["status"], "failed")
        self.assertEqual(result_json["failure"]["code"], "claude.budget_exhausted")
        self.assertEqual(result_json["failure"]["next_step"], CLAUDE_NEXT_STEPS["claude.budget_exhausted"])
        self.assertTrue(result_json["failure"]["reason"])

    async def test_steer_fork_and_readiness_tools_render_their_shapes(self) -> None:
        self.fake.hold(DEFAULT_PROMPT)
        host = await self.open_host()
        tools = self.toolset(host)
        handle_json = json.loads((await self.call(tools["spawn_claude_session"], {"prompt": DEFAULT_PROMPT})).output)
        await eventually(lambda: bool(self.fake.turn_clients()), "the prompt was sent")
        steered = await self.call(tools["steer_claude_session"], {"handle_id": handle_json["handle_id"], "message": "focus on tests"})
        self.assertEqual(json.loads(steered.output), {"steered": True})
        final = json.loads((await self.call(tools["wait_claude_turn"], {"handle_id": handle_json["handle_id"], "timeout_seconds": HANG_GUARD_SECONDS})).output)
        self.assertEqual((final["status"], final["result_text"]), ("completed", answer_for("focus on tests")))
        session = self.fake.history.add_session()
        forked = json.loads((await self.call(tools["fork_claude_session"], {"session_id": session})).output)
        self.assertEqual(forked, {"session_id": self.fake.history.forks[-1]})
        readiness = json.loads((await self.call(tools["check_claude_ready"], {})).output)
        self.assertEqual(Path(readiness.pop("cli_path")), Path(FAKE_CLI_PATH))
        self.assertEqual(readiness, {"cli_version": FAKE_CLI_VERSION, "signed_in": True, "failure": None})
        self.assertEqual(json.loads((await self.call(tools["get_claude_rate_limits"], {})).output), [])
        models = json.loads((await self.call(tools["list_claude_models"], {})).output)
        self.assertEqual([model["value"] for model in models], ["default", "sonnet"])
        self.assertEqual(models[0]["supported_effort_levels"], ["low", "medium", "high"])
        interrupted = json.loads((await self.call(tools["interrupt_claude_turn"], {"handle_id": handle_json["handle_id"]})).output)
        self.assertEqual(interrupted["status"], "completed")
        listed = json.loads((await self.call(tools["list_claude_sessions"], {})).output)
        self.assertEqual([item["session_id"] for item in listed], [session])
        waited = json.loads((await self.call(tools["wait_claude_turn"], {"handle_id": handle_json["handle_id"], "timeout_seconds": SHORT_TIMEOUT_SECONDS})).output)
        self.assertEqual(waited["status"], "completed")


if __name__ == "__main__":
    unittest.main()
