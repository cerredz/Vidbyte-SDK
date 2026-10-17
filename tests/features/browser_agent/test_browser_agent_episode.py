"""FILE: tests/features/browser_agent/test_browser_agent_episode.py

PURPOSE: Proves the run_episode tool and its worker: the orchestrator never holds an ACTION tool and a worker holds only them; the action cap, the per-tool screenshot cap, the per-tool observation window and the worker history trim hold; every non-cancelled episode returns one capped card and records one result, including stuck cards built from a cap stop, a schema miss, or a provider error; cancellation propagates; ready_to_submit is only recorded; a done card carries the recipe of its successful calls; episodes run one at a time; only the card text reaches the orchestrator; and the developer's permission policy binds every worker.
ROLE IN CODEBASE: Episode layer of tests/features/browser_agent/ (spec AC-5, AC-7, AC-8, AC-9, AC-17, AC-26, AC-27, AC-31; INV-5..INV-12, INV-19; EC-11..EC-15, EC-31, EC-34; D-8, D-9, D-10, D-16, D-17, D-24, D-25, D-27; T-2, T-6). Exercises vidbyte/agents/browser/episode.py, tools.py and runtime.py through BrowserAgent.run / arun.
ARCHITECTURE NOTE: Workers are scripted by name ("vc-scout-episode-<n>") and their browser calls reach FakeBrowserServers, so every count here is a count of real tools/call requests, and every stuck card is built from the worker's real loop metadata. Ordering checks yield to the event loop with asyncio.sleep(0); nothing waits on the clock.
FUNCTION INVENTORY: test_orchestrator_never_holds_action_tools_and_workers_hold_only_them (AC-5, INV-5, INV-7, D-24); test_action_cap_stops_the_worker_and_returns_a_stuck_card_with_evidence (AC-7, INV-9, INV-12, EC-11); test_a_call_past_the_action_cap_in_the_same_turn_is_not_executed (INV-9); test_a_second_screenshot_is_denied_in_context_and_the_worker_finishes_its_card (AC-8, INV-10); test_screenshot_cap_counts_each_screenshot_tool_case_insensitively_and_spares_other_tools (INV-10, A-1); test_older_observations_are_cut_and_the_newest_is_whole (AC-9, INV-11); test_worker_history_stays_within_its_token_cap_with_whole_call_groups (AC-31, INV-11); test_a_free_text_worker_reply_becomes_a_stuck_card_with_evidence (EC-12, INV-12); test_a_worker_provider_error_becomes_a_stuck_card_and_the_run_continues (AC-27, EC-13, D-27); test_cancelling_during_an_episode_propagates_and_records_no_card (AC-27, EC-14); test_ready_to_submit_is_recorded_and_nothing_acts_on_it (AC-17, INV-19); test_a_done_card_records_the_recipe_of_successful_calls_and_the_event_names_only_the_count (AC-26, D-17, EC-31, T-6); test_an_oversized_worker_card_is_capped_on_the_record_and_in_the_orchestrator_view (INV-6, D-25, section 9.1); test_two_episodes_in_one_turn_run_one_after_the_other_in_call_order (INV-8, EC-15); test_only_the_card_text_reaches_the_orchestrator (INV-6); test_the_developer_permission_policy_binds_every_worker (T-2, D-16); test_each_role_is_enforced_by_the_catalog_not_by_the_prompt (EC-34, INV-5, INV-7).
COMMON MODIFICATION PATTERNS: Give a fake tool distinct, long results with FakeBrowserServers.add when a test needs to tell observations apart. Take every bound from vidbyte.lib.constants.browser.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not assert on mock calls; count tools/call requests the fake server received. 3. Do not raise AssertionError inside a scripted worker step: the worker wraps it into an AgentExecutionError and the episode tool turns it into a stuck card, hiding the failure; record a flag and assert in the test body.
KNOWN EDGE CASES: Every BaseAgent's catalog gets the loop's internal isDone tool, so a worker's offered set is the ACTION tools plus isDone (AC-5's "only the ACTION tools" is read as "no other non-internal tool"). A worker's provider error reaches the episode tool wrapped in AgentExecutionError, so the stuck card's error type name may be the wrapper's or the cause's; the test accepts either and checks the summary renders the same name.
RELATED DOCS: tests/features/browser_agent/FEATURE.md; docs/spec/browser-agent/spec.md sections 6.1, 6.2, 6.3, 8.1 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent/test_browser_agent_episode.py -q
"""

