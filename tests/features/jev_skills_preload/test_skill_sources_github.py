"""FILE: tests/features/jev_skills_preload/test_skill_sources_github.py

PURPOSE: Pin GitHubSkill loading: one commit lookup and at most one tree listing per (repo, ref, token) group, raw SKILL.md fetches labelled with the SHA, the status map for every step (remembered or retried as the spec says), ref and path handling, the shallowest-match tree search, per-entry isolation of failures, the raw-file cap, and token precedence.
ROLE IN CODEBASE: Covers spec AC-7, INV-7, INV-8, FR-9, NFR-3, D-10, D-11, D-18, D-21, D-31 and EC-52 to EC-71, EC-112, EC-117 for vidbyte/agents/skills/github.py through vidbyte/agents/skills/loader.py.
ARCHITECTURE NOTE: Every request is answered by the conftest's URL-routed fake of HttpTransport._send_once, so the real transport's retry loop, the real SkillFetch step, SkillMarkdown, and the loader's memory all run. "Remembered" is observed as a second load that sends nothing.
FUNCTION INVENTORY: test_one_repo_and_ref_share_one_commit_lookup_and_one_tree_listing; test_commit_lookup_status_is_mapped_for_every_entry_in_the_group; test_raw_file_failure_stays_with_its_own_entry; test_full_sha_skips_the_lookup_and_other_refs_are_one_encoded_segment; test_tree_search_takes_the_shallowest_exact_folder; test_tree_search_without_a_match_or_with_a_tie_explains_path; test_truncated_tree_affects_only_entries_without_path; test_unusable_lookup_or_listing_is_fetch_failed_and_retried_next_load; test_well_formed_listing_without_the_skill_stays_not_found; test_raw_file_cap_is_inclusive; test_token_precedence_and_stripping; test_different_tokens_never_share_a_group.
COMMON MODIFICATION PATTERNS: A new status rule adds a row to STATUS_ROWS with its reason, whether it is remembered, how many attempts the transport makes, and the words the detail must hold.
WHAT NOT TO DO IN THIS FILE: 1. Do not let any request reach api.github.com; the fake raises on an unrouted URL. 2. Do not assert the order of concurrent raw fetches, only their counts.
KNOWN EDGE CASES: 429, 500, 502, 503, and 504 are retried once by the transport, 529 and every 3xx are not. A 403 is a rate limit only with x-ratelimit-remaining: 0 or a retry-after header. Response header names are lowercase, as httpx gives them.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 5 sequence diagram, 6.3 GitHubSkill, 9.2 URLs and failure mapping)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_github.py
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import pytest

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.agents.skills.loader import SkillLoader
    from vidbyte.lib.constants.skills import SKILL_MARKDOWN_MAX_BYTES

    from vidbyte import GitHubSkill, SkillUnavailableReason
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

API = "https://api.github.com"
REPO = "anthropics/skills"
SHA = "0123456789abcdef0123456789abcdef01234567"
BODY_MARKER = "UPSTREAM-BODY-MARKER-91c2"
REF = "v1.2.0"


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def commit_url(ref: str = "HEAD", repo: str = REPO) -> str:
    return f"{API}/repos/{repo}/commits/{quote(ref, safe='')}"


def tree_url(sha: str = SHA, repo: str = REPO) -> str:
    return f"{API}/repos/{repo}/git/trees/{sha}?recursive=1"


def raw_url(folder: str, sha: str = SHA, repo: str = REPO) -> str:
    return f"{API}/repos/{repo}/contents/{quote(folder + '/SKILL.md', safe='/')}?ref={sha}"


def tree_body(*paths: str, truncated: bool = False) -> str:
    return json.dumps({"sha": SHA, "tree": [{"path": path, "type": "blob", "mode": "100644"} for path in paths], "truncated": truncated})


def skill_file(name: str) -> bytes:
    return f"---\nname: {name}\ndescription: The {name} skill.\n---\nBody of {name}.\n".encode()


def label(folder: str) -> str:
    return f"github:{REPO}@{SHA[:12]}/{folder}/SKILL.md"


@pytest.mark.asyncio
async def test_one_repo_and_ref_share_one_commit_lookup_and_one_tree_listing(fake_http: Any) -> None:
    # AC-7, INV-7, NFR-3: five skills from one repository must cost seven requests, not fifteen.
    fake_http.answer(commit_url(), fake_http.reply(200, SHA))
    fake_http.answer(tree_url(), fake_http.reply(200, tree_body("skills/webapp-testing/SKILL.md", "skills/pdf/SKILL.md", "document-skills/docx/SKILL.md", "skills/pdf/reference.md", "README.md")))
    folders = {"webapp-testing": "skills/webapp-testing", "pdf": "skills/pdf", "docx": "document-skills/docx"}
    for name, folder in folders.items():
        fake_http.answer(raw_url(folder), fake_http.reply(200, skill_file(name)))
    resolutions = await SkillLoader(tuple(GitHubSkill(name=name, repo=REPO) for name in folders)).load()
    assert [resolution.document.source if resolution.document else resolution for resolution in resolutions] == [label(folder) for folder in folders.values()]
    assert [resolution.document.text for resolution in resolutions] == [f"Body of {name}.\n" for name in folders]
    assert (fake_http.count(commit_url()), fake_http.count(tree_url())) == (1, 1)
    assert sorted(fake_http.urls()) == sorted([commit_url(), tree_url(), *(raw_url(folder) for folder in folders.values())])
    accepts = {request.url: request.headers.get("accept") for request in fake_http.sent}
    assert accepts[commit_url()] == "application/vnd.github.sha"
    assert accepts[tree_url()] == "application/vnd.github+json"
    assert {accepts[raw_url(folder)] for folder in folders.values()} == {"application/vnd.github.raw"}
    assert all("authorization" not in request.headers for request in fake_http.sent)


# (case, status, response headers, reason, remembered, attempts on the commit URL, words the detail must hold)
STATUS_ROWS = [
    ("404 missing or private", 404, {}, "NOT_FOUND", True, 1, ("GITHUB_TOKEN", "token=")),
    ("422 unknown ref", 422, {}, "NOT_FOUND", True, 1, (REF,)),
    ("401 bad token", 401, {}, "AUTH_FAILED", True, 1, ("GITHUB_TOKEN",)),
    ("403 primary limit", 403, {"X-RateLimit-Remaining": "0"}, "RATE_LIMITED", False, 1, ("GITHUB_TOKEN",)),
    ("403 secondary limit", 403, {"Retry-After": "60"}, "RATE_LIMITED", False, 1, ()),
    ("403 with quota left", 403, {"X-RateLimit-Remaining": "4999"}, "AUTH_FAILED", True, 1, ("GITHUB_TOKEN",)),
    ("403 sso or blocked", 403, {}, "AUTH_FAILED", True, 1, ("GITHUB_TOKEN",)),
    ("429", 429, {"Retry-After": "1"}, "RATE_LIMITED", False, 2, ()),
    ("500", 500, {}, "FETCH_FAILED", False, 2, ("500",)),
    ("503", 503, {}, "FETCH_FAILED", False, 2, ("503",)),
    ("529", 529, {}, "FETCH_FAILED", False, 1, ("529",)),
    ("400", 400, {}, "FETCH_FAILED", False, 1, ("400",)),
    ("418 other 4xx", 418, {}, "FETCH_FAILED", False, 1, ("418",)),
    ("304 other 3xx", 304, {}, "FETCH_FAILED", False, 1, ("304",)),
    ("301 moved", 301, {"Location": "https://api.github.com/repositories/1"}, "NOT_FOUND", True, 1, ("301", "owner/repo")),
    ("302", 302, {"Location": "https://example.invalid/"}, "NOT_FOUND", True, 1, ("302",)),
    ("307", 307, {"Location": "https://example.invalid/"}, "NOT_FOUND", True, 1, ("307",)),
    ("308", 308, {"Location": "https://example.invalid/"}, "NOT_FOUND", True, 1, ("308",)),
]


@pytest.mark.parametrize(("case", "status", "headers", "reason", "remembered", "attempts", "hints"), STATUS_ROWS, ids=[row[0] for row in STATUS_ROWS])
@pytest.mark.asyncio
async def test_commit_lookup_status_is_mapped_for_every_entry_in_the_group(fake_http: Any, case: str, status: int, headers: dict[str, str], reason: str, remembered: bool, attempts: int, hints: tuple[str, ...]) -> None:
    # EC-52 to EC-57, EC-66, EC-71, D-10, D-11: a shared step's failure applies to exactly the entries that needed it.
    fake_http.answer(commit_url(REF), fake_http.reply(status, f"<html>{BODY_MARKER}</html>", headers))
    loader = SkillLoader((GitHubSkill(name="pdf", repo=REPO, ref=REF, path="skills/pdf"), GitHubSkill(name="docx", repo=REPO, ref=REF, path="skills/docx")))
    resolutions = await loader.load()
    assert [resolution.reason for resolution in resolutions] == [SkillUnavailableReason[reason]] * 2
    assert fake_http.count(commit_url(REF)) == attempts
    assert fake_http.urls() == [commit_url(REF)] * attempts
    for resolution in resolutions:
        assert all(hint.lower() in resolution.detail.lower() for hint in hints), resolution.detail
        assert BODY_MARKER not in resolution.detail
    # A remembered failure costs nothing on the next load; a transient one asks again.
    await loader.load()
    assert (fake_http.count(commit_url(REF)) == attempts) is remembered


@pytest.mark.asyncio
async def test_raw_file_failure_stays_with_its_own_entry(fake_http: Any) -> None:
    # INV-8, EC-69: one missing folder must not hide its sibling, and the detail names the path that was missing.
    fake_http.answer(commit_url(REF), fake_http.reply(200, SHA))
    fake_http.answer(raw_url("skills/pdf"), fake_http.reply(404, f'{{"message": "{BODY_MARKER}"}}'))
    fake_http.answer(raw_url("skills/docx"), fake_http.reply(200, skill_file("docx")))
    fake_http.answer(raw_url("skills/xlsx"), fake_http.reply(503, BODY_MARKER))
    pdf, docx, xlsx = await SkillLoader(tuple(GitHubSkill(name=name, repo=REPO, ref=REF, path=f"skills/{name}") for name in ("pdf", "docx", "xlsx"))).load()
    assert pdf.reason is SkillUnavailableReason.NOT_FOUND and "skills/pdf" in pdf.detail and BODY_MARKER not in pdf.detail
    assert docx.document is not None and docx.document.source == label("skills/docx")
    assert xlsx.reason is SkillUnavailableReason.FETCH_FAILED
    assert (fake_http.count(commit_url(REF)), fake_http.count(raw_url("skills/xlsx"))) == (1, 2)


@pytest.mark.asyncio
async def test_full_sha_skips_the_lookup_and_other_refs_are_one_encoded_segment(fake_http: Any) -> None:
    # EC-59, EC-60, D-18: a pinned SHA needs no lookup; a branch name with a slash stays one path segment.
    fake_http.answer(raw_url("skills/pdf"), fake_http.reply(200, skill_file("pdf")))
    (pinned,) = await SkillLoader((GitHubSkill(name="pdf", repo=REPO, ref=SHA, path="skills/pdf"),)).load()
    assert pinned.document is not None and pinned.document.source == label("skills/pdf")
    assert fake_http.urls() == [raw_url("skills/pdf")]
    fake_http.answer(f"{API}/repos/{REPO}/commits/release%2Fv1", fake_http.reply(200, SHA))
    (branch,) = await SkillLoader((GitHubSkill(name="pdf", repo=REPO, ref="release/v1", path="skills/pdf"),)).load()
    assert branch.document is not None
    assert fake_http.urls()[1:] == [f"{API}/repos/{REPO}/commits/release%2Fv1", raw_url("skills/pdf")]


@pytest.mark.parametrize(
    ("paths", "folder"),
    [
        (("a/b/pdf/SKILL.md", "skills/pdf/SKILL.md", "x/y/z/pdf/SKILL.md"), "skills/pdf"),
        (("skills/pdf/SKILL.md", "pdf/SKILL.md"), "pdf"),
        (("not-pdf/SKILL.md", "pdfx/SKILL.md", "deep/er/pdf/SKILL.md"), "deep/er/pdf"),
    ],
    ids=["shallowest of three depths", "repository root folder", "exact folder name only"],
)
@pytest.mark.asyncio
async def test_tree_search_takes_the_shallowest_exact_folder(fake_http: Any, paths: tuple[str, ...], folder: str) -> None:
    # EC-64, D-18: the npx skills shadowing rule; a prefix or suffix of the name is not a match.
    fake_http.answer(commit_url(), fake_http.reply(200, SHA))
    fake_http.answer(tree_url(), fake_http.reply(200, tree_body(*paths)))
    fake_http.answer(raw_url(folder), fake_http.reply(200, skill_file("pdf")))
    (resolution,) = await SkillLoader((GitHubSkill(name="pdf", repo=REPO),)).load()
    assert resolution.document is not None and resolution.document.source == label(folder)


@pytest.mark.asyncio
async def test_tree_search_without_a_match_or_with_a_tie_explains_path(fake_http: Any) -> None:
    # EC-62, EC-63, EC-73: both are remembered, and both tell the developer to pass path=.
    fake_http.answer(commit_url(), fake_http.reply(200, SHA))
    fake_http.answer(tree_url(), fake_http.reply(200, tree_body("not-pdf/SKILL.md", "pdfx/SKILL.md", "SKILL.md", "a/docx/SKILL.md", "b/docx/SKILL.md", "skills/pdf/README.md")))
    loader = SkillLoader((GitHubSkill(name="pdf", repo=REPO), GitHubSkill(name="docx", repo=REPO)))
    missing, tie = await loader.load()
    assert missing.reason is SkillUnavailableReason.NOT_FOUND
    assert REPO in missing.detail and SHA[:7] in missing.detail and "path=" in missing.detail
    assert tie.reason is SkillUnavailableReason.INVALID_SKILL
    assert "a/docx" in tie.detail and "b/docx" in tie.detail and "path=" in tie.detail
    sent = len(fake_http.sent)
    await loader.load()
    assert len(fake_http.sent) == sent


@pytest.mark.asyncio
async def test_truncated_tree_affects_only_entries_without_path(fake_http: Any) -> None:
    # EC-65, INV-8: a truncated listing cannot prove a folder is the only match; entries with path never needed it.
    fake_http.answer(commit_url(), fake_http.reply(200, SHA))
    fake_http.answer(tree_url(), fake_http.reply(200, tree_body("skills/pdf/SKILL.md", truncated=True)))
    fake_http.answer(raw_url("skills/docx"), fake_http.reply(200, skill_file("docx")))
    fake_http.answer(raw_url("skills/xlsx"), fake_http.reply(404, BODY_MARKER))
    searched, explicit, missing = await SkillLoader((GitHubSkill(name="pdf", repo=REPO), GitHubSkill(name="docx", repo=REPO, path="skills/docx"), GitHubSkill(name="xlsx", repo=REPO, path="skills/xlsx"))).load()
    assert searched.reason is SkillUnavailableReason.INVALID_SKILL and "path=" in searched.detail
    assert explicit.document is not None and explicit.document.source == label("skills/docx")
    assert missing.reason is SkillUnavailableReason.NOT_FOUND
    assert raw_url("skills/pdf") not in fake_http.urls()


UNEXPECTED = ("unexpected",)
UNREACHABLE = ("api.github.com", "next run")

# (case, commit answer, tree answer or None when the commit step already failed, words the detail must hold)
UNUSABLE_ROWS = [
    ("commit connection error", "connection", None, UNREACHABLE),
    ("commit answer is a proxy page", f"<html>{BODY_MARKER}</html>", None, UNEXPECTED),
    ("commit answer is a short sha", SHA[:12], None, UNEXPECTED),
    ("tree is not json", SHA, f"<html>{BODY_MARKER}</html>", UNEXPECTED),
    ("tree has no list", SHA, json.dumps({"sha": SHA, "truncated": False}), UNEXPECTED),
    ("tree list is an object", SHA, json.dumps({"sha": SHA, "tree": {"path": "pdf/SKILL.md"}}), UNEXPECTED),
    ("tree nests 2000 levels", SHA, '{"sha": "x", "tree": ' + "[" * 2000 + "]" * 2000 + "}", UNEXPECTED),
    ("tree connection error", SHA, "connection", (*UNREACHABLE, "path=")),
    ("tree keeps answering 503", SHA, 503, ("503",)),
    # EC-68 (r5, S4-R-1): a tree list whose items are not all objects with a text path. The first row is what
    # Python 3.12+ parses the 2000-level body to, so these rows pin the rule on every Python version.
    ("tree items are lists as 3.12 parses 2000 levels", SHA, json.dumps({"sha": "x", "tree": [[[]]]}), UNEXPECTED),
    ("tree items are not objects", SHA, json.dumps({"sha": SHA, "tree": [1, "a", None]}), UNEXPECTED),
    ("tree item has no path", SHA, json.dumps({"sha": SHA, "tree": [{"type": "blob"}]}), UNEXPECTED),
    ("tree item path is not text", SHA, json.dumps({"sha": SHA, "tree": [{"path": 7, "type": "blob"}]}), UNEXPECTED),
    ("one usable item beside a list item", SHA, json.dumps({"sha": SHA, "tree": [{"path": "skills/pdf/SKILL.md", "type": "blob"}, []]}), UNEXPECTED),
]


@pytest.mark.parametrize(("case", "commit", "tree", "hints"), UNUSABLE_ROWS, ids=[row[0] for row in UNUSABLE_ROWS])
@pytest.mark.asyncio
async def test_unusable_lookup_or_listing_is_fetch_failed_and_retried_next_load(fake_http: Any, case: str, commit: str, tree: str | int | None, hints: tuple[str, ...]) -> None:
    # EC-66 to EC-68, EC-112, EC-117, D-29: a bad answer is the network's fault, so the next run tries again.
    fake_http.answer(commit_url(), fake_http.connection_error() if commit == "connection" else fake_http.reply(200, commit))
    if tree == "connection":
        fake_http.answer(tree_url(), fake_http.connection_error())
    elif isinstance(tree, int):
        fake_http.answer(tree_url(), fake_http.reply(tree, BODY_MARKER))
    elif tree is not None:
        fake_http.answer(tree_url(), fake_http.reply(200, tree))
    loader = SkillLoader((GitHubSkill(name="pdf", repo=REPO),))
    (resolution,) = await loader.load()
    assert resolution.reason is SkillUnavailableReason.FETCH_FAILED
    assert all(hint.lower() in resolution.detail.lower() for hint in hints), resolution.detail
    assert BODY_MARKER not in resolution.detail
    first_round = len(fake_http.sent)
    await loader.load()
    assert fake_http.count(commit_url()) == 2
    assert len(fake_http.sent) == 2 * first_round


# (case, tree items that are all objects with a text path but hold no pdf/SKILL.md blob)
WELL_FORMED_TREES = [
    ("empty tree", []),
    ("folders and a submodule only", [{"path": "skills", "type": "tree", "mode": "040000"}, {"path": "skills/pdf", "type": "tree", "mode": "040000"}, {"path": "vendor/lib", "type": "commit", "mode": "160000"}]),
]


@pytest.mark.parametrize(("case", "items"), WELL_FORMED_TREES, ids=[row[0] for row in WELL_FORMED_TREES])
@pytest.mark.asyncio
async def test_well_formed_listing_without_the_skill_stays_not_found(fake_http: Any, case: str, items: list[dict[str, str]]) -> None:
    # EC-62, EC-68: the item check refuses only items that are not objects with a text path. An empty tree, or
    # folder and submodule entries, are a real answer, so the miss stays not_found and is remembered.
    fake_http.answer(commit_url(), fake_http.reply(200, SHA))
    fake_http.answer(tree_url(), fake_http.reply(200, json.dumps({"sha": SHA, "tree": items, "truncated": False})))
    loader = SkillLoader((GitHubSkill(name="pdf", repo=REPO),))
    (resolution,) = await loader.load()
    assert resolution.reason is SkillUnavailableReason.NOT_FOUND, resolution
    assert "path=" in resolution.detail
    sent = len(fake_http.sent)
    await loader.load()
    assert len(fake_http.sent) == sent


@pytest.mark.asyncio
async def test_raw_file_cap_is_inclusive(fake_http: Any) -> None:
    # EC-70, INV-12: a SKILL.md of exactly the cap loads; one byte more is remembered as too_large.
    head = b"---\nname: big\ndescription: A large skill.\n---\n"
    fake_http.answer(commit_url(REF), fake_http.reply(200, SHA))
    fake_http.answer(raw_url("skills/at-cap"), fake_http.reply(200, head + b"x" * (SKILL_MARKDOWN_MAX_BYTES - len(head))))
    fake_http.answer(raw_url("skills/over-cap"), fake_http.reply(200, head + b"x" * (SKILL_MARKDOWN_MAX_BYTES + 1 - len(head))))
    loader = SkillLoader((GitHubSkill(name="at-cap", repo=REPO, ref=REF, path="skills/at-cap"), GitHubSkill(name="over-cap", repo=REPO, ref=REF, path="skills/over-cap")))
    loaded, refused = await loader.load()
    assert loaded.document is not None
    assert refused.reason is SkillUnavailableReason.TOO_LARGE
    assert {request.max_response_bytes for request in fake_http.sent if "/contents/" in request.url} == {SKILL_MARKDOWN_MAX_BYTES}
    sent = len(fake_http.sent)
    await loader.load()
    assert len(fake_http.sent) == sent


@pytest.mark.parametrize(
    ("entry_token", "env_token", "sent"),
    [
        ("  ghp_entryFAKE000000000000000000000000  ", "ghp_envFAKE0000000000000000000000000000", "Bearer ghp_entryFAKE000000000000000000000000"),
        (None, "\tghp_envFAKE0000000000000000000000000000\n", "Bearer ghp_envFAKE0000000000000000000000000000"),
        (None, "   ", None),
        (None, None, None),
    ],
    ids=["entry token wins and is stripped", "env token is stripped", "blank env token means none", "no token"],
)
@pytest.mark.asyncio
async def test_token_precedence_and_stripping(monkeypatch: pytest.MonkeyPatch, fake_http: Any, entry_token: str | None, env_token: str | None, sent: str | None) -> None:
    # D-30, section 9.3: the entry's token, else GITHUB_TOKEN read at load time; the stripped value is the one sent.
    if env_token is not None:
        monkeypatch.setenv("GITHUB_TOKEN", env_token)
    fake_http.answer(commit_url(REF), fake_http.reply(200, SHA))
    fake_http.answer(raw_url("skills/pdf"), fake_http.reply(200, skill_file("pdf")))
    (resolution,) = await SkillLoader((GitHubSkill(name="pdf", repo=REPO, ref=REF, path="skills/pdf", token=entry_token),)).load()
    assert resolution.document is not None, resolution
    assert {request.headers.get("authorization") for request in fake_http.sent} == {sent}


@pytest.mark.asyncio
async def test_different_tokens_never_share_a_group(fake_http: Any) -> None:
    # EC-61, INV-7: one token's visibility must not decide another entry's result.
    fake_http.answer(commit_url(REF), fake_http.reply(200, SHA))
    for name in ("pdf", "docx", "xlsx"):
        fake_http.answer(raw_url(f"skills/{name}"), fake_http.reply(200, skill_file(name)))
    entries = (
        GitHubSkill(name="pdf", repo=REPO, ref=REF, path="skills/pdf", token="ghp_teamAFAKE"),
        GitHubSkill(name="docx", repo=REPO, ref=REF, path="skills/docx", token="ghp_teamBFAKE"),
        GitHubSkill(name="xlsx", repo=REPO, ref=REF, path="skills/xlsx", token="ghp_teamAFAKE"),
    )
    resolutions = await SkillLoader(entries).load()
    assert all(resolution.document is not None for resolution in resolutions)
    lookups = [request.headers.get("authorization") for request in fake_http.sent if request.url == commit_url(REF)]
    assert sorted(lookups) == ["Bearer ghp_teamAFAKE", "Bearer ghp_teamBFAKE"]
    raw_tokens = {request.url: request.headers.get("authorization") for request in fake_http.sent if "/contents/" in request.url}
    assert raw_tokens == {raw_url("skills/pdf"): "Bearer ghp_teamAFAKE", raw_url("skills/docx"): "Bearer ghp_teamBFAKE", raw_url("skills/xlsx"): "Bearer ghp_teamAFAKE"}
