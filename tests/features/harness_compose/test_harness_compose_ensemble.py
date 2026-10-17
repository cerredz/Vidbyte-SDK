"""FILE: tests/features/harness_compose/test_harness_compose_ensemble.py

PURPOSE: run_ensemble (AC-6, AC-8c, AC-20, INV-9 to INV-12, INV-16, INV-18, INV-23, INV-31, EC-23, EC-49 to EC-51, EC-70): the planner runs first with the planner files and the JSON instructions; an unanchored Grok fork proposer branches the planner's thread in place, while opencode and Muse proposers run in worktrees of their own; each proposer sees only its own role; the selector sees the successful proposals numbered by proposer position, narrows them in rounds while the target is above 1 and then selects one offered number, with repairs for a wrong role count or an unoffered number; ten 100,000-character proposals share a Grok selector's room equally, each cut to the same prefix and its truncation note; the implementer runs once, in place, after the selector and the backstop, with only the chosen proposal; no proposal means no selector and no implementer, yet the backstop runs; a proposer that writes stops the ensemble before the implementer.
ROLE IN CODEBASE: Start here when an ensemble stage runs in the wrong place or order, sees the wrong proposals, or lets a proposer's edit through.
ARCHITECTURE NOTE: Ten proposers share one fork step whose stand-in answers by the identity in its prompt (`replies`), so a proposer that saw another role's identity would answer with the wrong proposal. Stage order is read from the CliRunner spy; where each stage ran from the stand-in start records.
FUNCTION INVENTORY: roles_of builds role names and identities; proposal_text names one proposal; long_proposal builds one 100,000-character proposal; cut_length measures how much of one a prompt kept and checks its truncation note; block renders one proposal_block; ordered asserts that one label's calls all end before another's start; last_git_index finds the last git child running a subcommand; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new ensemble rule gets its own test; reuse roles_of and block for prompts.
WHAT NOT TO DO IN THIS FILE: Do not compare whole selector prompts; check the blocks, the schema chunks and the offered numbers.
KNOWN EDGE CASES: With three proposers the target is max(ceil(3 / 5), 1) = 1, so the selector answers a final selection with no round; with ten it is 2, so one round comes first.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-18, INV-23, §6.2 AC-6, AC-8, AC-20, §6.3 EC-23, EC-49 to EC-51, EC-70
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_ensemble.py
"""

from __future__ import annotations

import os
import re
import sys

import pytest

THREE = [("ROLE-ONE", "IDENTITY-ONE"), ("ROLE-TWO", "IDENTITY-TWO"), ("ROLE-THREE", "IDENTITY-THREE")]
PROPOSALS = {"ROLE-ONE": "PROPOSAL-ONE: lazy imports.", "ROLE-TWO": "PROPOSAL-TWO: cache the parser.", "ROLE-THREE": "PROPOSAL-THREE: drop plugins."}


def roles_of(count: int) -> list[tuple[str, str]]:
    return [(f"ROLE-{index:02d}", f"<IDENTITY-{index:02d}>") for index in range(1, count + 1)]


def proposal_text(index: int) -> str:
    return f"PROPOSAL-{index:02d} text."


def long_proposal(index: int) -> str:
    # Exactly the base result cap: a marker, then filler.
    return f"LONG-{index:02d}:" + "z" * 99_992


def cut_length(pack, prompt: str, index: int, total: int) -> int:
    # How much of long_proposal(index) the prompt kept, after checking
    # that its truncation note with the omitted count follows it.
    found = re.search(f"LONG-{index:02d}:z*", prompt)
    assert found, f"proposal {index} is missing from the prompt"
    kept = len(found.group())
    note = pack.render("truncation_note", omitted=total - kept)
    assert prompt[found.end() :].lstrip().startswith(note), f"proposal {index} does not end with its truncation note"
    return kept


def block(pack, number: int, role_name: str, text: str) -> str:
    return pack.render("proposal_block", number=number, role_name=role_name, text=text)


