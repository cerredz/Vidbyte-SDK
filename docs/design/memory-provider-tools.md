# Design Doc: Memory Provider Tools

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-28
**Last Updated:** 2026-05-28

---

## 1. Overview

This feature adds a `vidbyte/tools/builtins/memory/` namespace to the Vidbyte SDK exposing plug-and-play `BaseTool` subclasses for five major managed-memory platforms: **Supermemory**, **Mem0**, **Zep**, **Cognee**, and **Letta**. Each provider gets a dedicated module with three to four tools (add, search, delete, and optionally list/get). Developers pass an API key to any tool's constructor and attach it to an agent's `tools=[...]` list; the model can then persist, retrieve, and delete memories via third-party infrastructure without the SDK having to own or store any persistent state.

---

## 2. Goals & Non-Goals

### Goals
- Expose `BaseTool` subclasses for Supermemory, Mem0, Zep, Cognee, and Letta following exactly the same conventions as existing builtins
- Use only the stdlib `HttpTransport` already present in `vidbyte.lib.http`; add zero new required dependencies
- Accept API keys as constructor arguments (never read them from `os.environ` inside the tool itself — let callers inject them)
- Export all tools from `vidbyte.tools.builtins.memory` and from `vidbyte.tools.builtins`
- Cover add/store, search/retrieve, and delete operations for every provider
- Write a full `tests/test_memory_tools.py` with mocked HTTP and a runnable `scripts/test-memory-tools.py`

### Non-Goals
- Implementing a custom memory store inside the SDK (no vector DB, no embeddings)
- Installing provider-specific Python SDK packages as required dependencies
- Supporting streaming or webhook-based memory operations
- Authentication flows (OAuth, device-flow) — API key only
- Automatic memory extraction from agent conversation history (callers invoke tools explicitly or the model does)
- Supporting every optional parameter each provider API exposes (core CRUD only)

---

## 3. Background & Context

Persistent memory is one of the most-requested capabilities for production AI agents. Vidbyte's existing agent runtime (`vidbyte/agents/runtime.py`) has no memory layer — each `arun()` call starts with a blank context. Developers who need agents to remember user facts, session history, or learned preferences must today wire external memory systems themselves.

The SDK already provides a rich `tools/builtins/` namespace. Adding memory provider tools here gives developers a one-line upgrade path: `tools=[Mem0AddMemoryTool(api_key=...), Mem0SearchMemoryTool(api_key=...)]`. No new SDK primitives are needed — `BaseTool` + `HttpTransport` are sufficient.

Five providers were selected based on a 2026 landscape survey:

| Provider | Memory model | Target use case | API style |
|----------|-------------|-----------------|-----------|
| Supermemory | Semantic + temporal traces | Coding & general agents | Managed cloud REST |
| Mem0 | Vector + graph + KV, multi-scope | Personalization agents | Managed cloud REST |
| Zep | Temporal knowledge graph | Enterprise / temporal reasoning | Managed cloud REST |
| Cognee | Knowledge graph from unstructured data | Graph-reasoning agents | Self-hosted or cloud REST |
| Letta | Stateful memory blocks + archival | Long-running stateful agents | Managed cloud or self-hosted REST |

---

## 4. Requirements

