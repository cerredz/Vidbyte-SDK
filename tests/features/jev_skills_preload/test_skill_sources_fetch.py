"""FILE: tests/features/jev_skills_preload/test_skill_sources_fetch.py

PURPOSE: Pin the shared HTTP step: every request uses the fixed timeout, one retry after the fixed backoff, a size cap, and no redirects; transport failures and the whole-step deadline become explained, unremembered resolutions; an HTTP answer of any status is handed back; and a source that keeps failing costs each run at most one retried pair per step.
ROLE IN CODEBASE: Covers spec AC-20, AC-24, INV-19, NFR-1, D-9, D-27 and EC-66, EC-82, EC-103, EC-116 for vidbyte/agents/skills/fetch.py (SkillFetch.get) and the constants in vidbyte/lib/constants/skills.py, through both SkillFetch directly and full loads.
ARCHITECTURE NOTE: The real HttpTransport.request runs, with only _send_once and its backoff sleep replaced by the conftest fake; the deadline is shortened by patching the module global the spec names, so no test waits for real time beyond a fraction of a second.
FUNCTION INVENTORY: test_fetch_bounds_are_the_documented_values; test_every_step_sends_the_fixed_settings_and_its_cap; test_retry_waits_the_backoff_once; test_any_http_answer_is_handed_back; test_transport_failures_become_explained_resolutions; test_step_that_never_finishes_ends_at_the_deadline; test_a_timeout_that_is_not_the_deadline_propagates; test_a_source_that_keeps_failing_costs_each_run_one_retried_pair.
COMMON MODIFICATION PATTERNS: A new fetch step adds a row to the step-settings test; a new transport failure shape adds a row to the failure table.
WHAT NOT TO DO IN THIS FILE: 1. Do not sleep for real; the deadline is patched to 0.05 seconds and wrapped in an outer guard. 2. Do not patch SkillFetch itself; it is the unit under test.
KNOWN EDGE CASES: The transport retries only on status codes, never on a connection error or a timeout. A TimeoutError counts as the deadline only when the step's own deadline expired, so any other TimeoutError is a programming error and propagates.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 8.1 D-9 and D-27, 9.2 outbound requests and failure mapping, 9.3, 13 transport facts)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_fetch.py
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest

from vidbyte.lib.errors import ProviderRequestError

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.agents.skills import fetch as fetch_module
    from vidbyte.agents.skills.fetch import SkillFetch
    from vidbyte.agents.skills.loader import SkillLoader

    from vidbyte import (
        AnthropicSkill,
        GitHubSkill,
        InlineSkill,
        JevSkillStatus,
        LocalSkill,
        SkillUnavailableReason,
    )
    from vidbyte.lib.constants import skills as skill_constants
    from vidbyte.lib.dataclasses.skills import SkillResolution
    from vidbyte.lib.enums import SkillFetchStep
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

API = "https://api.github.com"
REPO = "anthropics/skills"
SHA = "0123456789abcdef0123456789abcdef01234567"
ANTHROPIC = "https://api.anthropic.com/v1"
COMMIT = f"{API}/repos/{REPO}/commits/HEAD"
TREE = f"{API}/repos/{REPO}/git/trees/{SHA}?recursive=1"
RAW = f"{API}/repos/{REPO}/contents/skills/pdf/SKILL.md?ref={SHA}"
CONTENT_LATEST = f"{ANTHROPIC}/skills/skill_x/versions/latest/content"
METADATA = f"{ANTHROPIC}/skills/skill_x"
CONTENT_7 = f"{ANTHROPIC}/skills/skill_x/versions/7/content"
SKILL = b"---\nname: pdf\ndescription: Reads PDFs.\n---\nBody.\n"


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _names_number(detail: str, number: int) -> bool:
    return str(number) in detail.replace(",", "").replace("_", "")


def test_fetch_bounds_are_the_documented_values() -> None:
    # NFR-1, NFR-4, section 9.3: the deadline must exceed one retried pair of attempts plus the backoff (D-27).
    values = {name: getattr(skill_constants, name) for name in ("SKILL_MARKDOWN_MAX_BYTES", "SKILL_DOWNLOAD_MAX_BYTES", "SKILL_FETCH_TIMEOUT_SECONDS", "SKILL_FETCH_RETRY_COUNT", "SKILL_FETCH_BACKOFF_SECONDS", "SKILL_FETCH_DEADLINE_SECONDS")}
    assert values == {"SKILL_MARKDOWN_MAX_BYTES": 1_048_576, "SKILL_DOWNLOAD_MAX_BYTES": 33_554_432, "SKILL_FETCH_TIMEOUT_SECONDS": 10.0, "SKILL_FETCH_RETRY_COUNT": 1, "SKILL_FETCH_BACKOFF_SECONDS": 0.5, "SKILL_FETCH_DEADLINE_SECONDS": 25.0}
    assert skill_constants.SKILL_TRANSIENT_REASONS == frozenset({SkillUnavailableReason.RATE_LIMITED, SkillUnavailableReason.FETCH_FAILED})
    pair = (values["SKILL_FETCH_RETRY_COUNT"] + 1) * values["SKILL_FETCH_TIMEOUT_SECONDS"] + values["SKILL_FETCH_RETRY_COUNT"] * values["SKILL_FETCH_BACKOFF_SECONDS"]
    assert values["SKILL_FETCH_DEADLINE_SECONDS"] > pair


@pytest.mark.asyncio
async def test_every_step_sends_the_fixed_settings_and_its_cap(fake_http: Any) -> None:
    # INV-19, section 9.2: each of the five steps uses the same timeout and no redirects, with the cap of what it downloads.
    fake_http.answer(COMMIT, fake_http.reply(200, SHA))
    fake_http.answer(TREE, fake_http.reply(200, json.dumps({"sha": SHA, "tree": [{"path": "skills/pdf/SKILL.md", "type": "blob"}], "truncated": False})))
    fake_http.answer(RAW, fake_http.reply(200, SKILL))
    fake_http.answer(CONTENT_LATEST, fake_http.reply(404, "no"))
    fake_http.answer(METADATA, fake_http.reply(200, json.dumps({"latest_version": "7"})))
    fake_http.answer(CONTENT_7, fake_http.reply(200, SKILL))
    resolutions = await SkillLoader((GitHubSkill(name="pdf", repo=REPO), AnthropicSkill(name="notes", skill_id="skill_x", api_key="sk-ant-FAKE-KEY"))).load()
    assert all(resolution.document is not None for resolution in resolutions), resolutions
    caps = {request.url: request.max_response_bytes for request in fake_http.sent}
    download, markdown = skill_constants.SKILL_DOWNLOAD_MAX_BYTES, skill_constants.SKILL_MARKDOWN_MAX_BYTES
    assert caps == {COMMIT: download, TREE: download, RAW: markdown, CONTENT_LATEST: download, METADATA: download, CONTENT_7: download}
    assert {request.timeout_seconds for request in fake_http.sent} == {skill_constants.SKILL_FETCH_TIMEOUT_SECONDS}
    assert {request.follow_redirects for request in fake_http.sent} == {False}


@pytest.mark.asyncio
async def test_retry_waits_the_backoff_once(fake_http: Any) -> None:
    # NFR-1, D-9: one retry after SKILL_FETCH_BACKOFF_SECONDS for a retryable status, and no retry loop of the SDK's own.
    fake_http.answer(RAW, fake_http.reply(503, "busy"), fake_http.reply(200, SKILL))
    (resolution,) = await SkillLoader((GitHubSkill(name="pdf", repo=REPO, ref=SHA, path="skills/pdf"),)).load()
    assert resolution.document is not None
    assert fake_http.urls() == [RAW, RAW]
    assert fake_http.sleeps == [skill_constants.SKILL_FETCH_BACKOFF_SECONDS]


@pytest.mark.parametrize("status", [200, 301, 404, 418, 529])
@pytest.mark.asyncio
async def test_any_http_answer_is_handed_back(fake_http: Any, status: int) -> None:
    # Section 8.5: SkillFetch maps only failures where no usable answer arrived; statuses belong to each resolver.
    fake_http.answer(RAW, fake_http.reply(status, "body", {"Location": "https://example.invalid/"} if status == 301 else None))
    answer = await SkillFetch().get(url=RAW, headers={"accept": "application/vnd.github.raw"}, max_bytes=skill_constants.SKILL_MARKDOWN_MAX_BYTES, step=SkillFetchStep.GITHUB_FILE)
    assert not isinstance(answer, SkillResolution)
    assert answer.status_code == status
    assert answer.raw_bytes == b"body"


# (case, what the transport raises or answers, cap passed, expected reason, numbers the detail must name)
FAILURES = [
    ("connection error", "connection", "markdown", "FETCH_FAILED", ()),
    ("oversized error body", ProviderRequestError("Provider response exceeded the configured size ceiling.", provider="http", status_code=500), "markdown", "FETCH_FAILED", (500,)),
    ("oversized success body", ProviderRequestError("Provider response exceeded the configured size ceiling.", provider="http", status_code=200), "markdown", "TOO_LARGE", ("cap",)),
    ("download over its cap", "oversized-download", "download", "TOO_LARGE", ("cap",)),
]


@pytest.mark.parametrize(("case", "failure", "cap_name", "reason", "numbers"), FAILURES, ids=[row[0] for row in FAILURES])
@pytest.mark.asyncio
async def test_transport_failures_become_explained_resolutions(fake_http: Any, case: str, failure: Any, cap_name: str, reason: str, numbers: tuple[Any, ...]) -> None:
    # Section 9.2 transport rows, INV-18: the detail names the host and the step and never the transport's excerpt.
    cap = skill_constants.SKILL_MARKDOWN_MAX_BYTES if cap_name == "markdown" else skill_constants.SKILL_DOWNLOAD_MAX_BYTES
    if failure == "connection":
        failure = fake_http.connection_error()
    elif failure == "oversized-download":
        failure = fake_http.oversized(skill_constants.SKILL_DOWNLOAD_MAX_BYTES + 1)
    fake_http.answer(TREE, failure)
    answer = await SkillFetch().get(url=TREE, headers={"accept": "application/vnd.github+json"}, max_bytes=cap, step=SkillFetchStep.GITHUB_TREE)
    assert isinstance(answer, SkillResolution)
    assert answer.reason is SkillUnavailableReason[reason]
    assert answer.transient is (reason == "FETCH_FAILED")
    assert SkillFetchStep.GITHUB_TREE.value in answer.detail
    assert "getaddrinfo" not in answer.detail
    for number in numbers:
        assert _names_number(answer.detail, cap if number == "cap" else number), answer.detail
    if case == "connection error":
        assert "api.github.com" in answer.detail
    assert fake_http.count(TREE) == 1


@pytest.mark.asyncio
async def test_step_that_never_finishes_ends_at_the_deadline(monkeypatch: pytest.MonkeyPatch, fake_http: Any, write_skill: Callable[..., Any], tmp_path: Any) -> None:
    # AC-24, EC-103, D-27: a server that drips bytes forever is cut off per step, the run's other skills still load, and the next load tries again.
    monkeypatch.setattr(fetch_module, "SKILL_FETCH_DEADLINE_SECONDS", 0.05)
    fake_http.answer(COMMIT, fake_http.reply(200, SHA))
    fake_http.answer(TREE, fake_http.HANG)
    fake_http.answer(f"{ANTHROPIC}/skills/skill_slow/versions/1/content", fake_http.HANG)
    folder = write_skill(tmp_path / "skills" / "local-one")
    loader = SkillLoader((GitHubSkill(name="pdf", repo=REPO), AnthropicSkill(name="slow", skill_id="skill_slow", version="1", api_key="sk-ant-FAKE-KEY"), LocalSkill(name="local-one", path=folder)))
    github, vendor, local = await asyncio.wait_for(loader.load(), timeout=5)
    assert github.reason is SkillUnavailableReason.FETCH_FAILED and vendor.reason is SkillUnavailableReason.FETCH_FAILED
    assert "api.github.com" in github.detail and SkillFetchStep.GITHUB_TREE.value in github.detail and "path=" in github.detail
    assert "api.anthropic.com" in vendor.detail and SkillFetchStep.VENDOR_CONTENT.value in vendor.detail
    assert local.document is not None
    sent = len(fake_http.sent)
    await asyncio.wait_for(loader.load(), timeout=5)
    assert len(fake_http.sent) > sent


@pytest.mark.asyncio
async def test_a_timeout_that_is_not_the_deadline_propagates(fake_http: Any) -> None:
    # Section 9.2, INV-9: only the step's own expired deadline is an expected failure; anything else is a programming error.
    fake_http.answer(TREE, TimeoutError("raised by something other than the step deadline"))
    with pytest.raises(TimeoutError, match="something other"):
        await SkillFetch().get(url=TREE, headers={}, max_bytes=skill_constants.SKILL_DOWNLOAD_MAX_BYTES, step=SkillFetchStep.GITHUB_TREE)


@pytest.mark.asyncio
async def test_a_source_that_keeps_failing_costs_each_run_one_retried_pair(fake_http: Any, make_agent: Callable[..., Any], jev: Callable[..., Any]) -> None:
    # AC-20, EC-116, NFR-1: transient failures retry on every run, but never more than retry + 1 attempts per step, and the run goes on.
    fake_http.answer(f"{API}/repos/{REPO}/commits/v1", fake_http.reply(503, "down"))
    fake_http.answer(f"{ANTHROPIC}/skills/skill_x/versions/1/content", fake_http.reply(503, "down"))
    jev({"house-review": 0.9})
    agent, runner = make_agent([GitHubSkill(name="pdf", repo=REPO, ref="v1", path="skills/pdf"), AnthropicSkill(name="notes", skill_id="skill_x", version="1", api_key="sk-ant-FAKE-KEY"), InlineSkill(name="house-review", description="Our checklist.", text="Read the tests first.")])
    attempts = skill_constants.SKILL_FETCH_RETRY_COUNT + 1
    for run in range(1, 11):
        reply = await agent.arun(f"Review change {run}.")
        assert reply.content == "completed"
        assert [(result.status, result.reason) for result in agent.response.skills.results] == [
            (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.FETCH_FAILED),
            (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.FETCH_FAILED),
            (JevSkillStatus.SELECTED, None),
        ]
        assert fake_http.count(f"{API}/repos/{REPO}/commits/v1") == attempts * run
        assert fake_http.count(f"{ANTHROPIC}/skills/skill_x/versions/1/content") == attempts * run
    assert len(runner.systems) == 10
