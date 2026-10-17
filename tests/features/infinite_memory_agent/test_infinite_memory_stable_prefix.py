"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_stable_prefix.py

PURPOSE: Proves item 7 of spec infinite-memory-context-economy: the root's system string and tool schemas are byte-identical across one run (no loop-settings block, the map drawn once), each tool iteration appends at most one status message (the map_update leaf with the changed and removed map lines, then the loop-settings block; the block alone when nothing changed; nothing when the block is empty), the change lines are cut by the map's own rule and the baseline still advances, a caller system option still wins, children keep their block and their build-time map, and the snapshot and cut helpers lifted from map_text keep its output.
ROLE IN CODEBASE: Stable-prefix layer of tests/features/infinite_memory_agent/. Runs the root and pairs through ScriptedTree, which records each call's system string, messages after middleware, and the full tool dicts; calls InfiniteWorkspace directly for map_snapshot, fit_map_lines and InfiniteMapSnapshot.
ARCHITECTURE NOTE: The expected status message is rebuilt from the spec, not captured: each root call observes workspace.map_text() when it arrives (the disk as the previous iteration left it), the change lines are the map lines whose text differs from the previous report plus INFINITE_MAP_REMOVED_LINE for paths that left the map, and the loop-settings block comes from the base AgentRuntime._render_loop_settings_block with the live iteration count. _main_cut is main's map_text cut loop copied verbatim (base 0f2aeb48), the oracle for the capped change lines.
FUNCTION INVENTORY: _capturing wraps root steps so each records map_text; _map_lines / _changes / _block / _expected_status build the INV-7.3 oracle; _main_cut is main's cut. Tests: AC-7.1 + AC-7.3 + INV-7.1/7.2/7.5 + NFR-7.1 one run; AC-7.2 + INV-7.3/7.4 + EC-7.2 every status message; AC-7.5 + NFR-7.2 the block alone; the empty block; AC-7.4 + EC-7.8 the capped report and the advanced baseline; INV-7.6 the caller system; FR-7.2 snapshot and cut; section 9.1 InfiniteMapSnapshot validation.
COMMON MODIFICATION PATTERNS: Add a root step wrapped in _capturing and the generic oracle checks its status message; add a workspace change by writing through a memory tool or bash.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not compare a status message with a captured one; rebuild it from map_text, the leaf, and the block. 3. Do not wait on time; every ordering comes from ScriptedTree.
KNOWN EDGE CASES: The root's first call has no status message (EC-7.4). The run journal lives under .runs/, which the map does not count, so starting a run or finishing a pair is not a workspace change. A removed file's description stays in files.jsonl, so files.jsonl's line does not change when bash deletes a note.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-context-economy/spec.md sections 6.1 (INV-7.x), 6.2 (AC-7.x), 7 (EC-7.x, NFR-7.x), 8.5, 9.1, 12.3 rows 24-25.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_stable_prefix.py -q
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    MAP_HEADER,
    ROOT,
    TASK,
    ModelCall,
    ScriptedTree,
    build_agent,
    generator,
    launch,
    map_section,
    observe,
    prompt_text,
    reply,
    simple_pair,
    task,
    tool_call,
    verifier,
    workspace_root,
)
from vidbyte import tool
from vidbyte.agents import AgentLoopSettings, AgentRuntime
from vidbyte.lib.errors import ConfigurationError

MAP_LINE = re.compile(r"^- (.+?) \(\d+ tokens\): ")


@tool(name="echo_text")
def echo_text(text: str) -> str:
    """Return the text unchanged; it never touches the workspace."""
    return f"ECHO:{text}"


def _capturing(agent: Any, maps: list[str], steps: Sequence[Any]) -> list[Any]:
    # Each root call records workspace.map_text() when it arrives: the disk as the previous tool iteration left it.
    def capture(_: ModelCall) -> None:
        maps.append(agent.workspace.map_text())

    return [observe(capture, step) for step in steps]


def _map_lines(map_text: str) -> tuple[str, dict[str, str]]:
    # The header line and the map's file lines by path, in map order.
    header, *lines = map_text.split("\n")
    by_path: dict[str, str] = {}
    for line in lines:
        match = MAP_LINE.match(line)
        assert match is not None, f"not a map file line: {line!r}"
        by_path[match.group(1)] = line
    return header, by_path


def _changes(before: str, after: str) -> list[str]:
    # INV-7.3: every added or changed map line in map order, then one removed line per path that left the map.
    from vidbyte.lib.constants.infinite import INFINITE_MAP_REMOVED_LINE

    _, old = _map_lines(before)
    _, new = _map_lines(after)
    changed = [line for path, line in new.items() if old.get(path) != line]
    removed = [INFINITE_MAP_REMOVED_LINE.format(path=path) for path in old if path not in new]
    return changed + removed


