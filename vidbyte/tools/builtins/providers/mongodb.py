"""MongoDB provider operation tools."""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.providers._base import ProviderOperationTool
from vidbyte.tools.builtins.providers._descriptions import (
    COLLECTION_DESCRIPTION,
    DOCUMENT_DESCRIPTION,
    STORE_BOUND_DESCRIPTION,
    WHERE_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class MongoCreateCollectionTool(ProviderOperationTool):
    """Tool wrapper for MongoDbSessionStore.create_collection()."""

    def __init__(self, store: object) -> None:
        super().__init__(store, provider_name="mongodb")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="mongodb_create_collection",
            description=(
                "Create a MongoDB collection through the bound provider store. "
                "The operation is useful before inserting documents that need a dedicated namespace. "
                "A validator object may be supplied when MongoDB should enforce document shape. "
                "The tool returns the created collection name as JSON. "
                "It does not create a new MongoDB connection. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(
                ToolParameter("collection", "string", COLLECTION_DESCRIPTION),
                ToolParameter("validator", "object", "The validator argument is an optional MongoDB collection validator document. It should follow MongoDB's validator shape. It is passed directly to create_collection. It can enforce JSON schema rules when MongoDB supports them. Omit it when no database-level validation is needed. Invalid validators are returned as provider errors.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return self._result(self.spec().name, lambda: self._store.create_collection(str(call.arguments["collection"]), validator=call.arguments.get("validator")))


class MongoCreateIndexTool(ProviderOperationTool):
    """Tool wrapper for MongoDbSessionStore.create_index()."""

    def __init__(self, store: object) -> None:
        super().__init__(store, provider_name="mongodb")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="mongodb_create_index",
            description=(
                "Create a MongoDB index through the bound provider store. "
                "Use this before frequent lookups on a document field. "
                "The keys argument is a list of field and direction pairs. "
                "The unique flag asks MongoDB to enforce uniqueness. "
                "The tool returns the created index name as JSON. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(
                ToolParameter("collection", "string", COLLECTION_DESCRIPTION),
                ToolParameter("keys", "array", "The keys argument is an array of two-item arrays. Each inner array contains a field name and a sort direction. Use 1 for ascending and -1 for descending. The order of entries controls the compound-index order. The field names are passed to MongoDB as supplied. Invalid key declarations are returned as provider errors."),
                ToolParameter("unique", "boolean", "The unique argument controls whether MongoDB enforces unique values for this index. Use true when duplicate indexed values should be rejected. Use false for ordinary lookup indexes. It defaults to false when omitted. It is passed directly to MongoDB's create_index call. Invalid uniqueness constraints are returned as provider errors.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        keys = [(str(item[0]), int(item[1])) for item in call.arguments["keys"]]
        return self._result(self.spec().name, lambda: self._store.create_index(str(call.arguments["collection"]), keys, unique=bool(call.arguments.get("unique", False))))


class MongoInsertDocumentTool(ProviderOperationTool):
    """Tool wrapper for MongoDbSessionStore.insert_document()."""

    def __init__(self, store: object) -> None:
        super().__init__(store, provider_name="mongodb")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="mongodb_insert_document",
            description=(
                "Insert one document into MongoDB through the bound provider store. "
                "Use this for atomic document creation. "
                "The tool returns the inserted document id as JSON. "
                "It does not perform application-specific validation. "
                "MongoDB validators and indexes still apply. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(ToolParameter("collection", "string", COLLECTION_DESCRIPTION), ToolParameter("document", "object", DOCUMENT_DESCRIPTION)),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return self._result(self.spec().name, lambda: self._store.insert_document(str(call.arguments["collection"]), dict(call.arguments["document"])))


class MongoFindDocumentsTool(ProviderOperationTool):
    """Tool wrapper for MongoDbSessionStore.find_documents()."""

    def __init__(self, store: object) -> None:
        super().__init__(store, provider_name="mongodb")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="mongodb_find_documents",
            description=(
                "Find documents in MongoDB through the bound provider store. "
                "Use this for read-only inspection of a collection. "
                "The query argument is a MongoDB query object. "
                "The limit argument bounds how many documents are returned. "
                "Object ids are stringified so the result is JSON-friendly. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(
                ToolParameter("collection", "string", COLLECTION_DESCRIPTION),
                ToolParameter("query", "object", WHERE_DESCRIPTION, required=False),
                ToolParameter("limit", "integer", "The limit argument caps returned documents. It protects the model context from very large result sets. It defaults to fifty when omitted. Use a smaller value when only a sample is needed. Use a larger value only when the caller can handle the output. Provider-side errors are returned as tool errors.", required=False),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return self._result(self.spec().name, lambda: self._store.find_documents(str(call.arguments["collection"]), dict(call.arguments.get("query") or {}), limit=int(call.arguments.get("limit", 50))))


class MongoUpdateDocumentsTool(ProviderOperationTool):
    """Tool wrapper for MongoDbSessionStore.update_documents()."""

    def __init__(self, store: object) -> None:
        super().__init__(store, provider_name="mongodb")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="mongodb_update_documents",
            description=(
                "Update MongoDB documents through the bound provider store. "
                "The operation applies a $set update with the supplied update object. "
                "Use the query argument to target the intended documents. "
                "The many flag controls whether one or all matches are updated. "
                "The tool returns the modified count as JSON. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(
                ToolParameter("collection", "string", COLLECTION_DESCRIPTION),
                ToolParameter("query", "object", WHERE_DESCRIPTION),
                ToolParameter("update", "object", DOCUMENT_DESCRIPTION),
                ToolParameter("many", "boolean", "The many argument controls update scope. Use true to update every matching document. Use false to update only the first matching document. It defaults to true when omitted. It should be false when the query targets a single expected record. Provider-side errors are returned as tool errors.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return self._result(self.spec().name, lambda: self._store.update_documents(str(call.arguments["collection"]), dict(call.arguments["query"]), dict(call.arguments["update"]), many=bool(call.arguments.get("many", True))))


class MongoDeleteDocumentsTool(ProviderOperationTool):
    """Tool wrapper for MongoDbSessionStore.delete_documents()."""

    def __init__(self, store: object) -> None:
        super().__init__(store, provider_name="mongodb")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="mongodb_delete_documents",
            description=(
                "Delete MongoDB documents through the bound provider store. "
                "Use this only when records should be removed from the database. "
                "The query argument controls which documents match. "
                "The many flag controls whether one or all matches are deleted. "
                "The tool returns the deleted count as JSON. "
                + STORE_BOUND_DESCRIPTION
            ),
            parameters=(
                ToolParameter("collection", "string", COLLECTION_DESCRIPTION),
                ToolParameter("query", "object", WHERE_DESCRIPTION),
                ToolParameter("many", "boolean", "The many argument controls delete scope. Use true to delete every matching document. Use false to delete only the first matching document. It defaults to true when omitted. It should be false when the query targets a single expected record. Provider-side errors are returned as tool errors.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return self._result(self.spec().name, lambda: self._store.delete_documents(str(call.arguments["collection"]), dict(call.arguments["query"]), many=bool(call.arguments.get("many", True))))


__all__ = [
    "MongoCreateCollectionTool",
    "MongoCreateIndexTool",
    "MongoInsertDocumentTool",
    "MongoFindDocumentsTool",
    "MongoUpdateDocumentsTool",
    "MongoDeleteDocumentsTool",
]
