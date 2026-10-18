"""FILE: tests/features/codex_host/test_codex_host_mcp_memory.py

PURPOSE: Proves list_codex_mcp_servers and the three memory functions over the in-memory app-server: one mcpServerStatus/list page mapped to CodexMcpServer records with an absent runtimeStatus read as NOT_REPORTED, its filters on the wire, Codex's refusal of an unknown thread, and its stability without the experimental API; set_codex_thread_memory_mode loading a thread whose goal is safe and refusing one whose goal is active, get_codex_memory_status's optional minimum and its range, and reset_codex_memories sending memory/reset alone.
ROLE IN CODEBASE: MCP and memory layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md AC-19, AC-21, INV-9, INV-24, INV-26, EC-26 to EC-29, T-8). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: A real CodexHost talks to FakeAppServer through FeatureHostCase; the MCP answers are built with codex_host_feature_fakes.mcp_server from the 0.163.0 McpServerStatus member names, so the SDK's ListMcpServerStatusResponse model validates them before the host's translator reads them. The fake records a request sent without params as {}, which is how memory/reset's None params show.
COMMON MODIFICATION PATTERNS: Add a status row to the EC-27 table when Codex adds an McpServerConnectionStatus or McpAuthStatus value and CodexMcp*Status gains its member.
KNOWN EDGE CASES: list_codex_mcp_servers sends no thread/read, because its thread filter is optional (EC-26), so an unknown thread is Codex's own -32600. The memory functions are experimental; their gate is proved in test_codex_host_feature_contract.py.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 6.1, 6.2, 6.3, 9.1 and 9.2.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_mcp_memory.py
"""

from __future__ import annotations

import unittest
from typing import Any

from tests.features.codex_host.codex_host_feature_fakes import mcp_server
from tests.features.codex_host.codex_host_feature_support import (
    LOAD_GOAL_UNFINISHED_CAUSE,
    LOAD_GOAL_UNFINISHED_MESSAGE,
    LOAD_GOAL_UNFINISHED_NEXT_STEP,
    assert_packet,
)
from tests.features.codex_host.codex_host_support import HOST_LOGGER, FeatureHostCase, assert_no_canary, mapped_summary, requires_sdk, thread_suffix

MEMORY_MODE = "set_codex_thread_memory_mode"
MCP = "list_codex_mcp_servers"
RPC_ERROR_TEXT = "Codex answered {method} with JSON-RPC error {code}: '{message}'."
MISMATCH_TEXT = "Codex's answer to {method} did not match the openai-codex response model."
MCP_ERROR_CANARY = "mcp-error-canary-5f0a"


def _server(name: str, **fields: Any) -> Any:
    from vidbyte.lib.dataclasses.codex_host_features import CodexMcpServer

    return CodexMcpServer(name=name, **fields)