### Functional Requirements
1. `SupermemoryAddMemoryTool(api_key)` — POST a document to Supermemory v3 API with content, optional container tags, and optional metadata.
2. `SupermemorySearchMemoryTool(api_key)` — POST a semantic search query to Supermemory v3 and return matching document excerpts.
3. `SupermemoryDeleteMemoryTool(api_key)` — DELETE a document by its Supermemory document ID.
4. `Mem0AddMemoryTool(api_key)` — POST messages to Mem0 v3 API scoped by user_id/agent_id/run_id.
5. `Mem0SearchMemoryTool(api_key)` — POST a search query to Mem0 v1 scoped by the same entity IDs.
6. `Mem0GetMemoriesTool(api_key)` — GET all memories for a given entity scope.
7. `Mem0DeleteMemoryTool(api_key)` — DELETE a memory entry by ID.
8. `ZepAddMemoryTool(api_key)` — POST messages to a Zep session, creating the session first if necessary.
9. `ZepGetMemoryTool(api_key)` — GET the context string and relevant facts for a Zep session.
10. `ZepSearchMemoryTool(api_key)` — POST a text search against a Zep session's memory graph.
11. `ZepDeleteSessionTool(api_key)` — DELETE a Zep session and its accumulated memory.
12. `CogneeAddTool(api_key, base_url)` — POST data to Cognee's `/api/v1/add` endpoint.
13. `CogneeCognifyTool(api_key, base_url)` — POST to `/api/v1/cognify` to build the knowledge graph from ingested data.
14. `CogneeSearchTool(api_key, base_url)` — POST a query to `/api/v1/search` with a configurable search type.
15. `CogneeDeleteTool(api_key, base_url)` — DELETE a Cognee dataset by ID.
16. `LettaAddArchivalMemoryTool(api_key, base_url)` — POST a text passage to a Letta agent's archival memory store.
17. `LettaSearchArchivalMemoryTool(api_key, base_url)` — GET archival memory entries matching a query for a given agent.
18. `LettaDeleteArchivalMemoryTool(api_key, base_url)` — DELETE an archival memory passage by ID.
19. `LettaGetMemoryBlockTool(api_key, base_url)` — GET the value of a named in-context memory block for a Letta agent.
20. All tools must return `ToolResult.success(...)` on success and `ToolResult.error(...)` on any HTTP or parse error, never raise.
21. All tools must validate required parameters via `BaseTool.validate_call()` before making HTTP calls.

### Non-Functional Requirements
- No provider-specific library imports; only stdlib + `vidbyte.lib.http.HttpTransport`
- `ToolPermission.WRITE` on all add/delete tools; `ToolPermission.READ` on all search/get tools
- HTTP timeout defaults to 30 seconds, exposed as an optional constructor argument `timeout_seconds`
- All JSON parsing errors are caught and surfaced as `ToolResult.error`
- Tools are importable in isolation without side effects (no network calls at import time)

---

## 5. High-Level Design

A new `vidbyte/tools/builtins/memory/` package is created following the same layout as `vidbyte/tools/builtins/code_search/`. A `BaseMemoryTool` in `base.py` extends `BaseTool`, holds a single `HttpTransport` instance, and provides two helpers: `_json_post()` and `_json_delete()`. Each provider module (`supermemory.py`, `mem0.py`, `zep.py`, `cognee.py`, `letta.py`) imports `BaseMemoryTool` and defines its tools using only those helpers plus stdlib `json`.

```
[Agent tools=[...]] 
    -> [SupermemoryAddMemoryTool.execute(call)]
        -> [BaseMemoryTool._json_post(url, headers, body)]
            -> [HttpTransport.request(...)]
                -> [https://api.supermemory.ai/v3/documents]
    -> ToolResult.success / ToolResult.error
```

Data flows in one direction: tool receives `ToolCall`, constructs an HTTP request, parses the JSON response, and returns a `ToolResult`. There is no shared state between tool instances or across calls. API keys are stored as instance variables set in `__init__` and never written to logs or metadata.

The existing `vidbyte/tools/builtins/__init__.py` is updated to re-export all memory tools so callers can import from a single namespace. The `vidbyte/tools/builtins/memory/__init__.py` exports the full flat list of 19 tool classes.

No changes to `pyproject.toml` are needed — `HttpTransport` uses only `urllib.request` from stdlib.

---

## 6. Detailed Design

### 6.1 BaseMemoryTool

**File:** `vidbyte/tools/builtins/memory/base.py`
**Type:** New file

#### What it does
Shared base for all memory provider tools. Holds one `HttpTransport`, provides `_json_post()`, `_json_get()`, and `_json_delete()` helpers that build the request, decode the response, and normalize errors into `ToolResult.error` values. Subclasses only need to build the `url`, `headers`, and `body` dicts.

