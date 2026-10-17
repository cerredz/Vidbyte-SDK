"""FILE: tests/features/browser_agent/test_browser_agent_recheck.py

PURPOSE: Proves the goal checks: a recheck is a fresh, tool-free agent that sees only the goal, done criteria and progress; a finish attempt by text or isDone ends the run only on `done` (or when the recheck is unavailable), and otherwise appends exactly one gap message and shows the verdict on the card; periodic rechecks follow recheck_every and never end a run; repeated stalls stop the run before another model call with the card as output; done_when is derived by one call before the run when not given, and a failure there stops the run before any browser action.
ROLE IN CODEBASE: Recheck layer of tests/features/browser_agent/ (spec AC-12, AC-13, AC-14, AC-15, AC-16; INV-14..INV-18; EC-17, EC-18, EC-19, EC-36; D-13, D-14, D-15; FR-11..FR-14). Exercises vidbyte/agents/browser/goal.py (BrowserGoalCheck) and the runtime's _continue_finish_attempt, _after_tool_iteration and _budget_stop hooks through BrowserAgent.run.
ARCHITECTURE NOTE: Rechecks are scripted by their fixed name ("vc-scout-recheck") and the done-when agent by "vc-scout-done-when"; ordering between agents is read from ScriptedModel.events, and event timing from EventLog's orchestrator call count at emit time.
FUNCTION INVENTORY: test_a_recheck_sees_only_the_goal_done_when_and_progress (AC-12, INV-15, D-13); test_a_refused_finish_appends_one_gap_message_and_the_next_call_shows_the_verdict (AC-13, INV-14, INV-16, EC-36); test_periodic_rechecks_follow_recheck_every_and_never_end_the_run (AC-14, INV-18); test_stalls_stop_the_run_before_another_model_call_with_the_card_as_output (AC-15, INV-17, EC-18, FR-14); test_done_when_is_derived_once_before_the_first_orchestrator_call_only_when_not_given (AC-16, FR-11, D-15); test_a_failing_or_off_schema_recheck_fails_open (EC-17, D-13); test_a_failing_done_when_call_stops_the_run_before_any_browser_action (EC-19, D-15).
COMMON MODIFICATION PATTERNS: Script a recheck that never changes its mind with forever(verdict(...)); count calls with ScriptedModel.calls_by to prove a stop happened before a further call.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not assert the order of the gap message and the model's own refused answer on the final-text path; EC-36 records that order as a limitation of the loop on main. 3. Do not assert whether a finish recheck resets the recheck_every counter; the spec does not say.
KNOWN EDGE CASES: Every BaseAgent's catalog gets the loop's internal isDone tool, so "its tool list is empty" (AC-12) is checked as "no tool but isDone". The recheck's verdict is shown on the card through the goal_card leaf's {verdict} and {gap} placeholders, so the card checks use template_regex with those fields known.
RELATED DOCS: tests/features/browser_agent/FEATURE.md; docs/spec/browser-agent/spec.md sections 6.1, 6.2, 6.3 and 8.1.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent/test_browser_agent_recheck.py -q
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.features.browser_agent.browser_agent_fixtures import (
    ACTION_COMMAND,
    DONE_WHEN,
    DONE_WHEN_AGENT,
    NAME,
    RECHECK,
    SYSTEM_PROMPT,
    TASK,
    EventLog,
    FakeBrowserServers,
    ScriptedModel,
    build_agent,
    card,
    card_section,
    criteria,
    distinctive_line,
    fail,
    find_error,
    forever,
    installed,
    prompt_text,
    reply,
    seen_text,
    template_regex,
    tool_call,
    verdict,
    worker,
)
from vidbyte.lib.errors import OutputSchemaViolationError, ProviderRequestError

FINAL = "FINAL-ANSWER: twenty programs are listed with URLs and deadlines."
PROGRESS_LINE = "Seedcamp - https://seedcamp.com/apply - closes 30 November"
GAP = "Only one of the twenty programs has a deadline recorded."
DONE = verdict("done", "Nothing is missing.")
EPISODE = {"task": "Open https://seedcamp.com/apply and read the application deadline.", "done_when": "The deadline is read from the page."}


def _progress(text: str = PROGRESS_LINE) -> Any:
    return tool_call("patch_goal", {"section": "progress", "text": text})


def _card_shows(system: str, value: str, gap: str) -> bool:
    return bool(template_regex(prompt_text("goal_card"), verdict=value, gap=gap).search(card_section(system)))


def test_a_recheck_sees_only_the_goal_done_when_and_progress() -> None:
    """AC-12, INV-15, D-13: the finish recheck's call holds the goal verbatim, the done criteria and the progress lines, no orchestrator message or rule, and no tool but isDone."""
    agent = build_agent()
    model = ScriptedModel(
        {
            NAME: [tool_call("firecrawl_search", {"query": "seed accelerators accepting applications"}), _progress(), reply(FINAL)],
            RECHECK: [DONE],
        }
    )
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
    model.assert_complete()
    (call,) = model.calls_by(RECHECK)
    text = seen_text(call)
    assert call.messages == [], "the recheck inherited a conversation"
    assert TASK in text and DONE_WHEN[0] in text and PROGRESS_LINE in text
    for leaked in (FINAL, "seed accelerators accepting applications", "Seedcamp https://seedcamp.com (query", SYSTEM_PROMPT):
        assert leaked not in text, f"the recheck saw orchestrator context: {leaked!r}"
    assert distinctive_line("orchestrator_system_prompt", "recheck_system_prompt") not in call.system
    assert distinctive_line("recheck_system_prompt", "orchestrator_system_prompt") in call.system
    assert set(call.tools) <= {"isDone"}, f"the recheck was offered tools: {call.tools}"
    assert template_regex(prompt_text("recheck_prompt"), goal=TASK).fullmatch(call.prompt.strip())


