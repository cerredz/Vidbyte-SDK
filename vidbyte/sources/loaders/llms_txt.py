"""Context Protocol Header

Description:
    Defines the llms.txt context-item loader.
Purpose:
    Parses an llms.txt index into a compact index primitive and optionally expands selected
    links into per-link DocumentContextItems.
Architecture:
    - LlmsTxtSource: Source[LlmsTxtDocument] implementing parse, index emission, and expansion.
Relations:
    Extends vidbyte.sources.base.Source and delegates linked documents to DocumentSource.
"""

from __future__ import annotations

from dataclasses import replace

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.lib.dataclasses.sources import (
    ArtifactRef,
    LlmsTxtDocument,
    LlmsTxtLink,
    LlmsTxtSection,
    Selection,
    SourceSnapshot,
)
from vidbyte.sources.base import Source
from vidbyte.sources.llms_txt.parser import parse_llms_txt
from vidbyte.sources.loaders.document import DocumentSource
from vidbyte.sources.regex import SourcesRegex


class LlmsTxtSource(Source[LlmsTxtDocument]):
    """Compiles an llms.txt index into a compact index primitive plus optional expanded sections."""

    def _parse(self, snapshot: SourceSnapshot) -> LlmsTxtDocument:
        # Delegates to the fail-closed parser; raises SourceParseError on malformed input.
        return parse_llms_txt(snapshot.raw_bytes, url=snapshot.url)

    def _emit(self, ir: LlmsTxtDocument, snapshot: SourceSnapshot, ref: ArtifactRef, selection: Selection) -> tuple[DocumentContextItem, ...]:
        # Always emits the index item, then optionally the deterministically ordered expanded items.
        items: list[DocumentContextItem] = [self._build_index_item(ir, snapshot)]
        if self._should_expand(selection):
            items.extend(self._expand_sections(ir, selection, snapshot.content_hash, ref))
        return tuple(items)

    def _should_expand(self, selection: Selection) -> bool:
        # Expand when explicitly requested or when a non-trivial allow/deny narrows the link set.
        return selection.expand or not selection.is_trivial

    def _build_index_item(self, ir: LlmsTxtDocument, snapshot: SourceSnapshot) -> DocumentContextItem:
        # Renders title, summary, and a per-section link inventory into one labeled item.
        lines = [f"# {ir.title}"]
        if ir.summary:
            lines.append(f"> {ir.summary}")
        for section in ir.sections:
            lines.append("")
            lines.append(f"## {section.name}")
            for link in section.links:
                note = f" - {link.note}" if link.note else ""
                lines.append(f"- [{link.title}]({link.url}){note}")
        body = "\n".join(lines)
        content = self._wrap_untrusted_content(body, snapshot.url) if self._label_untrusted else body
        metadata = self._untrusted_metadata(
            origin=snapshot.url,
            content_hash=snapshot.content_hash,
            source_kind="llms_txt",
            content_type=snapshot.content_type,
            extra={"section_count": len(ir.sections)},
        )
        return DocumentContextItem(
            source=snapshot.url,
            content=content,
            title=ir.title,
            document_id=f"llms-txt:{snapshot.content_hash[:12]}:000-index",
            metadata=metadata,
        )

    def _selected_links(self, ir: LlmsTxtDocument, selection: Selection) -> tuple[tuple[int, int, LlmsTxtLink, LlmsTxtSection], ...]:
        # Returns selected link tuples in document order.
        selected: list[tuple[int, int, LlmsTxtLink, LlmsTxtSection]] = []
        for s_idx, section in enumerate(ir.sections):
            if section.optional and selection.is_trivial:
                continue
            for l_idx, link in enumerate(section.links):
                key = f"{section.name}/{link.title}"
                if selection.selects(section.name, key):
                    selected.append((s_idx, l_idx, link, section))
        return tuple(selected)

    def _expand_sections(self, ir: LlmsTxtDocument, selection: Selection, parent_hash: str, ref: ArtifactRef) -> tuple[DocumentContextItem, ...]:
        # Fetches each selected link via a shared DocumentSource and returns sorted, re-stamped items.
        doc_source = DocumentSource(
            fetcher=self._fetcher,
            cache=self._cache,
            allowlist=self._allowlist,
            max_bytes=self._max_bytes,
            label_untrusted=self._label_untrusted,
        )
        expanded: list[DocumentContextItem] = []
        for s_idx, l_idx, link, section in self._selected_links(ir, selection):
            result = doc_source.load(ArtifactRef(url=link.url, pin=ref.pin))
            item = result.items[0]
            document_id = (
                f"llms-txt:{parent_hash[:12]}:{s_idx:03d}-{SourcesRegex.slugify(section.name)}:"
                f"{l_idx:03d}-{SourcesRegex.slugify(link.title)}"
            )
            metadata = {**dict(item.metadata), "parent": parent_hash, "section": section.name}
            expanded.append(replace(item, document_id=document_id, metadata=metadata))
        expanded.sort(key=lambda emitted: emitted.document_id or "")
        return tuple(expanded)


__all__ = [
    "LlmsTxtSource",
]