#### Interface / API
```python
class BaseMemoryTool(BaseTool):
    def __init__(self, api_key: str, base_url: str, timeout_seconds: float = 30.0) -> None: ...
    def _auth_headers(self, scheme: str = "Bearer") -> dict[str, str]: ...
    async def _json_post(self, url: str, headers: dict, body: dict) -> tuple[int, dict]: ...
    async def _json_get(self, url: str, headers: dict, params: dict | None = None) -> tuple[int, dict]: ...
    async def _json_delete(self, url: str, headers: dict) -> tuple[int, dict]: ...
    def _ok(self, status: int) -> bool: ...
```

#### Logic / Algorithm
1. `__init__` stores `api_key`, `base_url` (stripped of trailing `/`), `timeout_seconds`, and creates `HttpTransport()`.
2. `_auth_headers(scheme)` returns `{"authorization": f"{scheme} {self.api_key}"}`.
3. `_json_post` calls `self._transport.request(method="POST", url=url, headers=headers, json_body=body, timeout_seconds=self.timeout_seconds)`, decodes `response.body` with `json.loads`, returns `(status_code, parsed_dict)`.
4. `_json_get` appends `params` as query string using `urllib.parse.urlencode`, calls `GET`.
5. `_json_delete` calls `DELETE`.
6. `_ok(status)` returns `200 <= status < 300`.
7. All JSON parse errors are caught and re-raised as `RuntimeError` — callers wrap in `ToolResult.error`.

#### Edge Cases & Error Handling
- Network failure: `HttpTransport` raises `ProviderRequestError`; each tool's `execute()` catches all exceptions and returns `ToolResult.error`.
- Non-JSON response body: `json.loads` raises `json.JSONDecodeError`; caught by the tool.
- `api_key` empty string: constructor raises `ValueError` immediately, before any tool call.

---

### 6.2 Supermemory Tools

**File:** `vidbyte/tools/builtins/memory/supermemory.py`
**Type:** New file

#### What it does
Three tools wrapping the Supermemory v3 managed REST API (`https://api.supermemory.ai`).

#### Interface / API
```python
class SupermemoryAddMemoryTool(BaseMemoryTool):
    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None: ...
    def spec(self) -> ToolSpec: ...  # name="supermemory_add_memory"
    async def execute(self, call: ToolCall) -> ToolResult: ...

class SupermemorySearchMemoryTool(BaseMemoryTool):
    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None: ...
    def spec(self) -> ToolSpec: ...  # name="supermemory_search_memory"
    async def execute(self, call: ToolCall) -> ToolResult: ...

class SupermemoryDeleteMemoryTool(BaseMemoryTool):
    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None: ...
    def spec(self) -> ToolSpec: ...  # name="supermemory_delete_memory"
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

#### Logic / Algorithm

**SupermemoryAddMemoryTool.execute:**
1. Extract `content` (required), `container_tags` (optional list[str]), `metadata` (optional dict), `custom_id` (optional str) from call.arguments.
2. Build body: `{"content": content, "containerTags": container_tags or [], "metadata": metadata or {}}`, add `customId` if present.
3. POST to `{base_url}/v3/documents` with `Authorization: Bearer {api_key}`.
4. On 2xx: return `ToolResult.success` with JSON-serialized response.
5. On non-2xx: return `ToolResult.error` with `status_code` and response body.

**SupermemorySearchMemoryTool.execute:**
1. Extract `query` (required), `container_tag` (optional str), `top_k` (optional int, default 10).
2. Build body: `{"query": query, "containerTag": container_tag, "limit": top_k}`.
3. POST to `{base_url}/v3/search`.
4. Parse `results` array from response and return JSON string.

**SupermemoryDeleteMemoryTool.execute:**
1. Extract `document_id` (required).
2. DELETE `{base_url}/v3/documents/{document_id}`.
3. Return success or error based on status.

#### Parameters

| Tool | Parameter | Type | Required |
|------|-----------|------|----------|
| Add | content | string | yes |
| Add | container_tags | array | no |
| Add | metadata | object | no |
| Add | custom_id | string | no |
| Search | query | string | yes |
| Search | container_tag | string | no |
| Search | top_k | integer | no (default 10) |
| Delete | document_id | string | yes |

---

### 6.3 Mem0 Tools

**File:** `vidbyte/tools/builtins/memory/mem0.py`
**Type:** New file

#### What it does
Four tools wrapping the Mem0 managed cloud API (`https://api.mem0.ai`). Uses `Authorization: Token <api_key>` per Mem0's scheme.

