"""Context Protocol Header

Description:
    Unit tests for all memory provider tool classes.
Purpose:
    Verifies spec declarations, parameter validation, HTTP request construction,
    response parsing, and error handling — all without real network calls.
Architecture:
    - MockTransport: Configurable stub replacing HttpTransport.
    - MemoryToolTests: One test class grouping all provider assertions.
Relations:
    Tests vidbyte.tools.builtins.memory (all five provider modules).
"""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from typing import Any

from vidbyte.lib.errors import ProviderRequestError
from vidbyte.tools.builtins.memory import (
    CogneeAddTool,
    CogneeCognifyTool,
    CogneeDeleteTool,
    CogneeSearchTool,
    LettaAddArchivalMemoryTool,
    LettaDeleteArchivalMemoryTool,
    LettaGetMemoryBlockTool,
    LettaSearchArchivalMemoryTool,
    Mem0AddMemoryTool,
    Mem0DeleteMemoryTool,
    Mem0GetMemoriesTool,
    Mem0SearchMemoryTool,
    SupermemoryAddMemoryTool,
    SupermemoryDeleteMemoryTool,
    SupermemorySearchMemoryTool,
    ZepAddMemoryTool,
    ZepDeleteSessionTool,
    ZepGetMemoryTool,
    ZepSearchMemoryTool,
)
from vidbyte.tools.types import ToolCall, ToolStatus


@dataclass
class FakeHttpResponse:
    status_code: int
    body: str
    headers: dict


class MockTransport:
    """Replaces HttpTransport with a configurable stub for testing."""

    def __init__(self, status: int = 200, body: dict | str = None, raise_exc: Exception | None = None) -> None:
        self.status = status
        self.body = json.dumps(body or {})
        self.raise_exc = raise_exc
        self.last_call: dict = {}

    async def request(self, *, method: str, url: str, headers: Any = None, json_body: Any = None, timeout_seconds: float = 30.0, **kwargs: Any) -> FakeHttpResponse:
        self.last_call = {"method": method, "url": url, "headers": headers or {}, "json_body": json_body}
        if self.raise_exc:
            raise self.raise_exc
        return FakeHttpResponse(status_code=self.status, body=self.body, headers={})


def _inject_transport(tool: Any, transport: MockTransport) -> Any:
    """Replace the tool's internal HttpTransport with a mock."""
    tool._transport = transport
    return tool


