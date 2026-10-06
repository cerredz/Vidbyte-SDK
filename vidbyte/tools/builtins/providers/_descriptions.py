"""Shared provider-tool descriptions."""

from __future__ import annotations

STORE_BOUND_DESCRIPTION = (
    "This tool operates on a provider store instance that the developer already constructed. "
    "It does not open a new network connection by itself. "
    "It does not read secrets from the environment. "
    "It delegates exactly one atomic storage operation to the bound provider object. "
    "Use it when an agent needs controlled access to provider storage through the SDK tool permission system. "
    "The returned output is JSON so later agent steps can inspect ids, counts, or row payloads."
)

COLLECTION_DESCRIPTION = (
    "The collection argument names a MongoDB collection inside the bound store database. "
    "It should be the plain collection name, not a full connection string. "
    "The bound store decides which database receives the operation. "
    "Use a stable collection name when later tool calls need to read or mutate the same documents. "
    "The tool does not validate application-level schema rules beyond what MongoDB enforces. "
    "An invalid or inaccessible collection name is returned as a provider error result."
)

TABLE_DESCRIPTION = (
    "The table argument names the target table for the bound provider store. "
    "It should be a table identifier, not a raw SQL statement. "
    "PostgreSQL and SQLite stores quote identifiers before constructing SQL. "
    "Supabase stores pass the name to the Supabase table API. "
    "Use the schema argument on PostgreSQL-specific tools when the table is outside the default search path. "
    "An inaccessible or missing table is returned as a provider error result."
)

DOCUMENT_DESCRIPTION = (
    "The document argument is a JSON object to write into the target provider. "
    "It should contain only JSON-compatible values. "
    "The tool does not add application-specific fields except whatever the provider driver adds. "
    "Credential-like data should not be included because the document may be persisted. "
    "Nested objects and arrays are passed through to providers that support them. "
    "Invalid document shapes are returned as provider error results."
)

WHERE_DESCRIPTION = (
    "The where argument is a JSON object of equality filters. "
    "Each key is treated as a column or document field name. "
    "Each value is compared using the provider's ordinary equality operator. "
    "It is not a raw SQL or MongoDB operator string. "
    "Use a narrow filter for update and delete operations because matching records may be changed. "
    "An empty filter is only appropriate for read operations or intentionally broad maintenance calls."
)

ROW_DESCRIPTION = (
    "The row argument is a JSON object of column values to insert or update. "
    "Each key maps to one provider field or table column. "
    "Each value should already be JSON-compatible or accepted by the provider driver. "
    "The tool does not infer missing columns or default values. "
    "The provider applies its own constraints, defaults, and type coercions. "
    "Invalid rows are returned as provider error results."
)

__all__ = [
    "STORE_BOUND_DESCRIPTION",
    "COLLECTION_DESCRIPTION",
    "TABLE_DESCRIPTION",
    "DOCUMENT_DESCRIPTION",
    "WHERE_DESCRIPTION",
    "ROW_DESCRIPTION",
]
