"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_economy.py

PURPOSE: Proves the InfiniteMemory wiring of spec infinite-memory-context-economy items 1, 2, 3, 4 and 5: every agent reads in 200-line windows (and the setting validates and reaches the tool), every agent masks older grep/read_lines/search_memory outputs first and then trims with the low watermark, the workspace grep is smart-case with no context lines, the masking-then-trim pair moves its cut at most once per S tokens of growth (and twice per masking dip), and passed or fixed cards come back compact while every other card stays whole.
ROLE IN CODEBASE: Economy layer of tests/features/infinite_memory_agent/. Runs the root and pairs through ScriptedTree (the model is the only fake) and drives the root's own middleware objects directly for the growth sequences, as spec section 13 allows.
ARCHITECTURE NOTE: Masking is observed in the messages each model call receives, which ScriptedTree records after middleware. The middleware order (INV-0.4) is proven by behavior: each agent's middleware tuple, read from the BaseAgent objects ScriptedTree kept by name, masks a synthetic history with the leaf placeholder and trims 182 messages of 500 tokens to exactly the 132 INV-4.2 keeps (main keeps 180). Cards are compared with whole strings rebuilt from the journal's card and the result_card leaf, as main renders them.
FUNCTION INVENTORY: _lines_note / _window_footer build read cases; _view runs one middleware hook; _group / _first_kept / _grow build and read growth sequences; _compact / _full rebuild cards. Tests: AC-1.6, NFR-1.1; AC-1.5, FR-1.3; FR-1.3 every agent and the retriever; AC-2.1; AC-2.2, EC-2.1; AC-2.4; INV-0.4, INV-4.5, FR-2.2, FR-4.2, NFR-2.1; AC-3.1, AC-3.2, INV-3.4, NFR-3.1; AC-4.4; AC-4.5, EC-4.3; AC-5.1, AC-5.2, INV-5.1, INV-5.2, INV-5.4, EC-5.1, EC-5.2; AC-5.3, INV-5.3.
COMMON MODIFICATION PATTERNS: Add an agent-level case as a ScriptedTree script plus whole-string expectations; add a growth case through _grow.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not build the middleware yourself; read it from the agents the feature built. 3. Do not pin the placeholder's wording; it is the masked_output leaf.
KNOWN EDGE CASES: The growth sequences use one assistant narration of about 1,500 tokens per call so N passes 90,000 tokens within about 50 appends. A first-kept message is named by its call id, because masking replaces result contents.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-context-economy/spec.md sections 6.1 (INV-0.4, INV-1.x, INV-2.x, INV-3.4, INV-4.x, INV-5.x), 6.2 (AC-1.5, AC-1.6, AC-2.x, AC-3.1, AC-3.2, AC-4.4, AC-4.5, AC-5.x), 7 (EC-2.1, EC-4.3, EC-5.x), 12.3 rows 17, 18, 22, 23.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_economy.py -q
"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    TASK,
    ScriptedTree,
    build_agent,
    finished_cards,
    generator,
    launch,
    pair_key,
    prompt_text,
    reply,
    simple_pair,
    task,
    tool_call,
    tool_result,
    tool_results,
    verifier,
    workspace_root,
)
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareHook
from vidbyte.lib.errors import ConfigurationError

LONG_LINES = [f"line {number}" for number in range(1, 1001)]
PLANS = "Plans overview\nBasic plan 49 USD\nEnterprise plan 999 USD\nContact sales\n"


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _window_footer(start: int, shown: int, total: int) -> str:
    # INV-1.2: the footer after the window's lines.
    return f"\n[lines {start}-{start + shown - 1} of {total} shown; read on with start={start + shown}]"


def _view(middleware: Any, messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    # One before_model_call on a provider-message list; no transform means the list is unchanged.
    context = MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="economy", message="go", provider_messages=tuple(messages))
    decision = asyncio.run(middleware.before_model_call(context))
    if decision.transform is None or decision.transform.provider_messages is None:
        return list(messages)
    return list(decision.transform.provider_messages)


def _pair_scripts(name: str, summary: str, review: str, generator_steps: Sequence[Any] = ()) -> dict[str, list[Any]]:
    return {generator(name): [*generator_steps, reply(summary)], verifier(name): [reply(review)]}


# ---------------------------------------------------------------- item 1: the read window