#### Interface / API
```python
class Mem0AddMemoryTool(BaseMemoryTool):        # name="mem0_add_memory"
class Mem0SearchMemoryTool(BaseMemoryTool):     # name="mem0_search_memory"
class Mem0GetMemoriesTool(BaseMemoryTool):      # name="mem0_get_memories"
class Mem0DeleteMemoryTool(BaseMemoryTool):     # name="mem0_delete_memory"
```

#### Logic / Algorithm

**Mem0AddMemoryTool.execute:**
1. Extract `messages` (required, list of dicts with role/content), `user_id` (optional), `agent_id` (optional), `run_id` (optional). At least one entity ID recommended.
2. POST to `{base_url}/v3/memories/add/` with `Authorization: Token {api_key}`.
3. Return `ToolResult.success` with response JSON.

**Mem0SearchMemoryTool.execute:**
1. Extract `query` (required), `user_id`, `agent_id`, `run_id`, `limit` (default 10).
2. POST to `{base_url}/v1/memories/search/` with body `{"query": query, "user_id": ..., "limit": limit}`.
3. Parse and return `results` array.

**Mem0GetMemoriesTool.execute:**
1. Extract `user_id` (required), `page` (default 1), `page_size` (default 10).
2. GET `{base_url}/v1/memories/?user_id={user_id}&page={page}&page_size={page_size}`.
3. Return memory list as JSON.

**Mem0DeleteMemoryTool.execute:**
1. Extract `memory_id` (required).
2. DELETE `{base_url}/v1/memories/{memory_id}/`.

---

### 6.4 Zep Tools

**File:** `vidbyte/tools/builtins/memory/zep.py`
**Type:** New file

#### What it does
Four tools wrapping the Zep Cloud API (`https://api.getzep.com`). Zep organizes memory around sessions. Uses `Authorization: Api-Key {api_key}`.

#### Interface / API
```python
class ZepAddMemoryTool(BaseMemoryTool):     # name="zep_add_memory"
class ZepGetMemoryTool(BaseMemoryTool):     # name="zep_get_memory"
class ZepSearchMemoryTool(BaseMemoryTool):  # name="zep_search_memory"
class ZepDeleteSessionTool(BaseMemoryTool): # name="zep_delete_session"
```

#### Logic / Algorithm

**ZepAddMemoryTool.execute:**
1. Extract `session_id` (required), `messages` (required, list of role/content/role_type dicts).
2. POST to `{base_url}/api/v2/sessions/{session_id}/memory` with body `{"messages": messages}`.
3. Zep auto-creates the session if it does not exist (returns 200 or 201).
4. Return `ToolResult.success` with session_id and message count.

**ZepGetMemoryTool.execute:**
1. Extract `session_id` (required), `lastn` (optional int, number of recent messages to include in context).
2. GET `{base_url}/api/v2/sessions/{session_id}/memory?lastn={lastn}`.
3. Return the `context` string from the response (the formatted memory ready for injection).

**ZepSearchMemoryTool.execute:**
1. Extract `session_id` (required), `text` (required), `limit` (default 5).
2. POST to `{base_url}/api/v2/sessions/{session_id}/memory/search` with body `{"text": text, "limit": limit}`.
3. Parse and return `results` array.

