"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_verification.py

PURPOSE: Proves how a pair's verdict decides what reaches memory: the last VERDICT line wins in any Markdown wrapping or case, a missing verdict or a failing verifier commits nothing, drop_entry removes exactly the named staged entry, and a corrupted entries.jsonl at commit time drops each pair's entries with a message instead of crashing the batch. Since the S4 review it also pins two rules no earlier test caught when deleted: the entry rules a pair agent's remember meets when it stages, and the by stamp on an entry the verifier staged.
ROLE IN CODEBASE: Verification and commit layer of tests/features/infinite_memory_agent/ (spec AC-10, AC-11, AC-37, AC-38; INV-14..INV-17, INV-19, INV-29, INV-32; EC-12, EC-13, EC-17, EC-24; S4 review finding R-11). Exercises vidbyte/agents/infinite/launch.py (InfinitePair), vidbyte/agents/infinite/memory.py and vidbyte/agents/infinite/workspace.py through a real InfiniteMemoryAgent run.
ARCHITECTURE NOTE: Each test scripts one or two pairs whose generators stage entries with remember, then reads the verdict and dropped list from the pair_finished card in the journal and the committed lines from entries.jsonl.
FUNCTION INVENTORY: test_no_verdict_or_a_failing_verifier_drops_every_staged_entry (AC-10, EC-12); test_drop_entry_removes_only_the_named_staged_entry (AC-11); test_a_malformed_entries_line_drops_each_pairs_entries_but_the_run_finishes (AC-37, EC-24, INV-16); test_an_entry_that_no_longer_fits_at_commit_is_dropped_with_the_cap_reason (EC-17, INV-19); test_verdict_is_read_from_the_last_matching_line_in_any_markdown_or_case (AC-38, EC-13, INV-14, INV-15); test_a_pair_agents_remember_is_checked_against_the_entry_rules_when_it_stages (R-11, INV-17, INV-15, INV-32); test_an_entry_the_verifier_stages_is_committed_under_the_verifiers_own_key (R-11, INV-16). _names_any checks that a refusal names one of its expected tokens.
COMMON MODIFICATION PATTERNS: Add a verdict spelling as one VERDICT_REPLIES row with the verdict it must give. Add a stage-time entry rule as one STAGE_REFUSALS row naming the tokens its refusal may carry.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not write the malformed line before the generators have staged; AC-37 is about the commit-time re-check.
KNOWN EDGE CASES: In AC-37 whichever verifier is called first writes the malformed line, once; both commits come after it, because a pair commits only after its verifier returns.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-agent/spec.md sections 6.1, 6.2 and 8.5.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_verification.py -q
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    TASK,
    ScriptedTree,
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
    reply,
    task,
    template_regex,
    tool_call,
    tool_result,
    tool_results,
    verifier,
    workspace_root,
    write_jsonl,
)
from vidbyte.lib.errors import VidbyteSdkError

STAGED_TEXT = "Initech charges 30 USD per seat"


def _remember(text: str) -> object:
    return tool_call("remember", {"kind": "fact", "text": text})