def _block(agent: Any, iteration: int) -> str:
    # The base loop-settings block with the live iteration count; the default loop sets max_iterations only.
    loop = agent.settings.loop
    assert loop.max_tokens is None and loop.max_tool_calls is None, "precondition: the oracle renders max_iterations only"
    config = SimpleNamespace(max_iterations=loop.max_iterations, max_tokens=None, max_tool_calls=None)
    return AgentRuntime._render_loop_settings_block(SimpleNamespace(config=config), iteration_count=iteration, tokens_used=None, tool_call_count=0)


def _expected_status(agent: Any, before: str, after: str, iteration: int) -> str | None:
    # INV-7.3's three cases: changes (leaf, then the block when non-empty), the block alone, or nothing.
    changes = _changes(before, after)
    block = _block(agent, iteration)
    if changes:
        text = prompt_text("map_update").format(header=_map_lines(after)[0], changes="\n".join(changes))
        return f"{text}\n\n{block}" if block else text
    return block or None


def _main_cut(header: str, lines: Sequence[str]) -> list[str]:
    # main's InfiniteWorkspace.map_text cut loop at base 0f2aeb48, copied verbatim: the lines shown after the header.
    from vidbyte.lib.constants.infinite import INFINITE_MAP_MAX_TOKENS, INFINITE_MORE_FILES
    from vidbyte.lib.util import TokenEstimate
    from vidbyte.lib.util.text import TOKEN_ESTIMATE_CHARS_PER_TOKEN

    if TokenEstimate.count("\n".join((header, *lines))) <= INFINITE_MAP_MAX_TOKENS:
        return list(lines)
    room = INFINITE_MAP_MAX_TOKENS * TOKEN_ESTIMATE_CHARS_PER_TOKEN - len(INFINITE_MORE_FILES.format(count=len(lines))) - len("\n")
    shown = header
    kept: list[str] = []
    for index, line in enumerate(lines):
        if len(shown) + len("\n") + len(line) > room:
            return [*kept, INFINITE_MORE_FILES.format(count=len(lines) - index)]
        shown = f"{shown}\n{line}"
        kept.append(line)
    return kept


def _user_messages(call: ModelCall) -> list[str]:
    return [str(message.get("content")) for message in call.messages if message.get("role") == "user"]


def _note(path: str, text: str, description: str) -> Any:
    return tool_call("write_note", {"path": path, "text": text, "description": description})