def ordered(runs, earlier: str, later: str) -> bool:
    exits = [runs.position("exit", index) for index in runs.calls_of(earlier)]
    enters = [runs.position("enter", index) for index in runs.calls_of(later)]
    return bool(exits) and bool(enters) and max(exits) < min(enters)


def last_git_index(runs, word: str) -> int:
    return max(index for index, item in runs.git_calls() if runs.subcommand(item)[:1] == [word])


@pytest.mark.asyncio
async def test_ensemble_plans_proposes_selects_and_implements_in_order(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-6 / INV-23 / INV-9 / INV-10 / INV-12 / INV-31.
    api = compose_api
    sandbox.make_repo()
    plan_text = pack.plan_json(THREE)
    planner = steps.bind("grok", plan=True, label="planner", fake={"text": plan_text})
    fork = steps.bind("grok", "fork", plan=True, label="p-grok", fake={"text": PROPOSALS["ROLE-ONE"]})
    opencode = steps.bind("opencode", label="p-oc", fake={"final_parts": [PROPOSALS["ROLE-TWO"]]})
    muse = steps.bind("muse", label="p-muse", fake={"text": PROPOSALS["ROLE-THREE"]})
    selection = pack.selection_json(2, approach="APPROACH-LAZY", rationale="RATIONALE-RISK", guidance="GUIDANCE-CLI")
    selector = steps.bind("grok", plan=True, label="selector", fake={"text": selection})
    implementer = steps.bind("grok", edits=True, label="implementer", fake={"text": "Implemented.", "write_files": {"impl.txt": "implemented\n"}})
    roster = api.ensemble.EnsembleRoster(planner=planner, proposers=[fork, opencode, muse], selector=selector, implementer=implementer)
    result = await api.compose.run_ensemble(pack.TASK, roster=roster)

    # Plan first, with the planner files and the JSON instructions.
    planner_launch = sandbox.only_launch("planner")
    planner_prompt = pack.launch_prompt(planner_launch)
    assert pack.TASK in planner_prompt
    for stem in ("planner_system", "planner_turn", "plan_schema", "json_answer"):
        assert all(chunk in planner_prompt for chunk in pack.literal_chunks(stem)), f"the planner prompt lacks {stem}"
    assert all(ordered(runs, "planner", label) for label in ("p-grok", "p-oc", "p-muse"))

    # The Grok fork proposer branches the planner's thread in place.
    planner_thread = pack.launch_session(planner_launch)
    fork_launch = sandbox.only_launch("p-grok")
    assert fork_launch["start"]["options"]["--resume"] == planner_thread and fork_launch["start"]["switches"] == ["--fork-session"]
    assert "--permission-mode=plan" in fork_launch["start"]["argv"] and pack.same_path(fork_launch["start"]["cwd"], sandbox.workspace)

    # opencode and Muse proposers each run in a worktree of their own.
    folders = [pack.launch_workspace(sandbox.only_launch(label)) for label in ("p-oc", "p-muse")]
    assert all(pack.inside(folder, sandbox.tmp) and not pack.inside(folder, sandbox.workspace) for folder in folders)
    assert os.path.normcase(folders[0]) != os.path.normcase(folders[1])

    # Each proposer sees only its own role.
    for label, (name, identity) in zip(("p-grok", "p-oc", "p-muse"), THREE, strict=True):
        prompt = pack.launch_prompt(sandbox.only_launch(label))
        assert identity in prompt and name in prompt
        assert all(other not in prompt for _name, other in THREE if other != identity), f"{label} saw another role"

    # One selector turn over all three blocks, a final selection.
    (selector_launch,) = sandbox.launches(label="selector")
    selector_prompt = pack.launch_prompt(selector_launch)
    for number, (name, _identity) in enumerate(THREE, start=1):
        assert block(pack, number, name, PROPOSALS[name]) in selector_prompt
    assert all(chunk in selector_prompt for chunk in pack.literal_chunks("selection_schema"))
    assert all(ordered(runs, label, "selector") for label in ("p-grok", "p-oc", "p-muse"))

    # The implementer runs once, in place, after the backstop, with only
    # the chosen proposal.
    implementer_launch = sandbox.only_launch("implementer")
    assert "--permission-mode=acceptEdits" in implementer_launch["start"]["argv"] and pack.same_path(implementer_launch["start"]["cwd"], sandbox.workspace)
    implementer_prompt = pack.launch_prompt(implementer_launch)
    for text in (PROPOSALS["ROLE-TWO"], "APPROACH-LAZY", "RATIONALE-RISK", "GUIDANCE-CLI", "ROLE-TWO", pack.TASK):
        assert text in implementer_prompt
    assert PROPOSALS["ROLE-ONE"] not in implementer_prompt and PROPOSALS["ROLE-THREE"] not in implementer_prompt
    (implementer_call,) = runs.calls_of("implementer")
    assert ordered(runs, "selector", "implementer")
    selector_exit = max(runs.position("exit", index) for index in runs.calls_of("selector"))
    backstops = [index for index, item in runs.git_calls() if runs.subcommand(item)[:1] == ["write-tree"] and selector_exit < runs.position("enter", index) and runs.position("exit", index) < runs.position("enter", implementer_call)]
    assert backstops, "the backstop snapshot runs after the selector and before the implementer"

    # The record.
    assert result.failed_stage is None
    assert [role.name for role in result.plan.value.roles] == [name for name, _identity in THREE] and result.plan.text == plan_text
    assert [outcome.text for outcome in result.proposals] == [PROPOSALS[name] for name, _identity in THREE]
    assert result.rounds == () and result.selection.value.proposal == 2 and len(result.selection.turns) == 1
    assert result.implementation.ok and result.implementation.text == "Implemented."
    assert sandbox.status() == {"?? impl.txt"}
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1
    homes = sandbox.home / ".vidbyte" / "grok-homes"
    assert sorted(path.name for path in homes.iterdir()) == [pack.private_home(sandbox.home, sandbox.workspace).name]


@pytest.mark.asyncio
async def test_ten_proposers_narrow_in_one_round_with_repairs_for_bad_answers(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-20 / INV-23 / EC-49 / EC-50: a wrong role count and unoffered
    # numbers each get a repair turn on the same thread; ten proposals
    # give one round with target 2 offered 1 to 10, then a final turn
    # offered only the kept numbers.
    api = compose_api
    sandbox.make_repo()
    ten = roles_of(10)
    planner = steps.bind("grok", plan=True, label="planner", fake={"answers": [{"text": pack.plan_json(roles_of(3))}, {"text": pack.plan_json(ten)}]})
    replies = [{"contains": identity, "text": proposal_text(index)} for index, (_name, identity) in enumerate(ten, start=1)]
    fork = steps.bind("grok", "fork", plan=True, label="fork", fake={"replies": replies})
    selector = steps.bind("grok", plan=True, label="selector", fake={"answers": [
        {"text": pack.round_json([3, 11])}, {"text": pack.round_json([3, 7])}, {"text": pack.selection_json(9)}, {"text": pack.selection_json(7)},
    ]})
    implementer = steps.bind("grok", edits=True, label="implementer")
    roster = api.ensemble.EnsembleRoster(planner=planner, proposers=[fork] * 10, selector=selector, implementer=implementer)
    result = await api.compose.run_ensemble(pack.TASK, roster=roster)
    constants = api.constants

    first_plan, plan_repair = sandbox.launches(label="planner")
    assert plan_repair["start"]["options"]["--resume"] == pack.launch_session(first_plan) and plan_repair["start"]["switches"] == []
    assert all(chunk in pack.launch_prompt(plan_repair) for chunk in pack.longest_literal(constants.COMPOSE_ROLE_COUNT_PROBLEM))
    assert len(result.plan.turns) == 2 and len(result.plan.value.roles) == 10

    forks = sandbox.launches(label="fork")
    assert len(forks) == 10 and sorted(launch["start"].get("reply", -1) for launch in forks) == list(range(10)), "each proposer saw only its own identity"
    assert all(launch["start"]["options"].get("--resume") == pack.launch_session(plan_repair) and launch["start"]["switches"] == ["--fork-session"] for launch in forks)
    assert [outcome.text for outcome in result.proposals] == [proposal_text(index) for index in range(1, 11)]

    turns = sandbox.launches(label="selector")
    assert len(turns) == 4
    selector_thread = pack.launch_session(turns[0])
    assert all(turn["start"]["options"].get("--resume") == selector_thread and turn["start"]["switches"] == [] for turn in turns[1:])
    round_prompt = pack.launch_prompt(turns[0])
    for index, (name, _identity) in enumerate(ten, start=1):
        assert block(pack, index, name, proposal_text(index)) in round_prompt
    assert all(chunk in round_prompt for chunk in pack.literal_chunks("round_schema"))
    assert all(chunk in pack.launch_prompt(turns[1]) for chunk in pack.longest_literal(constants.COMPOSE_KEPT_PROBLEM))
    final_prompt = pack.launch_prompt(turns[2])
    assert block(pack, 3, "ROLE-03", proposal_text(3)) in final_prompt and block(pack, 7, "ROLE-07", proposal_text(7)) in final_prompt
    assert all(proposal_text(index) not in final_prompt for index in range(1, 11) if index not in (3, 7)), "the final turn offers only the kept numbers"
    assert all(chunk in pack.launch_prompt(turns[3]) for chunk in pack.longest_literal(constants.COMPOSE_PROPOSAL_PROBLEM))

    assert len(result.rounds) == 1 and result.rounds[0].value.kept == (3, 7) and len(result.rounds[0].turns) == 2
    assert result.selection.value.proposal == 7 and len(result.selection.turns) == 2
    assert proposal_text(7) in pack.launch_prompt(sandbox.only_launch("implementer"))
    assert result.failed_stage is None and sandbox.leftovers() == [] and sandbox.worktrees() == 1


@pytest.mark.asyncio
async def test_ten_long_proposals_share_a_grok_selectors_room_fairly(compose_api, sandbox, steps, runs, pack) -> None:
    # INV-18 / EC-23: ten 100,000-character proposals into a Grok
    # selector; every proposal keeps the same prefix followed by its
    # truncation note, none is sent as its note alone, role names stay
    # whole, and each prompt fits yet uses its room; the two kept
    # proposals each keep far more, and the implementer more again.
    api = compose_api
    sandbox.make_repo()
    ten = roles_of(10)
    total = api.threads_constants.NATIVE_RESULT_TEXT_MAX_CHARS
    planner = steps.bind("grok", plan=True, label="planner", fake={"text": pack.plan_json(ten)})
    replies = [{"contains": identity, "text": long_proposal(index)} for index, (_name, identity) in enumerate(ten, start=1)]
    fork = steps.bind("grok", "fork", plan=True, label="fork", fake={"replies": replies})
    selector = steps.bind("grok", plan=True, label="selector", fake={"answers": [{"text": pack.round_json([3, 7])}, {"text": pack.selection_json(7)}]})
    implementer = steps.bind("grok", edits=True, label="implementer")
    roster = api.ensemble.EnsembleRoster(planner=planner, proposers=[fork] * 10, selector=selector, implementer=implementer)
    result = await api.compose.run_ensemble(pack.TASK, roster=roster)
    assert result.failed_stage is None
    assert [outcome.text for outcome in result.proposals] == [long_proposal(index) for index in range(1, 11)], "records keep the whole proposals"
    cap = api.threads_constants.NATIVE_ARGV_PROMPT_MAX_CHARS
    round_turn, final_turn = sandbox.launches(label="selector")
    shares = {}
    for name, turn, numbers in (("round", round_turn, tuple(range(1, 11))), ("final", final_turn, (3, 7))):
        prompt = pack.launch_prompt(turn)
        assert cap - 200 <= len(prompt) <= cap, f"the {name} prompt fits and uses its room: {len(prompt)}"
        if sys.platform == "win32":
            assert pack.command_line_units(prompt) <= api.threads_constants.NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS
        kept = {number: cut_length(pack, prompt, number, total) for number in numbers}
        assert len(set(kept.values())) == 1, f"the {name} prompt shares its room unequally: {kept}"
        assert all(f"ROLE-{number:02d}" in prompt for number in numbers), "role names stay whole"
        shares[name] = min(kept.values())
    assert shares["round"] >= 500, f"each of ten proposals keeps real content, not just its note: {shares['round']}"
    assert shares["final"] > 2 * shares["round"], "two kept proposals share the room that ten shared"
    implementer_prompt = pack.launch_prompt(sandbox.only_launch("implementer"))
    assert len(implementer_prompt) <= cap and cut_length(pack, implementer_prompt, 7, total) > shares["final"]


@pytest.mark.asyncio
async def test_no_successful_proposal_stops_before_the_selector_but_the_backstop_runs(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-20 / EC-51 / INV-11 / INV-16: failed_stage PROPOSE, no selector
    # or implementer launch, and the backstop snapshot follows the last
    # proposer.
    api = compose_api
    sandbox.make_repo()
    planner = steps.bind("grok", plan=True, label="planner", fake={"text": pack.plan_json(roles_of(2))})
    fork = steps.bind("grok", "fork", plan=True, label="p-grok", fake={"mode": "key_rejected"})
    opencode = steps.bind("opencode", label="p-oc", fake={"mode": "fail", "vendor_text": "no idea"})
    selector = steps.bind("grok", plan=True, label="selector")
    implementer = steps.bind("grok", edits=True, label="implementer")
    roster = api.ensemble.EnsembleRoster(planner=planner, proposers=[fork, opencode], selector=selector, implementer=implementer)
    result = await api.compose.run_ensemble(pack.TASK, roster=roster)
    assert result.failed_stage is api.enums.EnsembleStage.PROPOSE
    assert len(result.proposals) == 2 and not any(outcome.ok for outcome in result.proposals)
    assert result.rounds == () and result.selection is None and result.implementation is None
    assert sandbox.launches(label="selector") == [] and sandbox.launches(label="implementer") == []
    proposer_exits = [runs.position("exit", index) for label in ("p-grok", "p-oc") for index in runs.calls_of(label)]
    assert runs.position("enter", last_git_index(runs, "write-tree")) > max(proposer_exits), "the backstop snapshot was taken"
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1


@pytest.mark.asyncio
async def test_single_proposer_that_writes_stops_the_ensemble_before_the_implementer(compose_api, sandbox, steps, runs, pack, check_compose_error) -> None:
    # AC-8c / EC-70 / INV-11: one proposer means no round and a final
    # selection offered number 1; the proposer's write is caught by the
    # backstop and the implementer never starts.
    api = compose_api
    sandbox.make_repo()
    planner = steps.bind("grok", plan=True, label="planner", fake={"text": pack.plan_json(roles_of(1))})
    fork = steps.bind("grok", "fork", plan=True, label="p-grok", fake={"text": proposal_text(1), "write_files": {"proposer-was-here.txt": "oops\n"}})
    selector = steps.bind("grok", plan=True, label="selector", fake={"text": pack.selection_json(1)})
    implementer = steps.bind("grok", edits=True, label="implementer")
    roster = api.ensemble.EnsembleRoster(planner=planner, proposers=[fork], selector=selector, implementer=implementer)
    with pytest.raises(api.ThreadComposeError) as caught:
        await api.compose.run_ensemble(pack.TASK, roster=roster)
    error = caught.value
    check_compose_error(error, problem="reader_changed_workspace", workspace=sandbox.workspace, observations=[("changed file", ("proposer-was-here.txt",))])
    assert error.diff.files == ("proposer-was-here.txt",)
    assert isinstance(error.result, api.ensemble.EnsembleResult) and error.result.selection.value.proposal == 1 and error.result.rounds == ()
    (selector_launch,) = sandbox.launches(label="selector")
    assert block(pack, 1, "ROLE-01", proposal_text(1)) in pack.launch_prompt(selector_launch)
    assert sandbox.launches(label="implementer") == [] and runs.calls_of("implementer") == []
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1
