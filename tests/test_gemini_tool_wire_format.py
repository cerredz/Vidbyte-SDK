"""Gemini's tool wire format is an OpenAPI subset, not full JSON Schema or OpenAI roles."""

from __future__ import annotations

import json
import unittest
from enum import Enum, IntEnum
from typing import Literal, Optional

from pydantic import BaseModel

from vidbyte import tool
from vidbyte.lib.config import TextModelMode
from vidbyte.lib.dataclasses.tools import ToolCall, ToolParameter, ToolResult, ToolSpec
from vidbyte.lib.tools import ToolsFormatter

GEMINI_TEST_KEY = "AQ" + "." + "x" * 40


def _spec_with_schema(schema: dict) -> ToolSpec:
    return ToolSpec(name="submitThing", description="Submit a thing.", input_schema=schema)


class GeminiToolSchemaTests(unittest.TestCase):
    """`parameters` must contain only keywords Gemini's Schema type accepts."""

    def test_additional_properties_is_dropped(self) -> None:
        # Every spec-declared tool goes through _parameters_schema, which stamps
        # additionalProperties: False. Gemini rejects the whole request over it.
        spec = ToolSpec(
            name="isDone",
            description="Signal completion.",
            parameters=(ToolParameter(name="done", type="bool", description="d", required=True),),
        )
        blob = json.dumps(ToolsFormatter.to_gemini_tool(spec))
        self.assertNotIn("additionalProperties", blob)

    def test_defs_and_refs_are_inlined(self) -> None:
        schema = {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"$ref": "#/$defs/Item"}}},
            "$defs": {"Item": {"type": "object", "properties": {"name": {"type": "string"}}}},
        }
        parameters = ToolsFormatter.to_gemini_tool(_spec_with_schema(schema))["function_declarations"][0]["parameters"]
        blob = json.dumps(parameters)
        self.assertNotIn("$defs", blob)
        self.assertNotIn("$ref", blob)
        self.assertEqual(parameters["properties"]["items"]["items"]["properties"]["name"]["type"], "string")

    def test_supported_keywords_survive(self) -> None:
        schema = {
            "type": "object",
            "description": "d",
            "properties": {"n": {"type": "integer", "minimum": 1, "enum": [1, 2]}},
            "required": ["n"],
        }
        parameters = ToolsFormatter.to_gemini_tool(_spec_with_schema(schema))["function_declarations"][0]["parameters"]
        self.assertEqual(parameters["required"], ["n"])
        self.assertEqual(parameters["properties"]["n"]["minimum"], 1)
        # Gemini's Schema.enum is a string list, so integer values travel as their JSON text.
        self.assertEqual(parameters["properties"]["n"]["enum"], ["1", "2"])

    def test_recursive_ref_terminates(self) -> None:
        schema = {
            "type": "object",
            "properties": {"child": {"$ref": "#/$defs/Node"}},
            "$defs": {"Node": {"type": "object", "properties": {"child": {"$ref": "#/$defs/Node"}}}},
        }
        blob = json.dumps(ToolsFormatter.to_gemini_tool(_spec_with_schema(schema)))
        self.assertNotIn("$ref", blob)


