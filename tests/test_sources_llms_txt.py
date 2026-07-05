"""Context Protocol Header

Description:
    Unit tests for the llms.txt parser and LlmsTxtSource loader.
Purpose:
    Verifies fail-closed parsing, index-first progressive disclosure, filtering, deterministic
    expansion ordering, and untrusted labeling/namespacing.
Architecture:
    - LlmsTxtParserTests / LlmsTxtSourceTests: unittest.TestCase suites over parser and loader.
Relations:
    Exercises vidbyte.sources.llms_txt.parser and vidbyte.sources.llms_txt.loader.
"""

from __future__ import annotations

import unittest

from vidbyte.lib.errors import SourceParseError, SourceSecurityError
from vidbyte.sources import (
    ArtifactRef,
    InMemoryFetcher,
    LlmsTxtSource,
    Selection,
    UrlAllowlist,
    parse_llms_txt,
)

_INDEX = b"""# Example

> A short summary.

Some prose details.

## Docs

- [Quickstart](https://ex.com/quick.md): Get started
- [Guide](https://ex.com/guide.md)

## Optional

- [Changelog](https://ex.com/changelog.md)
"""


def _fetcher() -> InMemoryFetcher:
    return InMemoryFetcher(
        {
            "https://ex.com/llms.txt": _INDEX,
            "https://ex.com/quick.md": b"# Quickstart\nget started",
            "https://ex.com/guide.md": b"# Guide\nthe guide",
            "https://ex.com/changelog.md": b"# Changelog\nv1",
        }
    )


def _source(**kwargs) -> LlmsTxtSource:
    kwargs.setdefault("fetcher", _fetcher())
    kwargs.setdefault("allowlist", UrlAllowlist(allowed_hosts=frozenset({"ex.com"})))
    return LlmsTxtSource(**kwargs)


class LlmsTxtParserTests(unittest.TestCase):
    def test_parse_minimal_index(self) -> None:
        # [Edge Case] Title, summary, details, and a section/link parse into the IR.
        doc = parse_llms_txt(_INDEX, url="https://ex.com/llms.txt")
        self.assertEqual(doc.title, "Example")
        self.assertEqual(doc.summary, "A short summary.")
        self.assertEqual(doc.sections[0].name, "Docs")
        self.assertEqual(doc.sections[0].links[0].url, "https://ex.com/quick.md")
        self.assertEqual(doc.sections[0].links[0].note, "Get started")

    def test_parse_missing_h1_fails_closed(self) -> None:
        # [Hidden Assumption] A first non-blank line that is not an H1 is fatal.
        with self.assertRaises(SourceParseError):
            parse_llms_txt(b"no title\n## S\n- [a](https://ex.com/a.md)", url="u")

    def test_parse_malformed_link_fails_closed(self) -> None:
        # [Silent Failure] A link bullet that cannot be parsed raises instead of half-loading.
        with self.assertRaises(SourceParseError):
            parse_llms_txt(b"# T\n## S\n- [text](", url="u")

    def test_parse_empty_link_target_fails_closed(self) -> None:
        # [Edge Case] An empty link target is malformed.
        with self.assertRaises(SourceParseError):
            parse_llms_txt(b"# T\n## S\n- [text]()", url="u")

    def test_parse_optional_section_flagged(self) -> None:
        # [Edge Case] A "## Optional" section is flagged optional.
        doc = parse_llms_txt(_INDEX, url="u")
        optional = [section for section in doc.sections if section.optional]
        self.assertEqual([section.name for section in optional], ["Optional"])

    def test_parse_crlf_and_bom(self) -> None:
        # [Hidden Failure] CRLF endings and a leading BOM still parse.
        raw = b"\xef\xbb\xbf# Title\r\n\r\n> sum\r\n\r\n## S\r\n- [a](https://ex.com/a.md)\r\n"
        doc = parse_llms_txt(raw, url="u")
        self.assertEqual(doc.title, "Title")
        self.assertEqual(doc.summary, "sum")
        self.assertEqual(doc.sections[0].links[0].title, "a")

    def test_parse_duplicate_sections_preserved(self) -> None:
        # [Edge Case] Duplicate section names are kept as separate sections.
        raw = b"# T\n## Docs\n- [a](https://ex.com/a.md)\n## Docs\n- [b](https://ex.com/b.md)\n"
        doc = parse_llms_txt(raw, url="u")
        self.assertEqual([section.name for section in doc.sections], ["Docs", "Docs"])


