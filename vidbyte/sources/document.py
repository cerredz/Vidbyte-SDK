"""Context Protocol Header

Description:
    Defines DocumentSource, the generic single-document base-case loader.
Purpose:
    Fetches one remote markdown/text URL and emits exactly one labeled DocumentContextItem;
    reused by LlmsTxtSource to expand each linked document through one fetch/label/ID path.
Architecture:
    - MarkdownDocument: Minimal IR (title, body, url) for a single fetched document.
    - DocumentSource: Source[MarkdownDocument] implementing _parse and _emit.
Relations:
    Extends vidbyte.sources.base.Source; emits vidbyte.context.primitives.DocumentContextItem.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.lib.errors import SourceParseError
from vidbyte.sources._markdown import first_h1_title
from vidbyte.sources.base import (
    ArtifactRef,
    Selection,
    Source,
    SourceSnapshot,
    untrusted_metadata,
    wrap_untrusted_content,
)


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """Minimal IR for a single fetched document: a title and its raw body text."""

    title: str
    body: str
    url: str


class DocumentSource(Source[MarkdownDocument]):
    """Compiles a single remote markdown/text document into one DocumentContextItem."""

    def _parse(self, snapshot: SourceSnapshot) -> MarkdownDocument:
        # Decodes UTF-8 (fail closed) and derives a title from the first H1 or the URL.
        try:
            text = snapshot.raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("Document body is not valid UTF-8.", details={"url": snapshot.url}) from exc
        title = first_h1_title(text) or snapshot.url
        return MarkdownDocument(title=title, body=text, url=snapshot.url)

    def _emit(self, ir: MarkdownDocument, snapshot: SourceSnapshot, ref: ArtifactRef, selection: Selection) -> tuple[DocumentContextItem, ...]:
        # A single document has nothing to filter; selection is accepted for signature parity.
        del ref, selection
        return (self._build_item(ir, snapshot),)

    def _build_item(self, ir: MarkdownDocument, snapshot: SourceSnapshot) -> DocumentContextItem:
        # Constructs the labeled DocumentContextItem (also used directly by LlmsTxtSource expansion).
        content = wrap_untrusted_content(ir.body, ir.url) if self._label_untrusted else ir.body
        metadata = untrusted_metadata(
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