from __future__ import annotations

import asyncio
import itertools
import json
from collections.abc import Mapping
from typing import Any

import pytest

from tests.features.browser_agent.browser_agent_fixtures import (
    ACTION_COMMAND,
    ACTION_TOOLS,
    FETCH_COMMAND,
    NAME,
    RECHECK,
    SCREENSHOT_DATA,
    SYSTEM_PROMPT,
    TASK,
    EventLog,
    FakeBrowserServers,
    ModelCall,
    ScriptedModel,
    build_agent,
    card,
    content_tokens,
    distinctive_line,
    error_result,
    fail,
    forever,
    image_result,
    installed,
    int_token,
    is_error,
    prompt_text,
    reply,
    seen_text,
    template_regex,
    text_result,
    tool_call,
    tool_calls,
    tool_results,
    unpaired,
    verdict,
    worker,
)
from vidbyte import tool
from vidbyte.lib.errors import ProviderRequestError

FINAL = "FINAL-ANSWER: the episode cards are recorded."
EPISODE = {"task": "Open https://seedcamp.com/apply and read the application deadline.", "done_when": "The deadline is read from the page."}
SECOND_EPISODE = {"task": "Open https://www.antler.co/apply and read the application deadline.", "done_when": "The deadline is read from the page."}
DONE = verdict("done", "Nothing is missing.")


@tool(name="note_lead")
def note_lead(name: str) -> str:
    """Remember the name of a program that looks promising."""
    return f"noted {name}"


def _letters(count: int, start: int = 0) -> str:
    return "".join(chr(ord("a") + (start + index) % 26) for index in range(count))


def _one_episode(worker_steps: list[Any], *, orchestrator_after: list[Any] | None = None) -> dict[str, list[Any]]:
    return {
        NAME: [tool_call("run_episode", EPISODE), *(orchestrator_after or [reply(FINAL)])],
        worker(1): worker_steps,
        RECHECK: [DONE],
    }


# ---------------------------------------------------------------- catalogs (INV-5, INV-7)


def test_orchestrator_never_holds_action_tools_and_workers_hold_only_them() -> None:
    """AC-5, INV-5, INV-7, D-24: every orchestrator call offers exactly the extras, SEARCH and FETCH tools, run_episode, patch_goal and isDone; every worker call offers the ACTION tools and nothing else but isDone, starting from the episode prompt."""
    agent = build_agent(tools=(note_lead,))
    model = ScriptedModel(_one_episode([tool_call("browser_navigate", {"url": "https://seedcamp.com/apply"}), card("done", "Opened the page.")]))
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
    model.assert_complete()
    orchestrator = model.calls_by(NAME)
    assert len(orchestrator) == 2
    for call in orchestrator:
        assert len(call.tools) == len(set(call.tools)), f"a tool is offered twice: {call.tools}"
        assert set(call.tools) == {"note_lead", "firecrawl_search", "fetch_markdown", "run_episode", "patch_goal", "isDone"}
    workers = model.calls_by(worker(1))
    assert len(workers) == 2
    for call in workers:
        assert set(call.tools) - {"isDone"} == set(ACTION_TOOLS), f"worker tools: {call.tools}"
    first = workers[0]
    assert template_regex(prompt_text("episode_prompt"), index=1, task=EPISODE["task"], done_when=EPISODE["done_when"]).fullmatch(first.prompt.strip())
    assert first.messages == []
    # D-24: the worker's rules are the developer's prompt plus the worker leaf; the orchestrator's carry the orchestrator leaf.
    worker_rules = distinctive_line("worker_system_prompt", "orchestrator_system_prompt")
    orchestrator_rules = distinctive_line("orchestrator_system_prompt", "worker_system_prompt")
    assert SYSTEM_PROMPT in first.system and worker_rules in first.system
    assert SYSTEM_PROMPT in orchestrator[0].system and orchestrator_rules in orchestrator[0].system
    assert orchestrator_rules not in first.system and worker_rules not in orchestrator[0].system


