"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_delegation.py

PURPOSE: Proves what launch_subagent promises the root and every generator: pairs in one call run at the same time, each verifier follows its own generator, the parent sees only capped cards in task order, a bad batch starts nothing, depth and role decide who may delegate, max_agents bounds the run, one failing pair never sinks its siblings, extras reach children only by name, context entries are pasted, finished names replay, and the loop's tool limits never cut a batch.
ROLE IN CODEBASE: Delegation layer of tests/features/infinite_memory_agent/ (spec AC-5..AC-8, AC-12, AC-13, AC-26, AC-28, AC-29, AC-31, AC-32, AC-35, AC-36; INV-4, INV-6..INV-13, INV-24, INV-26, INV-29, INV-30, INV-38; EC-4..EC-11, EC-38, EC-43). Exercises vidbyte/agents/infinite/launch.py through a real InfiniteMemoryAgent run.
ARCHITECTURE NOTE: Every agent in the tree is driven by one ScriptedTree routed by agent name. What the parent saw is read from the tool messages in its next model call; what happened on disk is read from the journal and entries.jsonl. Concurrency is proven with a Gate that opens only when both generators are inside a model call at once, never with timing.
FUNCTION INVENTORY: test_two_tasks_run_concurrently_and_each_verifier_follows_its_own_generator (AC-5, INV-4, INV-9, INV-12, INV-24); test_an_invalid_batch_starts_nothing_and_the_tool_stays_usable (AC-6, EC-4..EC-7, EC-38, EC-43); test_depth_cap_and_role_decide_who_holds_launch_subagent_and_drop_entry (AC-7, INV-8, INV-13, AC-17 SPARSE clause); test_a_batch_that_would_pass_max_agents_is_refused_whole (AC-8, INV-10, EC-8); test_a_failed_or_blank_generator_skips_its_verifier_and_its_sibling_still_reports (AC-12, EC-9, EC-10, INV-29); test_a_generator_stopped_by_max_iterations_is_partial_and_still_verified (AC-13, EC-11, INV-30); test_a_long_generator_reply_is_cut_in_its_card_and_the_rest_never_reaches_the_root (AC-26, INV-4, NFR-7); test_a_task_card_grants_exactly_the_extras_it_names (AC-28, AC-36, INV-6, INV-7); test_context_pastes_named_entries_and_lists_named_paths (AC-29, D-14); test_relaunching_a_finished_name_replays_its_card_without_building_agents (AC-31, INV-26); test_the_verifier_gets_the_generators_outcome_but_never_its_transcript (AC-32, INV-12); test_launch_subagent_is_exempt_from_the_tool_timeout_and_result_cap (AC-35, INV-38).
COMMON MODIFICATION PATTERNS: Add a rejected-batch case as one INVALID_BATCHES row naming the token the error must contain. Keep private markers (GEN-*-PRIVATE, VER-*-PRIVATE) unique strings so a leak check cannot match by accident.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not prove concurrency or ordering with sleeps or wall-clock time; use Gate, Signal, and ScriptedTree.events. 3. Do not assert card wording beyond the catalog templates and the field values the spec fixes.
KNOWN EDGE CASES: A runner AssertionError inside a child may be turned into a tool error by the parent, so every test ends with ScriptedTree.assert_complete, which also fails on unscripted calls. The result-card template is matched with its literal text only, so a template of bare placeholders would make renderings() weak.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-agent/spec.md sections 6.1, 6.2, 6.3, 9.2 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_delegation.py -q
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    MAP_HEADER,
    PASSED_REVIEW,
    ROOT,
    SYSTEM_PROMPT,
    TASK,
    Gate,
    ScriptedTree,
    Signal,
    after,
    build_agent,
    entry_record,
    events,
    fail,
    finished_cards,
    generator,
    int_token,
    is_error,
    journal_records,
    launch,
    observe,
    pair_key,
    prompt_text,
    read_jsonl,
    renderings,
    reply,
    seen_text,
    simple_pair,
    task,
    template_regex,
    tool_call,
    tool_result,
    tool_results,
    verifier,
    workspace_root,
    write_jsonl,
)
from vidbyte import tool
from vidbyte.lib.errors import VidbyteSdkError