**ZepDeleteSessionTool.execute:**
1. Extract `session_id` (required).
2. DELETE `{base_url}/api/v2/sessions/{session_id}`.

---

### 6.5 Cognee Tools

**File:** `vidbyte/tools/builtins/memory/cognee.py`
**Type:** New file

#### What it does
Four tools wrapping the Cognee REST API, which is typically self-hosted (default `http://localhost:8000`) but can be pointed at Cognee Cloud. Takes `base_url` as a constructor argument.

#### Interface / API
```python
class CogneeAddTool(BaseMemoryTool):      # name="cognee_add"
class CogneeCognifyTool(BaseMemoryTool):  # name="cognee_cognify"
class CogneeSearchTool(BaseMemoryTool):   # name="cognee_search"
class CogneeDeleteTool(BaseMemoryTool):   # name="cognee_delete"
```

#### Logic / Algorithm

**CogneeAddTool.execute:**
1. Extract `content` (required, text string), `dataset_id` (optional, defaults to "default").
2. POST to `{base_url}/api/v1/add` with body `{"data": content, "datasetId": dataset_id}`.
3. Return success with response.

**CogneeCognifyTool.execute:**
1. Extract `dataset_id` (optional, defaults to "default").
2. POST to `{base_url}/api/v1/cognify` with body `{"datasetId": dataset_id}`.
3. Triggers knowledge graph construction from previously added data.

**CogneeSearchTool.execute:**
1. Extract `query` (required), `search_type` (optional, default "GRAPH_COMPLETION"), `dataset_id` (optional).
2. POST to `{base_url}/api/v1/search` with body `{"query": query, "searchType": search_type, "datasetId": dataset_id}`.
3. Return search results array.

**CogneeDeleteTool.execute:**
1. Extract `dataset_id` (required).
2. DELETE `{base_url}/api/v1/datasets/{dataset_id}/`.

---

### 6.6 Letta Tools

**File:** `vidbyte/tools/builtins/memory/letta.py`
**Type:** New file

#### What it does
Four tools wrapping the Letta Cloud API (default `https://api.letta.com`) for managing agent archival memory and in-context memory blocks. Takes `base_url` as a constructor argument.

#### Interface / API
```python
class LettaAddArchivalMemoryTool(BaseMemoryTool):    # name="letta_add_archival_memory"
class LettaSearchArchivalMemoryTool(BaseMemoryTool): # name="letta_search_archival_memory"
class LettaDeleteArchivalMemoryTool(BaseMemoryTool): # name="letta_delete_archival_memory"
class LettaGetMemoryBlockTool(BaseMemoryTool):       # name="letta_get_memory_block"
```

#### Logic / Algorithm

**LettaAddArchivalMemoryTool.execute:**
1. Extract `agent_id` (required), `text` (required).
2. POST to `{base_url}/v1/agents/{agent_id}/archival-memory` with body `{"text": text}`.
3. Return success with created memory ID.

**LettaSearchArchivalMemoryTool.execute:**
1. Extract `agent_id` (required), `query` (required), `limit` (default 10).
2. GET `{base_url}/v1/agents/{agent_id}/archival-memory?query={query}&limit={limit}`.
3. Return matching passages list.

**LettaDeleteArchivalMemoryTool.execute:**
1. Extract `agent_id` (required), `memory_id` (required).
2. DELETE `{base_url}/v1/agents/{agent_id}/archival-memory/{memory_id}`.

**LettaGetMemoryBlockTool.execute:**
1. Extract `agent_id` (required), `block_name` (required, e.g. "persona", "human").
2. GET `{base_url}/v1/agents/{agent_id}/memory/block/{block_name}`.
3. Return block label and value.

---

### 6.7 Memory Package Init

**File:** `vidbyte/tools/builtins/memory/__init__.py`
**Type:** New file

