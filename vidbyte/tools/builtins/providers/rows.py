"""Row/table provider operation tools."""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.providers._base import ProviderOperationTool
from vidbyte.tools.builtins.providers._descriptions import (
    ROW_DESCRIPTION,
    STORE_BOUND_DESCRIPTION,
    TABLE_DESCRIPTION,
    WHERE_DESCRIPTION,
)
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class ProviderCreateSchemaTool(ProviderOperationTool):
    """Tool wrapper for stores that expose create_schema()."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=f"{self._provider_name}_create_schema",
            description=(
                "Create a database schema through the bound provider store. "
                "Use this when the provider supports named schemas and later tables should live there. "
                "The operation is idempotent when the provider method implements IF NOT EXISTS semantics. "
                "It returns the schema name as JSON. "
                "It does not create a new provider connection. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(ToolParameter("schema", "string", "The schema argument names the database schema to create. It should be an identifier, not a SQL statement. PostgreSQL-backed stores quote this identifier before execution. Use a stable schema name when later table operations should target it. Omit punctuation that is not valid for the backend. Provider-side errors are returned as tool errors."),),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return self._result(self.spec().name, lambda: self._store.create_schema(str(call.arguments["schema"])))


class ProviderCreateTableTool(ProviderOperationTool):
    """Tool wrapper for stores that expose create_table()."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=f"{self._provider_name}_create_table",
            description=(
                "Create a database table through the bound provider store. "
                "Use this before inserting rows into a provider-backed table. "
                "The columns object maps column names to provider SQL type declarations. "
                "The operation is idempotent when the backend supports IF NOT EXISTS. "
                "It returns the provider-qualified table name as JSON. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(
                ToolParameter("table", "string", TABLE_DESCRIPTION),
                ToolParameter("columns", "object", "The columns argument maps column names to SQL type declarations. Each key is treated as an identifier. Each value is a provider-specific SQL type fragment such as TEXT or JSONB. It should not include a full CREATE TABLE statement. The provider applies its own type validation. Invalid columns are returned as provider errors."),
                ToolParameter("schema", "string", "The schema argument optionally selects a PostgreSQL schema. It should be a schema identifier, not a SQL expression. SQLite-backed tools ignore unsupported schema usage by not passing this argument. Supabase row tools do not expose create_table because the client API does not generally create tables. Use this only with provider stores that support schemas. Provider-side errors are returned as tool errors.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        kwargs = {"schema": call.arguments.get("schema")} if call.arguments.get("schema") is not None else {}
        return self._result(self.spec().name, lambda: self._store.create_table(str(call.arguments["table"]), dict(call.arguments["columns"]), **kwargs))


class ProviderInsertRowTool(ProviderOperationTool):
    """Tool wrapper for stores that expose insert_row()."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=f"{self._provider_name}_insert_row",
            description=(
                "Insert one row through the bound provider store. "
                "Use this for atomic row creation in SQL-like providers. "
                "The row object maps columns to values. "
                "The tool returns provider response data or an affected-row count as JSON. "
                "Provider defaults and constraints still apply. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(
                ToolParameter("table", "string", TABLE_DESCRIPTION),
                ToolParameter("row", "object", ROW_DESCRIPTION),
                ToolParameter("schema", "string", "The schema argument optionally selects a PostgreSQL schema. It should be a schema identifier, not a SQL statement. Stores without schema support should be used without this argument. The table argument remains required when schema is supplied. Use the same schema value on later reads if the table is outside the default path. Provider-side errors are returned as tool errors.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        kwargs = {"schema": call.arguments.get("schema")} if call.arguments.get("schema") is not None else {}
        return self._result(self.spec().name, lambda: self._store.insert_row(str(call.arguments["table"]), dict(call.arguments["row"]), **kwargs))


class ProviderSelectRowsTool(ProviderOperationTool):
    """Tool wrapper for stores that expose select_rows()."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=f"{self._provider_name}_select_rows",
            description=(
                "Select rows through the bound provider store. "
                "Use this for read-only inspection of table data. "
                "The where object applies equality filters when supplied. "
                "The limit value bounds the result size. "
                "The tool returns row objects as JSON. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(
                ToolParameter("table", "string", TABLE_DESCRIPTION),
                ToolParameter("where", "object", WHERE_DESCRIPTION, required=False),
                ToolParameter("limit", "integer", "The limit argument caps returned rows. It protects the model context from large result sets. It defaults to fifty when omitted. Use a smaller value when only a sample is needed. Use a larger value only when the caller can handle the output. Provider-side errors are returned as tool errors.", required=False),
                ToolParameter("schema", "string", "The schema argument optionally selects a PostgreSQL schema. It should be a schema identifier, not a SQL statement. Stores without schema support should be used without this argument. The table argument remains required when schema is supplied. Use the same schema value on later writes if the table is outside the default path. Provider-side errors are returned as tool errors.", required=False),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        kwargs = {"schema": call.arguments.get("schema")} if call.arguments.get("schema") is not None else {}
        return self._result(self.spec().name, lambda: self._store.select_rows(str(call.arguments["table"]), dict(call.arguments.get("where") or {}), limit=int(call.arguments.get("limit", 50)), **kwargs))


class ProviderUpdateRowsTool(ProviderOperationTool):
    """Tool wrapper for stores that expose update_rows()."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=f"{self._provider_name}_update_rows",
            description=(
                "Update rows through the bound provider store. "
                "Use this when existing records should be changed in place. "
                "The values object supplies the columns to set. "
                "The where object controls which rows match. "
                "The tool returns provider response data or an affected-row count as JSON. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(
                ToolParameter("table", "string", TABLE_DESCRIPTION),
                ToolParameter("values", "object", ROW_DESCRIPTION),
                ToolParameter("where", "object", WHERE_DESCRIPTION),
                ToolParameter("schema", "string", "The schema argument optionally selects a PostgreSQL schema. It should be a schema identifier, not a SQL statement. Stores without schema support should be used without this argument. The table argument remains required when schema is supplied. Use the same schema value on later reads if the table is outside the default path. Provider-side errors are returned as tool errors.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        kwargs = {"schema": call.arguments.get("schema")} if call.arguments.get("schema") is not None else {}
        return self._result(self.spec().name, lambda: self._store.update_rows(str(call.arguments["table"]), dict(call.arguments["values"]), dict(call.arguments["where"]), **kwargs))


class ProviderDeleteRowsTool(ProviderOperationTool):
    """Tool wrapper for stores that expose delete_rows()."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=f"{self._provider_name}_delete_rows",
            description=(
                "Delete rows through the bound provider store. "
                "Use this only when matching records should be removed. "
                "The where object controls which rows match. "
                "The tool returns provider response data or an affected-row count as JSON. "
                "A narrow filter is recommended because deletes are destructive. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(
                ToolParameter("table", "string", TABLE_DESCRIPTION),
                ToolParameter("where", "object", WHERE_DESCRIPTION),
                ToolParameter("schema", "string", "The schema argument optionally selects a PostgreSQL schema. It should be a schema identifier, not a SQL statement. Stores without schema support should be used without this argument. The table argument remains required when schema is supplied. Use the same schema value on later reads if the table is outside the default path. Provider-side errors are returned as tool errors.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        kwargs = {"schema": call.arguments.get("schema")} if call.arguments.get("schema") is not None else {}
        return self._result(self.spec().name, lambda: self._store.delete_rows(str(call.arguments["table"]), dict(call.arguments["where"]), **kwargs))


__all__ = [
    "ProviderCreateSchemaTool",
    "ProviderCreateTableTool",
    "ProviderInsertRowTool",
    "ProviderSelectRowsTool",
    "ProviderUpdateRowsTool",
    "ProviderDeleteRowsTool",
]
