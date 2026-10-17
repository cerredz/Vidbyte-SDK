"""FILE: tests/features/agent_swarm/test_agent_swarm_workplace.py

PURPOSE: Pins the shared folder and the boundary checks around a run:
- a missing workplace is created with its parents when arun starts, never at construction;
- every file the agents write stays, and nothing else is added;
- a second run on the same folder sees the first run's files, and the user's own files stay byte-identical;
- a file at the workplace path, or a parent that is a file, is refused before any model call;
- the file tools refuse every path outside the folder;
- a blank or non-text goal is refused before any side effect, without blocking the next run.
ROLE IN CODEBASE: Workplace and boundary layer of tests/features/agent_swarm/ (spec AC-13 path refusals, AC-16, AC-18; EC-28, EC-29, EC-31; INV-18, INV-20, INV-21; FR-10, FR-17; D-11; A-11; T-1). Exercises AgentSwarmWorkplace, AgentSwarm.arun's checks, AgentSwarmRuntime.arun's goal check, and the file tools AgentSwarmTools roots in the folder.
ARCHITECTURE NOTE: Every folder is under tmp_path and every file operation is real; the model runner is the only fake.
FUNCTION INVENTORY: test_a_missing_workplace_is_created_with_its_parents_and_the_agents_files_stay (AC-16, INV-20); test_a_second_run_on_the_same_workplace_sees_earlier_files_and_user_files_stay_byte_identical (EC-31, INV-19, INV-20); test_constructing_the_swarm_or_its_runtime_creates_no_folder (D-11, A-11, FR-10); test_a_file_that_appears_at_the_workplace_path_is_refused_before_any_model_call (EC-28, INV-18); test_a_workplace_that_cannot_be_created_is_refused_with_the_os_error_as_cause (EC-29, INV-18); test_file_tools_refuse_paths_outside_the_workplace_and_change_nothing_there (AC-13, INV-21, T-1); test_a_blank_or_non_text_goal_is_refused_before_any_side_effect (AC-18, FR-17, INV-18).
COMMON MODIFICATION PATTERNS: A new workplace rule gets one test that builds the folder state by hand, runs a scripted swarm, and compares snapshot() before and after.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not compare paths as raw strings across the resolve boundary; compare resolved Path objects.
KNOWN EDGE CASES: The user files are written with CRLF line endings and compared as bytes, so a run that rewrote them in another encoding or line ending is caught on any platform. On Windows, creating a folder under a file raises FileExistsError; on Linux it raises NotADirectoryError; both are OSError.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm/spec.md sections 6.1 (INV-18, INV-20, INV-21), 6.3 (EC-28, EC-29, EC-31), 9.2 and 10.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_workplace.py -q
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    TOOL_CALLED,
    EventLog,
    ScriptedSwarm,
    assert_event_invariants,
    build_settings,
    build_swarm,
    is_error,
    of_kind,
    reply,
    run_swarm,
    send,
    snapshot,
    tool_call,
    tool_result,
    tool_results,
    workplace_path,
)

NAMES = ("builder", "tester")
PLAN = "# Plan\n\n1. Write c2f.py.\n2. Test it.\n"


def _names_the_path(error: BaseException, path: Path) -> bool:
    # The refusal names the folder, in its message or in its details.
    wanted = str(path.resolve())
    texts = [str(error), *(str(value) for value in (getattr(error, "details", None) or {}).values())]
    return any(wanted in text for text in texts)


@pytest.mark.asyncio
async def test_a_missing_workplace_is_created_with_its_parents_and_the_agents_files_stay(tmp_path: Path) -> None:
    """AC-16, INV-20, FR-10: a workplace whose parents do not exist is created when arun starts; the agents' files are all there afterwards and nothing else was added or removed."""
    from vidbyte import AgentSwarmStopReason

    workplace = tmp_path / "projects" / "c2f" / "workplace"
    scripted = ScriptedSwarm(
        {
            "builder": [tool_call("write_text", {"path": "notes/plan.md", "content": PLAN, "create_parents": True}), reply("Builder done.")],
            "tester": [tool_call("bash", {"command": "echo ok > test-log.txt"}), reply("Tester done.")],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, workplace=workplace)
    assert not (tmp_path / "projects").exists()
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert workplace.is_dir()
    files = snapshot(workplace)
    assert sorted(files) == ["notes/plan.md", "test-log.txt"]
    assert (workplace / "notes" / "plan.md").read_text(encoding="utf-8") == PLAN
    assert (workplace / "test-log.txt").read_text(encoding="utf-8").strip() == "ok"
    assert_event_invariants(result, NAMES, max_turns=500)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_second_run_on_the_same_workplace_sees_earlier_files_and_user_files_stay_byte_identical(tmp_path: Path) -> None:
    """EC-31, INV-19, INV-20: agents share one folder inside a run, a later run sees the earlier run's files, and files the user put there are never changed."""
    from vidbyte import AgentSwarmStopReason

    workplace = workplace_path(tmp_path)
    (workplace / "data").mkdir(parents=True)
    (workplace / "keep.txt").write_bytes(b"user notes\r\nline two\r\n")
    (workplace / "data" / "old.json").write_bytes(b'{"kept": true}')
    before = snapshot(workplace)
    log = EventLog()
    scripted = ScriptedSwarm(
        {
            # Run one: builder writes, then tells tester, who reads it. Run two: builder reads its own earlier file; tester reads the user's file.
            "builder": [
                tool_call("write_text", {"path": "shared.txt", "content": "from builder"}),
                send("tester", "shared.txt is ready."),
                reply("Builder done."),
                tool_call("read_lines", {"path": "shared.txt"}),
                reply("Builder second run."),
            ],
            "tester": [
                reply("Waiting."),
                tool_call("read_lines", {"path": "shared.txt"}),
                reply("Read it."),
                tool_call("read_lines", {"path": "keep.txt"}),
                reply("Tester second run."),
            ],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        first = await run_swarm(swarm)
        second = await run_swarm(swarm, "Check what the last run left in the folder.")

    for result in (first, second):
        assert result.stop_reason is AgentSwarmStopReason.QUIET
        assert_event_invariants(result, NAMES, max_turns=500)
    within_run = tool_result(scripted.calls_by("tester")[2], "read_lines")
    across_runs = tool_result(scripted.calls_by("builder")[4], "read_lines")
    user_file = tool_result(scripted.calls_by("tester")[4], "read_lines")
    assert not is_error(within_run) and "from builder" in within_run
    assert not is_error(across_runs) and "from builder" in across_runs
    assert not is_error(user_file) and "user notes" in user_file
    after = snapshot(workplace)
    assert {path: after.get(path) for path in before} == before
    assert sorted(after) == ["data/old.json", "keep.txt", "shared.txt"]
    scripted.assert_complete()


def test_constructing_the_swarm_or_its_runtime_creates_no_folder(tmp_path: Path) -> None:
    """D-11, A-11, FR-10: building AgentSwarm, AgentSwarmRuntime or AgentSwarmWorkplace touches no disk; prepare creates the folder, and preparing again keeps what is inside."""
    from vidbyte.agents.agent_swarm import AgentSwarm, AgentSwarmRuntime, AgentSwarmWorkplace

    workplace = tmp_path / "later" / "workplace"
    settings = build_settings(tmp_path, NAMES, workplace=workplace)
    AgentSwarm(settings)
    AgentSwarmRuntime(settings, workplace)
    place = AgentSwarmWorkplace(workplace)
    assert list(tmp_path.iterdir()) == []
    assert Path(place.root).resolve() == workplace.resolve()

    prepared = place.prepare()
    assert Path(prepared).resolve() == workplace.resolve() and workplace.is_dir()
    (workplace / "work.txt").write_text("in progress", encoding="utf-8")
    place.prepare()
    assert snapshot(workplace) == {"work.txt": b"in progress"}


@pytest.mark.asyncio
async def test_a_file_that_appears_at_the_workplace_path_is_refused_before_any_model_call(tmp_path: Path) -> None:
    """EC-28, INV-18: a file created at the workplace path after the settings were built is refused by arun with ConfigurationError naming the path; no model is called and the file is untouched."""
    from vidbyte.lib.errors import ConfigurationError

    swarm = build_swarm(tmp_path, NAMES)
    blocker = workplace_path(tmp_path)
    blocker.write_text("not a folder", encoding="utf-8")
    scripted = ScriptedSwarm({})
    with scripted.install():
        with pytest.raises(ConfigurationError) as refused:
            await run_swarm(swarm)

    assert _names_the_path(refused.value, blocker), str(refused.value)
    assert scripted.calls == []
    assert blocker.read_text(encoding="utf-8") == "not a folder"


@pytest.mark.asyncio
async def test_a_workplace_that_cannot_be_created_is_refused_with_the_os_error_as_cause(tmp_path: Path) -> None:
    """EC-29, INV-18: when the folder cannot be created (its parent is a file), arun raises ConfigurationError naming the path, chained from the OSError, before any model call."""
    from vidbyte.lib.errors import ConfigurationError

    blocker = tmp_path / "blocker.txt"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    workplace = blocker / "workplace"
    swarm = build_swarm(tmp_path, NAMES, workplace=workplace)
    scripted = ScriptedSwarm({})
    with scripted.install():
        with pytest.raises(ConfigurationError) as refused:
            await run_swarm(swarm)

    assert isinstance(refused.value.__cause__, OSError), repr(refused.value.__cause__)
    assert _names_the_path(refused.value, workplace), str(refused.value)
    assert scripted.calls == []
    assert sorted(path.name for path in tmp_path.iterdir()) == ["blocker.txt"]


@pytest.mark.asyncio
async def test_file_tools_refuse_paths_outside_the_workplace_and_change_nothing_there(tmp_path: Path) -> None:
    """AC-13, INV-21, T-1: read_lines, write_text and patch_file refuse relative escapes and absolute paths outside the workplace; the outside file is unchanged and its text never reaches the model."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET-OUTSIDE-TEXT", encoding="utf-8")
    attempts: list[tuple[str, dict[str, Any]]] = [
        ("read_lines", {"path": "../outside.txt"}),
        ("write_text", {"path": "../outside.txt", "content": "overwritten"}),
        ("patch_file", {"file_path": "../outside.txt", "search_block": "SECRET", "replace_block": "patched"}),
        ("read_lines", {"path": str(outside)}),
        ("write_text", {"path": str(outside), "content": "overwritten"}),
        ("patch_file", {"file_path": str(outside), "search_block": "SECRET", "replace_block": "patched"}),
    ]
    scripted = ScriptedSwarm({"builder": [*(tool_call(name, args) for name, args in attempts), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    results = tool_results(scripted.last_call("builder"))
    assert [name for name, _ in results] == [name for name, _ in attempts]
    assert all(is_error(content) for _, content in results), results
    assert all("SECRET-OUTSIDE-TEXT" not in content for _, content in results)
    assert outside.read_text(encoding="utf-8") == "SECRET-OUTSIDE-TEXT"
    assert [event.tool_status for event in of_kind(result.events, TOOL_CALLED, "builder")] == [ToolStatus.ERROR] * len(attempts)
    assert snapshot(workplace_path(tmp_path)) == {}
    assert_event_invariants(result, NAMES, max_turns=500)
    scripted.assert_complete()


BAD_GOALS = [
    pytest.param("", id="empty"),
    pytest.param("   \n\t ", id="blank"),
    pytest.param(None, id="none"),
    pytest.param(42, id="a-number"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["AgentSwarm", "AgentSwarmRuntime"])
@pytest.mark.parametrize("goal", BAD_GOALS)
async def test_a_blank_or_non_text_goal_is_refused_before_any_side_effect(tmp_path: Path, goal: Any, entry: str) -> None:
    """AC-18, FR-17, INV-18: AgentSwarm.arun and AgentSwarmRuntime.arun refuse a blank or non-text goal with ConfigurationError naming `goal`, before any folder, agent or model call; the next valid arun still runs."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.agents.agent_swarm import AgentSwarmRuntime
    from vidbyte.lib.errors import ConfigurationError

    settings = build_settings(tmp_path, NAMES)
    if entry == "AgentSwarm":
        from vidbyte.agents.agent_swarm import AgentSwarm

        runner: Any = AgentSwarm(settings)
    else:
        # AgentSwarmRuntime expects its folder to exist; it never creates one.
        workplace_path(tmp_path).mkdir()
        runner = AgentSwarmRuntime(settings, workplace_path(tmp_path))
    scripted = ScriptedSwarm({"builder": [reply("Builder done.")], "tester": [reply("Tester done.")]})
    with scripted.install():
        with pytest.raises(ConfigurationError) as refused:
            await run_swarm(runner, goal)
        assert refused.value.details["field"] == "goal"
        assert scripted.calls == []
        if entry == "AgentSwarm":
            assert not workplace_path(tmp_path).exists()
        # The refusal used up nothing: the same object still runs a valid goal.
        result = await run_swarm(runner)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert_event_invariants(result, NAMES, max_turns=500)
    scripted.assert_complete()
