"""FILE: tests/features/browser_agent/test_browser_agent_goal.py

PURPOSE: Proves the goal card: goal and done_when never change, plan and blockers are replaced, progress only grows one item per non-blank line, every refusal leaves the card unchanged and tells the model why, the card rides in every orchestrator call exactly once as it stands after the latest patch, a full progress section answers with progress_full, user text is rendered verbatim even when it looks like a format string, and the stall count follows the D-14 rule over random recheck sequences.
ROLE IN CODEBASE: Goal layer of tests/features/browser_agent/ (spec AC-10, AC-11, AC-32; INV-13, INV-14, INV-17; EC-16, EC-25, EC-37; D-12, D-14; FR-9, FR-10). Exercises vidbyte/agents/browser/goal.py through BrowserAgent.run and, for the two model-based property tests, through BrowserGoal directly with its real collaborators.
ARCHITECTURE NOTE: Orchestrator-level tests read the card from the system string the scripted runner received (card_section asserts it appears exactly once). The property tests drive BrowserGoal.patch and BrowserGoal.rechecked against a small reference model with a seeded random.Random, because hypothesis is not a dependency.
FUNCTION INVENTORY: test_patch_goal_changes_only_plan_progress_and_blockers_and_every_call_shows_the_latest_card (AC-10, AC-11, INV-13, INV-14); test_an_over_cap_patch_is_refused_with_the_patch_refused_leaf_and_changes_nothing (EC-16, D-12); test_a_progress_line_that_no_longer_fits_returns_progress_full_and_changes_nothing (AC-32, EC-37); test_user_text_is_rendered_verbatim_even_when_it_looks_like_a_format_string (INV-13, EC-25); test_patch_matches_a_reference_model_over_random_sequences (INV-13, D-12); test_stall_count_matches_the_d14_rule_over_random_recheck_sequences (INV-17, D-14).
COMMON MODIFICATION PATTERNS: Raise SEQUENCES or STEPS for a deeper search; keep the seeds fixed so a failure reproduces. Take every bound from vidbyte.lib.constants.browser.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not generate text with leading or trailing whitespace, blank plan or blockers text, or a None verdict payload in the property tests: the spec does not say how those are normalised, so a test of them would test a guess. 3. Do not assert how the card lays its sections out; match the goal_card leaf with template_regex.
KNOWN EDGE CASES: The spec bounds progress "in total" without fixing whether separators count, so the AC-32 fill leaves room for a one-character separator per line and the line that must not fit is longer than the slack under either reading. An invalid section may be refused by the tool's own schema check before patch_goal runs; either way it is an error result and the card is unchanged.
RELATED DOCS: tests/features/browser_agent/FEATURE.md; docs/spec/browser-agent/spec.md sections 6.1, 6.2, 6.3, 8.1 (D-12, D-14) and 9.1.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent/test_browser_agent_goal.py -q
"""

from __future__ import annotations

import random
import string
from typing import Any

from tests.features.browser_agent.browser_agent_fixtures import (
    DONE_WHEN,
    NAME,
    RECHECK,
    TASK,
    FakeBrowserServers,
    ScriptedModel,
    build_agent,
    build_settings,
    card,
    card_section,
    installed,
    is_error,
    prompt_text,
    reply,
    seen_text,
    template_regex,
    tool_call,
    tool_results,
    verdict,
    worker,
)

FINAL = "FINAL-ANSWER: the card holds what was found."
DONE = verdict("done", "Nothing is missing.")
SEQUENCES = 40
STEPS = 25
LINE_ALPHABET = string.ascii_letters + string.digits + "-:/.,()é€"


def _patch(section: str, text: str) -> Any:
    return tool_call("patch_goal", {"section": section, "text": text})


def _run_patches(patches: list[Any], **fields: Any) -> tuple[Any, ScriptedModel]:
    agent = build_agent(**fields)
    model = ScriptedModel({NAME: [*patches, reply(FINAL)], RECHECK: [DONE]})
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
    model.assert_complete()
    return agent, model


def _newest_result(model: ScriptedModel, call_index: int) -> str:
    """The newest tool result content in the orchestrator's `call_index`-th call (0-based)."""
    return tool_results(model.calls_by(NAME)[call_index])[-1][1]


# ---------------------------------------------------------------- patch_goal through the orchestrator


