"""FILE: tests/features/public_skill_loader/test_public_skill_loader_acceptance.py

PURPOSE: Run the public door end to end as a program that never builds a JevAgent: the spec's section 4 snippet prints exactly its three lines, one entry from each of the six sources plus a caller document resolves through root imports into exact text in input order, seven failing sources come back as reasons beside a healthy entry, and a second asyncio.run on a new event loop reuses the loader's memory and retries only the transient failure.
ROLE IN CODEBASE: Covers spec AC-1, AC-2, AC-7, AC-13, INV-5, INV-6, INV-7, INV-10, INV-11, NFR-5, G-1 and G-2 for vidbyte/__init__.py (the root exports) and vidbyte/agents/skills/loader.py.
ARCHITECTURE NOTE: Files are real under tmp_path and every request is answered at HttpTransport._send_once by the conftest's URL-routed fake, so the real SkillFetch, SkillMarkdown, resolvers, and loader memory run. The snippet is executed from its exact text, so its own import line is part of what is tested.
FUNCTION INVENTORY: test_spec_snippet_prints_its_three_lines; test_every_source_resolves_through_the_root_door_in_input_order; test_failing_sources_come_back_as_reasons_beside_a_healthy_entry; test_second_asyncio_run_reuses_memory_and_retries_only_transient_failures.
COMMON MODIFICATION PATTERNS: If spec section 4 changes, copy the snippet into SNIPPET verbatim and update the expected lines.
WHAT NOT TO DO IN THIS FILE: 1. Do not edit SNIPPET to make it pass; it is the user-facing contract. 2. Do not build a JevAgent here; the point is a caller that never does. 3. Do not mark the asyncio.run tests asyncio; they are plain functions so asyncio.run has no running loop.
KNOWN EDGE CASES: The snippet's LocalSkill path is relative, so it is pinned to the test's working folder (tmp_path), which has no no-such-folder/pdf/SKILL.md. The transport retries 429 and 503 once, so each such route is asked twice per load. A remembered resolution is never replaced, so only a file-read recorder, not the results, proves a remembered entry was not read again.
RELATED DOCS: docs/spec/public-skill-loader/spec.md (sections 4, 6.1, 6.2 AC-1, AC-2, AC-7, AC-13, 9.2 row 1)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/public_skill_loader/test_public_skill_loader_acceptance.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from vidbyte.lib.constants.skills import SKILL_MARKDOWN_MAX_BYTES

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte import (
        AnthropicSkill,
        GitHubSkill,
        InlineSkill,
        LocalSkill,
        OpenAISkill,
        SkillDocument,
        SkillLoader,
        SkillResolution,
        SkillsShSkill,
        SkillUnavailableReason,
    )
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

API = "https://api.github.com"
SHA = "0123456789abcdef0123456789abcdef01234567"

# Spec section 4, verbatim. Do not edit it to make the test pass.
SNIPPET = r'''
import asyncio

from vidbyte import ConfigurationError, InlineSkill, LocalSkill, SkillLoader

entries = (
    InlineSkill(name="house-review", description="Our review checklist.", text="Read the tests first.\n"),
    LocalSkill(name="pdf", path="no-such-folder/pdf"),
)
loader = SkillLoader(entries)  # a tuple or a list; reads no file, key, or URL
resolutions = asyncio.run(loader.load())  # inside a running loop: await loader.load()
for entry, resolution in zip(entries, resolutions, strict=True):
    if resolution.document is not None:
        print(entry.name, "loaded", len(resolution.document.text.encode("utf-8")), "bytes")
    else:
        print(entry.name, resolution.reason.value, resolution.transient)

try:
    SkillLoader((entries[0], entries[0]))
except ConfigurationError as error:
    print("rejected:", error.details["names"])
'''


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def raw_url(repo: str, folder: str) -> str:
    # A GitHub entry pinned to a full SHA with an explicit folder costs exactly this one request.
    return f"{API}/repos/{repo}/contents/{folder}/SKILL.md?ref={SHA}"


def body_of(name: str) -> str:
    # Leading spaces, a CRLF, a blank line, and no final newline: any trim or newline rewrite changes it.
    return f"  {name}: the first line keeps its indent.\r\n\nThe last line has no newline."


def test_spec_snippet_prints_its_three_lines(capsys: pytest.CaptureFixture[str]) -> None:
    # AC-1, G-1: the working folder is the autouse fixture's empty tmp_path, so pdf is not_found.
    exec(compile(SNIPPET, "spec-section-4-snippet", "exec"), {"__name__": "spec_section_4_snippet"})
    assert capsys.readouterr().out.splitlines() == [
        "house-review loaded 22 bytes",
        "pdf not_found False",
        "rejected: ['house-review']",
    ]


@pytest.mark.asyncio
async def test_every_source_resolves_through_the_root_door_in_input_order(tmp_path: Path, fake_http: Any, write_skill: Callable[..., Path], skill_md: Callable[..., bytes]) -> None:
    # AC-2, NFR-5, INV-5, INV-7: the list a repeatable option collects; names are out of sorted order on purpose.
    write_skill(tmp_path / "skills" / "sql-migrations", skill_md("sql-migrations", body_of("sql-migrations")))
    write_skill(tmp_path / ".agents" / "skills" / "react-best-practices", skill_md("react-best-practices", body_of("react-best-practices")))
    remote = {
        raw_url("anthropics/skills", "skills/webapp-testing"): "webapp-testing",
        "https://api.anthropic.com/v1/skills/skill_01AbCd/versions/1/content": "release-notes",
        "https://api.openai.com/v1/skills/skill_abc/versions/2/content": "spreadsheets",
    }
    for url, name in remote.items():
        fake_http.answer(url, fake_http.reply(200, skill_md(name, body_of(name))))
    caller_document = SkillDocument(name="caller-notes", description="Resolved by the caller.", text="  Caller text, kept exactly.\n")
    entries = [
        InlineSkill(name="house-review", description="Our review checklist.", text=body_of("house-review")),
        LocalSkill(name="sql-migrations", path="skills/sql-migrations"),
        SkillsShSkill(name="react-best-practices", source="vercel-labs/agent-skills"),
        GitHubSkill(name="webapp-testing", repo="anthropics/skills", ref=SHA, path="skills/webapp-testing", token="ghp_FAKEtokenForTests000000000000000000"),
        AnthropicSkill(name="release-notes", skill_id="skill_01AbCd", version="1", api_key="sk-ant-api03-FAKE-KEY"),
        OpenAISkill(name="spreadsheets", skill_id="skill_abc", version="2", api_key="sk-proj-FAKE-KEY"),
        caller_document,
    ]

    resolutions = await SkillLoader(entries).load()

    assert isinstance(resolutions, tuple) and all(isinstance(resolution, SkillResolution) for resolution in resolutions)
    assert [(resolution.reason, resolution.detail) for resolution in resolutions] == [(None, None)] * len(entries)
    assert [resolution.document.name for resolution in resolutions] == [entry.name for entry in entries]
    assert [resolution.document.text for resolution in resolutions[:6]] == [body_of(entry.name) for entry in entries[:6]]
    assert resolutions[6].document is caller_document
    assert sorted(fake_http.urls()) == sorted(remote)


@pytest.mark.asyncio
async def test_failing_sources_come_back_as_reasons_beside_a_healthy_entry(tmp_path: Path, fake_http: Any, write_skill: Callable[..., Path], skill_md: Callable[..., bytes]) -> None:
    # AC-7, INV-6, G-2: expected failures are data; none aborts the load or moves the healthy result from its slot.
    write_skill(tmp_path / "skills" / "malformed", b"No frontmatter here, only text.\n")
    head = skill_md("oversized", "", "Too big.")
    write_skill(tmp_path / "skills" / "oversized", head + b"x" * (SKILL_MARKDOWN_MAX_BYTES + 1 - len(head)))
    fake_http.answer(raw_url("acme/skills", "skills/gone"), fake_http.reply(404, "Not Found"))
    fake_http.answer(raw_url("acme/busy", "skills/throttled"), fake_http.reply(429, "slow down"))
    entries = (
        LocalSkill(name="missing-folder", path=tmp_path / "nowhere" / "missing-folder"),
        SkillsShSkill(name="not-installed", source="acme/skills"),
        GitHubSkill(name="gone", repo="acme/skills", ref=SHA, path="skills/gone"),
        InlineSkill(name="healthy", description="Still loads.", text="Healthy text.\n"),
        AnthropicSkill(name="no-key", skill_id="skill_nokey"),
        GitHubSkill(name="throttled", repo="acme/busy", ref=SHA, path="skills/throttled"),
        LocalSkill(name="malformed", path=tmp_path / "skills" / "malformed"),
        LocalSkill(name="oversized", path=tmp_path / "skills" / "oversized"),
    )

    resolutions = await SkillLoader(entries).load()

    reason = SkillUnavailableReason
    assert [resolution.reason for resolution in resolutions] == [
        reason.NOT_FOUND, reason.NOT_INSTALLED, reason.NOT_FOUND, None, reason.AUTH_FAILED, reason.RATE_LIMITED, reason.INVALID_SKILL, reason.TOO_LARGE,
    ]
    assert resolutions[3].document is not None and resolutions[3].document.text == "Healthy text.\n"
    failures = [resolution for index, resolution in enumerate(resolutions) if index != 3]
    assert all(resolution.document is None and isinstance(resolution.detail, str) and resolution.detail.strip() for resolution in failures)
    assert [resolution.transient for resolution in resolutions] == [False, False, False, False, False, True, False, False]
    # A missing key sends nothing; the two GitHub routes are asked (the 429 twice, through the transport's retry).
    assert sorted(fake_http.urls()) == sorted([raw_url("acme/skills", "skills/gone")] + [raw_url("acme/busy", "skills/throttled")] * 2)


def test_second_asyncio_run_reuses_memory_and_retries_only_transient_failures(tmp_path: Path, fake_http: Any, write_skill: Callable[..., Path], skill_md: Callable[..., bytes], record_io: Callable[[], Any]) -> None:
    # AC-13, INV-10, INV-11: a synchronous caller runs each load on a fresh event loop, so any loop-bound
    # state in the loader fails on the second run; the transient entry makes that run do real async work.
    present = write_skill(tmp_path / "skills" / "present", skill_md("present", "Present text.\n"))
    absent = tmp_path / "skills" / "absent"
    flaky = raw_url("acme/flaky", "skills/flaky")
    fake_http.answer(flaky, fake_http.reply(503, "busy"), fake_http.reply(503, "busy"), fake_http.reply(200, skill_md("flaky", "Flaky text.\n")))
    loader = SkillLoader([LocalSkill(name="present", path=present), LocalSkill(name="absent", path=absent), GitHubSkill(name="flaky", repo="acme/flaky", ref=SHA, path="skills/flaky")])

    first = asyncio.run(loader.load())
    assert [resolution.reason for resolution in first] == [None, SkillUnavailableReason.NOT_FOUND, SkillUnavailableReason.FETCH_FAILED]
    assert fake_http.count(flaky) == 2
    # Change both folders on disk; remembered entries must not notice, because they are never read again.
    (present / "SKILL.md").unlink()
    write_skill(absent, skill_md("absent", "Late text.\n"))
    with record_io() as second_run:
        second = asyncio.run(loader.load())

    assert second[0] is first[0] and second[1] is first[1]
    assert second[2].document is not None and second[2].document.text == "Flaky text.\n"
    assert second_run.touched(present, absent) == []
    assert fake_http.urls() == [flaky] * 3
    assert loader.documents() == (first[0].document, None, second[2].document)
