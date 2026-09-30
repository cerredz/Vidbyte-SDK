"""FILE: vidbyte/providers/tool_catalogs/apis_guru.py

PURPOSE: Adapts the APIs.guru OpenAPI directory into ToolCatalogEntry records whose install is the API's OpenAPI document.
ROLE IN CODEBASE: ToolCatalogs builds ApisGuruCatalog for ToolCatalogName.APIS_GURU only when the owner lists it; JevAgentAlignment reports matching APIs as owner actions because OPENAPI installs cannot be attached yet.
ARCHITECTURE NOTE: The directory is one ~9 MB JSON file (`list.json`), downloaded once per TTL and ranked locally; each API's preferred version supplies the title, description, and OpenAPI URL.
COMMON MODIFICATION PATTERNS: When an OpenAPI-to-tools bridge lands in vidbyte/sources, give the OPENAPI install an attach path in JevAgentAlignment rather than changing this adapter.
KNOWN EDGE CASES: Descriptions often contain HTML and are only capped, not cleaned. APIs without a preferred version or an OpenAPI URL are skipped.
RELATED DOCS: https://apis.guru/api-doc/ and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from vidbyte.lib.constants.tool_catalogs import APIS_GURU_LIST_URL
from vidbyte.lib.dataclasses.tool_catalogs import ToolCatalogEntry, ToolInstall
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName, ToolInstallKind
from vidbyte.providers.tool_catalogs.base import (
    IndexedToolCatalogProvider,
    mapping,
    text,
)


class ApisGuruCatalog(IndexedToolCatalogProvider):
    """The APIs.guru directory of public OpenAPI descriptions (discovery only)."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.APIS_GURU
    index_url: ClassVar[str] = APIS_GURU_LIST_URL

    def parse_index(self, body: str) -> Iterable[ToolCatalogEntry]:
        """Parse list.json into one entry per API, using its preferred version."""
        entries: list[ToolCatalogEntry] = []
        for api_id, raw in mapping(self.load_json(body)).items():
            api = mapping(raw)
            preferred = text(api.get("preferred"))
            version = mapping(mapping(api.get("versions")).get(preferred))
            info = mapping(version.get("info"))
            openapi_url = text(version.get("swaggerUrl") or version.get("openapiUrl"))
            if not text(api_id) or not preferred or not openapi_url:
                continue
            entries.append(
                ToolCatalogEntry(
                    catalog=self.name,
                    entry_id=text(api_id),
                    name=text(info.get("title")) or text(api_id),
                    description=text(info.get("description")),
                    installs=(ToolInstall(kind=ToolInstallKind.OPENAPI, url=openapi_url),),
                    version=preferred,
                    publisher=text(info.get("x-providerName")) or None,
                )
            )
        return entries


__all__ = ["ApisGuruCatalog"]
