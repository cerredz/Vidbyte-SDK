"""Context Protocol Header

Description:
    Unit tests for the Source[T] substrate: pinning, allowlist, size guard, cache, selection.
Purpose:
    Verifies the deterministic, fail-closed, offline-testable lifecycle shared by all loaders.
Architecture:
    - CountingFetcher: Wraps InMemoryFetcher to assert network calls (no-network guarantees).
    - SourcesBaseTests: unittest.TestCase covering every substrate scenario in the test plan.
Relations:
    Exercises vidbyte.sources.base, vidbyte.sources._fetch, and the HttpFetcher scheme guard
    that DirectHttpFetchTool relies on.
"""

from __future__ import annotations

import asyncio
import http.server
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from vidbyte.lib.dataclasses import ToolCall
from vidbyte.lib.dataclasses.sources import FetchResponse
from vidbyte.lib.errors import SourceFetchError, SourcePinMismatchError, SourceSecurityError
from vidbyte.lib.http.transport import SyncHttpTransport
from vidbyte.sources import (
    ArtifactRef,
    ChainedFetcher,
    DocumentSource,
    FileFetcher,
    FileSnapshotCache,
    HttpFetcher,
    InMemoryFetcher,
    InMemorySnapshotCache,
    NullSnapshotCache,
    PinPolicy,
    Selection,
    UrlAllowlist,
    sha256_hex,
)
from vidbyte.tools.builtins.operations.fetch import DirectHttpFetchTool

_DATA = b"# Title\nbody text"


class CountingFetcher:
    """InMemoryFetcher wrapper that records how many network fetches occurred."""

    def __init__(self, responses: dict[str, bytes]) -> None:
        self._inner = InMemoryFetcher(responses)
        self.calls = 0

    def fetch(self, url: str):
        self.calls += 1
        return self._inner.fetch(url)


class RedirectingFetcher:
    """Fake fetcher that reports its bytes as read from a fixed final URL, as after a redirect."""

    def __init__(self, final_url: str) -> None:
        self._final_url = final_url

    def fetch(self, url: str) -> FetchResponse:
        return FetchResponse(status_code=200, body_bytes=b"# x\n", url=self._final_url)


