"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_context.py

PURPOSE: Proves how the InfiniteMemory agent keeps a long run inside a small context: old tool exchanges are trimmed past INFINITE_HISTORY_MAX_TOKENS while the task (the prompt) and the map (the system string) reach every call, and each run on the same agent object starts from a clean context.
ROLE IN CODEBASE: Context layer of tests/features/infinite_memory_agent/ (spec AC-33, AC-40; INV-23, INV-39; D-28; EC-50). Exercises the trimming middleware wiring in vidbyte/agents/infinite/agent.py and the per-run context reset in vidbyte/agents/infinite/runtime.py.
ARCHITECTURE NOTE: The history cap is lowered by patching the name INFINITE_HISTORY_MAX_TOKENS in vidbyte.agents.infinite.agent before the agent is built, as spec section 13 directs. Tool results of equal size make the trimmed groups predictable: the middleware keeps whole groups from newest to oldest while they fit.
FUNCTION INVENTORY: test_root_history_is_trimmed_past_the_cap_while_task_and_map_survive (AC-33, INV-23, D-28); test_a_second_run_on_the_same_agent_starts_from_a_clean_context (AC-40, INV-39, EC-50).
COMMON MODIFICATION PATTERNS: If the cap moves to a different module, patch it where the spec's section 13 says the agent reads it.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not patch the constant in vidbyte.lib.constants.infinite; the agent module imports it by name, so only the agent module's binding counts.
KNOWN EDGE CASES: Each fetch_page result is about 100 tokens, so with a cap of 250 at most the two newest groups fit; the test only asserts the oldest is gone and the newest is present.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-agent/spec.md sections 6.1, 6.2, 8.1 (D-28) and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_context.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    MAP_HEADER,
    ROOT,
    TASK,
    ScriptedTree,
    build_agent,
    events,
    journal_records,
    reply,
    tool_call,
    workspace_root,
)
from vidbyte import tool

PAGE_BODY = "p" * 400


@tool(name="fetch_page")
def fetch_page(number: int) -> str:
    """Fetch one page of a long competitor price list."""
    return f"PAGE-{number}-{PAGE_BODY}"


def test_root_history_is_trimmed_past_the_cap_while_task_and_map_survive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-33, INV-23, D-28: with the cap patched to 250 tokens, later calls lose the oldest page but keep the newest, the task, and the map; the run finishes."""
    monkeypatch.setattr("vidbyte.agents.infinite.agent.INFINITE_HISTORY_MAX_TOKENS", 250)
    agent = build_agent(tmp_path, tools=(fetch_page,))
    tree = ScriptedTree({ROOT: [*(tool_call("fetch_page", {"number": number}) for number in range(1, 5)), reply("All four pages read.")]})
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    assert answer.content == "All four pages read."
    calls = tree.calls_by(ROOT)
    assert len(calls) == 5
    for call in calls:
        assert call.prompt == TASK, "the task must be re-sent as the prompt on every call"
        assert MAP_HEADER in call.system, "the map must be in every system string"
    last_history = json.dumps(calls[-1].messages)
    assert "PAGE-4-" in last_history, "the newest tool group must survive trimming"
    assert "PAGE-1-" not in last_history, "the oldest tool group must be trimmed once the history passes the cap"
    assert events(journal_records(workspace_root(tmp_path)))[-1] == "run_finished"


def test_a_second_run_on_the_same_agent_starts_from_a_clean_context(tmp_path: Path) -> None:
    """AC-40, INV-39, EC-50: the second run's first call carries no Tool calls or History section and nothing from the first run."""
    agent = build_agent(tmp_path)
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("grep", {"pattern": "FIRST-RUN-GREP-PATTERN"}),
                reply("FIRST-RUN-REPLY: Acme is 49 USD."),
                reply("SECOND-RUN-REPLY"),
            ]
        }
    )
    with tree.install():
        agent.run("FIRST-RUN-TASK: list Acme's prices.")
        agent.run("SECOND-RUN-TASK: list Globex's prices.")
    tree.assert_complete()
    second_start = tree.calls_by(ROOT)[2]
    assert second_start.prompt == "SECOND-RUN-TASK: list Globex's prices."
    assert "Tool calls:" not in second_start.system and "History:" not in second_start.system
    carried = second_start.system + json.dumps(second_start.messages)
    for marker in ("FIRST-RUN-TASK", "FIRST-RUN-REPLY", "FIRST-RUN-GREP-PATTERN"):
        assert marker not in carried, f"{marker} leaked from the first run into the second"