def test_patch_goal_changes_only_plan_progress_and_blockers_and_every_call_shows_the_latest_card() -> None:
    """AC-10, AC-11, INV-13, INV-14: goal and done_when patches are errors that leave the card as it was; plan is replaced; progress gains one item per non-blank line across two patches, in order; each next call carries the patched card exactly once."""
    patches = [
        _patch("goal", "Find one program."),
        _patch("done_when", "One program is listed."),
        _patch("plan", "Search the accelerator directories first."),
        _patch("plan", "Then open each program page and read its deadline."),
        _patch("progress", "Seedcamp - https://seedcamp.com/apply - closes 30 November\n\n   \nAntler - https://www.antler.co/apply - rolling"),
        _patch("progress", "Entrepreneur First - https://www.joinef.com - closes 1 December"),
        _patch("blockers", "Techstars asks for a login."),
    ]
    agent, model = _run_patches(patches)
    calls = model.calls_by(NAME)
    assert len(calls) == len(patches) + 1
    sections = [card_section(call.system) for call in calls]
    # The refused goal and done_when patches are errors and the card is exactly as before them.
    assert is_error(_newest_result(model, 1)) and is_error(_newest_result(model, 2))
    assert sections[0] == sections[1] == sections[2]
    assert not any("Find one program." in section or "One program is listed." in section for section in sections)
    # Accepted patches show on the very next call.
    assert "Search the accelerator directories first." in sections[3]
    assert "Then open each program page and read its deadline." in sections[4] and "Search the accelerator directories first." not in sections[4]
    assert "Antler - https://www.antler.co/apply - rolling" in sections[5]
    assert "Entrepreneur First - https://www.joinef.com - closes 1 December" in sections[6]
    assert "Techstars asks for a login." in sections[7]
    for index in (3, 4, 5, 6, 7):
        assert not is_error(_newest_result(model, index)), f"accepted patch {index} returned an error"
    goal = agent.response.goal
    assert (goal.goal, goal.done_when) == (TASK, DONE_WHEN)
    assert goal.plan == "Then open each program page and read its deadline."
    assert goal.progress == (
        "Seedcamp - https://seedcamp.com/apply - closes 30 November",
        "Antler - https://www.antler.co/apply - rolling",
        "Entrepreneur First - https://www.joinef.com - closes 1 December",
    )
    assert goal.blockers == "Techstars asks for a login."
    assert template_regex(prompt_text("goal_card"), goal=TASK, plan=goal.plan, blockers=goal.blockers).search(sections[7]), "the card is not the goal_card leaf"


def test_an_over_cap_patch_is_refused_with_the_patch_refused_leaf_and_changes_nothing() -> None:
    """EC-16, D-12: a progress line over BROWSER_ITEM_MAX_CHARS, a plan over BROWSER_PLAN_MAX_CHARS, and blockers over BROWSER_BLOCKERS_MAX_CHARS are each refused with the patch_refused leaf, and the card stays empty."""
    from vidbyte.lib.constants.browser import BROWSER_BLOCKERS_MAX_CHARS, BROWSER_ITEM_MAX_CHARS, BROWSER_PLAN_MAX_CHARS

    patches = [
        _patch("progress", "Seedcamp - https://seedcamp.com/apply\n" + "x" * (BROWSER_ITEM_MAX_CHARS + 1)),
        _patch("plan", "p" * (BROWSER_PLAN_MAX_CHARS + 1)),
        _patch("blockers", "b" * (BROWSER_BLOCKERS_MAX_CHARS + 1)),
    ]
    agent, model = _run_patches(patches)
    refused = template_regex(prompt_text("patch_refused"))
    for index in (1, 2, 3):
        content = _newest_result(model, index)
        assert is_error(content) and refused.search(content), f"patch {index} was not refused with patch_refused: {content[:200]!r}"
    goal = agent.response.goal
    assert (goal.plan, goal.progress, goal.blockers) == ("", (), ""), "a refused patch changed the card (a refused progress patch must add none of its lines)"