@pytest.mark.parametrize("finish", ("final_text", "is_done"))
def test_a_refused_finish_appends_one_gap_message_and_the_next_call_shows_the_verdict(finish: str) -> None:
    """AC-13, INV-14, INV-16, EC-36: a `continue` recheck refuses the first finish, appends exactly one continue_prompt message carrying the gap, and the next call's card shows the verdict and gap; the second recheck is fresh and its `done` ends the run with final_response or is_done."""

    def attempt(text: str) -> Any:
        return reply(text) if finish == "final_text" else tool_call("isDone", {"final_answer": text})

    log = EventLog()
    agent = build_agent(on_event=log)
    model = ScriptedModel({NAME: [_progress(), attempt("FIRST-ATTEMPT: one program found."), attempt(FINAL)], RECHECK: [verdict("continue", GAP), DONE]})
    with installed(model, FakeBrowserServers()):
        result = agent.run(TASK)
    model.assert_complete()
    calls = model.calls_by(NAME)
    assert len(calls) == 3
    third = calls[2]
    gap_messages = [m for m in third.messages if m.get("role") == "user" and GAP in str(m.get("content"))]
    assert len(gap_messages) == 1, f"expected one gap message, got {len(gap_messages)}"
    assert template_regex(prompt_text("continue_prompt"), verdict="continue", gap=GAP).fullmatch(str(gap_messages[0]["content"]).strip())
    assert _card_shows(third.system, "continue", GAP), "the next call's card does not show the continue verdict and gap"
    second_recheck = model.calls_by(RECHECK)[1]
    assert second_recheck.messages == [] and GAP not in seen_text(second_recheck), "the second recheck is not a fresh agent"
    assert result.content == FINAL
    assert agent.response.stop_reason == finish
    assert [(item.verdict, item.gap, item.at_finish) for item in agent.response.rechecks] == [("continue", GAP, True), ("done", "Nothing is missing.", True)]
    assert agent.response.rechecks[0].stalls == 0, "a continue with new progress is not a stall"
    assert log.kinds()[-1] == "run_finished"


def test_periodic_rechecks_follow_recheck_every_and_never_end_the_run() -> None:
    """AC-14, INV-18: with recheck_every=2 a recheck runs after the 2nd and the 4th episode, the next orchestrator call's card shows the latest verdict, and a periodic `done` does not end the run."""
    agent = build_agent(recheck_every=2, max_stalls=5)
    model = ScriptedModel(
        {
            NAME: [tool_call("run_episode", EPISODE)] * 4 + [reply(FINAL)],
            **{worker(index): [card("done", f"Read page {index}.")] for index in range(1, 5)},
            RECHECK: [verdict("continue", GAP), verdict("done", "Looks complete."), DONE],
        }
    )
    with installed(model, FakeBrowserServers()):
        result = agent.run(TASK)
    model.assert_complete()
    assert model.position(f"{worker(2)} answered 1") < model.position(f"{RECHECK} call 1") < model.position(f"{worker(3)} call 1")
    assert model.position(f"{worker(4)} answered 1") < model.position(f"{RECHECK} call 2") < model.position(f"{NAME} call 5")
    calls = model.calls_by(NAME)
    assert len(calls) == 5, "a periodic recheck ended the run"
    assert not _card_shows(calls[1].system, "continue", GAP)
    assert _card_shows(calls[2].system, "continue", GAP) and _card_shows(calls[3].system, "continue", GAP)
    assert _card_shows(calls[4].system, "done", "Looks complete.") and GAP not in card_section(calls[4].system)
    assert [(item.verdict, item.at_finish) for item in agent.response.rechecks] == [("continue", False), ("done", False), ("done", True)]
    assert result.content == FINAL and agent.response.stop_reason == "final_response"


