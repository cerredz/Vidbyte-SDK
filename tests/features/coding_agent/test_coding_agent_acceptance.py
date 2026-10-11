"""FILE: tests/features/coding_agent/test_coding_agent_acceptance.py

PURPOSE: Prove the caller-visible promise of CodingAgent end to end: one constructor gives a model seven tools that actually run under one root folder, a caller policy still wins, and a keyed WebFetch lets the model read what it fetched.
ROLE IN CODEBASE: Drives vidbyte.CodingAgent through BaseAgent's real tool loop (AgentRuntime permission checks, ToolsFormatter, usage tracking) with an offline scripted model from conftest.py and real bash subprocesses.
ARCHITECTURE NOTE: Only the model runner and the provider HTTP send are replaced; the file tools, the bash process, the permission policy, and the usage ledger are real. Bash commands are portable between Linux bash and Git for Windows bash.
FUNCTION INVENTORY: test_spec_snippet_* runs spec §4 as written (AC-1); test_default_policy_* (AC-2); test_caller_read_only_policy_* (AC-3); test_keyed_fetch_* (AC-7); test_missing_bash_* (AC-17).
COMMON MODIFICATION PATTERNS: Script one more tool call per scenario and assert on tool_call_states, files under root_dir, and the model-visible tool messages, never on private agent state.
WHAT NOT TO DO IN THIS FILE: 1. Do not mock BaseAgent, AgentRuntime, or the permission policy; they are the seams under test. 2. Do not use a real API key or open a socket; conftest.py fakes the HTTP send.
KNOWN EDGE CASES: tool_call_states includes the final isDone call; a denied call never reaches the tool, so a denied bash leaves no file behind; Windows needs Git for Windows for every bash call here except the missing-bash case.
RELATED DOCS: tests/features/coding_agent/FEATURE.md; docs/spec/coding-agent/spec.md (§4, §6.2 AC-1, AC-2, AC-3, AC-7, AC-17)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_acceptance.py
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from tests.agent_test_support import bind_test_runner, build_test_agent
from vidbyte.agents.base import BaseAgent
from vidbyte.tools.builtins.operations.clients import FirecrawlClient
from vidbyte.tools.builtins.operations.fetch import FirecrawlFetchTool
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolPermission

SPEC_SNIPPET_TOOL_NAMES = ("bash", "read_lines", "write_text", "replace_text", "glob", "grep", "firecrawl_fetch")

# Two documentation pages a Firecrawl scrape returns; each final URL differs from the requested one (a redirect).
FIRECRAWL_PAGES = {
    "https://docs.example.com/install": ("https://docs.example.com/v2/install", "# Install\n\nRun the installer, then restart the shell.\n" + "Install step detail.\n" * 30),
    "https://docs.example.com/usage": ("https://docs.example.com/v2/usage", "# Usage\n\nCreate the agent and call run().\n" + "Usage step detail.\n" * 30),
}


def _firecrawl_scrape(send: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]:
    # Answers one Firecrawl scrape request with the page registered for its URL.
    final_url, markdown = FIRECRAWL_PAGES[send["json_body"]["url"]]
    return 200, {"data": {"markdown": markdown, "metadata": {"sourceURL": final_url}}}


def _billed(agent: BaseAgent) -> list[tuple[object, ...]]:
    # The billable view of the last run: what was charged, to whom, how, and for how much.
    return [(record.operation, record.provider, record.mode, record.units, record.cost_usd) for record in agent.get_usage().operations]


def test_spec_snippet_builds_seven_tools_over_an_absolute_root_and_runs_through_the_loop(coding_agent_cls, script_model, tmp_path, monkeypatch) -> None:
    # AC-1: spec §4 run as written, from the folder that contains my-project, with an offline runner bound for run().
    monkeypatch.chdir(tmp_path)
    (tmp_path / "my-project").mkdir()
    CodingAgent = coding_agent_cls

    agent = CodingAgent(
        name="coder",
        system_prompt="You are a careful software engineer. Make the smallest change that fixes the task.",
        root_dir="my-project",
        firecrawl_api_key="fc-your-key",
        provider="openai",
        model_name="gpt-4.1",
    )

    assert agent.root_dir == (tmp_path / "my-project").resolve()
    assert agent.root_dir.is_absolute()
    assert agent.tools.names() == SPEC_SNIPPET_TOOL_NAMES

    runner = script_model([("bash", {"command": "echo snippet-ran"})], final_answer="Fixed the first failure.")
    bind_test_runner(agent, runner)
    reply = agent.run("Run the tests with python -m pytest -q and fix the first failure.")

    assert reply.content == "Fixed the first failure."
    assert reply.metadata["tool_call_states"] == ("succeeded", "succeeded")
    [(tool_name, seen)] = runner.tool_messages()
    assert tool_name == "bash"
    assert seen.splitlines()[0] == "snippet-ran"
    assert seen.splitlines()[-1] == "exit code: 0"


@pytest.mark.asyncio
async def test_default_policy_lets_the_model_write_edit_and_run_bash_under_root(coding_agent_cls, script_model, tmp_path) -> None:
    # AC-2 / INV-7: with no caller policy, WRITE and EXECUTE calls run (a plain BaseAgent would deny all three).
    runner = script_model(
        [
            ("write_text", {"path": "notes.txt", "content": "alpha beta"}),
            ("replace_text", {"path": "notes.txt", "search": "beta", "replacement": "gamma"}),
            ("bash", {"command": "cat notes.txt"}),
        ],
        final_answer="edited",
    )
    agent = build_test_agent(name="coder", system_prompt="Edit files.", root_dir=tmp_path, runner=runner, agent_type=coding_agent_cls)

    reply = await agent.arun("Change beta to gamma in notes.txt and show the file.")

    assert reply.metadata["tool_call_states"] == ("succeeded", "succeeded", "succeeded", "succeeded")
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "alpha gamma"
    bash_name, bash_seen = runner.tool_messages()[2]
    assert bash_name == "bash"
    assert bash_seen.splitlines()[0] == "alpha gamma"
    assert agent.permission_policy.allowed == frozenset(ToolPermission)


@pytest.mark.asyncio
async def test_caller_read_only_policy_denies_bash_and_write_without_side_effects(coding_agent_cls, script_model, tmp_path) -> None:
    # AC-3 / INV-7: the caller's exact policy object wins; denied calls spawn nothing, write nothing, and the run goes on.
    policy = PermissionPolicy()
    runner = script_model(
        [
            ("bash", {"command": "echo spawned > spawned.txt"}),
            ("write_text", {"path": "denied.txt", "content": "should not exist"}),
        ],
        final_answer="stayed read-only",
    )
    agent = build_test_agent(name="coder", system_prompt="Inspect only.", root_dir=tmp_path, permission_policy=policy, runner=runner, agent_type=coding_agent_cls)

    reply = await agent.arun("Try to change something.")

    assert agent.permission_policy is policy
    assert reply.metadata["tool_call_states"] == ("denied", "denied", "succeeded")
    assert reply.content == "stayed read-only"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_keyed_fetch_shows_every_page_to_the_model_and_bills_like_the_bare_tool(coding_agent_cls, script_model, fake_provider_http, tmp_path) -> None:
    # AC-7 / INV-16 / INV-20: same Firecrawl scrape through a CodingAgent and through a plain agent holding the bare tool.
    fake_provider_http(_firecrawl_scrape)
    fetch_call = ("firecrawl_fetch", {"urls": list(FIRECRAWL_PAGES)})
    coding_runner = script_model([fetch_call], final_answer="read both pages")
    bare_runner = script_model([fetch_call], final_answer="read both pages")
    coding = build_test_agent(name="coder", system_prompt="Read the docs.", root_dir=tmp_path, firecrawl_api_key="fc-test-key", runner=coding_runner, agent_type=coding_agent_cls)
    bare = build_test_agent(name="reader", system_prompt="Read the docs.", tools=[FirecrawlFetchTool(client=FirecrawlClient("fc-test-key"))], runner=bare_runner)

    await coding.arun("Read the install and usage pages.")
    await bare.arun("Read the install and usage pages.")

    [(_, coding_seen)] = coding_runner.tool_messages()
    [(_, bare_seen)] = bare_runner.tool_messages()
    # The provider summary comes first and is unchanged; the bare tool still shows nothing but that summary.
    assert coding_seen.startswith(bare_seen)
    assert all(markdown not in bare_seen for _, markdown in FIRECRAWL_PAGES.values())
    # After the summary, each page's final URL is followed by its full markdown, in payload order.
    pages_part = coding_seen[len(bare_seen):]
    positions = [pages_part.find(text) for page in FIRECRAWL_PAGES.values() for text in page]
    assert -1 not in positions
    assert positions == sorted(positions)
    # The view changes nothing about billing: same operation, provider, mode, units, and cost.
    assert _billed(coding) == _billed(bare)
    assert [row[:2] for row in _billed(coding)] == [("fetch", "firecrawl")]


@pytest.mark.asyncio
async def test_missing_bash_fails_only_the_bash_call_and_the_other_tools_keep_working(coding_agent_cls, script_model, tmp_path, monkeypatch) -> None:
    # AC-17: no usable bash (POSIX: none on PATH; Windows: no git on PATH) is one failed call, not a broken agent.
    empty_path = tmp_path / "empty-path"
    root = tmp_path / "root"
    empty_path.mkdir()
    root.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    # Windows also searches the current folder before PATH; make that folder empty too.
    monkeypatch.chdir(empty_path)
    runner = script_model(
        [
            ("bash", {"command": "echo hi > from-bash.txt"}),
            ("write_text", {"path": "kept.txt", "content": "still works"}),
            ("grep", {"pattern": "still works"}),
        ],
        final_answer="worked around the missing shell",
    )
    agent = build_test_agent(name="coder", system_prompt="Work.", root_dir=root, runner=runner, agent_type=coding_agent_cls)

    reply = await agent.arun("Record a note.")

    assert reply.metadata["tool_call_states"] == ("failed", "succeeded", "succeeded", "succeeded")
    assert reply.content == "worked around the missing shell"
    assert (root / "kept.txt").read_text(encoding="utf-8") == "still works"
    assert not (root / "from-bash.txt").exists()
    assert "kept.txt" in runner.tool_messages()[2][1]