def test_a_progress_line_that_no_longer_fits_returns_progress_full_and_changes_nothing() -> None:
    """AC-32, EC-37: with progress within one line of BROWSER_PROGRESS_MAX_CHARS, a further line returns the progress_full leaf as an error and the card keeps exactly what it had."""
    from vidbyte.lib.constants.browser import BROWSER_ITEM_MAX_CHARS, BROWSER_PROGRESS_MAX_CHARS

    line_chars = BROWSER_ITEM_MAX_CHARS - 2
    count = BROWSER_PROGRESS_MAX_CHARS // (line_chars + 1)
    lines = [f"{index:04d} " + "p" * (line_chars - 5) for index in range(count)]
    filled = sum(len(line) + 1 for line in lines)
    assert BROWSER_PROGRESS_MAX_CHARS - BROWSER_ITEM_MAX_CHARS < filled <= BROWSER_PROGRESS_MAX_CHARS, "the fill is not within one line of the cap"
    extra = "Z" * BROWSER_ITEM_MAX_CHARS
    # The spec does not say whether line separators count toward the total, so the extra line must overflow even without them.
    assert sum(len(line) for line in lines) + len(extra) > BROWSER_PROGRESS_MAX_CHARS, "the extra line would still fit"
    agent, model = _run_patches([_patch("progress", "\n".join(lines)), _patch("progress", extra)])
    assert not is_error(_newest_result(model, 1)), "the fill itself was refused"
    content = _newest_result(model, 2)
    leaf = prompt_text("progress_full").strip()
    assert is_error(content) and leaf[:200] in content, f"not the progress_full leaf: {content[:300]!r}"
    assert agent.response.goal.progress == tuple(lines)


def test_user_text_is_rendered_verbatim_even_when_it_looks_like_a_format_string() -> None:
    """INV-13, EC-25: a task, an episode task, and a progress line holding braces, percent signs, newlines and non-ASCII text reach the card, the worker, and the recheck verbatim."""
    task = "Find {programs} with deadlines {0} and {{escaped}} - 100% verbatim\nsecond line: Zürich, São Paulo, 東京"
    episode_task = "Open https://example.com/{slug}?q={query} and read {deadline}"
    progress = "Station F {Founders} - https://stationf.co - closes {date} 50%"
    agent = build_agent()
    model = ScriptedModel(
        {
            NAME: [tool_call("run_episode", {"task": episode_task, "done_when": "The {deadline} is read."}), _patch("progress", progress), reply(FINAL)],
            worker(1): [card("done", "Read {deadline}.")],
            RECHECK: [DONE],
        }
    )
    with installed(model, FakeBrowserServers()):
        agent.run(task)
    model.assert_complete()
    assert agent.response.goal.goal == task
    assert task in card_section(model.first_call(NAME).system)
    assert progress in card_section(model.calls_by(NAME)[2].system)
    assert episode_task in model.first_call(worker(1)).prompt
    recheck = seen_text(model.first_call(RECHECK))
    assert task in recheck and progress in recheck


# ---------------------------------------------------------------- model-based property tests


def _line(sample: random.Random, low: int, high: int) -> str:
    """A progress line with no leading or trailing whitespace."""
    body = "".join(sample.choice(LINE_ALPHABET + "  ") for _ in range(sample.randint(low, high)))
    return f"L{body}x".replace("\n", " ")


def _progress_text(sample: random.Random, *, overlong: bool, item_max: int) -> tuple[str, list[str]]:
    lines = [_line(sample, 1, 120) for _ in range(sample.randint(1, 4))]
    if overlong:
        lines.insert(sample.randrange(len(lines) + 1), "O" * (item_max + sample.randint(1, 40)))
    pieces: list[str] = []
    for line in lines:
        pieces.append(line)
        if sample.random() < 0.3:
            pieces.append(sample.choice(("", "   ", "\t")))
    return "\n".join(pieces), lines


