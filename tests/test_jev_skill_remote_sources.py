"""FILE: tests/test_jev_skill_remote_sources.py

PURPOSE: Verifies bounded GitHub and skills.sh skill retrieval with no live network calls.
ROLE IN CODEBASE: Exercises the source adapters owned by the remote-provider stage of Jev skill loading.
ARCHITECTURE NOTE: Fake transports capture exact URLs, headers, response caps, and failure boundaries.
COMMON MODIFICATION PATTERNS: Add a fake transport case when a provider URL form, selector, or failure rule changes.
KNOWN EDGE CASES: Ref/path interpretations are bounded, only 404 is ignored, and raw downloads receive no API key.
RELATED DOCS: docs/design/jev-skill-providers.md.
TESTS: Run with python scripts/test-jev-skill-providers.py.
"""

from __future__ import annotations

import base64
import json
import unittest
from typing import Any
from urllib.parse import urlsplit

from vidbyte.lib.dataclasses.skills import SkillSource
from vidbyte.lib.enums.skills import SkillSourceKind
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http.transport import HttpResponse
from vidbyte.providers.skills import SkillSourceResolver
from vidbyte.providers.skills.base import SkillSourceError
from vidbyte.providers.skills.github import GitHubSkillSourceAdapter
from vidbyte.providers.skills.skills_sh import SkillsShSkillSourceAdapter


class _FakeTransport:
    """Returns route-keyed responses and captures each bounded request."""

    def __init__(self, responses: dict[str, HttpResponse], failures: dict[str, Exception] | None = None) -> None:
        # Makes every expected network call explicit and inspectable in the test.
        self.responses = responses
        self.failures = failures or {}
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> HttpResponse:
        # Returns only a preconfigured response so no test reaches the network.
        self.calls.append(kwargs)
        url = str(kwargs["url"])
        if url in self.failures:
            raise self.failures[url]
        if url not in self.responses:
            raise AssertionError(f"Unexpected request URL: {url}")
        return self.responses[url]


def _response(payload: object, *, status: int = 200) -> HttpResponse:
    # Encodes a JSON object as an exact bounded HTTP response.
    body = json.dumps(payload)
    return HttpResponse(status_code=status, body=body, headers={"content-type": "application/json"}, raw_bytes=body.encode("utf-8"))


def _text_response(content: bytes, *, status: int = 200) -> HttpResponse:
    # Keeps raw bytes available so UTF-8 validation and CRLF preservation are exercised.
    return HttpResponse(status_code=status, body=content.decode("utf-8", errors="replace"), headers={"content-type": "text/plain"}, raw_bytes=content)


def _skill(name: str = "review-helper", description: str = "Review code") -> bytes:
    # Produces a valid complete SKILL.md source file.
    return f"---\nname: {name}\ndescription: {description}\n---\nKeep this body exact.\n".encode()


def _repository_and_tree(*, revision: str, tree: list[dict[str, object]], truncated: bool = False) -> dict[str, HttpResponse]:
    # Creates the two API responses used for repository catalog resolution.
    return {
        "https://api.github.com/repos/acme/skills": _response({"default_branch": revision}),
        f"https://api.github.com/repos/acme/skills/git/trees/{revision}?recursive=1": _response({"tree": tree, "truncated": truncated}),
    }


def _blob_response(content: bytes, sha: str) -> HttpResponse:
    # Encodes the documented GitHub Git Blob fields and exact decoded size.
    return _response({"sha": sha, "node_id": "node-1", "url": f"https://api.github.com/repos/acme/skills/git/blobs/{sha}", "encoding": "base64", "size": len(content), "content": base64.b64encode(content).decode("ascii")})


def _contents_response(content: bytes, path: str) -> HttpResponse:
    # Encodes the documented repository-contents file response.
    return _response({"type": "file", "encoding": "base64", "size": len(content), "path": path, "content": base64.b64encode(content).decode("ascii")})


