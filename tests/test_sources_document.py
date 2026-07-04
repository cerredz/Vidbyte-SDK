"""Context Protocol Header

Description:
    Unit tests for DocumentSource, the single-document base-case loader.
Purpose:
    Verifies stable IDs, title fallback, fail-closed decoding, and untrusted labeling.
Architecture:
    - DocumentSourceTests: unittest.TestCase over DocumentSource emission behavior.
Relations:
    Exercises vidbyte.sources.document and the shared base labeling helpers.
"""

from __future__ import annotations

import unittest

from vidbyte.lib.errors import SourceParseError
from vidbyte.sources import ArtifactRef, DocumentSource, InMemoryFetcher, sha256_hex


class DocumentSourceTests(unittest.TestCase):
    def _load(self, body: bytes, *, label_untrusted: bool = True):
        fetcher = InMemoryFetcher({"https://ex.com/x.md": body})
        source = DocumentSource(fetcher=fetcher, label_untrusted=label_untrusted)
        return source.load(ArtifactRef(url="https://ex.com/x.md"))

    def test_emits_single_item_with_stable_id(self) -> None:
        # [Silent Failure] Identical bytes always produce identical id and content.
        body = b"# Doc\nbody"
        result_a = self._load(body)
        result_b = self._load(body)
        self.assertEqual(len(result_a.items), 1)
        self.assertEqual(result_a.items[0].document_id, result_b.items[0].document_id)
        self.assertEqual(result_a.items[0].document_id, "document:" + sha256_hex(body)[:12])

    def test_title_falls_back_to_url_when_no_h1(self) -> None:
        # [Edge Case] A body without an H1 uses the URL as the title.
        result = self._load(b"no heading here")
        self.assertEqual(result.items[0].title, "https://ex.com/x.md")

    def test_non_utf8_body_fails_closed(self) -> None:
        # [Hidden Assumption] Undecodable bytes raise rather than lossily decode.
        with self.assertRaises(SourceParseError):
            self._load(b"\xff\xfe\x00bad")

    def test_empty_body_emits_empty_content_item(self) -> None:
        # [Edge Case] An empty document is valid: one item, empty body, stable id.
        result = self._load(b"")
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].metadata["content_sha256"], sha256_hex(b""))

    def test_item_is_labeled_untrusted(self) -> None:
        # [Hidden Assumption] Emitted items carry trust metadata and a visible boundary marker.
        item = self._load(b"# Doc\nbody").items[0]
        self.assertEqual(item.metadata["trust"], "untrusted-external")
        self.assertEqual(item.metadata["origin"], "https://ex.com/x.md")
        self.assertEqual(item.metadata["source_kind"], "document")
        self.assertIn("BEGIN UNTRUSTED EXTERNAL CONTENT", item.content)
        self.assertIn("END UNTRUSTED EXTERNAL CONTENT", item.content)

    def test_label_untrusted_false_omits_boundary(self) -> None:
        # [Edge Case] Disabling the boundary keeps the raw body but still labels metadata.
        item = self._load(b"# Doc\nbody", label_untrusted=False).items[0]
        self.assertNotIn("BEGIN UNTRUSTED EXTERNAL CONTENT", item.content)
        self.assertEqual(item.content, "# Doc\nbody")
        self.assertEqual(item.metadata["trust"], "untrusted-external")

    def test_non_textual_content_type_warns(self) -> None:
        # [Silent Failure] A non-text content type is recorded as a metadata warning, not a hard fail.
        from vidbyte.sources import FetchResponse

        fetcher = InMemoryFetcher(
            {"https://ex.com/x.md": FetchResponse(200, b"# Doc\nbody", content_type="application/octet-stream")}
        )
        item = DocumentSource(fetcher=fetcher).load(ArtifactRef(url="https://ex.com/x.md")).items[0]
        self.assertTrue(item.metadata.get("content_type_warning"))


if __name__ == "__main__":
    unittest.main()