MEMORY_TOOLS = {"bash", "grep", "read_lines", "remember", "write_note"}
GENERATOR_TOOLS = MEMORY_TOOLS | {"launch_subagent", "isDone"}
LEAF_GENERATOR_TOOLS = MEMORY_TOOLS | {"isDone"}
VERIFIER_TOOLS = MEMORY_TOOLS | {"drop_entry", "isDone"}


@tool(name="web_fetch")
def web_fetch(url: str) -> str:
    """Fetch a public web page and return its text."""
    return f"FETCHED:{url}"


@tool(name="calc")
def calc(expression: str) -> str:
    """Evaluate a small arithmetic expression."""
    return f"CALC:{expression}"


@tool(name="lookup")
def lookup(topic: str) -> str:
    """Look up a topic in the company wiki."""
    return f"WIKI:{topic}"


def _root_launch_result(tree: ScriptedTree, call_index: int = 1) -> str:
    """The newest launch_subagent result the root saw on its call number `call_index` (0-based)."""
    return tool_result(tree.calls_by(ROOT)[call_index], "launch_subagent")


# ---------------------------------------------------------------- AC-5


@pytest.mark.asyncio
async def test_two_tasks_run_concurrently_and_each_verifier_follows_its_own_generator(tmp_path: Path) -> None:
    """AC-5, INV-4, INV-9, INV-12, INV-24: both generators are active at once, verifiers follow their own generators, the root gets two cards in task order and nothing else."""
    agent = build_agent(tmp_path)
    both_active = Gate(2)
    beta_judged = Signal("beta's verifier gave its verdict")
    alpha_summary = "ALPHA-SUMMARY-TEXT: Acme lists Pro at 49 USD."
    beta_summary = "BETA-SUMMARY-TEXT: Globex lists Team at 59 USD."
    tree = ScriptedTree(
        {
            ROOT: [launch(task("alpha"), task("beta")), reply("ROOT-FINAL")],
            generator("alpha"): [
                after(both_active, tool_call("grep", {"pattern": "GEN-ALPHA-PRIVATE-QUERY"})),
                tool_call("remember", {"kind": "fact", "text": "Alpha staged fact ALPHA-STAGED-PRIVATE"}),
                # Alpha returns only after beta's pair is judged, so alpha finishes last although it is first in the batch.
                after(beta_judged, reply(alpha_summary)),
            ],
            verifier("alpha"): [tool_call("grep", {"pattern": "VER-ALPHA-PRIVATE-QUERY"}), reply("ALPHA-REVIEW-TEXT ok.\nVERDICT: passed")],
            generator("beta"): [
                after(both_active, tool_call("grep", {"pattern": "GEN-BETA-PRIVATE-QUERY"})),
                tool_call("remember", {"kind": "fact", "text": "Beta staged fact BETA-STAGED-PRIVATE"}),
                reply(beta_summary),
            ],
            verifier("beta"): [
                tool_call("grep", {"pattern": "VER-BETA-PRIVATE-QUERY"}),
                observe(lambda call: beta_judged.set(), reply("BETA-REVIEW-TEXT ok.\nVERDICT: passed")),
            ],
        }
    )
    with tree.install():
        answer = await agent.arun(TASK)
    tree.assert_complete()
    assert answer.content == "ROOT-FINAL"
    assert sorted(both_active.arrived) == sorted([generator("alpha"), generator("beta")])
    for name in ("alpha", "beta"):
        assert tree.position(f"{verifier(name)} call 1") > tree.position(f"{generator(name)} answered 3"), f"{name}'s verifier started before its generator returned"
    result = _root_launch_result(tree)
    assert not is_error(result)
    assert result.count(alpha_summary) == 1 and result.count(beta_summary) == 1
    assert result.index(alpha_summary) < result.index(beta_summary), "cards must come back in task order, not completion order"
    assert renderings(prompt_text("result_card"), result) == 2
    private = ("GEN-ALPHA-PRIVATE-QUERY", "GEN-BETA-PRIVATE-QUERY", "VER-ALPHA-PRIVATE-QUERY", "VER-BETA-PRIVATE-QUERY", "ALPHA-STAGED-PRIVATE", "BETA-STAGED-PRIVATE")
    for call in tree.calls_by(ROOT):
        leaked = [marker for marker in private if marker in seen_text(call)]
        assert not leaked, f"child-only text reached the root: {leaked}"
    committed = read_jsonl(workspace_root(tmp_path) / "entries.jsonl")
    assert sorted(entry["text"] for entry in committed) == ["Alpha staged fact ALPHA-STAGED-PRIVATE", "Beta staged fact BETA-STAGED-PRIVATE"]
    assert len({entry["id"] for entry in committed}) == 2, "concurrent commits must never share an id"


