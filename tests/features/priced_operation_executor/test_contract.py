"""FILE: tests/features/priced_operation_executor/test_contract.py

PURPOSE:
    Proves applications can execute real provider operations through SDK-priced
    tools without subclassing them or controlling their billing identity.
ROLE IN CODEBASE:
    Exercises operation tools through their public constructor and execute
    contract; provider networking remains outside this feature boundary.
ARCHITECTURE NOTE:
    These are contract and regression tests for the application-to-SDK seam
    introduced for cerredz/Vidbyte#284.
FUNCTION INVENTORY:
    PricedOperationExecutorTests: verifies success, error, exception, unit, and
    backward-compatibility behavior for injected operation executors.
COMMON MODIFICATION PATTERNS:
    Add a case when the executor or operation-usage contract gains a new public
    state; assert observable ToolResult behavior rather than private helpers.
WHAT NOT TO DO IN THIS FILE:
    1. Do not call real provider APIs.
    2. Do not assert private helper call order.
KNOWN EDGE CASES:
    Executor metadata may contain a spoofed operation_usage block and executor
    exceptions may contain secrets; both must be neutralized.
RELATED DOCS:
    tests/features/priced_operation_executor/FEATURE.md
TESTS:
    Run with python -m pytest tests/features/priced_operation_executor.
"""

from __future__ import annotations

import unittest

from vidbyte.tools.builtins.operations import BraveSearchTool, FirecrawlFetchTool
from vidbyte.tools.types import ToolCall, ToolResult, ToolStatus


class PricedOperationExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_brave_executor_result_keeps_safe_metadata_and_sdk_usage(self) -> None:
        observed: list[ToolCall] = []

        async def execute(call: ToolCall) -> ToolResult:
            observed.append(call)
            return ToolResult.success(
                "application_search",
                "provider payload",
                metadata={
                    "provider_request_id": "req_123",
                    "operation_usage": {"provider": "spoofed"},
                },
            )

        tool = BraveSearchTool(executor=execute)
        call = ToolCall("brave_search", {"query": "typed boundaries", "count": 7})

        result = await tool.execute(call)

        self.assertEqual(observed, [call])
        self.assertEqual(result.tool_name, "brave_search")
        self.assertEqual(result.output, "provider payload")
        self.assertEqual(result.metadata["provider_request_id"], "req_123")
        self.assertEqual(
            result.metadata["operation_usage"],
            {
                "operation": "search",
                "provider": "brave",
                "mode": "default",
                "units": 1,
            },
        )

    async def test_executor_error_is_priced_as_an_attempt(self) -> None:
        async def execute(call: ToolCall) -> ToolResult:
            return ToolResult.error(
                call.tool_name,
                "provider unavailable",
                metadata={"error": "provider_unavailable"},
            )

        result = await BraveSearchTool(executor=execute).execute(
            ToolCall("brave_search", {"query": "retry policy"}),
        )

        self.assertIs(result.status, ToolStatus.ERROR)
        self.assertEqual(result.metadata["error"], "provider_unavailable")
        self.assertEqual(result.metadata["operation_usage"]["provider"], "brave")

    async def test_executor_exception_is_redacted_and_priced(self) -> None:
        async def execute(call: ToolCall) -> ToolResult:
            del call
            raise RuntimeError("secret-provider-token")

        result = await BraveSearchTool(executor=execute).execute(
            ToolCall("brave_search", {"query": "redaction"}),
        )

        self.assertIs(result.status, ToolStatus.ERROR)
        self.assertNotIn("secret-provider-token", result.output)
        self.assertEqual(result.metadata["error"], "operation_executor_error")
        self.assertEqual(result.metadata["error_type"], "RuntimeError")
        self.assertEqual(result.metadata["operation_usage"]["units"], 1)

    async def test_firecrawl_executor_uses_requested_url_count(self) -> None:
        async def execute(call: ToolCall) -> ToolResult:
            return ToolResult.success(call.tool_name, "two documents")

        result = await FirecrawlFetchTool(executor=execute).execute(
            ToolCall("firecrawl_fetch", {"urls": ["https://a.test", "https://b.test"]}),
        )

        self.assertEqual(result.metadata["operation_usage"]["units"], 2)
        self.assertEqual(result.metadata["operation_usage"]["mode"], "scrape")

    async def test_tool_without_executor_keeps_contract_result(self) -> None:
        result = await BraveSearchTool().execute(
            ToolCall("brave_search", {"query": "backward compatibility"}),
        )

        self.assertEqual(result.output, "brave search: backward compatibility")
        self.assertEqual(result.metadata["operation_usage"]["provider"], "brave")


if __name__ == "__main__":
    unittest.main()
