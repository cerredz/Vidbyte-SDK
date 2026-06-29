"""Context Protocol Header

Description:
    Unit tests for the Source[T] substrate: pinning, allowlist, size guard, cache, selection.
Purpose:
    Verifies the deterministic, fail-closed, offline-testable lifecycle shared by all loaders.
Architecture:
    - CountingFetcher: Wraps InMemoryFetcher to assert network calls (no-network guarantees).
    - SourcesBaseTests: unittest.TestCase covering every substrate scenario in the test plan.
Relations:
    Exercises vidbyte.sources.base and vidbyte.sources._fetch.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.lib.errors import SourcePinMismatchError, SourceSecurityError
from vidbyte.sources import (
    ArtifactRef,
    DocumentSource,
    FileSnapshotCache,
    InMemoryFetcher,
    InMemorySnapshotCache,
    PinPolicy,
    Selection,
    UrlAllowlist,
    sha256_hex,
)

_DATA = b"# Title\nbody text"


class CountingFetcher:
    """InMemoryFetcher wrapper that records how many network fetches occurred."""

    def __init__(self, responses: dict[str, bytes]) -> None:
        self._inner = InMemoryFetcher(responses)
        self.calls = 0

    def fetch(self, url: str):
        self.calls += 1
        return self._inner.fetch(url)


class SourcesBaseTests(unittest.TestCase):
    def test_pin_mismatch_fails_closed(self) -> None:
        # [Hidden Assumption] A pinned hash that differs from fetched bytes must emit nothing.
        fetcher = InMemoryFetcher({"https://ex.com/x.md": _DATA})
        source = DocumentSource(fetcher=fetcher)
        with self.assertRaises(SourcePinMismatchError):
            source.load(ArtifactRef(url="https://ex.com/x.md", expected_hash="deadbeef"))

    def test_allowlist_rejects_http_by_default(self) -> None:
        # [Hidden Assumption] http:// is rejected before any fetch (https-only default).
        fetcher = CountingFetcher({"http://ex.com/x.md": _DATA})
        with self.assertRaises(SourceSecurityError):
            DocumentSource(fetcher=fetcher).load(ArtifactRef(url="http://ex.com/x.md"))
        self.assertEqual(fetcher.calls, 0)

    def test_allowlist_rejects_unlisted_host(self) -> None:
        # [Edge Case] A host outside allowed_hosts fails closed.
        fetcher = InMemoryFetcher({"https://bad.com/x.md": _DATA})
        source = DocumentSource(fetcher=fetcher, allowlist=UrlAllowlist(allowed_hosts=frozenset({"good.com"})))
        with self.assertRaises(SourceSecurityError):
            source.load(ArtifactRef(url="https://bad.com/x.md"))

    def test_allowlist_ignores_userinfo_and_port(self) -> None:
        # [Silent Failure] Host check uses hostname only, so user@evil and ports cannot bypass it.
        allow = UrlAllowlist(allowed_hosts=frozenset({"good.com"}))
        fetcher = InMemoryFetcher({"https://good.com:8443/x.md": _DATA})
        DocumentSource(fetcher=fetcher, allowlist=allow).load(ArtifactRef(url="https://good.com:8443/x.md"))
        spoof = InMemoryFetcher({"https://good.com@evil.com/x.md": _DATA})
        with self.assertRaises(SourceSecurityError):
            DocumentSource(fetcher=spoof, allowlist=allow).load(ArtifactRef(url="https://good.com@evil.com/x.md"))

    def test_size_guard_rejects_oversized_body(self) -> None:
        # [Edge Case] A body larger than max_bytes fails closed with nothing cached.
        fetcher = InMemoryFetcher({"https://ex.com/big.md": b"x" * 100})
        cache = InMemorySnapshotCache()
        with self.assertRaises(SourceSecurityError):
            DocumentSource(fetcher=fetcher, cache=cache, max_bytes=10).load(ArtifactRef(url="https://ex.com/big.md"))
        self.assertIsNone(cache.get(sha256_hex(b"x" * 100)))

    def test_pinned_warm_cache_does_no_network(self) -> None:
        # [Hidden Failure] A pinned ref whose expected hash is cached performs zero network I/O.
        cache = InMemorySnapshotCache()
        cache.put(sha256_hex(_DATA), _DATA)
        fetcher = CountingFetcher({})
        source = DocumentSource(fetcher=fetcher, cache=cache)
        result = source.load(ArtifactRef(url="https://ex.com/x.md", expected_hash=sha256_hex(_DATA)))
        self.assertEqual(fetcher.calls, 0)
        self.assertEqual(len(result.items), 1)

    def test_live_policy_always_refetches(self) -> None:
        # [Hidden Assumption] PinPolicy.LIVE re-fetches even with a warm cache.
        cache = InMemorySnapshotCache()
        cache.put(sha256_hex(_DATA), _DATA)
        fetcher = CountingFetcher({"https://ex.com/x.md": _DATA})
        source = DocumentSource(fetcher=fetcher, cache=cache)
        source.load(ArtifactRef(url="https://ex.com/x.md", expected_hash=sha256_hex(_DATA), pin=PinPolicy.LIVE))
        self.assertEqual(fetcher.calls, 1)

    def test_selection_matches_allow_and_deny(self) -> None:
        # [Edge Case] allow plus deny globs combine correctly.
        selection = Selection(allow=("Docs*",), deny=("Docs/secret*",))
        self.assertTrue(selection.matches("Docs"))
        self.assertTrue(selection.selects("Docs", "Docs/public"))
        self.assertFalse(selection.matches("Docs/secret-1"))
        self.assertFalse(selection.matches("Other"))

    def test_selection_is_case_insensitive(self) -> None:
        # [Silent Failure] Globs match case-insensitively.
        self.assertTrue(Selection(allow=("docs",)).matches("Docs"))

    def test_selection_is_trivial(self) -> None:
        # [Edge Case] Default selection is trivial; any narrowing is not.
        self.assertTrue(Selection().is_trivial)
        self.assertFalse(Selection(allow=("API*",)).is_trivial)
        self.assertFalse(Selection(deny=("x",)).is_trivial)

    def test_sha256_hex_of_empty_bytes(self) -> None:
        # [Edge Case] The empty-bytes hash is the stable known constant.
        self.assertEqual(sha256_hex(b""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    def test_store_noop_without_cache(self) -> None:
        # [Edge Case] Loading without a configured cache still succeeds.
        fetcher = InMemoryFetcher({"https://ex.com/x.md": _DATA})
        result = DocumentSource(fetcher=fetcher).load(ArtifactRef(url="https://ex.com/x.md"))
        self.assertEqual(len(result.items), 1)

    def test_filesnapshotcache_roundtrip_and_atomicity(self) -> None:
        # [Edge Case] put then get returns identical bytes; a missing hash returns None.
        with tempfile.TemporaryDirectory() as tmp:
            cache = FileSnapshotCache(Path(tmp) / "snaps")
            self.assertIsNone(cache.get(sha256_hex(_DATA)))
            cache.put(sha256_hex(_DATA), _DATA)
            self.assertEqual(cache.get(sha256_hex(_DATA)), _DATA)

    def test_filesnapshotcache_end_to_end_no_refetch(self) -> None:
        # [Hidden Failure] A pinned reload from the file cache reads from disk with no network.
        with tempfile.TemporaryDirectory() as tmp:
            cache = FileSnapshotCache(Path(tmp) / "snaps")
            first = CountingFetcher({"https://ex.com/x.md": _DATA})
            source_a = DocumentSource(fetcher=first, cache=cache)
            result_a = source_a.load(ArtifactRef(url="https://ex.com/x.md"))
            self.assertEqual(first.calls, 1)
            second = CountingFetcher({})
            source_b = DocumentSource(fetcher=second, cache=cache)
            result_b = source_b.load(ArtifactRef(url="https://ex.com/x.md", expected_hash=result_a.content_hash))
            self.assertEqual(second.calls, 0)
            self.assertEqual(
                [item.document_id for item in result_a.items],
                [item.document_id for item in result_b.items],
            )


if __name__ == "__main__":
    unittest.main()