class GeminiUnionTypeTests(unittest.TestCase):
    """Gemini's Schema.type is a single enum; JSON Schema type lists must be collapsed."""

    def _parameters(self, schema: dict) -> dict:
        return ToolsFormatter.to_gemini_tool(_spec_with_schema(schema))["function_declarations"][0]["parameters"]

    def test_nullable_string_becomes_string_with_nullable(self) -> None:
        # The shape zod-built MCP servers emit for nullable fields.
        schema = {
            "type": "object",
            "properties": {
                "note": {"type": ["string", "null"], "description": "Note text, or null to clear."},
                "pinned": {"type": "boolean"},
            },
            "required": ["note"],
        }
        note = self._parameters(schema)["properties"]["note"]
        self.assertEqual(note, {"type": "string", "description": "Note text, or null to clear.", "nullable": True})

    def test_nested_type_lists_are_collapsed(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": ["integer", "null"]}},
                "meta": {"type": "object", "properties": {"owner": {"type": ["null", "string"]}}},
            },
        }
        parameters = self._parameters(schema)
        self.assertEqual(parameters["properties"]["tags"]["items"], {"type": "integer", "nullable": True})
        self.assertEqual(parameters["properties"]["meta"]["properties"]["owner"], {"type": "string", "nullable": True})

    def test_several_types_become_any_of(self) -> None:
        node = self._parameters({"type": "object", "properties": {"v": {"type": ["string", "integer", "null"]}}})["properties"]["v"]
        self.assertEqual(node, {"nullable": True, "anyOf": [{"type": "string"}, {"type": "integer"}]})

    def test_degenerate_type_lists_do_not_raise(self) -> None:
        properties = self._parameters({"type": "object", "properties": {"a": {"type": []}, "b": {"type": ["null"]}}})["properties"]
        self.assertEqual(properties["a"], {})
        self.assertEqual(properties["b"], {"nullable": True})

    def test_non_union_schema_is_unchanged(self) -> None:
        schema = {
            "type": "object",
            "properties": {"n": {"type": "integer", "nullable": True}, "s": {"type": "array", "items": {"type": "string"}}},
            "required": ["n"],
        }
        self.assertEqual(self._parameters(schema), schema)

    def test_other_providers_keep_type_lists(self) -> None:
        schema = {"type": "object", "properties": {"note": {"type": ["string", "null"]}}}
        openai = ToolsFormatter.to_openai_tool(_spec_with_schema(schema))
        self.assertIn('"type": ["string", "null"]', json.dumps(openai))


class GeminiArrayItemsTests(unittest.TestCase):
    """Gemini rejects the whole request when an array schema has no `items`."""

    def _parameters(self, spec: ToolSpec) -> dict:
        return ToolsFormatter.to_gemini_tool(spec)["function_declarations"][0]["parameters"]

    def test_tool_parameter_array_gets_any_item_schema(self) -> None:
        # ToolParameter has no item schema, so every type="array" parameter renders item-less.
        spec = ToolSpec(
            name="tagThings",
            description="Tag things.",
            parameters=(ToolParameter(name="x", type="array", description="Tags.", required=True),),
        )
        x = self._parameters(spec)["properties"]["x"]
        self.assertEqual(x["type"], "array")
        self.assertEqual(x["items"], {})
        self.assertEqual(x["description"], "Tags.")

    def test_nested_and_nullable_arrays_get_items_at_every_level(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "grid": {"type": "array", "items": {"type": "array"}},
                "meta": {"type": "object", "properties": {"ids": {"type": "array"}}},
                "maybe": {"type": ["array", "null"]},
                "either": {"type": ["array", "string"]},
            },
        }
        properties = self._parameters(_spec_with_schema(schema))["properties"]
        self.assertEqual(properties["grid"], {"type": "array", "items": {"type": "array", "items": {}}})
        self.assertEqual(properties["meta"]["properties"]["ids"], {"type": "array", "items": {}})
        self.assertEqual(properties["maybe"], {"type": "array", "nullable": True, "items": {}})
        self.assertEqual(properties["either"], {"anyOf": [{"type": "array", "items": {}}, {"type": "string"}]})

    def test_array_with_items_is_unchanged(self) -> None:
        schema = {"type": "object", "properties": {"s": {"type": "array", "items": {"type": "string"}, "minItems": 1}}}
        self.assertEqual(self._parameters(_spec_with_schema(schema)), schema)

    def test_grep_tool_extensions_carry_items(self) -> None:
        from vidbyte.tools.builtins.code_search import GrepTool

        extensions = self._parameters(GrepTool(".").spec())["properties"]["extensions"]
        self.assertEqual(extensions["type"], "array")
        self.assertEqual(extensions["items"], {})

    def test_other_providers_keep_item_less_arrays(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "array"}}}
        openai = ToolsFormatter.to_openai_tool(_spec_with_schema(schema))
        self.assertNotIn("items", json.dumps(openai))


class Level(IntEnum):
    LOW = 1
    HIGH = 2


class Mood(str, Enum):
    CALM = "calm"
    LOUD = "loud"


@tool
def file_ticket(
    priority: Literal[1, 2, 3],
    level: Level,
    weight: Literal[0.5, 1.5],
    mood: Mood,
    tag: Literal["a", None],
    maybe: Optional[Literal[1, 2]] = None,
) -> str:
    """File a ticket."""
    return "filed"


class TicketReport(BaseModel):
    title: str
    priority: Literal[1, 2, 3]