@requires_sdk
class CodexMcpServerHostTests(FeatureHostCase):
    """AC-19, INV-9, INV-24, EC-26, EC-27 and T-8."""

    async def test_one_server_page_maps_its_tools_resources_and_statuses(self) -> None:
        # AC-19: two tools, one resource, oAuth, and no runtimeStatus, which is NOT_REPORTED.
        from vidbyte.lib.dataclasses.codex_host_features import CodexMcpServerPage
        from vidbyte.lib.enums.codex import CodexMcpAuthStatus, CodexMcpConnectionStatus

        self.server.mcp_servers = [mcp_server("docs", tools=("search", "fetch"), resources=1, auth="oAuth")]
        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        page = await self.call(host.list_codex_mcp_servers(thread_id=thread.thread_id))
        expected = _server("docs", auth_status=CodexMcpAuthStatus.OAUTH, connection_status=CodexMcpConnectionStatus.NOT_REPORTED, tool_names=("fetch", "search"), resource_count=1, resource_template_count=0)
        self.assertEqual(page, CodexMcpServerPage(servers=(expected,), next_cursor=""))
        self.assertIs(page.servers[0].auth_status, CodexMcpAuthStatus.OAUTH)
        self.assertIs(page.servers[0].connection_status, CodexMcpConnectionStatus.NOT_REPORTED)
        self.assertEqual([(request.method, request.params) for request in self.sent()], [("mcpServerStatus/list", {"threadId": thread.thread_id, "detail": "full"})])

    async def test_the_listing_works_on_a_host_without_the_experimental_api(self) -> None:
        # AC-19, INV-4: the MCP listing is stable and never gated.
        from vidbyte.lib.dataclasses.codex import CodexClientSettings

        self.server.mcp_servers = [mcp_server("docs")]
        host = await self.opened(CodexClientSettings(experimental_api=False))
        page = await self.call(host.list_codex_mcp_servers())
        self.assertEqual([server.name for server in page.servers], ["docs"])
        self.assertEqual([(request.method, request.params) for request in self.sent()], [("mcpServerStatus/list", {"detail": "full"})])

    async def test_every_filter_and_page_field_reaches_the_wire_and_the_optional_members_map(self) -> None:
        # INV-24 and section 9.2 "Wire params": {detail, threadId?, serverName?, cursor?, limit?}; Codex's nulls become "".
        from vidbyte.lib.enums.codex import CodexMcpAuthStatus, CodexMcpConnectionStatus, CodexMcpServerDetail

        self.server.mcp_servers = [
            mcp_server("docs", tools=("search",), resources=0, templates=2, auth="bearerToken", runtime="connected", pluginId="docs-plugin", httpOrigin="https://docs.example.invalid", toolsError="one tool failed", serverInfo={"name": "docs", "version": "1.4.2"}),
            mcp_server("other"),
        ]
        self.server.mcp_next_cursor = "cursor-3"
        host = await self.opened()
        page = await self.call(host.list_codex_mcp_servers(server_name="docs", detail=CodexMcpServerDetail.TOOLS_AND_AUTH_ONLY, cursor="cursor-2", limit=5))
        self.assertEqual(self.sent()[0].params, {"detail": "toolsAndAuthOnly", "serverName": "docs", "cursor": "cursor-2", "limit": 5})
        self.assertEqual(page.next_cursor, "cursor-3")
        expected = _server(
            "docs",
            # docs/spec/codex-host-first-class/spec.md section 13 (r5), D-40: BEARER, not BEARER_TOKEN, with the same wire value.
            auth_status=CodexMcpAuthStatus.BEARER,
            connection_status=CodexMcpConnectionStatus.CONNECTED,
            tool_names=("search",),
            resource_count=0,
            resource_template_count=2,
            plugin_id="docs-plugin",
            http_origin="https://docs.example.invalid",
            tools_error="one tool failed",
            version="1.4.2",
        )
        self.assertEqual(page.servers, (expected,))

    async def test_a_servers_error_text_is_returned_to_the_caller_but_reaches_no_log_record(self) -> None:
        # INV-9, T-8: an MCP server's error text is the caller's to read and never logged; the listing calls no MCP tool.
        records = self.capture_logs(HOST_LOGGER)
        self.server.mcp_servers = [mcp_server("docs", runtime="failed", toolsError=f"tools/list failed: {MCP_ERROR_CANARY}")]
        host = await self.opened()
        page = await self.call(host.list_codex_mcp_servers())
        self.assertEqual(page.servers[0].tools_error, f"tools/list failed: {MCP_ERROR_CANARY}")
        self.assertEqual(self.sent_methods(), ["mcpServerStatus/list"])
        self.assertTrue(records)
        assert_no_canary(self, [record.getMessage() for record in records], (MCP_ERROR_CANARY,))

    async def test_an_unknown_thread_filter_is_codexs_own_refusal_with_no_read_first(self) -> None:
        # EC-26: the filter is optional, so there is no exists-check read; Codex's -32600 is codex.api_error.
        host = await self.opened()
        error = await self.codex_error(host.list_codex_mcp_servers(thread_id="thr-never"), "codex.api_error")
        self.assertEqual(error.operation, MCP)
        self.assertIn(RPC_ERROR_TEXT.format(method="mcpServerStatus/list", code=-32600, message="thread not found: thr-never"), error.message)
        self.assertEqual(self.sent_methods(), ["mcpServerStatus/list"])

    async def test_servers_waiting_to_start_or_for_sign_in_report_their_statuses(self) -> None:
        # EC-27, A-6: Codex reports the connection and auth status; nothing is refused.
        from vidbyte.lib.enums.codex import CodexMcpAuthStatus, CodexMcpConnectionStatus

        rows = (
            ("authenticationRequired", "notLoggedIn", CodexMcpConnectionStatus.AUTHENTICATION_REQUIRED, CodexMcpAuthStatus.NOT_LOGGED_IN),
            ("starting", "unsupported", CodexMcpConnectionStatus.STARTING, CodexMcpAuthStatus.UNSUPPORTED),
            ("failed", "unknown", CodexMcpConnectionStatus.FAILED, CodexMcpAuthStatus.UNKNOWN),
            ("notStarted", "oAuth", CodexMcpConnectionStatus.NOT_STARTED, CodexMcpAuthStatus.OAUTH),
            ("cancelled", "oAuth", CodexMcpConnectionStatus.CANCELLED, CodexMcpAuthStatus.OAUTH),
            ("disabled", "oAuth", CodexMcpConnectionStatus.DISABLED, CodexMcpAuthStatus.OAUTH),
        )
        self.server.mcp_servers = [mcp_server(f"server-{index}", runtime=runtime, auth=auth) for index, (runtime, auth, _, _) in enumerate(rows)]
        host = await self.opened()
        page = await self.call(host.list_codex_mcp_servers())
        self.assertEqual([(server.connection_status, server.auth_status) for server in page.servers], [(connection, auth) for _, _, connection, auth in rows])

    async def test_a_server_answer_the_sdk_model_rejects_is_a_protocol_mismatch(self) -> None:
        # INV-2, INV-6: the modeled answer fails validation inside the call, naming the method.
        self.server.feature_answers["mcpServerStatus/list"] = {"data": [{"name": "docs"}], "nextCursor": None}
        host = await self.opened()
        error = await self.codex_error(host.list_codex_mcp_servers(), "codex.protocol_mismatch")
        self.assertEqual(error.operation, MCP)
        self.assertEqual(mapped_summary(self, error), MISMATCH_TEXT.format(method="mcpServerStatus/list"))