# ---------------------------------------------------------------- the action cap (INV-9)


def test_action_cap_stops_the_worker_and_returns_a_stuck_card_with_evidence() -> None:
    """AC-7, INV-9, INV-12, EC-11: with max_actions=3 and a worker that never stops calling, exactly three calls reach the server, the worker makes no fourth model call, and the stuck card carries max_tool_calls, actions 3, and the third result's first BROWSER_STALE_OBSERVATION_CHARS characters as its only evidence."""
    from vidbyte.lib.constants.browser import BROWSER_STALE_OBSERVATION_CHARS

    results: list[str] = []
    visits = itertools.count(1)

    def navigate(args: Mapping[str, Any]) -> dict[str, Any]:
        text = f"Visit {next(visits)} of {args.get('url')}: " + _letters(3 * BROWSER_STALE_OBSERVATION_CHARS)
        results.append(text)
        return text_result(text)

    servers = FakeBrowserServers()
    servers.add(ACTION_COMMAND, "browser_navigate", navigate)
    agent = build_agent(max_actions=3)
    model = ScriptedModel(_one_episode([forever(tool_call("browser_navigate", {"url": "https://seedcamp.com/apply"}))]))
    with installed(model, servers):
        result = agent.run(TASK)
    model.assert_complete()
    assert len(servers.calls_to(ACTION_COMMAND)) == 3
    assert len(model.calls_by(worker(1))) == 3, "the worker made a model call after its third action"
    assert "max_tool_calls: 0/3" in model.first_call(worker(1)).system
    (episode,) = agent.response.episodes
    assert (episode.index, episode.outcome, episode.stop_reason, episode.actions) == (1, "stuck", "max_tool_calls", 3)
    assert episode.evidence == (results[2][:BROWSER_STALE_OBSERVATION_CHARS],)
    assert template_regex(prompt_text("stuck_summary"), reason="max_tool_calls").fullmatch(episode.summary.strip())
    # The orchestrator receives the card as a normal result and goes on to answer.
    ((name, content),) = tool_results(model.calls_by(NAME)[1])
    assert name == "run_episode" and not is_error(content)
    assert template_regex(prompt_text("result_card"), index=1, outcome="stuck").search(content)
    assert result.content == FINAL


def test_a_call_past_the_action_cap_in_the_same_turn_is_not_executed() -> None:
    """INV-9: with max_actions=3 and two calls per turn, the fourth call in the second turn never reaches the server and the card counts three actions."""
    agent = build_agent(max_actions=3)
    pair = tool_calls(("browser_click", {"element": "Next"}), ("browser_click", {"element": "Next"}))
    model = ScriptedModel(_one_episode([pair, forever(pair)]))
    servers = FakeBrowserServers()
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    assert len(servers.calls_to(ACTION_COMMAND)) == 3
    assert len(model.calls_by(worker(1))) == 2
    (episode,) = agent.response.episodes
    assert (episode.outcome, episode.stop_reason, episode.actions) == ("stuck", "max_tool_calls", 3)


# ---------------------------------------------------------------- the screenshot cap (INV-10)


def test_a_second_screenshot_is_denied_in_context_and_the_worker_finishes_its_card() -> None:
    """AC-8, INV-10: with max_screenshots=1 the second screenshot is denied in context, never reaches the server, the worker makes its next call, and the episode ends with the worker's own card."""
    agent = build_agent(max_screenshots=1)
    model = ScriptedModel(
        _one_episode(
            [
                tool_call("browser_take_screenshot", {}),
                tool_call("browser_take_screenshot", {}),
                card("done", "Saved the deadline screenshot.", evidence=["C:/shots/page-1.png"]),
            ]
        )
    )
    servers = FakeBrowserServers()
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    assert servers.calls_to(ACTION_COMMAND) == [("browser_take_screenshot", {})]
    calls = model.calls_by(worker(1))
    assert len(calls) == 3, "the worker did not get its next model call after the denial"
    results = tool_results(calls[2])
    assert [name for name, _ in results] == ["browser_take_screenshot", "browser_take_screenshot"]
    assert not is_error(results[0][1]) and is_error(results[1][1])
    (episode,) = agent.response.episodes
    assert (episode.outcome, episode.summary, episode.evidence) == ("done", "Saved the deadline screenshot.", ("C:/shots/page-1.png",))
    assert episode.actions == 2, "a denied screenshot still counts toward max_actions"


