"""Context Protocol Header

Description:
    Defines built-in SQL tools using the @tool decorator for querying,
    listing tables, and describing table schemas.
Purpose:
    Provides read-only SQL access for agentic workflows using SQLite databases.
Architecture:
    - sql_query: Executes a read-only SQL query via SqliteBackend, returns JSON.
    - sql_list_tables: Lists all user tables in the database.
    - sql_describe_table: Returns column-level schema information for a table.
    - All tools are decorated with @tool(permission=ToolPermission.READ).
Relations:
    Related to vidbyte.lib.providers.sql and vidbyte.lib.providers.sql.base.
"""

from __future__ import annotations

import json
import logging

from vidbyte.lib.providers.sql.sqlite_backend import SqliteBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission

logger = logging.getLogger(__name__)


@tool(permission=ToolPermission.READ)
async def sql_query(connection_string: str, query: str) -> str:
    """Execute a read-only SQL query and return results as JSON.

    Args:
        connection_string: Database path for SQLite, or full connection string for other databases
        query: SQL SELECT query to execute (write operations are blocked by default)
    """
    backend = SqliteBackend()
    try:
        result = await backend.query(connection_string, query)
        return json.dumps(
            {
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "truncated": result.truncated,
            },
            default=str,
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except FileNotFoundError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        logger.exception("sql_query failed")
        return json.dumps({"error": f"Query execution failed: {exc}"})


@tool(permission=ToolPermission.READ)
async def sql_list_tables(connection_string: str) -> str:
    """List all tables in the database."""
    backend = SqliteBackend()
    try:
        tables = await backend.list_tables(connection_string)
        return json.dumps(tables, default=str)
    except FileNotFoundError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        logger.exception("sql_list_tables failed")
        return json.dumps({"error": str(exc)})


@tool(permission=ToolPermission.READ)
async def sql_describe_table(connection_string: str, table: str) -> str:
    """Describe the schema of a specific table."""
    backend = SqliteBackend()
    try:
        columns = await backend.describe_table(connection_string, table)
        lines = [
            "{:<4} {:<20} {:<15} {:<8} {:<12} {:<4}".format(
                col["cid"], col["name"], col["type"], "NOT NULL" if col["notnull"] else "",
                str(col["dflt_value"]) if col["dflt_value"] is not None else "",
                "PK" if col["pk"] else "",
            )
            for col in columns
        ]
        header = "{:<4} {:<20} {:<15} {:<8} {:<12} {:<4}".format(
            "cid", "name", "type", "notnull", "dflt_value", "pk"
        )
        return header + "\n" + "\n".join(lines)
    except ValueError as exc:
        return str(exc)
    except FileNotFoundError as exc:
        return str(exc)
    except Exception as exc:
        logger.exception("sql_describe_table failed")
        return str(exc)
