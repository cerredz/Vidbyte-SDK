"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_delegation.py

PURPOSE: Proves what launch_subagent promises the root and every generator: pairs in one call run at the same time, each verifier follows its own generator, the parent sees only capped cards in task order, a bad batch starts nothing, depth and role decide who may delegate, max_agents bounds the run, one failing pair never sinks its siblings, extras reach children only by name, context entries are pasted, finished names replay, and the loop's tool limits never cut a batch. It also holds the S4 review's regression tests for this layer: a card or journal record that cannot be written as given, the card bound of NFR-7 as amended in r5, and replay of a pair whose context entry was superseded.
ROLE IN CODEBASE: Delegation layer of tests/features/infinite_memory_agent/ (spec AC-5..AC-8, AC-12, AC-13, AC-26, AC-28, AC-29, AC-31, AC-32, AC-35, AC-36; INV-4, INV-6..INV-13, INV-24, INV-26, INV-29, INV-30, INV-38; NFR-7; EC-4..EC-11, EC-12, EC-38, EC-43; S4 review findings R-1, R-3, R-4). Exercises vidbyte/agents/infinite/launch.py through a real InfiniteMemoryAgent run.
ARCHITECTURE NOTE: Every agent in the tree is driven by one ScriptedTree routed by agent name. What the parent saw is read from the tool messages in its next model call; what happened on disk is read from the journal and entries.jsonl. Concurrency is proven with a Gate that opens only when both generators are inside a model call at once, never with timing.
FUNCTION INVENTORY: test_two_tasks_run_concurrently_and_each_verifier_follows_its_own_generator (AC-5, INV-4, INV-9, INV-12, INV-24); test_an_invalid_batch_starts_nothing_and_the_tool_stays_usable (AC-6, EC-4..EC-7, EC-38, EC-43); test_depth_cap_and_role_decide_who_holds_launch_subagent_and_drop_entry (AC-7, INV-8, INV-13, AC-17 SPARSE clause); test_a_batch_over_max_parallel_is_denied_by_the_middleware_and_starts_nothing (AC-6, EC-4); test_a_batch_that_would_pass_max_agents_is_refused_whole (AC-8, INV-10, EC-8); test_a_failed_or_blank_generator_skips_its_verifier_and_its_sibling_still_reports (AC-12, EC-9, EC-10, INV-29); test_a_generator_stopped_by_max_iterations_is_partial_and_still_verified (AC-13, EC-11, INV-30); test_a_long_generator_reply_is_cut_in_its_card_and_the_rest_never_reaches_the_root (AC-26, INV-4, NFR-7); test_a_task_card_grants_exactly_the_extras_it_names (AC-28, AC-36, INV-6, INV-7); test_context_pastes_named_entries_and_lists_named_paths (AC-29, D-14); test_relaunching_a_finished_name_replays_its_card_without_building_agents (AC-31, INV-26); test_the_verifier_gets_the_generators_outcome_but_never_its_transcript (AC-32, INV-12); test_launch_subagent_is_exempt_from_the_tool_timeout_and_result_cap (AC-35, INV-38); test_a_pair_whose_card_or_record_cannot_be_written_as_given_still_finishes_beside_its_sibling (R-1, INV-29, INV-32); test_an_unchecked_card_with_long_dropped_and_files_lists_stays_inside_the_nfr7_bound (R-3, NFR-7, INV-4, EC-12); test_a_finished_pair_replays_after_its_context_entry_was_superseded_and_new_pairs_still_run (R-4, INV-26, INV-9).
COMMON MODIFICATION PATTERNS: Add a rejected-batch case as one INVALID_BATCHES row naming the token the error must contain. Keep private markers (GEN-*-PRIVATE, VER-*-PRIVATE) unique strings so a leak check cannot match by accident.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not prove concurrency or ordering with sleeps or wall-clock time; use Gate, Signal, and ScriptedTree.events. 3. Do not assert card wording beyond the catalog templates and the field values the spec fixes.
KNOWN EDGE CASES: A runner AssertionError inside a child may be turned into a tool error by the parent, so every test ends with ScriptedTree.assert_complete, which also fails on unscripted calls. The result-card template is matched with its literal text only, so a template of bare placeholders would make renderings() weak. The R-1 path cases accept both spec-conformant outcomes: the path refused at write time, or accepted with the card error turned into an unchecked card; either way every key finishes and every card returns.
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
from vidbyte.lib.constants.infinite import INFINITE_TASK_NAME_PATTERN
from vidbyte.lib.errors import VidbyteSdkError

