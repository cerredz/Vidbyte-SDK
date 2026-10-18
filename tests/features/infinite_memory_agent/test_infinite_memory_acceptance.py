"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_acceptance.py

PURPOSE: Proves the caller-visible story of the InfiniteMemory agent end to end: the spec's section 4 snippet runs as written and leaves the documented workspace, a pair's memories reach disk only after its verifier, every child's usage reaches the root's ledger once, and a second agent on the same workspace sees what the first one saved.
ROLE IN CODEBASE: Acceptance layer of tests/features/infinite_memory_agent/ (spec AC-1, AC-9, AC-24, AC-30; INV-15, INV-16, INV-21, INV-22, INV-25, INV-35; G-1..G-5). Start here when a caller reports a regression; the narrower modules pin each rule.
ARCHITECTURE NOTE: Only the model runner is scripted (ScriptedTree, installed at BaseAgent._runner_for_model); the workspace, journal, pipeline, prompt catalog, and filesystem are real and live under tmp_path.
FUNCTION INVENTORY: test_section_4_snippet_prints_the_root_answer_and_leaves_the_documented_workspace (AC-1); test_staged_entries_reach_disk_only_after_the_verifier_returns (AC-9, INV-15, INV-16); test_root_usage_includes_every_generator_and_verifier_exactly_once (AC-24, INV-35); test_a_second_agent_on_the_same_workspace_sees_the_first_agents_entry (AC-30, INV-22, D-6).
COMMON MODIFICATION PATTERNS: Keep the section 4 snippet byte-for-byte as the spec prints it; if the spec's snippet changes, paste the new one.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not edit the snippet to make it easier to test; chdir into tmp_path instead.
KNOWN EDGE CASES: The snippet assigns a variable named `reply`, so the scripted tree for it is built by a module helper instead of the fixture's reply() inside the test body. AC-30's "map counts the entry" is checked by blanking entries.jsonl to the same length and showing the rendered map changes, because the spec fixes the count but not the map's wording.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-agent/spec.md sections 4, 6.2 and 9.1.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_acceptance.py -q
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    TASK,
    ModelCall,
    ScriptedTree,
    build_agent,
    events,
    finished_cards,
    generator,
    is_error,
    journal_paths,
    journal_records,
    launch,
    map_section,
    observe,
    pair_key,
    read_jsonl,
    reply,
    task,
    tool_call,
    tool_results,
    verifier,
    workspace_root,
)

FINAL_ANSWER = "FINAL-ANSWER: Acme is cheapest at 49 USD per seat."


def _root_answers_at_once() -> ScriptedTree:
    return ScriptedTree({ROOT: [reply(FINAL_ANSWER)]})