class _RedirectHandler(http.server.BaseHTTPRequestHandler):
    """Local test server: /a answers 302 to /b, and /b answers 200 with a tiny markdown body."""

    def do_GET(self) -> None:
        if self.path == "/a":
            self.send_response(302)
            self.send_header("Location", "/b")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"# b\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


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

    def test_allowlist_rejects_bare_string_schemes_and_hosts(self) -> None:
        # [Silent Failure] A bare string made `in` a substring test ("http" in "https"), failing open.
        with self.assertRaisesRegex(SourceSecurityError, r"UrlAllowlist\.allowed_schemes must be a collection"):
            UrlAllowlist(allowed_schemes="https")  # type: ignore[arg-type]
        with self.assertRaisesRegex(SourceSecurityError, r"UrlAllowlist\.allowed_hosts must be a collection"):
            UrlAllowlist(allowed_hosts="docs.acme.dev")  # type: ignore[arg-type]
        allow = UrlAllowlist(allowed_schemes=("https",), allowed_hosts=frozenset({"docs.acme.dev"}))
        for refused in ("http://docs.acme.dev/x", "https://acme.dev/x"):
            with self.assertRaises(SourceSecurityError):
                allow.check(refused)
        allow.check("https://docs.acme.dev/x")

    def test_allowlist_config_is_case_insensitive(self) -> None:
        # [Hidden Assumption] Hosts and schemes are case-insensitive, so a capitalized policy still admits its own
        # lowercase URLs, an unlisted host is still refused, and the default https-only allowlist is unchanged.
        for allow in (
            UrlAllowlist(allowed_hosts=frozenset({"Docs.Acme.dev"})),
            UrlAllowlist(allowed_schemes=("HTTPS",), allowed_hosts=frozenset({"docs.acme.dev"})),
        ):
            allow.check("https://docs.acme.dev/llms.txt")
            with self.assertRaises(SourceSecurityError):
                allow.check("https://evil.example/llms.txt")
        default = UrlAllowlist()
        self.assertEqual(default.allowed_schemes, ("https",))
        self.assertIsNone(default.allowed_hosts)
        default.check("https://docs.acme.dev/llms.txt")
        with self.assertRaises(SourceSecurityError):
            default.check("http://docs.acme.dev/llms.txt")

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

    def test_uppercase_pin_matches_same_bytes_cold_and_warm(self) -> None:
        # [Hidden Assumption] A hex digest is case-insensitive: an UPPERCASE pin of the right bytes loads cold and
        # from the pinned warm cache, while changed bytes under the same pin still fail closed.
        upper_pin = sha256_hex(_DATA).upper()
        cache = InMemorySnapshotCache()
        cold = DocumentSource(fetcher=InMemoryFetcher({"https://ex.com/x.md": _DATA}), cache=cache)
        self.assertEqual(len(cold.load(ArtifactRef(url="https://ex.com/x.md", expected_hash=upper_pin)).items), 1)
        fetcher = CountingFetcher({})
        warm = DocumentSource(fetcher=fetcher, cache=cache)
        self.assertEqual(len(warm.load(ArtifactRef(url="https://ex.com/x.md", expected_hash=upper_pin)).items), 1)
        self.assertEqual(fetcher.calls, 0)
        changed = DocumentSource(fetcher=InMemoryFetcher({"https://ex.com/x.md": _DATA + b"!"}))
        with self.assertRaises(SourcePinMismatchError):
            changed.load(ArtifactRef(url="https://ex.com/x.md", expected_hash=upper_pin))

    def test_string_pin_policy_is_served_from_pinned_warm_cache(self) -> None:
        # [Silent Failure] A manifest's pin: "pinned" equals PinPolicy.PINNED, so it must hit the pinned warm cache
        # with zero network I/O instead of silently re-fetching; an unknown spelling fails loudly at construction.
        pin = sha256_hex(_DATA)
        ref = ArtifactRef(url="https://ex.com/x.md", expected_hash=pin, pin="pinned")  # type: ignore[arg-type]
        self.assertIs(ref.pin, PinPolicy.PINNED)
        cache = InMemorySnapshotCache()
        cache.put(pin, _DATA)
        fetcher = CountingFetcher({})
        self.assertEqual(len(DocumentSource(fetcher=fetcher, cache=cache).load(ref).items), 1)
        self.assertEqual(fetcher.calls, 0)
        with self.assertRaises(ValueError):
            ArtifactRef(url="https://ex.com/x.md", pin="pinnned")  # type: ignore[arg-type]

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

    def test_selection_list_form_matches_tuple_form(self) -> None:
        # [Regression] Lists from YAML/JSON config normalize to tuples, so allow=["*"] stays trivial.
        listed = Selection(allow=["*"], deny=[])
        self.assertTrue(listed.is_trivial)
        self.assertEqual(listed, Selection())
        self.assertEqual(hash(listed), hash(Selection()))
        self.assertFalse(Selection(allow=["API*"]).is_trivial)
        self.assertFalse(Selection(deny=["x"]).matches("x"))

    def test_selection_rejects_bare_string_globs(self) -> None:
        # [Silent Failure] A bare string would become one glob per character; refuse it.
        for kwargs in ({"allow": "Docs*"}, {"deny": "secret"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SourceSecurityError):
                Selection(**kwargs)

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

    def test_filesnapshotcache_tolerates_concurrent_writers(self) -> None:
        # @intent snapshot-cache-tolerates-concurrent-writers
        # [Race Condition] An existing entry is never rewritten, and concurrent put/get of one hash never fails.
        content_hash = sha256_hex(_DATA)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "snaps"
            cache = FileSnapshotCache(root)
            cache.put(content_hash, _DATA)
            cache.put(content_hash, b"different bytes under the same hash")
            self.assertEqual(cache.get(content_hash), _DATA)
            self.assertEqual(list(root.glob("*.tmp")), [])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "snaps"
            cache = FileSnapshotCache(root)
            barrier = threading.Barrier(8)
            errors: list[BaseException] = []

            def worker() -> None:
                try:
                    barrier.wait()
                    for _ in range(20):
                        cache.put(content_hash, _DATA)
                        self.assertIn(cache.get(content_hash), (None, _DATA))
                except BaseException as exc:  # noqa: BLE001 - collected and asserted below
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            self.assertEqual(cache.get(content_hash), _DATA)
            self.assertEqual(list(root.glob("*.tmp")), [])

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

    def test_nullsnapshotcache_always_misses(self) -> None:
        # [Edge Case] NullSnapshotCache is an explicit no-cache implementation.
        cache = NullSnapshotCache()
        cache.put(sha256_hex(_DATA), _DATA)
        self.assertIsNone(cache.get(sha256_hex(_DATA)))

    def test_chainedfetcher_uses_first_success(self) -> None:
        # [Edge Case] ChainedFetcher can fall back from a miss to a later fetcher.
        fetcher = ChainedFetcher([InMemoryFetcher({}), InMemoryFetcher({"https://ex.com/x.md": _DATA})])
        result = DocumentSource(fetcher=fetcher).load(ArtifactRef(url="https://ex.com/x.md"))
        self.assertEqual(result.items[0].title, "Title")

    def test_filefetcher_reads_explicitly_allowed_file_url(self) -> None:
        # [Edge Case] FileFetcher supports local vendored fixtures when file:// is explicitly allowed.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.md"
            path.write_bytes(_DATA)
            source = DocumentSource(fetcher=FileFetcher(), allowlist=UrlAllowlist(allowed_schemes=("file",)))
            result = source.load(ArtifactRef(url=path.as_uri()))
            self.assertEqual(result.items[0].title, "Title")

    def test_filefetcher_keeps_file_uri_host_as_unc_share(self) -> None:
        # @intent file-uri-host-is-a-unc-share
        # [Silent Failure] A file URI host is the share serving the file, never dropped for a local path.
        path = FileFetcher()._resolve_path("file://docs-share/handbook/oncall.md")
        self.assertIn("docs-share", str(path))
        self.assertNotEqual(path, Path("/handbook/oncall.md").resolve())
        if sys.platform == "win32":
            self.assertTrue(str(path).startswith("\\\\docs-share\\handbook"))
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp).resolve() / "doc.md"
            local.write_bytes(_DATA)
            for url in (local.as_uri(), local.as_uri().replace("file://", "file://localhost", 1)):
                self.assertEqual(FileFetcher().fetch(url).body_bytes, _DATA)

    def test_httpfetcher_refuses_file_and_schemeless_urls_before_any_request(self) -> None:
        # [Hidden Assumption] HttpFetcher never opens a local file and only raises SourceFetchError.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secret.md"
            path.write_bytes(_DATA)
            cases = ((path.as_uri(), "file"), ("docs.example.invalid/page", ""))
            with mock.patch.object(SyncHttpTransport, "request_bytes") as request_bytes:
                for url, scheme in cases:
                    with self.assertRaises(SourceFetchError) as caught:
                        HttpFetcher().fetch(url)
                    self.assertEqual(caught.exception.details, {"url": url, "scheme": scheme})
            request_bytes.assert_not_called()

    def test_httpfetcher_wraps_read_timeout_so_chained_fetcher_falls_back(self) -> None:
        # @intent sync-request-bytes-normalizes-socket-errors
        # [Error Path] urllib leaves a body read timeout unwrapped; HttpFetcher must still raise SourceFetchError.
        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        response.read.side_effect = TimeoutError("The read operation timed out")
        url = "https://ex.com/x.md"
        with mock.patch("vidbyte.lib.http.transport.urlopen", return_value=response):
            with self.assertRaises(SourceFetchError) as caught:
                HttpFetcher().fetch(url)
            self.assertEqual(caught.exception.details, {"url": url, "status_code": None, "excerpt": "TimeoutError: The read operation timed out"})
            fetcher = ChainedFetcher([HttpFetcher(), InMemoryFetcher({url: _DATA})])
            result = DocumentSource(fetcher=fetcher).load(ArtifactRef(url=url))
        self.assertEqual(result.items[0].title, "Title")

    def test_httpfetcher_sends_iris_as_percent_encoded_uris(self) -> None:
        # @intent http-fetcher-sends-iris-as-uris
        # [Edge Case] http.client writes the request line as ASCII, so a non-ASCII path or query must be sent as UTF-8 percent escapes.
        cases = {
            "https://de.example.test/wiki/Müller": "https://de.example.test/wiki/M%C3%BCller",
            "https://ja.example.test/wiki/東京駅": "https://ja.example.test/wiki/%E6%9D%B1%E4%BA%AC%E9%A7%85",
            "https://shop.example.test/suche?q=größe&x=1": "https://shop.example.test/suche?q=gr%C3%B6%C3%9Fe&x=1",
            "https://de.example.test/wiki/M%C3%BCller?a=1&b=%2F": "https://de.example.test/wiki/M%C3%BCller?a=1&b=%2F",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                requested: list[str] = []
                response = mock.MagicMock(status=200, url=expected)
                response.__enter__.return_value = response
                response.read.return_value = _DATA
                response.headers.items.return_value = [("Content-Type", "text/markdown")]
                with mock.patch("vidbyte.lib.http.transport.urlopen", side_effect=lambda request, timeout: requested.append(request.full_url) or response):
                    result = HttpFetcher().fetch(url)
                self.assertEqual(requested, [expected])
                self.assertEqual(result.body_bytes, _DATA)

    def test_redirect_off_the_allowlist_is_refused(self) -> None:
        # @intent redirect-target-is-allowlisted
        # [Hidden Assumption] An allowlisted URL that redirects to an unlisted host must not load that host's bytes.
        source = DocumentSource(fetcher=RedirectingFetcher("https://evil.example/x"), allowlist=UrlAllowlist(allowed_hosts=frozenset({"good.com"})))
        with self.assertRaises(SourceSecurityError):
            source.load(ArtifactRef(url="https://good.com/start"))

    def test_redirect_within_the_allowlist_still_loads(self) -> None:
        # [Edge Case] A same-site move to another allowlisted URL is not refused.
        source = DocumentSource(fetcher=RedirectingFetcher("https://good.com/moved"), allowlist=UrlAllowlist(allowed_hosts=frozenset({"good.com"})))
        result = source.load(ArtifactRef(url="https://good.com/start"))
        self.assertEqual(result.items[0].title, "x")

    def test_snapshot_url_names_the_redirect_target(self) -> None:
        # @intent snapshot-url-is-where-the-bytes-came-from
        # [Regression] Verify that after a redirect the snapshot names the final URL the bytes were read from.
        source = DocumentSource(fetcher=RedirectingFetcher("https://good.com/moved"), allowlist=UrlAllowlist(allowed_hosts=frozenset({"good.com"})))
        result = source.load(ArtifactRef(url="https://good.com/start"))
        self.assertEqual(result.snapshot.url, "https://good.com/moved")
        self.assertEqual(result.ref.url, "https://good.com/start")

    def test_percent_encoded_request_form_is_not_a_redirect(self) -> None:
        # @intent snapshot-url-is-where-the-bytes-came-from
        # [Edge Case] Verify the percent-encoded request form of an IRI is not mistaken for a redirect target.
        iri = "https://good.com/文档/a.md"
        source = DocumentSource(fetcher=RedirectingFetcher("https://good.com/%E6%96%87%E6%A1%A3/a.md"), allowlist=UrlAllowlist(allowed_hosts=frozenset({"good.com"})))
        result = source.load(ArtifactRef(url=iri))
        self.assertEqual(result.snapshot.url, iri)

    def test_httpfetcher_reports_the_final_url_after_a_redirect(self) -> None:
        # [Hidden Assumption] urllib follows the 302 itself; FetchResponse.url must name where the bytes came from.
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            response = HttpFetcher(timeout_seconds=10).fetch(f"http://127.0.0.1:{server.server_address[1]}/a")
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(response.body_bytes, b"# b\n")
        self.assertTrue(response.url.endswith("/b"), response.url)

    def test_direct_http_fetch_tool_reports_fetch_failed_for_file_url(self) -> None:
        # [Edge Case] A model-supplied file:// URL is a clean fetch_failed result, not an execution error.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secret.md"
            path.write_bytes(_DATA)
            result = asyncio.run(DirectHttpFetchTool().execute(ToolCall("direct_http_fetch", {"url": path.as_uri()})))
        self.assertEqual(result.status.value, "error")
        self.assertEqual(result.metadata["error"], "fetch_failed")
        self.assertNotIn("# Title", result.output)

    def test_direct_http_fetch_tool_decodes_pages_with_their_declared_charset(self) -> None:
        # [Hidden Assumption] Pages declare their encoding in the Content-Type charset or a <meta charset>; reading
        # every page as UTF-8 turns windows-1252, Shift_JIS and GBK pages into U+FFFD for the model.
        german = "<html><body>Öffnungszeiten: Müllabfuhr am Dienstag – 5 €</body></html>"
        japanese = "<html><body>東京駅から品川駅まで</body></html>"
        meta_only = '<html><head><meta charset="Shift_JIS"></head><body>東京駅から品川駅まで</body></html>'
        cases = (
            (german.encode("cp1252"), "text/html; charset=windows-1252", german),
            (japanese.encode("shift_jis"), 'text/html; Charset="Shift_JIS"', japanese),
            (meta_only.encode("shift_jis"), "text/html", meta_only),
            ("<p>ünïcode ✓</p>".encode("utf-8"), "text/html; charset=x-bogus", "<p>ünïcode ✓</p>"),
            ("<p>ünïcode ✓</p>".encode("utf-8"), None, "<p>ünïcode ✓</p>"),
            # Codecs that codecs.lookup knows but that cannot decode text under errors="replace" must fall back too:
            # bytes-to-bytes codecs raise LookupError, and the domain-name codecs idna and punycode are never page
            # encodings (from Python 3.13 punycode decodes most pages to "" instead of raising).
            ("<p>ünïcode ✓</p>".encode("utf-8"), "text/html; charset=base64", "<p>ünïcode ✓</p>"),
            ('<meta charset="hex"><p>ünïcode ✓</p>'.encode("utf-8"), "text/html", '<meta charset="hex"><p>ünïcode ✓</p>'),
            ("<p>ünïcode ✓</p>".encode("utf-8"), "text/html; charset=idna", "<p>ünïcode ✓</p>"),
            ("<p>ünïcode ✓</p>".encode("utf-8"), "text/html; charset=punycode", "<p>ünïcode ✓</p>"),
            ('<meta charset="idna"><p>ünïcode ✓</p>'.encode("utf-8"), "text/html", '<meta charset="idna"><p>ünïcode ✓</p>'),
            ('<meta charset="punycode"><p>ünïcode ✓</p>'.encode("utf-8"), "text/html", '<meta charset="punycode"><p>ünïcode ✓</p>'),
        )
        for body, content_type, expected in cases:
            with self.subTest(content_type=content_type, expected=expected[:40]):
                response = FetchResponse(status_code=200, body_bytes=body, content_type=content_type, url="https://example.com/")
                with mock.patch.object(HttpFetcher, "fetch", return_value=response):
                    result = asyncio.run(DirectHttpFetchTool().execute(ToolCall("direct_http_fetch", {"url": "https://example.com/"})))
                self.assertEqual(result.status.value, "success")
                self.assertEqual(result.output, expected)
                self.assertNotIn("�", result.output)


if __name__ == "__main__":
    unittest.main()