def _not_found() -> HttpResponse:
    # Represents the only response ignored while testing alternate URL interpretations.
    return _response({"message": "Not Found"}, status=404)


class SkillSourceResolverTests(unittest.IsolatedAsyncioTestCase):
    """Checks closed public dispatch reaches the real remote adapters through fake HTTP."""

    async def test_resolver_dispatches_github_with_injected_bounded_transport(self) -> None:
        # [Hidden Failure] the public resolver must not replace an implemented GITHUB adapter with a placeholder error.
        content = _skill("release-review", "Review release changes")
        responses = _repository_and_tree(
            revision="stable",
            tree=[{"path": "guides/SKILL.md", "type": "blob", "sha": "github-resolver", "size": len(content)}],
        )
        responses["https://api.github.com/repos/acme/skills/git/blobs/github-resolver"] = _blob_response(content, "github-resolver")
        transport = _FakeTransport(responses)
        resolver = SkillSourceResolver(transport=transport)

        self.assertEqual(transport.calls, [])
        document = await resolver.resolve(
            SkillSource(kind=SkillSourceKind.GITHUB, location="acme/skills", skill_name="release-review")
        )

        self.assertEqual(document.text, content.decode("utf-8"))
        self.assertEqual(document.name, "release-review")
        self.assertEqual([call["url"] for call in transport.calls], list(responses))
        self.assertTrue(all(call["max_response_bytes"] > 0 for call in transport.calls))
        self.assertTrue(all(call["follow_redirects"] is False for call in transport.calls))

    async def test_resolver_dispatches_skills_sh_through_github_catalog(self) -> None:
        # [Hidden Failure] the public resolver must route skills.sh references through the shared bounded GitHub catalog.
        content = _skill("ux-guidelines", "Review interface changes")
        responses = _repository_and_tree(
            revision="development",
            tree=[{"path": "skills/ux-guidelines/SKILL.md", "type": "blob", "sha": "skills-sh-resolver", "size": len(content)}],
        )
        responses["https://api.github.com/repos/acme/skills/git/blobs/skills-sh-resolver"] = _blob_response(content, "skills-sh-resolver")
        transport = _FakeTransport(responses)
        resolver = SkillSourceResolver(transport=transport)

        self.assertEqual(transport.calls, [])
        document = await resolver.resolve(
            SkillSource(kind=SkillSourceKind.SKILLS_SH, location="https://skills.sh/acme/skills/ux-guidelines")
        )

        self.assertEqual(document.text, content.decode("utf-8"))
        self.assertEqual(document.name, "ux-guidelines")
        self.assertEqual([call["url"] for call in transport.calls], list(responses))
        self.assertTrue(all(call["max_response_bytes"] > 0 for call in transport.calls))
        self.assertTrue(all(call["follow_redirects"] is False for call in transport.calls))