def test_section_4_snippet_prints_the_root_answer_and_leaves_the_documented_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """AC-1, INV-21, INV-25: the section 4 snippet prints the root's final answer and leaves seed/brief.md, the bookkeeping files, and one finished journal."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "brief.md").write_text("Competitors: Acme, Globex, Initech, Umbrella, Hooli.\n", encoding="utf-8")
    tree = _root_answers_at_once()
    with tree.install():
        # ---- spec section 4, as printed ----
        from vidbyte import InfiniteMemoryAgent, InfiniteMemoryAgentSettings, InfiniteWorkspaceSettings

        # brief.md is an existing file next to this script.
        agent = InfiniteMemoryAgent(
            InfiniteMemoryAgentSettings(
                name="analyst",
                system_prompt="You research markets and report sourced findings.",
                provider="openai",
                model_name="gpt-4.1",
                root_dir=".",
                workspace=InfiniteWorkspaceSettings(root="memory", seed_files=("brief.md",)),
            )
        )

        try:
            reply = agent.run("Compare the list prices of our five competitors.")
        except KeyboardInterrupt:
            reply = agent.resume()  # continues that run; finished pairs are not run again
        print(reply.content)        # the root agent's final answer
        # ---- end of snippet ----
    tree.assert_complete()
    assert capsys.readouterr().out == FINAL_ANSWER + "\n"
    memory = tmp_path / "memory"
    assert (memory / "seed" / "brief.md").read_bytes() == (tmp_path / "brief.md").read_bytes()
    for name in ("entries.jsonl", "superseded.jsonl", "files.jsonl"):
        assert (memory / name).is_file(), f"{name} is missing"
    assert len(journal_paths(memory)) == 1
    records = journal_records(memory)
    assert records[0]["event"] == "run_started" and records[-1]["event"] == "run_finished"


def test_staged_entries_reach_disk_only_after_the_verifier_returns(tmp_path: Path) -> None:
    """AC-9, INV-15, INV-16: entries.jsonl has no line from the pair until the verifier returns; then both entries carry by, verified_by, run and at."""
    agent = build_agent(tmp_path)
    entries_file = workspace_root(tmp_path) / "entries.jsonl"
    seen_on_disk: list[tuple[str, str]] = []

    def look(call: ModelCall) -> None:
        seen_on_disk.append((call.agent, entries_file.read_text(encoding="utf-8")))

    tree = ScriptedTree(
        {
            ROOT: [launch(task("pricing")), reply("done")],
            generator("pricing"): [
                tool_call("remember", {"kind": "fact", "text": "Acme lists Pro at 49 USD per month"}),
                observe(look, tool_call("remember", {"kind": "decision", "text": "Compare monthly list prices only"})),
                observe(look, reply("Recorded two pricing facts.")),
            ],
            verifier("pricing"): [
                observe(look, tool_call("grep", {"pattern": "Acme"})),
                observe(look, reply("Both facts match their sources.\nVERDICT: passed")),
            ],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert [agent_name for agent_name, _ in seen_on_disk] == [generator("pricing")] * 2 + [verifier("pricing")] * 2
    assert all(text.strip() == "" for _, text in seen_on_disk), "a staged entry reached entries.jsonl before the verifier returned"
    run_id = journal_records(workspace_root(tmp_path))[0]["run"]
    committed = read_jsonl(entries_file)
    assert [entry["text"] for entry in committed] == ["Acme lists Pro at 49 USD per month", "Compare monthly list prices only"]
    assert [entry["kind"] for entry in committed] == ["fact", "decision"]
    for entry in committed:
        assert (entry["by"], entry["verified_by"], entry["run"]) == ("root/pricing/gen", "root/pricing/ver", run_id)
        assert datetime.fromisoformat(entry["at"]).utcoffset().total_seconds() == 0
    card = finished_cards(workspace_root(tmp_path))[pair_key("pricing")]
    assert card["entries"] == [entry["id"] for entry in committed] and len(set(card["entries"])) == 2
    assert card["verdict"] == "passed"


def test_root_usage_includes_every_generator_and_verifier_exactly_once(tmp_path: Path) -> None:
    """AC-24, INV-35: with fixed usage per runner, the root's get_usage() totals are the root's own plus each child's, counted once."""
    agent = build_agent(tmp_path)
    root_usage = {"input_tokens": 1_000, "output_tokens": 100}
    tree = ScriptedTree(
        {
            ROOT: [tool_call("launch_subagent", {"tasks": [task("pricing")]}, usage=root_usage), reply("done", usage=root_usage)],
            generator("pricing"): [reply("Found the prices.", usage={"input_tokens": 200, "output_tokens": 20})],
            verifier("pricing"): [reply("Checked.\nVERDICT: passed", usage={"input_tokens": 30, "output_tokens": 3})],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    usage = agent.get_usage()
    assert usage.model_call_count == 4
    assert (usage.input_tokens, usage.output_tokens) == (2_230, 223)


def test_a_second_agent_on_the_same_workspace_sees_the_first_agents_entry(tmp_path: Path) -> None:
    """AC-30, INV-22, D-6: agent B, built later on agent A's workspace, sees A's entry counted in its map and finds it with grep."""
    first = build_agent(tmp_path)
    first_tree = ScriptedTree({ROOT: [tool_call("remember", {"kind": "fact", "text": "Globex raised its list price to 99 USD"}), reply("saved")]})
    with first_tree.install():
        first.run(TASK)
    first_tree.assert_complete()
    second = build_agent(tmp_path)
    second_tree = ScriptedTree({ROOT: [tool_call("grep", {"pattern": "Globex raised its list price"}), reply("found")]})
    with second_tree.install():
        second.run("What did we learn about Globex?")
    second_tree.assert_complete()
    ((_, found),) = tool_results(second_tree.calls_by(ROOT)[-1])
    assert not is_error(found) and "entries.jsonl" in found and "Globex raised its list price to 99 USD" in found
    first_map = map_section(first_tree.first_call(ROOT).system)
    second_map = map_section(second_tree.first_call(ROOT).system)
    assert second_map != first_map
    entries_file = workspace_root(tmp_path) / "entries.jsonl"
    live_bytes = entries_file.read_bytes()
    live_map = second.workspace.map_text()
    assert live_map.strip() and live_map.strip() in second_map, "B's system string must carry the workspace's own map"
    # Every character but the line breaks becomes a space: the same length and token figures under any newline
    # handling, but no non-blank line, so only the live-entry count can change.
    entries_file.write_bytes(re.sub(r"[^\r\n]", " ", live_bytes.decode("utf-8")).encode("utf-8"))
    try:
        assert second.workspace.map_text() != live_map, "B's map does not count A's entry"
    finally:
        entries_file.write_bytes(live_bytes)
    journals = journal_paths(workspace_root(tmp_path))
    assert len(journals) == 2 and all(events(read_jsonl(path))[-1] == "run_finished" for path in journals)