def test_screenshot_cap_counts_each_screenshot_tool_case_insensitively_and_spares_other_tools() -> None:
    """INV-10, A-1: every ACTION tool whose name contains "screenshot" in any case is capped per tool; a tool without the marker is not."""
    servers = FakeBrowserServers()
    servers.serve(
        ACTION_COMMAND,
        {
            "browser_navigate": lambda args: text_result(f"Navigated to {args.get('url')}"),
            "browser_take_screenshot": lambda args: image_result("Saved screenshot to C:/shots/a.png"),
            "page_SCREENSHOT_full": lambda args: image_result("Saved full-page Screenshot to C:/shots/b.png"),
        },
    )
    agent = build_agent(max_screenshots=1)
    steps = [
        tool_calls(("page_SCREENSHOT_full", {}), ("page_SCREENSHOT_full", {})),
        tool_calls(("browser_take_screenshot", {}), ("browser_take_screenshot", {})),
        tool_calls(*(("browser_navigate", {"url": f"https://seedcamp.com/{page}"}) for page in ("a", "b", "c"))),
        card("done", "Captured both screenshots."),
    ]
    model = ScriptedModel(_one_episode(steps))
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    executed = [name for name, _ in servers.calls_to(ACTION_COMMAND)]
    assert executed.count("page_SCREENSHOT_full") == 1
    assert executed.count("browser_take_screenshot") == 1
    assert executed.count("browser_navigate") == 3
    (episode,) = agent.response.episodes
    assert episode.actions == 7


# ---------------------------------------------------------------- the observation diet (INV-11)


def test_older_observations_are_cut_and_the_newest_is_whole() -> None:
    """AC-9, INV-11: with keep_observations=1 the worker's fourth call carries the first two snapshots cut to BROWSER_STALE_OBSERVATION_CHARS plus the truncation note, and the third whole."""
    from vidbyte.lib.constants.browser import BROWSER_STALE_OBSERVATION_CHARS

    body = _letters(3 * BROWSER_STALE_OBSERVATION_CHARS)
    servers = FakeBrowserServers()
    servers.add(ACTION_COMMAND, "browser_snapshot", lambda args: text_result(f"[{args['tag']}]" + body))
    agent = build_agent(keep_observations=1)
    steps = [tool_call("browser_snapshot", {"tag": tag}) for tag in ("first", "second", "third")] + [card("done", "Read three snapshots.")]
    model = ScriptedModel(_one_episode(steps))
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    fourth = model.calls_by(worker(1))[3]
    snapshots = [content for name, content in tool_results(fourth) if name == "browser_snapshot"]
    assert len(snapshots) == 3
    for tag, content in zip(("first", "second"), snapshots[:2], strict=True):
        original = f"[{tag}]" + body
        assert content[:BROWSER_STALE_OBSERVATION_CHARS] == original[:BROWSER_STALE_OBSERVATION_CHARS]
        note = content[BROWSER_STALE_OBSERVATION_CHARS:]
        assert "truncated" in note and len(content) < len(original), f"{tag} snapshot was not cut: {note[:80]!r}"
        assert original[BROWSER_STALE_OBSERVATION_CHARS : BROWSER_STALE_OBSERVATION_CHARS + 40] not in note
    assert snapshots[2] == "[third]" + body
    # The window cuts only older results: on the second call the first snapshot is still the newest, so it is whole.
    assert tool_results(model.calls_by(worker(1))[1]) == [("browser_snapshot", "[first]" + body)]