Exports all 19 tool classes under the flat namespace. Developers can do:
```python
from vidbyte.tools.builtins.memory import Mem0AddMemoryTool, ZepSearchMemoryTool
```

### 6.8 Builtins Init Update

**File:** `vidbyte/tools/builtins/__init__.py`
**Type:** Modified

Adds re-exports of all 19 memory tool classes alongside existing exports.

---

## 7. Data Model Changes

N/A — No schema changes. This feature adds stateless tool classes that proxy to external APIs. No local database or data model is introduced.

---

## 8. API Changes

N/A — This is a library feature with no server-side HTTP endpoints. The tools themselves call third-party REST APIs.

External APIs consumed (reference):

| Provider | Base URL | Auth Scheme |
|----------|----------|-------------|
| Supermemory | `https://api.supermemory.ai` | `Authorization: Bearer <key>` |
| Mem0 | `https://api.mem0.ai` | `Authorization: Token <key>` |
| Zep | `https://api.getzep.com` | `Authorization: Api-Key <key>` |
| Cognee | configurable (default `http://localhost:8000`) | `Authorization: Bearer <key>` |
| Letta | configurable (default `https://api.letta.com`) | `Authorization: Bearer <key>` |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/memory-provider-tools.md` | This design doc |
| CREATE | `vidbyte/tools/builtins/memory/__init__.py` | Package init, exports all 19 tool classes |
| CREATE | `vidbyte/tools/builtins/memory/base.py` | BaseMemoryTool with HttpTransport helpers |
| CREATE | `vidbyte/tools/builtins/memory/supermemory.py` | 3 Supermemory tools |
| CREATE | `vidbyte/tools/builtins/memory/mem0.py` | 4 Mem0 tools |
| CREATE | `vidbyte/tools/builtins/memory/zep.py` | 4 Zep tools |
| CREATE | `vidbyte/tools/builtins/memory/cognee.py` | 4 Cognee tools |
| CREATE | `vidbyte/tools/builtins/memory/letta.py` | 4 Letta tools |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Add memory tool re-exports |
| CREATE | `tests/test_memory_tools.py` | Unit tests with mocked HTTP |
| CREATE | `scripts/test-memory-tools.py` | Runnable verification script |

Total: 10 new files, 1 modified file.

---

## 10. Testing Plan

### Unit Tests (`tests/test_memory_tools.py`)

All tests use `unittest.IsolatedAsyncioTestCase` with a `MockHttpTransport` that can be configured to return arbitrary `HttpResponse` objects. No real HTTP calls are made.

**SupermemoryAddMemoryTool:**
- `test_add_memory_success_returns_tool_result_success` — [Edge Case: happy path verified against spec]
- `test_add_memory_missing_content_returns_error` — [Hidden Assumption: content is always supplied]
- `test_add_memory_api_error_404_returns_tool_result_error` — [Silent Failure: non-2xx swallowed silently]
- `test_add_memory_non_json_response_returns_error` — [Hidden Failure: provider returns HTML error page]
- `test_add_memory_network_exception_returns_error` — [Hidden Failure: ProviderRequestError from transport]
- `test_add_memory_empty_api_key_raises_at_construction` — [Hidden Assumption: api_key is always valid]
- `test_add_memory_container_tags_forwarded_correctly` — [Silent Failure: tags silently dropped]

**SupermemorySearchMemoryTool:**
- `test_search_returns_results_on_success` — [Edge Case]
- `test_search_empty_results_array_returns_success` — [Edge Case: no results is not an error]
- `test_search_missing_query_returns_validation_error` — [Hidden Assumption]

**SupermemoryDeleteMemoryTool:**
- `test_delete_success_returns_success` — [Edge Case]
- `test_delete_nonexistent_id_returns_error` — [Hidden Assumption: ID always exists]

**Mem0AddMemoryTool:**
- `test_add_memory_with_user_id_succeeds` — [Edge Case]
- `test_add_memory_messages_list_empty_returns_error` — [Edge Case: zero-length messages]
- `test_add_memory_uses_token_auth_scheme_not_bearer` — [Silent Failure: wrong auth header causes silent 401]
- `test_add_memory_api_500_returns_tool_result_error` — [Hidden Failure]

**Mem0SearchMemoryTool:**
- `test_search_with_user_id_and_agent_id_both_included` — [Edge Case: both scopes]
- `test_search_empty_query_returns_validation_error` — [Hidden Assumption]

**Mem0GetMemoriesTool:**
- `test_get_memories_pagination_params_forwarded` — [Silent Failure: pagination silently ignored]
- `test_get_memories_missing_user_id_returns_error` — [Hidden Assumption]

**Mem0DeleteMemoryTool:**
- `test_delete_by_id_success` — [Edge Case]
- `test_delete_nonexistent_id_returns_error` — [Hidden Assumption]

**ZepAddMemoryTool:**
- `test_add_messages_to_session_success` — [Edge Case]
- `test_add_empty_messages_list_returns_error` — [Edge Case: zero messages]
- `test_add_missing_session_id_returns_validation_error` — [Hidden Assumption]
- `test_add_uses_api_key_auth_scheme` — [Silent Failure: wrong auth scheme]

**ZepGetMemoryTool:**
- `test_get_returns_context_string` — [Edge Case]
- `test_get_missing_session_id_returns_error` — [Hidden Assumption]

**ZepSearchMemoryTool:**
- `test_search_with_limit_forwarded` — [Silent Failure: limit silently ignored]
- `test_search_missing_text_returns_validation_error` — [Hidden Assumption]

**ZepDeleteSessionTool:**
- `test_delete_session_success` — [Edge Case]
- `test_delete_session_404_returns_error` — [Hidden Assumption: session always exists]

**CogneeAddTool:**
- `test_add_content_to_default_dataset` — [Edge Case]
- `test_add_content_to_named_dataset` — [Edge Case: custom dataset_id]
- `test_add_with_custom_base_url` — [Hidden Assumption: default base URL always correct]

**CogneeCognifyTool:**
- `test_cognify_triggers_graph_build` — [Edge Case]

**CogneeSearchTool:**
- `test_search_with_default_search_type` — [Edge Case]
- `test_search_with_custom_search_type_forwarded` — [Silent Failure: search_type silently ignored]
- `test_search_empty_query_returns_validation_error` — [Hidden Assumption]

**CogneeDeleteTool:**
- `test_delete_dataset_success` — [Edge Case]
- `test_delete_missing_dataset_id_returns_validation_error` — [Hidden Assumption]

**LettaAddArchivalMemoryTool:**
- `test_add_archival_text_success` — [Edge Case]
- `test_add_missing_agent_id_returns_validation_error` — [Hidden Assumption]
- `test_add_missing_text_returns_validation_error` — [Hidden Assumption]

**LettaSearchArchivalMemoryTool:**
- `test_search_returns_passages` — [Edge Case]
- `test_search_limit_param_forwarded_in_query_string` — [Silent Failure: limit silently dropped]

**LettaDeleteArchivalMemoryTool:**
- `test_delete_archival_memory_success` — [Edge Case]
- `test_delete_missing_memory_id_returns_validation_error` — [Hidden Assumption]

**LettaGetMemoryBlockTool:**
- `test_get_persona_block_returns_value` — [Edge Case]
- `test_get_block_non_json_response_returns_error` — [Hidden Failure]

### Integration Tests
- No real HTTP calls in CI. All provider calls are mocked.
- Hidden assumption surfaced at integration level: all five providers use different auth header formats (`Bearer`, `Token`, `Api-Key`). The integration test verifies each tool sends the exact correct `authorization` header value by inspecting what `MockHttpTransport.request()` was called with.
- Silent failure path: a tool that accidentally serializes `None` container_tags as the string `"None"` instead of an empty array would pass unit tests but fail here since `MockHttpTransport` validates the exact body shape.

### Manual / QA Test Cases
1. Given a valid Supermemory API key, when `SupermemoryAddMemoryTool(api_key=key).execute(ToolCall("supermemory_add_memory", {"content": "My name is Alice"}))` is called, then `ToolResult.status == SUCCESS` and the response contains a document ID — [Edge Case: live API roundtrip]
2. Given an invalid API key, when any tool's `execute()` is called, then `ToolResult.status == ERROR` and the output contains an HTTP error code — [Hidden Assumption: key is always valid]
3. Given a `Mem0SearchMemoryTool`, when `execute()` is called with `user_id="unknown_user"`, then `ToolResult.status == SUCCESS` with an empty results list (not an error) — [Edge Case: no memories yet]
4. Given a `ZepAddMemoryTool`, when called with a brand-new `session_id`, then the session is auto-created and the result is success — [Hidden Assumption: session must pre-exist]
5. Given a `CogneeAddTool` pointed at `http://localhost:8000` with no Cognee server running, when `execute()` is called, then `ToolResult.status == ERROR` with a network error message — [Hidden Failure: service unavailable]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte.lib.http.HttpTransport` | In-repo stdlib-backed | HTTP calls to all providers | Low — already used by providers module |
| Supermemory API | `https://api.supermemory.ai` | Memory storage | Medium — SaaS uptime dependency |
| Mem0 Platform API | `https://api.mem0.ai` | Memory storage | Medium — SaaS uptime dependency |
| Zep Cloud API | `https://api.getzep.com` | Memory storage | Medium — SaaS uptime dependency |
| Cognee REST API | Self-hosted or cloud | Graph memory | High — requires user to run Cognee server |
| Letta Cloud API | `https://api.letta.com` | Stateful memory | Medium — SaaS uptime dependency |

