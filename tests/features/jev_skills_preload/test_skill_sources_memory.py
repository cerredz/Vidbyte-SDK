"""FILE: tests/features/jev_skills_preload/test_skill_sources_memory.py

PURPOSE: Pin SkillLoader's memory and coordination: successes and permanent failures are remembered for the agent's lifetime and cost nothing afterwards, transient failures are retried on the next run, overlapping loads agree on the first remembered resolution, a crash or cancellation remembers nothing, each agent has its own memory, every group resolves concurrently, entries sharing GitHub lookups are grouped, and documents() always matches the last load.
ROLE IN CODEBASE: Covers spec AC-10, AC-15, AC-27, INV-5 to INV-10, NFR-2, D-5, D-22, D-24 and EC-94 to EC-98, EC-100, EC-101 for vidbyte/agents/skills/loader.py and its wiring through vidbyte/agents/jev/alignment/skills.py.
ARCHITECTURE NOTE: The loader's memory is a real seam and is never patched; ordering between overlapping work is forced with asyncio events inside the transport fake, never with sleeps. Only one test replaces GitHubSkillResolver.resolve, which spec section 13 names as the seam for isolating the loader's grouping.
FUNCTION INVENTORY: test_remembered_entries_cost_nothing_and_transient_ones_retry; test_overlapping_loads_agree_on_the_first_remembered_resolution; test_a_crash_while_loading_propagates_and_remembers_nothing; test_cancellation_while_loading_propagates_and_remembers_nothing; test_each_agent_has_its_own_memory; test_every_group_resolves_at_the_same_time; test_entries_sharing_lookups_are_grouped_and_results_keep_settings_order; test_documents_match_the_last_load_and_caller_documents_are_pre_remembered.
COMMON MODIFICATION PATTERNS: A new memory rule adds a run to the AC-10 sequence; a new grouping rule adds entries to the grouping test.
WHAT NOT TO DO IN THIS FILE: 1. Do not sleep to order concurrent work; use events and the conftest spin_loop. 2. Do not reach into the loader's private memory; observe it through requests, file reads, and documents().
KNOWN EDGE CASES: The rendezvous test patches the step deadline to one second, so an implementation that resolves groups one after another fails fast instead of hanging. A crash in one group must leave even its successful siblings unremembered, because memory is written only after every group returns. BaseAgent.arun re-raises every non-cancellation exception as AgentExecutionError chained from the original, so the crash test checks the original error as the direct cause at the agent boundary and unchanged at the preload boundary.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 5, 6.1 loading and memory, 8.1 D-22 and D-24, 9.1 loader memory)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_memory.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.skills import SkillDocument
from vidbyte.lib.errors import AgentExecutionError

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.agents.skills import fetch as fetch_module
    from vidbyte.agents.skills.github import GitHubSkillResolver
    from vidbyte.agents.skills.loader import SkillLoader

    from vidbyte import (
        AnthropicSkill,
        GitHubSkill,
        InlineSkill,
        JevSkillStatus,
        LocalSkill,
        SkillUnavailableReason,
    )
    from vidbyte.lib.dataclasses.skills import SkillResolution
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

API = "https://api.github.com"
ANTHROPIC = "https://api.anthropic.com/v1"
SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def raw_url(repo: str, folder: str) -> str:
    return f"{API}/repos/{repo}/contents/{folder}/SKILL.md?ref={SHA}"


def skill_file(name: str, body: str | None = None) -> bytes:
    return f"---\nname: {name}\ndescription: The {name} skill.\n---\n{body or f'Body of {name}.'}\n".encode()


def pinned(name: str, repo: str = "acme/skills", token: str | None = None) -> Any:
    # A GitHub entry pinned to a full SHA with an explicit folder, so it costs exactly one raw request.
    return GitHubSkill(name=name, repo=repo, ref=SHA, path=f"skills/{name}", token=token)


async def _until(condition: Callable[[], bool], spin_loop: Callable[..., Any]) -> None:
    # Yields to the event loop until a condition holds, failing instead of hanging if it never does.
    for _ in range(500):
        if condition():
            return
        await spin_loop(1)
    raise AssertionError("condition never became true")


@pytest.mark.asyncio
async def test_remembered_entries_cost_nothing_and_transient_ones_retry(tmp_path: Path, fake_http: Any, write_skill: Callable[..., Path], make_agent: Callable[..., Any], jev: Callable[..., Any], record_io: Callable[[], Any]) -> None:
    # AC-10, INV-5, NFR-2, EC-98: run 2 asks only for the flaky entry, run 3 asks for nothing and reads no file.
    fake_http.answer(raw_url("acme/skills", "skills/ok"), fake_http.reply(200, skill_file("ok")))
    fake_http.answer(f"{ANTHROPIC}/skills/skill_gone/versions/1/content", fake_http.reply(404, "gone"))
    fake_http.answer(raw_url("acme/flaky", "skills/flaky"), fake_http.reply(503, "busy"), fake_http.reply(503, "busy"), fake_http.reply(200, skill_file("flaky")))
    folder = write_skill(tmp_path / "skills" / "local-one", body="Local body.\n")
    jev(default=0.9)
    agent, runner = make_agent([pinned("ok"), AnthropicSkill(name="gone", skill_id="skill_gone", version="1", api_key="sk-ant-FAKE-KEY"), pinned("flaky", repo="acme/flaky"), LocalSkill(name="local-one", path=folder)])

    await agent.arun("Run one.")
    assert [(result.status, result.reason) for result in agent.response.skills.results] == [
        (JevSkillStatus.SELECTED, None),
        (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.NOT_FOUND),
        (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.FETCH_FAILED),
        (JevSkillStatus.SELECTED, None),
    ]
    run_one = len(fake_http.sent)
    assert fake_http.count(raw_url("acme/flaky", "skills/flaky")) == 2
    # The local file disappears; a remembered skill never reads it again.
    (folder / "SKILL.md").unlink()

    with record_io() as io_record:
        await agent.arun("Run two.")
        assert fake_http.urls()[run_one:] == [raw_url("acme/flaky", "skills/flaky")]
        assert [result.status for result in agent.response.skills.results] == [JevSkillStatus.SELECTED, JevSkillStatus.UNAVAILABLE, JevSkillStatus.SELECTED, JevSkillStatus.SELECTED]
        run_two = len(fake_http.sent)
        await agent.arun("Run three.")
    assert len(fake_http.sent) == run_two
    assert io_record.touched(folder) == []
    assert [result.reason for result in agent.response.skills.results] == [None, SkillUnavailableReason.NOT_FOUND, None, None]
    assert "Local body.\n" in runner.systems[2]


@pytest.mark.asyncio
async def test_overlapping_loads_agree_on_the_first_remembered_resolution(fake_http: Any, spin_loop: Callable[..., Any]) -> None:
    # AC-27, INV-10, EC-95, D-24: a late load must neither replace the remembered resolution nor disagree with documents().
    release = asyncio.Event()

    async def late_answer() -> Any:
        await release.wait()
        return fake_http.reply(200, skill_file("pdf", "Late text."))

    fake_http.answer(raw_url("acme/skills", "skills/pdf"), late_answer, fake_http.reply(200, skill_file("pdf", "Early text.")))
    loader = SkillLoader((pinned("pdf"),))
    slow, fast = asyncio.create_task(loader.load()), asyncio.create_task(loader.load())
    await _until(lambda: slow.done() or fast.done(), spin_loop)
    release.set()
    first, second = await asyncio.wait_for(asyncio.gather(slow, fast), timeout=5)
    assert first[0].document.text == second[0].document.text == "Early text.\n"
    assert loader.documents()[0] is second[0].document
    assert loader.documents()[0] is first[0].document
    assert fake_http.count(raw_url("acme/skills", "skills/pdf")) == 2


@pytest.mark.parametrize("error", [RuntimeError("resolver bug"), TypeError("resolver bug")], ids=["RuntimeError", "TypeError"])
@pytest.mark.asyncio
async def test_a_crash_while_loading_propagates_and_remembers_nothing(fake_http: Any, make_agent: Callable[..., Any], jev: Callable[..., Any], error: Exception) -> None:
    # AC-15, INV-9, EC-97: a programming error is never hidden as an unavailable skill, and the healthy sibling is not remembered either.
    fake_http.answer(raw_url("acme/skills", "skills/pdf"), error)
    jev(default=0.9)
    agent, runner = make_agent([pinned("pdf"), InlineSkill(name="house-review", description="Checklist.", text="Read the tests first.")])
    # BaseAgent.arun (unchanged by this feature) re-raises any non-cancellation exception as AgentExecutionError
    # chained from the original, so the original object must be the direct cause, never an UNAVAILABLE result.
    with pytest.raises(AgentExecutionError) as raised:
        await agent.arun("Run one.")
    assert raised.value.__cause__ is error
    assert agent.skill_preload.loader.documents() == (None, None)
    assert runner.systems == []
    # At the preload boundary this feature owns, the error passes through unchanged.
    with pytest.raises(type(error), match="resolver bug"):
        await agent.skill_preload.run("Run one again.", BaseAgentContext(system_prompt="Base."))
    assert agent.skill_preload.loader.documents() == (None, None)
    fake_http.answer(raw_url("acme/skills", "skills/pdf"), fake_http.reply(200, skill_file("pdf")))
    await agent.arun("Run two.")
    assert [result.status for result in agent.response.skills.results] == [JevSkillStatus.SELECTED, JevSkillStatus.SELECTED]
    assert fake_http.count(raw_url("acme/skills", "skills/pdf")) == 3


@pytest.mark.asyncio
async def test_cancellation_while_loading_propagates_and_remembers_nothing(fake_http: Any, make_agent: Callable[..., Any], jev: Callable[..., Any], spin_loop: Callable[..., Any]) -> None:
    # AC-15, EC-96: cancelling the run mid-load leaves the agent as if the load never started.
    fake_http.answer(raw_url("acme/skills", "skills/pdf"), fake_http.HANG)
    jev(default=0.9)
    agent, _ = make_agent([pinned("pdf"), InlineSkill(name="house-review", description="Checklist.", text="Read the tests first.")])
    run = asyncio.create_task(agent.arun("Run one."))
    await _until(lambda: fake_http.count(raw_url("acme/skills", "skills/pdf")) == 1, spin_loop)
    await spin_loop()
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert agent.skill_preload.loader.documents() == (None, None)
    fake_http.answer(raw_url("acme/skills", "skills/pdf"), fake_http.reply(200, skill_file("pdf")))
    await agent.arun("Run two.")
    assert [result.status for result in agent.response.skills.results] == [JevSkillStatus.SELECTED, JevSkillStatus.SELECTED]


@pytest.mark.asyncio
async def test_each_agent_has_its_own_memory(fake_http: Any, make_agent: Callable[..., Any], jev: Callable[..., Any]) -> None:
    # INV-6, EC-101, T-4: no process-wide cache, so an identical entry on a second agent is fetched again, and each key goes only with its own agent.
    content = f"{ANTHROPIC}/skills/skill_x/versions/1/content"
    fake_http.answer(content, fake_http.reply(200, skill_file("notes")))
    fake_http.answer(raw_url("acme/skills", "skills/pdf"), fake_http.reply(200, skill_file("pdf")))
    jev(default=0.9)
    first, _ = make_agent([pinned("pdf"), AnthropicSkill(name="notes", skill_id="skill_x", version="1", api_key="sk-ant-FAKE-TENANT-A")])
    second, _ = make_agent([pinned("pdf"), AnthropicSkill(name="notes", skill_id="skill_x", version="1", api_key="sk-ant-FAKE-TENANT-B")])
    await first.arun("Tenant A.")
    await second.arun("Tenant B.")
    await first.arun("Tenant A again.")
    assert fake_http.count(raw_url("acme/skills", "skills/pdf")) == 2
    assert [request.headers["x-api-key"] for request in fake_http.sent if request.url == content] == ["sk-ant-FAKE-TENANT-A", "sk-ant-FAKE-TENANT-B"]
    assert first.skill_preload.loader is not second.skill_preload.loader


@pytest.mark.asyncio
async def test_every_group_resolves_at_the_same_time(monkeypatch: pytest.MonkeyPatch, fake_http: Any) -> None:
    # INV-7, EC-74: no answer arrives until all four requests are in flight, so resolving groups or raw files one by one would hit the deadline.
    monkeypatch.setattr(fetch_module, "SKILL_FETCH_DEADLINE_SECONDS", 1.0)
    everyone_waiting = asyncio.Event()
    arrived: list[str] = []
    urls = {"pdf": raw_url("acme/skills", "skills/pdf"), "docx": raw_url("acme/skills", "skills/docx"), "other": raw_url("acme/other", "skills/other"), "notes": f"{ANTHROPIC}/skills/skill_x/versions/1/content"}

    def rendezvous(name: str) -> Callable[[], Any]:
        async def answer() -> Any:
            arrived.append(name)
            if len(arrived) == len(urls):
                everyone_waiting.set()
            await everyone_waiting.wait()
            return fake_http.reply(200, skill_file(name))

        return answer

    for name, url in urls.items():
        fake_http.answer(url, rendezvous(name))
    entries = (pinned("pdf"), pinned("docx"), pinned("other", repo="acme/other"), AnthropicSkill(name="notes", skill_id="skill_x", version="1", api_key="sk-ant-FAKE-KEY"))
    resolutions = await asyncio.wait_for(SkillLoader(entries).load(), timeout=5)
    assert [resolution.reason for resolution in resolutions] == [None] * 4
    assert sorted(arrived) == sorted(urls)


@pytest.mark.asyncio
async def test_entries_sharing_lookups_are_grouped_and_results_keep_settings_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # D-22, D-18, INV-7: one resolve call per (repo, ref, token); each call gets its entries in settings order; results come back in settings order.
    calls: list[tuple[str, ...]] = []

    async def recording_resolve(self: Any, entries: Any) -> tuple[Any, ...]:
        calls.append(tuple(entry.name for entry in entries))
        return tuple(SkillResolution(document=SkillDocument(name=entry.name, description="Grouped.", text=f"Text of {entry.name}.", source="github:test")) for entry in entries)

    monkeypatch.setattr(GitHubSkillResolver, "resolve", recording_resolve)
    folder = write_skill(tmp_path / "skills" / "local-one")
    entries = (
        GitHubSkill(name="a", repo="acme/skills", ref="v1"),
        LocalSkill(name="local-one", path=folder),
        GitHubSkill(name="b", repo="acme/skills", ref="v1", path="skills/b"),
        GitHubSkill(name="c", repo="acme/skills", ref="v1", token="ghp_FAKE"),
        GitHubSkill(name="d", repo="acme/skills", ref="v2"),
        GitHubSkill(name="e", repo="acme/other", ref="v1"),
        GitHubSkill(name="f", repo="acme/skills", ref="v1"),
    )
    resolutions = await SkillLoader(entries).load()
    assert sorted(calls) == sorted([("a", "b", "f"), ("c",), ("d",), ("e",)])
    assert [resolution.document.name for resolution in resolutions] == ["a", "local-one", "b", "c", "d", "e", "f"]


@pytest.mark.asyncio
async def test_documents_match_the_last_load_and_caller_documents_are_pre_remembered(tmp_path: Path, record_io: Callable[[], Any]) -> None:
    # INV-10, D-4, D-8: a caller's SkillDocument needs no load, so _build_batches can batch it before any run.
    caller = SkillDocument(name="caller-doc", description="Caller supplied.", text="Caller text.", source=None)
    loader = SkillLoader((caller, InlineSkill(name="house-review", description="Checklist.", text="  Read the tests first.\n"), LocalSkill(name="missing", path=tmp_path / "absent")))
    assert loader.documents() == (caller, None, None)
    resolutions = await loader.load()
    assert resolutions[0].document is caller
    assert loader.documents() == tuple(resolution.document for resolution in resolutions)
    assert loader.documents()[1].text == "  Read the tests first.\n"
    assert resolutions[2].reason is SkillUnavailableReason.NOT_FOUND