@requires_sdk
class CodexMemoryHostTests(FeatureHostCase):
    """AC-21, INV-26, EC-28 and EC-29."""

    async def test_a_paused_goal_thread_is_loaded_then_its_memory_set_then_status_and_reset_are_sent(self) -> None:
        # AC-21: the paused goal is not refused and stays paused; reset sends no params.
        from vidbyte.lib.dataclasses.codex_host_features import CodexMemoryStatus
        from vidbyte.lib.enums.codex import CodexMemoryMode

        thread = self.server.seed_thread(completed_turns=1)
        thread.status = "notLoaded"
        thread.goal = self.fakes.goal_record(thread.thread_id, "Ship the fix.", "paused")
        host = await self.opened()
        self.assertIsNone(await self.call(host.set_codex_thread_memory_mode(thread.thread_id, CodexMemoryMode.DISABLED)))
        status = await self.call(host.get_codex_memory_status(5))
        self.assertIsNone(await self.call(host.reset_codex_memories()))
        self.assertEqual(
            [(request.method, request.params) for request in self.sent()],
            [
                # openai-codex's thread_read always sends includeTurns, false unless asked (client.py:498-503).
                ("thread/read", {"threadId": thread.thread_id, "includeTurns": False}),
                ("thread/goal/get", {"threadId": thread.thread_id}),
                ("thread/resume", self.server.matching("thread/resume")[-1].params),
                ("thread/memoryMode/set", {"threadId": thread.thread_id, "mode": "disabled"}),
                ("memory/status", {"minConsolidatedThreads": 5}),
                ("memory/reset", {}),
            ],
        )
        self.assertEqual(self.server.matching("thread/resume")[-1].params.get("threadId"), thread.thread_id)
        self.assertEqual(thread.goal["status"], "paused")
        self.assertEqual(self.server.memory_modes[thread.thread_id], "disabled")
        self.assertEqual(status, CodexMemoryStatus(consolidated_threads=3, ready=True))

    async def test_a_loaded_thread_is_not_loaded_again_and_an_unknown_one_stops_at_its_read(self) -> None:
        # INV-26: the exists check, then the load only for a notLoaded thread.
        from vidbyte.lib.enums.codex import CodexMemoryMode

        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        await self.call(host.set_codex_thread_memory_mode(thread.thread_id, CodexMemoryMode.ENABLED))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/memoryMode/set"])
        self.assertEqual(self.server.memory_modes[thread.thread_id], "enabled")
        self.remark()
        error = await self.codex_error(host.set_codex_thread_memory_mode("thr-never", CodexMemoryMode.ENABLED), "codex.session_not_found")
        self.assertEqual(error.operation, MEMORY_MODE)
        self.assertEqual(self.sent_methods(), ["thread/read"])

    async def test_a_not_loaded_thread_with_an_active_goal_is_refused_before_any_resume(self) -> None:
        # EC-29, INV-26: the load guard of INV-12, whose next step (pause or clear the goal) clears the refusal.
        from vidbyte.lib.enums.codex import CodexMemoryMode

        thread = self.server.seed_thread(completed_turns=1)
        thread.status = "notLoaded"
        thread.goal = self.fakes.goal_record(thread.thread_id, "Ship the fix.", "active")
        host = await self.opened()
        error = await self.codex_error(host.set_codex_thread_memory_mode(thread.thread_id, CodexMemoryMode.DISABLED), "codex.goal_unfinished")
        assert_packet(
            self,
            error,
            operation=MEMORY_MODE,
            code="codex.goal_unfinished",
            message=LOAD_GOAL_UNFINISHED_MESSAGE.format(status="active", operation=MEMORY_MODE),
            cause=LOAD_GOAL_UNFINISHED_CAUSE.format(operation=MEMORY_MODE),
            next_step=LOAD_GOAL_UNFINISHED_NEXT_STEP,
            thread_id=thread.thread_id,
        )
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get"])
        self.assertNotIn(thread.thread_id, self.server.memory_modes)

    async def test_the_status_minimum_is_optional_and_bounded_by_the_schema_range(self) -> None:
        # EC-28, INV-26: no minimum sends no member; 1 and 4096 are sent; 0 and 5000 are refused naming the field.
        host = await self.opened()
        await self.call(host.get_codex_memory_status())
        for minimum in (1, 4096):
            await self.call(host.get_codex_memory_status(minimum))
        self.assertEqual([request.params for request in self.sent()], [{}, {"minConsolidatedThreads": 1}, {"minConsolidatedThreads": 4096}])
        for minimum in (0, 5000, -1):
            with self.subTest(minimum=minimum):
                await self.refused_locally(host.get_codex_memory_status(minimum), "min_consolidated_threads")

    async def test_a_memory_status_codex_reports_as_not_ready_is_returned_as_is(self) -> None:
        # INV-26: the status is Codex's own, mapped to CodexMemoryStatus.
        from vidbyte.lib.dataclasses.codex_host_features import CodexMemoryStatus

        self.server.memory_status = {"v2ConsolidatedThreads": 0, "v2Ready": False}
        host = await self.opened()
        self.assertEqual(await self.call(host.get_codex_memory_status()), CodexMemoryStatus(consolidated_threads=0, ready=False))

    async def test_codex_refusing_the_memory_mode_names_the_thread(self) -> None:
        # INV-2: a refused set is codex.api_error with Codex's message and the thread's id.
        from vidbyte.lib.enums.codex import CodexMemoryMode

        thread = self.server.seed_thread(completed_turns=1)
        self.server.fail("thread/memoryMode/set", self.fakes.FakeRpcError(-32600, "memories are off for this account"))
        host = await self.opened()
        error = await self.codex_error(host.set_codex_thread_memory_mode(thread.thread_id, CodexMemoryMode.ENABLED), "codex.api_error")
        expected = RPC_ERROR_TEXT.format(method="thread/memoryMode/set", code=-32600, message="memories are off for this account")
        self.assertEqual(mapped_summary(self, error), expected + thread_suffix(thread.thread_id))


if __name__ == "__main__":
    unittest.main()
