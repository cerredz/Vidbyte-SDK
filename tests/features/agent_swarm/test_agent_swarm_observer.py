"""FILE: tests/features/agent_swarm/test_agent_swarm_observer.py

PURPOSE: Pins what the swarm observer records about each member's own work. A history over the provider-boundary cap records one history_trimmed per model call the trim changed, with the exact number of messages that call did not send. A tool result longer than the result cap records tool_result_truncated with the exact omitted count, and one exactly at the cap records nothing. Two agents writing one file record file_changed with the same absolute path, naming the previous writer when it was another agent, through write_text and patch_file alike; a refused write records nothing. A bash command that exits non-zero, or runs out of time, records command_failed, and a zero exit records none.
ROLE IN CODEBASE: Observation layer of tests/features/agent_swarm/ (docs/spec/agent-swarm-v2/spec.md AC-11, AC-12, AC-13, AC-14; EC-15, EC-16, EC-17, EC-18, EC-19, EC-20; INV-24, INV-25, INV-26, INV-27, INV-36). Exercises AgentSwarmTrimMiddleware, AgentSwarmObserverMiddleware.after_tool_call, and AgentSwarmRuntime.record_history_trim and record_tool_outcome, through real files, real bash and the real loop.
ARCHITECTURE NOTE: Expected counts are computed from the run itself, never from the trim's internals: the loop's untrimmed history after k single-tool steps holds 2k messages, so what a trimmed call did not send is 2k minus the messages it carried. Sizes come from the constants and the SDK's four-characters-per-token estimate. Bash limits are lowered by monkeypatching the bash module's own globals, which it reads at call time.
FUNCTION INVENTORY: _next_own (the next event of the same agent); test_each_model_call_the_trim_changes_records_history_trimmed_with_its_exact_drop (AC-11, EC-20, INV-24, INV-36); test_a_tool_result_over_the_cap_records_its_exact_omitted_count_and_one_at_the_cap_records_none (AC-12, EC-19, INV-25); test_two_agents_writing_one_file_record_file_changed_naming_the_previous_writer (AC-13, EC-16, INV-26); test_a_refused_write_records_no_file_changed (EC-15); test_bash_records_command_failed_for_a_non_zero_exit_and_none_for_zero (AC-14, EC-17, EC-18, INV-27); test_a_bash_command_that_runs_out_of_time_records_command_failed_timeout (AC-14, INV-27).
COMMON MODIFICATION PATTERNS: A new derived event gets one test that makes the tool produce it through a real call and asserts that it is the next event of the same agent after that tool's tool_called.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not mock the trim, the tools or bash; the counts must come from the real pipeline. 3. Do not write a bash command that can outlive its test: the timeout case loops on the shell's own SECONDS counter, so even where only the launcher is killed (Windows) it stops by itself within a few seconds.
KNOWN EDGE CASES: read_lines returns a one-line file's text unchanged, so a file with no newline gives a tool output of exactly its length. Other agents' events may fall between a tool_called and its derived event, so the test follows the same agent's next event.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm-v2/spec.md sections 6.1 (INV-24 to INV-27, INV-36), 6.2 and 6.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_observer.py -q
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    COMMAND_FAILED,
    FILE_CHANGED,
    MODEL_CALLED,
    TOOL_CALLED,
    TRIMMED,
    TRUNCATED,
    EventLog,
    ScriptedSwarm,
    after,
    assert_event_invariants,
    build_swarm,
    describe,
    is_error,
    of_kind,
    only,
    reply,
    run_swarm,
    tool_call,
    tool_result,
    workplace_path,
)

NAMES = ("builder", "tester")


def _next_own(events: Any, event: Any) -> Any:
    # The first event after `event` that names the same agent.
    return next(item for item in events[event.sequence :] if item.agent == event.agent)


def _write(tmp_path: Path, name: str, text: str) -> None:
    root = workplace_path(tmp_path)
    root.mkdir(exist_ok=True)
    (root / name).write_text(text, encoding="utf-8", newline="")


@pytest.mark.asyncio
async def test_each_model_call_the_trim_changes_records_history_trimmed_with_its_exact_drop(tmp_path: Path) -> None:
    """AC-11, EC-20, INV-24, INV-36: builder reads a file just under the result cap until its history outgrows AGENT_SWARM_HISTORY_MAX_TOKENS; every call the trim changed records one history_trimmed, before that call's model_called, with messages_dropped equal to the untrimmed history length minus what the call carried, and at least two consecutive calls are trimmed."""
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_HISTORY_MAX_TOKENS, AGENT_SWARM_TOOL_RESULT_MAX_CHARS
    from vidbyte.lib.util.text import TOKEN_ESTIMATE_CHARS_PER_TOKEN

    size = AGENT_SWARM_TOOL_RESULT_MAX_CHARS - 1_000
    reads = AGENT_SWARM_HISTORY_MAX_TOKENS * TOKEN_ESTIMATE_CHARS_PER_TOKEN // size + 2
    _write(tmp_path, "big.txt", "b" * size)
    log = EventLog()
    scripted = ScriptedSwarm({"builder": [*(tool_call("read_lines", {"path": "big.txt"}) for _ in range(reads)), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    builder_calls = scripted.calls_by("builder")
    assert len(builder_calls) == reads + 1
    # Call k (from 0) follows k single-tool steps, so the loop's untrimmed history holds 2k messages.
    expected = [2 * k - len(call.messages) for k, call in enumerate(builder_calls) if len(call.messages) < 2 * k]
    trimmed = of_kind(result.events, TRIMMED, "builder")
    assert [event.messages_dropped for event in trimmed] == expected, describe(result.events)
    assert len(expected) >= 2 and all(count > 0 for count in expected)
    assert all(_next_own(result.events, event).kind.value == MODEL_CALLED for event in trimmed)
    assert of_kind(result.events, TRIMMED, "tester") == [] and of_kind(result.events, TRUNCATED) == []
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
@pytest.mark.parametrize(("extra", "omitted"), [pytest.param(2_345, 2_345, id="over-the-cap"), pytest.param(0, None, id="exactly-the-cap")])
async def test_a_tool_result_over_the_cap_records_its_exact_omitted_count_and_one_at_the_cap_records_none(tmp_path: Path, extra: int, omitted: int | None) -> None:
    """AC-12, EC-19, INV-25: a read_lines output of the cap plus 2,345 characters records tool_result_truncated (read_lines, 2,345) as the agent's next event after its tool_called, and the model still sees a capped result; an output of exactly the cap records nothing and reaches the model whole."""
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_TOOL_RESULT_MAX_CHARS

    cap = AGENT_SWARM_TOOL_RESULT_MAX_CHARS
    _write(tmp_path, "wide.txt", "w" * (cap + extra))
    log = EventLog()
    scripted = ScriptedSwarm({"builder": [tool_call("read_lines", {"path": "wide.txt"}), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    visible = tool_result(scripted.calls_by("builder")[1], "read_lines")
    called = only(result.events, TOOL_CALLED, "builder")
    if omitted is None:
        assert of_kind(result.events, TRUNCATED) == [], describe(result.events)
        assert visible == "w" * cap
    else:
        truncated = only(result.events, TRUNCATED, "builder")
        assert (truncated.tool_name, truncated.omitted_chars) == ("read_lines", omitted)
        assert _next_own(result.events, called) == truncated
        assert len(visible) <= cap + cap // 100, f"{len(visible)} characters reached the model"
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_two_agents_writing_one_file_record_file_changed_naming_the_previous_writer(tmp_path: Path) -> None:
    """AC-13, EC-16, INV-26: ada writes notes.md with write_text, ben patches it with patch_file through a relative file_path, then ada writes it again; the three file_changed events carry one absolute path of that file, with peer "", then "ada", then "ben"."""
    from vidbyte import AgentSwarmStopReason

    names = ("ada", "ben")
    log = EventLog()
    ada_changed, ben_changed = log.signal(FILE_CHANGED, "ada"), log.signal(FILE_CHANGED, "ben")
    scripted = ScriptedSwarm(
        {
            "ada": [
                tool_call("write_text", {"path": "notes.md", "content": "# Notes\nTODO\n"}),
                after(ben_changed, tool_call("write_text", {"path": "notes.md", "content": "# Notes\nFINAL\n"})),
                reply("Ada done."),
            ],
            "ben": [after(ada_changed, tool_call("patch_file", {"file_path": "notes.md", "search_block": "TODO", "replace_block": "DONE"})), reply("Ben done.")],
        }
    )
    swarm = build_swarm(tmp_path, names, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    changes = of_kind(result.events, FILE_CHANGED)
    assert [(event.agent, event.peer) for event in changes] == [("ada", ""), ("ben", "ada"), ("ada", "ben")], describe(result.events)
    assert len({event.path for event in changes}) == 1
    assert Path(changes[0].path).is_absolute() and Path(changes[0].path).resolve() == (workplace_path(tmp_path) / "notes.md").resolve()
    assert (workplace_path(tmp_path) / "notes.md").read_text(encoding="utf-8") == "# Notes\nFINAL\n"
    for change in changes:
        tool = of_kind(result.events, TOOL_CALLED, change.agent)
        assert any(_next_own(result.events, event) == change for event in tool), change
    assert_event_invariants(result, names, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_refused_write_records_no_file_changed(tmp_path: Path) -> None:
    """EC-15, INV-26: a write_text outside the workplace is a tool error with tool_called status error and records no file_changed."""
    from vidbyte.lib.dataclasses.tools import ToolStatus

    log = EventLog()
    scripted = ScriptedSwarm({"builder": [tool_call("write_text", {"path": "../outside.txt", "content": "x"}), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert is_error(tool_result(scripted.calls_by("builder")[1], "write_text"))
    assert only(result.events, TOOL_CALLED, "builder").tool_status is ToolStatus.ERROR
    assert of_kind(result.events, FILE_CHANGED) == [] and not (tmp_path / "outside.txt").exists()
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_bash_records_command_failed_for_a_non_zero_exit_and_none_for_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-14, EC-17, EC-18, INV-27: a zero exit records no command_failed; exit 3 records one command_failed "exit code 3"; exit 4 with output the tool itself cut records exactly one command_failed "exit code 4"; each follows its own tool_called; the file the zero-exit command wrote records no file_changed, because bash reports no path."""
    import vidbyte.tools.builtins.bash as bash_module

    monkeypatch.setattr(bash_module, "BASH_MAX_OUTPUT_BYTES", 16)
    commands = ["echo fine > fine.txt", "echo broken; exit 3", "printf 'abcdefghij%.0s' 1 2 3 4 5; exit 4"]
    log = EventLog()
    scripted = ScriptedSwarm({"tester": [*(tool_call("bash", {"command": command}) for command in commands), reply("Tester done.")], "builder": [reply("Builder done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    tools = of_kind(result.events, TOOL_CALLED, "tester")
    assert [event.tool_name for event in tools] == ["bash", "bash", "bash"]
    followers = [_next_own(result.events, event) for event in tools]
    assert followers[0].kind.value != COMMAND_FAILED
    assert [(event.kind.value, event.text) for event in followers[1:]] == [(COMMAND_FAILED, "exit code 3"), (COMMAND_FAILED, "exit code 4")], describe(result.events)
    assert len(of_kind(result.events, COMMAND_FAILED)) == 2
    # EC-17: a write made through bash is real but invisible to file_changed (NG-5).
    assert (workplace_path(tmp_path) / "fine.txt").read_text(encoding="utf-8").strip() == "fine" and of_kind(result.events, FILE_CHANGED) == []
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_bash_command_that_runs_out_of_time_records_command_failed_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-14, INV-27: a bash command still running at the bash time limit is a tool error and records one command_failed with text "timeout" as tester's next event after that tool_called."""
    import vidbyte.tools.builtins.bash as bash_module
    from vidbyte.lib.dataclasses.tools import ToolStatus

    monkeypatch.setattr(bash_module, "BASH_TIMEOUT_SECONDS", 0.5)
    log = EventLog()
    # The loop ends on its own after about three seconds, so nothing outlives the test even where only the launcher is killed.
    scripted = ScriptedSwarm({"tester": [tool_call("bash", {"command": "while (( SECONDS < 3 )); do :; done"}), reply("Tester done.")], "builder": [reply("Builder done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    called = only(result.events, TOOL_CALLED, "tester")
    assert (called.tool_name, called.tool_status) == ("bash", ToolStatus.ERROR)
    failed = only(result.events, COMMAND_FAILED, "tester")
    assert failed.text == "timeout" and _next_own(result.events, called) == failed, describe(result.events)
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()