class LlmsTxtSourceTests(unittest.TestCase):
    def test_emit_index_only_by_default(self) -> None:
        # [Silent Failure] The default load emits only the index (no accidental fan-out).
        result = _source().load(ArtifactRef(url="https://ex.com/llms.txt"))
        self.assertEqual(len(result.items), 1)
        self.assertTrue(result.items[0].document_id.endswith(":000-index"))

    def test_emit_index_lists_all_links(self) -> None:
        # [Silent Failure] The index content lists every link URL (not truncated).
        content = _source().load(ArtifactRef(url="https://ex.com/llms.txt")).items[0].content
        for url in ("https://ex.com/quick.md", "https://ex.com/guide.md", "https://ex.com/changelog.md"):
            self.assertIn(url, content)

    def test_expand_fetches_and_emits_per_link(self) -> None:
        # [Edge Case] Expansion emits the index plus one item per non-optional link, sorted.
        result = _source().load(ArtifactRef(url="https://ex.com/llms.txt"), selection=Selection(expand=True))
        self.assertEqual(len(result.items), 3)
        ids = [item.document_id for item in result.items]
        self.assertTrue(ids[0].endswith(":000-index"))
        self.assertEqual(ids[1:], sorted(ids[1:]))

    def test_expand_excludes_optional_by_default(self) -> None:
        # [Hidden Assumption] Optional-section links are not expanded unless explicitly selected.
        result = _source().load(ArtifactRef(url="https://ex.com/llms.txt"), selection=Selection(expand=True))
        self.assertNotIn("changelog", " ".join(item.document_id for item in result.items))

    def test_expand_respects_allow_deny_globs(self) -> None:
        # [Edge Case] A link-level allow glob expands only the matching link.
        result = _source().load(
            ArtifactRef(url="https://ex.com/llms.txt"),
            selection=Selection(allow=("Docs/Quickstart",)),
        )
        self.assertEqual(len(result.items), 2)  # index + quickstart only
        self.assertIn("quickstart", result.items[1].document_id)

    def test_expand_failed_link_fails_closed_by_default(self) -> None:
        # [Hidden Assumption] A link host outside the allowlist fails the whole expansion.
        fetcher = InMemoryFetcher(
            {
                "https://ex.com/llms.txt": b"# I\n## S\n- [a](https://other.com/a.md)\n",
                "https://other.com/a.md": b"# A",
            }
        )
        source = LlmsTxtSource(fetcher=fetcher, allowlist=UrlAllowlist(allowed_hosts=frozenset({"ex.com"})))
        with self.assertRaises(SourceSecurityError):
            source.load(ArtifactRef(url="https://ex.com/llms.txt"), selection=Selection(expand=True))

    def test_expanded_ids_namespaced_under_parent(self) -> None:
        # [Silent Failure] Expanded item ids are namespaced under the parent hash and link it back.
        result = _source().load(ArtifactRef(url="https://ex.com/llms.txt"), selection=Selection(expand=True))
        parent_hash = result.content_hash
        for item in result.items[1:]:
            self.assertTrue(item.document_id.startswith(f"llms-txt:{parent_hash[:12]}:"))
            self.assertEqual(item.metadata["parent"], parent_hash)
            self.assertEqual(item.metadata["section"], "Docs")

    def test_deterministic_across_two_loads(self) -> None:
        # [Silent Failure] The same bytes loaded twice yield identical id lists and order.
        ids_a = [item.document_id for item in _source().load(ArtifactRef(url="https://ex.com/llms.txt"), selection=Selection(expand=True)).items]
        ids_b = [item.document_id for item in _source().load(ArtifactRef(url="https://ex.com/llms.txt"), selection=Selection(expand=True)).items]
        self.assertEqual(ids_a, ids_b)


if __name__ == "__main__":
    unittest.main()