class GitHubSkillSourceTests(unittest.IsolatedAsyncioTestCase):
    """Checks repository discovery, explicit URL forms, response bounds, and safe auth."""

    async def test_repository_uses_metadata_default_and_frontmatter_name(self) -> None:
        # [Hidden Assumption] a directory basename is not the skill identity when metadata names it differently.
        content = b"---\r\nname: release-review\r\ndescription: Review releases\r\n---\r\nPreserve this text.\r\n"
        responses = _repository_and_tree(
            revision="stable-release",
            tree=[{"path": "guides/different-folder/SKILL.md", "type": "blob", "sha": "blob-1", "size": len(content)}],
        )
        responses["https://api.github.com/repos/acme/skills/git/blobs/blob-1"] = _blob_response(content, "blob-1")
        transport = _FakeTransport(responses)

        document = await GitHubSkillSourceAdapter(transport=transport).resolve(
            SkillSource(kind=SkillSourceKind.GITHUB, location="acme/skills", skill_name="release-review")
        )

        self.assertEqual(document.name, "release-review")
        self.assertEqual(document.text, content.decode("utf-8"))
        self.assertEqual(document.source, "https://github.com/acme/skills/blob/stable-release/guides/different-folder/SKILL.md")
        self.assertEqual([call["url"] for call in transport.calls], list(responses))
        self.assertTrue(all(call["follow_redirects"] is False for call in transport.calls))
        self.assertTrue(all(call["max_response_bytes"] > 0 for call in transport.calls))

    async def test_repository_with_multiple_skills_requires_selector(self) -> None:
        # [Ambiguous Selection] two valid catalog entries never cause the adapter to pick the first.
        first = _skill("one")
        second = _skill("two")
        responses = _repository_and_tree(
            revision="trunk",
            tree=[
                {"path": "one/SKILL.md", "type": "blob", "sha": "one", "size": len(first)},
                {"path": "two/SKILL.md", "type": "blob", "sha": "two", "size": len(second)},
            ],
        )
        responses["https://api.github.com/repos/acme/skills/git/blobs/one"] = _blob_response(first, "one")
        responses["https://api.github.com/repos/acme/skills/git/blobs/two"] = _blob_response(second, "two")

        with self.assertRaisesRegex(SkillSourceError, "ambiguous"):
            await GitHubSkillSourceAdapter(transport=_FakeTransport(responses)).resolve(
                SkillSource(kind=SkillSourceKind.GITHUB, location="acme/skills")
            )

    async def test_blob_and_raw_urls_resolve_single_documents(self) -> None:
        # [Realistic Usage] direct blob and raw source forms retrieve one named SKILL.md file each.
        content = _skill()
        blob_url = "https://api.github.com/repos/acme/skills/contents/skills/review/SKILL.md?ref=main"
        blob_payload = {
            "type": "file",
            "encoding": "base64",
            "size": len(content),
            "path": "skills/review/SKILL.md",
            "content": base64.b64encode(content).decode("ascii"),
        }
        blob_transport = _FakeTransport(
            {
                "https://api.github.com/repos/acme/skills": _response({"default_branch": "main"}),
                blob_url: _response(blob_payload),
                "https://api.github.com/repos/acme/skills/contents/review/SKILL.md?ref=main%2Fskills": _not_found(),
                "https://api.github.com/repos/acme/skills/contents/SKILL.md?ref=main%2Fskills%2Freview": _not_found(),
            }
        )
        blob = await GitHubSkillSourceAdapter(transport=blob_transport).resolve(
            SkillSource(kind=SkillSourceKind.GITHUB, location="https://github.com/acme/skills/blob/main/skills/review/SKILL.md")
        )

        raw_url = "https://raw.githubusercontent.com/acme/skills/main/SKILL.md"
        raw_transport = _FakeTransport({raw_url: _text_response(content)})
        raw = await GitHubSkillSourceAdapter(transport=raw_transport).resolve(
            SkillSource(kind=SkillSourceKind.GITHUB, location=raw_url)
        )

        self.assertEqual(blob.text, content.decode("utf-8"))
        self.assertEqual(raw.text, content.decode("utf-8"))
        self.assertEqual(blob.source, "https://github.com/acme/skills/blob/main/skills/review/SKILL.md")
        self.assertEqual(raw.source, "https://github.com/acme/skills/blob/main/SKILL.md")
        self.assertEqual(
            [call["url"] for call in blob_transport.calls],
            [
                "https://api.github.com/repos/acme/skills",
                blob_url,
                "https://api.github.com/repos/acme/skills/contents/review/SKILL.md?ref=main%2Fskills",
                "https://api.github.com/repos/acme/skills/contents/SKILL.md?ref=main%2Fskills%2Freview",
            ],
        )
        self.assertEqual([call["url"] for call in raw_transport.calls], [raw_url])

    async def test_github_raw_route_stays_anonymous_even_with_api_key(self) -> None:
        # [Credential Boundary] github.com/raw inputs become anonymous raw-host requests.
        content = _skill()
        raw_url = "https://raw.githubusercontent.com/acme/skills/main/SKILL.md"
        transport = _FakeTransport({raw_url: _text_response(content)})

        document = await GitHubSkillSourceAdapter(transport=transport).resolve(
            SkillSource(
                kind=SkillSourceKind.GITHUB,
                location="https://github.com/acme/skills/raw/main/SKILL.md?raw=1",
                api_key="private-key-marker",
            )
        )

        self.assertEqual(document.text, content.decode("utf-8"))
        self.assertEqual([call["url"] for call in transport.calls], [raw_url])
        self.assertNotIn("Authorization", transport.calls[0]["headers"])

    async def test_literal_slash_ref_is_ambiguous_until_revision_is_explicit(self) -> None:
        # [Ambiguous Ref] both valid branch/path splits fail closed rather than returning the first file.
        url = "https://github.com/acme/skills/blob/feature/topic/SKILL.md"
        first_content = _skill("topic-skill")
        second_content = _skill("feature-topic-skill")
        first_url = "https://api.github.com/repos/acme/skills/contents/topic/SKILL.md?ref=feature"
        second_url = "https://api.github.com/repos/acme/skills/contents/SKILL.md?ref=feature%2Ftopic"
        responses = {
            "https://api.github.com/repos/acme/skills": _response({"default_branch": "main"}),
            first_url: _contents_response(first_content, "topic/SKILL.md"),
            second_url: _contents_response(second_content, "SKILL.md"),
        }
        transport = _FakeTransport(responses)

        with self.assertRaisesRegex(SkillSourceError, "ambiguous revision"):
            await GitHubSkillSourceAdapter(transport=transport).resolve(SkillSource(kind=SkillSourceKind.GITHUB, location=url))

        self.assertIn(first_url, [call["url"] for call in transport.calls])
        self.assertIn(second_url, [call["url"] for call in transport.calls])

        explicit_url = "https://api.github.com/repos/acme/skills/contents/SKILL.md?ref=feature%2Ftopic"
        explicit_transport = _FakeTransport(
            {
                "https://api.github.com/repos/acme/skills": _response({"default_branch": "main"}),
                explicit_url: _contents_response(second_content, "SKILL.md"),
            }
        )
        explicit = await GitHubSkillSourceAdapter(transport=explicit_transport).resolve(
            SkillSource(kind=SkillSourceKind.GITHUB, location=url, revision="feature/topic")
        )
        self.assertEqual(explicit.name, "feature-topic-skill")
        self.assertEqual([call["url"] for call in explicit_transport.calls], ["https://api.github.com/repos/acme/skills", explicit_url])

    async def test_tree_url_rejects_two_existing_ref_path_interpretations(self) -> None:
        # [Wrong Content Prevention] a slash ref and nested tree path cannot select each other's SKILL.md.
        url = "https://github.com/acme/skills/tree/feature/topic"
        short_content = _skill("short-ref")
        slash_content = _skill("slash-ref")
        responses = {
            "https://api.github.com/repos/acme/skills": _response({"default_branch": "main"}),
            "https://api.github.com/repos/acme/skills/git/trees/feature?recursive=1": _response(
                {"tree": [{"path": "topic/SKILL.md", "type": "blob", "sha": "short-ref", "size": len(short_content)}], "truncated": False}
            ),
            "https://api.github.com/repos/acme/skills/git/blobs/short-ref": _blob_response(short_content, "short-ref"),
            "https://api.github.com/repos/acme/skills/git/trees/feature%2Ftopic?recursive=1": _response(
                {"tree": [{"path": "SKILL.md", "type": "blob", "sha": "slash-ref", "size": len(slash_content)}], "truncated": False}
            ),
            "https://api.github.com/repos/acme/skills/git/blobs/slash-ref": _blob_response(slash_content, "slash-ref"),
        }

        with self.assertRaisesRegex(SkillSourceError, "ambiguous revision"):
            await GitHubSkillSourceAdapter(transport=_FakeTransport(responses)).resolve(
                SkillSource(kind=SkillSourceKind.GITHUB, location=url)
            )

    async def test_alternate_interpretation_timeout_fails_closed(self) -> None:
        # [Transport Failure] an inconclusive alternate ref probe cannot silently accept the first interpretation.
        url = "https://github.com/acme/skills/blob/feature/topic/SKILL.md"
        first_url = "https://api.github.com/repos/acme/skills/contents/topic/SKILL.md?ref=feature"
        second_url = "https://api.github.com/repos/acme/skills/contents/SKILL.md?ref=feature%2Ftopic"
        responses = {
            "https://api.github.com/repos/acme/skills": _response({"default_branch": "main"}),
            first_url: _contents_response(_skill("short-ref"), "topic/SKILL.md"),
        }
        failures = {second_url: ProviderRequestError("simulated timeout", provider="github")}
        transport = _FakeTransport(responses, failures=failures)

        with self.assertRaisesRegex(SkillSourceError, "request could not be completed"):
            await GitHubSkillSourceAdapter(transport=transport).resolve(SkillSource(kind=SkillSourceKind.GITHUB, location=url))

        self.assertEqual([call["url"] for call in transport.calls], ["https://api.github.com/repos/acme/skills", first_url, second_url])

    async def test_too_many_ref_path_splits_requires_explicit_revision(self) -> None:
        # [Bounded Work] pathological URL depth is refused with guidance to pin one revision.
        location = "https://github.com/acme/skills/blob/branch/a/b/c/d/e/f/g/h/i/SKILL.md"
        transport = _FakeTransport({})

        with self.assertRaisesRegex(SkillSourceError, "set SkillSource.revision explicitly"):
            await GitHubSkillSourceAdapter(transport=transport).resolve(SkillSource(kind=SkillSourceKind.GITHUB, location=location))

        self.assertEqual(transport.calls, [])

    async def test_encoded_slash_revision_requires_explicit_revision(self) -> None:
        # [Edge Case] encoded slash refs are rejected unless the descriptor supplies their exact revision.
        location = "https://github.com/acme/skills/tree/feature%2Ftopic/guides/SKILL.md"
        missing_transport = _FakeTransport({})
        with self.assertRaisesRegex(SkillSourceError, "revision"):
            await GitHubSkillSourceAdapter(transport=missing_transport).resolve(SkillSource(kind=SkillSourceKind.GITHUB, location=location))
        self.assertEqual(missing_transport.calls, [])

        content = _skill()
        responses = {
            "https://api.github.com/repos/acme/skills": _response({"default_branch": "main"}),
            "https://api.github.com/repos/acme/skills/git/trees/feature%2Ftopic?recursive=1": _response(
                {"tree": [{"path": "guides/SKILL.md", "type": "blob", "sha": "slash-ref", "size": len(content)}], "truncated": False}
            ),
            "https://api.github.com/repos/acme/skills/git/blobs/slash-ref": _blob_response(content, "slash-ref"),
        }
        transport = _FakeTransport(responses)
        document = await GitHubSkillSourceAdapter(transport=transport).resolve(
            SkillSource(kind=SkillSourceKind.GITHUB, location=location, revision="feature/topic")
        )

        self.assertEqual(document.text, content.decode("utf-8"))
        self.assertIn("blob/feature%2Ftopic/guides/SKILL.md", document.source or "")

    async def test_truncated_tree_is_rejected(self) -> None:
        # [Truncated Catalog] an incomplete recursive tree cannot prove which skill matches.
        responses = _repository_and_tree(revision="trunk", tree=[], truncated=True)
        with self.assertRaisesRegex(SkillSourceError, "truncated"):
            await GitHubSkillSourceAdapter(transport=_FakeTransport(responses)).resolve(
                SkillSource(kind=SkillSourceKind.GITHUB, location="acme/skills")
            )

    async def test_invalid_hosts_userinfo_and_credential_queries_are_rejected(self) -> None:
        # [Security Boundary] malformed origins and query credentials are refused before transport use.
        locations = (
            "https://evil.example/acme/skills",
            "https://user:secret@github.com/acme/skills",
            "https://github.com/acme/skills?access_token=hidden-value",
            "https://github.com/acme/skills?raw=secret-value",
        )
        for location in locations:
            transport = _FakeTransport({})
            with self.subTest(location=urlsplit(location).hostname), self.assertRaises(SkillSourceError) as caught:
                await GitHubSkillSourceAdapter(transport=transport).resolve(SkillSource(kind=SkillSourceKind.GITHUB, location=location))
            self.assertNotIn("hidden-value", str(caught.exception))
            self.assertNotIn("secret-value", str(caught.exception))
            self.assertNotIn("secret", str(caught.exception))
            self.assertEqual(transport.calls, [])

    async def test_api_key_is_only_sent_to_api_and_errors_do_not_echo_it(self) -> None:
        # [Secret Handling] Bearer credentials stay on api.github.com and upstream error text is suppressed.
        key = "github-private-key-marker"
        responses = {"https://api.github.com/repos/acme/skills": _response({"message": key}, status=401)}
        transport = _FakeTransport(responses)
        with self.assertRaises(SkillSourceError) as caught:
            await GitHubSkillSourceAdapter(transport=transport).resolve(
                SkillSource(kind=SkillSourceKind.GITHUB, location="acme/skills", api_key=key)
            )

        self.assertEqual(transport.calls[0]["headers"].get("Authorization"), f"Bearer {key}")
        self.assertTrue(all(urlsplit(str(call["url"])).hostname == "api.github.com" for call in transport.calls))
        self.assertNotIn(key, str(caught.exception))

    async def test_raw_file_read_is_bounded_and_never_sends_api_key(self) -> None:
        # [Response Limit] a raw response over the local cap fails and receives no API credential.
        content = b"x" * 256_001
        url = "https://raw.githubusercontent.com/acme/skills/main/SKILL.md"
        transport = _FakeTransport({url: _text_response(content)})
        with self.assertRaisesRegex(SkillSourceError, "size limit"):
            await GitHubSkillSourceAdapter(transport=transport).resolve(
                SkillSource(kind=SkillSourceKind.GITHUB, location=url, api_key="private-key")
            )

        call = transport.calls[0]
        self.assertNotIn("Authorization", call["headers"])
        self.assertEqual(call["max_response_bytes"], 256_001)
        self.assertFalse(call["follow_redirects"])

    async def test_catalog_fetch_failure_is_not_silently_dropped(self) -> None:
        # [Silent Failure] a failed candidate aborts name-based catalog selection rather than hiding a possible match.
        wanted = _skill("wanted")
        responses = _repository_and_tree(
            revision="trunk",
            tree=[
                {"path": "a/SKILL.md", "type": "blob", "sha": "unavailable", "size": 80},
                {"path": "b/SKILL.md", "type": "blob", "sha": "wanted", "size": len(wanted)},
            ],
        )
        responses["https://api.github.com/repos/acme/skills/git/blobs/unavailable"] = _response({"message": "missing"}, status=404)
        responses["https://api.github.com/repos/acme/skills/git/blobs/wanted"] = _blob_response(wanted, "wanted")
        transport = _FakeTransport(responses)

        with self.assertRaises(SkillSourceError):
            await GitHubSkillSourceAdapter(transport=transport).resolve(
                SkillSource(kind=SkillSourceKind.GITHUB, location="acme/skills", skill_name="wanted")
            )

        self.assertEqual(len(transport.calls), 3)
        self.assertNotIn("missing", repr(transport.calls))

    async def test_git_blob_response_sha_must_match_tree_entry(self) -> None:
        # [Stale Response] content returned for another SHA cannot be mistaken for the selected tree entry.
        content = _skill()
        responses = _repository_and_tree(
            revision="trunk",
            tree=[{"path": "review/SKILL.md", "type": "blob", "sha": "requested-sha", "size": len(content)}],
        )
        responses["https://api.github.com/repos/acme/skills/git/blobs/requested-sha"] = _blob_response(content, "different-sha")

        with self.assertRaisesRegex(SkillSourceError, "different skill blob"):
            await GitHubSkillSourceAdapter(transport=_FakeTransport(responses)).resolve(
                SkillSource(kind=SkillSourceKind.GITHUB, location="acme/skills")
            )

    async def test_repository_frontmatter_name_must_match_requested_name(self) -> None:
        # [Catalog Match] a directory name cannot substitute for a missing requested frontmatter name.
        content = _skill("actual-name")
        responses = _repository_and_tree(
            revision="trunk",
            tree=[{"path": "wanted/SKILL.md", "type": "blob", "sha": "actual", "size": len(content)}],
        )
        responses["https://api.github.com/repos/acme/skills/git/blobs/actual"] = _blob_response(content, "actual")

        with self.assertRaisesRegex(SkillSourceError, "requested skill name"):
            await GitHubSkillSourceAdapter(transport=_FakeTransport(responses)).resolve(
                SkillSource(kind=SkillSourceKind.GITHUB, location="acme/skills", skill_name="wanted")
            )