def test_worker_history_stays_within_its_token_cap_with_whole_call_groups() -> None:
    """AC-31, INV-11: seventeen distinct ACTION tools with full 8,000-character results pass BROWSER_WORKER_HISTORY_MAX_TOKENS; the next worker call stays under it, keeps the newest call and result, never splits a call from its result, and starts from the episode prompt."""
    from vidbyte.lib.constants.browser import BROWSER_WORKER_HISTORY_MAX_TOKENS
    from vidbyte.lib.util import TokenEstimate

    names = [f"probe_{chr(ord('a') + index)}" for index in range(17)]
    servers = FakeBrowserServers()
    servers.serve(ACTION_COMMAND, {name: (lambda args, letter=chr(ord("A") + index): text_result(letter * 9_000)) for index, name in enumerate(names)})
    agent = build_agent(keep_observations=1)
    model = ScriptedModel(_one_episode([tool_call(name, {}) for name in names] + [card("done", "Probed every tool.")]))
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    calls = model.calls_by(worker(1))
    after = calls[17]
    # Call n+1 always carries call n's result whole (the newest group survives the trim), so these are the full results.
    full = [call.messages[-1]["content"] for call in calls[1:18]]
    assert [call.messages[-1]["name"] for call in calls[1:18]] == names
    assert sum(TokenEstimate.count(text) for text in full) > BROWSER_WORKER_HISTORY_MAX_TOKENS, "the recipe no longer passes the cap"
    assert content_tokens(after.messages) <= BROWSER_WORKER_HISTORY_MAX_TOKENS
    assert len(after.messages) < 2 * 17, "nothing was trimmed"
    assert unpaired(after.messages) == (set(), set()), "a tool call was separated from its result"
    assert after.messages[-2]["role"] == "assistant" and after.messages[-2]["tool_calls"][0]["function"]["name"] == "probe_q"
    assert after.messages[-1]["role"] == "tool" and after.messages[-1]["content"].startswith("Q" * 1_000)
    assert template_regex(prompt_text("episode_prompt"), index=1, task=EPISODE["task"], done_when=EPISODE["done_when"]).fullmatch(after.prompt.strip())


# ---------------------------------------------------------------- stuck cards (INV-12)


def test_a_free_text_worker_reply_becomes_a_stuck_card_with_evidence() -> None:
    """EC-12, INV-12: a worker that keeps answering free text ends contract_unsatisfied, and the stuck card counts its one action and keeps that call's result as evidence."""
    from vidbyte.lib.constants.browser import BROWSER_STALE_OBSERVATION_CHARS

    page = "Seedcamp application page: " + _letters(2 * BROWSER_STALE_OBSERVATION_CHARS)
    servers = FakeBrowserServers()
    servers.add(ACTION_COMMAND, "browser_navigate", lambda args: text_result(page))
    agent = build_agent()
    model = ScriptedModel(_one_episode([tool_call("browser_navigate", {"url": "https://seedcamp.com/apply"}), forever(reply("I looked at the page and it seems fine."))]))
    with installed(model, servers):
        result = agent.run(TASK)
    model.assert_complete()
    (episode,) = agent.response.episodes
    assert (episode.outcome, episode.stop_reason, episode.actions) == ("stuck", "contract_unsatisfied", 1)
    assert episode.evidence == (page[:BROWSER_STALE_OBSERVATION_CHARS],)
    assert template_regex(prompt_text("stuck_summary"), reason="contract_unsatisfied").fullmatch(episode.summary.strip())
    assert result.content == FINAL


def test_a_worker_provider_error_becomes_a_stuck_card_and_the_run_continues() -> None:
    """AC-27, EC-13, D-27: a worker whose model call raises a provider error yields a stuck card with actions None and no evidence, the orchestrator gets it, and a second episode still runs."""
    agent = build_agent()
    model = ScriptedModel(
        {
            NAME: [tool_call("run_episode", EPISODE), tool_call("run_episode", SECOND_EPISODE), reply(FINAL)],
            worker(1): [fail(ProviderRequestError("upstream returned 503", provider="openai", status_code=503))],
            worker(2): [card("done", "Antler is rolling.")],
            RECHECK: [DONE],
        }
    )
    with installed(model, FakeBrowserServers()):
        result = agent.run(TASK)
    model.assert_complete()
    first, second = agent.response.episodes
    assert (first.index, first.outcome, first.actions, first.evidence, first.recipe) == (1, "stuck", None, (), ())
    assert first.stop_reason in {"AgentExecutionError", "ProviderRequestError"}, first.stop_reason
    assert template_regex(prompt_text("stuck_summary"), reason=first.stop_reason).fullmatch(first.summary.strip())
    ((name, content),) = tool_results(model.calls_by(NAME)[1])
    assert name == "run_episode" and not is_error(content)
    assert (second.index, second.outcome) == (2, "done")
    assert result.content == FINAL


