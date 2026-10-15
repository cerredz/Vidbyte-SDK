"""FILE: tests/features/jev_skills_preload/test_skill_sources_acceptance.py

PURPOSE: Run the developer-facing contract end to end: the spec's section 4 snippet prints exactly its five documented lines, constructing an agent with all six entry types reads no file, sends no request, and reads no key variable, and a run stopped by the preflight gate or handed to a specialist contacts no skill source.
ROLE IN CODEBASE: Covers spec AC-1, AC-2, AC-18, INV-1, INV-4, INV-27, D-5 and EC-94 for the public names exported from vidbyte, JevAgent, and the lazy SkillLoader inside JevSkillsPreload.
ARCHITECTURE NOTE: The snippet is copied from the spec unchanged except for one added line that binds the offline main-model runner; GitHub is answered at the transport seam and Jev by the conftest's NamedJev. Construction is watched by the conftest's I/O recorder plus refusing socket and process stand-ins, and a run window afterwards proves the recorder would have seen the same reads.
FUNCTION INVENTORY: test_developer_snippet_prints_the_documented_lines; test_construction_reads_no_file_sends_no_request_and_reads_no_key; test_gate_stop_and_specialist_contact_no_skill_source.
COMMON MODIFICATION PATTERNS: If the section 4 snippet changes, copy it here again verbatim and update the expected lines.
WHAT NOT TO DO IN THIS FILE: 1. Do not edit the snippet to make it pass; it is the user-facing contract. 2. Do not let the construction window include a run.
KNOWN EDGE CASES: The selected and skipped lines depend on Jev, so NamedJev answers 0.9 for house-review and webapp-testing and 0.1 for sql-migrations, as AC-1 states; react-best-practices and release-notes must never reach Jev.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 4, 6.1 construction, 6.2 AC-1, AC-2, AC-18)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_acceptance.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from vidbyte.lib.dataclasses.agents import AgentMessage

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte import (
        AnthropicSkill,
        GitHubSkill,
        InlineSkill,
        JevAgent,
        JevAgentSettings,
        JevAlignmentSettings,
        JevRuntimeSettings,
        LocalSkill,
        OpenAISkill,
        SkillsShSkill,
    )
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

SHA = "0123456789abcdef0123456789abcdef01234567"
KEY_VARIABLES = {"GITHUB_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"}


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _refuse_sockets_and_processes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    # Records and refuses every way to open a connection or start a process, as the coding-agent web-fetch tests do.
    attempts: list[str] = []

    def refuse(what: str) -> Callable[..., Any]:
        def record(*args: Any, **kwargs: Any) -> Any:
            attempts.append(what)
            raise AssertionError(f"{what} must not run here (INV-1, INV-13)")

        return record

    for target, name in ((socket.socket, "connect"), (socket.socket, "connect_ex"), (socket, "create_connection"), (subprocess, "Popen"), (os, "system")):
        monkeypatch.setattr(target, name, refuse(name))
    return attempts


@pytest.mark.asyncio
async def test_developer_snippet_prints_the_documented_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str], fake_http: Any, write_skill: Callable[..., Path], jev: Callable[..., Any], bind_main_runner: Callable[..., Any]) -> None:
    # AC-1, FR-1: no .agents/skills folder and no ANTHROPIC_API_KEY, so two lines are unavailable with the documented reasons.
    write_skill(tmp_path / "skills" / "sql-migrations", name="sql-migrations", description="Plans SQL migrations.", body="Keep each step reversible.\n")
    fake_http.answer("https://api.github.com/repos/anthropics/skills/commits/v1.2.0", fake_http.reply(200, SHA))
    fake_http.answer(f"https://api.github.com/repos/anthropics/skills/git/trees/{SHA}?recursive=1", fake_http.reply(200, json.dumps({"sha": SHA, "tree": [{"path": "skills/webapp-testing/SKILL.md", "type": "blob"}], "truncated": False})))
    fake_http.answer(f"https://api.github.com/repos/anthropics/skills/contents/skills/webapp-testing/SKILL.md?ref={SHA}", fake_http.reply(200, b"---\nname: webapp-testing\ndescription: Tests web apps with Playwright.\n---\nStart the dev server first.\n"))
    jev({"house-review": 0.9, "webapp-testing": 0.9, "sql-migrations": 0.1})

    # --- spec section 4, verbatim except the marked line ---
    skills = (
        InlineSkill(name="house-review", description="Our PR review checklist.", text="Read every edited function and its tests first."),
        LocalSkill(name="sql-migrations", path="skills/sql-migrations"),                # reads skills/sql-migrations/SKILL.md
        SkillsShSkill(name="react-best-practices", source="vercel-labs/agent-skills"),  # the copy `npx skills add` installed
        GitHubSkill(name="webapp-testing", repo="anthropics/skills", ref="v1.2.0"),
        AnthropicSkill(name="release-notes", skill_id="skill_01AbCd"),                 # key from ANTHROPIC_API_KEY
    )
    agent = JevAgent(JevAgentSettings(name="dev-assistant", system_prompt="You help engineers review and ship code.",
        provider="openai", model_name="gpt-4.1-mini", alignment=JevAlignmentSettings(skills=skills)))  # reads and fetches nothing
    bind_main_runner(agent)  # added: the offline main-model runner

    reply = await agent.arun("Review PR 182 and check it doesn't break the public API.")
    for skill in agent.response.skills.results:
        print(skill.name, skill.status.value, skill.reason.value if skill.reason else "-")
    # --- end of snippet ---

    assert reply.content == "completed"
    assert capsys.readouterr().out.splitlines() == [
        "house-review selected -",
        "sql-migrations skipped -",
        "react-best-practices unavailable not_installed",
        "webapp-testing selected -",
        "release-notes unavailable auth_failed",
    ]
    details = {result.name: result.detail for result in agent.response.skills.results}
    assert "npx skills add vercel-labs/agent-skills --skill react-best-practices" in details["react-best-practices"]
    assert "ANTHROPIC_API_KEY" in details["release-notes"]


def _entries_pointing_nowhere(root: Path) -> tuple[Any, ...]:
    return (
        InlineSkill(name="inline-one", description="Inline.", text="Inline text."),
        LocalSkill(name="local-one", path=root / "missing" / "local-one"),
        LocalSkill(name="local-relative", path="missing/relative"),
        SkillsShSkill(name="sh-one", source="acme/skills"),
        SkillsShSkill(name="sh-two", source="acme/skills", directory=root / "missing" / "vendor"),
        GitHubSkill(name="gh-one", repo="acme/unreachable"),
        AnthropicSkill(name="anthropic-one", skill_id="skill_unreachable"),
        OpenAISkill(name="openai-one", skill_id="skill_unreachable"),
    )


@pytest.mark.asyncio
async def test_construction_reads_no_file_sends_no_request_and_reads_no_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_http: Any, record_io: Callable[[], Any], jev: Callable[..., Any], bind_main_runner: Callable[..., Any]) -> None:
    # AC-2, INV-1, D-5: everything that could touch a source waits for the first run that reaches the preload.
    attempts = _refuse_sockets_and_processes(monkeypatch)
    with record_io() as construction:
        entries = _entries_pointing_nowhere(tmp_path)
        settings = JevAgentSettings(name="lazy", system_prompt="Base.", provider="openai", model_name="gpt-4.1-mini", alignment=JevAlignmentSettings(skills=entries))
        agent = JevAgent(settings, JevRuntimeSettings(preflight=()))
    assert construction.touched(tmp_path) == []
    assert KEY_VARIABLES.isdisjoint(construction.env_keys)
    assert fake_http.sent == [] and attempts == []
    # Non-vacuity: the same recorder sees the reads once a run reaches the preload.
    fake_http.answer("https://api.github.com/repos/acme/unreachable/commits/HEAD", fake_http.connection_error())
    jev(default=0.9)
    bind_main_runner(agent)
    with record_io() as first_run:
        await agent.arun("Do the work.")
    assert first_run.touched(tmp_path) != []
    assert "GITHUB_TOKEN" in first_run.env_keys
    assert fake_http.urls() == ["https://api.github.com/repos/acme/unreachable/commits/HEAD"]


@pytest.mark.asyncio
async def test_gate_stop_and_specialist_contact_no_skill_source(fake_http: Any, make_agent: Callable[..., Any], jev: Callable[..., Any]) -> None:
    # AC-18, INV-4, INV-27, EC-94: loading happens only inside a run that reaches the preload.
    raw = f"https://api.github.com/repos/acme/skills/contents/skills/pdf/SKILL.md?ref={SHA}"
    fake_http.answer(raw, fake_http.reply(200, b"---\nname: pdf\ndescription: Reads PDFs.\n---\nBody.\n"))
    runner = jev(default=0.9)
    agent, main_model = make_agent([GitHubSkill(name="pdf", repo="acme/skills", ref=SHA, path="skills/pdf")])
    agent.preflight.pass_ = AsyncMock(return_value=False)
    stopped = await agent.arun("Unclear work.")
    assert stopped.metadata["strategy"] == "jev_preflight"
    assert (fake_http.sent, agent.response.skills.results) == ([], ())
    agent.preflight.pass_ = AsyncMock(return_value=True)
    agent.preflight.specialist = SimpleNamespace(agent=SimpleNamespace(arun=AsyncMock(return_value=AgentMessage(sender="expert", recipient="orchestrator", content="delegated"))))
    delegated = await agent.arun("Specialist work.")
    assert delegated.content == "delegated"
    assert (fake_http.sent, agent.response.skills.results, runner.requests, main_model.systems) == ([], (), [], [])
    # The first run that reaches the preload is the one that loads.
    agent.preflight.specialist = None
    await agent.arun("Normal work.")
    assert fake_http.urls() == [raw]
    assert [result.name for result in agent.response.skills.results] == ["pdf"]