def _first_gemini_request(**agent_options: object) -> dict:
    # Runs a Gemini agent over a fake transport and returns the first request body it sends.
    from unittest.mock import patch

    from vidbyte import Agent
    from vidbyte.lib.http import HttpTransport
    from vidbyte.lib.http.transport import HttpResponse

    sent: list = []
    done = {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "isDone", "args": {"final_answer": '{"title": "t", "priority": 1}'}}}]}}]}

    async def fake_gemini(self, *, json_body=None, **kwargs) -> HttpResponse:
        sent.append(json_body or {})
        return HttpResponse(status_code=200, body=json.dumps(done), headers={})

    agent = Agent(name="r", system_prompt="s", provider="gemini", model_name="gemini-3.5-flash", api_keys=[GEMINI_TEST_KEY], model_mode=TextModelMode.DIRECT, **agent_options)
    with patch.object(HttpTransport, "request", fake_gemini):
        agent.run("go")
    return sent[0]


class GeminiEnumValueTests(unittest.TestCase):
    """Gemini's Schema.enum is a list of strings; typed enum values fail the request with a 400."""

    @classmethod
    def setUpClass(cls) -> None:
        body = _first_gemini_request(tools=[file_ticket])
        declarations = [d for entry in body["tools"] for d in entry.get("function_declarations", [])]
        cls.properties = next(d for d in declarations if d["name"] == "file_ticket")["parameters"]["properties"]

    def test_int_literal_values_become_strings_and_keep_their_type(self) -> None:
        self.assertEqual(self.properties["priority"]["type"], "integer")
        self.assertEqual(self.properties["priority"]["enum"], ["1", "2", "3"])

    def test_int_enum_from_defs_becomes_strings(self) -> None:
        level = self.properties["level"]
        self.assertNotIn("$ref", level)
        self.assertEqual(level["type"], "integer")
        self.assertEqual(level["enum"], ["1", "2"])

    def test_float_literal_values_become_strings(self) -> None:
        self.assertEqual(self.properties["weight"]["type"], "number")
        self.assertEqual(self.properties["weight"]["enum"], ["0.5", "1.5"])

    def test_optional_int_literal_any_of_branch_becomes_strings(self) -> None:
        self.assertEqual(self.properties["maybe"]["anyOf"][0], {"enum": ["1", "2"], "type": "integer"})

    def test_string_enum_and_nullable_literal_are_unchanged(self) -> None:
        self.assertEqual(self.properties["mood"]["enum"], ["calm", "loud"])
        self.assertEqual(self.properties["tag"]["enum"], ["a", None])

    def test_response_schema_int_literal_becomes_strings(self) -> None:
        body = _first_gemini_request(output_schema=TicketReport)
        priority = body["generationConfig"]["responseSchema"]["properties"]["priority"]
        self.assertEqual(priority["type"], "integer")
        self.assertEqual(priority["enum"], ["1", "2", "3"])

    def test_other_providers_keep_typed_enum_values(self) -> None:
        openai = ToolsFormatter.to_openai_tool(file_ticket.spec())["function"]["parameters"]
        self.assertEqual(openai["properties"]["priority"]["enum"], [1, 2, 3])


_OBJECT_ONLY_KEYWORDS = ("properties", "required", "propertyOrdering")
_ARRAY_ONLY_KEYWORDS = ("items", "minItems", "maxItems")


def _misplaced_type_keywords(node: object, path: str = "$") -> list[str]:
    # Walks every schema node and names each one carrying object or array keywords without that type.
    if not isinstance(node, dict):
        return []
    found = [f"{path}.{key}" for key in _OBJECT_ONLY_KEYWORDS if key in node and node.get("type") != "object"]
    found += [f"{path}.{key}" for key in _ARRAY_ONLY_KEYWORDS if key in node and node.get("type") != "array"]
    for name, sub in (node.get("properties") or {}).items():
        found += _misplaced_type_keywords(sub, f"{path}.properties.{name}")
    found += _misplaced_type_keywords(node.get("items"), f"{path}.items")
    for index, branch in enumerate(node.get("anyOf") or []):
        found += _misplaced_type_keywords(branch, f"{path}.anyOf[{index}]")
    return found