class SupermemoryAddTests(unittest.IsolatedAsyncioTestCase):

    async def test_add_memory_success_returns_tool_result_success(self) -> None:
        """Happy path: 200 response is surfaced as ToolResult.SUCCESS."""
        tool = _inject_transport(SupermemoryAddMemoryTool("key123"), MockTransport(200, {"id": "doc_abc"}))
        result = await tool.execute(ToolCall("supermemory_add_memory", {"content": "Alice likes cats"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("doc_abc", result.output)

    async def test_add_memory_missing_content_returns_error(self) -> None:
        """[Hidden Assumption] content is always supplied."""
        tool = SupermemoryAddMemoryTool("key123")
        result = await tool.execute(ToolCall("supermemory_add_memory", {}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("Missing", result.output)

    async def test_add_memory_api_error_404_returns_tool_result_error(self) -> None:
        """[Silent Failure] non-2xx is not swallowed."""
        tool = _inject_transport(SupermemoryAddMemoryTool("key123"), MockTransport(404, {"detail": "not found"}))
        result = await tool.execute(ToolCall("supermemory_add_memory", {"content": "test"}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("404", result.output)

    async def test_add_memory_non_json_response_returns_error(self) -> None:
        """[Hidden Failure] provider returns HTML error page instead of JSON."""
        transport = MockTransport(500, {})
        transport.body = "<html>error</html>"
        tool = _inject_transport(SupermemoryAddMemoryTool("key123"), transport)
        result = await tool.execute(ToolCall("supermemory_add_memory", {"content": "test"}))
        self.assertEqual(result.status, ToolStatus.ERROR)

    async def test_add_memory_network_exception_returns_error(self) -> None:
        """[Hidden Failure] ProviderRequestError from transport is caught."""
        transport = MockTransport(raise_exc=ProviderRequestError("network down", provider="supermemory"))
        tool = _inject_transport(SupermemoryAddMemoryTool("key123"), transport)
        result = await tool.execute(ToolCall("supermemory_add_memory", {"content": "test"}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("Request failed", result.output)

    def test_add_memory_empty_api_key_raises_at_construction(self) -> None:
        """[Hidden Assumption] api_key is never empty."""
        with self.assertRaises(ValueError):
            SupermemoryAddMemoryTool("")

    async def test_add_memory_container_tags_forwarded_correctly(self) -> None:
        """[Silent Failure] container_tags are not silently dropped from the body."""
        transport = MockTransport(200, {"id": "x"})
        tool = _inject_transport(SupermemoryAddMemoryTool("key123"), transport)
        await tool.execute(ToolCall("supermemory_add_memory", {"content": "test", "container_tags": ["user_42"]}))
        self.assertEqual(transport.last_call["json_body"]["containerTags"], ["user_42"])

    async def test_add_memory_custom_id_forwarded(self) -> None:
        """[Silent Failure] custom_id is included when provided."""
        transport = MockTransport(200, {"id": "x"})
        tool = _inject_transport(SupermemoryAddMemoryTool("key123"), transport)
        await tool.execute(ToolCall("supermemory_add_memory", {"content": "test", "custom_id": "conv_001"}))
        self.assertEqual(transport.last_call["json_body"]["customId"], "conv_001")

    async def test_add_memory_uses_bearer_auth(self) -> None:
        """[Silent Failure] wrong auth scheme causes silent 401."""
        transport = MockTransport(200, {"id": "x"})
        tool = _inject_transport(SupermemoryAddMemoryTool("mykey"), transport)
        await tool.execute(ToolCall("supermemory_add_memory", {"content": "test"}))
        self.assertIn("Bearer mykey", transport.last_call["headers"]["authorization"])


class SupermemorySearchTests(unittest.IsolatedAsyncioTestCase):

    async def test_search_returns_results_on_success(self) -> None:
        """[Edge Case] happy path returns results array."""
        transport = MockTransport(200, {"results": [{"id": "doc1", "text": "Alice likes cats"}]})
        tool = _inject_transport(SupermemorySearchMemoryTool("key123"), transport)
        result = await tool.execute(ToolCall("supermemory_search_memory", {"query": "cats"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("doc1", result.output)

    async def test_search_empty_results_array_returns_success(self) -> None:
        """[Edge Case] zero results is not an error."""
        transport = MockTransport(200, {"results": []})
        tool = _inject_transport(SupermemorySearchMemoryTool("key123"), transport)
        result = await tool.execute(ToolCall("supermemory_search_memory", {"query": "xyz"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)

    async def test_search_missing_query_returns_validation_error(self) -> None:
        """[Hidden Assumption] query is always supplied."""
        tool = SupermemorySearchMemoryTool("key123")
        result = await tool.execute(ToolCall("supermemory_search_memory", {}))
        self.assertEqual(result.status, ToolStatus.ERROR)

    async def test_search_container_tag_forwarded(self) -> None:
        """[Silent Failure] container_tag is included in search body."""
        transport = MockTransport(200, {"results": []})
        tool = _inject_transport(SupermemorySearchMemoryTool("key123"), transport)
        await tool.execute(ToolCall("supermemory_search_memory", {"query": "test", "container_tag": "user_99"}))
        self.assertEqual(transport.last_call["json_body"]["containerTag"], "user_99")


class SupermemoryDeleteTests(unittest.IsolatedAsyncioTestCase):

    async def test_delete_success_returns_success(self) -> None:
        """[Edge Case] delete returns ToolResult.SUCCESS on 200."""
        transport = MockTransport(200, {})
        tool = _inject_transport(SupermemoryDeleteMemoryTool("key123"), transport)
        result = await tool.execute(ToolCall("supermemory_delete_memory", {"document_id": "doc_abc"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("doc_abc", result.output)

    async def test_delete_nonexistent_id_returns_error(self) -> None:
        """[Hidden Assumption] document_id always exists."""
        transport = MockTransport(404, {"detail": "not found"})
        tool = _inject_transport(SupermemoryDeleteMemoryTool("key123"), transport)
        result = await tool.execute(ToolCall("supermemory_delete_memory", {"document_id": "bad_id"}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class Mem0AddTests(unittest.IsolatedAsyncioTestCase):

    async def test_add_memory_with_user_id_succeeds(self) -> None:
        """[Edge Case] basic add with user_id returns success."""
        transport = MockTransport(200, {"event_id": "evt_1"})
        tool = _inject_transport(Mem0AddMemoryTool("mem0key"), transport)
        result = await tool.execute(ToolCall("mem0_add_memory", {
            "messages": [{"role": "user", "content": "My name is Bob"}],
            "user_id": "bob_123",
        }))
        self.assertEqual(result.status, ToolStatus.SUCCESS)

    async def test_add_memory_uses_token_auth_scheme_not_bearer(self) -> None:
        """[Silent Failure] Mem0 requires 'Token' scheme, not Bearer."""
        transport = MockTransport(200, {})
        tool = _inject_transport(Mem0AddMemoryTool("mem0key"), transport)
        await tool.execute(ToolCall("mem0_add_memory", {
            "messages": [{"role": "user", "content": "hi"}],
        }))
        self.assertIn("Token mem0key", transport.last_call["headers"]["authorization"])

    async def test_add_memory_empty_messages_returns_error(self) -> None:
        """[Edge Case] empty messages list is rejected."""
        tool = Mem0AddMemoryTool("mem0key")
        result = await tool.execute(ToolCall("mem0_add_memory", {"messages": []}))
        self.assertEqual(result.status, ToolStatus.ERROR)

    async def test_add_memory_api_500_returns_tool_result_error(self) -> None:
        """[Hidden Failure] 500 from Mem0 is surfaced as error."""
        transport = MockTransport(500, {"detail": "internal error"})
        tool = _inject_transport(Mem0AddMemoryTool("mem0key"), transport)
        result = await tool.execute(ToolCall("mem0_add_memory", {
            "messages": [{"role": "user", "content": "hi"}],
        }))
        self.assertEqual(result.status, ToolStatus.ERROR)


class Mem0SearchTests(unittest.IsolatedAsyncioTestCase):

    async def test_search_with_user_id_and_agent_id_both_included(self) -> None:
        """[Edge Case] both scopes forwarded in body."""
        transport = MockTransport(200, {"results": []})
        tool = _inject_transport(Mem0SearchMemoryTool("mem0key"), transport)
        await tool.execute(ToolCall("mem0_search_memory", {"query": "cats", "user_id": "u1", "agent_id": "a1"}))
        body = transport.last_call["json_body"]
        self.assertEqual(body["user_id"], "u1")
        self.assertEqual(body["agent_id"], "a1")

    async def test_search_empty_query_returns_validation_error(self) -> None:
        """[Hidden Assumption] query is always supplied."""
        tool = Mem0SearchMemoryTool("mem0key")
        result = await tool.execute(ToolCall("mem0_search_memory", {}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class Mem0GetTests(unittest.IsolatedAsyncioTestCase):

    async def test_get_memories_pagination_params_forwarded(self) -> None:
        """[Silent Failure] pagination params not silently ignored."""
        transport = MockTransport(200, {"count": 5, "results": []})
        tool = _inject_transport(Mem0GetMemoriesTool("mem0key"), transport)
        await tool.execute(ToolCall("mem0_get_memories", {"user_id": "bob", "page": 2, "page_size": 5}))
        self.assertIn("page=2", transport.last_call["url"])
        self.assertIn("page_size=5", transport.last_call["url"])

    async def test_get_memories_missing_user_id_returns_error(self) -> None:
        """[Hidden Assumption] user_id is always provided."""
        tool = Mem0GetMemoriesTool("mem0key")
        result = await tool.execute(ToolCall("mem0_get_memories", {}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class Mem0DeleteTests(unittest.IsolatedAsyncioTestCase):

    async def test_delete_by_id_success(self) -> None:
        """[Edge Case] successful delete returns ToolResult.SUCCESS."""
        transport = MockTransport(200, {})
        tool = _inject_transport(Mem0DeleteMemoryTool("mem0key"), transport)
        result = await tool.execute(ToolCall("mem0_delete_memory", {"memory_id": "mem_xyz"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("mem_xyz", result.output)

    async def test_delete_nonexistent_id_returns_error(self) -> None:
        """[Hidden Assumption] memory_id always exists."""
        transport = MockTransport(404, {"detail": "not found"})
        tool = _inject_transport(Mem0DeleteMemoryTool("mem0key"), transport)
        result = await tool.execute(ToolCall("mem0_delete_memory", {"memory_id": "bad_id"}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class ZepAddTests(unittest.IsolatedAsyncioTestCase):

    async def test_add_messages_to_session_success(self) -> None:
        """[Edge Case] basic add to new session returns success."""
        transport = MockTransport(200, {})
        tool = _inject_transport(ZepAddMemoryTool("zepkey"), transport)
        result = await tool.execute(ToolCall("zep_add_memory", {
            "session_id": "sess_1",
            "messages": [{"role": "human", "role_type": "human", "content": "Hello"}],
        }))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("sess_1", result.output)

    async def test_add_empty_messages_list_returns_error(self) -> None:
        """[Edge Case] empty messages list is rejected before HTTP call."""
        tool = ZepAddMemoryTool("zepkey")
        result = await tool.execute(ToolCall("zep_add_memory", {"session_id": "s", "messages": []}))
        self.assertEqual(result.status, ToolStatus.ERROR)

    async def test_add_missing_session_id_returns_validation_error(self) -> None:
        """[Hidden Assumption] session_id is always provided."""
        tool = ZepAddMemoryTool("zepkey")
        result = await tool.execute(ToolCall("zep_add_memory", {"messages": [{"role": "human", "content": "hi"}]}))
        self.assertEqual(result.status, ToolStatus.ERROR)

    async def test_add_uses_api_key_auth_scheme(self) -> None:
        """[Silent Failure] Zep requires 'Api-Key' scheme, not Bearer."""
        transport = MockTransport(200, {})
        tool = _inject_transport(ZepAddMemoryTool("zepkey"), transport)
        await tool.execute(ToolCall("zep_add_memory", {
            "session_id": "s",
            "messages": [{"role": "human", "content": "hi"}],
        }))
        self.assertIn("Api-Key zepkey", transport.last_call["headers"]["authorization"])


class ZepGetTests(unittest.IsolatedAsyncioTestCase):

    async def test_get_returns_context_string(self) -> None:
        """[Edge Case] context string from response is returned."""
        transport = MockTransport(200, {"context": "Alice is a developer.", "messages": []})
        tool = _inject_transport(ZepGetMemoryTool("zepkey"), transport)
        result = await tool.execute(ToolCall("zep_get_memory", {"session_id": "sess_1"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("Alice is a developer.", result.output)

    async def test_get_missing_session_id_returns_error(self) -> None:
        """[Hidden Assumption] session_id is required."""
        tool = ZepGetMemoryTool("zepkey")
        result = await tool.execute(ToolCall("zep_get_memory", {}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class ZepSearchTests(unittest.IsolatedAsyncioTestCase):

    async def test_search_with_limit_forwarded(self) -> None:
        """[Silent Failure] limit param is not silently ignored."""
        transport = MockTransport(200, {"results": []})
        tool = _inject_transport(ZepSearchMemoryTool("zepkey"), transport)
        await tool.execute(ToolCall("zep_search_memory", {"session_id": "s", "text": "cats", "limit": 3}))
        self.assertEqual(transport.last_call["json_body"]["limit"], 3)

    async def test_search_missing_text_returns_validation_error(self) -> None:
        """[Hidden Assumption] text param is required."""
        tool = ZepSearchMemoryTool("zepkey")
        result = await tool.execute(ToolCall("zep_search_memory", {"session_id": "s"}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class ZepDeleteTests(unittest.IsolatedAsyncioTestCase):

    async def test_delete_session_success(self) -> None:
        """[Edge Case] successful session delete returns ToolResult.SUCCESS."""
        transport = MockTransport(200, {})
        tool = _inject_transport(ZepDeleteSessionTool("zepkey"), transport)
        result = await tool.execute(ToolCall("zep_delete_session", {"session_id": "sess_1"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("sess_1", result.output)

    async def test_delete_session_404_returns_error(self) -> None:
        """[Hidden Assumption] session always exists before delete."""
        transport = MockTransport(404, {"detail": "not found"})
        tool = _inject_transport(ZepDeleteSessionTool("zepkey"), transport)
        result = await tool.execute(ToolCall("zep_delete_session", {"session_id": "bad"}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class CogneeAddTests(unittest.IsolatedAsyncioTestCase):

    async def test_add_content_to_default_dataset(self) -> None:
        """[Edge Case] adds content to 'default' dataset when none specified."""
        transport = MockTransport(200, {"status": "queued"})
        tool = _inject_transport(CogneeAddTool("ckey"), transport)
        result = await tool.execute(ToolCall("cognee_add", {"content": "The sky is blue."}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(transport.last_call["json_body"]["datasetId"], "default")

    async def test_add_content_to_named_dataset(self) -> None:
        """[Edge Case] custom dataset_id is forwarded."""
        transport = MockTransport(200, {})
        tool = _inject_transport(CogneeAddTool("ckey"), transport)
        await tool.execute(ToolCall("cognee_add", {"content": "text", "dataset_id": "project_alpha"}))
        self.assertEqual(transport.last_call["json_body"]["datasetId"], "project_alpha")

    async def test_add_with_custom_base_url(self) -> None:
        """[Hidden Assumption] default localhost base_url is not always correct."""
        transport = MockTransport(200, {})
        tool = _inject_transport(CogneeAddTool("ckey", base_url="https://cognee.example.com"), transport)
        await tool.execute(ToolCall("cognee_add", {"content": "hello"}))
        self.assertIn("cognee.example.com", transport.last_call["url"])


class CogneeCognifyTests(unittest.IsolatedAsyncioTestCase):

    async def test_cognify_triggers_graph_build(self) -> None:
        """[Edge Case] cognify POSTs to correct endpoint and returns success."""
        transport = MockTransport(200, {"status": "cognifying"})
        tool = _inject_transport(CogneeCognifyTool("ckey"), transport)
        result = await tool.execute(ToolCall("cognee_cognify", {}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("/api/v1/cognify", transport.last_call["url"])


class CogneeSearchTests(unittest.IsolatedAsyncioTestCase):

    async def test_search_with_default_search_type(self) -> None:
        """[Edge Case] default search_type is GRAPH_COMPLETION."""
        transport = MockTransport(200, [{"text": "blue sky"}])
        tool = _inject_transport(CogneeSearchTool("ckey"), transport)
        result = await tool.execute(ToolCall("cognee_search", {"query": "sky color"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(transport.last_call["json_body"]["searchType"], "GRAPH_COMPLETION")

    async def test_search_with_custom_search_type_forwarded(self) -> None:
        """[Silent Failure] search_type override is not silently ignored."""
        transport = MockTransport(200, [])
        tool = _inject_transport(CogneeSearchTool("ckey"), transport)
        await tool.execute(ToolCall("cognee_search", {"query": "test", "search_type": "SEMANTIC"}))
        self.assertEqual(transport.last_call["json_body"]["searchType"], "SEMANTIC")

    async def test_search_empty_query_returns_validation_error(self) -> None:
        """[Hidden Assumption] query is always provided."""
        tool = CogneeSearchTool("ckey")
        result = await tool.execute(ToolCall("cognee_search", {}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class CogneeDeleteTests(unittest.IsolatedAsyncioTestCase):

    async def test_delete_dataset_success(self) -> None:
        """[Edge Case] successful dataset delete returns ToolResult.SUCCESS."""
        transport = MockTransport(200, {})
        tool = _inject_transport(CogneeDeleteTool("ckey"), transport)
        result = await tool.execute(ToolCall("cognee_delete", {"dataset_id": "project_alpha"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("project_alpha", result.output)

    async def test_delete_missing_dataset_id_returns_validation_error(self) -> None:
        """[Hidden Assumption] dataset_id is always provided."""
        tool = CogneeDeleteTool("ckey")
        result = await tool.execute(ToolCall("cognee_delete", {}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class LettaAddTests(unittest.IsolatedAsyncioTestCase):

    async def test_add_archival_text_success(self) -> None:
        """[Edge Case] add archival memory returns success with ID."""
        transport = MockTransport(200, {"id": "mem_01", "text": "Alice is a developer"})
        tool = _inject_transport(LettaAddArchivalMemoryTool("lettakey"), transport)
        result = await tool.execute(ToolCall("letta_add_archival_memory", {"agent_id": "agent_1", "text": "Alice is a developer"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)

    async def test_add_missing_agent_id_returns_validation_error(self) -> None:
        """[Hidden Assumption] agent_id is always provided."""
        tool = LettaAddArchivalMemoryTool("lettakey")
        result = await tool.execute(ToolCall("letta_add_archival_memory", {"text": "some text"}))
        self.assertEqual(result.status, ToolStatus.ERROR)

    async def test_add_missing_text_returns_validation_error(self) -> None:
        """[Hidden Assumption] text is always provided."""
        tool = LettaAddArchivalMemoryTool("lettakey")
        result = await tool.execute(ToolCall("letta_add_archival_memory", {"agent_id": "agent_1"}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class LettaSearchTests(unittest.IsolatedAsyncioTestCase):

    async def test_search_returns_passages(self) -> None:
        """[Edge Case] search returns matching archival passages."""
        transport = MockTransport(200, [{"id": "m1", "text": "Alice is a developer"}])
        tool = _inject_transport(LettaSearchArchivalMemoryTool("lettakey"), transport)
        result = await tool.execute(ToolCall("letta_search_archival_memory", {"agent_id": "a1", "query": "Alice"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("m1", result.output)

    async def test_search_limit_param_forwarded_in_query_string(self) -> None:
        """[Silent Failure] limit is not silently dropped from query string."""
        transport = MockTransport(200, [])
        tool = _inject_transport(LettaSearchArchivalMemoryTool("lettakey"), transport)
        await tool.execute(ToolCall("letta_search_archival_memory", {"agent_id": "a1", "query": "test", "limit": 3}))
        self.assertIn("limit=3", transport.last_call["url"])


class LettaDeleteTests(unittest.IsolatedAsyncioTestCase):

    async def test_delete_archival_memory_success(self) -> None:
        """[Edge Case] successful delete returns ToolResult.SUCCESS."""
        transport = MockTransport(200, {})
        tool = _inject_transport(LettaDeleteArchivalMemoryTool("lettakey"), transport)
        result = await tool.execute(ToolCall("letta_delete_archival_memory", {"agent_id": "a1", "memory_id": "m1"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("m1", result.output)

    async def test_delete_missing_memory_id_returns_validation_error(self) -> None:
        """[Hidden Assumption] memory_id is always provided."""
        tool = LettaDeleteArchivalMemoryTool("lettakey")
        result = await tool.execute(ToolCall("letta_delete_archival_memory", {"agent_id": "a1"}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class LettaGetBlockTests(unittest.IsolatedAsyncioTestCase):

    async def test_get_persona_block_returns_value(self) -> None:
        """[Edge Case] reading persona block returns label and value."""
        transport = MockTransport(200, {"label": "persona", "value": "You are a helpful assistant."})
        tool = _inject_transport(LettaGetMemoryBlockTool("lettakey"), transport)
        result = await tool.execute(ToolCall("letta_get_memory_block", {"agent_id": "a1", "block_name": "persona"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("persona", result.output)

    async def test_get_block_non_json_response_returns_error(self) -> None:
        """[Hidden Failure] non-JSON body from Letta causes error, not crash."""
        transport = MockTransport(200, {})
        transport.body = "not json!!"
        tool = _inject_transport(LettaGetMemoryBlockTool("lettakey"), transport)
        result = await tool.execute(ToolCall("letta_get_memory_block", {"agent_id": "a1", "block_name": "persona"}))
        self.assertEqual(result.status, ToolStatus.ERROR)


class SpecTests(unittest.TestCase):

    def test_all_tool_specs_have_names_and_descriptions(self) -> None:
        """[Edge Case] every tool returns a valid ToolSpec."""
        tools = [
            SupermemoryAddMemoryTool("k"), SupermemorySearchMemoryTool("k"), SupermemoryDeleteMemoryTool("k"),
            Mem0AddMemoryTool("k"), Mem0SearchMemoryTool("k"), Mem0GetMemoriesTool("k"), Mem0DeleteMemoryTool("k"),
            ZepAddMemoryTool("k"), ZepGetMemoryTool("k"), ZepSearchMemoryTool("k"), ZepDeleteSessionTool("k"),
            CogneeAddTool("k"), CogneeCognifyTool("k"), CogneeSearchTool("k"), CogneeDeleteTool("k"),
            LettaAddArchivalMemoryTool("k"), LettaSearchArchivalMemoryTool("k"),
            LettaDeleteArchivalMemoryTool("k"), LettaGetMemoryBlockTool("k"),
        ]
        for t in tools:
            spec = t.spec()
            self.assertTrue(spec.name, f"{type(t).__name__} has empty spec name")
            self.assertTrue(spec.description, f"{type(t).__name__} has empty spec description")

    def test_all_tool_names_are_unique(self) -> None:
        """[Silent Failure] duplicate tool names would cause registry conflicts."""
        tools = [
            SupermemoryAddMemoryTool("k"), SupermemorySearchMemoryTool("k"), SupermemoryDeleteMemoryTool("k"),
            Mem0AddMemoryTool("k"), Mem0SearchMemoryTool("k"), Mem0GetMemoriesTool("k"), Mem0DeleteMemoryTool("k"),
            ZepAddMemoryTool("k"), ZepGetMemoryTool("k"), ZepSearchMemoryTool("k"), ZepDeleteSessionTool("k"),
            CogneeAddTool("k"), CogneeCognifyTool("k"), CogneeSearchTool("k"), CogneeDeleteTool("k"),
            LettaAddArchivalMemoryTool("k"), LettaSearchArchivalMemoryTool("k"),
            LettaDeleteArchivalMemoryTool("k"), LettaGetMemoryBlockTool("k"),
        ]
        names = [t.spec().name for t in tools]
        self.assertEqual(len(names), len(set(names)), f"Duplicate tool names found: {names}")


if __name__ == "__main__":
    unittest.main()