def test_patch_matches_a_reference_model_over_random_sequences() -> None:
    """INV-13, D-12: over seeded random patch sequences, BrowserGoal.patch replaces plan and blockers, appends progress per non-blank line, refuses whole patches that break a cap or name another section, never changes goal or done_when, and never mutates an earlier card."""
    from vidbyte.agents.browser.events import BrowserAgentEvents
    from vidbyte.agents.browser.goal import BrowserGoal
    from vidbyte.agents.browser.response import BrowserResponse
    from vidbyte.lib.constants.browser import BROWSER_BLOCKERS_MAX_CHARS, BROWSER_ITEM_MAX_CHARS, BROWSER_PLAN_MAX_CHARS
    from vidbyte.lib.dataclasses.browser import BrowserGoalCard
    from vidbyte.lib.enums import BrowserGoalSection
    from vidbyte.lib.errors import ConfigurationError

    caps = {"plan": BROWSER_PLAN_MAX_CHARS, "blockers": BROWSER_BLOCKERS_MAX_CHARS}
    sample = random.Random(20261017)
    settings = build_settings()
    for _ in range(SEQUENCES):
        response = BrowserResponse()
        response.start(TASK)
        events = BrowserAgentEvents(None)
        events.start()
        goal = BrowserGoal(BrowserGoalCard(goal=TASK, done_when=DONE_WHEN), settings, response, events)
        expected: dict[str, Any] = {"plan": "", "progress": (), "blockers": ""}
        cards: list[tuple[Any, tuple[Any, ...]]] = []
        any_accepted = False
        for _ in range(STEPS):
            before = goal.card
            cards.append((before, (before.goal, before.done_when, before.plan, before.progress, before.blockers)))
            roll = sample.random()
            accepted = True
            if roll < 0.1:
                section: Any = sample.choice(("goal", "done_when", "facts"))
                text = _line(sample, 1, 40)
                accepted = False
            elif roll < 0.55:
                section = "progress"
                overlong = sample.random() < 0.15
                text, lines = _progress_text(sample, overlong=overlong, item_max=BROWSER_ITEM_MAX_CHARS)
                accepted = not overlong
                if accepted:
                    expected["progress"] = (*expected["progress"], *lines)
            else:
                section = sample.choice(("plan", "blockers"))
                overlong = sample.random() < 0.15
                text = "T" * (caps[section] + sample.randint(1, 30)) if overlong else _line(sample, 1, 300)
                accepted = not overlong
                if accepted:
                    expected[section] = text
            if section in {"plan", "progress", "blockers"} and sample.random() < 0.5:
                section = BrowserGoalSection(section)
            if accepted:
                after = goal.patch(section, text)
                assert after == goal.card
                any_accepted = True
            else:
                try:
                    goal.patch(section, text)
                except ConfigurationError:
                    pass
                else:
                    raise AssertionError(f"patch({section!r}, {text[:40]!r}...) was accepted but must be refused")
                assert goal.card == before, "a refused patch changed the card"
            current = goal.card
            assert (current.goal, current.done_when) == (TASK, DONE_WHEN)
            assert (current.plan, current.progress, current.blockers) == (expected["plan"], expected["progress"], expected["blockers"])
            if any_accepted:
                # Section 9.1: each accepted patch copies the card to agent.response.goal, and a refusal leaves it as it was.
                assert response.state.goal == current, "agent.response.goal is not the current card"
        for old, fields in cards:
            assert (old.goal, old.done_when, old.plan, old.progress, old.blockers) == fields, "an earlier card was mutated"


def test_stall_count_matches_the_d14_rule_over_random_recheck_sequences() -> None:
    """INV-17, D-14: over seeded random sequences of progress patches and verdicts, each recheck's stall count is +1 on `stalled` or on `continue` with progress unchanged since the previous recheck (the first compares with the empty start), 0 otherwise, and stalled() turns on at max_stalls."""
    from vidbyte.agents.browser.events import BrowserAgentEvents
    from vidbyte.agents.browser.goal import BrowserGoal
    from vidbyte.agents.browser.response import BrowserResponse
    from vidbyte.lib.dataclasses.browser import BrowserGoalCard, BrowserVerdictPayload

    sample = random.Random(1714)
    for _ in range(SEQUENCES):
        max_stalls = sample.randint(1, 4)
        response = BrowserResponse()
        response.start(TASK)
        events = BrowserAgentEvents(None)
        events.start()
        goal = BrowserGoal(BrowserGoalCard(goal=TASK, done_when=DONE_WHEN), build_settings(max_stalls=max_stalls), response, events)
        stalls = 0
        compared: tuple[str, ...] = ()
        rechecks = 0
        lines = 0
        for _ in range(STEPS):
            if sample.random() < 0.35:
                lines += 1
                goal.patch("progress", f"Program {lines} - https://example.com/{lines}")
                continue
            value = sample.choice(("continue", "continue", "done", "stalled"))
            at_finish = sample.random() < 0.5
            result = goal.rechecked(BrowserVerdictPayload(verdict=value, gap=f"Gap {rechecks}."), at_finish=at_finish)
            rechecks += 1
            progress = goal.card.progress
            stalls = stalls + 1 if value == "stalled" or (value == "continue" and progress == compared) else 0
            compared = progress
            assert result is not None
            assert (result.verdict, result.gap, result.at_finish, result.stalls) == (value, f"Gap {rechecks - 1}.", at_finish, stalls)
            assert goal.stalled() is (stalls >= max_stalls), f"stalls={stalls}, max_stalls={max_stalls}"
        assert [item.stalls for item in response.state.rechecks][-1:] == ([stalls] if rechecks else [])
        assert len(response.state.rechecks) == rechecks
