"""FILE: tests/test_mongodb_tools.py

PURPOSE: Tests the MongoDB provider operation tools against a recording fake store.
ROLE IN CODEBASE: Regression coverage proving declared boolean arguments are read strictly, so a stringly "false" is refused before the store is called.
ARCHITECTURE NOTE: RecordingStore is a fake store that records every provider call; MongoBooleanArgumentTests drives the tools through execute().
COMMON MODIFICATION PATTERNS: Add a fake store method when a new MongoDB tool gains a boolean argument, then assert the store sees no call on refusal.
KNOWN EDGE CASES: A JSON null means the documented default; only a real bool is passed through; any other value is a tool error.
RELATED DOCS: docs/design/tool-args-strict-booleans.md; vidbyte/tools/base.py (@intent boolean-tool-args-reject-stringly-truthiness)
TESTS: python -m pytest tests/test_mongodb_tools.py
"""

from __future__ import annotations

import unittest
from typing import Any

from vidbyte.tools.builtins.providers.mongodb import (
    MongoCreateIndexTool,
    MongoDeleteDocumentsTool,
    MongoUpdateDocumentsTool,
)
from vidbyte.tools.types import ToolCall, ToolStatus


class RecordingStore:
    """Records provider calls so tests can prove whether the store was reached."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def delete_documents(self, collection: str, query: dict[str, Any], *, many: bool) -> int:
        self.calls.append(("delete_documents", {"collection": collection, "query": query, "many": many}))
        return 1

    def update_documents(self, collection: str, query: dict[str, Any], update: dict[str, Any], *, many: bool) -> int:
        self.calls.append(("update_documents", {"collection": collection, "query": query, "update": update, "many": many}))
        return 1

    def create_index(self, collection: str, keys: list[tuple[str, int]], *, unique: bool) -> str:
        self.calls.append(("create_index", {"collection": collection, "keys": keys, "unique": unique}))
        return "idx"


class MongoBooleanArgumentTests(unittest.IsolatedAsyncioTestCase):
    """Verifies MongoDB tools refuse stringly booleans before touching the store."""

    async def test_delete_documents_refuses_string_many_without_calling_store(self) -> None:
        store = RecordingStore()
        result = await MongoDeleteDocumentsTool(store).execute(
            ToolCall("mongodb_delete_documents", {"collection": "users", "query": {"name": "a"}, "many": "false"})
        )
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("'many' must be a boolean (true/false)", result.output)
        self.assertEqual(store.calls, [])

    async def test_update_documents_refuses_string_many_without_calling_store(self) -> None:
        store = RecordingStore()
        result = await MongoUpdateDocumentsTool(store).execute(
            ToolCall("mongodb_update_documents", {"collection": "users", "query": {}, "update": {"x": 1}, "many": "false"})
        )
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertEqual(store.calls, [])

    async def test_create_index_refuses_string_unique_without_calling_store(self) -> None:
        store = RecordingStore()
        result = await MongoCreateIndexTool(store).execute(
            ToolCall("mongodb_create_index", {"collection": "users", "keys": [["email", 1]], "unique": "true"})
        )
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertEqual(store.calls, [])

    async def test_real_and_missing_booleans_reach_the_store(self) -> None:
        store = RecordingStore()
        delete = MongoDeleteDocumentsTool(store)
        await delete.execute(ToolCall("mongodb_delete_documents", {"collection": "users", "query": {}, "many": False}))
        await delete.execute(ToolCall("mongodb_delete_documents", {"collection": "users", "query": {}, "many": None}))
        self.assertEqual([call[1]["many"] for call in store.calls], [False, True])


if __name__ == "__main__":
    unittest.main()
