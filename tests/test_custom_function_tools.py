from __future__ import annotations

import functools
import json
import unittest
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field

from vidbyte import tool, vidbyte_tool
from vidbyte.agents import AgentRuntime
from vidbyte.lib.dataclasses.tools import ToolParameter
from vidbyte.tools import FunctionTool, ToolCall, ToolRegistry, Tools, ToolStatus
from vidbyte.tools.security import PermissionPolicy


class Passenger(BaseModel):
    name: str
    age: int


class Quote(BaseModel):
    sku: str
    price: float


@dataclass
class QuoteRecord:
    sku: str
    price: float


class Priority(Enum):
    LOW = "low"
    HIGH = "high"


class Ticket(BaseModel):
    priority: Priority
    due: datetime


@dataclass
class TicketRecord:
    priority: Priority
    due: datetime


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


class StructuredToolOutputTests(unittest.IsolatedAsyncioTestCase):
    # @intent tool-model-output-is-json
    # A tool returning a model or dataclass must hand the model a JSON object, not the object's repr string.

    async def _run(self, func: Callable[..., Any], output_schema: type | None = Quote) -> Any:
        runtime = AgentRuntime(agent_name="rt-agent", system_prompt="sys", tools=Tools().add(FunctionTool(func, output_schema=output_schema)), permission_policy=PermissionPolicy())
        _, result = await runtime.execute_tool_call(ToolCall(func.__name__, {}), provider="openai")
        return result

    async def test_model_instance_passes_its_output_schema(self) -> None:
        def quote() -> Quote:
            return Quote(sku="A1", price=9.5)

        result = await self._run(quote)

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(json.loads(result.output), {"price": 9.5, "sku": "A1"})

    async def test_dataclass_instance_passes_its_output_schema(self) -> None:
        def quote() -> QuoteRecord:
            return QuoteRecord(sku="A1", price=9.5)

        result = await self._run(quote)

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(json.loads(result.output), {"price": 9.5, "sku": "A1"})

    async def test_nested_models_and_dataclasses_serialize_as_objects(self) -> None:
        @tool
        def quotes() -> dict[str, Any]:
            """List quotes."""
            return {"items": [Quote(sku="A1", price=9.5), QuoteRecord(sku="B2", price=1.0)], "kind": QuoteRecord}

        result = await quotes.execute(ToolCall("quotes", {}))

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        payload = json.loads(result.output)
        self.assertEqual(payload["items"], [{"price": 9.5, "sku": "A1"}, {"price": 1.0, "sku": "B2"}])
        self.assertEqual(payload["kind"], str(QuoteRecord))

    async def test_enum_and_datetime_leaves_serialize_like_the_model(self) -> None:
        due = datetime(2026, 10, 9, 15)

        def ticket_model() -> Ticket:
            return Ticket(priority=Priority.HIGH, due=due)

        def ticket_record() -> TicketRecord:
            return TicketRecord(priority=Priority.HIGH, due=due)

        def ticket_dict() -> dict[str, Any]:
            return {"priority": Priority.HIGH, "due": due}

        results = [await self._run(func, output_schema=Ticket) for func in (ticket_model, ticket_record, ticket_dict)]

        for result in results:
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(result.output, '{"due": "2026-10-09T15:00:00", "priority": "high"}')

    async def test_wrong_shape_still_fails_its_output_schema(self) -> None:
        def quote() -> Passenger:
            return Passenger(name="Al", age=30)

        result = await self._run(quote)

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertEqual(result.metadata["error"], "output_schema_violation")


if __name__ == "__main__":
    unittest.main()

