from __future__ import annotations

import functools
import unittest
from collections.abc import Callable
from typing import Annotated, Any

from pydantic import BaseModel, Field

from vidbyte import tool, vidbyte_tool
from vidbyte.lib.dataclasses.tools import ToolParameter
from vidbyte.tools import ToolCall, ToolRegistry, ToolStatus


class Passenger(BaseModel):
    name: str
    age: int


def _logged(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    return wrapper


class CustomFunctionToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_alias_generates_schema_and_executes(self) -> None:
        @tool
        def echo(value: str) -> str:
            """Echo a value."""
            return value

        result = await echo.execute(ToolCall("echo", {"value": "ok"}))

        self.assertEqual(echo.spec().name, "echo")
        self.assertEqual(result.output, "ok")

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

    async def test_nested_model_and_dataclass_arguments_keep_their_types(self) -> None:
        received: dict[str, object] = {}

        @vidbyte_tool
        def book(
            nights: int,
            status: ToolStatus,
            passenger: Passenger | None = None,
            parameter: ToolParameter | None = None,
        ) -> str:
            """Book a trip."""
            received.update(nights=nights, status=status, passenger=passenger, parameter=parameter)
            return f"{passenger.name}:{parameter.name}" if passenger and parameter else "none"

        result = await book.execute(
            ToolCall(
                "book",
                {
                    "nights": "4",
                    "status": "success",
                    "passenger": {"name": "Al", "age": 30},
                    "parameter": {"name": "city", "type": "string", "description": "Destination"},
                },
            )
        )

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.output, "Al:city")
        self.assertEqual(received["nights"], 4)
        self.assertIs(received["status"], ToolStatus.SUCCESS)
        self.assertEqual(received["passenger"], Passenger(name="Al", age=30))
        self.assertIsInstance(received["parameter"], ToolParameter)
        self.assertEqual(received["parameter"].name, "city")  # type: ignore[union-attr]

    async def test_sync_decorated_async_function_result_is_awaited(self) -> None:
        @tool
        @_logged
        async def restart(service: str) -> str:
            """Restart a service."""
            return f"restarted {service}"

        result = await restart.execute(ToolCall("restart", {"service": "db"}))

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.output, "restarted db")

    async def test_sync_decorated_async_function_error_becomes_failure(self) -> None:
        @tool
        @_logged
        async def restart(service: str) -> str:
            """Restart a service."""
            raise RuntimeError(f"cannot restart {service}")

        result = await restart.execute(ToolCall("restart", {"service": "db"}))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertEqual(result.output, "cannot restart db")
        self.assertEqual(result.metadata["error_type"], "RuntimeError")

    async def test_annotated_field_metadata_reaches_schema_and_validation(self) -> None:
        # This module uses `from __future__ import annotations`, so these hints are strings too.
        calls: list[tuple[str, int]] = []

        @tool
        def book_stay(
            city: Annotated[str, Field(description="Destination city name", min_length=2)],
            nights: Annotated[int, Field(ge=1, le=9, description="Number of nights (1-9)")] = 1,
        ) -> str:
            """Book a stay."""
            calls.append((city, nights))
            return f"{city}:{nights}"

        spec = book_stay.spec()
        nights_schema = spec.input_schema["properties"]["nights"]
        self.assertEqual(nights_schema["description"], "Number of nights (1-9)")
        self.assertEqual(nights_schema["minimum"], 1)
        self.assertEqual(nights_schema["maximum"], 9)
        self.assertEqual(spec.input_schema["properties"]["city"]["minLength"], 2)
        self.assertEqual(spec.input_schema["required"], ["city"])
        parameters = {parameter.name: parameter for parameter in spec.parameters}
        self.assertEqual(parameters["nights"].description, "Number of nights (1-9)")
        self.assertEqual(parameters["city"].description, "Destination city name")

        rejected = await book_stay.execute(ToolCall("book_stay", {"city": "Rome", "nights": 40}))
        self.assertEqual(rejected.status, ToolStatus.ERROR)
        self.assertEqual(rejected.metadata["error_type"], "validation")
        self.assertIn("nights", rejected.output)
        self.assertIsNotNone(book_stay.validate_call(ToolCall("book_stay", {"city": "X"})))
        self.assertEqual(calls, [])

        accepted = await book_stay.execute(ToolCall("book_stay", {"city": "Rome", "nights": 3}))
        self.assertEqual(accepted.status, ToolStatus.SUCCESS)
        self.assertEqual(accepted.output, "Rome:3")
        defaulted = await book_stay.execute(ToolCall("book_stay", {"city": "Oslo"}))
        self.assertEqual(defaulted.output, "Oslo:1")
        self.assertEqual(calls, [("Rome", 3), ("Oslo", 1)])


if __name__ == "__main__":
    unittest.main()