@pytest.mark.asyncio
async def test_cancelling_during_an_episode_propagates_and_records_no_card() -> None:
    """AC-27, EC-14: cancelling arun while the second worker waits propagates CancelledError; the first episode's card stays and the second has none."""
    entered = asyncio.Event()
    never = asyncio.Event()

    async def wait_forever(call: ModelCall) -> object:
        entered.set()
        await never.wait()
        return card("done", "unreachable")

    model = ScriptedModel(
        {
            NAME: [tool_call("run_episode", EPISODE), tool_call("run_episode", SECOND_EPISODE)],
            worker(1): [card("done", "Seedcamp closes 30 November.")],
            worker(2): [wait_forever],
        }
    )
    log = EventLog(model)
    agent = build_agent(on_event=log)
    with installed(model, FakeBrowserServers()):
        run = asyncio.ensure_future(agent.arun(TASK))
        waiter = asyncio.ensure_future(entered.wait())
        try:
            await asyncio.wait({run, waiter}, return_when=asyncio.FIRST_COMPLETED)
            assert entered.is_set(), f"the second worker never started; the run ended with {run.exception() if run.done() else None!r}"
            run.cancel()
            with pytest.raises(asyncio.CancelledError):
                await run
        finally:
            waiter.cancel()
            await agent.close_mcp_servers()
    assert [episode.index for episode in agent.response.episodes] == [1]
    assert [event.episode for event in log.of("episode_finished")] == [1]


# ---------------------------------------------------------------- outcomes and recipes


def test_ready_to_submit_is_recorded_and_nothing_acts_on_it() -> None:
    """AC-17, INV-19: a worker that returns ready_to_submit is recorded with that outcome and no recipe, and the ACTION server gets no call after the worker's own."""
    agent = build_agent()
    worker_steps = [
        tool_call("browser_navigate", {"url": "https://seedcamp.com/apply"}),
        tool_call("browser_type", {"element": "Company name", "text": "Vidbyte"}),
        card("ready_to_submit", "The application form is filled and ready to submit.", evidence=["C:/shots/page-1.png"]),
    ]
    model = ScriptedModel(_one_episode(worker_steps))
    servers = FakeBrowserServers()
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    (episode,) = agent.response.episodes
    assert (episode.outcome, episode.actions, episode.recipe) == ("ready_to_submit", 2, ())
    assert [name for name, _ in servers.calls_to(ACTION_COMMAND)] == ["browser_navigate", "browser_type"]
    ((_, content),) = tool_results(model.calls_by(NAME)[1])
    assert template_regex(prompt_text("result_card"), index=1, outcome="ready_to_submit").search(content)


def test_a_done_card_records_the_recipe_of_successful_calls_and_the_event_names_only_the_count() -> None:
    """AC-26, D-17, EC-31, T-6: three successful calls and one denied screenshot give actions 4 and a three-step recipe in order with JSON arguments; the recipe_recorded event names only the count, and no event carries the typed secret."""
    secret = "S3cret-Passw0rd-for-the-form"
    url = "https://seedcamp.com/apply"
    log = EventLog()
    agent = build_agent(max_screenshots=1, on_event=log)
    worker_steps = [
        tool_call("browser_navigate", {"url": url}),
        tool_call("browser_type", {"element": "Password", "text": secret}),
        tool_call("browser_take_screenshot", {}),
        tool_call("browser_take_screenshot", {}),
        card("done", "Logged in and saved a screenshot.", evidence=["C:/shots/page-1.png"]),
    ]
    model = ScriptedModel(_one_episode(worker_steps))
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
    model.assert_complete()
    (episode,) = agent.response.episodes
    assert episode.actions == 4
    steps = [(step.tool, json.loads(step.arguments)) for step in episode.recipe]
    assert steps == [("browser_navigate", {"url": url}), ("browser_type", {"element": "Password", "text": secret}), ("browser_take_screenshot", {})]
    (recorded,) = log.of("recipe_recorded")
    assert int_token(3).search(recorded.detail), recorded.detail
    for leaked in (url, secret, "browser_"):
        assert leaked not in recorded.detail
    assert all(secret not in repr(event) for event in log.events)