# ---------------------------------------------------------------- AC-6


def _no_generator(card: dict[str, Any]) -> dict[str, Any]:
    trimmed = dict(card)
    trimmed.pop("generator_prompt")
    return trimmed


INVALID_BATCHES = (
    pytest.param([task("alpha"), task("beta"), task("gamma")], ("max_parallel",), id="more-than-max-parallel"),
    pytest.param([task("alpha"), task("alpha")], ("alpha",), id="duplicate-name"),
    pytest.param([task("alpha", ver="   ")], ("verifier_prompt",), id="blank-verifier-prompt"),
    pytest.param([_no_generator(task("alpha"))], ("generator_prompt",), id="missing-generator-prompt"),
    pytest.param([task("alpha", tools=["web_fetch"])], ("web_fetch",), id="tool-the-root-lacks"),
    pytest.param([task("alpha", context=["#99"])], (99,), id="unknown-context-id"),
    pytest.param([task("alpha", context=["#40"])], (40,), id="superseded-context-id"),
    pytest.param([task("Pricing Research!")], ("Pricing Research!", r"^[a-z0-9][a-z0-9-]{0,39}$"), id="name-fails-pattern"),
    pytest.param([task("alpha", budget_share=0.5)], ("budget_share",), id="unknown-field"),
)


