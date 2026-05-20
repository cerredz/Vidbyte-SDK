from __future__ import annotations

import unittest

from vidbyte import vidbyte_tool
from vidbyte.tools import ToolCall, ToolRegistry, ToolStatus


class CustomFunctionToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_decorated_function_generates_schema_and_executes(self) -> None:
        @vidbyte_tool
        async def fetch_user_metrics(user_id: int, metric_type: str = "engagement") -> str:
            """Fetches real-time performance metrics for a specific user ID."""
            return f"{metric_type}:{user_id}"

        spec = fetch_user_metrics.spec()

        self.assertEqual(spec.name, "fetch_user_metrics")
        self.assertIn("Fetches real-time", spec.description)
        self.assertIn("user_id", spec.input_schema["properties"])
        self.assertEqual(spec.input_schema["required"], ["user_id"])

        result = await fetch_user_metrics.execute(
            ToolCall("fetch_user_metrics", {"user_id": "42"})
        )

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.output, "engagement:42")

    async def test_sync_function_result_is_json_serialized_when_possible(self) -> None:
        @vidbyte_tool(name="lookup")
        def lookup_user(user_id: int) -> dict[str, int]:
            """Looks up a user."""
            return {"user_id": user_id}

        result = await lookup_user.execute(ToolCall("lookup", {"user_id": 7}))

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.output, '{"user_id": 7}')

    async def test_validation_error_prevents_function_invocation(self) -> None:
        calls: list[int] = []

        @vidbyte_tool
        def double(value: int) -> int:
            calls.append(value)
            return value * 2

        result = await double.execute(ToolCall("double", {"value": "not-an-int"}))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("value", result.output)
        self.assertEqual(calls, [])

    def test_bad_varargs_signature_is_rejected(self) -> None:
        with self.assertRaises(TypeError):

            @vidbyte_tool
            def invalid(*args: str) -> str:
                return ",".join(args)

    async def test_registry_accepts_raw_and_decorated_functions(self) -> None:
        @vidbyte_tool
        def decorated(name: str) -> str:
            """Decorated greeting."""
            return f"hello {name}"

        def raw(value: int) -> int:
            """Raw increment."""
            return value + 1

        registry = ToolRegistry(tools=[decorated, raw])

        self.assertIsNotNone(registry.get("decorated"))
        self.assertIsNotNone(registry.get("raw"))
        self.assertIn("Decorated greeting", registry.specs_as_prompt_str())

        result = await registry.get("raw").execute(ToolCall("raw", {"value": 2}))  # type: ignore[union-attr]
        self.assertEqual(result.output, "3")


if __name__ == "__main__":
    unittest.main()

