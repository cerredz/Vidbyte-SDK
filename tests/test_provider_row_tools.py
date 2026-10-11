"""FILE: tests/test_provider_row_tools.py

PURPOSE: Tests the provider row tools against a real in-memory SQLite store.
ROLE IN CODEBASE: Regression coverage proving a JSON null limit on select_rows means the documented default.
ARCHITECTURE NOTE: ProviderRowNullLimitTests creates a table, inserts rows, and drives select_rows through execute().
COMMON MODIFICATION PATTERNS: Add a case here when another optional row-tool argument gains null handling.
KNOWN EDGE CASES: A JSON null limit, where, or schema behaves exactly like an omitted key.
RELATED DOCS: docs/design/provider-rows-null-limit.md; vidbyte/tools/base.py (@intent null-optional-arg-means-default)
TESTS: python -m pytest tests/test_provider_row_tools.py
"""

from __future__ import annotations

import json
import unittest

from vidbyte.lib.providers.sqlite import SqliteSessionStore
from vidbyte.tools.builtins import ProviderCreateTableTool, ProviderInsertRowTool, ProviderSelectRowsTool
from vidbyte.tools.types import ToolCall, ToolStatus


class ProviderRowNullLimitTests(unittest.IsolatedAsyncioTestCase):
    """Verifies select_rows treats a null limit like an omitted one."""

    async def test_select_rows_null_limit_matches_omitted_limit(self) -> None:
        store = SqliteSessionStore(path=":memory:")
        await ProviderCreateTableTool(store, provider_name="sqlite").execute(
            ToolCall("sqlite_create_table", {"table": "items", "columns": {"sku": "TEXT PRIMARY KEY", "qty": "INTEGER"}})
        )
        insert = ProviderInsertRowTool(store, provider_name="sqlite")
        await insert.execute(ToolCall("sqlite_insert_row", {"table": "items", "row": {"sku": "A1", "qty": 3}}))
        await insert.execute(ToolCall("sqlite_insert_row", {"table": "items", "row": {"sku": "B2", "qty": 5}}))
        select = ProviderSelectRowsTool(store, provider_name="sqlite")
        null_result = await select.execute(
            ToolCall("sqlite_select_rows", {"table": "items", "where": None, "limit": None, "schema": None})
        )
        omitted_result = await select.execute(ToolCall("sqlite_select_rows", {"table": "items"}))
        self.assertEqual(null_result.status, ToolStatus.SUCCESS, null_result.output)
        self.assertEqual(json.loads(null_result.output), json.loads(omitted_result.output))
        self.assertEqual({row["sku"] for row in json.loads(null_result.output)}, {"A1", "B2"})


if __name__ == "__main__":
    unittest.main()