@pytest.mark.parametrize(("patched", "orchestrator_calls"), ((True, 4), (False, 2)), ids=("progress-once", "no-progress"))
def test_stalls_stop_the_run_before_another_model_call_with_the_card_as_output(patched: bool, orchestrator_calls: int) -> None:
    """AC-15, INV-17, EC-18, FR-14: with max_stalls=2 and a recheck that keeps saying `continue` while progress stands still, the run stops with goal_stalled before a further model call, its output is the stalled_output leaf holding the card, and the last event is run_stopped; the first recheck compares with the empty progress the run started with."""
    log = EventLog()
    agent = build_agent(max_stalls=2, on_event=log)
    opening = [_progress()] if patched else []
    model = ScriptedModel({NAME: [*opening, forever(reply("FINISHED: one program."))], RECHECK: [forever(verdict("continue", GAP))]})
    with installed(model, FakeBrowserServers()):
        result = agent.run(TASK)
    model.assert_complete()
    assert len(model.calls_by(NAME)) == orchestrator_calls
    assert len(model.calls_by(RECHECK)) == orchestrator_calls - (1 if patched else 0)
    assert agent.response.stop_reason == "goal_stalled"
    assert result.metadata.get("stop_reason") == "goal_stalled"
    assert template_regex(prompt_text("stalled_output")).fullmatch(result.content.strip())
    assert TASK in result.content and (PROGRESS_LINE in result.content) is patched
    assert [item.stalls for item in agent.response.rechecks] == ([0, 1, 2] if patched else [1, 2])
    kinds = log.kinds()
    assert kinds[-1] == "run_stopped" and "run_finished" not in kinds


def test_done_when_is_derived_once_before_the_first_orchestrator_call_only_when_not_given() -> None:
    """AC-16, FR-11, D-15: with done_when=() one done-when call turns the task into criteria before the first orchestrator call, they become the card's done_when, and goal_set follows; with done_when given no such call is made."""
    derived = ("Twenty programs are listed with their application URL.", "Each listed program has an application deadline.")
    log = EventLog()
    model = ScriptedModel({DONE_WHEN_AGENT: [criteria(*derived)], NAME: [reply(FINAL)], RECHECK: [DONE]})
    log.model = model
    agent = build_agent(done_when=(), on_event=log)
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
    model.assert_complete()
    assert len(model.calls_by(DONE_WHEN_AGENT)) == 1
    assert TASK in seen_text(model.first_call(DONE_WHEN_AGENT))
    assert model.position(f"{DONE_WHEN_AGENT} answered 1") < model.position(f"{NAME} call 1")
    assert agent.response.goal.done_when == derived
    first_card = card_section(model.first_call(NAME).system)
    assert all(item in first_card for item in derived)
    assert all(item in seen_text(model.first_call(RECHECK)) for item in derived)
    kinds = log.kinds()
    assert kinds.index("run_started") < kinds.index("goal_set")
    assert log.calls_at("goal_set") == [0], "goal_set did not come before the first orchestrator call"
    # With done_when given, nobody derives it.
    given = ScriptedModel({NAME: [reply(FINAL)], RECHECK: [DONE]})
    with installed(given, FakeBrowserServers()):
        build_agent().run(TASK)
    given.assert_complete()
    assert DONE_WHEN_AGENT not in given.agents_called()


@pytest.mark.parametrize(
    "recheck",
    (
        pytest.param([fail(ProviderRequestError("upstream returned 503", provider="openai", status_code=503))], id="provider-error"),
        pytest.param([forever(reply("Looks done to me, I think."))], id="off-schema"),
    ),
)
def test_a_failing_or_off_schema_recheck_fails_open(recheck: list[Any]) -> None:
    """EC-17, D-13: when the recheck's model fails or answers off-schema, the finish is accepted, goal_rechecked reports unavailable, and no recheck result is recorded."""
    log = EventLog()
    agent = build_agent(on_event=log)
    model = ScriptedModel({NAME: [reply(FINAL)], RECHECK: recheck})
    with installed(model, FakeBrowserServers()):
        result = agent.run(TASK)
    model.assert_complete()
    assert result.content == FINAL and agent.response.stop_reason == "final_response"
    assert len(model.calls_by(NAME)) == 1
    assert agent.response.rechecks == []
    (rechecked,) = log.of("goal_rechecked")
    assert "unavailable" in rechecked.detail.lower(), rechecked.detail


@pytest.mark.parametrize(
    ("step", "expected"),
    (
        pytest.param(fail(ProviderRequestError("upstream returned 503", provider="openai", status_code=503)), ProviderRequestError, id="provider-error"),
        pytest.param(forever(reply("Done when it is done.")), OutputSchemaViolationError, id="off-schema"),
    ),
)
def test_a_failing_done_when_call_stops_the_run_before_any_browser_action(step: Any, expected: type[BaseException]) -> None:
    """EC-19, D-15: with done_when=() a failing or off-schema done-when call raises out of the run before any orchestrator call, episode, or browser action."""
    log = EventLog()
    agent = build_agent(done_when=(), on_event=log)
    model = ScriptedModel({DONE_WHEN_AGENT: [step]})
    servers = FakeBrowserServers()
    with installed(model, servers), pytest.raises(Exception) as raised:
        agent.run(TASK)
    assert find_error(raised.value, expected) is not None, f"{expected.__name__} is not in the raised chain: {raised.value!r}"
    assert NAME not in model.agents_called(), "the orchestrator was called before done_when existed"
    assert servers.calls_to(ACTION_COMMAND) == []
    assert log.of("episode_started") == [] and log.of("goal_set") == []