@pytest.mark.parametrize(("batch", "named"), INVALID_BATCHES)
def test_an_invalid_batch_starts_nothing_and_the_tool_stays_usable(tmp_path: Path, batch: list[dict[str, Any]], named: tuple[Any, ...]) -> None:
    """AC-6, INV-9, INV-11, INV-26, INV-32, EC-4..EC-7, EC-38, EC-43: the batch returns an error naming the problem, starts no agent, writes no journal record, and a valid call then works."""
    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(41, "Prices are listed in USD", supersedes=40)])
    write_jsonl(root / "superseded.jsonl", [entry_record(40, "Prices are listed in EUR")])
    agent = build_agent(tmp_path, max_parallel=2)
    tree = ScriptedTree({ROOT: [tool_call("launch_subagent", {"tasks": batch}), launch(task("ok-task")), reply("done")], **simple_pair("ok-task", "OK-TASK-SUMMARY")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    rejected = _root_launch_result(tree, 1)
    assert is_error(rejected), rejected
    assert template_regex(prompt_text("launch_rejected_prompt")).search(rejected)
    for token in named:
        pattern = int_token(token) if isinstance(token, int) else re.compile(re.escape(str(token)))
        assert pattern.search(rejected), f"the rejection does not name {token!r}: {rejected}"
    accepted = _root_launch_result(tree, 2)
    assert not is_error(accepted) and "OK-TASK-SUMMARY" in accepted
    assert tree.agents_called() == {ROOT, generator("ok-task"), verifier("ok-task")}
    records = journal_records(root)
    assert events(records) == ["run_started", "pair_started", "pair_finished", "run_finished"]
    assert records[1]["key"] == pair_key("ok-task")


# ---------------------------------------------------------------- AC-7, AC-8


def test_depth_cap_and_role_decide_who_holds_launch_subagent_and_drop_entry(tmp_path: Path) -> None:
    """AC-7, INV-6, INV-8, INV-13, AC-17 (SPARSE clause): with max_depth=2 the depth-1 generator may delegate, the depth-2 one may not, and no verifier may."""
    agent = build_agent(tmp_path, max_depth=2)
    nested = generator("a")
    tree = ScriptedTree(
        {
            ROOT: [launch(task("a")), reply("done")],
            generator("a"): [launch(task("b")), reply("A-SUMMARY")],
            verifier("a"): [reply(PASSED_REVIEW)],
            **simple_pair("b", "B-SUMMARY", parent=nested),
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert set(tree.first_call(generator("a")).tools) == GENERATOR_TOOLS
    assert set(tree.first_call(generator("b", nested)).tools) == LEAF_GENERATOR_TOOLS
    assert set(tree.first_call(verifier("a")).tools) == VERIFIER_TOOLS
    assert set(tree.first_call(verifier("b", nested)).tools) == VERIFIER_TOOLS
    assert not is_error(tool_result(tree.calls_by(generator("a"))[1], "launch_subagent"))
    assert "root/a/gen/b" in finished_cards(workspace_root(tmp_path))


def test_a_batch_that_would_pass_max_agents_is_refused_whole(tmp_path: Path) -> None:
    """AC-8, INV-10, EC-8: with max_agents=4 a first batch of two pairs runs, and one more pair is refused without starting."""
    agent = build_agent(tmp_path, max_agents=4)
    tree = ScriptedTree({ROOT: [launch(task("x"), task("y")), launch(task("z")), reply("done")], **simple_pair("x", "X-SUMMARY"), **simple_pair("y", "Y-SUMMARY")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert not is_error(_root_launch_result(tree, 1))
    refused = _root_launch_result(tree, 2)
    assert is_error(refused) and "max_agents" in refused and int_token(4).search(refused), refused
    assert tree.agents_called() == {ROOT, generator("x"), verifier("x"), generator("y"), verifier("y")}
    records = journal_records(workspace_root(tmp_path))
    assert [record["key"] for record in records if record["event"] == "pair_started"] == [pair_key("x"), pair_key("y")]


# ---------------------------------------------------------------- AC-12, AC-13


@pytest.mark.parametrize("failure", ("raises", "blank"))
def test_a_failed_or_blank_generator_skips_its_verifier_and_its_sibling_still_reports(tmp_path: Path, failure: str) -> None:
    """AC-12, EC-9, EC-10, INV-29: a generator that raises or answers blank gives a failed/unchecked card, its verifier never runs, and its sibling is done."""
    agent = build_agent(tmp_path)
    broken = fail(VidbyteSdkError("provider exploded: 503 from upstream")) if failure == "raises" else reply("   ")
    tree = ScriptedTree({ROOT: [launch(task("broken"), task("steady")), reply("done")], generator("broken"): [broken], **simple_pair("steady", "STEADY-SUMMARY")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert verifier("broken") not in tree.agents_called()
    result = _root_launch_result(tree)
    assert not is_error(result) and "STEADY-SUMMARY" in result
    cards = finished_cards(workspace_root(tmp_path))
    assert (cards[pair_key("broken")]["status"], cards[pair_key("broken")]["verdict"]) == ("failed", "unchecked")
    assert (cards[pair_key("steady")]["status"], cards[pair_key("steady")]["verdict"]) == ("done", "passed")
    if failure == "raises":
        assert cards[pair_key("broken")]["review"].strip(), "a raised error's text belongs in the card's review"


def test_a_generator_stopped_by_max_iterations_is_partial_and_still_verified(tmp_path: Path) -> None:
    """AC-13, EC-11, INV-30: a generator that hits max_iterations with non-blank content is partial, and its verifier still runs."""
    from vidbyte.agents.settings import AgentLoopSettings

    agent = build_agent(tmp_path, loop=AgentLoopSettings(max_iterations=2))
    tree = ScriptedTree(
        {
            ROOT: [launch(task("slow")), reply("done")],
            generator("slow"): [tool_call("grep", {"pattern": "list price"}), tool_call("grep", {"pattern": "discount"})],
            verifier("slow"): [reply("Partial work checked.\nVERDICT: passed")],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    card = finished_cards(workspace_root(tmp_path))[pair_key("slow")]
    assert (card["status"], card["verdict"]) == ("partial", "passed")


# ---------------------------------------------------------------- AC-26


def test_a_long_generator_reply_is_cut_in_its_card_and_the_rest_never_reaches_the_root(tmp_path: Path) -> None:
    """AC-26, INV-4, INV-12, NFR-7: summary and review are each cut to INFINITE_CARD_TEXT_MAX_TOKENS plus the marker; the root and the verifier never see the cut-off tails."""
    from vidbyte.lib.constants.infinite import INFINITE_CARD_TEXT_MAX_TOKENS, INFINITE_TRUNCATION_MARKER
    from vidbyte.lib.util import TokenEstimate

    long_summary = "SUMMARY-HEAD " + "s" * 4_970 + " SUMMARY-TAIL-NEVER-SEEN"
    long_review = "REVIEW-HEAD " + "r" * 4_000 + " REVIEW-TAIL-NEVER-SEEN\nVERDICT: passed"
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [launch(task("verbose")), reply("done")], **simple_pair("verbose", long_summary, long_review)})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    card = finished_cards(workspace_root(tmp_path))[pair_key("verbose")]
    assert card["verdict"] == "passed"
    for text, original in ((card["summary"], long_summary), (card["review"], long_review)):
        assert text.endswith(INFINITE_TRUNCATION_MARKER)
        kept = text[: -len(INFINITE_TRUNCATION_MARKER)]
        assert original.startswith(kept) and kept
        assert TokenEstimate.count(kept) <= INFINITE_CARD_TEXT_MAX_TOKENS
    for call in tree.calls_by(ROOT):
        assert "SUMMARY-TAIL-NEVER-SEEN" not in seen_text(call) and "REVIEW-TAIL-NEVER-SEEN" not in seen_text(call)
    assert "SUMMARY-HEAD" in _root_launch_result(tree)
    assert "SUMMARY-TAIL-NEVER-SEEN" not in seen_text(tree.first_call(verifier("verbose"))), "the verifier gets the capped summary"


# ---------------------------------------------------------------- AC-28, AC-36


def test_a_task_card_grants_exactly_the_extras_it_names(tmp_path: Path) -> None:
    """AC-28, AC-36, INV-6, INV-7: the root holds every extra; a pair holds exactly the named ones, including one added with add_tool, and they work."""
    agent = build_agent(tmp_path, tools=(web_fetch, calc))
    agent.add_tool(lookup)
    tree = ScriptedTree(
        {
            ROOT: [launch(task("intel", tools=["web_fetch", "lookup"])), reply("done")],
            generator("intel"): [tool_call("web_fetch", {"url": "https://example.com/pricing"}), tool_call("lookup", {"topic": "acme"}), reply("INTEL-SUMMARY")],
            verifier("intel"): [reply(PASSED_REVIEW)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert {"web_fetch", "calc", "lookup"} <= set(tree.first_call(ROOT).tools)
    assert not is_error(_root_launch_result(tree))
    assert set(tree.first_call(generator("intel")).tools) == GENERATOR_TOOLS | {"web_fetch", "lookup"}
    assert set(tree.first_call(verifier("intel")).tools) == VERIFIER_TOOLS | {"web_fetch", "lookup"}
    results = dict(tool_results(tree.calls_by(generator("intel"))[-1]))
    assert results["web_fetch"] == "FETCHED:https://example.com/pricing"
    assert results["lookup"] == "WIKI:acme"


# ---------------------------------------------------------------- AC-29


def test_context_pastes_named_entries_and_lists_named_paths(tmp_path: Path) -> None:
    """AC-29, D-14: the generator's first message holds the named entry's text and the named path, not the file's content or unnamed entries."""
    root = workspace_root(tmp_path)
    write_jsonl(
        root / "entries.jsonl",
        [entry_record(1, "UNNAMED-ENTRY-ONE Hooli is private"), entry_record(2, "UNNAMED-ENTRY-TWO Initech has no list price"), entry_record(3, "Acme list price is 49 USD per seat")],
    )
    note = root / "notes" / "x.md"
    note.parent.mkdir(parents=True)
    note.write_text("NOTE-X-BODY-NOT-PASTED\n", encoding="utf-8")
    write_jsonl(root / "files.jsonl", [{"path": "notes/x.md", "description": "Pricing scratch notes", "by": "root", "run": "20261015T024900Z-1a2b3c4d", "at": "2026-10-15T02:51:07Z"}])
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [launch(task("acme", context=["#3", "notes/x.md"])), reply("done")], **simple_pair("acme", "ACME-SUMMARY")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    first = tree.first_call(generator("acme")).prompt
    assert "Acme list price is 49 USD per seat" in first and "notes/x.md" in first
    assert "NOTE-X-BODY-NOT-PASTED" not in first
    assert "UNNAMED-ENTRY-ONE" not in first and "UNNAMED-ENTRY-TWO" not in first


# ---------------------------------------------------------------- AC-31


def test_relaunching_a_finished_name_replays_its_card_without_building_agents(tmp_path: Path) -> None:
    """AC-31, INV-26: launching a finished name again returns its recorded card with the replayed label, runs no agent, and adds no usage."""
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [launch(task("a")), launch(task("a")), reply("done")], **simple_pair("a", "A-SUMMARY-ONCE")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    replayed = _root_launch_result(tree, 2)
    assert not is_error(replayed)
    assert "A-SUMMARY-ONCE" in replayed
    assert template_regex(prompt_text("replayed_label")).search(replayed)
    records = journal_records(workspace_root(tmp_path))
    assert events(records).count("pair_started") == 1 and events(records).count("pair_finished") == 1
    assert agent.get_usage().model_call_count == 5, "3 root calls + 1 generator + 1 verifier; a replay adds none"


# ---------------------------------------------------------------- AC-32


def test_the_verifier_gets_the_generators_outcome_but_never_its_transcript(tmp_path: Path) -> None:
    """AC-32, INV-12: the verifier's first message holds its prompt, goal, criteria, status, the reply, staged s1, and the written path; never the generator's tool calls or results."""
    agent = build_agent(tmp_path)
    card = task("x", goal="GOAL-X-TEXT", criteria=["CRITERION-ONE-TEXT", "CRITERION-TWO-TEXT"], gen="GEN-PROMPT-TEXT", ver="VER-PROMPT-TEXT")
    tree = ScriptedTree(
        {
            ROOT: [launch(card), reply("done")],
            generator("x"): [
                tool_call("grep", {"pattern": "GEN-GREP-PRIVATE"}),
                tool_call("write_note", {"path": "notes/n.md", "text": "GEN-NOTE-BODY-PRIVATE", "description": "Findings for task x"}),
                tool_call("remember", {"kind": "fact", "text": "STAGED-FACT-TEXT Acme is 49 USD"}),
                reply("did X"),
            ],
            verifier("x"): [reply(PASSED_REVIEW)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    first = tree.first_call(verifier("x"))
    for expected in ("VER-PROMPT-TEXT", "GOAL-X-TEXT", "CRITERION-ONE-TEXT", "CRITERION-TWO-TEXT", "did X", "STAGED-FACT-TEXT Acme is 49 USD", "notes/n.md"):
        assert expected in first.prompt, f"the verifier's first message lacks {expected!r}"
    assert re.search(r"\bdone\b", first.prompt) and re.search(r"(?<![\w-])s1(?![\w-])", first.prompt)
    assert template_regex(prompt_text("verifier_system_prompt")).search(first.system), "the verifier preamble is missing from its system text"
    assert SYSTEM_PROMPT in first.system and MAP_HEADER in first.system
    for call in tree.calls_by(verifier("x")):
        assert "GEN-GREP-PRIVATE" not in seen_text(call) and "GEN-NOTE-BODY-PRIVATE" not in seen_text(call)


# ---------------------------------------------------------------- AC-35


@pytest.mark.asyncio
async def test_launch_subagent_is_exempt_from_the_tool_timeout_and_result_cap(tmp_path: Path) -> None:
    """AC-35, INV-38, D-29: a batch outlives a tiny tool timeout and its cards pass result_max_chars uncut."""
    from vidbyte.agents.settings import AgentLoopSettings, ToolSettings

    loop = AgentLoopSettings(tool_settings=ToolSettings(tool_timeout_seconds=0.001, result_max_chars=200))
    agent = build_agent(tmp_path, loop=loop)
    both_active = Gate(2)
    summary_a = "AAA-SUMMARY-" + "a" * 280 + "-AAA-END"
    summary_b = "BBB-SUMMARY-" + "b" * 280 + "-BBB-END"
    tree = ScriptedTree(
        {
            ROOT: [launch(task("a"), task("b")), reply("done")],
            generator("a"): [after(both_active, reply(summary_a))],
            verifier("a"): [reply(PASSED_REVIEW)],
            generator("b"): [after(both_active, reply(summary_b))],
            verifier("b"): [reply(PASSED_REVIEW)],
        }
    )
    with tree.install():
        await agent.arun(TASK)
    tree.assert_complete()
    result = _root_launch_result(tree)
    assert not is_error(result), result[:300]
    assert summary_a in result and summary_b in result
    assert "truncated" not in result
    assert set(finished_cards(workspace_root(tmp_path))) == {pair_key("a"), pair_key("b")}