def test_an_oversized_worker_card_is_capped_on_the_record_and_in_the_orchestrator_view() -> None:
    """INV-6, D-25, section 9.1: a worker card with too many, too long items keeps the first BROWSER_MAX_ITEMS items in order, each within BROWSER_ITEM_MAX_CHARS, a summary within BROWSER_SUMMARY_MAX_CHARS, and the orchestrator sees at most BROWSER_CARD_MAX_TOKENS plus the cut marker."""
    from vidbyte.lib.constants.browser import BROWSER_CARD_CUT_MARKER, BROWSER_CARD_MAX_TOKENS, BROWSER_ITEM_MAX_CHARS, BROWSER_MAX_ITEMS, BROWSER_SUMMARY_MAX_CHARS
    from vidbyte.lib.util import TokenEstimate

    facts = [f"Fact {index:03d} " + _letters(BROWSER_ITEM_MAX_CHARS + 100, index) for index in range(BROWSER_MAX_ITEMS + 10)]
    summary = "Summary " + _letters(BROWSER_SUMMARY_MAX_CHARS + 1_000)
    agent = build_agent()
    model = ScriptedModel(_one_episode([card("done", summary, facts=facts)]))
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
    model.assert_complete()
    (episode,) = agent.response.episodes
    assert len(episode.facts) == BROWSER_MAX_ITEMS
    for kept, original in zip(episode.facts, facts, strict=False):
        assert len(kept) <= BROWSER_ITEM_MAX_CHARS and kept[:40] == original[:40]
    assert len(episode.summary) <= BROWSER_SUMMARY_MAX_CHARS and episode.summary[:40] == summary[:40]
    ((_, content),) = tool_results(model.calls_by(NAME)[1])
    assert content.endswith(BROWSER_CARD_CUT_MARKER), "a card over its token cap was not cut"
    assert TokenEstimate.count(content[: -len(BROWSER_CARD_CUT_MARKER)]) <= BROWSER_CARD_MAX_TOKENS


def test_two_episodes_in_one_turn_run_one_after_the_other_in_call_order() -> None:
    """INV-8, EC-15: two run_episode calls in one turn run one at a time, in call order, and record indexes 1 and 2."""
    second_started_early: list[bool] = []
    model = ScriptedModel({})

    async def slow_first(call: ModelCall) -> object:
        # Yield to the loop many times; a concurrent second episode would start meanwhile.
        for _ in range(50):
            await asyncio.sleep(0)
        second_started_early.append(worker(2) in model.agents_called())
        return card("done", "Seedcamp closes 30 November.")

    model.scripts.update(
        {
            NAME: [tool_calls(("run_episode", EPISODE), ("run_episode", SECOND_EPISODE)), reply(FINAL)],
            worker(1): [slow_first],
            worker(2): [card("done", "Antler is rolling.")],
            RECHECK: [DONE],
        }
    )
    log = EventLog(model)
    agent = build_agent(on_event=log)
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
    model.assert_complete()
    assert second_started_early == [False], "the second episode started before the first one finished"
    assert model.position(f"{worker(1)} answered 1") < model.position(f"{worker(2)} call 1")
    assert [(episode.index, episode.task) for episode in agent.response.episodes] == [(1, EPISODE["task"]), (2, SECOND_EPISODE["task"])]
    order = [(event.kind.value, event.episode) for event in log.events if event.kind.value in {"episode_started", "episode_finished"}]
    assert order == [("episode_started", 1), ("episode_finished", 1), ("episode_started", 2), ("episode_finished", 2)]
    results = tool_results(model.calls_by(NAME)[1])
    assert [name for name, _ in results] == ["run_episode", "run_episode"]