No new Python package dependencies are added to `pyproject.toml`.

---

## 12. Rollout & Deployment

- No breaking changes. This is additive only.
- No feature flags needed.
- The new `vidbyte/tools/builtins/memory/` package is importable immediately after install.
- Callers who do not use memory tools are unaffected.
- API keys are caller-provided; no secrets are added to the repo.
- Rollback: delete `vidbyte/tools/builtins/memory/` and revert `vidbyte/tools/builtins/__init__.py`.

---

## 13. Open Questions

- [ ] Should we expose `LettaUpdateMemoryBlockTool` for modifying core memory blocks, or is archival memory sufficient for initial release?
- [ ] Should Cognee tools default to `http://localhost:8000` or require the caller to always pass `base_url`? (Currently defaulting to localhost to match Cognee docs.)
- [ ] Do any providers need request retry logic, or is the single-attempt from `HttpTransport` sufficient for v1?

---

## 14. Alternatives Considered

### Alternative 1: Use provider Python SDKs (`mem0ai`, `supermemory`, `zep-cloud`) as dependencies
- What: Add each provider's official SDK to `pyproject.toml` as optional or required dependencies, and call their SDK clients instead of raw HTTP.
- Why rejected: Violates the SDK's "intentionally minimal" philosophy. Adds large transitive dependency trees (`httpx`, provider-specific models, etc.) for every user whether they need memory or not. The REST APIs are simple enough that `HttpTransport` covers them with 5-10 lines per tool.

### Alternative 2: Single generic `MemoryTool` with a `provider` parameter
- What: One tool class that accepts `provider="mem0"`, `provider="zep"`, etc. and routes internally.
- Why rejected: Breaks the `ToolSpec` model — the model's tool description would be ambiguous and parameter sets differ significantly across providers. Individual tool classes let the model see exactly which provider it is using and which parameters are valid.

### Alternative 3: Implement memory within the SDK (no third-party providers)
- What: Ship a built-in vector store (e.g., in-memory or SQLite-backed) as part of the SDK.
- Why rejected: Explicitly out of scope per user request. Also adds significant complexity and storage concerns (SQLite, embedding models, serialization). Third-party providers handle all of this and can be upgraded independently.