MEMORY_TOOLS = {"bash", "grep", "read_lines", "remember", "write_note"}
GENERATOR_TOOLS = MEMORY_TOOLS | {"launch_subagent", "isDone"}
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
    pytest.param([task("alpha"), task("alpha")], ("alpha",), id="duplicate-name"),
    pytest.param([task("alpha", ver="   ")], ("verifier_prompt",), id="blank-verifier-prompt"),
    pytest.param([_no_generator(task("alpha"))], ("generator_prompt",), id="missing-generator-prompt"),
    pytest.param([task("alpha", tools=["web_fetch"])], ("web_fetch",), id="tool-the-root-lacks"),
    pytest.param([task("alpha", context=["#99"])], (99,), id="unknown-context-id"),
    pytest.param([task("alpha", context=["#40"])], (40,), id="superseded-context-id"),
    pytest.param([task("Pricing Research!")], ("Pricing Research!", INFINITE_TASK_NAME_PATTERN), id="name-fails-pattern"),
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
    """AC-7, INV-6, INV-8, INV-13, AC-17 (SPARSE clause): with max_depth=2 every generator holds launch_subagent, the depth-1 one delegates, the depth-2 one is refused by the middleware with a reason naming max_depth, and no verifier may delegate."""
    agent = build_agent(tmp_path, max_depth=2)
    nested = generator("a")
    tree = ScriptedTree(
        {
            ROOT: [launch(task("a")), reply("done")],
            generator("a"): [launch(task("b")), reply("A-SUMMARY")],
            verifier("a"): [reply(PASSED_REVIEW)],
            generator("b", nested): [launch(task("c")), reply("B-SUMMARY")],
            verifier("b", nested): [reply(PASSED_REVIEW)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert set(tree.first_call(generator("a")).tools) == GENERATOR_TOOLS
    assert set(tree.first_call(generator("b", nested)).tools) == GENERATOR_TOOLS
    assert set(tree.first_call(verifier("a")).tools) == VERIFIER_TOOLS
    assert set(tree.first_call(verifier("b", nested)).tools) == VERIFIER_TOOLS
    assert not is_error(tool_result(tree.calls_by(generator("a"))[1], "launch_subagent"))
    refused = tool_result(tree.calls_by(generator("b", nested))[1], "launch_subagent")
    assert "Tool denied by middleware" in refused and "max_depth" in refused and int_token(2).search(refused), refused
    assert generator("c", generator("b", nested)) not in tree.agents_called()
    cards = finished_cards(workspace_root(tmp_path))
    assert "root/a/gen/b" in cards and "root/a/gen/b/gen/c" not in cards


def test_a_batch_over_max_parallel_is_denied_by_the_middleware_and_starts_nothing(tmp_path: Path) -> None:
    """AC-6, INV-9, EC-4: a batch of more than max_parallel tasks is refused by DelegationLimitsMiddleware before the tool runs, naming max_parallel; nothing starts, nothing is journaled, and a valid call then works."""
    agent = build_agent(tmp_path, max_parallel=2)
    tree = ScriptedTree({ROOT: [launch(task("alpha"), task("beta"), task("gamma")), launch(task("ok-task")), reply("done")], **simple_pair("ok-task", "OK-TASK-SUMMARY")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    refused = _root_launch_result(tree, 1)
    assert "Tool denied by middleware" in refused and "max_parallel" in refused and int_token(2).search(refused) and int_token(3).search(refused), refused
    accepted = _root_launch_result(tree, 2)
    assert not is_error(accepted) and "OK-TASK-SUMMARY" in accepted
    assert tree.agents_called() == {ROOT, generator("ok-task"), verifier("ok-task")}
    assert events(journal_records(workspace_root(tmp_path))) == ["run_started", "pair_started", "pair_finished", "run_finished"]


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


# ---------------------------------------------------------------- S4 review regressions: R-1 (INV-29)


CARD_BUILD_TRIGGERS = (
    pytest.param("path", "\u2028", id="u2028-in-a-note-path"),
    pytest.param("path", "\u0085", id="u0085-in-a-note-path"),
    pytest.param("reply", "\ud83d", id="lone-surrogate-in-the-reply"),
)


@pytest.mark.parametrize(("trigger", "character"), CARD_BUILD_TRIGGERS)
def test_a_pair_whose_card_or_record_cannot_be_written_as_given_still_finishes_beside_its_sibling(tmp_path: Path, trigger: str, character: str) -> None:
    """R-1, INV-29, INV-32: a note path that splitlines() breaks, or a lone surrogate in the generator's reply, stays inside its pair: both keys get pair_finished, both cards reach the root, and launch_subagent returns no error."""
    root = workspace_root(tmp_path)
    agent = build_agent(tmp_path)
    # U+2028 and U+0085 are legal in file names on NTFS and POSIX alike, so the write itself succeeds on every host.
    odd_path = f"notes/acme{character}prices.md"
    if trigger == "path":
        steps_a = [tool_call("write_note", {"path": odd_path, "text": "Acme Pro is 49 USD.", "description": "Acme prices"}), reply("A-SUMMARY")]
    else:
        # A provider's JSON may carry "\ud83d" escaped; it decodes to a lone surrogate, which UTF-8 cannot encode.
        steps_a = [reply(f"A-SUMMARY found {character}")]
    tree = ScriptedTree(
        {
            ROOT: [launch(task("a"), task("b")), reply("ROOT-FINAL")],
            generator("a"): steps_a,
            verifier("a"): [reply(PASSED_REVIEW)],
            **simple_pair("b", "B-SUMMARY"),
        }
    )
    with tree.install():
        answer = agent.run(TASK)
    result = _root_launch_result(tree)
    assert not is_error(result), f"launch_subagent failed instead of returning both cards: {ascii(result[:300])}"
    assert "A-SUMMARY" in result and "B-SUMMARY" in result, ascii(result[:600])
    records = journal_records(root)
    finished = sorted(str(record["key"]) for record in records if record["event"] == "pair_finished")
    assert finished == [pair_key("a"), pair_key("b")], f"every reserved key needs exactly one pair_finished: {events(records)}"
    tree.assert_complete()
    assert answer.content == "ROOT-FINAL"
    card = finished_cards(root)[pair_key("a")]
    assert card["summary"].startswith("A-SUMMARY"), ascii(card)
    if trigger != "path":
        return
    written = tool_result(tree.calls_by(generator("a"))[-1], "write_note")
    if is_error(written):
        # The path was refused at write time: a refusal with the quota line that wrote nothing (INV-32).
        assert template_regex(prompt_text("memory_rejected_prompt")).search(written) and template_regex(prompt_text("quota_line")).search(written), ascii(written)
        assert not [path for path in root.rglob("*") if path.name.startswith("acme")], "a refused note path left a file behind"
    elif card["verdict"] == "unchecked":
        # The path was accepted and the error came after the generator returned, so INV-29 keeps its status.
        assert card["status"] == "done", ascii(card)


# ---------------------------------------------------------------- S4 review regressions: R-3 (NFR-7 as amended in r5)


def test_an_unchecked_card_with_long_dropped_and_files_lists_stays_inside_the_nfr7_bound(tmp_path: Path) -> None:
    """R-3, NFR-7, INV-4, EC-12: with summary, review, dropped and files all far over the card cap, the rendered card holds at most 4 x INFINITE_CARD_TEXT_MAX_TOKENS of field text, one marker per cut field, and the fixed template; the journal's card keeps both lists whole."""
    from string import Formatter

    from vidbyte.lib.constants.infinite import INFINITE_CARD_TEXT_MAX_TOKENS, INFINITE_TRUNCATION_MARKER
    from vidbyte.lib.util import TokenEstimate

    root = workspace_root(tmp_path)
    # Enough written paths that their joined list is over the card cap
    # whatever the cap is; each path is about 12 tokens.
    notes = [f"notes/competitor-{index:03d}-list-price-history.md" for index in range(INFINITE_CARD_TEXT_MAX_TOKENS // 8)]
    for relative in notes:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Seed line.\n", encoding="utf-8")
    # Ten distinct one-line entries of about 185 tokens each, under the raised max_entry_tokens of 200.
    facts = [(f"Competitor {index:02d} lists " + "tier-price-detail " * 40).strip() for index in range(10)]
    agent = build_agent(tmp_path, workspace={"max_entry_tokens": 200, "max_entries_per_agent": 10})
    steps = [tool_call("remember", {"kind": "fact", "text": fact}) for fact in facts]
    steps += [tool_call("write_note", {"path": relative, "text": "One more price point.\n"}) for relative in notes]
    long_summary = "Summary of the competitor pricing research. " * (INFINITE_CARD_TEXT_MAX_TOKENS // 4)
    # EC-12: the review has no VERDICT line, so the verdict is unchecked and every staged entry is dropped.
    long_review = "Reviewed the pricing notes and their sources line by line. " * (INFINITE_CARD_TEXT_MAX_TOKENS // 8)
    tree = ScriptedTree({ROOT: [launch(task("a")), reply("done")], generator("a"): [*steps, reply(long_summary)], verifier("a"): [reply(long_review)]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert not any(is_error(content) for _, content in tool_results(tree.calls_by(generator("a"))[-1])), "precondition: every remember and write_note succeeded"
    stored = finished_cards(root)[pair_key("a")]
    assert (stored["status"], stored["verdict"]) == ("done", "unchecked")
    for fact in facts:
        assert any(fact in item for item in stored["dropped"]), "the journal's card must keep every dropped entry whole"
    assert sorted(stored["files"]) == sorted(notes), "the journal's card must keep every written path"
    card = _root_launch_result(tree)
    literal = "".join(text for text, _, _, _ in Formatter().parse(prompt_text("result_card")))
    short_fields = ("a", pair_key("a"), "done", "unchecked", "-")
    bound = TokenEstimate.count(literal) + sum(TokenEstimate.count(value) for value in short_fields) + 4 * (INFINITE_CARD_TEXT_MAX_TOKENS + TokenEstimate.count(INFINITE_TRUNCATION_MARKER))
    assert TokenEstimate.count(card) <= bound, f"the card is {TokenEstimate.count(card)} tokens, over the NFR-7 bound of {bound}"
    assert card.count(INFINITE_TRUNCATION_MARKER) == 4, "summary, review, dropped and files are each cut once, with one marker"


# ---------------------------------------------------------------- S4 review regressions: R-4 (INV-26)


def test_a_finished_pair_replays_after_its_context_entry_was_superseded_and_new_pairs_still_run(tmp_path: Path) -> None:
    """R-4, INV-26, INV-9: pair a names #1 and supersedes it; relaunching a alone, then a beside a new task b, replays a's card each time, runs b, and refuses nothing."""
    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(1, "Acme Pro costs 49 USD")])
    agent = build_agent(tmp_path)
    card_a = task("a", context=["#1"], gen="Check the Acme Pro price in entry #1 and update it.")
    tree = ScriptedTree(
        {
            ROOT: [launch(card_a), launch(card_a), launch(card_a, task("b")), reply("ROOT-FINAL")],
            generator("a"): [tool_call("remember", {"kind": "fact", "text": "Acme Pro costs 59 USD", "supersedes": 1}), reply("A-SUMMARY")],
            verifier("a"): [reply(PASSED_REVIEW)],
            **simple_pair("b", "B-SUMMARY"),
        }
    )
    with tree.install():
        agent.run(TASK)
    first, alone, mixed = (_root_launch_result(tree, index) for index in (1, 2, 3))
    assert not is_error(first) and [entry["id"] for entry in read_jsonl(root / "entries.jsonl")] == [2], "precondition: pair a replaced #1 with #2"
    replayed = template_regex(prompt_text("replayed_label"))
    assert not is_error(alone), f"relaunching the finished pair a was refused: {ascii(alone[:300])}"
    assert replayed.search(alone) and "A-SUMMARY" in alone, alone[:300]
    assert not is_error(mixed), f"a batch of finished a plus new b was refused: {ascii(mixed[:300])}"
    assert len(replayed.findall(mixed)) == 1 and "A-SUMMARY" in mixed and "B-SUMMARY" in mixed, mixed[:600]
    assert mixed.index("A-SUMMARY") < mixed.index("B-SUMMARY"), "cards come back in task order"
    tree.assert_complete()
    records = journal_records(root)
    for name in ("a", "b"):
        started = [record for record in records if record["event"] == "pair_started" and record["key"] == pair_key(name)]
        ended = [record for record in records if record["event"] == "pair_finished" and record["key"] == pair_key(name)]
        assert len(started) == len(ended) == 1, f"pair {name} must start and finish exactly once: {events(records)}"