def test_only_the_card_text_reaches_the_orchestrator() -> None:
    """INV-6: the worker's observations and any screenshot payload never reach an orchestrator call; the orchestrator's history gains only the run_episode result."""
    marker = "SNAPSHOT-ONLY-7731 Seedcamp form fields: company, founders, deck."
    servers = FakeBrowserServers()
    servers.add(ACTION_COMMAND, "browser_snapshot", lambda args: text_result(marker))
    agent = build_agent()
    worker_steps = [tool_call("browser_snapshot", {}), tool_call("browser_take_screenshot", {}), card("done", "Read the form fields.")]
    model = ScriptedModel(_one_episode(worker_steps))
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    assert marker in seen_text(model.calls_by(worker(1))[-1]), "positive control: the worker saw its own observation"
    for call in model.calls_by(NAME):
        assert marker not in seen_text(call)
        assert "Saved screenshot to" not in seen_text(call)
    for call in model.calls:
        assert SCREENSHOT_DATA[:64] not in seen_text(call)
    assert [name for name, _ in tool_results(model.calls_by(NAME)[1])] == ["run_episode"]
    assert len(model.calls_by(NAME)[1].messages) == 2


def test_the_developer_permission_policy_binds_every_worker() -> None:
    """T-2, D-16: with a restrictive PermissionPolicy the worker's browser click is denied before it reaches the server, while the orchestrator's SAFE run_episode and patch_goal still work."""
    from vidbyte.lib.dataclasses.security import PermissionPolicy

    agent = build_agent(permission_policy=PermissionPolicy())
    model = ScriptedModel(
        {
            NAME: [tool_call("run_episode", EPISODE), tool_call("patch_goal", {"section": "blockers", "text": "Clicks are not permitted."}), reply(FINAL)],
            worker(1): [tool_call("browser_click", {"element": "Submit application"}), card("blocked", "The click was denied.")],
            RECHECK: [DONE],
        }
    )
    servers = FakeBrowserServers()
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    assert servers.calls_to(ACTION_COMMAND) == []
    ((name, content),) = tool_results(model.calls_by(worker(1))[1])
    assert name == "browser_click" and is_error(content)
    (episode,) = agent.response.episodes
    assert (episode.outcome, episode.actions) == ("blocked", 1)
    assert agent.response.goal.blockers == "Clicks are not permitted."


def test_each_role_is_enforced_by_the_catalog_not_by_the_prompt() -> None:
    """EC-34, INV-5, INV-7: an orchestrator that calls an ACTION tool by name, and a worker that calls a FETCH tool by name, each get an error result, and neither server receives the call."""
    agent = build_agent()
    model = ScriptedModel(
        {
            NAME: [tool_call("browser_click", {"element": "Apply"}), tool_call("run_episode", EPISODE), reply(FINAL)],
            worker(1): [tool_call("fetch_markdown", {"url": "https://seedcamp.com/apply"}), card("stuck", "No fetch tool here.")],
            RECHECK: [DONE],
        }
    )
    servers = FakeBrowserServers()
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    assert servers.calls_to(ACTION_COMMAND) == [] and servers.calls_to(FETCH_COMMAND) == []
    ((name, content),) = tool_results(model.calls_by(NAME)[1])
    assert name == "browser_click" and is_error(content)
    ((name, content),) = tool_results(model.calls_by(worker(1))[1])
    assert name == "fetch_markdown" and is_error(content)


def test_a_failed_browser_call_counts_as_an_action_but_not_a_recipe_step() -> None:
    """D-17: a call the server answers with an error counts toward actions and stays out of the recipe of a done card."""
    servers = FakeBrowserServers()
    servers.add(ACTION_COMMAND, "browser_click", lambda args: error_result("element not found"))
    agent = build_agent()
    worker_steps = [tool_call("browser_navigate", {"url": "https://seedcamp.com/apply"}), tool_call("browser_click", {"element": "Missing"}), card("done", "Read the page without clicking.")]
    model = ScriptedModel(_one_episode(worker_steps))
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    (episode,) = agent.response.episodes
    assert episode.actions == 2
    assert [step.tool for step in episode.recipe] == ["browser_navigate"]
