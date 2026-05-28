"""Standalone verification script for memory provider tools.

Run with: python scripts/test-memory-tools.py

Exercises every tool class directly using a mock HttpTransport.
Prints PASS/FAIL per test case and exits non-zero if any fail.
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Mock transport
# ---------------------------------------------------------------------------

@dataclass
class FakeResponse:
    status_code: int
    body: str
    headers: dict


class MockTransport:
    def __init__(self, status: int = 200, body: Any = None, raise_exc: Exception | None = None) -> None:
        self.status = status
        self.body = json.dumps(body or {})
        self.raise_exc = raise_exc
        self.last_call: dict = {}

    def request(self, *, method: str, url: str, headers: Any = None, json_body: Any = None, timeout_seconds: float = 30.0, **kwargs: Any) -> FakeResponse:
        self.last_call = {"method": method, "url": url, "headers": headers or {}, "json_body": json_body}
        if self.raise_exc:
            raise self.raise_exc
        return FakeResponse(status_code=self.status, body=self.body, headers={})


def inject(tool: Any, transport: MockTransport) -> Any:
    tool._transport = transport
    return tool


# ---------------------------------------------------------------------------
# Import tools
# ---------------------------------------------------------------------------

from vidbyte.tools.builtins.memory import (
    CogneeAddTool, CogneeCognifyTool, CogneeDeleteTool, CogneeSearchTool,
    LettaAddArchivalMemoryTool, LettaDeleteArchivalMemoryTool,
    LettaGetMemoryBlockTool, LettaSearchArchivalMemoryTool,
    Mem0AddMemoryTool, Mem0DeleteMemoryTool, Mem0GetMemoriesTool, Mem0SearchMemoryTool,
    SupermemoryAddMemoryTool, SupermemoryDeleteMemoryTool, SupermemorySearchMemoryTool,
    ZepAddMemoryTool, ZepDeleteSessionTool, ZepGetMemoryTool, ZepSearchMemoryTool,
)
from vidbyte.tools.types import ToolCall, ToolStatus


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

passed = 0
failed = 0


def run(name: str, coro) -> None:
    global passed, failed
    try:
        asyncio.run(coro)
        print(f"  PASS  {name}")
        passed += 1
    except Exception:
        print(f"  FAIL  {name}")
        traceback.print_exc()
        failed += 1


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))
        failed += 1


# ---------------------------------------------------------------------------
# Supermemory
# ---------------------------------------------------------------------------

print("\n=== Supermemory ===")


async def smem_add_success():
    t = inject(SupermemoryAddMemoryTool("key"), MockTransport(200, {"id": "doc_1"}))
    r = await t.execute(ToolCall("supermemory_add_memory", {"content": "Alice likes cats"}))
    assert r.status == ToolStatus.SUCCESS and "doc_1" in r.output

run("add_memory_success", smem_add_success())


async def smem_add_missing_content():
    t = SupermemoryAddMemoryTool("key")
    r = await t.execute(ToolCall("supermemory_add_memory", {}))
    assert r.status == ToolStatus.ERROR

run("add_memory_missing_content_returns_error", smem_add_missing_content())


async def smem_add_bearer_auth():
    transport = MockTransport(200, {"id": "x"})
    t = inject(SupermemoryAddMemoryTool("mykey"), transport)
    await t.execute(ToolCall("supermemory_add_memory", {"content": "hi"}))
    assert "Bearer mykey" in transport.last_call["headers"]["authorization"]

run("add_memory_bearer_auth_scheme", smem_add_bearer_auth())


async def smem_add_container_tags():
    transport = MockTransport(200, {"id": "x"})
    t = inject(SupermemoryAddMemoryTool("key"), transport)
    await t.execute(ToolCall("supermemory_add_memory", {"content": "hi", "container_tags": ["u1"]}))
    assert transport.last_call["json_body"]["containerTags"] == ["u1"]

run("add_memory_container_tags_forwarded", smem_add_container_tags())


async def smem_search_success():
    t = inject(SupermemorySearchMemoryTool("key"), MockTransport(200, {"results": [{"id": "d1"}]}))
    r = await t.execute(ToolCall("supermemory_search_memory", {"query": "cats"}))
    assert r.status == ToolStatus.SUCCESS

run("search_memory_success", smem_search_success())


async def smem_search_no_query():
    t = SupermemorySearchMemoryTool("key")
    r = await t.execute(ToolCall("supermemory_search_memory", {}))
    assert r.status == ToolStatus.ERROR

run("search_memory_missing_query_error", smem_search_no_query())


async def smem_delete_success():
    t = inject(SupermemoryDeleteMemoryTool("key"), MockTransport(200, {}))
    r = await t.execute(ToolCall("supermemory_delete_memory", {"document_id": "doc_abc"}))
    assert r.status == ToolStatus.SUCCESS and "doc_abc" in r.output

run("delete_memory_success", smem_delete_success())


async def smem_delete_404():
    t = inject(SupermemoryDeleteMemoryTool("key"), MockTransport(404, {}))
    r = await t.execute(ToolCall("supermemory_delete_memory", {"document_id": "bad"}))
    assert r.status == ToolStatus.ERROR

run("delete_memory_404_returns_error", smem_delete_404())

try:
    SupermemoryAddMemoryTool("")
    check("empty_api_key_raises_ValueError", False, "no ValueError raised")
except ValueError:
    check("empty_api_key_raises_ValueError", True)


# ---------------------------------------------------------------------------
# Mem0
# ---------------------------------------------------------------------------

print("\n=== Mem0 ===")


async def mem0_add_success():
    t = inject(Mem0AddMemoryTool("m0key"), MockTransport(200, {"event_id": "e1"}))
    r = await t.execute(ToolCall("mem0_add_memory", {
        "messages": [{"role": "user", "content": "hi"}], "user_id": "u1",
    }))
    assert r.status == ToolStatus.SUCCESS

run("add_memory_success", mem0_add_success())


async def mem0_add_token_auth():
    transport = MockTransport(200, {})
    t = inject(Mem0AddMemoryTool("m0key"), transport)
    await t.execute(ToolCall("mem0_add_memory", {"messages": [{"role": "user", "content": "hi"}]}))
    assert "Token m0key" in transport.last_call["headers"]["authorization"]

run("add_memory_token_auth_scheme", mem0_add_token_auth())


async def mem0_add_empty_messages():
    t = Mem0AddMemoryTool("m0key")
    r = await t.execute(ToolCall("mem0_add_memory", {"messages": []}))
    assert r.status == ToolStatus.ERROR

run("add_memory_empty_messages_error", mem0_add_empty_messages())


async def mem0_search():
    transport = MockTransport(200, {"results": [{"id": "m1"}]})
    t = inject(Mem0SearchMemoryTool("m0key"), transport)
    r = await t.execute(ToolCall("mem0_search_memory", {"query": "cats", "user_id": "u1"}))
    assert r.status == ToolStatus.SUCCESS

run("search_memory_success", mem0_search())


async def mem0_get_pagination():
    transport = MockTransport(200, {"results": []})
    t = inject(Mem0GetMemoriesTool("m0key"), transport)
    await t.execute(ToolCall("mem0_get_memories", {"user_id": "bob", "page": 2, "page_size": 5}))
    assert "page=2" in transport.last_call["url"] and "page_size=5" in transport.last_call["url"]

run("get_memories_pagination_forwarded", mem0_get_pagination())


async def mem0_delete():
    t = inject(Mem0DeleteMemoryTool("m0key"), MockTransport(200, {}))
    r = await t.execute(ToolCall("mem0_delete_memory", {"memory_id": "mx"}))
    assert r.status == ToolStatus.SUCCESS and "mx" in r.output

run("delete_memory_success", mem0_delete())


# ---------------------------------------------------------------------------
# Zep
# ---------------------------------------------------------------------------

print("\n=== Zep ===")


async def zep_add_success():
    t = inject(ZepAddMemoryTool("zkey"), MockTransport(200, {}))
    r = await t.execute(ToolCall("zep_add_memory", {
        "session_id": "s1",
        "messages": [{"role": "human", "role_type": "human", "content": "hi"}],
    }))
    assert r.status == ToolStatus.SUCCESS and "s1" in r.output

run("add_memory_success", zep_add_success())


async def zep_add_api_key_scheme():
    transport = MockTransport(200, {})
    t = inject(ZepAddMemoryTool("zkey"), transport)
    await t.execute(ToolCall("zep_add_memory", {
        "session_id": "s1",
        "messages": [{"role": "human", "content": "hi"}],
    }))
    assert "Api-Key zkey" in transport.last_call["headers"]["authorization"]

run("add_memory_api_key_auth_scheme", zep_add_api_key_scheme())


async def zep_add_empty_messages():
    t = ZepAddMemoryTool("zkey")
    r = await t.execute(ToolCall("zep_add_memory", {"session_id": "s1", "messages": []}))
    assert r.status == ToolStatus.ERROR

run("add_memory_empty_messages_error", zep_add_empty_messages())


async def zep_get_context():
    t = inject(ZepGetMemoryTool("zkey"), MockTransport(200, {"context": "Alice is a developer."}))
    r = await t.execute(ToolCall("zep_get_memory", {"session_id": "s1"}))
    assert r.status == ToolStatus.SUCCESS and "Alice" in r.output

run("get_memory_context_string", zep_get_context())


async def zep_search_limit():
    transport = MockTransport(200, {"results": []})
    t = inject(ZepSearchMemoryTool("zkey"), transport)
    await t.execute(ToolCall("zep_search_memory", {"session_id": "s1", "text": "cats", "limit": 3}))
    assert transport.last_call["json_body"]["limit"] == 3

run("search_memory_limit_forwarded", zep_search_limit())


async def zep_delete():
    t = inject(ZepDeleteSessionTool("zkey"), MockTransport(200, {}))
    r = await t.execute(ToolCall("zep_delete_session", {"session_id": "s1"}))
    assert r.status == ToolStatus.SUCCESS and "s1" in r.output

run("delete_session_success", zep_delete())


# ---------------------------------------------------------------------------
# Cognee
# ---------------------------------------------------------------------------

print("\n=== Cognee ===")


async def cog_add_default_dataset():
    transport = MockTransport(200, {"status": "ok"})
    t = inject(CogneeAddTool("ckey"), transport)
    r = await t.execute(ToolCall("cognee_add", {"content": "sky is blue"}))
    assert r.status == ToolStatus.SUCCESS
    assert transport.last_call["json_body"]["datasetId"] == "default"

run("add_to_default_dataset", cog_add_default_dataset())


async def cog_add_custom_dataset():
    transport = MockTransport(200, {})
    t = inject(CogneeAddTool("ckey"), transport)
    await t.execute(ToolCall("cognee_add", {"content": "text", "dataset_id": "proj_alpha"}))
    assert transport.last_call["json_body"]["datasetId"] == "proj_alpha"

run("add_custom_dataset_forwarded", cog_add_custom_dataset())


async def cog_cognify():
    transport = MockTransport(200, {"status": "cognifying"})
    t = inject(CogneeCognifyTool("ckey"), transport)
    r = await t.execute(ToolCall("cognee_cognify", {}))
    assert r.status == ToolStatus.SUCCESS
    assert "/api/v1/cognify" in transport.last_call["url"]

run("cognify_triggers_graph_build", cog_cognify())


async def cog_search_default_type():
    transport = MockTransport(200, [{"text": "blue sky"}])
    t = inject(CogneeSearchTool("ckey"), transport)
    r = await t.execute(ToolCall("cognee_search", {"query": "sky"}))
    assert r.status == ToolStatus.SUCCESS
    assert transport.last_call["json_body"]["searchType"] == "GRAPH_COMPLETION"

run("search_default_search_type", cog_search_default_type())


async def cog_search_custom_type():
    transport = MockTransport(200, [])
    t = inject(CogneeSearchTool("ckey"), transport)
    await t.execute(ToolCall("cognee_search", {"query": "test", "search_type": "SEMANTIC"}))
    assert transport.last_call["json_body"]["searchType"] == "SEMANTIC"

run("search_custom_type_forwarded", cog_search_custom_type())


async def cog_delete():
    t = inject(CogneeDeleteTool("ckey"), MockTransport(200, {}))
    r = await t.execute(ToolCall("cognee_delete", {"dataset_id": "proj_alpha"}))
    assert r.status == ToolStatus.SUCCESS and "proj_alpha" in r.output

run("delete_dataset_success", cog_delete())


# ---------------------------------------------------------------------------
# Letta
# ---------------------------------------------------------------------------

print("\n=== Letta ===")


async def letta_add():
    t = inject(LettaAddArchivalMemoryTool("lkey"), MockTransport(200, {"id": "m1", "text": "hi"}))
    r = await t.execute(ToolCall("letta_add_archival_memory", {"agent_id": "a1", "text": "Alice is a dev"}))
    assert r.status == ToolStatus.SUCCESS

run("add_archival_memory_success", letta_add())


async def letta_add_missing_agent():
    t = LettaAddArchivalMemoryTool("lkey")
    r = await t.execute(ToolCall("letta_add_archival_memory", {"text": "hi"}))
    assert r.status == ToolStatus.ERROR

run("add_archival_missing_agent_id_error", letta_add_missing_agent())


async def letta_search():
    transport = MockTransport(200, [{"id": "m1", "text": "Alice"}])
    t = inject(LettaSearchArchivalMemoryTool("lkey"), transport)
    r = await t.execute(ToolCall("letta_search_archival_memory", {"agent_id": "a1", "query": "Alice"}))
    assert r.status == ToolStatus.SUCCESS and "m1" in r.output

run("search_archival_memory_success", letta_search())


async def letta_search_limit():
    transport = MockTransport(200, [])
    t = inject(LettaSearchArchivalMemoryTool("lkey"), transport)
    await t.execute(ToolCall("letta_search_archival_memory", {"agent_id": "a1", "query": "test", "limit": 3}))
    assert "limit=3" in transport.last_call["url"]

run("search_archival_limit_in_query_string", letta_search_limit())


async def letta_delete():
    t = inject(LettaDeleteArchivalMemoryTool("lkey"), MockTransport(200, {}))
    r = await t.execute(ToolCall("letta_delete_archival_memory", {"agent_id": "a1", "memory_id": "m1"}))
    assert r.status == ToolStatus.SUCCESS and "m1" in r.output

run("delete_archival_memory_success", letta_delete())


async def letta_get_block():
    t = inject(LettaGetMemoryBlockTool("lkey"), MockTransport(200, {"label": "persona", "value": "You are helpful."}))
    r = await t.execute(ToolCall("letta_get_memory_block", {"agent_id": "a1", "block_name": "persona"}))
    assert r.status == ToolStatus.SUCCESS and "persona" in r.output

run("get_memory_block_success", letta_get_block())


async def letta_get_block_bad_json():
    transport = MockTransport(200, {})
    transport.body = "not json!"
    t = inject(LettaGetMemoryBlockTool("lkey"), transport)
    r = await t.execute(ToolCall("letta_get_memory_block", {"agent_id": "a1", "block_name": "persona"}))
    assert r.status == ToolStatus.ERROR

run("get_memory_block_non_json_returns_error", letta_get_block_bad_json())


# ---------------------------------------------------------------------------
# Cross-provider spec integrity
# ---------------------------------------------------------------------------

print("\n=== Spec integrity ===")

all_tools = [
    SupermemoryAddMemoryTool("k"), SupermemorySearchMemoryTool("k"), SupermemoryDeleteMemoryTool("k"),
    Mem0AddMemoryTool("k"), Mem0SearchMemoryTool("k"), Mem0GetMemoriesTool("k"), Mem0DeleteMemoryTool("k"),
    ZepAddMemoryTool("k"), ZepGetMemoryTool("k"), ZepSearchMemoryTool("k"), ZepDeleteSessionTool("k"),
    CogneeAddTool("k"), CogneeCognifyTool("k"), CogneeSearchTool("k"), CogneeDeleteTool("k"),
    LettaAddArchivalMemoryTool("k"), LettaSearchArchivalMemoryTool("k"),
    LettaDeleteArchivalMemoryTool("k"), LettaGetMemoryBlockTool("k"),
]

check("all_19_tools_importable", len(all_tools) == 19, f"got {len(all_tools)}")

names = [t.spec().name for t in all_tools]
check("all_tool_names_unique", len(names) == len(set(names)), f"duplicates: {[n for n in names if names.count(n) > 1]}")

for t in all_tools:
    spec = t.spec()
    check(f"spec_valid_{spec.name}", bool(spec.name) and bool(spec.description))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

total = passed + failed
print(f"\n{'='*50}")
print(f"{passed}/{total} tests passed")

sys.exit(0 if failed == 0 else 1)