def test_every_agent_reads_a_long_note_in_a_200_line_window_with_a_footer(tmp_path: Path) -> None:
    """AC-1.6, NFR-1.1, FR-1.3: the root, a generator and its verifier each get lines 1-200 and the footer naming start=201."""
    _write(workspace_root(tmp_path), "notes/long.md", "\n".join(LONG_LINES) + "\n")
    read = tool_call("read_lines", {"path": "notes/long.md"})
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [read, launch(task("alpha")), reply("done")], generator("alpha"): [read, reply("ALPHA")], verifier("alpha"): [read, reply("ok\nVERDICT: passed")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    expected = "\n".join(LONG_LINES[:200]) + _window_footer(1, 200, 1000)
    for name in (ROOT, generator("alpha"), verifier("alpha")):
        assert tool_result(tree.calls_by(name)[1], "read_lines") == expected, name


def test_the_workspace_read_window_validates_and_reaches_read_lines(tmp_path: Path) -> None:
    """AC-1.5, INV-1.5, FR-1.3: bad values name InfiniteWorkspaceSettings.max_read_lines; the default is 200; a custom value reaches the root's read_lines."""
    from vidbyte.agents.infinite import InfiniteWorkspaceSettings
    from vidbyte.lib.constants.infinite import INFINITE_DEFAULT_MAX_READ_LINES

    root = workspace_root(tmp_path)
    for bad in (0, -1, True, 2.5, "200", None):
        with pytest.raises(ConfigurationError) as caught:
            InfiniteWorkspaceSettings(root=root, max_read_lines=bad)
        assert "InfiniteWorkspaceSettings.max_read_lines" in str(caught.value) + str(getattr(caught.value, "details", "")), bad
    assert InfiniteWorkspaceSettings(root=root).max_read_lines == INFINITE_DEFAULT_MAX_READ_LINES == 200
    _write(root, "notes/long.md", "\n".join(LONG_LINES) + "\n")
    agent = build_agent(tmp_path, workspace={"max_read_lines": 50})
    tree = ScriptedTree({ROOT: [tool_call("read_lines", {"path": "notes/long.md", "start": 101}), reply("done")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert tool_result(tree.calls_by(ROOT)[1], "read_lines") == "\n".join(LONG_LINES[100:150]) + _window_footer(101, 50, 1000)


def test_a_custom_read_window_reaches_every_agents_read_lines_including_the_retrievers(tmp_path: Path) -> None:
    """FR-1.3: with max_read_lines=50 in DELEGATED mode, the root, a generator, its verifier and the retriever each read lines 101-150."""
    retriever = f"{ROOT}/root/recall"
    _write(workspace_root(tmp_path), "notes/long.md", "\n".join(LONG_LINES) + "\n")
    read = tool_call("read_lines", {"path": "notes/long.md", "start": 101})
    recall = tool_call("recall", {"question": "What does line 120 say?", "purpose": "Quote it in the report."})
    agent = build_agent(tmp_path, workspace={"max_read_lines": 50, "recall_mode": "delegated"})
    tree = ScriptedTree(
        {
            ROOT: [read, launch(task("alpha")), recall, reply("done")],
            generator("alpha"): [read, reply("ALPHA")],
            verifier("alpha"): [read, reply("ok\nVERDICT: passed")],
            retriever: [read, reply("NOT FOUND (line 120)")],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    expected = "\n".join(LONG_LINES[100:150]) + _window_footer(101, 50, 1000)
    for name in (ROOT, generator("alpha"), verifier("alpha"), retriever):
        assert tool_result(tree.calls_by(name)[1], "read_lines") == expected, name


# ---------------------------------------------------------------- item 2: masking


def test_the_root_masks_the_two_oldest_of_five_grep_outputs_and_keeps_every_call(tmp_path: Path) -> None:
    """AC-2.1, INV-2.3, INV-2.4, INV-2.6: the sixth call sees grep outputs 1-2 as the masked_output leaf and 3-5 whole."""
    _write(workspace_root(tmp_path), "notes/plans.md", PLANS)
    patterns = ["Plans", "Basic", "Enterprise", "Contact", "USD"]
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [*(tool_call("grep", {"pattern": pattern}) for pattern in patterns), reply("done")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    calls = tree.calls_by(ROOT)
    # Each output whole, as the call right after it saw it.
    whole = [tool_result(calls[index + 1], "grep") for index in range(5)]
    assert all("notes/plans.md" in text for text in whole), whole
    final = calls[5]
    outputs = [content for name, content in tool_results(final) if name == "grep"]
    placeholder = prompt_text("masked_output")
    assert outputs == [placeholder, placeholder, *whole[2:]]
    sent = [json.loads(turn["tool_calls"][0]["function"]["arguments"])["pattern"] for turn in final.messages if turn.get("role") == "assistant" and turn.get("tool_calls")]
    assert sent == patterns, "masking changed or removed a tool call"


def test_only_read_lines_outputs_are_masked_among_launch_bash_and_remember_results(tmp_path: Path) -> None:
    """AC-2.2, INV-2.2, EC-2.1: with four read_lines results, only the oldest is masked; keep_recent + 1 launch cards, bash and remember results all stay whole."""
    from vidbyte.lib.constants.infinite import INFINITE_MASK_KEEP_RECENT

    root = workspace_root(tmp_path)
    for number in range(4):
        _write(root, f"notes/r{number}.md", f"READ-BODY-{number}\n")
    agent = build_agent(tmp_path)
    reads = [tool_call("read_lines", {"path": f"notes/r{number}.md"}) for number in range(4)]
    # One more result per out-of-scope tool than the window keeps: an unscoped window (main's tools=()) would mask the oldest of each.
    extra = INFINITE_MASK_KEEP_RECENT + 1
    names = [f"pair{number}" for number in range(extra)]
    launches = [launch(task(name)) for name in names]
    bashes = [tool_call("bash", {"command": f"echo BASH-OUTPUT-{number}"}) for number in range(extra)]
    remembers = [tool_call("remember", {"kind": "fact", "text": f"Acme lists plan {number} at {number + 40} USD"}) for number in range(extra)]
    steps = [reads[0], *launches, *bashes, *remembers, *reads[1:], reply("done")]
    pairs: dict[str, list[Any]] = {}
    for name in names:
        pairs.update(simple_pair(name, f"{name.upper()}-SUMMARY"))
    tree = ScriptedTree({ROOT: steps, **pairs})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    calls = tree.calls_by(ROOT)
    final = calls[-1]
    results = tool_results(final)
    by_name: dict[str, list[str]] = {}
    for name, content in results:
        by_name.setdefault(name, []).append(content)
    assert by_name["read_lines"] == [prompt_text("masked_output"), "READ-BODY-1", "READ-BODY-2", "READ-BODY-3"]
    for name in ("launch_subagent", "bash", "remember"):
        # Each result as the model call right after its own step saw it.
        issued = [index for index, step in enumerate(steps) if getattr(step, "name", None) == name]
        assert len(issued) == extra, name
        assert by_name[name] == [tool_result(calls[index + 1], name) for index in issued], f"a {name} result changed"


def test_masking_runs_before_the_trim_so_a_masked_view_under_the_cap_keeps_every_call(tmp_path: Path) -> None:
    """AC-2.4, INV-0.4: ten reads of about 10,000 tokens each exceed 90,000 raw; masked first, the view keeps all ten calls."""
    from vidbyte.lib.constants.infinite import INFINITE_HISTORY_MAX_TOKENS, INFINITE_MASK_KEEP_RECENT

    root = workspace_root(tmp_path)
    agent = build_agent(tmp_path)
    for number in range(10):
        _write(root, f"notes/big{number}.md", "\n".join(f"BIG{number}-{row:03d} " + "w" * 190 for row in range(200)) + "\n")
    tree = ScriptedTree({ROOT: [*(tool_call("read_lines", {"path": f"notes/big{number}.md"}) for number in range(10)), reply("done")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    final = tree.calls_by(ROOT)[-1]
    raw_chars = sum(len(tool_result(tree.calls_by(ROOT)[number + 1], "read_lines")) for number in range(10))
    assert raw_chars // 4 > INFINITE_HISTORY_MAX_TOKENS, "precondition: the unmasked outputs alone exceed the cap"
    calls = [turn for turn in final.messages if turn.get("role") == "assistant" and turn.get("tool_calls")]
    assert len(calls) == 10, "the trim dropped calls, so it ran before masking"
    outputs = [content for name, content in tool_results(final) if name == "read_lines"]
    masked = 10 - INFINITE_MASK_KEEP_RECENT
    assert outputs[:masked] == [prompt_text("masked_output")] * masked
    assert all(text.startswith(f"BIG{number}-000 ") for number, text in zip(range(masked, 10), outputs[masked:], strict=True))


def test_every_agent_masks_first_then_trims_with_the_low_watermark_then_limits_delegation(tmp_path: Path) -> None:
    """INV-0.4, INV-4.5, FR-2.2, FR-4.2, NFR-2.1: the root and a generator hold three middleware, a verifier two; each masks with the leaf and trims 91,000 tokens to 66,000."""
    from vidbyte.lib.constants.infinite import INFINITE_MASK_KEEP_RECENT
    from vidbyte.lib.util import TokenEstimate
    from vidbyte.middleware.builtins.delegation_limits import DelegationLimitsMiddleware

    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [launch(task("alpha")), reply("done")], **simple_pair("alpha", "ALPHA")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    placeholder = prompt_text("masked_output")
    assert TokenEstimate.count(placeholder) <= 60
    greps: list[dict[str, Any]] = []
    for number in range(INFINITE_MASK_KEEP_RECENT + 2):
        greps += [
            {"role": "assistant", "content": None, "tool_calls": [{"id": f"g{number}", "type": "function", "function": {"name": "grep", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": f"g{number}", "name": "grep", "content": f"GREP-{number}"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": f"b{number}", "type": "function", "function": {"name": "bash", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": f"b{number}", "name": "bash", "content": f"BASH-{number}"},
        ]
    # 182 messages of 500 tokens: M = 90,000, L = 65,000, S = 25,000, so INV-4.2 drops 50 and keeps 132 (main keeps 180).
    long_history = [{"role": "user", "content": f"{number:04d}" + "x" * 1996} for number in range(182)]
    for name, middleware, limited in ((ROOT, agent.middleware, True), (generator("alpha"), tree.agents[generator("alpha")].middleware, True), (verifier("alpha"), tree.agents[verifier("alpha")].middleware, False)):
        assert len(middleware) == (3 if limited else 2), name
        masked = _view(middleware[0], greps)
        contents = [message["content"] for message in masked if message["role"] == "tool"]
        assert contents == [placeholder, "BASH-0", placeholder, "BASH-1", "GREP-2", "BASH-2", "GREP-3", "BASH-3", "GREP-4", "BASH-4"], name
        trimmed = _view(middleware[1], long_history)
        assert trimmed == long_history[50:], f"{name}: kept {len(trimmed)} of 182"
        if limited:
            assert isinstance(middleware[2], DelegationLimitsMiddleware), name


# ---------------------------------------------------------------- item 3: workspace grep


def test_every_agents_workspace_grep_is_smart_case_with_no_context_lines(tmp_path: Path) -> None:
    """AC-3.1, AC-3.2, INV-3.4, NFR-3.1: "enterprise plan" finds the line alone; "Enterprise" matches; "ENTERPRISE" does not; the generator's grep is the same."""
    _write(workspace_root(tmp_path), "notes/plans.md", PLANS)
    agent = build_agent(tmp_path)
    tree = ScriptedTree(
        {
            ROOT: [tool_call("grep", {"pattern": "enterprise plan"}), tool_call("grep", {"pattern": "Enterprise"}), tool_call("grep", {"pattern": "ENTERPRISE"}), launch(task("alpha")), reply("done")],
            generator("alpha"): [tool_call("grep", {"pattern": "basic plan"}), reply("ALPHA")],
            verifier("alpha"): [tool_call("grep", {"pattern": "contact"}), reply("ok\nVERDICT: passed")],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    calls = tree.calls_by(ROOT)
    assert tool_result(calls[1], "grep") == "notes/plans.md:3\n3: Enterprise plan 999 USD"
    assert tool_result(calls[2], "grep") == "notes/plans.md:3\n3: Enterprise plan 999 USD"
    assert tool_result(calls[3], "grep") == "No matches found."
    assert tool_result(tree.calls_by(generator("alpha"))[1], "grep") == "notes/plans.md:2\n2: Basic plan 49 USD"
    assert tool_result(tree.calls_by(verifier("alpha"))[1], "grep") == "notes/plans.md:4\n4: Contact sales"


# ---------------------------------------------------------------- item 4: the masking-then-trim pair over growth

NARRATION = "n" * 6_000  # about 1,500 tokens per call turn
BIG_OUTPUT = "o" * 16_000  # about 4,000 tokens per read_lines result
TINY_OUTPUT = "tiny"


def _group(number: int, output: str) -> list[dict[str, Any]]:
    # One narrated read_lines call and its result, named by its call id.
    call = {"id": f"call-{number}", "type": "function", "function": {"name": "read_lines", "arguments": json.dumps({"path": f"notes/n{number}.md"})}}
    return [{"role": "assistant", "content": NARRATION, "tool_calls": [call]}, {"role": "tool", "tool_call_id": f"call-{number}", "name": "read_lines", "content": f"{number:05d}" + output}]


def _group_tokens(group: Sequence[dict[str, Any]]) -> int:
    # Tokens appended, counted as the trim's default counter does (ceil(chars / 4)) over each message's text and call.
    return sum(math.ceil(len(str(message.get("content") or "") + json.dumps(message.get("tool_calls") or "")) / 4) for message in group)


def _first_kept(view: Sequence[dict[str, Any]]) -> int:
    # The number of the first call the trimmed view still holds.
    for message in view:
        if message.get("tool_calls"):
            return int(message["tool_calls"][0]["id"].removeprefix("call-"))
    raise AssertionError("the view kept no call")


def _per_call_view(middleware: Sequence[Any], history: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    # Masking, then the trim, as the root runs them before each call.
    return _view(middleware[1], _view(middleware[0], history))


def test_with_equal_outputs_the_cut_moves_at_most_once_per_s_tokens_appended(tmp_path: Path) -> None:
    """AC-4.4, INV-4.4, NFR-4.1: from the first view that trims, the first kept message changes at most ceil(G / S) times."""
    from vidbyte.lib.constants.infinite import INFINITE_HISTORY_LOW_WATERMARK_TOKENS, INFINITE_HISTORY_MAX_TOKENS

    middleware = build_agent(tmp_path).middleware
    window = INFINITE_HISTORY_MAX_TOKENS - INFINITE_HISTORY_LOW_WATERMARK_TOKENS
    history: list[dict[str, Any]] = []
    first_trim: int | None = None
    appended_after = 0
    moves = 0
    previous: int | None = None
    for number in range(170):
        group = _group(number, BIG_OUTPUT)
        history += group
        view = _per_call_view(middleware, history)
        trimmed = len(view) < len(history)
        if first_trim is None and trimmed:
            first_trim, previous = number, _first_kept(view)
            continue
        if first_trim is not None:
            appended_after += _group_tokens(group)
            current = _first_kept(view)
            moves += int(current != previous)
            previous = current
    assert first_trim is not None, "precondition: the history never passed the cap"
    assert moves >= 2, "precondition: the sequence must move the cut more than once"
    assert moves <= math.ceil(appended_after / window), f"{moves} moves for {appended_after} tokens appended (S = {window})"


def test_one_masking_dip_moves_the_cut_back_once_and_forward_once(tmp_path: Path) -> None:
    """AC-4.5, EC-4.3, NFR-4.1: a small output that pushes a big one past the newest three lowers N below a multiple of S; the cut moves back, then forward again."""
    middleware = build_agent(tmp_path).middleware
    history: list[dict[str, Any]] = []
    number = 0
    dip_at: int | None = None
    current: int | None = None
    for number in range(200):
        history += _group(number, BIG_OUTPUT)
        view = _per_call_view(middleware, history)
        if len(view) == len(history):
            continue
        current = _first_kept(view)
        probe = _per_call_view(middleware, [*history, *_group(number + 1, TINY_OUTPUT)])
        if _first_kept(probe) < current:
            dip_at = number + 1
            break
    assert dip_at is not None and current is not None, "no append in 200 lowered N below a multiple of S"
    history += _group(dip_at, TINY_OUTPUT)
    back = _first_kept(_per_call_view(middleware, history))
    assert back < current, "the dip must move the cut back to an earlier message"
    positions = [back]
    for follow in range(dip_at + 1, dip_at + 5):
        history += _group(follow, BIG_OUTPUT)
        positions.append(_first_kept(_per_call_view(middleware, history)))
    changes = [(before, after) for before, after in zip(positions, positions[1:]) if before != after]
    assert len(changes) == 1 and changes[0][1] > back, f"expected one forward move after the dip, got {positions}"


# ---------------------------------------------------------------- item 5: card diet


def _compact(card: dict[str, Any]) -> str:
    # INV-5.1: the finished-pair line, a newline, then the summary or "-".
    from vidbyte.lib.constants.infinite import INFINITE_FINISHED_PAIR_LINE

    line = INFINITE_FINISHED_PAIR_LINE.format(name=card["name"], status=card["status"], verdict=card["verdict"], entries=", ".join(f"#{number}" for number in card["entries"]) or "-")
    return f"{line}\n{card['summary'] or '-'}"


def _full(card: dict[str, Any]) -> str:
    # INV-5.2: main's full rendering through the result_card leaf (the lists here are far below the card cap).
    return prompt_text("result_card").format(
        name=card["name"],
        key=card["key"],
        status=card["status"],
        verdict=card["verdict"],
        summary=card["summary"] or "-",
        review=card["review"] or "-",
        entries=", ".join(f"#{number}" for number in card["entries"]) or "-",
        dropped="; ".join(card["dropped"]) or "-",
        files=", ".join(card["files"]) or "-",
    )


def test_passed_and_fixed_cards_are_compact_while_failed_unchecked_and_partial_cards_stay_whole(tmp_path: Path) -> None:
    """AC-5.1, AC-5.2, INV-5.1, INV-5.2, INV-5.4, EC-5.1, EC-5.2: one batch of five; the launch result is each card's exact rendering in task order."""
    from vidbyte.agents.settings import AgentLoopSettings

    # Three iterations let alpha remember, write a note and reply, and stop slow's third grep as partial.
    agent = build_agent(tmp_path, loop=AgentLoopSettings(max_iterations=3))
    alpha_steps = [tool_call("remember", {"kind": "fact", "text": "Acme lists Pro at 49 USD per month"}), tool_call("write_note", {"path": "notes/alpha.md", "text": "Alpha detail.", "description": "Alpha detail"})]
    slow_steps = [tool_call("grep", {"pattern": pattern}) for pattern in ("list price", "discount", "annual")]
    tree = ScriptedTree(
        {
            ROOT: [launch(task("alpha"), task("beta"), task("gamma"), task("delta"), task("slow")), reply("done")],
            **_pair_scripts("alpha", "ALPHA-SUMMARY", "ALPHA-REVIEW-HIDDEN all sourced.\nVERDICT: passed", alpha_steps),
            **_pair_scripts("beta", "BETA-SUMMARY", "BETA-REVIEW-HIDDEN one price fixed.\nVERDICT: fixed"),
            **_pair_scripts("gamma", "GAMMA-SUMMARY", "GAMMA-REVIEW-SHOWN no sources.\nVERDICT: failed"),
            **_pair_scripts("delta", "DELTA-SUMMARY", "DELTA-REVIEW-SHOWN without a verdict line."),
            generator("slow"): slow_steps,
            verifier("slow"): [reply("SLOW-REVIEW-SHOWN partial work checked.\nVERDICT: passed")],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    cards = finished_cards(workspace_root(tmp_path))
    names = ("alpha", "beta", "gamma", "delta", "slow")
    verdicts = {name: (cards[pair_key(name)]["status"], cards[pair_key(name)]["verdict"]) for name in names}
    assert verdicts == {"alpha": ("done", "passed"), "beta": ("done", "fixed"), "gamma": ("done", "failed"), "delta": ("done", "unchecked"), "slow": ("partial", "passed")}
    result = tool_result(tree.calls_by(ROOT)[1], "launch_subagent")
    expected = [_compact(cards[pair_key("alpha")]), _compact(cards[pair_key("beta")]), *(_full(cards[pair_key(name)]) for name in ("gamma", "delta", "slow"))]
    assert result == "\n\n".join(expected)
    assert _compact(cards[pair_key("alpha")]) == "- alpha: done, verdict passed, entries #1\nALPHA-SUMMARY"
    for hidden in ("ALPHA-REVIEW-HIDDEN", "BETA-REVIEW-HIDDEN", "notes/alpha.md"):
        assert hidden not in result
    for shown in ("GAMMA-REVIEW-SHOWN", "DELTA-REVIEW-SHOWN", "SLOW-REVIEW-SHOWN"):
        assert shown in result
    # INV-5.4: the journal still holds the whole card.
    assert cards[pair_key("alpha")]["review"].startswith("ALPHA-REVIEW-HIDDEN") and cards[pair_key("alpha")]["files"] == ["notes/alpha.md"]


def test_a_replayed_passed_card_is_the_label_then_the_compact_card(tmp_path: Path) -> None:
    """AC-5.3, INV-5.3: relaunching a finished passed name returns the replayed label line followed by the compact card."""
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [launch(task("a")), launch(task("a")), reply("done")], **simple_pair("a", "A-SUMMARY-ONCE")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    card = finished_cards(workspace_root(tmp_path))[pair_key("a")]
    assert tool_result(tree.calls_by(ROOT)[1], "launch_subagent") == _compact(card)
    assert tool_result(tree.calls_by(ROOT)[2], "launch_subagent") == f"{prompt_text('replayed_label')}\n{_compact(card)}"