class SkillsShSkillSourceTests(unittest.IsolatedAsyncioTestCase):
    """Checks skills.sh slug parsing and routes through the GitHub source API."""

    async def test_slug_selects_nested_github_skill_without_skills_sh_api(self) -> None:
        # [Realistic Usage] a leaderboard slug selects a unique nested SKILL.md through GitHub metadata.
        content = _skill("UX Guidelines", "Design review guidance")
        responses = _repository_and_tree(
            revision="development",
            tree=[{"path": "skills/ux-guidelines/SKILL.md", "type": "blob", "sha": "ux", "size": len(content)}],
        )
        responses["https://api.github.com/repos/acme/skills/git/blobs/ux"] = _blob_response(content, "ux")
        transport = _FakeTransport(responses)
        document = await SkillsShSkillSourceAdapter(transport=transport).resolve(
            SkillSource(kind=SkillSourceKind.SKILLS_SH, location="https://skills.sh/acme/skills/ux-guidelines")
        )

        self.assertEqual(document.name, "UX Guidelines")
        self.assertEqual(document.source, "https://github.com/acme/skills/blob/development/skills/ux-guidelines/SKILL.md")
        self.assertTrue(all(urlsplit(str(call["url"])).hostname == "api.github.com" for call in transport.calls))

    async def test_owner_repo_slug_shorthand_uses_same_github_catalog(self) -> None:
        # [Input Form] owner/repo/slug shorthand follows the same metadata and tree requests.
        content = _skill("ux-guidelines")
        responses = _repository_and_tree(
            revision="development",
            tree=[{"path": "skills/ux-guidelines/SKILL.md", "type": "blob", "sha": "ux", "size": len(content)}],
        )
        responses["https://api.github.com/repos/acme/skills/git/blobs/ux"] = _blob_response(content, "ux")

        document = await SkillsShSkillSourceAdapter(transport=_FakeTransport(responses)).resolve(
            SkillSource(kind=SkillSourceKind.SKILLS_SH, location="acme/skills/ux-guidelines")
        )

        self.assertEqual(document.name, "ux-guidelines")

    async def test_skills_sh_rejects_incomplete_or_foreign_selection(self) -> None:
        # [Validation] skills.sh descriptors must provide a safe owner/repository/slug tuple.
        adapter = SkillsShSkillSourceAdapter(transport=_FakeTransport({}))
        for location in ("acme/skills", "https://evil.example/acme/skills/slug", "https://skills.sh/acme/skills/slug?token=hidden"):
            with self.subTest(location=location), self.assertRaises(SkillSourceError):
                await adapter.resolve(SkillSource(kind=SkillSourceKind.SKILLS_SH, location=location))


if __name__ == "__main__":
    unittest.main()
