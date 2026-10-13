from __future__ import annotations

import functools
import json
import unittest
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from types import MappingProxyType
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, Strict
from pydantic.alias_generators import to_camel

from vidbyte import tool, vidbyte_tool
from vidbyte.agents import AgentRuntime
from vidbyte.lib.dataclasses.tools import ToolParameter
from vidbyte.lib.tools.formatter import ToolsFormatter
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


class Hotel(BaseModel):
    name: str
    city: str


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


class Tally(BaseModel):
    counts: dict[Priority, int]


class DailyTally(BaseModel):
    by_day: dict[date, int]


@dataclass
class DailyTallyRecord:
    by_day: dict[date, int]


class Slots(BaseModel):
    slots: dict[int | str, str]


class OrderOut(BaseModel):
    id: str
    tags: dict[str, str]


@dataclass(frozen=True)
class OrderRecord:
    id: str
    tags: Mapping[str, str]


class AliasedOrder(BaseModel):
    order_id: str = Field(alias="orderId")
    total_cents: int = Field(alias="totalCents")


class CamelOrder(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    order_id: str
    total_cents: int


class StrictFilter(BaseModel):
    model_config = ConfigDict(strict=True)
    priority: Priority
    due: date
    window: tuple[int, int]


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

    async def test_null_for_defaulted_argument_uses_the_default(self) -> None:
        # @intent null-optional-arg-means-default
        @tool
        def search(
            query: str,
            limit: int = 5,
            lang: Annotated[str, Field(min_length=2)] = "en",
            page: int | None = 3,
        ) -> str:
            return f"{query}:{limit}:{lang}:{page}"

        call = ToolCall("search", {"query": "x", "limit": None, "lang": None, "page": None})
        result = await search.execute(call)

        # A null for a defaulted parameter that rejects None means "leave it out"; one that accepts None keeps None.
        self.assertIsNone(search.validate_call(call))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.output, "x:5:en:None")

        # A required parameter still rejects null.
        missing = ToolCall("search", {"query": None})
        self.assertIn("query", search.validate_call(missing) or "")
        self.assertEqual((await search.execute(missing)).status, ToolStatus.ERROR)

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

    async def test_raising_function_tool_reports_execution_error_kind(self) -> None:
        # A @tool function that raises must look like a raising BaseTool to the model and to ToolErrorPolicy.
        @tool
        def check_stock(sku: str) -> str:
            """Check stock for a SKU."""
            raise RuntimeError(f"inventory offline for {sku}")

        call = ToolCall("check_stock", {"sku": "A1"})
        result = await check_stock.execute(call)

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertEqual(result.output, "inventory offline for A1")
        self.assertEqual(result.metadata["error"], "execution_error")
        self.assertEqual(result.metadata["error_type"], "RuntimeError")
        formatted = ToolsFormatter.format_tool_result(call, result, "openai")
        self.assertIn("kind=execution_error", formatted["content"])

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

    async def test_strict_arguments_accept_the_models_json_spellings(self) -> None:
        # @intent tool-arguments-validate-in-json-mode
        received: list[tuple[StrictFilter, date]] = []

        @tool
        def find(criteria: StrictFilter, day: Annotated[date, Strict()]) -> str:
            """Find tickets."""
            received.append((criteria, day))
            return "ok"

        arguments = {"criteria": {"priority": "high", "due": "2026-10-11", "window": [9, 17]}, "day": "2026-10-12"}
        call = ToolCall("find", json.loads(json.dumps(arguments)))

        self.assertIsNone(find.validate_call(call))
        result = await find.execute(call)
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(received, [(StrictFilter(priority=Priority.HIGH, due=date(2026, 10, 11), window=(9, 17)), date(2026, 10, 12))])

    async def test_strict_arguments_keep_strictness_and_python_objects(self) -> None:
        # JSON mode is still strict, and a call built in code with Python objects still validates in Python mode.
        @tool
        def find(criteria: StrictFilter, day: Annotated[date, Strict()]) -> str:
            """Find tickets."""
            return f"{criteria.priority.value}:{day.isoformat()}"

        loose = ToolCall("find", {"criteria": {"priority": "high", "due": "2026-10-11", "window": "9-17"}, "day": "2026-10-12"})
        rejected = await find.execute(loose)
        self.assertEqual(rejected.status, ToolStatus.ERROR)
        self.assertEqual(rejected.metadata["error_type"], "validation")
        self.assertIn("criteria.window", find.validate_call(loose) or "")

        built = StrictFilter(priority=Priority.LOW, due=date(2026, 1, 2), window=(1, 2))
        accepted = await find.execute(ToolCall("find", {"criteria": built, "day": date(2026, 1, 3)}))
        self.assertEqual(accepted.output, "low:2026-01-03")


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

    async def test_non_string_dict_keys_serialize_like_the_model(self) -> None:
        # json.dumps never passes keys to default=, so Enum, date, and mixed int/str keys once degraded to a repr.
        def tally_model() -> Tally:
            return Tally(counts={Priority.HIGH: 3, Priority.LOW: 1})

        def tally_dict() -> dict[str, Any]:
            return {"counts": {Priority.HIGH: 3, Priority.LOW: 1}}

        def daily_model() -> DailyTally:
            return DailyTally(by_day={date(2026, 1, 2): 4})

        def daily_record() -> DailyTallyRecord:
            return DailyTallyRecord(by_day={date(2026, 1, 2): 4})

        def slots_model() -> Slots:
            return Slots(slots={1: "bolts", "top": "nuts"})

        def slots_dict() -> dict[str, Any]:
            return {"slots": {1: "bolts", "top": "nuts"}}

        cases = [
            (tally_model, tally_dict, Tally, '{"counts": {"high": 3, "low": 1}}'),
            (daily_model, daily_record, DailyTally, '{"by_day": {"2026-01-02": 4}}'),
            (slots_model, slots_dict, Slots, '{"slots": {"1": "bolts", "top": "nuts"}}'),
        ]

        for model_func, plain_func, schema, expected in cases:
            model_result = await self._run(model_func, output_schema=schema)
            plain_result = await self._run(plain_func, output_schema=schema)

            self.assertEqual(plain_result.status, ToolStatus.SUCCESS, plain_result.output)
            self.assertEqual(model_result.output, expected)
            self.assertEqual(plain_result.output, expected)

    # @intent read-only-mappings-are-json-objects
    # A MappingProxyType, as frozen records hold, must reach the model as the same JSON object a dict would.
    async def test_read_only_mapping_serializes_as_an_object(self) -> None:
        def bare() -> Mapping[str, int]:
            return MappingProxyType({"n": 1})

        def nested() -> dict[str, Any]:
            return {"items": [MappingProxyType({"a": 1})], "meta": MappingProxyType({"b": MappingProxyType({"c": 2})})}

        bare_result = await self._run(bare, output_schema=None)
        nested_result = await self._run(nested, output_schema=None)

        self.assertEqual(bare_result.output, '{"n": 1}')
        self.assertEqual(nested_result.output, '{"items": [{"a": 1}], "meta": {"b": {"c": 2}}}')

    async def test_frozen_record_with_read_only_mapping_passes_its_output_schema(self) -> None:
        def get_order() -> OrderRecord:
            return OrderRecord(id="o1", tags=MappingProxyType({"tier": "gold"}))

        def get_order_dict() -> OrderRecord:
            return OrderRecord(id="o1", tags={"tier": "gold"})

        result = await self._run(get_order, output_schema=OrderOut)
        control = await self._run(get_order_dict, output_schema=OrderOut)

        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        self.assertEqual(json.loads(result.output), {"id": "o1", "tags": {"tier": "gold"}})
        self.assertEqual(result.output, control.output)

    async def test_read_only_mapping_with_enum_keys_serializes_like_the_model(self) -> None:
        # Enum keys force the key-normalizing second pass, which must also see the proxy as an object.
        def tally() -> dict[str, Any]:
            return {"counts": MappingProxyType({Priority.HIGH: 3, Priority.LOW: 1})}

        result = await self._run(tally, output_schema=Tally)

        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        self.assertEqual(result.output, '{"counts": {"high": 3, "low": 1}}')

    async def test_string_keyed_dict_output_is_unchanged(self) -> None:
        def report() -> dict[str, Any]:
            return {"b": [1, 2.5, None], "a": {"z": True}}

        result = await self._run(report, output_schema=None)

        self.assertEqual(result.output, '{"a": {"z": true}, "b": [1, 2.5, null]}')

    # @intent tool-output-keeps-non-ascii-readable
    # A dict or model return must hand the model the same characters a str return would, not \uXXXX escapes.
    async def test_non_ascii_output_stays_readable(self) -> None:
        def weather() -> dict[str, Any]:
            return {"city": "Zürich", "stations": ["品川", "新横浜"]}

        def hotel() -> Hotel:
            return Hotel(name="Hôtel Élysée", city="Zürich")

        weather_result = await self._run(weather, output_schema=None)
        hotel_result = await self._run(hotel, output_schema=Hotel)

        self.assertEqual(hotel_result.status, ToolStatus.SUCCESS, hotel_result.output)
        self.assertEqual(weather_result.output, '{"city": "Zürich", "stations": ["品川", "新横浜"]}')
        self.assertEqual(hotel_result.output, '{"city": "Zürich", "name": "Hôtel Élysée"}')
        for result, expected in ((weather_result, weather()), (hotel_result, hotel().model_dump())):
            self.assertNotIn("\\u", result.output)
            self.assertEqual(json.loads(result.output), expected)

    # @intent tool-model-output-round-trips
    # A camelCase API model returned as its own output_schema must pass the check, so models dump by alias.
    async def test_aliased_model_passes_its_own_output_schema(self) -> None:
        def field_alias() -> AliasedOrder:
            return AliasedOrder(orderId="A-1", totalCents=4200)

        def camel() -> CamelOrder:
            return CamelOrder(orderId="A-1", totalCents=4200)

        def nested() -> dict[str, Any]:
            # A non-string key forces the key-normalizing second pass, which must also dump models by alias.
            return {"orders": {1: CamelOrder(orderId="A-1", totalCents=4200)}}

        def quote() -> Quote:
            # Control: a model without aliases serializes exactly as before.
            return Quote(sku="A1", price=9.5)

        for func, schema in ((field_alias, AliasedOrder), (camel, CamelOrder)):
            result = await self._run(func, output_schema=schema)

            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(result.output, '{"orderId": "A-1", "totalCents": 4200}')
            self.assertEqual(schema.model_validate_json(result.output), func())
        nested_result = await self._run(nested, output_schema=None)
        self.assertEqual(nested_result.output, '{"orders": {"1": {"orderId": "A-1", "totalCents": 4200}}}')
        quote_result = await self._run(quote)
        self.assertEqual(quote_result.output, '{"price": 9.5, "sku": "A1"}')

    async def test_wrong_shape_still_fails_its_output_schema(self) -> None:
        def quote() -> Passenger:
            return Passenger(name="Al", age=30)

        result = await self._run(quote)

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertEqual(result.metadata["error"], "output_schema_violation")


if __name__ == "__main__":
    unittest.main()