def test_one_root_run_keeps_one_system_string_and_one_tool_list_while_children_keep_their_block(tmp_path: Path) -> None:
    """AC-7.1, AC-7.3, INV-7.1, INV-7.2, INV-7.5, NFR-7.1: write a note, remember, run bash, launch a pair; the root's prefix never changes."""
    agent = build_agent(tmp_path)
    maps: list[str] = []
    steps = [
        _note("notes/new.md", "Fresh findings about pricing.", "Fresh pricing findings"),
        tool_call("remember", {"kind": "fact", "text": "Acme lists Pro at 49 USD per month"}),
        tool_call("bash", {"command": "printf 'Bash wrote this line\\n' > memory/notes/bash.md"}),
        launch(task("alpha")),
        reply("done"),
    ]
    tree = ScriptedTree({ROOT: _capturing(agent, maps, steps), **simple_pair("alpha", "ALPHA-SUMMARY")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    root_calls = tree.calls_by(ROOT)
    assert len(root_calls) == 5
    assert len({call.system for call in root_calls}) == 1, "the root's system string changed between calls"
    assert all(call.raw_tools == root_calls[0].raw_tools for call in root_calls), "the root's tool dicts changed between calls"
    for call in root_calls:
        assert "max_iterations:" not in call.system
        assert MAP_HEADER in call.system
        assert "notes/new.md" not in map_section(call.system) and "notes/bash.md" not in map_section(call.system), "the root's map was drawn again"
    # The children keep the loop-settings block and a map drawn when they were built, as on main.
    for child in (generator("alpha"), verifier("alpha")):
        system = tree.first_call(child).system
        assert "- max_iterations: 0/500" in system and MAP_HEADER in system, child
        assert "notes/new.md" in map_section(system) and "notes/bash.md" in map_section(system), child


def test_each_tool_iteration_appends_one_status_message_with_the_changed_map_lines_and_the_loop_block(tmp_path: Path) -> None:
    """AC-7.2, AC-7.5, INV-7.3, INV-7.4, EC-7.2: the exact message after a new note, a new entry, a bash write plus delete, and a no-change tool."""
    agent = build_agent(tmp_path, tools=(echo_text,))
    maps: list[str] = []
    steps = [
        _note("notes/new.md", "Fresh findings about pricing.", "Fresh pricing findings"),
        tool_call("remember", {"kind": "fact", "text": "Acme lists Pro at 49 USD per month"}),
        tool_call("bash", {"command": "printf 'Bash wrote this line\\n' > memory/notes/bash.md && rm memory/notes/new.md"}),
        tool_call("echo_text", {"text": "nothing changes"}),
        reply("done"),
    ]
    tree = ScriptedTree({ROOT: _capturing(agent, maps, steps)})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    root_calls = tree.calls_by(ROOT)
    assert len(maps) == len(root_calls) == 5
    assert _user_messages(root_calls[0]) == [], "the first call has no status message (EC-7.4)"
    for index in range(1, len(root_calls)):
        expected = _expected_status(agent, maps[index - 1], maps[index], index)
        assert root_calls[index].messages[-1] == {"role": "user", "content": expected}, f"status message before root call {index}"
        assert len(_user_messages(root_calls[index])) == index, "more than one status message for one tool iteration"
    # AC-7.2 in its own words: the leaf text, the new note's map line, and the iteration counter.
    after_note = str(root_calls[1].messages[-1]["content"])
    assert re.search(r"^- notes/new\.md \(\d+ tokens\): Fresh pricing findings$", after_note, re.MULTILINE), after_note
    assert after_note.endswith("- max_iterations: 1/500")
    assert "- notes/new.md: removed" in str(root_calls[3].messages[-1]["content"])
    assert re.search(r"^- notes/bash\.md \(\d+ tokens\): ", str(root_calls[3].messages[-1]["content"]), re.MULTILINE)
    # AC-7.5, NFR-7.2: the no-change iteration's message is exactly the block, at most 40 tokens.
    from vidbyte.lib.util import TokenEstimate

    quiet = str(root_calls[4].messages[-1]["content"])
    assert quiet == _block(agent, 4) and quiet.endswith("- max_iterations: 4/500")
    assert MAP_HEADER not in quiet and _map_lines(maps[4])[0] not in quiet
    assert TokenEstimate.count(quiet) <= 40


def test_with_an_empty_loop_block_a_quiet_iteration_appends_nothing_and_a_change_appends_the_leaf_alone(tmp_path: Path) -> None:
    """INV-7.3 third case: AgentLoopSettings() sets no budget, so the block is empty."""
    agent = build_agent(tmp_path, tools=(echo_text,), loop=AgentLoopSettings())
    maps: list[str] = []
    steps = [_note("notes/new.md", "Fresh findings about pricing.", "Fresh pricing findings"), tool_call("echo_text", {"text": "quiet"}), reply("done")]
    tree = ScriptedTree({ROOT: _capturing(agent, maps, steps)})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    root_calls = tree.calls_by(ROOT)
    expected = prompt_text("map_update").format(header=_map_lines(maps[1])[0], changes="\n".join(_changes(maps[0], maps[1])))
    assert root_calls[1].messages[-1] == {"role": "user", "content": expected}
    assert _user_messages(root_calls[2]) == [expected], "a quiet iteration with an empty block appended a message"
    assert root_calls[2].messages[-1]["role"] == "tool"


def test_a_report_over_the_map_cap_is_cut_by_the_maps_rule_and_its_left_out_lines_are_never_repeated(tmp_path: Path) -> None:
    """AC-7.4, EC-7.8, INV-7.3, INV-7.4: one bash loop writes 1,000 notes; the next report is capped; the report after it names only the new change."""
    from vidbyte.lib.constants.infinite import INFINITE_MAP_MAX_TOKENS, INFINITE_MORE_FILES
    from vidbyte.lib.util import TokenEstimate

    agent = build_agent(tmp_path)
    snapshots: list[Any] = []

    def snap(_: ModelCall) -> None:
        snapshots.append(agent.workspace.map_snapshot())

    loop = "mkdir -p memory/bulk && for i in $(seq 1000 1999); do echo \"bulk note $i\" > memory/bulk/n$i.md; done"
    steps = [tool_call("bash", {"command": loop}), _note("notes/after.md", "One more finding.", "After the bulk write"), reply("done")]
    tree = ScriptedTree({ROOT: [observe(snap, step) for step in steps]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    root_calls = tree.calls_by(ROOT)
    before_paths = {path for path, _ in snapshots[0].lines}
    added = [line for path, line in snapshots[1].lines if path not in before_paths]
    assert len(added) == 1000, "precondition: the bash loop wrote 1,000 notes"
    header = snapshots[1].header
    shown = _main_cut(header, added)
    assert shown[-1].startswith("… and "), "precondition: 1,000 change lines exceed the map cap"
    report = str(root_calls[1].messages[-1]["content"])
    assert report == prompt_text("map_update").format(header=header, changes="\n".join(shown)) + "\n\n" + _block(agent, 1)
    assert TokenEstimate.count("\n".join((header, *shown))) <= INFINITE_MAP_MAX_TOKENS
    left_out = len(added) - (len(shown) - 1)
    assert shown[-1] == INFINITE_MORE_FILES.format(count=left_out)
    next_report = str(root_calls[2].messages[-1]["content"])
    assert not any(line in next_report for line in added), "the next report repeated change lines the capped report left out"
    assert re.search(r"^- notes/after\.md \(\d+ tokens\): After the bulk write$", next_report, re.MULTILINE), next_report


def test_a_caller_system_option_still_replaces_the_root_prompt_and_status_messages_still_arrive(tmp_path: Path) -> None:
    """INV-7.6, prior D-27: system="CALLER-SYSTEM" is every root call's system; the status message follows the note iteration."""
    agent = build_agent(tmp_path)
    maps: list[str] = []
    tree = ScriptedTree({ROOT: _capturing(agent, maps, [_note("notes/new.md", "Fresh findings.", "Fresh findings"), reply("done")])})
    with tree.install():
        agent.run(TASK, system="CALLER-SYSTEM")
    tree.assert_complete()
    root_calls = tree.calls_by(ROOT)
    assert [call.system for call in root_calls] == ["CALLER-SYSTEM", "CALLER-SYSTEM"]
    assert root_calls[1].messages[-1] == {"role": "user", "content": _expected_status(agent, maps[0], maps[1], 1)}


def test_the_map_snapshot_and_the_lifted_cut_render_map_text_unchanged(tmp_path: Path) -> None:
    """FR-7.2, INV-7.3, row 24: map_snapshot holds the header and uncapped (path, line) pairs; fit_map_lines is main's cut; map_text is header plus the cut lines."""
    from vidbyte.agents.infinite import InfiniteWorkspaceSettings
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.dataclasses.infinite import InfiniteMapSnapshot

    workspace = InfiniteWorkspace(InfiniteWorkspaceSettings(root=workspace_root(tmp_path)))
    small = workspace.map_snapshot()
    assert isinstance(small, InfiniteMapSnapshot)
    assert workspace.map_text() == "\n".join((small.header, *(line for _, line in small.lines)))
    assert [path for path, _ in small.lines] == list(_map_lines(workspace.map_text())[1])
    bulk = workspace.root / "bulk"
    bulk.mkdir()
    for number in range(1200):
        (bulk / f"n{number:04d}.md").write_text(f"bulk note {number}\n", encoding="utf-8")
    large = workspace.map_snapshot()
    lines = [line for _, line in large.lines]
    assert len(lines) == len(small.lines) + 1200, "map_snapshot must not cut its lines"
    fitted = InfiniteWorkspace.fit_map_lines(large.header, lines)
    assert list(fitted) == _main_cut(large.header, lines)
    assert fitted[-1].startswith("… and ") and len(fitted) < len(lines), "precondition: 1,200 notes must overflow the map cap"
    assert workspace.map_text() == "\n".join((large.header, *fitted))
    assert list(InfiniteWorkspace.fit_map_lines(small.header, [line for _, line in small.lines])) == [line for _, line in small.lines]


def test_a_map_snapshot_refuses_duplicate_paths_and_a_non_text_header() -> None:
    """Section 9.1: header is a str; lines are (str, str) pairs with unique paths."""
    from vidbyte.lib.dataclasses.infinite import InfiniteMapSnapshot

    InfiniteMapSnapshot(header="Files: 1 of 2.", lines=(("notes/a.md", "- notes/a.md (1 tokens): A"),))
    for header, lines in (
        ("h", (("notes/a.md", "- a"), ("notes/a.md", "- a again"))),
        (None, ()),
        ("h", (("notes/a.md",),)),
        ("h", ((1, "- a"),)),
    ):
        with pytest.raises(ConfigurationError):
            InfiniteMapSnapshot(header=header, lines=lines)  # type: ignore[arg-type]


def test_the_removed_line_label_is_the_spec_format() -> None:
    """Section 8.5: INFINITE_MAP_REMOVED_LINE is "- {path}: removed"."""
    from vidbyte.lib.constants.infinite import INFINITE_MAP_REMOVED_LINE

    assert INFINITE_MAP_REMOVED_LINE == "- {path}: removed"