class GeminiTypeListKeywordTests(unittest.TestCase):
    """A type list split into anyOf branches must carry each type-only keyword in its own branch."""

    def _reduce(self, node: dict) -> dict:
        schema = {"type": "object", "properties": {"v": node}}
        return ToolsFormatter.to_gemini_tool(_spec_with_schema(schema))["function_declarations"][0]["parameters"]

    def test_object_keywords_move_into_the_object_branch(self) -> None:
        parameters = self._reduce({"type": ["object", "string"], "properties": {"a": {"type": "string"}}, "required": ["a"]})
        self.assertEqual(_misplaced_type_keywords(parameters), [])
        self.assertEqual(
            parameters["properties"]["v"],
            {"anyOf": [{"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}, {"type": "string"}]},
        )

    def test_array_keywords_move_into_the_array_branch(self) -> None:
        parameters = self._reduce({"type": ["array", "string"], "items": {"type": "integer"}, "maxItems": 3})
        self.assertEqual(_misplaced_type_keywords(parameters), [])
        self.assertEqual(parameters["properties"]["v"], {"anyOf": [{"type": "array", "items": {"type": "integer"}, "maxItems": 3}, {"type": "string"}]})

    def test_fork_conversation_declaration_has_no_typeless_object_keywords(self) -> None:
        from vidbyte.tools.builtins.fork import ForkConversationTool

        parameters = ToolsFormatter.to_gemini_tool(ForkConversationTool().spec())["function_declarations"][0]["parameters"]
        self.assertEqual(_misplaced_type_keywords(parameters), [])
        self.assertEqual(parameters["properties"]["handoff"]["anyOf"][0]["type"], "object")

    def test_nullable_single_type_is_unchanged(self) -> None:
        self.assertEqual(self._reduce({"type": ["string", "null"], "maxLength": 5})["properties"]["v"], {"type": "string", "maxLength": 5, "nullable": True})


class GeminiToolResultRoleTests(unittest.TestCase):
    """generateContent accepts only 'user' and 'model' turns."""

    def test_tool_result_uses_a_user_turn(self) -> None:
        call = ToolCall("submitThing", {})
        message = ToolsFormatter.format_tool_result(call, ToolResult.success("submitThing", "ok"), "gemini")
        self.assertEqual(message["role"], "user")
        self.assertEqual(message["parts"][0]["functionResponse"]["name"], "submitThing")

    def test_tool_error_result_uses_a_user_turn(self) -> None:
        call = ToolCall("submitThing", {})
        message = ToolsFormatter.format_tool_result(call, ToolResult.failure("submitThing", "boom"), "gemini")
        self.assertEqual(message["role"], "user")


class GeminiContentsOrderingTests(unittest.TestCase):
    """`contents` must place the prompt before the tool exchange it provoked."""

    def _contents(self, messages: list) -> list:
        from vidbyte.lib.config import TextModelConfig
        from vidbyte.lib.enums import ModelProvider
        from vidbyte.providers.gemini import GeminiProvider

        config = TextModelConfig(provider=ModelProvider.GEMINI, model="gemini-3.6-flash", messages=tuple(messages))
        return GeminiProvider()._create_contents(config, "do the thing")

    def test_prompt_precedes_a_trailing_tool_exchange(self) -> None:
        contents = self._contents(
            [
                {"role": "model", "parts": [{"functionCall": {"name": "t", "args": {}}}]},
                {"role": "user", "parts": [{"functionResponse": {"name": "t", "response": {}}}]},
            ]
        )
        self.assertEqual([c["role"] for c in contents], ["user", "model", "user"])
        self.assertEqual(contents[0]["parts"][0]["text"], "do the thing")

    def test_prompt_appends_when_history_has_no_tool_turns(self) -> None:
        contents = self._contents([{"role": "user", "parts": [{"text": "earlier"}]}])
        self.assertEqual(contents[-1]["parts"][0]["text"], "do the thing")

    def test_already_introduced_call_leaves_history_alone(self) -> None:
        # The call already follows a user turn, so the history is legal as-is.
        contents = self._contents(
            [
                {"role": "user", "parts": [{"text": "earlier"}]},
                {"role": "model", "parts": [{"functionCall": {"name": "t", "args": {}}}]},
            ]
        )
        self.assertEqual(contents[0]["parts"][0]["text"], "earlier")
        self.assertIn("functionCall", contents[1]["parts"][0])
        self.assertEqual(contents[2]["parts"][0]["text"], "do the thing")

    def test_prompt_precedes_call_even_when_other_turns_trail_it(self) -> None:
        # Contract feedback is appended after the tool exchange, so the tool block is no
        # longer trailing — the prompt still belongs in front of the call.
        contents = self._contents(
            [
                {"role": "model", "parts": [{"functionCall": {"name": "t", "args": {}}}]},
                {"role": "user", "parts": [{"functionResponse": {"name": "t", "response": {}}}]},
                {"role": "user", "content": "that did not match the schema"},
            ]
        )
        self.assertEqual(contents[0]["parts"][0]["text"], "do the thing")
        self.assertIn("functionCall", contents[1]["parts"][0])
        self.assertEqual(contents[3]["parts"][0]["text"], "that did not match the schema")

    def test_prompt_precedes_a_rejected_text_draft(self) -> None:
        # A rejected plain-text answer is appended as an assistant turn before the contract
        # feedback, so the exchange opens with a model turn; the prompt must still come first.
        contents = self._contents([{"role": "assistant", "content": "draft"}, {"role": "user", "content": "feedback"}])
        self.assertEqual([c["role"] for c in contents], ["user", "model", "user"])
        self.assertEqual(contents[0]["parts"][0]["text"], "do the thing")
        self.assertEqual(contents[-1]["parts"][0]["text"], "feedback")

    def test_model_text_before_a_call_joins_the_call_turn(self) -> None:
        # A context note pinned to the top of the conversation arrives as an assistant turn
        # just before the call; Gemini rejects a call turn that follows another model turn.
        call = {"functionCall": {"name": "t", "args": {}}}
        contents = self._contents(
            [
                {"role": "assistant", "content": "pinned note"},
                {"role": "model", "parts": [call]},
                {"role": "user", "parts": [{"functionResponse": {"name": "t", "response": {}}}]},
            ]
        )
        self.assertEqual([c["role"] for c in contents], ["user", "model", "user"])
        self.assertEqual(contents[0]["parts"], [{"text": "do the thing"}])
        self.assertEqual(contents[1]["parts"], [{"text": "pinned note"}, call])

    def test_openai_shaped_history_is_converted_to_parts(self) -> None:
        # Contract feedback and assistant turns are appended in the OpenAI {role, content}
        # shape, which Gemini cannot read.
        contents = self._contents([{"role": "assistant", "content": "prior answer"}])
        model_turn = next(c for c in contents if c["role"] == "model")
        self.assertEqual(model_turn["parts"][0]["text"], "prior answer")
        self.assertNotIn("content", model_turn)

    def test_prompt_skips_a_replayed_exchange_and_opens_this_runs_round(self) -> None:
        # A replayed transcript already holds an introduced exchange; the prompt opens this run's call instead.
        call = {"role": "model", "parts": [{"functionCall": {"name": "hours", "args": {}}}]}
        response = {"role": "user", "parts": [{"functionResponse": {"name": "hours", "response": {}}}]}
        contents = self._contents([{"role": "user", "content": "Hours on Sunday?"}, call, response, {"role": "assistant", "content": "closed"}, call, response])
        self.assertEqual([c["role"] for c in contents], ["user", "model", "user", "model", "user", "model", "user"])
        self.assertEqual(contents[3]["parts"], [{"text": "closed"}])
        self.assertEqual(contents[4]["parts"], [{"text": "do the thing"}])
        self.assertIn("functionCall", contents[5]["parts"][0])


def _call_turn(*names: str) -> dict:
    return {"role": "model", "parts": [{"functionCall": {"name": name, "args": {}}} for name in names]}


def _response_turn(name: str) -> dict:
    return {"role": "user", "parts": [{"functionResponse": {"name": name, "response": {"r": name}}}]}


def _gemini_part_count_errors(contents: list) -> list:
    # Mirrors Gemini's 400: a call turn must be answered by the next content, part for part.
    errors = []
    for index, turn in enumerate(contents):
        calls = sum("functionCall" in part for part in turn.get("parts", []))
        if not calls:
            continue
        following = contents[index + 1] if index + 1 < len(contents) else None
        responses = sum("functionResponse" in part for part in following.get("parts", [])) if following else 0
        if following is not None and responses != calls:
            errors.append(f"turn {index}: {calls} calls, {responses} responses")
    return errors


class GeminiParallelFunctionResponseTests(unittest.TestCase):
    """Responses to one parallel call turn must arrive as one user content."""

    def _contents(self, messages: list) -> list:
        from vidbyte.lib.config import TextModelConfig
        from vidbyte.lib.enums import ModelProvider
        from vidbyte.providers.gemini import GeminiProvider

        config = TextModelConfig(provider=ModelProvider.GEMINI, model="gemini-3.6-flash", messages=tuple(messages))
        return GeminiProvider()._create_contents(config, "go")

    def test_three_parallel_responses_merge_into_one_user_content(self) -> None:
        contents = self._contents([_call_turn("a", "b", "c"), _response_turn("a"), _response_turn("b"), _response_turn("c")])
        self.assertEqual([c["role"] for c in contents], ["user", "model", "user"])
        self.assertEqual([p["functionResponse"]["response"]["r"] for p in contents[2]["parts"]], ["a", "b", "c"])
        self.assertEqual(_gemini_part_count_errors(contents), [])

    def test_text_turns_and_separate_call_turns_are_not_merged(self) -> None:
        contents = self._contents(
            [
                _call_turn("a"),
                _response_turn("a"),
                _call_turn("b", "c"),
                _response_turn("b"),
                _response_turn("c"),
                {"role": "user", "content": "feedback"},
            ]
        )
        self.assertEqual([len(c["parts"]) for c in contents], [1, 1, 1, 2, 2, 1])
        self.assertEqual(contents[-1]["parts"][0]["text"], "feedback")
        self.assertEqual(_gemini_part_count_errors(contents), [])


class GeminiParallelCallAgentTests(unittest.IsolatedAsyncioTestCase):
    """End to end: a Gemini agent survives parallel calls across two runs on one agent."""

    async def test_parallel_calls_validate_across_two_runs(self) -> None:
        from unittest.mock import patch

        from vidbyte import Agent, tool
        from vidbyte.lib.http import HttpTransport
        from vidbyte.lib.http.transport import HttpResponse

        @tool
        def search(query: str) -> str:
            """Search for a query."""
            return f"result {query}"

        def model_turn(*parts: dict) -> dict:
            return {"candidates": [{"content": {"role": "model", "parts": list(parts)}}]}

        def search_call(query: str) -> dict:
            return {"functionCall": {"name": "search", "args": {"query": query}}}

        done = {"functionCall": {"name": "isDone", "args": {"final_answer": "done"}}}
        replies = [
            model_turn(search_call("a"), search_call("b"), search_call("c")),
            model_turn(done),
            model_turn(search_call("d"), search_call("e")),
            model_turn(done),
        ]
        sent: list = []

        async def strict_gemini(self, *, json_body=None, **kwargs) -> HttpResponse:
            contents = list((json_body or {}).get("contents", []))
            sent.append(contents)
            errors = _gemini_part_count_errors(contents)
            if errors:
                body = {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "Please ensure that the number of function response parts is equal to the number of function call parts of the function call turn."}}
                return HttpResponse(status_code=400, body=json.dumps(body), headers={})
            return HttpResponse(status_code=200, body=json.dumps(replies.pop(0)), headers={})

        agent = Agent(name="r", system_prompt="s", tools=[search], provider="gemini", model_name="gemini-3.5-flash", api_keys=[GEMINI_TEST_KEY], model_mode=TextModelMode.DIRECT)
        with patch.object(HttpTransport, "request", strict_gemini):
            await agent.arun("go")
            await agent.arun("again")

        self.assertEqual(replies, [])
        merged = next(c for c in sent[1] if any("functionResponse" in p for p in c["parts"]))
        self.assertEqual(merged["role"], "user")
        self.assertEqual(len(merged["parts"]), 3)
        self.assertTrue(all(_gemini_part_count_errors(contents) == [] for contents in sent))


class AgentRequestTimeoutTests(unittest.TestCase):
    """A slow reasoning model needs a longer HTTP read than the 60s config default."""

    def _runner(self, **kwargs):
        from vidbyte.agents import BaseAgent

        agent = BaseAgent(name="w", system_prompt="s", provider="xai", model_name="grok-4.5", api_keys=["xai-k"], model_mode=TextModelMode.DIRECT, **kwargs)
        runner, _ = agent._runner_for_model()
        return runner

    def test_timeout_reaches_the_model_config(self) -> None:
        self.assertEqual(self._runner(timeout_seconds=300.0)._config.timeout_seconds, 300.0)

    def test_default_is_left_alone_when_unset(self) -> None:
        self.assertEqual(self._runner()._config.timeout_seconds, 60.0)


if __name__ == "__main__":
    unittest.main()
