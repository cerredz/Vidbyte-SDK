"""Context Protocol Header

Description:
    Defines the generic single-document context-item loader.
Purpose:
    Fetches one remote markdown/text URL and emits exactly one labeled DocumentContextItem.
Architecture:
    - DocumentSource: Source[MarkdownDocument] implementing _parse and _emit.
Relations:
    Extends vidbyte.sources.base.Source and uses vidbyte.sources.regex.DocumentRegex.
"""

from __future__ import annotations

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.lib.dataclasses.sources import (
    ArtifactRef,
    MarkdownDocument,
    Selection,
    SourceSnapshot,
)
from vidbyte.lib.errors import SourceParseError
from vidbyte.sources.base import Source
from vidbyte.sources.regex import DocumentRegex


class DocumentSource(Source[MarkdownDocument]):
    """Compiles a single remote markdown/text document into one DocumentContextItem."""

    def _parse(self, snapshot: SourceSnapshot) -> MarkdownDocument:
        # Decodes UTF-8 and derives a title from the first H1 or the URL.
        try:
            text = snapshot.raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("Document body is not valid UTF-8.", details={"url": snapshot.url}) from exc
        title = DocumentRegex.first_h1_title(text) or snapshot.url
        return MarkdownDocument(title=title, body=text, url=snapshot.url)

    def _emit(self, ir: MarkdownDocument, snapshot: SourceSnapshot, ref: ArtifactRef, selection: Selection) -> tuple[DocumentContextItem, ...]:
        # A single document has nothing to filter; selection is accepted for signature parity.
        del ref, selection
        return (self._build_item(ir, snapshot),)

    def _build_item(self, ir: MarkdownDocument, snapshot: SourceSnapshot) -> DocumentContextItem:
        # Constructs the labeled DocumentContextItem used by document loads and llms.txt expansion.
        content = self._wrap_untrusted_content(ir.body, ir.url) if self._label_untrusted else ir.body
        metadata = self._untrusted_metadata(
            origin=ir.url,
            content_hash=snapshot.content_hash,
            source_kind="document",
            content_type=snapshot.content_type,
        )
        return DocumentContextItem(
            source=ir.url,
            content=content,
            title=ir.title,
            document_id=f"document:{snapshot.content_hash[:12]}",
            metadata=metadata,
        )


__all__ = [
    "DocumentSource",
    "MarkdownDocument",
]
