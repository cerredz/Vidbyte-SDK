"""FILE: tests/features/agent_swarm/test_agent_swarm_compaction.py

PURPOSE: Pins per-agent compaction. A compact call, or a measured context at the trigger, rewrites the member's own history at the end of a tool iteration: one summary side call through the member's runner gets the summarizer leaf (with the focus) and a transcript of only the older messages, the live list becomes the summary message plus the kept newest groups, and mail is appended after the summary. One compaction runs per iteration, the last focus wins, a request survives a turn end, nothing older means nothing happens, a blank summary still compacts, a failed summary keeps the history and fails nobody, and a side call can itself reach the token budget. Every size estimate counts whole messages (spec r4 INV-33), so a Gemini member's parts history and an OpenAI history of write calls, whose text sits in tool_calls, compact at the trigger like any other. A repeat automatic compaction waits until the estimate of the history has grown by the target since the last compaction, while a compact request compacts at once (spec r4 INV-32, D-12). The same whole-message estimate measures a member whose provider reports no usage and decides that growth, so a Gemini member compacts at the estimated trigger and again after each target of new parts history (S5 re-review R-20).
ROLE IN CODEBASE: Compaction layer of tests/features/agent_swarm/ (docs/spec/agent-swarm-v2/spec.md r4 AC-16, AC-17, AC-18; EC-6, EC-21, EC-22, EC-23, EC-24, EC-35; INV-30 to INV-35; D-12; S4 review R-2, R-6, R-7; S5 re-review R-20). Exercises AgentSwarmMemberRuntime._after_tool_iteration, AgentSwarmHandoffSummarizer, AgentSwarmCompactTool and AgentSwarmRuntime.request_compaction, take_compaction_request, last_prompt_tokens and record_compaction, over the real ContextCompactionEngine.
ARCHITECTURE NOTE: The summary side call reaches the same scripted runner as the loop, so it is one more step in the agent's script (spec section 13): a script that is one step short, or one step long, fails assert_complete. Two files of sixty thousand characters make the older history: together they pass AGENT_SWARM_COMPACTION_TARGET_TOKENS by the four-characters-per-token estimate, one of them alone does not, so the newest read is kept and the oldest is summarized. Measured context is scripted through each response's usage.
FUNCTION INVENTORY: _setup / _run (write the two files; run one scripted swarm and check it with the oracle); _run_unchecked / _check (the same run and check split in two, for a test that asserts its own outcome before the oracle, so a missing compaction fails on that assertion and not on a leftover step); _request_tokens (what a provider would count as one request's prompt, for usage computed from each request); _write_parts / _gemini_builder / _is_side_call (numbered one-line part files; the build_swarm fields for a Gemini builder; whether a call is the summary side call); test_a_compact_call_summarizes_only_the_older_history_and_mail_follows_the_summary (AC-16, INV-30, INV-33, INV-34, INV-35); test_a_measured_context_at_the_trigger_compacts_automatically_and_one_below_does_not (AC-17, INV-32); test_a_pending_request_and_the_trigger_in_one_iteration_compact_once (AC-17, INV-31); test_anthropic_context_is_measured_as_all_three_input_buckets (INV-32, EC-35); test_a_gemini_member_at_the_trigger_compacts_its_parts_history_through_one_summary_call (INV-32, INV-33, R-2); test_an_openai_history_of_write_calls_only_compacts_at_the_trigger (INV-32, INV-33, R-2); test_automatic_compaction_waits_for_a_target_of_new_history_and_a_compact_request_does_not (INV-32, D-12, INV-31, R-6); test_a_gemini_member_compacts_again_each_time_its_parts_history_grows_by_the_target (INV-32, INV-33, INV-36, R-20); test_a_gemini_member_whose_provider_reports_no_usage_compacts_when_its_estimate_reaches_the_trigger (INV-32, INV-33, EC-8, R-20); test_the_summary_call_tokens_are_added_to_the_members_tokens_used (INV-35, R-7); test_a_failed_summary_keeps_the_history_delivers_mail_and_fails_nobody (AC-18, INV-35); test_a_compact_request_with_nothing_older_changes_nothing_and_is_consumed (EC-21); test_two_compact_calls_in_one_response_compact_once_with_the_last_focus (EC-22); test_a_request_made_with_isdone_waits_for_the_next_iteration_after_the_wake (EC-23); test_a_blank_summary_still_compacts_to_the_prefix (EC-24); test_a_side_call_that_reaches_the_budget_completes_its_compaction_and_stops_the_swarm (EC-6); test_the_summarizer_prompt_names_the_ten_sections_in_order (INV-34).
COMMON MODIFICATION PATTERNS: A new compaction rule gets one test built on _setup and _run that scripts the side call as a step and compares the next loop call's messages with the previous call's.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not mock ContextCompactionEngine or the summarizer; the real engine decides what is kept. 3. Do not make the files smaller or larger without redoing the size argument above.
KNOWN EDGE CASES: messages_dropped is the number of summarized messages (the engine's before-minus-after count plus the one summary message added). The side call's model_called carries the loop's model call count at that moment, which equals the preceding loop call's. An Anthropic member's history uses Anthropic message shapes, so its test reads only events and the summary's position. A Gemini member's history is model and user turns of parts with no content key; the engine's summary stays an assistant message with content, which the Gemini provider maps to a model turn. Three sixty-thousand-character writes are the smallest write-only history with something older to summarize, because group rounding keeps the second write's whole group. The hysteresis test's goal alone is over the trigger, so every call meets the trigger and only the growth rule spaces the compactions; its usage is computed from each request, never scripted as a constant. A Gemini member whose provider reports no usage records the estimate of the history at the check as its compaction's input_tokens; INV-33 fixes what that estimate counts but not its exact text, so the test computes it with the member's own static _estimate over the history it can see (the last loop call before the check plus the read the compaction kept).
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm-v2/spec.md sections 6.1 (INV-30 to INV-35), 6.2, 6.3, 8.5 (_after_tool_iteration) and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_compaction.py -q
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    ANTHROPIC_MODEL,
    COMPACTION,
    DEFAULT_USAGE,
    DELIVERED,
    FAILED,
    FAKE_ANTHROPIC_KEY,
    FAKE_GEMINI_KEY,
    FAKE_OPENAI_KEY,
    GEMINI_MODEL,
    IDLE,
    MODEL_CALLED,
    MODEL_ERROR,
    RELEASED,
    SENT,
    STOPPING,
    TOOL_CALLED,
    TRIMMED,
    WOKE,
    EventLog,
    ScriptedSwarm,
    Signal,
    after,
    assert_event_invariants,
    build_swarm,
    calls,
    compact,
    describe,
    fail,
    finish,
    member,
    observe,
    of_kind,
    only,
    prompt_text,
    provider_error,
    reply,
    run_swarm,
    seen_text,
    send,
    template_regex,
    tool_call,
    workplace_path,
)

NAMES = ("builder", "tester")
NOTE = "Tester here: c2f must accept negative input."
FOCUS = "keep the c2f command-line interface in detail"
SUMMARY = "IDENTITY builder. GOAL the converter. NEXT STEPS run the tests."
MARK_ONE, MARK_TWO = "OLDER-HISTORY-MARK", "NEWER-HISTORY-MARK"
READ_ONE = tool_call("read_lines", {"path": "older.txt"})
READ_TWO = tool_call("read_lines", {"path": "newer.txt"})
# One mark per write, so a transcript or a later call shows which writes it still holds.
WRITE_MARKS = ("FIRST-WRITE-MARK", "SECOND-WRITE-MARK", "THIRD-WRITE-MARK")
SECTIONS = ("IDENTITY", "PEERS", "GOAL", "MESSAGES RECEIVED", "MESSAGES SENT", "PROMISES TO PEERS", "FILES CHANGED", "WORK IN PROGRESS", "DECISIONS", "NEXT STEPS")


def _setup(tmp_path: Path) -> None:
    # Two one-line files: each read alone fits the compaction target, both together do not.
    root = workplace_path(tmp_path)
    root.mkdir()
    (root / "older.txt").write_text(MARK_ONE + "1" * 60_000, encoding="utf-8", newline="")
    (root / "newer.txt").write_text(MARK_TWO + "2" * 60_000, encoding="utf-8", newline="")


async def _run(tmp_path: Path, scripted: ScriptedSwarm, log: EventLog, names: tuple[str, ...] = NAMES, **fields: Any) -> Any:
    # One scripted run, checked by the oracle and for unused or missing steps.
    swarm = build_swarm(tmp_path, names, on_event=log.callback, **fields)
    with scripted.install():
        result = await run_swarm(swarm)
    assert_event_invariants(result, names, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()
    return result


async def _run_unchecked(tmp_path: Path, scripted: ScriptedSwarm, log: EventLog, names: tuple[str, ...] = NAMES, **fields: Any) -> tuple[Any, Any]:
    # One scripted run for a test that asserts its own outcome first and then calls _check, so a missing compaction fails on its own assertion rather than on a leftover step.
    swarm = build_swarm(tmp_path, names, on_event=log.callback, **fields)
    with scripted.install():
        result = await run_swarm(swarm)
    return swarm, result


def _check(swarm: Any, result: Any, scripted: ScriptedSwarm, log: EventLog, names: tuple[str, ...] = NAMES) -> None:
    # The oracle and the script check that _run makes, for a run made by _run_unchecked.
    assert_event_invariants(result, names, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


def _request_tokens(call: Any) -> int:
    # What a provider would count as this request's prompt, at four characters per token: the system string, the goal, the history and the tool declarations.
    sent = call.system + call.prompt + json.dumps(call.messages, ensure_ascii=False) + json.dumps(call.tool_schemas) + json.dumps(call.tool_descriptions)
    return math.ceil(len(sent) / 4)


def _next_own(events: Any, event: Any) -> Any:
    # The first event after `event` that names the same agent.
    return next(item for item in events[event.sequence :] if item.agent == event.agent)


def _is_summary(message: dict[str, Any], text: str) -> bool:
    # INV-34: an assistant message that opens with the prefix leaf and ends with the summarizer's text.
    content = str(message.get("content") or "")
    return message.get("role") == "assistant" and content.startswith(prompt_text("compaction_summary_prefix").strip()) and content.rstrip().endswith(text)


def _write_parts(tmp_path: Path, count: int, chars: int) -> None:
    # Files part1.txt to part<count>.txt in a new workplace, each one line: a numbered mark and `chars` more characters.
    root = workplace_path(tmp_path)
    root.mkdir()
    for n in range(1, count + 1):
        (root / f"part{n}.txt").write_text(f"PART-{n}-" + "r" * chars, encoding="utf-8", newline="")


def _gemini_builder() -> dict[str, Any]:
    # The build_swarm fields that make builder a Gemini member beside an OpenAI tester.
    return {"agents": (member("builder", provider="gemini", model_name=GEMINI_MODEL), member("tester")), "api_keys": (FAKE_OPENAI_KEY, FAKE_GEMINI_KEY)}


def _is_side_call(call: Any) -> bool:
    # A compaction summary side call is the call whose system string is the summarizer leaf.
    return template_regex(prompt_text("compaction_summarizer_prompt")).search(call.system) is not None


@pytest.mark.asyncio
async def test_a_compact_call_summarizes_only_the_older_history_and_mail_follows_the_summary(tmp_path: Path) -> None:
    """AC-16, INV-30, INV-33, INV-34, INV-35: builder reads two files, then calls compact with a focus while tester's message waits; one side call gets the summarizer leaf with the focus, no history, and a transcript holding the older read only; the next call carries the summary, the newer read and the compact call verbatim, then the inbox; compaction records trigger tool, the focus, the measured context and two dropped messages."""
    from vidbyte.lib.enums import AgentSwarmCompactionTrigger

    _setup(tmp_path)
    log = EventLog()
    entered, tester_sent = Signal("builder's third call"), log.signal(SENT, "tester")
    third = observe(lambda call: entered.set(), after(tester_sent, compact(FOCUS, usage={"input_tokens": 1234, "output_tokens": 2})))
    scripted = ScriptedSwarm(
        {
            "builder": [READ_ONE, READ_TWO, third, reply(SUMMARY, usage={"input_tokens": 500, "output_tokens": 50}), reply("Builder done.")],
            "tester": [after(entered, send("builder", NOTE)), reply("Tester done.")],
        }
    )
    result = await _run(tmp_path, scripted, log)

    before, side, after_call = scripted.calls_by("builder")[2:5]
    assert side.messages == [] and template_regex(prompt_text("compaction_summarizer_prompt")).search(side.system) and FOCUS in side.system
    assert MARK_ONE in side.prompt and MARK_TWO not in seen_text(side)
    assert _is_summary(after_call.messages[0], SUMMARY), after_call.messages[0]
    assert after_call.messages[1:3] == before.messages[2:4]
    assert after_call.messages[4]["role"] == "tool" and template_regex(prompt_text("compact_requested")).search(after_call.messages[4]["content"])
    assert after_call.messages[5]["role"] == "user" and NOTE in after_call.messages[5]["content"] and len(after_call.messages) == 6
    side_called = of_kind(result.events, MODEL_CALLED, "builder")[3]
    assert (side_called.input_tokens, side_called.output_tokens, side_called.model_calls) == (500, 50, 3)
    compaction = _next_own(result.events, side_called)
    assert (compaction.kind.value, compaction.compaction_trigger, compaction.text) == (COMPACTION, AgentSwarmCompactionTrigger.TOOL, FOCUS)
    assert (compaction.input_tokens, compaction.messages_dropped) == (1234, 2)
    assert _next_own(result.events, compaction).kind.value == DELIVERED, describe(result.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("below", [0, 1], ids=["at-the-trigger", "one-below"])
async def test_a_measured_context_at_the_trigger_compacts_automatically_and_one_below_does_not(tmp_path: Path, below: int) -> None:
    """AC-17, INV-32: when builder's last reported input_tokens equals AGENT_SWARM_COMPACTION_TRIGGER_TOKENS, its next tool iteration compacts with trigger auto, a blank text and that measured value; one token less compacts nothing and the next call carries the full history."""
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TRIGGER_TOKENS as TRIGGER
    from vidbyte.lib.enums import AgentSwarmCompactionTrigger

    _setup(tmp_path)
    measured = TRIGGER - below
    second = tool_call("read_lines", {"path": "newer.txt"}, usage={"input_tokens": measured, "output_tokens": 2})
    side = [reply(SUMMARY)] if not below else []
    scripted = ScriptedSwarm({"builder": [READ_ONE, second, *side, reply("Builder done.")], "tester": [reply("Tester done.")]})
    result = await _run(tmp_path, scripted, EventLog())

    last = scripted.last_call("builder")
    if below:
        assert of_kind(result.events, COMPACTION) == [] and len(last.messages) == 4
    else:
        compaction = only(result.events, COMPACTION, "builder")
        assert (compaction.compaction_trigger, compaction.text, compaction.input_tokens, compaction.messages_dropped) == (AgentSwarmCompactionTrigger.AUTO, "", TRIGGER, 2)
        assert _is_summary(last.messages[0], SUMMARY) and len(last.messages) == 3


@pytest.mark.asyncio
async def test_a_pending_request_and_the_trigger_in_one_iteration_compact_once(tmp_path: Path) -> None:
    """AC-17, INV-31: one response holds a read and a compact call and reports a context at the trigger; that iteration makes one side call and records one compaction with trigger tool."""
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TRIGGER_TOKENS as TRIGGER
    from vidbyte.lib.enums import AgentSwarmCompactionTrigger

    _setup(tmp_path)
    both = calls(READ_TWO, compact("both"), usage={"input_tokens": TRIGGER, "output_tokens": 2})
    scripted = ScriptedSwarm({"builder": [READ_ONE, both, reply(SUMMARY), reply("Builder done.")], "tester": [reply("Tester done.")]})
    result = await _run(tmp_path, scripted, EventLog())

    compaction = only(result.events, COMPACTION, "builder")
    assert (compaction.compaction_trigger, compaction.text, compaction.messages_dropped) == (AgentSwarmCompactionTrigger.TOOL, "both", 2)
    assert len(scripted.calls_by("builder")) == 4


@pytest.mark.asyncio
async def test_anthropic_context_is_measured_as_all_three_input_buckets(tmp_path: Path) -> None:
    """INV-32, INV-22, EC-35: an Anthropic member whose billed input_tokens is far below the trigger but whose input, cache-write and cache-read buckets sum to it compacts automatically; model_called keeps the billed input and the cache reads, and compaction records the three-bucket total."""
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TRIGGER_TOKENS as TRIGGER
    from vidbyte.lib.enums import AgentSwarmCompactionTrigger

    _setup(tmp_path)
    usage = {"input_tokens": 1_000, "cache_creation_input_tokens": 2_000, "cache_read_input_tokens": TRIGGER - 3_000, "output_tokens": 5}
    second = tool_call("read_lines", {"path": "newer.txt"}, usage=usage)
    scripted = ScriptedSwarm({"builder": [READ_ONE, second, reply(SUMMARY), reply("Builder done.")], "tester": [reply("Tester done.")]})
    agents = (member("builder", provider="anthropic", model_name=ANTHROPIC_MODEL), member("tester"))
    result = await _run(tmp_path, scripted, EventLog(), agents=agents, api_keys=(FAKE_OPENAI_KEY, FAKE_ANTHROPIC_KEY))

    billed = of_kind(result.events, MODEL_CALLED, "builder")[1]
    assert (billed.input_tokens, billed.cached_tokens) == (1_000, TRIGGER - 3_000)
    compaction = only(result.events, COMPACTION, "builder")
    assert (compaction.compaction_trigger, compaction.input_tokens) == (AgentSwarmCompactionTrigger.AUTO, TRIGGER)
    assert _is_summary(scripted.last_call("builder").messages[0], SUMMARY)


@pytest.mark.asyncio
async def test_a_gemini_member_at_the_trigger_compacts_its_parts_history_through_one_summary_call(tmp_path: Path) -> None:
    """INV-32, INV-33 (spec r4, S4 R-2), AC-17: a Gemini member's history is Gemini's own shape (a model turn of functionCall parts, then a user turn of functionResponse parts, with no content key), and its second response reports promptTokenCount at AGENT_SWARM_COMPACTION_TRIGGER_TOKENS; counting whole messages, the newer read fits the target and both reads do not, so one summary side call gets the older read only; one compaction (auto, "", the trigger, two messages) is recorded, and the next call carries the summary, then the newer call and result."""
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TRIGGER_TOKENS as TRIGGER
    from vidbyte.lib.enums import AgentSwarmCompactionTrigger

    _setup(tmp_path)
    log = EventLog()
    second = tool_call("read_lines", {"path": "newer.txt"}, usage={"input_tokens": TRIGGER, "output_tokens": 2})
    scripted = ScriptedSwarm({"builder": [READ_ONE, second, reply(SUMMARY), reply("Builder done.")], "tester": [reply("Tester done.")]})
    agents = (member("builder", provider="gemini", model_name=GEMINI_MODEL), member("tester"))
    swarm, result = await _run_unchecked(tmp_path, scripted, log, agents=agents, api_keys=(FAKE_OPENAI_KEY, FAKE_GEMINI_KEY))

    # The read reached the model as Gemini parts, so an estimate of the content key alone counts none of it.
    first_read = scripted.calls_by("builder")[1]
    assert [(message["role"], sorted(message)) for message in first_read.messages] == [("model", ["parts", "role"]), ("user", ["parts", "role"])]
    assert MARK_ONE in json.dumps(first_read.messages[1]["parts"])
    compactions = [(event.compaction_trigger, event.text, event.input_tokens, event.messages_dropped) for event in of_kind(result.events, COMPACTION, "builder")]
    assert compactions == [(AgentSwarmCompactionTrigger.AUTO, "", TRIGGER, 2)], describe(result.events)
    side, last = scripted.calls_by("builder")[2:4]
    assert side.messages == [] and template_regex(prompt_text("compaction_summarizer_prompt")).search(side.system)
    assert MARK_ONE in side.prompt and MARK_TWO not in seen_text(side)
    assert _is_summary(last.messages[0], SUMMARY) and [message["role"] for message in last.messages] == ["assistant", "model", "user"]
    assert MARK_TWO in json.dumps(last.messages[2]["parts"]) and MARK_ONE not in seen_text(last)
    _check(swarm, result, scripted, log)


@pytest.mark.asyncio
async def test_an_openai_history_of_write_calls_only_compacts_at_the_trigger(tmp_path: Path) -> None:
    """INV-32, INV-33 (spec r4, S4 R-2), AC-17: builder's history is three write_text calls of sixty thousand characters each, whose text sits in the call turns' tool_calls arguments with content None while each result is one short line; the third response reports the trigger; counting whole messages, the third write fits the target and the second does not, so three messages are kept, which the strategy rounds up to the two newest whole groups, and one summary side call gets the first write only; one compaction (auto, "", the trigger, two messages) is recorded, and the next call carries the summary, then the second and third writes verbatim."""
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TRIGGER_TOKENS as TRIGGER
    from vidbyte.lib.enums import AgentSwarmCompactionTrigger

    log = EventLog()
    at_trigger = {"input_tokens": TRIGGER, "output_tokens": 2}
    writes = [tool_call("write_text", {"path": f"part{n}.py", "content": mark + str(n) * 60_000}, usage=at_trigger if n == 2 else None) for n, mark in enumerate(WRITE_MARKS)]
    scripted = ScriptedSwarm({"builder": [*writes, reply(SUMMARY), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm, result = await _run_unchecked(tmp_path, scripted, log)

    # Every call turn carries its text only in tool_calls, and every result is one short line, so an estimate of content alone sees almost nothing.
    third = scripted.calls_by("builder")[2]
    assert [message["role"] for message in third.messages] == ["assistant", "tool", "assistant", "tool"]
    assert all(message["content"] is None and len(message["tool_calls"]) == 1 for message in third.messages[::2])
    assert all(len(message["content"]) < 1_000 for message in third.messages[1::2]), [len(message["content"]) for message in third.messages[1::2]]
    compactions = [(event.compaction_trigger, event.text, event.input_tokens, event.messages_dropped) for event in of_kind(result.events, COMPACTION, "builder")]
    assert compactions == [(AgentSwarmCompactionTrigger.AUTO, "", TRIGGER, 2)], describe(result.events)
    side, after_call = scripted.calls_by("builder")[3:5]
    assert side.messages == [] and template_regex(prompt_text("compaction_summarizer_prompt")).search(side.system)
    assert WRITE_MARKS[0] in side.prompt and WRITE_MARKS[1] not in seen_text(side) and WRITE_MARKS[2] not in seen_text(side)
    assert _is_summary(after_call.messages[0], SUMMARY) and after_call.messages[1:3] == third.messages[2:4] and len(after_call.messages) == 5
    assert WRITE_MARKS[2] in json.dumps(after_call.messages[3]) and WRITE_MARKS[0] not in seen_text(after_call)
    _check(swarm, result, scripted, log)


@pytest.mark.asyncio
async def test_automatic_compaction_waits_for_a_target_of_new_history_and_a_compact_request_does_not(tmp_path: Path) -> None:
    """INV-32, D-12 (spec r4, S4 R-6), INV-31: the goal alone is over AGENT_SWARM_COMPACTION_TRIGGER_TOKENS and compaction never touches it (INV-4), and every loop call reports the size of the request it carried, so the measured context is at the trigger on every call; builder reads one 30,000-character file per iteration, about 7,500 estimated tokens, so three reads stay under AGENT_SWARM_COMPACTION_TARGET_TOKENS and four pass it, and the response of iteration 6 also calls compact. Nothing older exists before iteration 4, so the first compaction is iteration 4's (auto); iteration 6's request compacts at once (tool) although only two reads came since; each automatic compaction after it waits for four more reads (iterations 10 and 14). Each records the measured context of its own iteration's call and the messages it summarized."""
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TARGET_TOKENS as TARGET
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TRIGGER_TOKENS as TRIGGER
    from vidbyte.lib.enums import AgentSwarmCompactionTrigger

    # One read is a quarter of its characters in tokens: three stay under the target and four pass it, each by thousands of tokens.
    reads, request_at, part_chars = 14, 6, 30_000
    assert 3 * part_chars // 4 < TARGET < 4 * part_chars // 4
    root = workplace_path(tmp_path)
    root.mkdir()
    for n in range(1, reads + 1):
        (root / f"part{n}.txt").write_text(f"PART-{n}-" + "r" * part_chars, encoding="utf-8", newline="")
    goal = "Read every part file in order. " + "g" * (4 * TRIGGER + 12_000)
    summarizer = template_regex(prompt_text("compaction_summarizer_prompt"))
    measured: list[int] = []
    side_after: list[int] = []

    def builder(call: Any) -> Any:
        # A summary side call is answered with the summary; a loop call reports what it carried and reads the next part.
        if summarizer.search(call.system):
            side_after.append(len(measured))
            return reply(SUMMARY)
        measured.append(_request_tokens(call))
        usage = {"input_tokens": measured[-1], "output_tokens": 20}
        n = len(measured)
        if n > reads:
            return reply("Builder done.", usage=usage)
        read = tool_call("read_lines", {"path": f"part{n}.txt"}, usage=usage)
        return calls(read, compact(), usage=usage) if n == request_at else read

    log = EventLog()
    scripted = ScriptedSwarm({"tester": [reply("Tester done.")]}, behaviours={"builder": builder})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm, goal)

    auto, tool = AgentSwarmCompactionTrigger.AUTO, AgentSwarmCompactionTrigger.TOOL
    assert len(measured) == reads + 1 and min(measured) >= TRIGGER, measured
    assert side_after == [4, 6, 10, 14], f"summary side calls followed loop calls {side_after}"
    compactions = of_kind(result.events, COMPACTION, "builder")
    assert [(event.compaction_trigger, event.input_tokens, event.messages_dropped) for event in compactions] == [
        (auto, measured[3], 2),
        (tool, measured[5], 5),
        (auto, measured[9], 10),
        (auto, measured[13], 9),
    ], describe(result.events)
    assert of_kind(result.events, TRIMMED) == [] and of_kind(result.events, MODEL_ERROR) == []
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_gemini_member_compacts_again_each_time_its_parts_history_grows_by_the_target(tmp_path: Path) -> None:
    """INV-32, INV-33 (S5 re-review R-20), INV-36: a Gemini member's provider reports promptTokenCount at AGENT_SWARM_COMPACTION_TRIGGER_TOKENS on every call, and builder reads one 30,000-character file per iteration, about 7,500 estimated tokens held only in parts. Nothing older exists before iteration 4, so the first compaction is iteration 4's; each later automatic compaction waits until the whole-message estimate of the parts history has grown by AGENT_SWARM_COMPACTION_TARGET_TOKENS, four more reads, so iterations 8 and 12 compact again and the 90,000-token trim never fires."""
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TARGET_TOKENS as TARGET
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TRIGGER_TOKENS as TRIGGER
    from vidbyte.lib.enums import AgentSwarmCompactionTrigger

    # Three reads stay under the target and four pass it, each by thousands of tokens.
    reads, part_chars = 14, 30_000
    assert 3 * part_chars // 4 < TARGET < 4 * part_chars // 4
    _write_parts(tmp_path, reads, part_chars)
    at_trigger = {"input_tokens": TRIGGER, "output_tokens": 2}
    loop: list[Any] = []
    side_after: list[int] = []

    def builder(call: Any) -> Any:
        # A summary side call is answered with the summary; a loop call reads the next part and reports the trigger.
        if _is_side_call(call):
            side_after.append(len(loop))
            return reply(SUMMARY)
        loop.append(call)
        if len(loop) > reads:
            return reply("Builder done.", usage=at_trigger)
        return tool_call("read_lines", {"path": f"part{len(loop)}.txt"}, usage=at_trigger)

    log = EventLog()
    scripted = ScriptedSwarm({"tester": [reply("Tester done.")]}, behaviours={"builder": builder})
    swarm, result = await _run_unchecked(tmp_path, scripted, log, **_gemini_builder())

    # The reads reached the model as parts with no content key, so an estimate of content alone never sees the history grow.
    assert [(message["role"], sorted(message)) for message in loop[1].messages] == [("model", ["parts", "role"]), ("user", ["parts", "role"])]
    assert "PART-1-" in json.dumps(loop[1].messages[1]["parts"])
    assert side_after == [4, 8, 12], f"summary side calls followed loop calls {side_after}"
    auto = AgentSwarmCompactionTrigger.AUTO
    compactions = [(event.compaction_trigger, event.text, event.input_tokens, event.messages_dropped) for event in of_kind(result.events, COMPACTION, "builder")]
    assert compactions == [(auto, "", TRIGGER, 2), (auto, "", TRIGGER, 9), (auto, "", TRIGGER, 9)], describe(result.events)
    assert of_kind(result.events, TRIMMED) == [] and of_kind(result.events, MODEL_ERROR) == []
    _check(swarm, result, scripted, log)


@pytest.mark.asyncio
async def test_a_gemini_member_whose_provider_reports_no_usage_compacts_when_its_estimate_reaches_the_trigger(tmp_path: Path) -> None:
    """INV-32, INV-33 (S5 re-review R-20), EC-8: a Gemini member whose provider reports no usage is measured by the whole-message estimate of its parts history. Builder reads five 60,000-character files, about 15,000 estimated tokens each, so the estimate after four reads is under AGENT_SWARM_COMPACTION_TRIGGER_TOKENS and after five it is over; iteration 5 makes the one summary side call, keeps the newest read, and records compaction (auto, "", the estimate of the history at that check, eight messages)."""
    from vidbyte.agents.agent_swarm.member import AgentSwarmMemberRuntime
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TRIGGER_TOKENS as TRIGGER
    from vidbyte.lib.enums import AgentSwarmCompactionTrigger

    reads, part_chars = 5, 60_000
    assert (reads - 1) * part_chars // 4 < TRIGGER < reads * part_chars // 4
    _write_parts(tmp_path, reads, part_chars)
    loop: list[Any] = []
    side_after: list[int] = []

    def builder(call: Any) -> Any:
        # No response reports usage, the summary's included; a loop call reads the next part.
        if _is_side_call(call):
            side_after.append(len(loop))
            return reply(SUMMARY, usage={})
        loop.append(call)
        if len(loop) > reads:
            return reply("Builder done.", usage={})
        return tool_call("read_lines", {"path": f"part{len(loop)}.txt"}, usage={})

    log = EventLog()
    scripted = ScriptedSwarm({"tester": [reply("Tester done.")]}, behaviours={"builder": builder})
    swarm, result = await _run_unchecked(tmp_path, scripted, log, **_gemini_builder())

    # The reads reached the model as parts, and builder's provider reported nothing, so its model_called events carry zeros.
    assert [(message["role"], sorted(message)) for message in loop[1].messages] == [("model", ["parts", "role"]), ("user", ["parts", "role"])]
    assert {(event.input_tokens, event.output_tokens) for event in of_kind(result.events, MODEL_CALLED, "builder")} == {(0, 0)}
    assert side_after == [5], f"summary side calls followed loop calls {side_after}"
    # The history at iteration 5's check is the history sent on loop call 5 plus the read it kept, which loop call 6 carries after the summary.
    estimate = AgentSwarmMemberRuntime._estimate
    checked = loop[4].messages + loop[5].messages[1:]
    compactions = [(event.compaction_trigger, event.text, event.input_tokens, event.messages_dropped) for event in of_kind(result.events, COMPACTION, "builder")]
    assert compactions == [(AgentSwarmCompactionTrigger.AUTO, "", estimate(checked), 8)], describe(result.events)
    assert _is_summary(loop[5].messages[0], SUMMARY) and len(loop[5].messages) == 3
    # The member's estimate counts every read's characters, and four reads were not enough.
    assert estimate(loop[4].messages) < TRIGGER and estimate(checked) >= reads * part_chars // 4, (estimate(loop[4].messages), estimate(checked))
    _check(swarm, result, scripted, log)


@pytest.mark.asyncio
async def test_the_summary_call_tokens_are_added_to_the_members_tokens_used(tmp_path: Path) -> None:
    """INV-35 (S4 R-7): builder's second response reports the trigger, so that iteration compacts through one summary side call reporting 1,000 input and 500 output tokens; builder's reply metadata tokens_used is its three loop calls' input plus output plus the side call's 1,500, and tester's is its one call's."""
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_COMPACTION_TRIGGER_TOKENS as TRIGGER

    _setup(tmp_path)
    at_trigger = {"input_tokens": TRIGGER, "output_tokens": 2}
    side_usage = {"input_tokens": 1_000, "output_tokens": 500}
    second = tool_call("read_lines", {"path": "newer.txt"}, usage=at_trigger)
    scripted = ScriptedSwarm({"builder": [READ_ONE, second, reply(SUMMARY, usage=side_usage), reply("Builder done.")], "tester": [reply("Tester done.")]})
    result = await _run(tmp_path, scripted, EventLog())

    assert only(result.events, COMPACTION, "builder").messages_dropped == 2
    # None of these usages reports total_tokens, so each call counts its input plus its output.
    loop = sum(usage["input_tokens"] + usage["output_tokens"] for usage in (DEFAULT_USAGE, at_trigger, DEFAULT_USAGE))
    side = side_usage["input_tokens"] + side_usage["output_tokens"]
    used = {item.sender: item.metadata["tokens_used"] for item in result.replies}
    assert used == {"builder": loop + side, "tester": DEFAULT_USAGE["input_tokens"] + DEFAULT_USAGE["output_tokens"]}, used


@pytest.mark.asyncio
async def test_a_failed_summary_keeps_the_history_delivers_mail_and_fails_nobody(tmp_path: Path) -> None:
    """AC-18, EC-25, INV-35: the summary side call raises a provider error; one model_error "<Type>: <message>" is recorded, no compaction, the next call carries the whole history unchanged followed by tester's message, and builder keeps running to a normal end."""
    from vidbyte import AgentSwarmStopReason

    _setup(tmp_path)
    log = EventLog()
    entered, tester_sent = Signal("builder's third call"), log.signal(SENT, "tester")
    error = provider_error("openai returned 503: summary failed")
    scripted = ScriptedSwarm(
        {
            "builder": [READ_ONE, READ_TWO, observe(lambda call: entered.set(), after(tester_sent, compact(FOCUS))), fail(error), reply("Builder done.")],
            "tester": [after(entered, send("builder", NOTE)), reply("Tester done.")],
        }
    )
    result = await _run(tmp_path, scripted, log)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    model_error = only(result.events, MODEL_ERROR, "builder")
    assert re.fullmatch(r"\w+: [\s\S]+", model_error.text) and str(error) in model_error.text, model_error.text
    assert of_kind(result.events, COMPACTION) == [] and of_kind(result.events, FAILED) == []
    before, last = scripted.calls_by("builder")[2], scripted.calls_by("builder")[4]
    assert last.messages[:4] == before.messages and [m["role"] for m in last.messages[4:]] == ["assistant", "tool", "user"]
    assert NOTE in last.messages[-1]["content"]
    assert model_error.sequence < only(result.events, DELIVERED, "builder").sequence
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done."), ("tester", "Tester done.")]


@pytest.mark.asyncio
async def test_a_compact_request_with_nothing_older_changes_nothing_and_is_consumed(tmp_path: Path) -> None:
    """EC-21, INV-33: a compact call as builder's first act finds a single provider group, so no side call and no compaction happen; the request is consumed, so the later iteration over a long history does not compact either."""
    _setup(tmp_path)
    scripted = ScriptedSwarm({"builder": [compact(), READ_ONE, READ_TWO, reply("Builder done.")], "tester": [reply("Tester done.")]})
    result = await _run(tmp_path, scripted, EventLog())

    assert of_kind(result.events, COMPACTION) == []
    builder_calls = scripted.calls_by("builder")
    assert [len(call.messages) for call in builder_calls] == [0, 2, 4, 6]
    assert builder_calls[1].messages[1]["name"] == "compact"


@pytest.mark.asyncio
async def test_two_compact_calls_in_one_response_compact_once_with_the_last_focus(tmp_path: Path) -> None:
    """EC-22, INV-31: two compact calls in one response give two tool_called events and one compaction whose text, and the summarizer's instruction, carry the second focus only."""
    _setup(tmp_path)
    twice = calls(compact("first focus"), compact("second focus"))
    scripted = ScriptedSwarm({"builder": [READ_ONE, READ_TWO, twice, reply(SUMMARY), reply("Builder done.")], "tester": [reply("Tester done.")]})
    result = await _run(tmp_path, scripted, EventLog())

    assert [event.tool_name for event in of_kind(result.events, TOOL_CALLED, "builder")].count("compact") == 2
    assert only(result.events, COMPACTION, "builder").text == "second focus"
    side = scripted.calls_by("builder")[3]
    assert "second focus" in side.system and "first focus" not in side.system


@pytest.mark.asyncio
async def test_a_request_made_with_isdone_waits_for_the_next_iteration_after_the_wake(tmp_path: Path) -> None:
    """EC-23, INV-30: compact called in the same response as isDone is still pending when builder parks; after tester's message wakes it, its first tool iteration compacts with the focus, after agent_woke."""
    from vidbyte.lib.enums import AgentSwarmCompactionTrigger

    _setup(tmp_path)
    log = EventLog()
    builder_idle = log.signal(IDLE, "builder")
    scripted = ScriptedSwarm(
        {
            "builder": [READ_ONE, READ_TWO, calls(compact(FOCUS), finish("First pass.")), tool_call("read_lines", {"path": "missing.txt"}), reply(SUMMARY), reply("Builder done.")],
            "tester": [after(builder_idle, send("builder", NOTE)), reply("Tester done.")],
        }
    )
    result = await _run(tmp_path, scripted, log)

    compaction = only(result.events, COMPACTION, "builder")
    assert (compaction.compaction_trigger, compaction.text) == (AgentSwarmCompactionTrigger.TOOL, FOCUS)
    assert only(result.events, WOKE, "builder").sequence < compaction.sequence
    assert _is_summary(scripted.last_call("builder").messages[0], SUMMARY)


@pytest.mark.asyncio
async def test_a_blank_summary_still_compacts_to_the_prefix(tmp_path: Path) -> None:
    """EC-24, INV-34: a summarizer that returns blank text still records compaction, and the summary message holds the prefix leaf only."""
    _setup(tmp_path)
    scripted = ScriptedSwarm({"builder": [READ_ONE, READ_TWO, compact(), reply(""), reply("Builder done.")], "tester": [reply("Tester done.")]})
    result = await _run(tmp_path, scripted, EventLog())

    assert only(result.events, COMPACTION, "builder").messages_dropped == 2
    summary = scripted.last_call("builder").messages[0]
    assert summary["role"] == "assistant" and str(summary["content"]).strip() == prompt_text("compaction_summary_prefix").strip()


@pytest.mark.asyncio
async def test_a_side_call_that_reaches_the_budget_completes_its_compaction_and_stops_the_swarm(tmp_path: Path) -> None:
    """EC-6, INV-15, INV-35: the summary side call's 1,000 tokens reach max_tokens; its model_called is followed by swarm_stopping, builder's compaction is still recorded, and builder ends agent_released without another model call."""
    from vidbyte import AgentSwarmStopReason

    _setup(tmp_path)
    log = EventLog()
    # The scripted runner never suspends, so the side call waits for tester's turn to end; otherwise the stop would refuse tester's first call.
    side = after(log.signal(IDLE, "tester"), reply(SUMMARY, usage={"input_tokens": 900, "output_tokens": 100}))
    scripted = ScriptedSwarm({"builder": [READ_ONE, READ_TWO, compact(), side], "tester": [reply("Tester done.")]})
    result = await _run(tmp_path, scripted, log, max_tokens=1_000)

    assert result.stop_reason is AgentSwarmStopReason.MAX_TOKENS, describe(result.events)
    side_called = of_kind(result.events, MODEL_CALLED, "builder")[3]
    assert result.events[side_called.sequence].kind.value == STOPPING
    compaction = _next_own(result.events, side_called)
    assert compaction.kind.value == COMPACTION and _next_own(result.events, compaction).kind.value == RELEASED, describe(result.events)


def test_the_summarizer_prompt_names_the_ten_sections_in_order() -> None:
    """INV-34: the summarizer leaf names IDENTITY, PEERS, GOAL, MESSAGES RECEIVED, MESSAGES SENT, PROMISES TO PEERS, FILES CHANGED, WORK IN PROGRESS, DECISIONS and NEXT STEPS, in that order, and holds the focus field."""
    text = prompt_text("compaction_summarizer_prompt")
    positions = [re.search(rf"\b{re.escape(section)}\b", text) for section in SECTIONS]
    assert all(positions), [section for section, found in zip(SECTIONS, positions, strict=True) if not found]
    starts = [found.start() for found in positions if found]
    assert starts == sorted(starts), "the ten sections are out of order"
    assert "{focus}" in text