@pytest.mark.parametrize("ending", ("no-verdict-line", "verifier-raises"))
def test_no_verdict_or_a_failing_verifier_drops_every_staged_entry(tmp_path: Path, ending: str) -> None:
    """AC-10, EC-12, INV-14, INV-15, INV-29: no VERDICT line, or a verifier error, gives unchecked; entries.jsonl stays unchanged and dropped names the entry."""
    agent = build_agent(tmp_path)
    entries = workspace_root(tmp_path) / "entries.jsonl"
    before = entries.read_bytes()
    last = reply("Looks fine to me, nothing to add.") if ending == "no-verdict-line" else fail(VidbyteSdkError("verifier provider is down"))
    tree = ScriptedTree({ROOT: [launch(task("p")), reply("done")], generator("p"): [_remember(STAGED_TEXT), reply("P-SUMMARY")], verifier("p"): [last]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    card = finished_cards(workspace_root(tmp_path))[pair_key("p")]
    assert (card["status"], card["verdict"]) == ("done", "unchecked")
    assert entries.read_bytes() == before
    assert card["entries"] == []
    assert any("s1" in item or STAGED_TEXT in item for item in card["dropped"]), card["dropped"]
    if ending == "verifier-raises":
        assert card["review"].strip(), "a raised error's text belongs in the card's review"


def test_drop_entry_removes_only_the_named_staged_entry(tmp_path: Path) -> None:
    """AC-11, INV-15, INV-16: the verifier drops s1 and passes; only s2 is committed, and dropped names s1."""
    agent = build_agent(tmp_path)
    tree = ScriptedTree(
        {
            ROOT: [launch(task("p")), reply("done")],
            generator("p"): [_remember("Acme is free for everyone"), _remember("Acme charges 49 USD per seat"), reply("P-SUMMARY")],
            verifier("p"): [tool_call("drop_entry", {"id": "s1"}), reply("Dropped the wrong entry.\nVERDICT: passed")],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    dropped_result = tool_result(tree.calls_by(verifier("p"))[1], "drop_entry")
    assert not is_error(dropped_result)
    assert template_regex(prompt_text("entry_dropped_prompt")).search(dropped_result)
    assert "s2" in dropped_result, "the drop result lists the remaining staged keys"
    committed = read_jsonl(workspace_root(tmp_path) / "entries.jsonl")
    assert [entry["text"] for entry in committed] == ["Acme charges 49 USD per seat"]
    assert (committed[0]["by"], committed[0]["verified_by"]) == ("root/p/gen", "root/p/ver")
    card = finished_cards(workspace_root(tmp_path))[pair_key("p")]
    assert card["verdict"] == "passed" and card["entries"] == [committed[0]["id"]]
    assert any("s1" in item for item in card["dropped"]) and not any("s2" in item for item in card["dropped"]), card["dropped"]


def test_a_malformed_entries_line_drops_each_pairs_entries_but_the_run_finishes(tmp_path: Path) -> None:
    """AC-37, EC-24, INV-16, INV-29: a malformed line written before either commit drops both pairs' entries with a message naming the file and line; verdicts stay passed and the run finishes."""
    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(1, "Hooli is private"), entry_record(2, "Umbrella sells only to governments")])
    agent = build_agent(tmp_path)
    corrupted: list[str] = []

    def corrupt(call: object) -> None:
        # The first verifier to start appends line 3, after both generators staged and before either commit.
        if not corrupted:
            with (root / "entries.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
                handle.write("{not valid json\n")
            corrupted.append("done")

    tree = ScriptedTree(
        {
            ROOT: [launch(task("a"), task("b")), reply("ROOT-FINAL")],
            generator("a"): [_remember("Acme charges 49 USD per seat"), reply("A-SUMMARY")],
            generator("b"): [_remember("Globex charges 59 USD per seat"), reply("B-SUMMARY")],
            verifier("a"): [observe(corrupt, reply("Checked.\nVERDICT: passed"))],
            verifier("b"): [observe(corrupt, reply("Checked.\nVERDICT: passed"))],
        }
    )
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    assert answer.content == "ROOT-FINAL"
    cards = finished_cards(root)
    assert set(cards) == {pair_key("a"), pair_key("b")}
    for key in (pair_key("a"), pair_key("b")):
        card = cards[key]
        assert (card["status"], card["verdict"]) == ("done", "passed")
        assert card["entries"] == []
        assert any("entries.jsonl" in item and int_token(3).search(item) for item in card["dropped"]), card["dropped"]
    result = tool_result(tree.calls_by(ROOT)[1], "launch_subagent")
    assert not is_error(result) and "A-SUMMARY" in result and "B-SUMMARY" in result
    assert events(journal_records(root))[-1] == "run_finished"


def test_an_entry_that_no_longer_fits_at_commit_is_dropped_with_the_cap_reason(tmp_path: Path) -> None:
    """EC-17, INV-16, INV-19: when the workspace fills between staging and commit, the entry is dropped with a cap message and the verdict stands."""
    root = workspace_root(tmp_path)
    agent = build_agent(tmp_path, workspace={"max_tokens": 1_000, "max_file_tokens": 1_000})

    def fill(call: object) -> None:
        # 3,980 characters is 995 tokens, so the 1,000-token workspace has no room left for one more entry line.
        (root / "filler.txt").write_text("f" * 3_980, encoding="utf-8")

    tree = ScriptedTree(
        {
            ROOT: [launch(task("p")), reply("done")],
            generator("p"): [_remember(STAGED_TEXT), reply("P-SUMMARY")],
            verifier("p"): [observe(fill, reply("Checked.\nVERDICT: passed"))],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    card = finished_cards(root)[pair_key("p")]
    assert card["verdict"] == "passed" and card["entries"] == []
    assert any("max_tokens" in item or int_token(1_000).search(item) for item in card["dropped"]), card["dropped"]
    assert read_jsonl(root / "entries.jsonl") == []


VERDICT_REPLIES = (
    pytest.param("**VERDICT: passed**", "passed", id="bold-line"),
    pytest.param("VERDICT: **passed**", "passed", id="bold-value"),
    pytest.param("VERDICT: passed.", "passed", id="trailing-period"),
    pytest.param("Verdict: PASSED", "passed", id="mixed-case"),
    pytest.param("`VERDICT: fixed`", "fixed", id="backticks"),
    pytest.param("_VERDICT: failed_", "failed", id="underscores"),
    pytest.param("VERDICT: passed\nThen one source turned out to be stale.\n**VERDICT: failed**", "failed", id="last-line-wins"),
)


@pytest.mark.parametrize(("ending", "verdict"), VERDICT_REPLIES)
def test_verdict_is_read_from_the_last_matching_line_in_any_markdown_or_case(tmp_path: Path, ending: str, verdict: str) -> None:
    """AC-38, EC-13, INV-14, INV-15: the last VERDICT line decides, in any Markdown wrapping or case; passed, fixed, and failed all commit the staged entry."""
    agent = build_agent(tmp_path)
    tree = ScriptedTree(
        {
            ROOT: [launch(task("p")), reply("done")],
            generator("p"): [_remember(STAGED_TEXT), reply("P-SUMMARY")],
            verifier("p"): [reply(f"Checked every source.\n{ending}")],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    card = finished_cards(workspace_root(tmp_path))[pair_key("p")]
    assert card["verdict"] == verdict
    committed = read_jsonl(workspace_root(tmp_path) / "entries.jsonl")
    assert [(entry["text"], entry["verified_by"]) for entry in committed] == [(STAGED_TEXT, "root/p/ver")]
    assert card["entries"] == [committed[0]["id"]]


# ---------------------------------------------------------------- S4 review: guardrails no test pinned (R-11)


STAGE_REFUSALS: tuple[tuple[str, dict[str, Any], tuple[Any, ...]], ...] = (
    ("text over max_entry_tokens", {"kind": "fact", "text": "Globex pricing detail " * 15}, ("max_entry_tokens", 60)),
    ("text of a live entry", {"kind": "fact", "text": "  acme pro COSTS 49 usd   per seat "}, ("already recorded as #7",)),
    ("supersedes a missing id", {"kind": "fact", "text": "Initech costs 30 USD per seat", "supersedes": 99}, (99,)),
)


def _names_any(content: str, tokens: tuple[Any, ...]) -> bool:
    """True when the content names at least one token: an int as a standalone number, anything else as text."""
    return any((int_token(token) if isinstance(token, int) else re.compile(re.escape(str(token)))).search(content) for token in tokens)


def test_a_pair_agents_remember_is_checked_against_the_entry_rules_when_it_stages(tmp_path: Path) -> None:
    """R-11, INV-17, INV-15, INV-32: a generator's over-cap text, a live entry's text, a missing supersedes id, and a reworded repeat of its own staged entry are each refused at stage time with the quota line; the verifier repeating that entry is refused as already staged as s1; only s1 is staged and committed."""
    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(7, "Acme Pro costs 49 USD per seat")])
    agent = build_agent(tmp_path)
    tree = ScriptedTree(
        {
            ROOT: [launch(task("p")), reply("done")],
            generator("p"): [
                *(tool_call("remember", args) for _, args, _ in STAGE_REFUSALS),
                _remember(STAGED_TEXT),
                _remember("  initech CHARGES 30 usd   per SEAT "),
                reply("P-SUMMARY"),
            ],
            verifier("p"): [_remember(STAGED_TEXT), reply("Checked.\nVERDICT: passed")],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    results = [content for name, content in tool_results(tree.calls_by(generator("p"))[-1]) if name == "remember"]
    assert len(results) == len(STAGE_REFUSALS) + 2
    rejected = template_regex(prompt_text("memory_rejected_prompt"))
    quota = template_regex(prompt_text("quota_line"))
    for (label, _, named), content in zip(STAGE_REFUSALS, results, strict=False):
        assert is_error(content), f"{label} was staged instead of refused: {content}"
        assert rejected.search(content) and quota.search(content), f"{label}: {content}"
        assert _names_any(content, named), f"{label} does not name any of {named}: {content}"
    staged, repeated = results[-2:]
    assert not is_error(staged) and template_regex(prompt_text("remember_staged_prompt"), key="s1").search(staged), staged
    assert is_error(repeated) and "already staged as s1" in repeated, repeated
    # Refused calls cost nothing: after one accepted call the generator still has 4 of its 5 entries.
    assert template_regex(prompt_text("quota_line"), entries_left=4, entries_max=5).search(repeated), repeated
    checked = tool_result(tree.calls_by(verifier("p"))[-1], "remember")
    assert is_error(checked) and "already staged as s1" in checked, checked
    assert not re.search(r"(?<![\w-])s2(?![\w-])", tree.first_call(verifier("p")).prompt), "only s1 may reach the verifier as staged"
    committed = read_jsonl(root / "entries.jsonl")
    assert [(entry["id"], entry["text"], entry["by"]) for entry in committed] == [(7, "Acme Pro costs 49 USD per seat", "root"), (8, STAGED_TEXT, "root/p/gen")]
    card = finished_cards(root)[pair_key("p")]
    assert (card["verdict"], card["entries"], card["dropped"]) == ("passed", [8], [])


def test_an_entry_the_verifier_stages_is_committed_under_the_verifiers_own_key(tmp_path: Path) -> None:
    """R-11, INV-16, INV-15: the generator's entry commits first with by=root/p/gen, the verifier's own entry next with by=root/p/ver, and both carry verified_by=root/p/ver."""
    fee = "Initech's 30 USD price excludes a 99 USD setup fee"
    agent = build_agent(tmp_path)
    tree = ScriptedTree(
        {
            ROOT: [launch(task("p")), reply("done")],
            generator("p"): [_remember(STAGED_TEXT), reply("P-SUMMARY")],
            verifier("p"): [_remember(fee), reply("Added the missing setup fee.\nVERDICT: fixed")],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    staged = tool_result(tree.calls_by(verifier("p"))[-1], "remember")
    assert not is_error(staged) and template_regex(prompt_text("remember_staged_prompt"), key="s2").search(staged), staged
    committed = read_jsonl(workspace_root(tmp_path) / "entries.jsonl")
    assert [(entry["text"], entry["by"], entry["verified_by"]) for entry in committed] == [(STAGED_TEXT, "root/p/gen", "root/p/ver"), (fee, "root/p/ver", "root/p/ver")]
    card = finished_cards(workspace_root(tmp_path))[pair_key("p")]
    assert (card["verdict"], card["entries"]) == ("fixed", [entry["id"] for entry in committed])
